from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dataforge.application import DataForge
from dataforge.config import Settings
from dataforge.dataflow_studio import DataFlowStudio, _conversation_config


class FakeHealthAdapter:
    def __init__(self, operators: list[str], ready_servings: set[str] | None = None):
        self.operators = operators
        self.servings = ready_servings or set()

    def list_operators(self):
        return [{"name": name} for name in self.operators]

    def ready_serving_ids(self):
        return set(self.servings)


class DataFlowHealthTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.dataforge = DataForge(
            Settings(project_root=root, state_dir=root / ".dataforge", dataflow_path=None)
        )
        self.studio = DataFlowStudio(self.dataforge.settings)
        self.studio.status.backend_available = True
        self.studio.status.frontend_available = True
        self.studio.status.operator_count = 4
        self.studio.status.pipeline_count = 2
        self.studio.status.message = "DataFlow 已连接"

    def tearDown(self):
        self.temporary.cleanup()

    def test_pipeline_preflight_checks_operators_and_serving(self):
        self.studio.adapter = FakeHealthAdapter(
            ["NormalizeMedicalTextOperator", "Text2QAGenerator"],
            {"serving-ready"},
        )
        config = {
            "operators": [
                {"name": "NormalizeMedicalTextOperator", "params": {}},
                {
                    "name": "Text2QAGenerator",
                    "params": {"llm_serving": "serving-ready"},
                },
            ]
        }

        check = self.studio.preflight_pipeline(config)

        self.assertEqual(check["status"], "ready")
        self.assertTrue(check["requires_serving"])
        self.assertEqual(check["configured_serving_count"], 1)

    def test_conversation_draft_binds_serving_and_schema_adapter(self):
        config = _conversation_config("dataset-1", "serving-ready")

        self.assertEqual(config["input_dataset"], {"id": "dataset-1"})
        self.assertEqual(
            [operator["name"] for operator in config["operators"]],
            ["ConsistentChatGenerator", "ConversationSchemaAdapterOperator"],
        )
        self.assertEqual(
            config["operators"][0]["params"]["prompt_template"],
            "ConsistentChatPrompt",
        )
        self.assertEqual(
            config["operators"][1]["params"],
            {"source_field": "conversation", "target_field": "messages"},
        )

    def test_health_blocks_published_pipeline_with_missing_operator(self):
        self.studio.adapter = FakeHealthAdapter(["NormalizeMedicalTextOperator"])
        schema = self.dataforge.store.get_knowledge_type("text_chunk")["schema"]
        self.dataforge.store.register_standard_pipeline(
            "std-unavailable",
            "依赖缺失流程",
            "text_chunk",
            "studio:pipeline-missing",
            "dataflow-studio",
            1,
            "测试健康检查",
            schema,
            "validated",
            False,
            {
                "config": {
                    "operators": [
                        {"name": "NormalizeMedicalTextOperator"},
                        {"name": "MissingOptionalOperator"},
                    ]
                }
            },
            "hash",
            "task",
        )

        report = self.studio.health_report(self.dataforge)

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["summary"]["published_pipeline_issues"], 1)
        pipeline = next(item for item in report["pipelines"] if item["id"] == "std-unavailable")
        self.assertEqual(pipeline["missing_operators"], ["MissingOptionalOperator"])


if __name__ == "__main__":
    unittest.main()
