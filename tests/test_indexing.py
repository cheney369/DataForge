from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dataforge.application import DataForge
from dataforge.api.helpers import execute_knowledge_job_safely
from dataforge.config import Settings
from dataforge.indexing.embeddings import EmbeddingBatch
from dataforge.errors import ValidationError
from dataforge.knowledge import KnowledgeService


class FakeEmbeddingClient:
    def __init__(self, config):
        self.config = config

    def embed(self, texts):
        vectors = []
        for text in texts:
            checksum = sum(ord(char) for char in text)
            vectors.append([
                float((checksum % 17) + 1),
                float((len(text) % 13) + 1),
                float((checksum % 7) + 1),
                1.0,
            ])
        return EmbeddingBatch(vectors, len(texts) * 3, self.config["model"])

    def test(self):
        return {"status": "ready", "model": self.config["model"], "dimension": 4, "latency_ms": 1}


class FakeRerankerClient:
    calls = []

    def __init__(self, config):
        self.config = config

    def test(self):
        return {"status": "ready", "model": self.config["model"], "latency_ms": 2}

    def rerank(self, query, documents, *, top_n):
        self.calls.append({"query": query, "documents": documents, "top_n": top_n})
        ranked = list(reversed(range(len(documents))))[:top_n]
        return {
            "model": self.config["model"],
            "results": [
                {"index": index, "relevance_score": 0.99 - position * 0.01}
                for position, index in enumerate(ranked)
            ],
            "usage": {"total_tokens": 7},
            "latency_ms": 2,
        }


class IndexingFlowTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.app = DataForge(
            Settings(project_root=self.root, state_dir=self.root / ".dataforge", dataflow_path=None)
        )
        self.knowledge = KnowledgeService(self.app)
        source = self.root / "guide.txt"
        source.write_text("患者应定期监测血压并按医嘱复诊。", encoding="utf-8")
        version_id = self.app.sources.ingest(source).source_version["id"]
        job = self.knowledge.create_job(
            name="随访知识库",
            knowledge_type_id="text_chunk",
            standard_pipeline_id="std-text-chunk-v1",
            source_version_ids=[version_id],
        )
        finished = self.knowledge.execute_job(job["id"])
        self.base_id = finished["knowledge_base_id"]
        repo = self.app.indexing.repository
        self.embedding = repo.save_embedding_service(
            {
                "name": "测试向量模型",
                "provider": "openai-compatible",
                "base_url": "http://embedding.test/v1",
                "model": "test-embedding",
                "dimension": 4,
                "batch_size": 1,
                "concurrency": 1,
                "timeout_seconds": 2,
                "max_retries": 0,
            }
        )
        self.vector_store = repo.save_vector_store(
            {
                "name": "内存向量库",
                "kind": "memory",
                "uri": "memory://indexing-test",
                "database_name": "default",
                "collection_prefix": "test",
            }
        )
        self.profile = repo.create_index_profile(
            {
                "logical_key": "test-text-index",
                "name": "测试文本索引",
                "knowledge_type_id": "text_chunk",
                "embedding_service_id": self.embedding["id"],
                "vector_store_id": self.vector_store["id"],
                "config": {
                    "embedding_template": "{{ content }}",
                    "stored_fields": ["content", "chunk_index"],
                    "metadata_fields": ["source_locator"],
                    "filter_fields": [
                        {"source": "chunk_index", "target": "chunk_index", "type": "integer"}
                    ],
                    "missing_policy": "error",
                    "metric_type": "COSINE",
                },
            }
        )

    def tearDown(self):
        self.temporary.cleanup()

    @patch("dataforge.indexing.service.OpenAIRerankerClient", FakeRerankerClient)
    @patch("dataforge.indexing.service.OpenAIEmbeddingClient", FakeEmbeddingClient)
    def test_profile_index_retrieval_and_lineage_flow(self):
        published = self.app.indexing.publish_profile(
            self.profile["id"], base_id=self.base_id, make_default=True
        )
        self.assertEqual(published["validation_status"], "validated")
        self.assertEqual(published["validation"]["dimension"], 4)

        created = self.app.indexing.create_index(self.base_id)
        completed = self.app.indexing.execute_job(created["index_job"]["id"])
        self.assertEqual(completed["status"], "completed")
        index = self.app.indexing.repository.get_knowledge_index(
            created["knowledge_index"]["id"]
        )
        self.assertEqual(index["status"], "available")
        self.assertEqual(index["record_count"], index["expected_count"])

        retrieval = self.app.indexing.repository.create_retrieval_profile(
            {
                "logical_key": "test-retrieval",
                "name": "测试上下文检索",
                "index_profile_id": published["id"],
                "config": {
                    "top_k": 5,
                    "score_threshold": 0,
                    "return_fields": ["content", "chunk_index"],
                    "context_template": "内容：{{ content }}\n位置：{{ source_locator }}",
                    "context_separator": "\n---\n",
                },
            }
        )
        released = self.app.indexing.publish_retrieval_profile(
            retrieval["id"], base_id=self.base_id
        )
        self.assertEqual(released["validation_status"], "validated")

        result = self.app.indexing.query(
            retrieval["id"], self.base_id, "患者应该何时复诊？", filters={"chunk_index": 0}
        )
        self.assertEqual(len(result["results"]), 1)
        self.assertIn("定期监测血压", result["results"][0]["fields"]["content"])
        self.assertIn("内容：", result["context"])
        self.assertEqual(
            result["results"][0]["source"]["source_version_id"],
            self.app.store.list_knowledge_records(self.base_id)[0]["source_version_id"],
        )
        self.assertFalse(result["reranker"]["enabled"])

        reranker = self.app.indexing.repository.save_reranker_service(
            {
                "name": "测试重排模型",
                "base_url": "http://reranker.test/v1",
                "model": "bge-reranker-large",
                "timeout_seconds": 2,
                "max_retries": 0,
            }
        )
        reranked_profile = self.app.indexing.repository.create_retrieval_profile(
            {
                "name": "测试重排检索",
                "index_profile_id": published["id"],
                "config": {
                    "top_k": 1,
                    "score_threshold": 0,
                    "reranker_enabled": True,
                    "reranker_service_id": reranker["id"],
                    "rerank_candidate_count": 3,
                    "return_fields": ["content"],
                    "context_template": "{{ content }}",
                },
            }
        )
        reranked_profile = self.app.indexing.publish_retrieval_profile(
            reranked_profile["id"], base_id=self.base_id
        )
        reranked = self.app.indexing.query(
            reranked_profile["id"], self.base_id, "患者应该何时复诊？"
        )

        self.assertEqual(reranked["reranker"]["model"], "bge-reranker-large")
        self.assertEqual(reranked["reranker"]["returned_count"], 1)
        self.assertEqual(reranked["results"][0]["score"], 0.99)
        self.assertEqual(reranked["results"][0]["rerank_score"], 0.99)
        self.assertIsNotNone(reranked["results"][0]["vector_score"])
        self.assertEqual(FakeRerankerClient.calls[-1]["top_n"], 1)

        incompatible = self.app.indexing.repository.create_retrieval_profile(
            {
                "name": "错误字段检索",
                "index_profile_id": published["id"],
                "config": {
                    "top_k": 3,
                    "return_fields": ["content"],
                    "context_template": "{{ field_not_stored }}",
                },
            }
        )
        with self.assertRaisesRegex(ValidationError, "上下文模板字段尚未"):
            self.app.indexing.publish_retrieval_profile(incompatible["id"])

    @patch("dataforge.indexing.service.OpenAIEmbeddingClient", FakeEmbeddingClient)
    def test_rebuild_versions_and_idempotent_retry_keep_old_index(self):
        published = self.app.indexing.publish_profile(self.profile["id"], make_default=True)
        first = self.app.indexing.create_index(self.base_id)
        first_job = self.app.indexing.execute_job(first["index_job"]["id"])
        self.assertEqual(first_job["status"], "completed")

        repo = self.app.indexing.repository
        repo.update_index_job(first_job["id"], status="failed", error="simulated restart")
        repo.update_knowledge_index(first["knowledge_index"]["id"], status="failed")
        retry = self.app.indexing.retry_job(first_job["id"])
        retried = self.app.indexing.execute_job(retry["id"])

        self.assertEqual(retried["status"], "completed")
        self.assertEqual(retried["stats"]["embedded_records"], 0)
        second_profile = repo.create_index_profile(
            {
                "logical_key": published["logical_key"],
                "name": "测试文本索引 V2",
                "knowledge_type_id": "text_chunk",
                "embedding_service_id": self.embedding["id"],
                "vector_store_id": self.vector_store["id"],
                "config": {**self.profile["config"], "embedding_template": "文本：{{ content }}"},
            }
        )
        self.assertEqual(second_profile["version"], 2)
        self.assertEqual(second_profile["supersedes_id"], published["id"])
        self.assertEqual(repo.get_index_profile(published["id"])["validation_status"], "validated")

    @patch("dataforge.indexing.service.OpenAIEmbeddingClient", FakeEmbeddingClient)
    def test_published_default_creates_independent_auto_index_after_asset_commit(self):
        self.app.indexing.publish_profile(self.profile["id"], make_default=True)
        source = self.root / "auto-index.txt"
        source.write_text("患者需要每天记录血压。", encoding="utf-8")
        version_id = self.app.sources.ingest(source).source_version["id"]
        job = self.knowledge.create_job(
            name="自动索引知识库",
            knowledge_type_id="text_chunk",
            standard_pipeline_id="std-text-chunk-v1",
            source_version_ids=[version_id],
        )

        execute_knowledge_job_safely(self.knowledge, job["id"])

        completed = self.app.store.get_knowledge_job(job["id"])
        self.assertEqual(completed["status"], "completed")
        indexes = self.app.indexing.repository.list_knowledge_indexes(
            completed["knowledge_base_id"]
        )
        self.assertEqual(len(indexes), 1)
        self.assertEqual(indexes[0]["status"], "available")


if __name__ == "__main__":
    unittest.main()
