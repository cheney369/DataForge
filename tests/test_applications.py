from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dataforge.application import DataForge
from dataforge.config import Settings
from dataforge.errors import AuthenticationError, ValidationError
from dataforge.indexing.embeddings import EmbeddingBatch
from dataforge.knowledge import KnowledgeService


class ApplicationEmbeddingClient:
    def __init__(self, config):
        self.config = config

    def embed(self, texts):
        return EmbeddingBatch(
            [[float(len(text) + 1), 2.0, 3.0, 4.0] for text in texts],
            len(texts), self.config["model"],
        )

    def test(self):
        return {"status": "ready", "model": self.config["model"], "dimension": 4}


class ApplicationChatClient:
    calls = []

    def __init__(self, config):
        self.config = config

    def test(self):
        return {"status": "ready", "model": self.config["model"], "latency_ms": 1}

    def complete(self, messages, *, temperature, max_tokens):
        self.calls.append(messages)
        context_seen = "每天记录血压" in "\n".join(item["content"] for item in messages)
        return {
            "content": "应每天记录血压。" if context_seen else "未找到依据。",
            "model": self.config["model"], "finish_reason": "stop",
            "usage": {"prompt_tokens": 30, "completion_tokens": 8, "total_tokens": 38},
            "latency_ms": 12,
        }

    def stream(self, messages, *, temperature, max_tokens):
        self.calls.append(messages)
        yield {"type": "delta", "content": "应每天"}
        yield {"type": "delta", "content": "记录血压。"}
        yield {
            "type": "complete", "content": "应每天记录血压。",
            "model": self.config["model"], "finish_reason": "stop",
            "usage": {"prompt_tokens": 30, "completion_tokens": 8, "total_tokens": 38},
            "latency_ms": 13,
        }


class AIApplicationFlowTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.app = DataForge(
            Settings(project_root=root, state_dir=root / ".dataforge", dataflow_path=None)
        )
        path = root / "guide.txt"
        path.write_text("高血压患者应每天记录血压。", encoding="utf-8")
        source = self.app.sources.ingest(path).source_version
        knowledge = KnowledgeService(self.app)
        job = knowledge.create_job(
            name="血压知识", knowledge_type_id="text_chunk",
            standard_pipeline_id="std-text-chunk-v1", source_version_ids=[source["id"]],
        )
        self.base_id = knowledge.execute_job(job["id"])["knowledge_base_id"]

    def tearDown(self):
        self.temporary.cleanup()

    @patch("dataforge.applications.service.OpenAIChatClient", ApplicationChatClient)
    @patch("dataforge.indexing.service.OpenAIChatClient", ApplicationChatClient)
    @patch("dataforge.indexing.service.OpenAIEmbeddingClient", ApplicationEmbeddingClient)
    def test_versioned_rag_application_publishes_and_records_run(self):
        repo = self.app.indexing.repository
        embedding = repo.save_embedding_service({
            "name": "应用测试向量", "base_url": "http://embedding.test/v1",
            "model": "app-embedding", "dimension": 4,
        })
        vector = repo.save_vector_store({
            "name": "应用测试存储", "kind": "memory", "uri": "memory://application",
            "database_name": "default", "collection_prefix": "app",
        })
        profile = repo.create_index_profile({
            "name": "应用索引", "knowledge_type_id": "text_chunk",
            "embedding_service_id": embedding["id"], "vector_store_id": vector["id"],
            "config": {
                "embedding_template": "{{ content }}", "stored_fields": ["content"],
                "metadata_fields": ["source_locator"], "filter_fields": [],
                "missing_policy": "error", "metric_type": "COSINE",
            },
        })
        profile = self.app.indexing.publish_profile(profile["id"])
        index_job = self.app.indexing.create_index(self.base_id, profile["id"])
        self.app.indexing.execute_job(index_job["index_job"]["id"])
        retrieval = repo.create_retrieval_profile({
            "name": "应用检索", "index_profile_id": profile["id"],
            "config": {
                "top_k": 3, "score_threshold": 0, "return_fields": ["content"],
                "context_template": "{{ content }}", "context_separator": "\n---\n",
            },
        })
        retrieval = self.app.indexing.publish_retrieval_profile(retrieval["id"])
        collection = self.app.delivery.create_collection("血压集合", "", "text_chunk")
        collection_version = self.app.delivery.create_version(
            collection["id"], retrieval["id"], [self.base_id]
        )
        self.app.delivery.publish_version(collection_version["id"])
        binding = self.app.delivery.create_binding({
            "binding_key": "bp-knowledge", "name": "血压知识接入",
            "collection_id": collection["id"], "follow_latest": True,
        })
        llm = repo.save_llm_service({
            "name": "应用测试 LLM", "base_url": "http://llm.test/v1", "model": "test-chat",
        })
        application = self.app.applications.create_application(
            "bp-assistant", "血压助手", "基于知识回答"
        )
        draft = self.app.applications.create_version(
            application["id"], binding["id"], llm["id"],
            {
                "system_prompt": "你是健康知识助手。仅依据以下资料：\n{{ context }}",
                "user_prompt": "问题：{{ question }}", "temperature": 0.1,
                "max_tokens": 300, "top_k": 3,
            },
        )
        published = self.app.applications.publish_version(draft["id"])
        self.assertEqual(published["status"], "published")
        self.assertEqual(published["validation"]["llm"]["model"], "test-chat")

        public_config = self.app.applications.published_config("bp-assistant")
        self.assertEqual(
            public_config["schema_version"], "dataforge.application-config/v1"
        )
        self.assertEqual(public_config["release"]["version"], 1)
        self.assertEqual(public_config["knowledge"]["binding_key"], "bp-knowledge")
        self.assertEqual(public_config["model"]["model"], "test-chat")
        self.assertNotIn("api_key", public_config["model"])

        response = self.app.applications.chat(
            "bp-assistant", "患者每天需要记录什么？",
            history=[{"role": "user", "content": "我有高血压"},
                     {"role": "assistant", "content": "请遵医嘱管理。"}],
        )

        self.assertEqual(response["answer"], "应每天记录血压。")
        self.assertEqual(response["usage"]["total_tokens"], 38)
        self.assertEqual(response["application"]["version"], 1)
        run = self.app.applications.repository.get_run(response["run_id"])
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["retrieval"]["result_count"], 1)
        self.assertEqual(run["response"]["model"], "test-chat")

        credential = self.app.applications.create_credential(
            application["id"], "应用 A 正式环境"
        )
        self.assertTrue(credential["api_key"].startswith("dfk_"))
        listed = self.app.applications.repository.list_credentials(application["id"])
        self.assertNotIn("api_key", listed[0])
        self.assertNotIn("key_hash", listed[0])

        invoked = self.app.applications.invoke(
            "bp-assistant",
            credential["api_key"],
            {"query": "患者每天需要记录什么？"},
            session_id="session-a",
            user_id="user-a",
            metadata={"source": "application-a"},
        )
        self.assertEqual(invoked["output"], {"answer": "应每天记录血压。"})
        self.assertEqual(invoked["application"]["version"], 1)
        self.assertEqual(len(invoked["citations"]), 1)
        self.assertNotIn("retrieval", invoked)
        invoked_run = self.app.applications.repository.get_run(invoked["request_id"])
        self.assertEqual(invoked_run["request"]["mode"], "production")
        self.assertEqual(invoked_run["request"]["session_id"], "session-a")
        self.assertEqual(invoked_run["request"]["metadata"]["source"], "application-a")

        events = list(self.app.applications.invoke_stream(
            "bp-assistant",
            credential["api_key"],
            {"query": "患者每天需要记录什么？"},
            version_number=1,
        ))
        self.assertEqual([item["event"] for item in events], [
            "start", "retrieval", "delta", "delta", "complete"
        ])
        self.assertEqual(events[-1]["data"]["output"]["answer"], "应每天记录血压。")

        self.app.applications.revoke_credential(credential["id"])
        with self.assertRaises(AuthenticationError):
            self.app.applications.invoke(
                "bp-assistant", credential["api_key"], {"query": "还能调用吗？"}
            )

    def test_application_contract_rejects_unknown_prompt_variables(self):
        application = self.app.applications.create_application("contract-app", "契约应用", "")
        with self.assertRaises(ValidationError):
            self.app.applications._normalize_config({
                "system_prompt": "上下文：{{ context }}",
                "user_prompt": "{{ unsupported }}",
            })


if __name__ == "__main__":
    unittest.main()
