from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .application import DataForge
from .errors import NotFoundError, ValidationError
from .processing.native import split_text


KNOWLEDGE_TYPES = [
    {
        "id": "text_chunk",
        "name": "文本知识库",
        "description": "把长文档整理成可搜索、可引用的文本片段。",
        "schema": {
            "type": "object",
            "required": ["content", "chunk_index"],
            "properties": {"content": "string", "chunk_index": "integer"},
        },
    },
    {
        "id": "faq",
        "name": "问答知识库",
        "description": "从文档中整理常见问题和对应答案。",
        "schema": {
            "type": "object",
            "required": ["question", "answer"],
            "properties": {"question": "string", "answer": "string"},
        },
    },
    {
        "id": "knowledge_triple",
        "name": "知识图谱",
        "description": "提取实体以及实体之间的关系。",
        "schema": {
            "type": "object",
            "required": ["subject", "predicate", "object"],
            "properties": {"subject": "string", "predicate": "string", "object": "string"},
        },
    },
    {
        "id": "multi_turn_dialogue",
        "name": "多轮对话库",
        "description": "把内容整理成有上下文的连续对话。",
        "schema": {
            "type": "object",
            "required": ["messages"],
            "properties": {"messages": "array"},
        },
    },
]


STANDARD_PIPELINES = [
    {
        "id": "std-text-chunk-v1",
        "name": "医疗文档文本分块流程",
        "knowledge_type_id": "text_chunk",
        "pipeline_ref": "medical-document-v1",
        "engine": "dataflow",
        "version": 1,
        "description": "文本标准化、分块和去重；输出已经通过文本块格式验证。",
        "validation_status": "validated",
    },
    {
        "id": "std-faq-text2qa-v1",
        "name": "文档转标准问答流程",
        "knowledge_type_id": "faq",
        "pipeline_ref": "Text2Qa Pipeline",
        "engine": "dataflow-studio",
        "version": 1,
        "description": "来自 DataFlow 的 Text2Qa 流程；完成算力配置和样本验证后启用。",
        "validation_status": "configured",
    },
    {
        "id": "std-dialogue-synthesis-v1",
        "name": "多轮对话生成流程",
        "knowledge_type_id": "multi_turn_dialogue",
        "pipeline_ref": "Text Conversation Synthesis Pipeline",
        "engine": "dataflow-studio",
        "version": 1,
        "description": "来自 DataFlow 的多轮对话流程；完成样本格式验证后启用。",
        "validation_status": "configured",
    },
]


class JobCancelled(Exception):
    """Internal cooperative stop signal for a knowledge production attempt."""


