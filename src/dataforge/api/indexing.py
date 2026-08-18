from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks

from ..application import DataForge
from ..errors import ValidationError
from .schemas import (
    CreateIndexRequest,
    EmbeddingServiceRequest,
    GraphStoreRequest,
    IndexProfileRequest,
    LLMServiceRequest,
    PublishProfileRequest,
    RerankerServiceRequest,
    RetrievalProfileRequest,
    RetrievalQueryRequest,
    VectorStoreRequest,
)


def _run_index_job(dataforge: DataForge, job_id: str) -> None:
    try:
        dataforge.indexing.execute_job(job_id)
    except Exception:
        return


def _clean(payload: Any) -> dict[str, Any]:
    return payload.model_dump(exclude_none=True)


def build_indexing_router(dataforge: DataForge) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["indexing"])
    repo = dataforge.indexing.repository

    @router.get("/llm-services")
    def list_llm_services():
        return repo.list_llm_services()

    @router.post("/llm-services", status_code=201)
    def save_llm_service(payload: LLMServiceRequest):
        if not payload.name.strip() or not payload.base_url.strip() or not payload.model.strip():
            raise ValidationError("LLM 服务名称、地址和模型不能为空")
        return repo.save_llm_service(_clean(payload))

    @router.post("/llm-services/{service_id}/test")
    def test_llm_service(service_id: str):
        return dataforge.indexing.test_llm_service(service_id)

    @router.get("/embedding-services")
    def list_embedding_services():
        return repo.list_embedding_services()

    @router.post("/embedding-services", status_code=201)
    def save_embedding_service(payload: EmbeddingServiceRequest):
        if not payload.name.strip() or not payload.base_url.strip() or not payload.model.strip():
            raise ValidationError("模型服务名称、地址和模型不能为空")
        return repo.save_embedding_service(_clean(payload))

    @router.post("/embedding-services/{service_id}/test")
    def test_embedding_service(service_id: str):
        return dataforge.indexing.test_embedding_service(service_id)

    @router.get("/reranker-services")
    def list_reranker_services():
        return repo.list_reranker_services()

    @router.post("/reranker-services", status_code=201)
    def save_reranker_service(payload: RerankerServiceRequest):
        if not payload.name.strip() or not payload.base_url.strip() or not payload.model.strip():
            raise ValidationError("Reranker 服务名称、地址和模型不能为空")
        return repo.save_reranker_service(_clean(payload))

    @router.post("/reranker-services/{service_id}/test")
    def test_reranker_service(service_id: str):
        return dataforge.indexing.test_reranker_service(service_id)

    @router.get("/vector-stores")
    def list_vector_stores():
        return repo.list_vector_stores()

    @router.post("/vector-stores", status_code=201)
    def save_vector_store(payload: VectorStoreRequest):
        if payload.kind not in {"milvus", "memory"}:
            raise ValidationError("当前仅支持 Milvus 向量库")
        return repo.save_vector_store(_clean(payload))

    @router.post("/vector-stores/{store_id}/test")
    def test_vector_store(store_id: str):
        return dataforge.indexing.test_vector_store(store_id)

    @router.get("/graph-stores")
    def list_graph_stores():
        return repo.list_graph_stores()

    @router.post("/graph-stores", status_code=201)
    def save_graph_store(payload: GraphStoreRequest):
        if payload.kind not in {"neo4j", "memory"}:
            raise ValidationError("当前仅支持 Neo4j 图数据库")
        return repo.save_graph_store(_clean(payload))

    @router.post("/graph-stores/{store_id}/test")
    def test_graph_store(store_id: str):
        return dataforge.indexing.test_graph_store(store_id)

    @router.get("/index-profiles")
    def list_index_profiles(knowledge_type_id: str | None = None):
        return repo.list_index_profiles(knowledge_type_id)

    @router.post("/index-profiles", status_code=201)
    def create_index_profile(payload: IndexProfileRequest):
        return repo.create_index_profile(_clean(payload))

    @router.get("/index-profiles/{profile_id}/preview")
    def preview_index_profile(profile_id: str, base_id: str | None = None):
        return dataforge.indexing.preview_profile(profile_id, base_id)

    @router.post("/index-profiles/{profile_id}/publish")
    def publish_index_profile(profile_id: str, payload: PublishProfileRequest):
        return dataforge.indexing.publish_profile(
            profile_id, base_id=payload.base_id, make_default=payload.make_default
        )

    @router.post("/index-profiles/{profile_id}/deactivate")
    def deactivate_index_profile(profile_id: str):
        return repo.deactivate_index_profile(profile_id)

    @router.get("/knowledge-indexes")
    def list_knowledge_indexes(knowledge_base_id: str | None = None):
        return repo.list_knowledge_indexes(knowledge_base_id)

    @router.post("/knowledge-indexes", status_code=202)
    def create_knowledge_index(payload: CreateIndexRequest, background_tasks: BackgroundTasks):
        created = dataforge.indexing.create_index(
            payload.knowledge_base_id, payload.index_profile_id
        )
        background_tasks.add_task(_run_index_job, dataforge, created["index_job"]["id"])
        return created

    @router.get("/index-jobs")
    def list_index_jobs():
        return repo.list_index_jobs()

    @router.get("/index-jobs/{job_id}")
    def get_index_job(job_id: str):
        return {"job": repo.get_index_job(job_id), "batches": repo.list_batches(job_id)}

    @router.post("/index-jobs/{job_id}/cancel")
    def cancel_index_job(job_id: str):
        return repo.request_index_job_cancel(job_id)

    @router.post("/index-jobs/{job_id}/retry", status_code=202)
    def retry_index_job(job_id: str, background_tasks: BackgroundTasks):
        retry = dataforge.indexing.retry_job(job_id)
        background_tasks.add_task(_run_index_job, dataforge, retry["id"])
        return retry

    @router.get("/retrieval-profiles")
    def list_retrieval_profiles():
        return repo.list_retrieval_profiles()

    @router.post("/retrieval-profiles", status_code=201)
    def create_retrieval_profile(payload: RetrievalProfileRequest):
        return repo.create_retrieval_profile(_clean(payload))

    @router.post("/retrieval-profiles/{profile_id}/publish")
    def publish_retrieval_profile(profile_id: str, payload: PublishProfileRequest):
        return dataforge.indexing.publish_retrieval_profile(
            profile_id, base_id=payload.base_id, make_default=payload.make_default
        )

    @router.post("/retrieval/query")
    def query(payload: RetrievalQueryRequest):
        return dataforge.indexing.query(
            payload.retrieval_profile_id,
            payload.knowledge_base_id,
            payload.query,
            filters=payload.filters,
            top_k=payload.top_k,
        )

    return router
