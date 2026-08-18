from __future__ import annotations

from fastapi import APIRouter

from ..application import DataForge
from .schemas import (
    ApplicationBindingRequest,
    ApplicationQueryRequest,
    CollectionVersionRequest,
    KnowledgeCollectionRequest,
    PublishCollectionVersionRequest,
    RepointBindingRequest,
)


def build_delivery_router(dataforge: DataForge) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["delivery"])
    repository = dataforge.delivery.repository

    @router.get("/knowledge-collections")
    def list_knowledge_collections():
        return repository.list_collections()

    @router.post("/knowledge-collections", status_code=201)
    def create_knowledge_collection(payload: KnowledgeCollectionRequest):
        return dataforge.delivery.create_collection(
            payload.name, payload.description, payload.knowledge_type_id
        )

    @router.get("/knowledge-collections/{collection_id}")
    def get_knowledge_collection(collection_id: str):
        return {
            "collection": repository.get_collection(collection_id),
            "versions": repository.list_versions(collection_id),
        }

    @router.post("/knowledge-collections/{collection_id}/versions", status_code=201)
    def create_collection_version(collection_id: str, payload: CollectionVersionRequest):
        return dataforge.delivery.create_version(
            collection_id, payload.retrieval_profile_id, payload.knowledge_base_ids
        )

    @router.get("/collection-versions")
    def list_collection_versions(collection_id: str | None = None):
        return repository.list_versions(collection_id)

    @router.get("/collection-versions/{version_id}")
    def get_collection_version(version_id: str):
        return repository.get_version(version_id)

    @router.post("/collection-versions/{version_id}/publish")
    def publish_collection_version(
        version_id: str, payload: PublishCollectionVersionRequest
    ):
        return dataforge.delivery.publish_version(version_id, payload.make_current)

    @router.post("/collection-versions/{version_id}/query")
    def query_collection_version(version_id: str, payload: ApplicationQueryRequest):
        return dataforge.delivery.query_version(
            version_id, payload.query, filters=payload.filters, top_k=payload.top_k
        )

    @router.get("/application-bindings")
    def list_application_bindings():
        return repository.list_bindings()

    @router.post("/application-bindings", status_code=201)
    def create_application_binding(payload: ApplicationBindingRequest):
        return dataforge.delivery.create_binding(payload.model_dump(exclude_none=True))

    @router.get("/application-bindings/{binding_id}/events")
    def list_application_binding_events(binding_id: str):
        return repository.list_binding_events(binding_id)

    @router.post("/application-bindings/{binding_id}/repoint")
    def repoint_application_binding(binding_id: str, payload: RepointBindingRequest):
        return dataforge.delivery.repoint_binding(
            binding_id,
            collection_version_id=payload.collection_version_id,
            follow_latest=payload.follow_latest,
        )

    @router.post("/application-access/{binding_key}/query")
    def query_application_binding(binding_key: str, payload: ApplicationQueryRequest):
        return dataforge.delivery.query_binding(
            binding_key, payload.query, filters=payload.filters, top_k=payload.top_k
        )

    return router
