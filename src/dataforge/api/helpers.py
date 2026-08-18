from __future__ import annotations

import json
from typing import Any

from ..application import DataForge
from ..knowledge import KnowledgeService


def execute_run_safely(dataforge: DataForge, run_id: str) -> None:
    try:
        dataforge.execute_run(run_id)
    except Exception:
        # The application layer persists terminal failure details.
        return


def execute_knowledge_job_safely(service: KnowledgeService, job_id: str) -> None:
    try:
        completed = service.execute_job(job_id)
        # Knowledge publication is committed and marked complete before this
        # independently recoverable derived stage starts.
        base_id = completed.get("knowledge_base_id")
        if completed.get("status") == "completed" and base_id:
            pending = [
                job
                for job in service.dataforge.indexing.repository.list_index_jobs()
                if job["knowledge_base_id"] == base_id and job["status"] == "pending"
            ]
            for index_job in pending:
                service.dataforge.indexing.execute_job(index_job["id"])
    except Exception:
        return


def enrich_sources(dataforge: DataForge) -> list[dict[str, Any]]:
    result = []
    for source in dataforge.store.list_sources():
        versions = dataforge.store.list_source_versions(source["id"])
        result.append(
            {
                **source,
                "version_count": len(versions),
                "latest_version": versions[0] if versions else None,
                "versions": versions,
            }
        )
    return result


def read_asset_preview(dataforge: DataForge, asset_version_id: str, limit: int) -> list[Any]:
    version = dataforge.store.get_asset_version(asset_version_id)
    path = dataforge.blobs.resolve(version["blob_uri"])
    records: list[Any] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            records.append(json.loads(line))
            if len(records) >= limit:
                break
    return records
