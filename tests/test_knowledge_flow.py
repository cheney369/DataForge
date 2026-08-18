from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dataforge.application import DataForge
from dataforge.config import Settings
from dataforge.errors import ValidationError
from dataforge.knowledge import KnowledgeService, validate_record


class KnowledgeFlowTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.app = DataForge(
            Settings(project_root=self.root, state_dir=self.root / ".dataforge", dataflow_path=None)
        )
        self.service = KnowledgeService(self.app)

    def tearDown(self):
        self.temporary.cleanup()

    def _ingest(self, name: str, text: str) -> str:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return self.app.sources.ingest(path, name=path.stem).source_version["id"]

    def test_parallel_job_creates_traceable_knowledge_base(self):
        first = self._ingest("guide-a.txt", "高血压患者应定期监测血压并遵医嘱复诊。")
        second = self._ingest("guide-b.md", "# 随访建议\n\n记录症状变化，出现异常时及时就医。")

        job = self.service.create_job(
            name="临床指南文本库",
            knowledge_type_id="text_chunk",
            standard_pipeline_id="std-text-chunk-v1",
            source_version_ids=[first, second],
        )
        finished = self.service.execute_job(job["id"])

        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["progress"], 100)
        self.assertTrue(finished["validation"]["passed"])
        base = self.app.store.get_knowledge_base(finished["knowledge_base_id"])
        self.assertEqual(base["knowledge_type_id"], "text_chunk")
        records = self.app.store.list_knowledge_records(base["id"])
        self.assertEqual({record["source_version_id"] for record in records}, {first, second})
        items = self.app.store.list_knowledge_job_items(job["id"])
        self.assertEqual({item["status"] for item in items}, {"completed"})
        self.assertTrue(all(item["run_id"] and item["asset_version_id"] for item in items))
        lineage = self.service.get_record_lineage(records[0]["id"])
        self.assertEqual(lineage["knowledge_base_name"], "临床指南文本库")
        self.assertIn("chunk_index", lineage["source_locator"])
        self.assertTrue(lineage["source_locator"]["source_excerpt"])

        self.assertEqual(self.app.store.count_knowledge_records(base["id"]), len(records))
        searched = self.app.store.list_knowledge_records(base["id"], limit=10, query="高血压")
        self.assertEqual(len(searched), 1)
        self.assertIn("高血压", searched[0]["data"]["content"])
        events = self.app.store.list_knowledge_job_events(job["id"])
        self.assertEqual(events[0]["event_type"], "created")
        self.assertEqual(events[-1]["event_type"], "published")
        self.assertEqual([event["sequence"] for event in events], list(range(1, len(events) + 1)))

    def test_incompatible_or_unvalidated_pipeline_is_rejected(self):
        source = self._ingest("faq.txt", "如何复诊？请通过门诊预约。")
        with self.assertRaisesRegex(ValidationError, "不兼容"):
            self.service.create_job(
                name="错误组合",
                knowledge_type_id="faq",
                standard_pipeline_id="std-text-chunk-v1",
                source_version_ids=[source],
            )
        with self.assertRaisesRegex(ValidationError, "尚未通过"):
            self.service.create_job(
                name="待验证组合",
                knowledge_type_id="faq",
                standard_pipeline_id="std-faq-text2qa-v1",
                source_version_ids=[source],
            )

    def test_schema_change_creates_new_knowledge_type_version(self):
        original = self.app.store.get_knowledge_type("text_chunk")
        updated_schema = {
            "type": "object",
            "required": ["content", "chunk_index", "title"],
            "properties": {
                "content": "string",
                "chunk_index": "integer",
                "title": "string",
            },
        }

        version = self.app.store.create_knowledge_type_version(
            original["id"],
            "text_chunk_v2",
            original["name"],
            "增加标题字段",
            updated_schema,
        )
        self.service.seed()

        self.assertEqual(version["version"], 2)
        self.assertEqual(version["logical_key"], original["id"])
        self.assertEqual(version["supersedes_id"], original["id"])
        self.assertFalse(self.app.store.get_knowledge_type(original["id"])["active"])
        self.assertTrue(self.app.store.get_knowledge_type(version["id"])["active"])
        with self.assertRaisesRegex(ValidationError, "已停用"):
            self.service.create_job(
                name="旧契约任务",
                knowledge_type_id=original["id"],
                standard_pipeline_id="std-text-chunk-v1",
                source_version_ids=[self._ingest("old-schema.txt", "旧版本")],
            )
    def test_default_pipeline_is_resolved_by_knowledge_type(self):
        source = self._ingest("guide.txt", "患者应遵医嘱定期复诊。")
        job = self.service.create_job(
            name="自动匹配流程",
            knowledge_type_id="text_chunk",
            standard_pipeline_id=None,
            source_version_ids=[source],
        )

        self.assertEqual(job["standard_pipeline_id"], "std-text-chunk-v1")

    def test_csv_record_line_and_chunk_character_range_are_preserved(self):
        csv_source = self._ingest(
            "faq.csv",
            "question,answer\n如何预约,通过医院小程序预约\n何时复诊,两周后复诊\n",
        )
        job = self.service.create_job(
            name="CSV 溯源验证",
            knowledge_type_id="text_chunk",
            standard_pipeline_id="std-text-chunk-v1",
            source_version_ids=[csv_source],
        )

        finished = self.service.execute_job(job["id"])
        records = self.app.store.list_knowledge_records(finished["knowledge_base_id"])
        line_numbers = {
            self.service.get_record_lineage(record["id"])["source_locator"]["line_number"]
            for record in records
        }

        self.assertEqual(line_numbers, {2, 3})
        for record in records:
            locator = self.service.get_record_lineage(record["id"])["source_locator"]
            self.assertEqual(locator["kind"], "csv")
            self.assertGreaterEqual(locator["chunk_character_start"], 0)
            self.assertGreater(locator["chunk_character_end"], locator["chunk_character_start"])

    def test_fixed_schema_validation(self):
        schema = self.app.store.get_knowledge_type("knowledge_triple")["schema"]
        self.assertEqual(validate_record({"subject": "A", "predicate": "属于", "object": "B"}, schema), [])
        self.assertEqual(validate_record({"subject": "A", "predicate": "属于"}, schema), ["缺少字段：object"])

    def test_standard_pipeline_keeps_frozen_dataflow_release(self):
        snapshot = {
            "upstream_pipeline_id": "pipeline-1",
            "config": {"operators": [{"name": "Cleaner"}]},
            "config_hash": "abc123",
        }
        pipeline = self.app.store.register_standard_pipeline(
            "std-custom-v2",
            "已发布清洗流程",
            "text_chunk",
            "studio:pipeline-1",
            "dataflow-studio",
            2,
            "测试发布快照",
            self.app.store.get_knowledge_type("text_chunk")["schema"],
            "validated",
            pipeline_snapshot=snapshot,
            pipeline_hash="abc123",
            sample_task_id="task-1",
        )

        self.assertEqual(pipeline["pipeline_snapshot"], snapshot)
        self.assertEqual(pipeline["pipeline_hash"], "abc123")
        self.assertEqual(pipeline["sample_task_id"], "task-1")

        released_default = self.app.store.register_standard_pipeline(
            "std-text-chunk-v1",
            "冻结后的默认流程",
            "text_chunk",
            "studio:pipeline-1",
            "dataflow-studio",
            2,
            "不应被启动种子覆盖",
            self.app.store.get_knowledge_type("text_chunk")["schema"],
            "validated",
            True,
            snapshot,
            "abc123",
            "task-1",
        )
        self.service.seed()
        preserved = self.app.store.get_standard_pipeline("std-custom-v2")
        default_release = self.app.store.get_standard_pipeline("std-text-chunk-v1")

        self.assertEqual(preserved["pipeline_snapshot"], snapshot)
        self.assertEqual(default_release["name"], released_default["name"])
        self.assertEqual(default_release["pipeline_snapshot"], snapshot)
        self.assertEqual(default_release["version"], 2)
        with self.assertRaisesRegex(ValidationError, "不可覆盖"):
            self.app.store.register_standard_pipeline(
                "std-custom-v2",
                "试图覆盖发布版本",
                "text_chunk",
                "studio:pipeline-changed",
                "dataflow-studio",
                3,
                "不允许覆盖",
                self.app.store.get_knowledge_type("text_chunk")["schema"],
                "validated",
                pipeline_snapshot={"config": {"operators": []}},
                pipeline_hash="changed",
                sample_task_id="task-changed",
            )

    def test_inactive_pipeline_keeps_history_but_rejects_new_jobs(self):
        source = self._ingest("inactive.txt", "患者应定期复诊。")
        pipeline = self.app.store.register_standard_pipeline(
            "std-retired-v1",
            "即将停用的流程",
            "text_chunk",
            "studio:retired",
            "dataflow-studio",
            1,
            "停用治理测试",
            self.app.store.get_knowledge_type("text_chunk")["schema"],
            "validated",
            pipeline_snapshot={"config": {"operators": [{"name": "Cleaner"}]}},
            pipeline_hash="retired",
            sample_task_id="task-retired",
        )

        inactive = self.app.store.deactivate_standard_pipeline(pipeline["id"])

        self.assertFalse(inactive["active"])
        self.assertEqual(inactive["validation_status"], "inactive")
        self.assertIn(
            pipeline["id"],
            {item["id"] for item in self.app.store.list_standard_pipelines()},
        )
        with self.assertRaisesRegex(ValidationError, "尚未通过"):
            self.service.create_job(
                name="不可使用停用流程",
                knowledge_type_id="text_chunk",
                standard_pipeline_id=pipeline["id"],
                source_version_ids=[source],
            )

    def test_failed_job_retry_creates_a_new_auditable_attempt(self):
        source = self._ingest("retry.txt", "患者应定期监测血压并记录结果。")
        original = self.service.create_job(
            name="可重试知识库",
            knowledge_type_id="text_chunk",
            standard_pipeline_id="std-text-chunk-v1",
            source_version_ids=[source],
        )
        self.app.store.update_knowledge_job(
            original["id"],
            status="failed",
            error="temporary failure",
        )

        retry = self.service.retry_job(original["id"])

        self.assertNotEqual(retry["id"], original["id"])
        self.assertEqual(retry["retry_of_job_id"], original["id"])
        self.assertEqual(retry["attempt_no"], 2)
        self.assertEqual(retry["status"], "pending")
        with self.assertRaisesRegex(ValidationError, "已经创建后续尝试"):
            self.service.retry_job(original["id"])

        completed = self.service.execute_job(retry["id"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(self.app.store.get_knowledge_job(original["id"])["status"], "failed")
        detail = self.service.get_job_detail(original["id"])
        self.assertEqual(detail["retry_job"]["id"], retry["id"])

    def test_pending_job_can_be_cancelled_and_retried_without_publishing(self):
        source = self._ingest("cancel.txt", "患者应按计划复诊。")
        original = self.service.create_job(
            name="取消任务验证",
            knowledge_type_id="text_chunk",
            standard_pipeline_id="std-text-chunk-v1",
            source_version_ids=[source],
        )

        cancelled = self.service.cancel_job(original["id"])

        self.assertEqual(cancelled["status"], "cancelled")
        self.assertTrue(cancelled["cancel_requested"])
        self.assertIsNotNone(cancelled["cancelled_at"])
        detail = self.service.get_job_detail(original["id"])
        self.assertEqual(detail["items"][0]["status"], "cancelled")
        self.assertEqual(detail["events"][-1]["event_type"], "cancel_requested")
        self.assertIsNone(detail["knowledge_base_id"])
        with self.assertRaisesRegex(ValidationError, "等待处理"):
            self.service.execute_job(original["id"])

        retry = self.service.retry_job(original["id"])
        self.assertEqual(retry["attempt_no"], 2)
        self.assertEqual(self.service.execute_job(retry["id"])["status"], "completed")

    def test_interrupted_attempt_is_failed_on_service_recovery(self):
        source = self._ingest("interrupted.txt", "患者应记录每日血压。")
        job = self.service.create_job(
            name="中断恢复验证",
            knowledge_type_id="text_chunk",
            standard_pipeline_id="std-text-chunk-v1",
            source_version_ids=[source],
        )
        self.app.store.update_knowledge_job(job["id"], status="running", progress=35)
        self.app.store.update_knowledge_job_item(
            job["id"],
            source,
            status="running",
        )

        recovered = self.service.recover_interrupted_jobs()

        self.assertEqual(recovered, [job["id"]])
        failed = self.app.store.get_knowledge_job(job["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("服务进程", failed["error"])
        item = self.app.store.list_knowledge_job_items(job["id"])[0]
        self.assertEqual(item["status"], "failed")
        self.assertEqual(
            self.app.store.list_knowledge_job_events(job["id"])[-1]["event_type"],
            "recovered",
        )
        self.assertEqual(self.service.retry_job(job["id"])["attempt_no"], 2)


if __name__ == "__main__":
    unittest.main()
