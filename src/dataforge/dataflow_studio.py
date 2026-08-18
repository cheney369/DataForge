from __future__ import annotations

import json
import shutil
import sys
import types
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .application import DataForge
from .config import Settings
from .database import new_id
from .errors import ValidationError
from .ingestion import materialize_source_records
from .integrations.dataflow import DataFlowAdapter


@dataclass
class StudioStatus:
    available: bool = False
    frontend_available: bool = False
    backend_available: bool = False
    message: str = "DataFlow 加工中心尚未初始化"
    operator_count: int = 0
    pipeline_count: int = 0
    capabilities: tuple[str, ...] = ()
    basic_pipeline_id: str | None = None
    basic_pipeline_ready: bool = False
    text2qa_pipeline_id: str | None = None
    text2qa_pipeline_configured: bool = False
    text2qa_pipeline_ready: bool = False
    text2qa_message: str = "Text2QA 尚未配置"
    conversation_pipeline_id: str | None = None
    conversation_pipeline_configured: bool = False
    conversation_message: str = "多轮对话流程尚未配置"


class DataFlowStudio:
    """Mount the upstream DataFlow WebUI while keeping its state inside DataForge."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.project_root / "third_party" / "dataflow_webui"
        self.backend_root = self.root / "backend"
        self.frontend_dist = self.root / "frontend" / "dist"
        self.state_root = settings.state_dir / "dataflow-studio"
        self.container: Any | None = None
        self.adapter: DataFlowAdapter | None = None
        self.status = StudioStatus(frontend_available=self.frontend_dist.is_dir())

    def mount(self, app: FastAPI) -> StudioStatus:
        if not self.backend_root.is_dir():
            self.status.message = "未找到 DataFlow 工作台后端源码"
            return self.status
        if not self.settings.dataflow_path or not (self.settings.dataflow_path / "dataflow").is_dir():
            self.status.message = "未找到 DataFlow 核心项目"
            self._mount_frontend(app)
            return self.status

        try:
            self._prepare_imports_and_state()
            # Register the two lightweight DataForge operators before the
            # upstream registry takes its availability snapshot.
            import dataforge.processing.dataflow_pipeline  # noqa: F401

            from app.api.v1.router import api_router
            from app.core.container import container
            from app.services.dataflow_engine import dataflow_engine

            container.init()
            self.container = container
            self.adapter = DataFlowAdapter(container, dataflow_engine, self.state_root)
            app.include_router(api_router, prefix="/api/v1")
            self.status.backend_available = True
            self.status.operator_count = len(container.operator_registry.get_op_list(lang="zh"))
            self.status.pipeline_count = len(container.pipeline_registry.list_pipelines())
            self.status.capabilities = (
                "pipelines",
                "operators",
                "datasets",
                "tasks",
                "logs",
                "results",
                "schemas",
            )
            self.status.message = "DataFlow 原工作台已接入"
        except Exception as exc:
            self.status.message = f"DataFlow 工作台初始化失败：{exc}"

        self._mount_frontend(app)
        self.status.available = self.status.frontend_available and self.status.backend_available
        return self.status

    def _prepare_imports_and_state(self) -> None:
        for path in (self.settings.dataflow_path, self.backend_root):
            value = str(path)
            if value not in sys.path:
                sys.path.insert(0, value)

        # DataFlow's serving package eagerly imports every local GPU/audio/cloud
        # backend.  The WebUI only requires the HTTP API serving class at startup,
        # so expose that lightweight module without forcing unrelated runtimes.
        serving_path = self.settings.dataflow_path / "dataflow" / "serving"
        if "dataflow.serving" not in sys.modules:
            serving_package = types.ModuleType("dataflow.serving")
            serving_package.__path__ = [str(serving_path)]
            serving_package.__package__ = "dataflow.serving"
            sys.modules["dataflow.serving"] = serving_package
        from dataflow.serving.api_llm_serving_request import APILLMServing_request

        sys.modules["dataflow.serving"].APILLMServing_request = APILLMServing_request

        from app.core.config import settings as upstream

        data_dir = self.state_root / "data"
        core_dir = data_dir / "dataflow_core"
        resources_dir = self.state_root / "resources"
        for directory in (data_dir, core_dir, resources_dir, self.state_root / "cache"):
            directory.mkdir(parents=True, exist_ok=True)

        source_pipelines = self.settings.dataflow_path / "dataflow" / "statics" / "pipelines" / "api_pipelines"
        target_pipelines = core_dir / "api_pipelines"
        if source_pipelines.is_dir():
            shutil.copytree(source_pipelines, target_pipelines, dirs_exist_ok=True)
        target_pipelines.mkdir(parents=True, exist_ok=True)
        (core_dir / "example_data").mkdir(parents=True, exist_ok=True)

        upstream.BASE_DIR = str(self.state_root)
        upstream.DATA_REGISTRY = str(data_dir / "data_registry.yaml")
        upstream.TASK_REGISTRY = str(data_dir / "task_registry.json")
        upstream.PIPELINE_REGISTRY = str(data_dir / "pipeline_registry.json")
        upstream.SERVING_REGISTRY = str(data_dir / "serving_registry.yaml")
        upstream.TEXT2SQL_DATABASE_REGISTRY = str(data_dir / "text2sql_database_registry.yaml")
        upstream.TEXT2SQL_DATABASE_MANAGER_REGISTRY = str(data_dir / "text2sql_database_manager_registry.yaml")
        upstream.DATAFLOW_CORE_DIR = str(core_dir)
        upstream.OPS_JSON_PATH = str(data_dir / "ops.json")
        upstream.PREFERENCES_PATH = str(data_dir / "user_preferences.json")
        upstream.SQLITE_DB_DIR = str(data_dir / "text2sql_dbs")
        upstream.CACHE_DIR = str(self.state_root / "cache")
        upstream.RESOURCE_DIR = str(resources_dir)

    def _mount_frontend(self, app: FastAPI) -> None:
        if self.frontend_dist.is_dir():
            app.mount("/studio", StaticFiles(directory=self.frontend_dist, html=True), name="dataflow-studio")
            self.status.frontend_available = True

    def describe(self) -> dict[str, Any]:
        return asdict(self.status)

    def list_pipelines(self) -> list[dict[str, Any]]:
        return self.adapter.list_pipelines() if self.adapter else []

    def get_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        pipeline = self.adapter.get_pipeline(pipeline_id) if self.adapter else None
        if not pipeline:
            raise ValidationError(f"DataFlow 流程不存在：{pipeline_id}")
        return pipeline

    def capture_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        snapshot = self.adapter.capture_pipeline(pipeline_id) if self.adapter else None
        if not snapshot:
            raise ValidationError(f"DataFlow 流程不存在：{pipeline_id}")
        return snapshot

    def validate_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        result = self.adapter.validate_pipeline(pipeline_id) if self.adapter else None
        if result is None:
            raise ValidationError(f"DataFlow 流程不存在：{pipeline_id}")
        return result

    def list_tasks(self, pipeline_id: str | None = None) -> list[dict[str, Any]]:
        return self.adapter.list_tasks(pipeline_id) if self.adapter else []

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self.adapter.get_task(task_id) if self.adapter else None
        if not task:
            raise ValidationError(f"DataFlow 任务不存在：{task_id}")
        return task

    def get_task_detail(self, task_id: str, limit: int = 8) -> dict[str, Any]:
        detail = self.adapter.get_task_detail(task_id, limit=limit) if self.adapter else None
        if not detail:
            raise ValidationError(f"DataFlow 任务不存在：{task_id}")
        return detail

    def cancel_task(self, task_id: str) -> dict[str, Any]:
        self.get_task(task_id)
        if not self.adapter or not self.adapter.cancel_task(task_id):
            raise ValidationError("任务无法取消，可能已经结束或执行器不支持取消")
        return {"task_id": task_id, "cancelled": True}

    def list_datasets(self) -> list[dict[str, Any]]:
        return self.adapter.list_datasets() if self.adapter else []

    def list_operators(self) -> list[dict[str, Any]]:
        return self.adapter.list_operators() if self.adapter else []

    def list_schemas(self) -> list[dict[str, Any]]:
        return self.adapter.list_schemas() if self.adapter else []

    def list_servings(self) -> list[dict[str, Any]]:
        return self.adapter.list_servings() if self.adapter else []

    def ensure_llm_serving(self, service: dict[str, Any]) -> dict[str, Any]:
        if not self.adapter or not self.status.backend_available:
            raise ValidationError("DataFlow 运行时尚未就绪")
        try:
            return self.adapter.ensure_api_llm_serving(service)
        except (OSError, TypeError, ValueError) as exc:
            raise ValidationError(f"DataFlow 模型服务同步失败：{exc}") from exc

    def preflight_pipeline(self, config: dict[str, Any]) -> dict[str, Any]:
        """Report whether a frozen pipeline can run in the current environment."""
        operators = config.get("operators") or []
        required_operators = [
            str(operator.get("name"))
            for operator in operators
            if isinstance(operator, dict) and operator.get("name")
        ]
        issues: list[dict[str, str]] = []
        if not self.adapter or not self.status.backend_available:
            issues.append(
                {
                    "code": "runtime_unavailable",
                    "message": self.status.message or "DataFlow 运行时不可用",
                }
            )
            available_operators: set[str] = set()
            ready_servings: set[str] = set()
        else:
            available_operators = {
                str(item.get("name"))
                for item in self.adapter.list_operators()
                if item.get("name")
            }
            ready_servings = self.adapter.ready_serving_ids()

        missing_operators = sorted(set(required_operators) - available_operators)
        if not required_operators:
            issues.append({"code": "empty_pipeline", "message": "流程尚未配置算子"})
        if missing_operators:
            issues.append(
                {
                    "code": "missing_operators",
                    "message": f"缺少可用算子：{'、'.join(missing_operators)}",
                }
            )

        requires_serving = _operators_requiring_llm_serving(config)
        configured_servings = _llm_serving_ids(config)
        if requires_serving and not configured_servings:
            issues.append(
                {
                    "code": "serving_unbound",
                    "message": f"算子 {'、'.join(sorted(requires_serving))} 尚未绑定模型服务",
                }
            )
        unavailable_servings = sorted(configured_servings - ready_servings)
        if unavailable_servings:
            issues.append(
                {
                    "code": "serving_unavailable",
                    "message": "流程绑定的模型服务当前未就绪",
                }
            )

        return {
            "status": "ready" if not issues else "blocked",
            "operator_count": len(required_operators),
            "required_operators": required_operators,
            "missing_operators": missing_operators,
            "requires_serving": bool(requires_serving),
            "configured_serving_count": len(configured_servings),
            "unavailable_serving_count": len(unavailable_servings),
            "issues": issues,
        }

    def health_report(self, dataforge: DataForge) -> dict[str, Any]:
        """Summarize runtime and published-pipeline readiness without secrets."""
        runtime_checks = [
            {
                "id": "core",
                "name": "DataFlow 核心运行时",
                "status": "ready" if self.status.backend_available else "blocked",
                "message": self.status.message,
            },
            {
                "id": "studio",
                "name": "可视化调试台",
                "status": "ready" if self.status.frontend_available else "warning",
                "message": "前端资源已挂载" if self.status.frontend_available else "调试台前端尚未构建",
            },
            {
                "id": "operators",
                "name": "可用算子",
                "status": "ready" if self.status.operator_count else "blocked",
                "message": f"当前已加载 {self.status.operator_count} 个算子",
            },
        ]
        pipelines = []
        for pipeline in dataforge.store.list_standard_pipelines():
            if pipeline.get("engine") != "dataflow-studio":
                continue
            check = self.preflight_pipeline((pipeline.get("pipeline_snapshot") or {}).get("config") or {})
            pipelines.append(
                {
                    "id": pipeline["id"],
                    "name": pipeline["name"],
                    "validation_status": pipeline["validation_status"],
                    "active": bool(pipeline["active"]),
                    **check,
                }
            )
        blocked_published = [
            pipeline
            for pipeline in pipelines
            if pipeline["validation_status"] == "validated"
            and pipeline["active"]
            and pipeline["status"] != "ready"
        ]
        runtime_blocked = any(item["status"] == "blocked" for item in runtime_checks)
        warnings = [item for item in runtime_checks if item["status"] == "warning"]
        overall = "blocked" if runtime_blocked or blocked_published else "degraded" if warnings or any(
            pipeline["status"] != "ready" for pipeline in pipelines
        ) else "ready"
        return {
            "status": overall,
            "runtime": runtime_checks,
            "pipelines": pipelines,
            "summary": {
                "available_operators": self.status.operator_count,
                "registered_pipelines": self.status.pipeline_count,
                "ready_servings": len(self.adapter.ready_serving_ids()) if self.adapter else 0,
                "published_pipeline_issues": len(blocked_published),
            },
        }

    def bootstrap_basic_text_pipeline(self, dataforge: DataForge) -> dict[str, Any] | None:
        """Provision and sample-validate one dependency-free DataFlow channel."""
        if not self.adapter or not self.status.backend_available:
            return None

        identity_tag = "dataforge:basic-text-v1"
        bootstrap_dir = self.state_root / "bootstrap"
        bootstrap_dir.mkdir(parents=True, exist_ok=True)
        sample_file = bootstrap_dir / "basic-text-sample.jsonl"
        if not sample_file.is_file():
            sample = {
                "document_id": "dataforge-bootstrap-document",
                "source_id": "dataforge-bootstrap-source",
                "source_version_id": "dataforge-bootstrap-version",
                "source_record_index": 0,
                "raw_content": "高血压患者应定期监测血压。\n\n出现不适时应及时就医。",
            }
            sample_file.write_text(
                json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        dataset = self.adapter.register_dataset(
            {
                "name": "DataForge 基础文本流程验证样本",
                "root": str(sample_file),
                "pipeline": "DataForge Basic Text",
                "meta": {"dataforge_bootstrap": True},
            }
        )
        config = {
            "input_dataset": {"id": dataset["id"]},
            "operators": [
                {
                    "name": "NormalizeMedicalTextOperator",
                    "location": [180, 180],
                    "params": {
                        "input_key": "raw_content",
                        "output_key": "normalized_content",
                    },
                },
                {
                    "name": "ChunkMedicalTextOperator",
                    "location": [520, 180],
                    "params": {
                        "chunk_size": 600,
                        "chunk_overlap": 80,
                        "input_key": "normalized_content",
                        "output_key": "content",
                    },
                },
            ],
        }
        pipeline, created = self.adapter.ensure_pipeline(
            name="DataForge 基础文本标准化与分块",
            config=config,
            identity_tag=identity_tag,
        )
        pipeline_id = pipeline["id"]
        self.status.basic_pipeline_id = pipeline_id
        self.status.pipeline_count = len(self.adapter.list_pipelines())

        existing = dataforge.store.get_standard_pipeline("std-text-chunk-v1")
        if existing.get("pipeline_snapshot"):
            self.status.basic_pipeline_ready = bool(
                existing.get("active") and existing.get("validation_status") == "validated"
            )
            return {
                "pipeline": pipeline,
                "standard_pipeline": existing,
                "sample_task_id": existing.get("sample_task_id"),
                "created": created,
                "published": False,
            }

        snapshot = self.capture_pipeline(pipeline_id)
        result = self.adapter.execute_pipeline(pipeline_id, snapshot["config"])
        if result.get("status") != "completed":
            detail = (result.get("output") or {}).get("error") or "基础 DataFlow 流程执行失败"
            raise ValidationError(str(detail))
        output_file = self.task_output_file(result["task_id"])

        from .knowledge import validate_record

        knowledge_type = dataforge.store.get_knowledge_type("text_chunk")
        checked = 0
        with output_file.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                checked += 1
                errors = validate_record(json.loads(line), knowledge_type["schema"])
                if errors:
                    raise ValidationError(
                        f"基础 DataFlow 流程第 {line_number} 条输出格式错误：{'；'.join(errors)}"
                    )
        if not checked:
            raise ValidationError("基础 DataFlow 流程没有生成验证记录")

        standard = dataforge.store.register_standard_pipeline(
            "std-text-chunk-v1",
            "DataFlow 文档标准化分块流程",
            "text_chunk",
            f"studio:{pipeline_id}",
            "dataflow-studio",
            1,
            "由 DataFlow 执行文本标准化、分块和去重；发布配置已冻结。",
            knowledge_type["schema"],
            "validated",
            True,
            snapshot,
            snapshot["config_hash"],
            result["task_id"],
        )
        self.status.basic_pipeline_ready = True
        return {
            "pipeline": pipeline,
            "standard_pipeline": standard,
            "sample_task_id": result["task_id"],
            "checked_records": checked,
            "created": created,
            "published": True,
        }

    def bootstrap_text2qa_pipeline(
        self,
        dataforge: DataForge,
        serving_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Configure DataFlow's Text2QA operators for DataForge FAQ records."""
        if not self.adapter or not self.status.backend_available:
            return None

        identity_tag = "dataforge:text2qa-v1"
        sample_file = self.state_root / "bootstrap" / "basic-text-sample.jsonl"
        if not sample_file.is_file():
            raise ValidationError("基础文本样本尚未准备好")
        dataset = self.adapter.register_dataset(
            {
                "name": "DataForge Text2QA 验证样本",
                "root": str(sample_file),
                "pipeline": "DataForge Text2QA",
                "meta": {"dataforge_bootstrap": True, "knowledge_type": "faq"},
            }
        )
        ready_servings = self.adapter.ready_serving_ids()
        if serving_id and serving_id not in ready_servings:
            raise ValidationError("指定的模型服务不存在、缺少 API Key，或当前不可用")
        initial_serving_id = serving_id or (
            next(iter(ready_servings)) if len(ready_servings) == 1 else None
        )
        config = _text2qa_config(dataset["id"], initial_serving_id)
        pipeline, created = self.adapter.ensure_pipeline(
            name="DataForge 文档转 FAQ（Text2QA）",
            config=config,
            identity_tag=identity_tag,
        )
        pipeline_id = pipeline["id"]
        self.status.text2qa_pipeline_id = pipeline_id
        self.status.text2qa_pipeline_configured = True
        self.status.pipeline_count = len(self.adapter.list_pipelines())

        if initial_serving_id:
            pipeline, changed = _bind_missing_llm_serving(
                pipeline,
                initial_serving_id,
            )
            if changed:
                pipeline = self.adapter.update_pipeline(
                    pipeline_id,
                    {"config": pipeline["config"]},
                )

        snapshot = self.capture_pipeline(pipeline_id)
        configured_ids = _llm_serving_ids(snapshot["config"])
        serving_ready = bool(configured_ids) and configured_ids.issubset(ready_servings)
        knowledge_type = dataforge.store.get_knowledge_type("faq")
        existing = dataforge.store.get_standard_pipeline("std-faq-text2qa-v1")

        if existing["validation_status"] == "inactive" or not existing["active"]:
            self.status.text2qa_pipeline_ready = False
            self.status.text2qa_message = "Text2QA 标准流程版本已停用；如需恢复请发布新版本"
            return {
                "pipeline": pipeline,
                "standard_pipeline": existing,
                "created": created,
                "published": False,
                "inactive": True,
            }

        if existing["validation_status"] == "validated" and existing.get("pipeline_snapshot"):
            self.status.text2qa_pipeline_ready = True
            self.status.text2qa_message = "Text2QA 已通过样本验证并发布"
            return {
                "pipeline": pipeline,
                "standard_pipeline": existing,
                "created": created,
                "published": False,
            }

        if not serving_ready:
            configured = dataforge.store.register_standard_pipeline(
                "std-faq-text2qa-v1",
                "DataFlow 文档转 FAQ 流程",
                "faq",
                f"studio:{pipeline_id}",
                "dataflow-studio",
                1,
                "使用 DataFlow Text2QAGenerator 生成问答，并由 Text2QASampleEvaluator 评估质量。",
                knowledge_type["schema"],
                "configured",
                False,
                snapshot,
                snapshot["config_hash"],
                None,
            )
            self.status.text2qa_message = (
                "Pipeline 已配置；请先在 DataFlow Serving 中配置可用模型服务"
                if not ready_servings
                else "检测到多个模型服务；请明确选择 Text2QA 使用的 Serving"
            )
            return {
                "pipeline": pipeline,
                "standard_pipeline": configured,
                "created": created,
                "published": False,
                "requires_serving": True,
            }

        result = self.adapter.execute_pipeline(pipeline_id, snapshot["config"])
        if result.get("status") != "completed":
            detail = (result.get("output") or {}).get("error") or "Text2QA 样本执行失败"
            self.status.text2qa_message = str(detail)
            return {
                "pipeline": pipeline,
                "standard_pipeline": existing,
                "created": created,
                "published": False,
                "execution_error": str(detail),
            }
        output_file = self.task_output_file(result["task_id"])
        from .knowledge import validate_record

        checked = 0
        with output_file.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                checked += 1
                errors = validate_record(json.loads(line), knowledge_type["schema"])
                if errors:
                    raise ValidationError(
                        f"Text2QA 第 {line_number} 条输出格式错误：{'；'.join(errors)}"
                    )
        if not checked:
            raise ValidationError("Text2QA 没有生成有效 FAQ 记录")

        standard = dataforge.store.register_standard_pipeline(
            "std-faq-text2qa-v1",
            "DataFlow 文档转 FAQ 流程",
            "faq",
            f"studio:{pipeline_id}",
            "dataflow-studio",
            1,
            "使用 DataFlow Text2QAGenerator 生成问答，并由 Text2QASampleEvaluator 评估质量。",
            knowledge_type["schema"],
            "validated",
            False,
            snapshot,
            snapshot["config_hash"],
            result["task_id"],
        )
        self.status.text2qa_pipeline_ready = True
        self.status.text2qa_message = "Text2QA 已通过样本验证并发布"
        return {
            "pipeline": pipeline,
            "standard_pipeline": standard,
            "sample_task_id": result["task_id"],
            "checked_records": checked,
            "created": created,
            "published": True,
        }

    def bootstrap_conversation_pipeline(
        self,
        dataforge: DataForge,
        serving_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Prepare a low-cost, manually runnable multi-turn dialogue draft."""
        if not self.adapter or not self.status.backend_available:
            return None

        sample_file = self.state_root / "bootstrap" / "basic-text-sample.jsonl"
        if not sample_file.is_file():
            raise ValidationError("基础文本样本尚未准备好")
        dataset = self.adapter.register_dataset(
            {
                "name": "DataForge 多轮对话生成占位输入",
                "root": str(sample_file),
                "pipeline": "DataForge Conversation Synthesis",
                "meta": {
                    "dataforge_bootstrap": True,
                    "knowledge_type": "multi_turn_dialogue",
                },
            }
        )
        ready_servings = self.adapter.ready_serving_ids()
        if serving_id and serving_id not in ready_servings:
            raise ValidationError("指定的模型服务不存在、缺少 API Key，或当前不可用")
        selected_serving_id = serving_id or (
            next(iter(ready_servings)) if len(ready_servings) == 1 else None
        )
        pipeline, created = self.adapter.ensure_pipeline(
            name="DataForge 多轮对话数据生成",
            config=_conversation_config(dataset["id"], selected_serving_id),
            identity_tag="dataforge:conversation-v1",
        )
        pipeline_id = pipeline["id"]
        self.status.conversation_pipeline_id = pipeline_id
        self.status.conversation_pipeline_configured = True
        self.status.pipeline_count = len(self.adapter.list_pipelines())

        if selected_serving_id:
            pipeline, changed = _bind_missing_llm_serving(pipeline, selected_serving_id)
            if changed:
                pipeline = self.adapter.update_pipeline(
                    pipeline_id,
                    {"config": pipeline["config"]},
                )

        snapshot = self.capture_pipeline(pipeline_id)
        configured_ids = _llm_serving_ids(snapshot["config"])
        serving_ready = bool(configured_ids) and configured_ids.issubset(ready_servings)
        knowledge_type = dataforge.store.get_knowledge_type("multi_turn_dialogue")
        existing = dataforge.store.get_standard_pipeline("std-dialogue-synthesis-v1")

        if existing["validation_status"] == "validated" and existing.get("pipeline_snapshot"):
            self.status.conversation_message = "多轮对话流程已通过样本验证并发布"
            return {
                "pipeline": pipeline,
                "standard_pipeline": existing,
                "created": created,
                "published": False,
            }

        configured = dataforge.store.register_standard_pipeline(
            "std-dialogue-synthesis-v1",
            "多轮对话生成流程",
            "multi_turn_dialogue",
            f"studio:{pipeline_id}",
            "dataflow-studio",
            1,
            "使用 DataFlow ConsistentChatGenerator 生成对话，并转换为统一 messages 结构。",
            knowledge_type["schema"],
            "configured",
            False,
            snapshot,
            snapshot["config_hash"],
            None,
        )
        self.status.conversation_message = (
            "Pipeline 已配置，可在调试台运行小样本并验证发布"
            if serving_ready
            else "Pipeline 已配置；运行前请选择可用的模型服务"
        )
        return {
            "pipeline": pipeline,
            "standard_pipeline": configured,
            "created": created,
            "published": False,
            "requires_serving": not serving_ready,
        }

    def task_output_file(self, task_id: str) -> Path:
        if not self.adapter:
            raise ValidationError("DataFlow 调试台未就绪")
        self.get_task(task_id)
        output = self.adapter.output_file(task_id)
        if not output:
            raise ValidationError(f"找不到任务 {task_id} 的最终输出文件，请重新运行样例")
        return output

    def run_pipeline_for_source(
        self,
        dataforge: DataForge,
        source_version_id: str,
        pipeline_id: str,
        pipeline_snapshot: dict[str, Any] | None = None,
        on_task_started: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if not self.adapter or not self.status.backend_available:
            raise ValidationError(self.status.message)
        imported = self.send_source(dataforge, source_version_id)
        if pipeline_snapshot:
            config = pipeline_snapshot.get("config") or {}
        else:
            config = self.get_pipeline(pipeline_id).get("config") or {}
        dataset_id = imported["dataset"]["id"]
        existing_input = config.get("input_dataset")
        config = json.loads(json.dumps(config))
        config["input_dataset"] = (
            {**existing_input, "id": dataset_id}
            if isinstance(existing_input, dict)
            else dataset_id
        )
        result = self.adapter.execute_pipeline(
            pipeline_id,
            config,
            on_task_started=on_task_started,
        )
        if result.get("status") != "completed":
            detail = (result.get("output") or {}).get("error") or "DataFlow 流程执行失败"
            raise ValidationError(str(detail))
        return {
            "task_id": result["task_id"],
            "output_file": self.task_output_file(result["task_id"]),
            "source_version": dataforge.store.get_source_version(source_version_id),
            "input_file": Path(imported["dataset"]["root"]),
        }

    def send_source(self, dataforge: DataForge, source_version_id: str) -> dict[str, Any]:
        if not self.adapter or not self.status.backend_available:
            raise ValidationError(self.status.message)

        version = dataforge.store.get_source_version(source_version_id)
        source = dataforge.store.get_source(version["source_id"])
        source_blob = dataforge.blobs.resolve(version["blob_uri"])
        import_dir = self.state_root / "imports"
        target = import_dir / f"{source_version_id}.jsonl"
        record_count = materialize_source_records(source_blob, version, target)
        dataset = self.adapter.register_dataset(
            {
                "name": f"{source['name']}（版本 {version['version_no']}）",
                "root": str(target),
                "pipeline": "DataForge 文件入口",
                "meta": {
                    "dataforge_source_id": source["id"],
                    "dataforge_source_version_id": source_version_id,
                    "original_filename": version["original_filename"],
                },
            }
        )
        return {"dataset": dataset, "record_count": record_count, "studio_url": "/studio/#/m/"}

    def publish_task(self, dataforge: DataForge, task_id: str) -> dict[str, Any]:
        """Publish a completed upstream task result as a versioned DataForge asset."""
        if not self.adapter or not self.status.backend_available:
            raise ValidationError(self.status.message)
        task = self.get_task(task_id)
        if task.get("status") != "completed":
            raise ValidationError("只有已经完成的 DataFlow 任务才能发布为数据资产")

        for existing in dataforge.store.list_runs():
            if existing.get("stats", {}).get("dataflow_task_id") == task_id and existing.get("asset_version_id"):
                return {
                    "run": existing,
                    "asset_version": dataforge.store.get_asset_version(existing["asset_version_id"]),
                    "created": False,
                }

        pipeline_config = task.get("pipeline_config") or {}
        dataset_ref = pipeline_config.get("input_dataset") or {}
        dataset_id = dataset_ref.get("id") if isinstance(dataset_ref, dict) else dataset_ref
        dataset = self.adapter.get_dataset(dataset_id) if dataset_id and self.adapter else None
        source_version_id = (dataset or {}).get("meta", {}).get("dataforge_source_version_id")
        if not source_version_id:
            raise ValidationError("该任务的输入不是从 DataForge 文件管理送入的，无法建立完整来源追溯")
        source_version = dataforge.store.get_source_version(source_version_id)
        source = dataforge.store.get_source(source_version["source_id"])

        execution_results = (task.get("output") or {}).get("execution_results") or []
        if not execution_results:
            raise ValidationError("该任务没有可发布的处理结果")
        output_file = self.task_output_file(task_id)

        record_count = 0
        schema: dict[str, str] = {}
        with output_file.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record_count += 1
                if not schema:
                    first = json.loads(line)
                    if isinstance(first, dict):
                        schema = {key: type(value).__name__ for key, value in first.items()}
        if not record_count:
            raise ValidationError("DataFlow 任务结果为空，不能发布为数据资产")

        upstream_pipeline_id = task.get("pipeline_id") or "custom"
        upstream_pipeline = self.adapter.get_pipeline(upstream_pipeline_id) if self.adapter else {}
        upstream_pipeline = upstream_pipeline or {}
        pipeline_id = f"dataflow-studio:{upstream_pipeline_id}"
        dataforge.store.register_pipeline(
            pipeline_id,
            upstream_pipeline.get("name") or "DataFlow 可视化流程",
            1,
            "dataflow-studio",
            {"upstream_pipeline": upstream_pipeline, "output_asset_type": "dataflow_dataset"},
        )
        run_id = new_id("run")
        run = dataforge.store.create_run(
            pipeline_id,
            source_version_id,
            "dataflow-studio",
            output_file.parent,
            run_id=run_id,
        )
        stats = {
            "dataflow_task_id": task_id,
            "input_records": (dataset or {}).get("num_samples", 0),
            "output_chunks": record_count,
            "pipeline_version": 1,
        }
        dataforge.store.add_run_event(run_id, "created", "DataFlow 任务成果开始发布", {"task_id": task_id})
        dataforge.store.transition_run(run_id, "preparing", stats=stats)
        dataforge.store.transition_run(run_id, "running", stats=stats)
        dataforge.store.add_run_event(run_id, "processing_completed", "DataFlow 可视化流程已完成", {"records": record_count})
        dataforge.store.transition_run(run_id, "publishing", stats=stats)
        blob_uri, sha256, size_bytes = dataforge.blobs.put_file(output_file)
        asset, asset_version = dataforge.store.publish_asset(
            logical_key=f"{source['id']}:{pipeline_id}:dataflow_dataset",
            name=f"{source['name']} / DataFlow 处理成果",
            asset_type="dataflow_dataset",
            run_id=run_id,
            source_version_id=source_version_id,
            blob_uri=blob_uri,
            sha256=sha256,
            size_bytes=size_bytes,
            record_count=record_count,
            schema=schema,
        )
        dataforge.store.add_run_event(run_id, "asset_published", "DataFlow 成果已生成数据资产", {"asset_version_id": asset_version["id"]})
        run = dataforge.store.transition_run(run_id, "completed", stats=stats, asset_version_id=asset_version["id"])
        dataforge.store.add_run_event(run_id, "completed", "发布完成")
        return {"run": run, "asset": asset, "asset_version": asset_version, "created": True}


def mount_dataflow_studio(app: FastAPI, settings: Settings) -> DataFlowStudio:
    studio = DataFlowStudio(settings)
    studio.mount(app)
    return studio


def _text2qa_config(dataset_id: str, serving_id: str | None) -> dict[str, Any]:
    return {
        "input_dataset": {"id": dataset_id},
        "operators": [
            {
                "name": "NormalizeMedicalTextOperator",
                "location": [100, 180],
                "params": {
                    "input_key": "raw_content",
                    "output_key": "normalized_content",
                },
            },
            {
                "name": "ChunkMedicalTextOperator",
                "location": [380, 180],
                "params": {
                    "chunk_size": 600,
                    "chunk_overlap": 80,
                    "input_key": "normalized_content",
                    "output_key": "content",
                },
            },
            {
                "name": "Text2QAGenerator",
                "location": [680, 180],
                "params": {
                    "llm_serving": serving_id,
                    "input_key": "content",
                    "input_question_num": 1,
                    "output_prompt_key": "generated_prompt",
                    "output_question_key": "question",
                    "output_answer_key": "answer",
                },
            },
            {
                "name": "Text2QASampleEvaluator",
                "location": [980, 180],
                "params": {
                    "llm_serving": serving_id,
                    "input_question_key": "question",
                    "input_answer_key": "answer",
                    "output_question_quality_key": "question_quality_grade",
                    "output_question_quality_feedback_key": "question_quality_feedback",
                    "output_answer_alignment_key": "answer_alignment_grade",
                    "output_answer_alignment_feedback_key": "answer_alignment_feedback",
                    "output_answer_verifiability_key": "answer_verifiability_grade",
                    "output_answer_verifiability_feedback_key": "answer_verifiability_feedback",
                    "output_downstream_value_key": "downstream_value_grade",
                    "output_downstream_value_feedback_key": "downstream_value_feedback",
                },
            },
        ],
    }


def _conversation_config(dataset_id: str, serving_id: str | None) -> dict[str, Any]:
    return {
        "input_dataset": {"id": dataset_id},
        "operators": [
            {
                "name": "ConsistentChatGenerator",
                "location": [180, 180],
                "params": {
                    "llm_serving": serving_id,
                    "num_dialogs_per_intent": 1,
                    "num_turns_per_dialog": 4,
                    "temperature": 0.7,
                    "prompt_template": "ConsistentChatPrompt",
                },
            },
            {
                "name": "ConversationSchemaAdapterOperator",
                "location": [560, 180],
                "params": {
                    "source_field": "conversation",
                    "target_field": "messages",
                },
            },
        ],
    }


def _llm_serving_ids(config: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for operator in config.get("operators") or []:
        params = operator.get("params") or {}
        if isinstance(params, dict) and isinstance(params.get("init"), list):
            values = {
                item.get("name"): item.get("value")
                for item in params["init"]
                if isinstance(item, dict)
            }
            serving_id = values.get("llm_serving")
        else:
            serving_id = params.get("llm_serving") if isinstance(params, dict) else None
        if isinstance(serving_id, dict):
            serving_id = serving_id.get("id") or serving_id.get("serving_id")
        if serving_id:
            result.add(str(serving_id))
    return result


def _operators_requiring_llm_serving(config: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for operator in config.get("operators") or []:
        if not isinstance(operator, dict):
            continue
        params = operator.get("params") or {}
        has_serving_parameter = isinstance(params, dict) and "llm_serving" in params
        if isinstance(params, dict) and isinstance(params.get("init"), list):
            has_serving_parameter = any(
                isinstance(item, dict) and item.get("name") == "llm_serving"
                for item in params["init"]
            )
        if has_serving_parameter and operator.get("name"):
            result.add(str(operator["name"]))
    return result


def _bind_missing_llm_serving(
    pipeline: dict[str, Any],
    serving_id: str,
) -> tuple[dict[str, Any], bool]:
    updated = json.loads(json.dumps(pipeline))
    changed = False
    for operator in (updated.get("config") or {}).get("operators") or []:
        params = operator.get("params") or {}
        init_params = params.get("init") if isinstance(params, dict) else None
        if not isinstance(init_params, list):
            continue
        for item in init_params:
            if item.get("name") == "llm_serving" and not item.get("value"):
                item["value"] = serving_id
                changed = True
    return updated, changed
