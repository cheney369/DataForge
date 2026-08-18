from __future__ import annotations

import hashlib
import json
import os
from threading import BoundedSemaphore, Lock
from typing import Any, TYPE_CHECKING

from ..errors import ValidationError
from .embeddings import OpenAIEmbeddingClient
from .graph_stores import create_graph_store
from .llms import OpenAIChatClient
from .rerankers import OpenAIRerankerClient
from .repository import IndexingRepository
from .templates import build_projection, referenced_fields, render_template
from .vector_stores import create_vector_store, validate_field_name

if TYPE_CHECKING:
    from ..application import DataForge


DEFAULT_EMBEDDING_ID = "embedding-bce-local"
DEFAULT_VECTOR_STORE_ID = "vector-milvus-local"
DEFAULT_LLM_ID = "llm-qwen3-local"
DEFAULT_RERANKER_ID = "reranker-bge-local"

_EMBEDDING_LIMITS: dict[tuple[str, int], BoundedSemaphore] = {}
_EMBEDDING_LIMITS_LOCK = Lock()

DEFAULT_PROFILE_CONFIGS = {
    "text_chunk": {
        "name": "文本块语义索引",
        "embedding_template": "{{ content }}",
        "stored_fields": ["content", "chunk_index"],
        "metadata_fields": ["source_locator"],
    },
    "faq": {
        "name": "FAQ 问题语义索引",
        "embedding_template": "{{ question }}",
        "stored_fields": ["question", "answer"],
        "metadata_fields": ["source_locator"],
    },
    "knowledge_triple": {
        "name": "知识三元组语义索引",
        "embedding_template": "{{ subject }} | {{ predicate }} | {{ object }}",
        "stored_fields": ["subject", "predicate", "object"],
        "metadata_fields": ["source_locator"],
    },
    "multi_turn_dialogue": {
        "name": "多轮对话窗口索引",
        "embedding_template": "{{ messages }}",
        "stored_fields": ["messages"],
        "metadata_fields": ["source_locator"],
    },
}


