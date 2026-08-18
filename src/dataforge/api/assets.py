from fastapi import APIRouter
from fastapi.responses import FileResponse

from ..application import DataForge
from ..knowledge import KnowledgeService
from .helpers import read_asset_preview


def build_assets_router(dataforge: DataForge, knowledge: KnowledgeService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["assets"])

    @router.get("/knowledge-bases")
    def list_knowledge_bases():
        return [
            {**base, **dataforge.indexing.repository.summarize_knowledge_base(base["id"])}
            for base in dataforge.store.list_knowledge_bases()
        ]

    @router.get("/knowledge-bases/{base_id}")
    def get_knowledge_base(base_id: str, page: int = 1, page_size: int = 50, query: str = ""):
        safe_page = max(1, page)
        safe_size = max(10, min(page_size, 100))
        total = dataforge.store.count_knowledge_records(base_id, query)
        base = dataforge.store.get_knowledge_base(base_id)
        return {
            "knowledge_base": {
                **base,
                **dataforge.indexing.repository.summarize_knowledge_base(base_id),
            },
            "records": dataforge.store.list_knowledge_records(
                base_id, safe_size, (safe_page - 1) * safe_size, query
            ),
            "pagination": {
                "page": safe_page,
                "page_size": safe_size,
                "total": total,
                "pages": max(1, (total + safe_size - 1) // safe_size),
            },
            "query": query,
        }

    @router.get("/knowledge-records/{record_id}/lineage")
    def get_knowledge_record_lineage(record_id: str):
        return knowledge.get_record_lineage(record_id)

    @router.get("/assets")
    def list_assets():
        return dataforge.store.list_assets()

    @router.get("/assets/{asset_id}/versions")
    def list_asset_versions(asset_id: str):
        return dataforge.store.list_asset_versions(asset_id)

    @router.get("/asset-versions/{asset_version_id}/lineage")
    def get_lineage(asset_version_id: str):
        return dataforge.lineage(asset_version_id)

    @router.get("/asset-versions/{asset_version_id}/preview")
    def preview_asset(asset_version_id: str, limit: int = 5):
        return read_asset_preview(dataforge, asset_version_id, max(1, min(limit, 50)))

    @router.get("/asset-versions/{asset_version_id}/download")
    def download_asset(asset_version_id: str):
        version = dataforge.store.get_asset_version(asset_version_id)
        path = dataforge.blobs.resolve(version["blob_uri"])
        return FileResponse(
            path,
            filename=f"{asset_version_id}.jsonl",
            media_type="application/x-ndjson",
        )

    return router