class KnowledgeService:
    def __init__(self, dataforge: DataForge):
        self.dataforge = dataforge
        self.studio: Any | None = None

    def seed(self) -> None:
        store = self.dataforge.store
        schemas: dict[str, dict[str, Any]] = {}
        for item in KNOWLEDGE_TYPES:
            store.register_knowledge_type(item["id"], item["name"], item["description"], item["schema"])
            schemas[item["id"]] = item["schema"]
        for item in STANDARD_PIPELINES:
            try:
                # Published releases are immutable governance records. Startup
                # seeds must not replace their frozen DataFlow snapshot.
                store.get_standard_pipeline(item["id"])
            except NotFoundError:
                store.register_standard_pipeline(
                    item["id"],
                    item["name"],
                    item["knowledge_type_id"],
                    item["pipeline_ref"],
                    item["engine"],
                    item["version"],
                    item["description"],
                    schemas[item["knowledge_type_id"]],
                    item["validation_status"],
                    item["id"] == "std-text-chunk-v1",
                )

    def recover_interrupted_jobs(self) -> list[str]:
        return self.dataforge.store.recover_interrupted_knowledge_jobs()

    def create_job(
        self,
        *,
        name: str,
        knowledge_type_id: str,
        standard_pipeline_id: str | None,
        source_version_ids: list[str],
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValidationError("请填写知识库名称")
        if not source_version_ids:
            raise ValidationError("请至少选择一个源文件版本")
        knowledge_type = self.dataforge.store.get_knowledge_type(knowledge_type_id)
        if not knowledge_type["active"]:
            raise ValidationError("该知识类型版本已停用，请选择当前版本")
        pipeline = (
            self.dataforge.store.get_standard_pipeline(standard_pipeline_id)
            if standard_pipeline_id
            else self.dataforge.store.get_default_standard_pipeline(knowledge_type_id)
        )
        if pipeline["knowledge_type_id"] != knowledge_type_id:
            raise ValidationError("所选标准流程与知识库类型不兼容")
        if pipeline["validation_status"] != "validated" or not pipeline["active"]:
            raise ValidationError("该标准流程尚未通过输出格式验证，不能用于正式加工")
        if pipeline.get("engine") == "dataflow-studio":
            if not self.studio:
                raise ValidationError("DataFlow 运行时当前不可用")
            preflight = self.studio.preflight_pipeline(
                (pipeline.get("pipeline_snapshot") or {}).get("config") or {}
            )
            if preflight["status"] != "ready":
                messages = "；".join(issue["message"] for issue in preflight["issues"])
                raise ValidationError(f"标准流程当前不可运行：{messages}")
        for version_id in dict.fromkeys(source_version_ids):
            self.dataforge.store.get_source_version(version_id)
        return self.dataforge.store.create_knowledge_job(
            name.strip(), knowledge_type_id, pipeline["id"], list(dict.fromkeys(source_version_ids))
        )

    def execute_job(self, job_id: str) -> dict[str, Any]:
        store = self.dataforge.store
        job = store.get_knowledge_job(job_id)
        if job["status"] != "pending":
            raise ValidationError("只有等待处理的任务可以开始执行")
        pipeline = store.get_standard_pipeline(job["standard_pipeline_id"])
        source_ids = job["source_version_ids"]
        store.update_knowledge_job(job_id, status="running", progress=5)
        self._record_event(job_id, "started", "开始执行标准流程")
        try:
            results = []
            with ThreadPoolExecutor(max_workers=min(4, len(source_ids))) as executor:
                self._raise_if_cancelled(job_id)
                futures = {
                    executor.submit(self._execute_job_source, job_id, pipeline, version_id): version_id
                    for version_id in source_ids
                }
                for completed, future in enumerate(as_completed(futures), start=1):
                    results.append(future.result())
                    self._raise_if_cancelled(job_id)
                    progress = 5 + int(completed / len(futures) * 70)
                    store.update_knowledge_job(job_id, status="running", progress=progress)

            self._raise_if_cancelled(job_id)
            self._record_event(job_id, "validating", "正在校验处理结果的输出结构")
            records: list[dict[str, Any]] = []
            validation_errors: list[dict[str, Any]] = []
            input_cache: dict[str, dict[int, dict[str, Any]]] = {}
            for result in results:
                if isinstance(result, dict):
                    output = Path(result["output_file"])
                    source_version = result["source_version"]
                    run_id = None
                    asset_version_id = None
                    input_file = Path(result["input_file"])
                    dataflow_task_id = result["task_id"]
                else:
                    output = self.dataforge.blobs.resolve(result.asset_version["blob_uri"])
                    source_version = result.source_version
                    run_id = result.run["id"]
                    asset_version_id = result.asset_version["id"]
                    input_file = Path(result.run["work_dir"]) / "input" / "source_records.jsonl"
                    dataflow_task_id = None
                raw_records = input_cache.setdefault(str(input_file), _read_source_records(input_file))
                with output.open(encoding="utf-8") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        errors = validate_record(data, pipeline["output_schema"])
                        if errors:
                            validation_errors.append(
                                {
                                    "source_version_id": source_version["id"],
                                    "line": line_number,
                                    "errors": errors,
                                }
                            )
                            continue
                        source_record = raw_records.get(
                            int(data.get("source_record_index") or 0), {}
                        )
                        source_locator = {
                            **(source_record.get("source_locator") or {}),
                            "source_record_index": data.get("source_record_index"),
                            "chunk_index": data.get("chunk_index"),
                            "document_id": data.get("document_id"),
                            "dataflow_task_id": dataflow_task_id,
                            "source_excerpt": _source_excerpt(raw_records, data),
                        }
                        target = str(data.get("content") or "")
                        raw_content = str(source_record.get("raw_content") or "")
                        relative_start = raw_content.find(target) if target else -1
                        if relative_start >= 0:
                            source_locator["chunk_character_start"] = relative_start
                            source_locator["chunk_character_end"] = relative_start + len(target)
                        records.append(
                            {
                                "source_version_id": source_version["id"],
                                "run_id": run_id,
                                "asset_version_id": asset_version_id,
                                "source_locator": source_locator,
                                "data": data,
                            }
                        )

            validation = {
                "passed": not validation_errors,
                "checked_records": len(records) + len(validation_errors),
                "valid_records": len(records),
                "invalid_records": len(validation_errors),
                "errors": validation_errors[:20],
            }
            self._raise_if_cancelled(job_id)
            store.update_knowledge_job(job_id, status="running", progress=85, validation=validation)
            if validation_errors:
                raise ValidationError(f"输出格式验证失败，共 {len(validation_errors)} 条数据不符合知识库格式")
            if not records:
                raise ValidationError("处理结果为空，未生成知识资产")

            self._raise_if_cancelled(job_id)
            self._record_event(
                job_id,
                "validation_completed",
                f"输出结构校验通过，共 {len(records)} 条有效记录",
                {"record_count": len(records)},
            )
            knowledge_base = store.create_knowledge_base(
                job["name"], job["knowledge_type_id"], job["standard_pipeline_id"], job_id, records
            )
            self._record_event(
                job_id,
                "published",
                f"知识资产已入库，共 {len(records)} 条记录",
                {"knowledge_base_id": knowledge_base["id"], "record_count": len(records)},
            )
            try:
                auto_index = self.dataforge.indexing.create_auto_index_job(knowledge_base["id"])
                if auto_index:
                    index_job = auto_index["index_job"]
                    self._record_event(
                        job_id,
                        "index_created",
                        "已根据默认索引方案创建异步索引任务",
                        {
                            "knowledge_index_id": auto_index["knowledge_index"]["id"],
                            "index_job_id": index_job["id"],
                        },
                    )
            except Exception as indexing_error:
                # Indexing is an independent derived stage. Its failure must
                # never invalidate the already committed factual knowledge base.
                self._record_event(
                    job_id,
                    "index_failed",
                    f"知识资产已入库，但自动索引未能启动：{indexing_error}",
                )
            return store.update_knowledge_job(
                job_id,
                status="completed",
                progress=100,
                validation=validation,
                knowledge_base_id=knowledge_base["id"],
            )
        except JobCancelled:
            self._record_event(job_id, "cancelled", "任务已停止，处理结果未发布")
            current = store.get_knowledge_job(job_id)
            if current["status"] != "cancelled":
                return store.update_knowledge_job(job_id, status="cancelled")
            return current
        except Exception as exc:
            if store.is_knowledge_job_cancel_requested(job_id):
                self._record_event(job_id, "cancelled", "任务已停止，处理结果未发布")
                return store.get_knowledge_job(job_id)
            self._record_event(job_id, "failed", f"任务执行失败：{exc}")
            return store.update_knowledge_job(job_id, status="failed", error=str(exc))

    def _raise_if_cancelled(self, job_id: str) -> None:
        if self.dataforge.store.is_knowledge_job_cancel_requested(job_id):
            raise JobCancelled()

    def _record_event(
        self,
        job_id: str,
        event_type: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.dataforge.store.add_knowledge_job_event(
                job_id, event_type, message, detail
            )
        except Exception:
            # Observability must never change the processing result.
            pass

    def _execute_job_source(
        self,
        job_id: str,
        pipeline: dict[str, Any],
        source_version_id: str,
    ) -> Any:
        store = self.dataforge.store
        self._raise_if_cancelled(job_id)
        store.update_knowledge_job_item(job_id, source_version_id, status="running")
        version = store.get_source_version(source_version_id)
        source = store.get_source(version["source_id"])
        source_label = source["name"]
        self._record_event(
            job_id,
            "source_started",
            f"开始处理文档：{source_label}",
            {"source_version_id": source_version_id},
        )
        try:
            if pipeline["pipeline_ref"] == "medical-document-v1":
                engine = "dataflow" if self.dataforge.settings.dataflow_path else "native"
                result = self.dataforge.run(
                    source_version_id,
                    pipeline_id=pipeline["pipeline_ref"],
                    engine_override=engine,
                )
                self._raise_if_cancelled(job_id)
                store.update_knowledge_job_item(
                    job_id,
                    source_version_id,
                    status="completed",
                    run_id=result.run["id"],
                    asset_version_id=result.asset_version["id"],
                )
                self._record_event(
                    job_id,
                    "source_completed",
                    f"文档处理完成：{source_label}",
                    {"source_version_id": source_version_id},
                )
                return result
            if pipeline["pipeline_ref"].startswith("studio:") and self.studio:
                upstream_id = pipeline["pipeline_ref"].removeprefix("studio:")

                def record_task(task_id: str) -> None:
                    store.update_knowledge_job_item(
                        job_id,
                        source_version_id,
                        dataflow_task_id=task_id,
                    )
                    self._raise_if_cancelled(job_id)

                result = self.studio.run_pipeline_for_source(
                    self.dataforge,
                    source_version_id,
                    upstream_id,
                    pipeline.get("pipeline_snapshot") or None,
                    on_task_started=record_task,
                )
                self._raise_if_cancelled(job_id)
                store.update_knowledge_job_item(
                    job_id,
                    source_version_id,
                    status="completed",
                    dataflow_task_id=result["task_id"],
                )
                try:
                    task_detail = self.studio.get_task_detail(result["task_id"])
                    operator_details = (task_detail.get("status") or {}).get("operators_detail") or {}
                except Exception:
                    operator_details = {}
                self._record_event(
                    job_id,
                    "source_completed",
                    f"文档处理完成：{source_label}（{len(operator_details)} 个算子）",
                    {
                        "source_version_id": source_version_id,
                        "operator_count": len(operator_details),
                    },
                )
                return result
            raise ValidationError("该标准流程缺少可执行的 DataFlow 流程版本")
        except JobCancelled:
            store.update_knowledge_job_item(
                job_id,
                source_version_id,
                status="cancelled",
            )
            self._record_event(job_id, "source_cancelled", f"已停止处理文档：{source_label}")
            raise
        except Exception as exc:
            if store.is_knowledge_job_cancel_requested(job_id):
                store.update_knowledge_job_item(
                    job_id,
                    source_version_id,
                    status="cancelled",
                )
                self._record_event(job_id, "source_cancelled", f"已停止处理文档：{source_label}")
                raise JobCancelled() from exc
            store.update_knowledge_job_item(
                job_id,
                source_version_id,
                status="failed",
                error=str(exc),
            )
            self._record_event(job_id, "source_failed", f"文档处理失败：{source_label}；{exc}")
            raise

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        store = self.dataforge.store
        cancelled = store.request_knowledge_job_cancel(job_id)
        self._record_event(job_id, "cancel_requested", "用户请求取消任务")
        if self.studio:
            for item in store.list_knowledge_job_items(job_id):
                task_id = item.get("dataflow_task_id")
                if not task_id:
                    continue
                try:
                    self.studio.cancel_task(task_id)
                except (NotFoundError, ValidationError):
                    # Cooperative cancellation still prevents validation and
                    # publishing when an upstream executor cannot be interrupted.
                    pass
        return cancelled

    def retry_job(self, job_id: str) -> dict[str, Any]:
        store = self.dataforge.store
        failed = store.get_knowledge_job(job_id)
        if failed["status"] not in {"failed", "cancelled"}:
            raise ValidationError("只有失败或已取消的任务可以重试")
        existing_retry = store.get_knowledge_job_retry(job_id)
        if existing_retry:
            raise ValidationError(f"该任务已经创建后续尝试：{existing_retry['id']}")
        pipeline = store.get_standard_pipeline(failed["standard_pipeline_id"])
        if pipeline["validation_status"] != "validated" or not pipeline["active"]:
            raise ValidationError("原任务使用的标准流程当前不可用，不能直接重试")
        for version_id in failed["source_version_ids"]:
            store.get_source_version(version_id)
        retry = store.create_knowledge_job(
            failed["name"],
            failed["knowledge_type_id"],
            failed["standard_pipeline_id"],
            failed["source_version_ids"],
            retry_of_job_id=failed["id"],
            attempt_no=int(failed.get("attempt_no") or 1) + 1,
        )
        self._record_event(
            failed["id"],
            "retry_created",
            f"已创建第 {retry['attempt_no']} 次尝试",
            {"retry_job_id": retry["id"]},
        )
        self._record_event(
            retry["id"],
            "retry_started",
            f"从第 {failed.get('attempt_no') or 1} 次尝试重新开始",
            {"retry_of_job_id": failed["id"]},
        )
        return retry

    def get_job_detail(self, job_id: str) -> dict[str, Any]:
        store = self.dataforge.store
        job = store.get_knowledge_job(job_id)
        pipeline = store.get_standard_pipeline(job["standard_pipeline_id"])
        knowledge_type = store.get_knowledge_type(job["knowledge_type_id"])
        sources = []
        for version_id in job["source_version_ids"]:
            version = store.get_source_version(version_id)
            source = store.get_source(version["source_id"])
            sources.append(
                {
                    "source_id": source["id"],
                    "source_name": source["name"],
                    "source_version_id": version["id"],
                    "version_no": version["version_no"],
                    "original_filename": version["original_filename"],
                    "size_bytes": version["size_bytes"],
                }
            )
        executions = store.list_knowledge_job_executions(job.get("knowledge_base_id"))
        for execution in executions:
            execution["engine"] = execution.get("engine") or pipeline["engine"]
        retry = store.get_knowledge_job_retry(job_id)
        return {
            **job,
            "knowledge_type_name": knowledge_type["name"],
            "standard_pipeline_name": pipeline["name"],
            "standard_pipeline": {
                "id": pipeline["id"],
                "name": pipeline["name"],
                "pipeline_ref": pipeline["pipeline_ref"],
                "engine": pipeline["engine"],
                "version": pipeline["version"],
                "validation_status": pipeline["validation_status"],
                "pipeline_hash": pipeline.get("pipeline_hash"),
                "sample_task_id": pipeline.get("sample_task_id"),
                "uses_frozen_snapshot": bool(pipeline.get("pipeline_snapshot")),
            },
            "sources": sources,
            "items": store.list_knowledge_job_items(job_id),
            "events": store.list_knowledge_job_events(job_id),
            "executions": executions,
            "retry_job": (
                {
                    "id": retry["id"],
                    "status": retry["status"],
                    "attempt_no": retry.get("attempt_no", 1),
                    "created_at": retry["created_at"],
                }
                if retry
                else None
            ),
        }

    def get_record_lineage(self, record_id: str) -> dict[str, Any]:
        lineage = self.dataforge.store.get_knowledge_record_lineage(record_id)
        locator = lineage.get("source_locator") or {}
        if locator.get("source_excerpt"):
            return lineage
        run_id = lineage.get("run_id")
        if not run_id:
            return lineage
        run = self.dataforge.store.get_run(run_id)
        input_file = Path(run["work_dir"]) / "input" / "source_records.jsonl"
        locator["source_excerpt"] = _source_excerpt(_read_source_records(input_file), lineage.get("data") or {})
        lineage["source_locator"] = locator
        return lineage


def _read_source_records(path: Path) -> dict[int, dict[str, Any]]:
    if not path.is_file():
        return {}
    result: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            result[int(item.get("source_record_index", len(result)))] = item
    return result


def _source_excerpt(
    source_records: dict[int, dict[str, Any]], record: dict[str, Any]
) -> str:
    source_index = int(record.get("source_record_index") or 0)
    raw = str((source_records.get(source_index) or {}).get("raw_content") or "")
    if not raw:
        return ""
    chunk_index = int(record.get("chunk_index") or 0)
    target = str(record.get("content") or "")
    chunk_size = max(600, len(target)) if target else 600
    chunks = split_text(raw, chunk_size, min(80, max(0, chunk_size - 1)))
    if chunk_index < len(chunks):
        return chunks[chunk_index]
    return raw[: max(800, len(target))]


def validate_record(record: Any, schema: dict[str, Any]) -> list[str]:
    if not isinstance(record, dict):
        return ["数据必须是对象"]
    errors: list[str] = []
    properties = schema.get("properties", {})
    for field in schema.get("required", []):
        if field not in record or record[field] is None:
            errors.append(f"缺少字段：{field}")
            continue
        expected = properties.get(field)
        value = record[field]
        matches = {
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }.get(expected, True)
        if not matches:
            errors.append(f"字段 {field} 应为 {expected}")
    return errors