class IndexingService:
    def __init__(self, dataforge: DataForge):
        self.dataforge = dataforge
        self.repository = IndexingRepository(dataforge.store)
        self.repository.initialize()
        self.seed_defaults()

    def seed_defaults(self) -> None:
        if not self.repository.list_llm_services():
            self.repository.save_llm_service(
                {
                    "id": DEFAULT_LLM_ID,
                    "name": "Qwen3 本地 LLM",
                    "provider": "openai-compatible",
                    "base_url": os.getenv(
                        "DATAFORGE_LLM_BASE_URL",
                        "http://127.0.0.1:8001/v1",
                    ),
                    "model": os.getenv("DATAFORGE_LLM_MODEL", "Qwen3-32B"),
                    "timeout_seconds": 60,
                    "max_retries": 1,
                    "api_key_env": os.getenv("DATAFORGE_LLM_API_KEY_ENV", ""),
                }
            )
        if not self.repository.list_embedding_services():
            self.repository.save_embedding_service(
                {
                    "id": DEFAULT_EMBEDDING_ID,
                    "name": "BCE 本地 Embedding",
                    "provider": "openai-compatible",
                    "base_url": os.getenv(
                        "DATAFORGE_EMBEDDING_BASE_URL",
                        "http://127.0.0.1:8002/v1",
                    ),
                    "model": os.getenv("DATAFORGE_EMBEDDING_MODEL", "bce-embedding-base"),
                    "dimension": int(os.getenv("DATAFORGE_EMBEDDING_DIMENSION", "768")),
                    "batch_size": int(os.getenv("DATAFORGE_EMBEDDING_BATCH_SIZE", "32")),
                    "concurrency": int(os.getenv("DATAFORGE_EMBEDDING_CONCURRENCY", "1")),
                    "timeout_seconds": 30,
                    "max_retries": 2,
                    "api_key_env": os.getenv("DATAFORGE_EMBEDDING_API_KEY_ENV", ""),
                }
            )
        if not self.repository.list_reranker_services():
            self.repository.save_reranker_service(
                {
                    "id": DEFAULT_RERANKER_ID,
                    "name": "BGE 本地 Reranker",
                    "provider": "openai-compatible",
                    "base_url": os.getenv(
                        "DATAFORGE_RERANKER_BASE_URL",
                        "http://127.0.0.1:8197/v1",
                    ),
                    "model": os.getenv(
                        "DATAFORGE_RERANKER_MODEL", "bge-reranker-large"
                    ),
                    "timeout_seconds": 30,
                    "max_retries": 1,
                    "api_key_env": os.getenv("DATAFORGE_RERANKER_API_KEY_ENV", ""),
                }
            )
        if not self.repository.list_vector_stores():
            self.repository.save_vector_store(
                {
                    "id": DEFAULT_VECTOR_STORE_ID,
                    "name": "Milvus Standalone",
                    "kind": os.getenv("DATAFORGE_VECTOR_STORE_KIND", "milvus"),
                    "uri": os.getenv("DATAFORGE_MILVUS_URI", "http://127.0.0.1:19530"),
                    "database_name": os.getenv("DATAFORGE_MILVUS_DATABASE", "default"),
                    "collection_prefix": os.getenv(
                        "DATAFORGE_MILVUS_COLLECTION_PREFIX", "dataforge"
                    ),
                    "token_env": os.getenv("DATAFORGE_MILVUS_TOKEN_ENV", ""),
                }
            )
        existing = {item["logical_key"] for item in self.repository.list_index_profiles()}
        for knowledge_type_id, defaults in DEFAULT_PROFILE_CONFIGS.items():
            logical_key = f"default-{knowledge_type_id}"
            if logical_key in existing:
                continue
            config = {
                "embedding_template": defaults["embedding_template"],
                "stored_fields": defaults["stored_fields"],
                "metadata_fields": defaults["metadata_fields"],
                "filter_fields": [],
                "missing_policy": "error",
                "metric_type": "COSINE",
            }
            self.repository.create_index_profile(
                {
                    "logical_key": logical_key,
                    "name": defaults["name"],
                    "description": "系统预置草稿，可在页面中调整、验证并发布。",
                    "knowledge_type_id": knowledge_type_id,
                    "embedding_service_id": DEFAULT_EMBEDDING_ID,
                    "vector_store_id": DEFAULT_VECTOR_STORE_ID,
                    "config": config,
                }
            )

    def test_embedding_service(self, service_id: str) -> dict[str, Any]:
        service = self.repository.get_embedding_service(service_id)
        try:
            result = OpenAIEmbeddingClient(service).test()
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
        return self.repository.record_embedding_test(service_id, result)

    def test_llm_service(self, service_id: str) -> dict[str, Any]:
        service = self.repository.get_llm_service(service_id)
        try:
            result = OpenAIChatClient(service).test()
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
        return self.repository.record_llm_test(service_id, result)

    def test_reranker_service(self, service_id: str) -> dict[str, Any]:
        service = self.repository.get_reranker_service(service_id)
        try:
            result = OpenAIRerankerClient(service).test()
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
        return self.repository.record_reranker_test(service_id, result)

    def test_vector_store(self, store_id: str) -> dict[str, Any]:
        config = self.repository.get_vector_store(store_id)
        try:
            result = create_vector_store(config).test()
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
        return self.repository.record_vector_store_test(store_id, result)

    def test_graph_store(self, store_id: str) -> dict[str, Any]:
        config = self.repository.get_graph_store(store_id)
        try:
            result = create_graph_store(config).test()
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
        return self.repository.record_graph_store_test(store_id, result)

    def preview_profile(self, profile_id: str, base_id: str | None = None) -> dict[str, Any]:
        profile = self.repository.get_index_profile(profile_id)
        knowledge_type = self.dataforge.store.get_knowledge_type(profile["knowledge_type_id"])
        sample = self._sample_record(knowledge_type, base_id)
        indexed_text, metadata, filters = build_projection(
            sample["data"], sample.get("source_locator") or {}, profile["config"]
        )
        return {
            "sample": sample["data"],
            "indexed_text": indexed_text,
            "metadata": metadata,
            "filter_fields": filters,
        }

    def publish_profile(
        self, profile_id: str, *, base_id: str | None = None, make_default: bool = True
    ) -> dict[str, Any]:
        profile = self.repository.get_index_profile(profile_id)
        self._validate_profile_fields(profile)
        embedding = self.test_embedding_service(profile["embedding_service_id"])
        vector = self.test_vector_store(profile["vector_store_id"])
        if embedding["status"] != "ready":
            raise ValidationError(
                f"Embedding 服务未就绪：{embedding.get('last_test', {}).get('error', '连接失败')}"
            )
        if vector["status"] != "ready":
            raise ValidationError(
                f"向量库未就绪：{vector.get('last_test', {}).get('error', '连接失败')}"
            )
        graph = None
        if profile.get("graph_store_id"):
            graph = self.test_graph_store(profile["graph_store_id"])
            if graph["status"] != "ready":
                raise ValidationError(
                    f"图数据库未就绪：{graph.get('last_test', {}).get('error', '连接失败')}"
                )
        preview = self.preview_profile(profile_id, base_id)
        embedding_batch = self._embed(embedding, [preview["indexed_text"]])
        config = {
            **profile["config"],
            "_snapshots": {
                "embedding_service": embedding,
                "vector_store": vector,
                "graph_store": graph,
            },
        }
        validation = {
            "passed": True,
            "sample": preview,
            "dimension": len(embedding_batch.vectors[0]),
            "embedding_model": embedding_batch.model,
        }
        return self.repository.publish_index_profile(
            profile_id, config, validation, make_default
        )

    def create_index(self, base_id: str, profile_id: str | None = None) -> dict[str, Any]:
        base = self.dataforge.store.get_knowledge_base(base_id)
        profile = (
            self.repository.get_index_profile(profile_id)
            if profile_id
            else self.repository.get_default_index_profile(base["knowledge_type_id"])
        )
        if not profile:
            raise ValidationError("该知识类型尚未发布默认索引方案")
        if profile["validation_status"] != "validated" or not profile["active"]:
            raise ValidationError("索引方案尚未发布或已停用")
        if profile["knowledge_type_id"] != base["knowledge_type_id"]:
            raise ValidationError("索引方案与知识库类型不兼容")
        index = self.repository.create_knowledge_index(base, profile)
        job = self.repository.create_index_job(index["id"])
        return {"knowledge_index": index, "index_job": job}

    def create_auto_index_job(self, base_id: str) -> dict[str, Any] | None:
        base = self.dataforge.store.get_knowledge_base(base_id)
        if not self.repository.get_default_index_profile(base["knowledge_type_id"]):
            return None
        return self.create_index(base_id)

    def execute_job(self, job_id: str) -> dict[str, Any]:
        job = self.repository.get_index_job(job_id)
        if job["status"] != "pending":
            raise ValidationError("只有等待中的索引任务可以执行")
        index = self.repository.get_knowledge_index(job["knowledge_index_id"])
        profile = self.repository.get_index_profile(index["index_profile_id"])
        snapshots = profile["config"].get("_snapshots") or {}
        embedding_config = snapshots.get("embedding_service")
        vector_config = snapshots.get("vector_store")
        if not embedding_config or not vector_config:
            raise ValidationError("索引方案缺少已发布的服务快照")
        embedding = OpenAIEmbeddingClient(embedding_config)
        vector_store = create_vector_store(vector_config)
        graph_store = (
            create_graph_store(snapshots["graph_store"])
            if snapshots.get("graph_store")
            else None
        )
        batch_size = max(1, int(embedding_config.get("batch_size") or 32))
        batches = self.repository.create_batches(job_id, index["expected_count"], batch_size)
        self.repository.update_index_job(job_id, status="running", progress=1)
        self.repository.update_knowledge_index(index["id"], status="indexing", error=None)
        vector_store.ensure_collection(
            index["collection_name"],
            index["dimension"],
            profile["config"].get("filter_fields") or [],
            profile["config"].get("metric_type") or "COSINE",
        )
        existing_hashes = self.repository.get_index_record_hashes(index["id"])
        total_tokens = 0
        embedded_count = 0
        try:
            for position, batch_info in enumerate(batches, start=1):
                current_job = self.repository.get_index_job(job_id)
                if current_job["cancel_requested"] or current_job["status"] == "cancelled":
                    return current_job
                if batch_info["status"] == "completed":
                    continue
                self.repository.update_batch(batch_info["id"], status="running")
                records = self.repository.list_records_for_indexing(
                    index["knowledge_base_id"],
                    limit=batch_info["record_limit"],
                    offset=batch_info["record_offset"],
                )
                prepared = [self._prepare_index_record(index, profile, item) for item in records]
                changed = [
                    item for item in prepared
                    if existing_hashes.get(item["knowledge_record_id"]) != item["content_hash"]
                ]
                if changed:
                    embedded = self._embed(
                        embedding_config,
                        [item["indexed_text"] for item in changed],
                        client=embedding,
                    )
                    total_tokens += embedded.tokens
                    embedded_count += len(changed)
                    vector_rows = []
                    graph_rows = []
                    for item, vector in zip(changed, embedded.vectors):
                        vector_rows.append({**item["vector_row"], "embedding": vector})
                        if graph_store and profile["knowledge_type_id"] == "knowledge_triple":
                            graph_rows.append(item["graph_row"])
                    vector_store.upsert(index["collection_name"], vector_rows)
                    if graph_rows:
                        graph_store.upsert_triples(graph_rows)
                    self.repository.save_index_records(index["id"], changed)
                    existing_hashes.update(
                        {item["knowledge_record_id"]: item["content_hash"] for item in changed}
                    )
                self.repository.update_batch(
                    batch_info["id"],
                    status="completed",
                    record_count=len(records),
                    token_count=total_tokens,
                )
                progress = min(90, int(position / max(1, len(batches)) * 90))
                self.repository.update_index_job(
                    job_id,
                    status="running",
                    progress=progress,
                    stats={
                        "embedded_records": embedded_count,
                        "token_count": total_tokens,
                        "completed_batches": position,
                        "total_batches": len(batches),
                    },
                )

            self.repository.update_knowledge_index(index["id"], status="validating")
            mapped_count = self.repository.count_index_records(index["id"])
            vector_count = vector_store.count(index["collection_name"])
            validation = {
                "passed": mapped_count == index["expected_count"] == vector_count,
                "expected_count": index["expected_count"],
                "mapped_count": mapped_count,
                "vector_count": vector_count,
                "dimension": index["dimension"],
            }
            if not validation["passed"]:
                raise ValidationError(f"索引完整性校验失败：{validation}")
            self.repository.update_knowledge_index(
                index["id"],
                status="available",
                record_count=mapped_count,
                validation=validation,
                is_current=True,
            )
            return self.repository.update_index_job(
                job_id,
                status="completed",
                progress=100,
                stats={
                    "embedded_records": embedded_count,
                    "token_count": total_tokens,
                    "completed_batches": len(batches),
                    "total_batches": len(batches),
                    "validation": validation,
                },
            )
        except Exception as exc:
            for batch in self.repository.list_batches(job_id):
                if batch["status"] == "running":
                    self.repository.update_batch(batch["id"], status="failed", error=str(exc))
            self.repository.update_knowledge_index(index["id"], status="failed", error=str(exc))
            return self.repository.update_index_job(
                job_id, status="failed", error=str(exc), stats={"token_count": total_tokens}
            )

    def retry_job(self, job_id: str) -> dict[str, Any]:
        prior = self.repository.get_index_job(job_id)
        if prior["status"] not in {"failed", "cancelled"}:
            raise ValidationError("只有失败或取消的索引任务可以重试")
        self.repository.update_knowledge_index(
            prior["knowledge_index_id"], status="pending", error=None
        )
        return self.repository.create_index_job(
            prior["knowledge_index_id"],
            retry_of_job_id=job_id,
            attempt_no=int(prior["attempt_no"]) + 1,
        )

    def publish_retrieval_profile(
        self, profile_id: str, *, base_id: str | None = None, make_default: bool = True
    ) -> dict[str, Any]:
        profile = self.repository.get_retrieval_profile(profile_id)
        index_profile = self.repository.get_index_profile(profile["index_profile_id"])
        if index_profile["validation_status"] != "validated":
            raise ValidationError("检索方案依赖的索引方案尚未发布")
        config = profile["config"]
        available = set(index_profile["config"].get("stored_fields") or []) | {
            "indexed_text", "score", "source_locator", "source_version_id",
            "knowledge_record_id", "knowledge_base_id", "vector_score", "rerank_score",
        }
        unknown = set(config.get("return_fields") or []) - available
        if unknown:
            raise ValidationError(f"返回字段尚未由索引方案保存：{'、'.join(sorted(unknown))}")
        context_fields = set(referenced_fields(config.get("context_template") or ""))
        unknown_context = context_fields - available
        if unknown_context:
            raise ValidationError(
                f"上下文模板字段尚未由索引方案保存：{'、'.join(sorted(unknown_context))}"
            )
        if base_id:
            self.repository.get_available_index(base_id, index_profile["id"])
        reranker = None
        if config.get("reranker_enabled"):
            service_id = str(config.get("reranker_service_id") or "").strip()
            if not service_id:
                raise ValidationError("启用 Reranker 后必须选择模型服务")
            reranker = self.test_reranker_service(service_id)
            if not reranker["active"] or reranker["status"] != "ready":
                raise ValidationError(
                    f"Reranker 服务未就绪：{reranker.get('last_test', {}).get('error', '连接失败')}"
                )
            candidate_count = max(1, min(200, int(config.get("rerank_candidate_count") or 20)))
            if candidate_count < max(1, int(config.get("top_k") or 5)):
                raise ValidationError("Reranker 候选数不能小于 Top K 上限")
        validation = {
            "passed": True,
            "return_fields": config.get("return_fields") or [],
            "context_template_fields": sorted(context_fields),
            "reranker": reranker,
        }
        return self.repository.publish_retrieval_profile(
            profile_id, validation, make_default
        )

    def query(
        self,
        retrieval_profile_id: str,
        knowledge_base_id: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
        knowledge_index_id: str | None = None,
    ) -> dict[str, Any]:
        if not query.strip():
            raise ValidationError("检索问题不能为空")
        retrieval = self.repository.get_retrieval_profile(retrieval_profile_id)
        if retrieval["validation_status"] != "validated" or not retrieval["active"]:
            raise ValidationError("检索方案尚未发布或已停用")
        index_profile = self.repository.get_index_profile(retrieval["index_profile_id"])
        index = (
            self.repository.get_knowledge_index(knowledge_index_id)
            if knowledge_index_id
            else self.repository.get_available_index(knowledge_base_id, index_profile["id"])
        )
        if index["knowledge_base_id"] != knowledge_base_id:
            raise ValidationError("指定索引不属于目标知识库")
        if index["index_profile_id"] != index_profile["id"] or index["status"] != "available":
            raise ValidationError("指定索引与检索方案不兼容或当前不可用")
        snapshots = index_profile["config"]["_snapshots"]
        vector = self._embed(snapshots["embedding_service"], [query.strip()])
        store = create_vector_store(snapshots["vector_store"])
        retrieval_config = retrieval["config"]
        maximum = max(1, min(100, int(retrieval_config.get("top_k") or 5)))
        limit = min(maximum, max(1, int(top_k or maximum)))
        reranker_enabled = bool(retrieval_config.get("reranker_enabled"))
        candidate_limit = (
            max(limit, min(200, int(retrieval_config.get("rerank_candidate_count") or 20)))
            if reranker_enabled else limit
        )
        expression = self._build_filter_expression(index_profile, filters or {})
        hits = store.search(
            index["collection_name"], vector.vectors[0], limit=candidate_limit,
            filter_expression=expression, output_fields=["*"],
            metric=index_profile["config"].get("metric_type") or "COSINE",
        )
        threshold = float(retrieval_config.get("score_threshold") or 0)
        hits = [hit for hit in hits if hit["score"] >= threshold]
        hits, reranker_audit = self._rerank_hits(
            retrieval, query.strip(), hits, limit
        )
        results = []
        contexts = []
        for hit in hits:
            lineage = self.repository.get_index_record_lineage(index["id"], hit["id"])
            factual = lineage["data"]
            source = {
                "source_version_id": factual.get("source_version_id") or hit.get("source_version_id"),
                "source_name": lineage["source_name"],
                "original_filename": lineage["original_filename"],
                "source_locator": lineage["source_locator"],
            }
            available = {
                **factual,
                **((hit.get("metadata") or {}).get("stored") or {}),
                "indexed_text": hit.get("indexed_text"),
                "score": hit["score"],
                "vector_score": hit["vector_score"],
                "rerank_score": hit.get("rerank_score"),
                "source_locator": lineage["source_locator"],
                "source_version_id": hit.get("source_version_id"),
                "knowledge_record_id": lineage["knowledge_record_id"],
                "knowledge_base_id": knowledge_base_id,
            }
            fields = {
                field: available.get(field)
                for field in retrieval_config.get("return_fields") or []
            }
            context = render_template(
                retrieval_config.get("context_template") or "{{ indexed_text }}",
                available,
                missing_policy="empty",
            )
            result = {
                "index_record_id": hit["id"],
                "knowledge_record_id": lineage["knowledge_record_id"],
                "score": hit["score"],
                "vector_score": hit["vector_score"],
                "rerank_score": hit.get("rerank_score"),
                "fields": fields,
                "source": source,
                "context": context,
            }
            results.append(result)
            contexts.append(context)
        return {
            "query": query,
            "retrieval_profile": {"id": retrieval["id"], "name": retrieval["name"], "version": retrieval["version"]},
            "knowledge_index": {"id": index["id"], "version": index["version"]},
            "reranker": reranker_audit,
            "results": results,
            "context": str(retrieval_config.get("context_separator") or "\n\n---\n\n").join(contexts),
        }

    def _rerank_hits(
        self,
        retrieval: dict[str, Any],
        query: str,
        hits: list[dict[str, Any]],
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not retrieval["config"].get("reranker_enabled"):
            return [
                {**hit, "vector_score": hit["score"], "rerank_score": None}
                for hit in hits[:limit]
            ], {"enabled": False}
        snapshot = retrieval.get("validation", {}).get("reranker")
        if not snapshot:
            raise ValidationError("已发布检索方案缺少 Reranker 服务快照")
        documents = [str(hit.get("indexed_text") or "") for hit in hits]
        ranked = OpenAIRerankerClient(snapshot).rerank(query, documents, top_n=limit)
        reordered = []
        for item in ranked["results"]:
            original = hits[item["index"]]
            reordered.append(
                {
                    **original,
                    "score": item["relevance_score"],
                    "vector_score": original["score"],
                    "rerank_score": item["relevance_score"],
                }
            )
        return reordered, {
            "enabled": True,
            "service_id": snapshot["id"],
            "model": ranked["model"],
            "candidate_count": len(hits),
            "returned_count": len(reordered),
            "latency_ms": ranked["latency_ms"],
            "usage": ranked["usage"],
        }

    def _sample_record(
        self, knowledge_type: dict[str, Any], base_id: str | None
    ) -> dict[str, Any]:
        if base_id:
            base = self.dataforge.store.get_knowledge_base(base_id)
            if base["knowledge_type_id"] != knowledge_type["id"]:
                raise ValidationError("样本知识库与索引方案类型不兼容")
            records = self.dataforge.store.list_knowledge_records(base_id, limit=1)
            if records:
                return records[0]
        sample: dict[str, Any] = {}
        for name, kind in knowledge_type["schema"].get("properties", {}).items():
            sample[name] = {
                "string": f"示例{name}",
                "integer": 1,
                "array": [{"role": "user", "content": f"示例{name}"}],
                "object": {"value": f"示例{name}"},
            }.get(kind, f"示例{name}")
        return {"data": sample, "source_locator": {"page_number": 1}}

    def _validate_profile_fields(self, profile: dict[str, Any]) -> None:
        knowledge_type = self.dataforge.store.get_knowledge_type(profile["knowledge_type_id"])
        fields = set(knowledge_type["schema"].get("properties") or {}) | {"source_locator"}
        config = profile["config"]
        used = set(referenced_fields(config.get("embedding_template") or ""))
        used.update(config.get("stored_fields") or [])
        used.update(config.get("metadata_fields") or [])
        for mapping in config.get("filter_fields") or []:
            used.add(str(mapping.get("source") or ""))
            validate_field_name(str(mapping.get("target") or mapping.get("source") or ""))
        unknown = {field.split(".", 1)[0] for field in used if field} - fields
        if unknown:
            raise ValidationError(f"索引方案引用了不存在的知识字段：{'、'.join(sorted(unknown))}")
        if not referenced_fields(config.get("embedding_template") or ""):
            raise ValidationError("向量化模板至少需要引用一个知识字段")

    def _prepare_index_record(
        self, index: dict[str, Any], profile: dict[str, Any], item: dict[str, Any]
    ) -> dict[str, Any]:
        indexed_text, metadata, filters = build_projection(
            item["data"], item["source_locator"], profile["config"]
        )
        content_hash = hashlib.sha256(
            json.dumps(
                {"text": indexed_text, "metadata": metadata, "filters": filters},
                ensure_ascii=False, sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        record_key = f"{index['id']}:{item['id']}"
        external_id = f"irec_{hashlib.sha256(record_key.encode()).hexdigest()[:32]}"
        vector_row = {
            "id": external_id,
            "knowledge_record_id": item["id"],
            "knowledge_base_id": index["knowledge_base_id"],
            "knowledge_index_id": index["id"],
            "source_version_id": item["source_version_id"],
            "content_hash": content_hash,
            "indexed_text": indexed_text,
            "metadata": metadata,
            **filters,
        }
        return {
            "knowledge_record_id": item["id"],
            "external_id": external_id,
            "content_hash": content_hash,
            "indexed_text": indexed_text,
            "metadata": metadata,
            "vector_row": vector_row,
            "graph_row": {
                "index_record_id": external_id,
                "knowledge_record_id": item["id"],
                "knowledge_index_id": index["id"],
                "subject": item["data"].get("subject"),
                "predicate": item["data"].get("predicate"),
                "object": item["data"].get("object"),
            },
        }

    def _build_filter_expression(
        self, profile: dict[str, Any], filters: dict[str, Any]
    ) -> str:
        allowed = {
            str(item.get("target") or item.get("source")): item
            for item in profile["config"].get("filter_fields") or []
        }
        clauses = []
        for field, value in filters.items():
            if field not in allowed:
                raise ValidationError(f"检索方案不允许过滤字段：{field}")
            validate_field_name(field)
            literal = json.dumps(value, ensure_ascii=False)
            clauses.append(f"{field} == {literal}")
        return " and ".join(clauses)

    def _embed(
        self,
        config: dict[str, Any],
        texts: list[str],
        *,
        client: OpenAIEmbeddingClient | None = None,
    ):
        """Apply the configured process-local concurrency ceiling to model calls."""
        limit = max(1, int(config.get("concurrency") or 1))
        key = (str(config.get("id") or config.get("model") or "embedding"), limit)
        with _EMBEDDING_LIMITS_LOCK:
            semaphore = _EMBEDDING_LIMITS.setdefault(key, BoundedSemaphore(limit))
        with semaphore:
            return (client or OpenAIEmbeddingClient(config)).embed(texts)
