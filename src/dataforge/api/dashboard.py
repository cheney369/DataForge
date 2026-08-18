from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..application import DataForge
from ..deployment import readiness_report, utc_now
from .helpers import enrich_sources


def build_dashboard_router(
    dataforge: DataForge, *, studio=None, frontend_dist: Path | None = None
) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["workspace"])

    @router.get("/liveness")
    def liveness():
        return {"status": "alive", "checked_at": utc_now()}

    @router.get("/readiness")
    def readiness():
        report = readiness_report(
            dataforge, frontend_dist=frontend_dist, studio=studio
        )
        if not report["ready"]:
            return JSONResponse(status_code=503, content=report)
        return report

    @router.get("/health")
    def health():
        return dataforge.health()

    @router.get("/parser-capabilities")
    def parser_capabilities(refresh: bool = False):
        return dataforge.parser_capabilities.describe(refresh=refresh)

    @router.get("/dashboard")
    def dashboard():
        sources = enrich_sources(dataforge)
        runs = dataforge.store.list_runs()
        assets = dataforge.store.list_assets()
        knowledge_bases = dataforge.store.list_knowledge_bases()
        knowledge_indexes = dataforge.indexing.repository.list_knowledge_indexes()
        completed = sum(run["status"] == "completed" for run in runs)
        failed = sum(run["status"] == "failed" for run in runs)
        return {
            "counts": {
                "sources": len(sources),
                "source_versions": sum(item["version_count"] for item in sources),
                "runs": len(runs),
                "assets": len(assets),
            },
            "knowledge_counts": {
                "knowledge_bases": len(knowledge_bases),
                "knowledge_indexes": len(knowledge_indexes),
                "searchable_bases": len({
                    item["knowledge_base_id"]
                    for item in knowledge_indexes
                    if item["status"] == "available"
                }),
            },
            "run_summary": {
                "completed": completed,
                "failed": failed,
                "active": len(runs) - completed - failed,
            },
            "recent_runs": runs[:6],
            "recent_assets": assets[:6],
            "health": dataforge.health(),
        }

    return router
