from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from ..application import DataForge
from ..config import Settings
from ..ingestion import preview_source_records
from .helpers import enrich_sources


def build_documents_router(dataforge: DataForge, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["documents"])

    @router.get("/sources")
    def list_sources(query: str = "", kind: str = ""):
        sources = enrich_sources(dataforge)
        normalized_query = query.strip().casefold()
        normalized_kind = kind.strip().casefold().removeprefix(".")
        if normalized_query:
            sources = [
                source
                for source in sources
                if normalized_query in source["name"].casefold()
                or any(
                    normalized_query in version["original_filename"].casefold()
                    for version in source["versions"]
                )
            ]
        if normalized_kind:
            sources = [
                source
                for source in sources
                if source["kind"].casefold() == normalized_kind
                or any(
                    Path(version["original_filename"]).suffix.casefold().removeprefix(".")
                    == normalized_kind
                    for version in source["versions"]
                )
            ]
        return sources

    @router.post("/sources", status_code=201)
    async def upload_source(
        file: UploadFile = File(...),
        name: str | None = Form(None),
        kind: str = Form("file"),
        source_id: str | None = Form(None),
    ):
        upload_dir = settings.state_dir / "uploads"
        temporary_dir = upload_dir / uuid.uuid4().hex
        temporary_dir.mkdir(parents=True, exist_ok=False)
        safe_name = Path(file.filename or "upload.txt").name
        temporary = temporary_dir / safe_name
        try:
            with temporary.open("wb") as handle:
                while chunk := await file.read(1024 * 1024):
                    handle.write(chunk)
            result = dataforge.sources.ingest(
                temporary,
                source_id=source_id,
                name=name or Path(safe_name).stem,
                kind=kind,
            )
            return {
                "source": result.source,
                "source_version": result.source_version,
                "created": result.created,
            }
        finally:
            await file.close()
            temporary.unlink(missing_ok=True)
            temporary_dir.rmdir()

    @router.get("/sources/{source_id}/versions")
    def list_source_versions(source_id: str):
        return dataforge.store.list_source_versions(source_id)

    @router.get("/source-versions/{source_version_id}/preview")
    def preview_source_version(
        source_version_id: str,
        max_records: int = 20,
        max_chars: int = 12_000,
    ):
        version = dataforge.store.get_source_version(source_version_id)
        path = dataforge.blobs.resolve(version["blob_uri"])
        preview = preview_source_records(
            path,
            version,
            max_records=max(1, min(max_records, 50)),
            max_chars=max(500, min(max_chars, 50_000)),
        )
        return {"source_version": version, **preview}

    @router.get("/source-versions/{source_version_id}/download")
    def download_source_version(source_version_id: str):
        version = dataforge.store.get_source_version(source_version_id)
        path = dataforge.blobs.resolve(version["blob_uri"])
        return FileResponse(
            path,
            filename=version["original_filename"],
            media_type=version["media_type"],
        )

    return router
