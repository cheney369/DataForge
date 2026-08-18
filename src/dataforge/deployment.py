from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ValidationError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def readiness_report(
    dataforge,
    *,
    frontend_dist: Path | None = None,
    studio=None,
) -> dict[str, Any]:
    """Return a fast, side-effect-free deployment readiness snapshot."""
    checks: list[dict[str, Any]] = []
    settings = dataforge.settings

    required_dirs = [settings.state_dir, settings.blobs_dir, settings.runs_dir]
    missing_dirs = [str(path) for path in required_dirs if not path.is_dir()]
    unwritable_dirs = [str(path) for path in required_dirs if path.is_dir() and not os.access(path, os.W_OK)]
    state_status = "blocked" if missing_dirs or unwritable_dirs else "ready"
    checks.append(
        {
            "id": "state",
            "name": "状态目录",
            "status": state_status,
            "message": (
                f"状态目录可写：{settings.state_dir}"
                if state_status == "ready"
                else f"目录缺失或不可写：{', '.join(missing_dirs + unwritable_dirs)}"
            ),
        }
    )

    try:
        with dataforge.store.connect() as connection:
            connection.execute("SELECT 1").fetchone()
        database_status = "ready"
        database_message = f"SQLite 可访问：{settings.database_path}"
    except Exception as exc:
        database_status = "blocked"
        database_message = f"SQLite 不可访问：{exc}"
    checks.append(
        {
            "id": "database",
            "name": "元数据数据库",
            "status": database_status,
            "message": database_message,
        }
    )

    resolved_frontend = frontend_dist or settings.project_root / "frontend" / "dist"
    frontend_ready = (resolved_frontend / "index.html").is_file() and (
        resolved_frontend / "assets"
    ).is_dir()
    checks.append(
        {
            "id": "frontend",
            "name": "管理界面",
            "status": "ready" if frontend_ready else "warning",
            "message": (
                f"前端资源已构建：{resolved_frontend}"
                if frontend_ready
                else f"前端资源未构建：{resolved_frontend}"
            ),
        }
    )

    if studio is not None:
        dataflow_ready = bool(studio.status.backend_available)
        dataflow_message = studio.status.message
    else:
        dataflow_ready = bool(
            settings.dataflow_path and (settings.dataflow_path / "dataflow").is_dir()
        )
        dataflow_message = (
            f"DataFlow 源码可用：{settings.dataflow_path}"
            if dataflow_ready
            else "未发现 DataFlow；原生处理仍可使用"
        )
    checks.append(
        {
            "id": "dataflow",
            "name": "DataFlow 运行时",
            "status": "ready" if dataflow_ready else "warning",
            "message": dataflow_message,
        }
    )

    resources = _resource_summary(dataforge)
    resource_status = (
        "warning"
        if any(group["failed"] or group["configured"] for group in resources.values())
        else "ready"
    )
    checks.append(
        {
            "id": "model_storage",
            "name": "模型与存储",
            "status": resource_status,
            "message": "依赖状态来自最近一次连接测试；可运行 doctor --deep 刷新",
        }
    )

    blocked = [item for item in checks if item["status"] == "blocked"]
    warnings = [item for item in checks if item["status"] == "warning"]
    return {
        "status": "blocked" if blocked else "degraded" if warnings else "ready",
        "ready": not blocked,
        "checked_at": utc_now(),
        "environment": os.getenv("DATAFORGE_ENV", "development"),
        "checks": checks,
        "resources": resources,
        "configuration": {
            "project_root": str(settings.project_root),
            "state_dir": str(settings.state_dir),
            "dataflow_path": str(settings.dataflow_path) if settings.dataflow_path else None,
            "frontend_dist": str(resolved_frontend),
        },
    }


def probe_dependencies(dataforge) -> dict[str, Any]:
    """Explicitly call active model/storage services and persist their latest status."""
    repo = dataforge.indexing.repository
    groups = [
        ("llm", repo.list_llm_services(), dataforge.indexing.test_llm_service),
        ("embedding", repo.list_embedding_services(), dataforge.indexing.test_embedding_service),
        ("reranker", repo.list_reranker_services(), dataforge.indexing.test_reranker_service),
        ("vector", repo.list_vector_stores(), dataforge.indexing.test_vector_store),
        ("graph", repo.list_graph_stores(), dataforge.indexing.test_graph_store),
    ]
    results: list[dict[str, Any]] = []
    for kind, services, test in groups:
        for service in services:
            if not service.get("active", True):
                continue
            tested = test(service["id"])
            results.append(
                {
                    "kind": kind,
                    "id": tested["id"],
                    "name": tested["name"],
                    "status": tested["status"],
                    "last_test": tested.get("last_test") or {},
                }
            )
    return {
        "status": "ready" if all(item["status"] == "ready" for item in results) else "degraded",
        "checked_at": utc_now(),
        "results": results,
    }


def smoke_server(base_url: str, *, timeout_seconds: float = 10) -> dict[str, Any]:
    """Verify the public process, readiness and API surfaces of a running server."""
    base = base_url.rstrip("/")
    paths = ["/api/liveness", "/api/readiness", "/api/health"]
    checks = []
    for path in paths:
        started = time.monotonic()
        try:
            request = urllib.request.Request(
                f"{base}{path}", headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
                status_code = response.status
            ok = status_code == 200 and (
                path != "/api/readiness" or bool(body.get("ready"))
            )
            error = None
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            status_code = getattr(exc, "code", None)
            body = None
            ok = False
            error = str(exc)
        checks.append(
            {
                "path": path,
                "ok": ok,
                "status_code": status_code,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "status": body.get("status") if isinstance(body, dict) else None,
                "error": error,
            }
        )
    if not all(item["ok"] for item in checks):
        failed = ", ".join(item["path"] for item in checks if not item["ok"])
        raise ValidationError(f"服务冒烟检查失败：{failed}")
    return {"status": "ready", "base_url": base, "checks": checks}


def _resource_summary(dataforge) -> dict[str, dict[str, int]]:
    repo = dataforge.indexing.repository
    groups = {
        "llm": repo.list_llm_services(),
        "embedding": repo.list_embedding_services(),
        "reranker": repo.list_reranker_services(),
        "vector": repo.list_vector_stores(),
        "graph": repo.list_graph_stores(),
    }
    summary = {}
    for name, services in groups.items():
        active = [item for item in services if item.get("active", True)]
        summary[name] = {
            "total": len(active),
            "ready": sum(item.get("status") == "ready" for item in active),
            "configured": sum(item.get("status") == "configured" for item in active),
            "failed": sum(item.get("status") == "failed" for item in active),
        }
    return summary
