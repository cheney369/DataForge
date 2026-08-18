from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dataforge.application import DataForge
from dataforge.config import Settings
from dataforge.errors import ValidationError
from dataforge.indexing.embeddings import EmbeddingBatch
from dataforge.knowledge import KnowledgeService


class DeliveryEmbeddingClient:
    def __init__(self, config):
        self.config = config

    def embed(self, texts):
        vectors = []
        for text in texts:
            vectors.append([
                float(sum(ord(char) for char in text) % 17 + 1),
                float(len(text) % 11 + 1),
                1.0,
                2.0,
            ])
        return EmbeddingBatch(vectors, len(texts), self.config["model"])

    def test(self):
        return {"status": "ready", "model": self.config["model"], "dimension": 4}


class DeliveryFlowTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.app = DataForge(
            Settings(project_root=root, state_dir=root / ".dataforge", dataflow_path=None)
        )
        self.knowledge = KnowledgeService(self.app)
        self.base_ids = []
        for filename, name, content in (
            ("blood-pressure.txt", "血压管理指南", "高血压患者应每天记录血压。"),
            ("follow-up.txt", "复诊管理指南", "患者应按医嘱定期复诊并记录症状。"),
        ):
            path = root / filename
            path.write_text(content, encoding="utf-8")
            version = self.app.sources.ingest(path).source_version
            job = self.knowledge.create_job(
                name=name,
                knowledge_type_id="text_chunk",
                standard_pipeline_id="std-text-chunk-v1",
                source_version_ids=[version["id"]],
            )
            completed = self.knowledge.execute_job(job["id"])
            self.base_ids.append(completed["knowledge_base_id"])

        repository = self.app.indexing.repository
        embedding = repository.save_embedding_service({
            "name": "集合测试模型", "base_url": "http://embedding.test/v1",
            "model": "collection-embedding", "dimension": 4, "batch_size": 8,
            "concurrency": 1, "timeout_seconds": 2, "max_retries": 0,
        })
        vector = repository.save_vector_store({
            "name": "集合内存向量库", "kind": "memory", "uri": "memory://delivery",
            "database_name": "default", "collection_prefix": "delivery",
        })
        self.profile = repository.create_index_profile({
            "name": "集合文本索引", "knowledge_type_id": "text_chunk",
            "embedding_service_id": embedding["id"], "vector_store_id": vector["id"],
            "config": {
                "embedding_template": "{{ content }}", "stored_fields": ["content", "chunk_index"],
                "metadata_fields": ["source_locator"], "filter_fields": [],
                "missing_policy": "error", "metric_type": "COSINE",
            },
        })

    def tearDown(self):
        self.temporary.cleanup()

    @patch("dataforge.indexing.service.OpenAIEmbeddingClient", DeliveryEmbeddingClient)
    def test_versioned_collection_latest_and_pinned_application_delivery(self):
        repository = self.app.indexing.repository
        published = self.app.indexing.publish_profile(self.profile["id"], make_default=True)
        for base_id in self.base_ids:
            created = self.app.indexing.create_index(base_id, published["id"])
            self.assertEqual(
                self.app.indexing.execute_job(created["index_job"]["id"])["status"],
                "completed",
            )
        retrieval = repository.create_retrieval_profile({
            "name": "集合检索契约", "index_profile_id": published["id"],
            "config": {
                "top_k": 5, "score_threshold": 0,
                "return_fields": ["content", "chunk_index"],
                "context_template": "{{ content }}", "context_separator": "\n---\n",
            },
        })
        retrieval = self.app.indexing.publish_retrieval_profile(retrieval["id"])

        collection = self.app.delivery.create_collection(
            "慢病随访知识集合", "跨知识库交付", "text_chunk"
        )
        first = self.app.delivery.create_version(
            collection["id"], retrieval["id"], self.base_ids
        )
        first = self.app.delivery.publish_version(first["id"], make_current=True)
        self.assertEqual(first["status"], "published")
        self.assertEqual(len(first["members"]), 2)

        latest_binding = self.app.delivery.create_binding({
            "binding_key": "chronic-care", "name": "慢病应用",
            "collection_id": collection["id"], "follow_latest": True,
        })
        pinned_binding = self.app.delivery.create_binding({
            "binding_key": "chronic-care-v1", "name": "慢病应用回归基线",
            "collection_id": collection["id"], "collection_version_id": first["id"],
            "follow_latest": False,
        })
        with self.assertRaisesRegex(ValidationError, "应用标识已存在"):
            self.app.delivery.create_binding({
                "binding_key": "chronic-care", "name": "重复应用",
                "collection_id": collection["id"], "follow_latest": True,
            })
        first_result = self.app.delivery.query_binding(
            latest_binding["binding_key"], "患者平时应注意什么？"
        )
        self.assertEqual(
            {item["collection_member"]["knowledge_base_id"] for item in first_result["results"]},
            set(self.base_ids),
        )
        self.assertIn("记录血压", first_result["context"])
        self.assertIn("定期复诊", first_result["context"])

        second = self.app.delivery.create_version(
            collection["id"], retrieval["id"], [self.base_ids[0]]
        )
        second = self.app.delivery.publish_version(second["id"], make_current=True)
        latest_result = self.app.delivery.query_binding("chronic-care", "记录什么？")
        pinned_result = self.app.delivery.query_binding("chronic-care-v1", "注意什么？")

        self.assertEqual(latest_result["collection"]["version"], 2)
        self.assertEqual(len(latest_result["results"]), 1)
        self.assertEqual(pinned_result["collection"]["version"], 1)
        self.assertEqual(len(pinned_result["results"]), 2)
        self.assertEqual(latest_binding["follow_latest"], True)
        self.assertEqual(pinned_binding["pinned_version"], 1)


if __name__ == "__main__":
    unittest.main()
