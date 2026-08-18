from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, BackgroundTasks

from ..application import DataForge
from ..database import new_id
from ..errors import ValidationError
from ..knowledge import KnowledgeService, validate_record
from .helpers import execute_knowledge_job_safely, execute_run_safely
from .schemas import (
    KnowledgeJobRequest,
    KnowledgeTypeRequest,
    RunRequest,
    StandardPipelinePublishRequest,
)


def _validate_knowledge_type_payload(payload: KnowledgeTypeRequest) -> None:
    if not payload.name.strip():
        raise ValidationError("请填写知识类型名称")
    required = payload.schema.get("required")
    properties = payload.schema.get("properties")
    if payload.schema.get("type") != "object" or not isinstance(required, list) or not required:
        raise ValidationError("知识类型必须是对象，并至少包含一个必填字段")
    if not isinstance(properties, dict) or any(field not in properties for field in required):
        raise ValidationError("每个必填字段都必须在字段定义中声明")
    supported = {"string", "integer", "array", "object"}
    invalid = [name for name, kind in properties.items() if kind not in supported]
    if invalid:
        raise ValidationError(f"字段类型暂不支持：{'、'.join(invalid)}")


def build_processing_router(dataforge: DataForge, knowledge: KnowledgeService, studio: Any) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["processing"])

    @router.get("/dataflow-studio/status")
    def dataflow_studio_status():
        return studio.describe()

    @router.get("/dataflow-health")
    def dataflow_health():
        return studio.health_report(dataforge)

    @router.get("/dataflow-pipelines")
    def list_dataflow_pipelines():
        return studio.list_pipelines()

    @router.get("/dataflow-pipelines/{pipeline_id}")
    def get_dataflow_pipeline(pipeline_id: str):
        pipeline = studio.get_pipeline(pipeline_id)
        snapshot = studio.capture_pipeline(pipeline_id)
        return {**pipeline, "config_hash": snapshot["config_hash"]}

    @router.post("/dataflow-pipelines/{pipeline_id}/validate")
    def validate_dataflow_pipeline(pipeline_id: str):
        return studio.validate_pipeline(pipeline_id)

    @router.get("/dataflow-tasks")
    def list_dataflow_tasks(pipeline_id: str | None = None):
        return studio.list_tasks(pipeline_id)

    @router.get("/dataflow-tasks/{task_id}")
    def get_dataflow_task(task_id: str, limit: int = 8):
        return studio.get_task_detail(task_id, limit)

    @router.post("/dataflow-tasks/{task_id}/cancel")
    def cancel_dataflow_task(task_id: str):
        return studio.cancel_task(task_id)

    @router.get("/dataflow-datasets")
    def list_dataflow_datasets():
        return studio.list_datasets()

    @router.get("/dataflow-operators")
    def list_dataflow_operators():
        return studio.list_operators()

    @router.get("/dataflow-schemas")
    def list_dataflow_schemas():
        return studio.list_schemas()

    @router.get("/dataflow-servings")
    def list_dataflow_servings():
        return studio.list_servings()

    @router.post("/dataflow-text2qa/activate")
    def activate_dataflow_text2qa(serving_id: str | None = None):
        return studio.bootstrap_text2qa_pipeline(dataforge, serving_id)

    @router.post("/dataflow-conversation/configure")
    def configure_dataflow_conversation(serving_id: str | None = None):
        return studio.bootstrap_conversation_pipeline(dataforge, serving_id)

    @router.post("/source-versions/{source_version_id}/send-to-dataflow")
    def send_source_to_dataflow(source_version_id: str):
        return studio.send_source(dataforge, source_version_id)

    @router.post("/dataflow-tasks/{task_id}/publish")
    def publish_dataflow_task(task_id: str):
        return studio.publish_task(dataforge, task_id)

    @router.get("/pipelines")
    def list_pipelines():
        return dataforge.store.list_pipelines()

    @router.get("/knowledge-types")
    def list_knowledge_types():
        return dataforge.store.list_knowledge_types()

    @router.post("/knowledge-types", status_code=201)
    def create_knowledge_type(payload: KnowledgeTypeRequest):
        _validate_knowledge_type_payload(payload)
        return dataforge.store.register_knowledge_type(
            new_id("ktype"), payload.name.strip(), payload.description.strip(), payload.schema
        )

    @router.post("/knowledge-types/{type_id}/versions", status_code=201)
    def create_knowledge_type_version(type_id: str, payload: KnowledgeTypeRequest):
        _validate_knowledge_type_payload(payload)
        return dataforge.store.create_knowledge_type_version(
            type_id,
            new_id("ktype"),
            payload.name.strip(),
            payload.description.strip(),
            payload.schema,
        )

    @router.get("/standard-pipelines")
    def list_standard_pipelines(knowledge_type_id: str | None = None):
        return dataforge.store.list_standard_pipelines(knowledge_type_id)

    @router.post("/standard-pipelines/publish", status_code=201)
    def publish_standard_pipeline(payload: StandardPipelinePublishRequest):
        if not payload.name.strip():
            raise ValidationError("请填写标准流程名称")
        if payload.version < 1:
            raise ValidationError("流程版本必须大于 0")
        pipeline = studio.get_pipeline(payload.dataflow_pipeline_id)
        snapshot = studio.capture_pipeline(payload.dataflow_pipeline_id)
        if not (pipeline.get("config") or {}).get("operators"):
            raise ValidationError("空白草稿不能发布，请先配置至少一个算子")
        task = studio.get_task(payload.sample_task_id)
        if task.get("status") != "completed":
            raise ValidationError("请选择该流程一次已经成功完成的样本任务")
        if task.get("pipeline_id") != payload.dataflow_pipeline_id:
            raise ValidationError("样本任务与所选 DataFlow 流程不一致")
        preflight = studio.preflight_pipeline(snapshot.get("config") or {})
        if preflight["status"] != "ready":
            messages = "；".join(issue["message"] for issue in preflight["issues"])
            raise ValidationError(f"流程当前不可发布：{messages}")
        knowledge_type = dataforge.store.get_knowledge_type(payload.knowledge_type_id)
        prior_versions = [
            item
            for item in dataforge.store.list_standard_pipelines(payload.knowledge_type_id)
            if item["name"] == payload.name.strip()
        ]
        if prior_versions and payload.version <= max(item["version"] for item in prior_versions):
            next_version = max(item["version"] for item in prior_versions) + 1
            raise ValidationError(f"同名标准流程必须发布更高版本，建议使用 V{next_version}")
        output_file = studio.task_output_file(payload.sample_task_id)
        checked = 0
        invalid: list[dict[str, Any]] = []
        with output_file.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                checked += 1
                errors = validate_record(json.loads(line), knowledge_type["schema"])
                if errors and len(invalid) < 20:
                    invalid.append({"line": line_number, "errors": errors})
        if not checked:
            raise ValidationError("样本任务输出为空，不能发布")
        if invalid:
            first = "；".join(invalid[0]["errors"])
            raise ValidationError(f"输出格式不符合“{knowledge_type['name']}”：{first}")
        published = dataforge.store.register_standard_pipeline(
            new_id("std"),
            payload.name.strip(),
            payload.knowledge_type_id,
            f"studio:{payload.dataflow_pipeline_id}",
            "dataflow-studio",
            payload.version,
            payload.description.strip() or f"由 DataFlow 流程“{snapshot['name']}”发布。",
            knowledge_type["schema"],
            "validated",
            payload.make_default,
            snapshot,
            snapshot["config_hash"],
            payload.sample_task_id,
        )
        return {**published, "checked_records": checked}

    @router.post("/standard-pipelines/{pipeline_id}/default")
    def set_default_standard_pipeline(pipeline_id: str):
        return dataforge.store.set_default_standard_pipeline(pipeline_id)

    @router.post("/standard-pipelines/{pipeline_id}/deactivate")
    def deactivate_standard_pipeline(pipeline_id: str):
        return dataforge.store.deactivate_standard_pipeline(pipeline_id)

    @router.get("/knowledge-jobs")
    def list_knowledge_jobs():
        return dataforge.store.list_knowledge_jobs()

    @router.get("/knowledge-jobs/{job_id}")
    def get_knowledge_job(job_id: str):
        return knowledge.get_job_detail(job_id)

    @router.post("/knowledge-jobs/{job_id}/retry", status_code=202)
    def retry_knowledge_job(job_id: str, background_tasks: BackgroundTasks):
        job = knowledge.retry_job(job_id)
        background_tasks.add_task(execute_knowledge_job_safely, knowledge, job["id"])
        return job

    @router.post("/knowledge-jobs/{job_id}/cancel")
    def cancel_knowledge_job(job_id: str):
        return knowledge.cancel_job(job_id)

    @router.post("/knowledge-jobs", status_code=202)
    def start_knowledge_job(payload: KnowledgeJobRequest, background_tasks: BackgroundTasks):
        job = knowledge.create_job(
            name=payload.name,
            knowledge_type_id=payload.knowledge_type_id,
            standard_pipeline_id=payload.standard_pipeline_id,
            source_version_ids=payload.source_version_ids,
        )
        background_tasks.add_task(execute_knowledge_job_safely, knowledge, job["id"])
        return job

    @router.get("/runs")
    def list_runs():
        return dataforge.store.list_runs()

    @router.post("/runs", status_code=202)
    def start_run(payload: RunRequest, background_tasks: BackgroundTasks):
        if payload.engine not in {None, "dataflow", "native"}:
            raise ValidationError(f"Unknown processing engine: {payload.engine}")
        run = dataforge.create_run(
            payload.source_version_id,
            pipeline_id=payload.pipeline_id,
            engine_override=payload.engine,
        )
        background_tasks.add_task(execute_run_safely, dataforge, run["id"])
        return run

    @router.get("/runs/{run_id}")
    def get_run(run_id: str):
        return {"run": dataforge.store.get_run(run_id), "events": dataforge.store.list_run_events(run_id)}

    return router
