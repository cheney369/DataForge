from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from dataforge.integrations.dataflow import DataFlowAdapter, pipeline_config_hash


class FakePipelineRegistry:
    def __init__(self):
        self.pipeline = {
            "id": "pipeline-1",
            "name": "样例流程",
            "config": {"operators": [{"name": "Cleaner", "params": {"threshold": 2}}]},
            "tags": ["sample"],
            "updated_at": "2026-08-11T10:00:00",
        }

    def list_pipelines(self):
        return [self.pipeline]

    def get_pipeline(self, pipeline_id):
        return self.pipeline if pipeline_id == self.pipeline["id"] else None

    def validate_pipeline_config(self, config):
        return SimpleNamespace(model_dump=lambda: {"valid": bool(config.get("operators")), "errors": []})

    def create_pipeline(self, payload):
        self.pipeline = {"id": "pipeline-created", **copy.deepcopy(payload)}
        return self.pipeline


class FakeTaskRegistry:
    def __init__(self):
        self.tasks = {}
        self.update_calls = []
        self.kill_calls = []

    def start_execution(self, config):
        task = {
            "task_id": "task-1",
            "pipeline_id": None,
            "pipeline_config": copy.deepcopy(config),
            "status": "queued",
            "output": {},
            "logs": [],
        }
        self.tasks[task["task_id"]] = task
        return task["task_id"], config, task

    def update(self, task_id, updates):
        self.update_calls.append((task_id, copy.deepcopy(updates)))
        self.tasks[task_id].update(updates)
        return self.tasks[task_id]

    def get(self, task_id):
        return self.tasks.get(task_id)

    def list_executions(self):
        return list(self.tasks.values())

    def get_execution_status(self, task_id):
        task = self.tasks[task_id]
        return {**task, "operators_detail": {"Cleaner": {"status": "completed"}}}

    def get_execution_logs(self, task_id):
        return ["completed"]

    def get_execution_result(self, task_id, limit=5):
        return {
            "task_id": task_id,
            "status": self.tasks[task_id]["status"],
            "sample_data": [{"content": "ok"}],
            "cache_file": "/private/cache/result.jsonl",
        }

    def kill_execution(self, task_id):
        self.kill_calls.append(task_id)
        return task_id in self.tasks


class FakeEngine:
    def run(self, config, task_id, execution_path=None):
        return {
            "task_id": task_id,
            "status": "completed",
            "output": {"execution_results": [{"index": 0}]},
            "logs": ["completed"],
        }


class FakeServingRegistry:
    def __init__(self):
        self.items = {}

    def _get_all(self):
        return self.items

    def _get(self, serving_id):
        item = copy.deepcopy(self.items.get(serving_id))
        return {"id": serving_id, **item} if item else None

    def _set(self, name, cls_name, params):
        serving_id = "dataforge-serving"
        params = copy.deepcopy(params)
        params.append(
            {
                "name": "key_name_of_api_key",
                "value": f"DF_API_KEY_{serving_id}",
            }
        )
        self.items[serving_id] = {
            "name": name,
            "cls_name": cls_name,
            "params": params,
        }
        return serving_id

    def _update(self, serving_id, name=None, params=None):
        self.items[serving_id]["name"] = name or self.items[serving_id]["name"]
        key_param = next(
            item
            for item in self.items[serving_id]["params"]
            if item["name"] == "key_name_of_api_key"
        )
        self.items[serving_id]["params"] = copy.deepcopy(params) + [key_param]
        return True

    def get_serving_classes(self):
        return [
            {
                "cls_name": "APILLMServing_request",
                "params": [
                    {"name": "api_url", "default_value": ""},
                    {"name": "model_name", "default_value": ""},
                    {"name": "temperature", "default_value": 0.0},
                    {"name": "max_workers", "default_value": 10},
                    {"name": "max_retries", "default_value": 5},
                    {"name": "connect_timeout", "default_value": 10.0},
                    {"name": "read_timeout", "default_value": 120.0},
                ],
            }
        ]


class DataFlowAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.tasks = FakeTaskRegistry()
        self.container = SimpleNamespace(
            pipeline_registry=FakePipelineRegistry(),
            task_registry=self.tasks,
            dataset_registry=SimpleNamespace(list=lambda: [], get=lambda _id: None),
            operator_registry=SimpleNamespace(get_op_list=lambda lang="zh": []),
            json_schema_manager=SimpleNamespace(list_all=lambda: []),
            serving_registry=SimpleNamespace(
                _get_all=lambda: {
                    "serving-1": {
                        "name": "FAQ model",
                        "cls_name": "APILLMServing_request",
                        "params": [
                            {
                                "name": "api_url",
                                "value": "https://models.example/v1/chat?token=secret",
                            },
                            {"name": "model_name", "value": "faq-model"},
                            {"name": "key_name_of_api_key", "value": "DATAFORGE_TEST_FAQ_KEY"},
                        ],
                    }
                }
            ),
        )
        self.adapter = DataFlowAdapter(
            self.container,
            FakeEngine(),
            Path(self.temporary.name),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_capture_is_immutable_and_hash_is_deterministic(self):
        first = self.adapter.capture_pipeline("pipeline-1")
        self.assertIsNotNone(first)
        original_hash = first["config_hash"]
        self.assertEqual(original_hash, pipeline_config_hash(first["config"]))

        first["config"]["operators"][0]["params"]["threshold"] = 99
        second = self.adapter.capture_pipeline("pipeline-1")

        self.assertEqual(second["config_hash"], original_hash)
        self.assertEqual(second["config"]["operators"][0]["params"]["threshold"], 2)

    def test_execute_records_pipeline_through_public_registry_api(self):
        result = self.adapter.execute_pipeline(
            "pipeline-1",
            {"input_dataset": "dataset-1", "operators": [{"name": "Cleaner"}]},
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["pipeline_id"], "pipeline-1")
        self.assertEqual(len(self.tasks.update_calls), 2)
        self.assertEqual(self.tasks.update_calls[0], ("task-1", {"pipeline_id": "pipeline-1"}))

    def test_execute_reports_task_id_before_engine_starts(self):
        started = []

        result = self.adapter.execute_pipeline(
            "pipeline-1",
            {"operators": [{"name": "Cleaner"}]},
            on_task_started=started.append,
        )

        self.assertEqual(started, ["task-1"])
        self.assertEqual(result["status"], "completed")

    def test_completed_task_is_not_sent_to_upstream_kill(self):
        self.adapter.execute_pipeline("pipeline-1", {"operators": [{"name": "Cleaner"}]})

        self.assertFalse(self.adapter.cancel_task("task-1"))
        self.assertEqual(self.tasks.kill_calls, [])

    def test_managed_pipeline_is_created_once_by_identity_tag(self):
        created, was_created = self.adapter.ensure_pipeline(
            name="Managed",
            config={"operators": [{"name": "Cleaner"}]},
            identity_tag="dataforge:test-v1",
        )
        created["tags"].append("dataforge:test-v1")
        self.container.pipeline_registry.pipeline = created

        existing, created_again = self.adapter.ensure_pipeline(
            name="Changed name",
            config={"operators": []},
            identity_tag="dataforge:test-v1",
        )

        self.assertTrue(was_created)
        self.assertFalse(created_again)
        self.assertEqual(existing["id"], "pipeline-created")

    def test_task_detail_does_not_expose_config_or_cache_paths(self):
        self.adapter.execute_pipeline("pipeline-1", {"operators": [{"name": "Cleaner"}]})

        detail = self.adapter.get_task_detail("task-1")

        self.assertNotIn("pipeline_config", detail["task"])
        self.assertNotIn("pipeline_config", detail["status"])
        self.assertNotIn("cache_file", detail["result"])
        self.assertEqual(detail["result"]["sample_data"], [{"content": "ok"}])

    def test_serving_facade_reports_readiness_without_exposing_secrets(self):
        os.environ["DATAFORGE_TEST_FAQ_KEY"] = "secret-value"
        try:
            serving = self.adapter.list_servings()[0]
        finally:
            os.environ.pop("DATAFORGE_TEST_FAQ_KEY", None)

        self.assertTrue(serving["ready"])
        self.assertTrue(serving["key_configured"])
        self.assertEqual(serving["api_url"], "https://models.example/v1/chat")
        self.assertNotIn("key_name_of_api_key", serving)
        self.assertNotIn("secret-value", str(serving))

    def test_dataforge_llm_is_mirrored_without_persisting_api_key(self):
        registry = FakeServingRegistry()
        self.container.serving_registry = registry

        serving = self.adapter.ensure_api_llm_serving(
            {
                "id": "llm-qwen",
                "base_url": "https://models.example/v1/",
                "model": "Qwen3-32B",
                "timeout_seconds": 60,
                "max_retries": 1,
                "api_key_env": "",
            }
        )

        self.assertTrue(serving["ready"])
        self.assertEqual(serving["model_name"], "Qwen3-32B")
        self.assertEqual(
            serving["api_url"], "https://models.example/v1/chat/completions"
        )
        saved_param_names = {
            item["name"]
            for item in registry.items["dataforge-serving"]["params"]
        }
        self.assertNotIn("api_key", saved_param_names)
        self.assertEqual(os.environ["DF_API_KEY_dataforge-serving"], "dataforge-internal")
        os.environ.pop("DF_API_KEY_dataforge-serving", None)


if __name__ == "__main__":
    unittest.main()
