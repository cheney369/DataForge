from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from dataforge.config import Settings
from dataforge.web import create_app


class DataForgeWebTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        settings = Settings(
            project_root=self.root,
            state_dir=self.root / ".dataforge",
            dataflow_path=None,
        )
        self.client = TestClient(create_app(settings))

    def tearDown(self):
        self.client.close()
        self.temporary.cleanup()

    def test_web_api_covers_source_to_asset_lifecycle(self):
        uploaded = self.client.post(
            "/api/sources",
            data={"name": "门诊随访", "kind": "medical_document"},
            files={"file": ("follow-up.txt", "患者血压稳定。\n建议一个月后复诊。", "text/plain")},
        )
        self.assertEqual(uploaded.status_code, 201)
        ingestion = uploaded.json()
        self.assertEqual(ingestion["source_version"]["original_filename"], "follow-up.txt")

        sources = self.client.get("/api/sources").json()
        self.assertEqual(sources[0]["version_count"], 1)
        self.assertEqual(len(sources[0]["versions"]), 1)

        started = self.client.post(
            "/api/runs",
            json={
                "source_version_id": ingestion["source_version"]["id"],
                "pipeline_id": "medical-document-v1",
                "engine": "native",
            },
        )
        self.assertEqual(started.status_code, 202)
        run_id = started.json()["id"]
        run_detail = self.client.get(f"/api/runs/{run_id}").json()
        self.assertEqual(run_detail["run"]["status"], "completed")
        self.assertEqual(run_detail["events"][-1]["event_type"], "completed")

        assets = self.client.get("/api/assets").json()
        self.assertEqual(len(assets), 1)
        asset_id = assets[0]["id"]
        versions = self.client.get(f"/api/assets/{asset_id}/versions").json()
        version_id = versions[0]["id"]

        preview = self.client.get(f"/api/asset-versions/{version_id}/preview").json()
        self.assertGreater(len(preview), 0)
        lineage = self.client.get(f"/api/asset-versions/{version_id}/lineage").json()
        self.assertEqual(lineage["run_id"], run_id)
        download = self.client.get(f"/api/asset-versions/{version_id}/download")
        self.assertEqual(download.status_code, 200)
        self.assertIn("患者血压稳定", download.text)

        dashboard = self.client.get("/api/dashboard").json()
        self.assertEqual(dashboard["counts"], {"sources": 1, "source_versions": 1, "runs": 1, "assets": 1})
        self.assertEqual(dashboard["run_summary"]["completed"], 1)

    def test_api_returns_structured_validation_errors(self):
        response = self.client.post(
            "/api/runs",
            json={"source_version_id": "missing", "engine": "native"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "NotFoundError")

    def test_modular_api_contract_keeps_public_paths(self):
        paths = set(self.client.get("/openapi.json").json()["paths"])
        expected = {
            "/api/health",
            "/api/liveness",
            "/api/readiness",
            "/api/parser-capabilities",
            "/api/dashboard",
            "/api/sources",
            "/api/sources/{source_id}/versions",
            "/api/source-versions/{source_version_id}/preview",
            "/api/source-versions/{source_version_id}/download",
            "/api/knowledge-types",
            "/api/knowledge-types/{type_id}/versions",
            "/api/standard-pipelines",
            "/api/knowledge-jobs",
            "/api/knowledge-bases",
            "/api/runs",
            "/api/assets",
            "/api/dataflow-studio/status",
            "/api/dataflow-health",
            "/api/dataflow-pipelines/{pipeline_id}",
            "/api/dataflow-tasks/{task_id}",
            "/api/dataflow-datasets",
            "/api/dataflow-operators",
            "/api/dataflow-schemas",
            "/api/dataflow-servings",
            "/api/dataflow-text2qa/activate",
            "/api/dataflow-conversation/configure",
            "/api/knowledge-jobs/{job_id}/retry",
            "/api/knowledge-jobs/{job_id}/cancel",
            "/api/standard-pipelines/{pipeline_id}/deactivate",
            "/api/embedding-services",
            "/api/llm-services",
            "/api/llm-services/{service_id}/test",
            "/api/embedding-services/{service_id}/test",
            "/api/reranker-services",
            "/api/reranker-services/{service_id}/test",
            "/api/vector-stores",
            "/api/vector-stores/{store_id}/test",
            "/api/graph-stores",
            "/api/index-profiles",
            "/api/index-profiles/{profile_id}/preview",
            "/api/index-profiles/{profile_id}/publish",
            "/api/knowledge-indexes",
            "/api/index-jobs",
            "/api/index-jobs/{job_id}/retry",
            "/api/retrieval-profiles",
            "/api/retrieval/query",
            "/api/knowledge-collections",
            "/api/knowledge-collections/{collection_id}/versions",
            "/api/collection-versions/{version_id}",
            "/api/collection-versions/{version_id}/publish",
            "/api/collection-versions/{version_id}/query",
            "/api/application-bindings",
            "/api/application-bindings/{binding_id}/repoint",
            "/api/application-access/{binding_key}/query",
            "/api/ai-applications",
            "/api/ai-applications/{application_id}/versions",
            "/api/ai-application-versions/{version_id}/publish",
            "/api/ai-application-versions/{version_id}/preview",
            "/api/ai-applications/{application_id}/credentials",
            "/api/ai-application-credentials/{credential_id}/revoke",
            "/api/ai-application-runs",
            "/api/ai-applications/{app_key}/chat",
            "/v1/apps/{app_key}/invoke",
            "/v1/apps/{app_key}/versions/{version_number}/invoke",
            "/v1/application-configs/{app_key}",
            "/v1/application-configs/{app_key}/versions/{version_number}",
        }
        self.assertTrue(expected.issubset(paths), expected - paths)

    def test_deployment_endpoints_distinguish_liveness_and_readiness(self):
        liveness = self.client.get("/api/liveness")
        readiness = self.client.get("/api/readiness")

        self.assertEqual(liveness.status_code, 200)
        self.assertEqual(liveness.json()["status"], "alive")
        self.assertEqual(readiness.status_code, 200)
        self.assertTrue(readiness.json()["ready"])
        self.assertEqual(readiness.json()["status"], "degraded")
        self.assertEqual(
            {item["id"] for item in readiness.json()["checks"]},
            {"state", "database", "frontend", "dataflow", "model_storage"},
        )

    def test_application_serving_requires_bearer_credential(self):
        response = self.client.post(
            "/v1/apps/missing-app/invoke",
            json={"inputs": {"query": "test"}},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "AuthenticationError")
        self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_index_resources_and_projection_are_configurable_through_api(self):
        resources = self.client.get("/api/embedding-services").json()
        llms = self.client.get("/api/llm-services").json()
        rerankers = self.client.get("/api/reranker-services").json()
        vectors = self.client.get("/api/vector-stores").json()
        profiles = self.client.get("/api/index-profiles").json()

        self.assertEqual(resources[0]["model"], "bce-embedding-base")
        self.assertEqual(llms[0]["model"], "Qwen3-32B")
        self.assertEqual(rerankers[0]["model"], "bge-reranker-large")
        self.assertEqual(resources[0]["dimension"], 768)
        self.assertEqual(vectors[0]["kind"], "milvus")
        self.assertEqual(
            {item["knowledge_type_id"] for item in profiles},
            {"text_chunk", "faq", "knowledge_triple", "multi_turn_dialogue"},
        )
        faq = next(item for item in profiles if item["knowledge_type_id"] == "faq")
        preview = self.client.get(f"/api/index-profiles/{faq['id']}/preview")
        self.assertEqual(preview.status_code, 200)
        self.assertIn("示例question", preview.json()["indexed_text"])
        self.assertEqual(
            set(preview.json()["metadata"]["stored"]), {"question", "answer"}
        )

    def test_optional_mineru_is_reported_without_blocking_native_parsing(self):
        capabilities = self.client.get("/api/parser-capabilities").json()

        self.assertTrue(capabilities["native"]["available"])
        self.assertTrue(capabilities["native"]["in_use"])
        self.assertFalse(capabilities["mineru"]["in_use"])
        self.assertIn(capabilities["mineru"]["integration_state"], {"reserved", "disabled"})

    def test_source_versions_can_be_filtered_previewed_and_downloaded(self):
        payload = "标题：复诊注意事项\n\n请记录每日血压，并在一个月后复诊。"
        uploaded = self.client.post(
            "/api/sources",
            data={"name": "门诊复诊指南", "kind": "medical_document"},
            files={"file": ("follow-up-guide.md", payload, "text/markdown")},
        ).json()
        version_id = uploaded["source_version"]["id"]

        matched = self.client.get("/api/sources", params={"query": "复诊", "kind": "md"})
        self.assertEqual(matched.status_code, 200)
        self.assertEqual([source["name"] for source in matched.json()], ["门诊复诊指南"])
        self.assertEqual(self.client.get("/api/sources", params={"query": "不存在"}).json(), [])

        preview = self.client.get(f"/api/source-versions/{version_id}/preview")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["preview_record_count"], 1)
        self.assertIn("每日血压", preview.json()["records"][0]["content"])

        download = self.client.get(f"/api/source-versions/{version_id}/download")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content.decode(), payload)
        self.assertIn("follow-up-guide.md", download.headers["content-disposition"])

    def test_knowledge_catalog_filters_compatible_standard_pipelines(self):
        types = self.client.get("/api/knowledge-types")
        self.assertEqual(types.status_code, 200)
        self.assertEqual(
            {item["id"] for item in types.json()},
            {"text_chunk", "faq", "knowledge_triple", "multi_turn_dialogue"},
        )

        text_pipelines = self.client.get(
            "/api/standard-pipelines", params={"knowledge_type_id": "text_chunk"}
        ).json()
        self.assertEqual([item["id"] for item in text_pipelines], ["std-text-chunk-v1"])
        self.assertEqual(text_pipelines[0]["validation_status"], "validated")

        triple_pipelines = self.client.get(
            "/api/standard-pipelines", params={"knowledge_type_id": "knowledge_triple"}
        ).json()
        self.assertEqual(triple_pipelines, [])

    def test_business_job_uses_default_published_pipeline(self):
        uploaded = self.client.post(
            "/api/sources",
            files={"file": ("guide.txt", "患者应按时复诊并记录症状。", "text/plain")},
        ).json()

        started = self.client.post(
            "/api/knowledge-jobs",
            json={
                "name": "复诊指南知识库",
                "knowledge_type_id": "text_chunk",
                "source_version_ids": [uploaded["source_version"]["id"]],
            },
        )

        self.assertEqual(started.status_code, 202)
        job = self.client.get(f"/api/knowledge-jobs/{started.json()['id']}").json()
        self.assertEqual(job["standard_pipeline_id"], "std-text-chunk-v1")
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["standard_pipeline"]["pipeline_ref"], "medical-document-v1")
        self.assertEqual(job["standard_pipeline"]["engine"], "dataflow")
        self.assertEqual(job["sources"][0]["original_filename"], "guide.txt")
        self.assertEqual(job["executions"][0]["engine"], "native")
        self.assertGreater(job["executions"][0]["record_count"], 0)
        self.assertTrue(job["validation"]["passed"])
        knowledge_base = self.client.get("/api/knowledge-bases").json()[0]
        self.assertEqual(knowledge_base["index_status"], "unindexed")

    def test_failed_knowledge_job_can_be_retried_through_api(self):
        uploaded = self.client.post(
            "/api/sources",
            files={"file": ("retry.txt", "患者应记录每日血压。", "text/plain")},
        ).json()
        store = self.client.app.state.dataforge.store
        failed = store.create_knowledge_job(
            "重试接口验证",
            "text_chunk",
            "std-text-chunk-v1",
            [uploaded["source_version"]["id"]],
        )
        store.update_knowledge_job(failed["id"], status="failed", error="temporary")

        response = self.client.post(f"/api/knowledge-jobs/{failed['id']}/retry")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["attempt_no"], 2)
        self.assertEqual(response.json()["retry_of_job_id"], failed["id"])
        detail = self.client.get(f"/api/knowledge-jobs/{response.json()['id']}").json()
        self.assertEqual(detail["status"], "completed")
        duplicate = self.client.post(f"/api/knowledge-jobs/{failed['id']}/retry")
        self.assertEqual(duplicate.status_code, 400)

    def test_pending_knowledge_job_can_be_cancelled_through_api(self):
        uploaded = self.client.post(
            "/api/sources",
            files={"file": ("cancel.txt", "患者应按计划复诊。", "text/plain")},
        ).json()
        store = self.client.app.state.dataforge.store
        job = store.create_knowledge_job(
            "取消接口验证",
            "text_chunk",
            "std-text-chunk-v1",
            [uploaded["source_version"]["id"]],
        )

        response = self.client.post(f"/api/knowledge-jobs/{job['id']}/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")
        detail = self.client.get(f"/api/knowledge-jobs/{job['id']}").json()
        self.assertEqual(detail["items"][0]["status"], "cancelled")
        duplicate = self.client.post(f"/api/knowledge-jobs/{job['id']}/cancel")
        self.assertEqual(duplicate.status_code, 400)

    def test_knowledge_type_can_be_configured_without_frontend_changes(self):
        created = self.client.post(
            "/api/knowledge-types",
            json={
                "name": "术语知识库",
                "description": "保存术语及其解释。",
                "schema": {
                    "type": "object",
                    "required": ["term", "definition"],
                    "properties": {"term": "string", "definition": "string"},
                },
            },
        )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["name"], "术语知识库")
        self.assertIn(
            created.json()["id"],
            {item["id"] for item in self.client.get("/api/knowledge-types").json()},
        )

        versioned = self.client.post(
            f"/api/knowledge-types/{created.json()['id']}/versions",
            json={
                "name": "术语知识库",
                "description": "增加术语分类。",
                "schema": {
                    "type": "object",
                    "required": ["term", "definition", "category"],
                    "properties": {
                        "term": "string",
                        "definition": "string",
                        "category": "string",
                    },
                },
            },
        )
        self.assertEqual(versioned.status_code, 201)
        self.assertEqual(versioned.json()["version"], 2)
        types = self.client.get("/api/knowledge-types").json()
        original = next(item for item in types if item["id"] == created.json()["id"])
        self.assertFalse(original["active"])

    def test_dataflow_studio_frontend_is_mounted_separately(self):
        project_root = Path(__file__).resolve().parents[1]
        client = TestClient(
            create_app(
                Settings(
                    project_root=project_root,
                    state_dir=self.root / ".studio-test",
                    dataflow_path=None,
                )
            )
        )
        response = client.get("/studio/")
        client.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Vite App", response.text)
        self.assertNotIn("DataForge 知识生产平台", response.text)


if __name__ == "__main__":
    unittest.main()
