from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..application import DEFAULT_PIPELINE_ID


class RunRequest(BaseModel):
    source_version_id: str
    pipeline_id: str = DEFAULT_PIPELINE_ID
    engine: str | None = None


class KnowledgeJobRequest(BaseModel):
    name: str
    knowledge_type_id: str
    standard_pipeline_id: str | None = None
    source_version_ids: list[str]


class KnowledgeTypeRequest(BaseModel):
    name: str
    description: str = ""
    schema: dict[str, Any]


class StandardPipelinePublishRequest(BaseModel):
    name: str
    description: str = ""
    knowledge_type_id: str
    dataflow_pipeline_id: str
    sample_task_id: str
    version: int = 1
    make_default: bool = True


class EmbeddingServiceRequest(BaseModel):
    id: str | None = None
    name: str
    provider: str = "openai-compatible"
    base_url: str
    model: str
    dimension: int = 0
    batch_size: int = 32
    concurrency: int = 1
    timeout_seconds: float = 30
    max_retries: int = 2
    api_key_env: str = ""


class RerankerServiceRequest(BaseModel):
    id: str | None = None
    name: str
    provider: str = "openai-compatible"
    base_url: str
    model: str
    timeout_seconds: float = 30
    max_retries: int = 1
    api_key_env: str = ""


class LLMServiceRequest(BaseModel):
    id: str | None = None
    name: str
    provider: str = "openai-compatible"
    base_url: str
    model: str
    timeout_seconds: float = 60
    max_retries: int = 1
    api_key_env: str = ""


class VectorStoreRequest(BaseModel):
    id: str | None = None
    name: str
    kind: str = "milvus"
    uri: str
    database_name: str = "default"
    collection_prefix: str = "dataforge"
    token_env: str = ""


class GraphStoreRequest(BaseModel):
    id: str | None = None
    name: str
    kind: str = "neo4j"
    uri: str
    graph_space: str = "neo4j"
    username_env: str = ""
    password_env: str = ""


class IndexProfileRequest(BaseModel):
    logical_key: str | None = None
    name: str
    description: str = ""
    knowledge_type_id: str
    embedding_service_id: str
    vector_store_id: str
    graph_store_id: str | None = None
    config: dict[str, Any]


class PublishProfileRequest(BaseModel):
    base_id: str | None = None
    make_default: bool = True


class CreateIndexRequest(BaseModel):
    knowledge_base_id: str
    index_profile_id: str | None = None


class RetrievalProfileRequest(BaseModel):
    logical_key: str | None = None
    name: str
    description: str = ""
    index_profile_id: str
    config: dict[str, Any]


class RetrievalQueryRequest(BaseModel):
    retrieval_profile_id: str
    knowledge_base_id: str
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int | None = None


class KnowledgeCollectionRequest(BaseModel):
    name: str
    description: str = ""
    knowledge_type_id: str


class CollectionVersionRequest(BaseModel):
    retrieval_profile_id: str
    knowledge_base_ids: list[str] = Field(default_factory=list)


class PublishCollectionVersionRequest(BaseModel):
    make_current: bool = True


class ApplicationBindingRequest(BaseModel):
    binding_key: str
    name: str
    description: str = ""
    collection_id: str
    collection_version_id: str | None = None
    follow_latest: bool = True


class RepointBindingRequest(BaseModel):
    collection_version_id: str | None = None
    follow_latest: bool = True


class ApplicationQueryRequest(BaseModel):
    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int | None = None


class AIApplicationRequest(BaseModel):
    app_key: str
    name: str
    description: str = ""


class AIApplicationVersionRequest(BaseModel):
    application_binding_id: str
    llm_service_id: str
    config: dict[str, Any]


class AIApplicationChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int | None = None


class AIApplicationCredentialRequest(BaseModel):
    name: str


class AIApplicationInvokeRequest(BaseModel):
    inputs: dict[str, Any]
    history: list[dict[str, str]] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    user_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    stream: bool = False
