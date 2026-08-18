from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import (
    build_applications_router,
    build_assets_router,
    build_dashboard_router,
    build_delivery_router,
    build_documents_router,
    build_indexing_router,
    build_processing_router,
)
from .application import DataForge
from .config import Settings
from .dataflow_studio import mount_dataflow_studio
from .errors import AuthenticationError, DataForgeError, NotFoundError
from .knowledge import KnowledgeService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.load()
    dataforge = DataForge(resolved)
    knowledge = KnowledgeService(dataforge)
    recovered_job_ids = knowledge.recover_interrupted_jobs()
    recovered_index_job_ids = dataforge.indexing.repository.recover_interrupted_jobs()
    app = FastAPI(title="Medical DataForge", version="0.1.0")
    app.state.dataforge = dataforge
    app.state.recovered_knowledge_job_ids = recovered_job_ids
    app.state.recovered_index_job_ids = recovered_index_job_ids
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DataForgeError)
    async def dataforge_error_handler(_, exc: DataForgeError):
        status = (
            401 if isinstance(exc, AuthenticationError)
            else 404 if isinstance(exc, NotFoundError)
            else 400
        )
        return JSONResponse(
            status_code=status,
            content={"error": type(exc).__name__, "message": str(exc)},
            headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
        )

    studio = mount_dataflow_studio(app, resolved)
    app.state.dataflow_studio = studio
    knowledge.studio = studio
    if studio.status.backend_available:
        dataflow_llm_serving_id = None
        try:
            llm_services = [
                item
                for item in dataforge.indexing.repository.list_llm_services()
                if item.get("active", True)
            ]
            if llm_services:
                dataflow_llm_serving_id = studio.ensure_llm_serving(llm_services[0])["id"]
        except Exception as exc:
            studio.status.text2qa_message = f"Text2QA 模型服务同步失败：{exc}"
        try:
            app.state.dataflow_bootstrap = studio.bootstrap_basic_text_pipeline(dataforge)
        except Exception as exc:
            studio.status.basic_pipeline_ready = False
            studio.status.message = f"DataFlow 已接入，基础流程初始化失败：{exc}"
        try:
            app.state.dataflow_text2qa_bootstrap = studio.bootstrap_text2qa_pipeline(
                dataforge, serving_id=dataflow_llm_serving_id
            )
        except Exception as exc:
            studio.status.text2qa_pipeline_ready = False
            studio.status.text2qa_message = f"Text2QA 初始化失败：{exc}"
        try:
            app.state.dataflow_conversation_bootstrap = studio.bootstrap_conversation_pipeline(
                dataforge, serving_id=dataflow_llm_serving_id
            )
        except Exception as exc:
            studio.status.conversation_pipeline_configured = False
            studio.status.conversation_message = f"多轮对话流程初始化失败：{exc}"

    frontend_dist = resolved.project_root / "frontend" / "dist"
    app.include_router(
        build_dashboard_router(dataforge, studio=studio, frontend_dist=frontend_dist)
    )
    app.include_router(build_documents_router(dataforge, resolved))
    app.include_router(build_processing_router(dataforge, knowledge, studio))
    app.include_router(build_assets_router(dataforge, knowledge))
    app.include_router(build_indexing_router(dataforge))
    app.include_router(build_delivery_router(dataforge))
    app.include_router(build_applications_router(dataforge))

    assets_dir = frontend_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str):
        if full_path.startswith(("api/", "v1/")):
            raise HTTPException(status_code=404, detail="API route not found")
        index = frontend_dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return {
            "message": "DataForge API is running; build the frontend with `npm run build` in frontend/.",
            "docs": "/docs",
        }

    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.getenv("DATAFORGE_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("DATAFORGE_WEB_PORT", "8000"))
    uvicorn.run("dataforge.web:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
