from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit


def pipeline_config_hash(config: dict[str, Any]) -> str:
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DataFlowAdapter:
    """Stable DataForge-facing facade over DataFlow WebUI registries and engine."""

    def __init__(self, container: Any, engine: Any, state_root: Path):
        self.container = container
        self.engine = engine
        self.state_root = state_root
        self._task_lock = threading.Lock()

    def list_pipelines(self) -> list[dict[str, Any]]:
        result = []
        for pipeline in self.container.pipeline_registry.list_pipelines():
            config = pipeline.get("config") or {}
            result.append(
                {
                    "id": pipeline.get("id"),
                    "name": pipeline.get("name") or "未命名流程",
                    "operator_count": len(config.get("operators") or []),
                    "operator_names": [item.get("name") for item in config.get("operators") or []],
                    "updated_at": pipeline.get("updated_at"),
                    "is_draft": not config.get("operators"),
                    "tags": pipeline.get("tags") or [],
                    "config_hash": pipeline_config_hash(config),
                }
            )
        return result

    def get_pipeline(self, pipeline_id: str) -> dict[str, Any] | None:
        pipeline = self.container.pipeline_registry.get_pipeline(pipeline_id)
        return copy.deepcopy(pipeline) if pipeline else None

    def ensure_pipeline(
        self,
        *,
        name: str,
        config: dict[str, Any],
        identity_tag: str,
    ) -> tuple[dict[str, Any], bool]:
        """Create a DataForge-managed Studio pipeline once and preserve later edits."""
        for pipeline in self.container.pipeline_registry.list_pipelines():
            if identity_tag in (pipeline.get("tags") or []):
                return copy.deepcopy(pipeline), False
        pipeline = self.container.pipeline_registry.create_pipeline(
            {
                "name": name,
                "config": copy.deepcopy(config),
                "tags": ["dataforge-managed", identity_tag],
            }
        )
        return copy.deepcopy(pipeline), True

    def update_pipeline(self, pipeline_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        pipeline = self.container.pipeline_registry.update_pipeline(
            pipeline_id,
            copy.deepcopy(payload),
        )
        return copy.deepcopy(pipeline)

    def capture_pipeline(self, pipeline_id: str) -> dict[str, Any] | None:
        pipeline = self.get_pipeline(pipeline_id)
        if not pipeline:
            return None
        config = pipeline.get("config") or {}
        return {
            "upstream_pipeline_id": pipeline_id,
            "name": pipeline.get("name") or "未命名流程",
            "config": config,
            "config_hash": pipeline_config_hash(config),
            "tags": pipeline.get("tags") or [],
            "upstream_updated_at": pipeline.get("updated_at"),
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        }

    def validate_pipeline(self, pipeline_id: str) -> dict[str, Any] | None:
        pipeline = self.get_pipeline(pipeline_id)
        if not pipeline:
            return None
        result = self.container.pipeline_registry.validate_pipeline_config(pipeline.get("config") or {})
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if hasattr(result, "dict"):
            return result.dict()
        return dict(result)

    def list_tasks(self, pipeline_id: str | None = None) -> list[dict[str, Any]]:
        tasks = self.container.task_registry.list_executions()
        if pipeline_id:
            tasks = [item for item in tasks if item.get("pipeline_id") == pipeline_id]
        tasks.sort(
            key=lambda item: item.get("completed_at") or item.get("started_at") or "",
            reverse=True,
        )
        return [
            {
                "task_id": item.get("task_id"),
                "pipeline_id": item.get("pipeline_id"),
                "status": item.get("status"),
                "started_at": item.get("started_at"),
                "completed_at": item.get("completed_at"),
            }
            for item in tasks
        ]

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        task = self.container.task_registry.get(task_id)
        return copy.deepcopy(task) if task else None

    def get_task_detail(self, task_id: str, *, limit: int = 8) -> dict[str, Any] | None:
        task = self.get_task(task_id)
        if not task:
            return None
        status = self.container.task_registry.get_execution_status(task_id)
        logs = self.container.task_registry.get_execution_logs(task_id)
        result = self.container.task_registry.get_execution_result(task_id, limit=max(1, min(limit, 50)))
        safe_result = None
        if result:
            safe_result = {
                key: result.get(key)
                for key in (
                    "task_id",
                    "pipeline_id",
                    "status",
                    "step",
                    "operator_name",
                    "operator_status",
                    "sample_data",
                    "sample_count",
                    "total_count",
                    "file_exists",
                    "started_at",
                    "completed_at",
                    "operators_detail",
                )
            }
        safe_task = {
            key: task.get(key)
            for key in (
                "task_id",
                "pipeline_id",
                "status",
                "started_at",
                "completed_at",
            )
        }
        safe_status = None
        if status:
            safe_status = {
                key: status.get(key)
                for key in (
                    "task_id",
                    "pipeline_id",
                    "status",
                    "operators_detail",
                    "operator_logs",
                    "started_at",
                    "completed_at",
                )
            }
        return {"task": safe_task, "status": safe_status, "logs": logs, "result": safe_result}

    def execute_pipeline(
        self,
        pipeline_id: str,
        config: dict[str, Any],
        *,
        on_task_started: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        frozen_config = copy.deepcopy(config)
        with self._task_lock:
            task_id, _, _ = self.container.task_registry.start_execution(config=frozen_config)
            self.container.task_registry.update(task_id, {"pipeline_id": pipeline_id})
            if on_task_started:
                try:
                    on_task_started(task_id)
                except Exception:
                    self.container.task_registry.kill_execution(task_id)
                    raise
            # Upstream registries and intermediate cache files are file-backed and
            # shared, so execution must stay inside the lock until DataFlow offers
            # isolated task storage.
            result = self.engine.run(frozen_config, task_id, execution_path=None)
            updated = self.container.task_registry.update(task_id, result)
        return updated or {"task_id": task_id, **result}

    def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if not task or task.get("status") in {
            "completed",
            "success",
            "failed",
            "cancelled",
            "canceled",
        }:
            return False
        return bool(self.container.task_registry.kill_execution(task_id))

    def register_dataset(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.container.dataset_registry.add_or_update(payload)

    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        dataset = self.container.dataset_registry.get(dataset_id)
        return copy.deepcopy(dataset) if dataset else None

    def list_datasets(self) -> list[dict[str, Any]]:
        return self.container.dataset_registry.list()

    def list_operators(self, lang: str = "zh") -> list[dict[str, Any]]:
        return self.container.operator_registry.get_op_list(lang=lang)

    def list_schemas(self) -> list[dict[str, Any]]:
        return self.container.json_schema_manager.list_all()

    def list_servings(self) -> list[dict[str, Any]]:
        """Return serving metadata without exposing API keys or secret values."""
        registry = self.container.serving_registry._get_all() or {}
        result: list[dict[str, Any]] = []
        for serving_id, serving in registry.items():
            values = {
                item.get("name"): (
                    item.get("value")
                    if item.get("value") is not None
                    else item.get("default_value")
                )
                for item in serving.get("params") or []
                if item.get("name")
            }
            key_name = values.get("key_name_of_api_key") or f"DF_API_KEY_{serving_id}"
            has_inline_key = bool(values.get("api_key"))
            key_configured = has_inline_key or bool(os.getenv(str(key_name)))
            result.append(
                {
                    "id": serving_id,
                    "name": serving.get("name") or "未命名模型服务",
                    "class_name": serving.get("cls_name"),
                    "api_url": _safe_api_url(values.get("api_url")),
                    "model_name": values.get("model_name"),
                    "key_configured": key_configured,
                    "ready": serving.get("cls_name") == "APILLMServing_request" and key_configured,
                }
            )
        return result

    def ensure_api_llm_serving(self, service: dict[str, Any]) -> dict[str, Any]:
        """Mirror a DataForge LLM resource into DataFlow without storing its secret."""
        registry = self.container.serving_registry
        name = f"DataForge · {service['id']}"
        existing = next(
            (
                (serving_id, item)
                for serving_id, item in (registry._get_all() or {}).items()
                if item.get("name") == name
                and item.get("cls_name") == "APILLMServing_request"
            ),
            None,
        )
        classes = registry.get_serving_classes()
        class_info = next(
            (
                item
                for item in classes
                if item.get("cls_name") == "APILLMServing_request"
            ),
            None,
        )
        if not class_info:
            raise ValueError("DataFlow APILLMServing_request is unavailable")
        values = {
            "api_url": _chat_completions_url(service["base_url"]),
            "model_name": service["model"],
            "temperature": 0.0,
            "max_workers": 4,
            "max_retries": int(service.get("max_retries") or 1),
            "connect_timeout": 10.0,
            "read_timeout": float(service.get("timeout_seconds") or 60),
        }
        params = copy.deepcopy(class_info.get("params") or [])
        for param in params:
            if param.get("name") in values:
                param["value"] = values[param["name"]]
        if existing:
            serving_id = existing[0]
            registry._update(serving_id, name=name, params=params)
        else:
            serving_id = registry._set(name, "APILLMServing_request", params)

        configured = registry._get(serving_id)
        configured_values = {
            item.get("name"): (
                item.get("value")
                if item.get("value") is not None
                else item.get("default_value")
            )
            for item in configured.get("params") or []
        }
        key_name = str(
            configured_values.get("key_name_of_api_key")
            or f"DF_API_KEY_{serving_id}"
        )
        key_reference = str(service.get("api_key_env") or "").strip()
        if key_reference:
            api_key = os.getenv(key_reference)
            if not api_key:
                raise ValueError(f"LLM API Key 环境变量尚未配置：{key_reference}")
        else:
            # APILLMServing_request always sends a Bearer header. The current
            # internal endpoint does not require authentication, so a non-secret
            # placeholder keeps the upstream interface usable without persisting it.
            api_key = os.getenv(
                "DATAFORGE_DATAFLOW_NO_AUTH_TOKEN", "dataforge-internal"
            )
        os.environ[key_name] = api_key
        return next(
            item for item in self.list_servings() if item["id"] == serving_id
        )

    def ready_serving_ids(self) -> set[str]:
        return {item["id"] for item in self.list_servings() if item["ready"]}

    def output_file(self, task_id: str) -> Path | None:
        task = self.get_task(task_id)
        if not task:
            return None
        persisted = (task.get("output") or {}).get("final_output_file")
        if persisted and Path(persisted).is_file():
            return Path(persisted)
        results = (task.get("output") or {}).get("execution_results") or []
        if not results:
            return None
        step = int(results[-1].get("index", len(results) - 1)) + 1
        candidates = (
            self.state_root / "cache" / "task_outputs" / f"{task_id}.jsonl",
            self.state_root / "cache" / f"{task_id}_output" / f"dataflow_cache_step_step{step}.jsonl",
            self.state_root / "cache" / f"dataflow_cache_step_{step - 1}.jsonl",
        )
        return next((candidate for candidate in candidates if candidate.is_file()), None)


def _safe_api_url(value: Any) -> str | None:
    if not value:
        return None
    parsed = urlsplit(str(value))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _chat_completions_url(value: Any) -> str:
    base = str(value).rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"
