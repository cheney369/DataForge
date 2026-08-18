from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from ..errors import ValidationError
from .repository import DeliveryRepository

if TYPE_CHECKING:
    from ..application import DataForge


BINDING_KEY = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class DeliveryService:
    def __init__(self, dataforge: DataForge):
        self.dataforge = dataforge
        self.repository = DeliveryRepository(dataforge.store)
        self.repository.initialize()

    def create_collection(self, name: str, description: str, knowledge_type_id: str) -> dict[str, Any]:
        if not name.strip():
            raise ValidationError("请填写知识集合名称")
        knowledge_type = self.dataforge.store.get_knowledge_type(knowledge_type_id)
        if not knowledge_type["active"]:
            raise ValidationError("只能基于当前生效的知识类型创建集合")
        return self.repository.create_collection(name, description, knowledge_type_id)

    def create_version(
        self,
        collection_id: str,
        retrieval_profile_id: str,
        knowledge_base_ids: list[str],
    ) -> dict[str, Any]:
        collection = self.repository.get_collection(collection_id)
        retrieval = self.dataforge.indexing.repository.get_retrieval_profile(retrieval_profile_id)
        if retrieval["validation_status"] != "validated" or not retrieval["active"]:
            raise ValidationError("只能使用已发布的检索方案创建集合版本")
        index_profile = self.dataforge.indexing.repository.get_index_profile(
            retrieval["index_profile_id"]
        )
        if index_profile["knowledge_type_id"] != collection["knowledge_type_id"]:
            raise ValidationError("检索方案与知识集合类型不兼容")
        unique_ids = list(dict.fromkeys(knowledge_base_ids))
        if not unique_ids:
            raise ValidationError("集合版本至少需要一个知识库成员")
        members: list[dict[str, str]] = []
        for base_id in unique_ids:
            base = self.dataforge.store.get_knowledge_base(base_id)
            if base["knowledge_type_id"] != collection["knowledge_type_id"]:
                raise ValidationError(f"知识库“{base['name']}”与集合类型不兼容")
            index = self.dataforge.indexing.repository.get_available_index(
                base_id, index_profile["id"]
            )
            members.append({
                "knowledge_base_id": base_id,
                "knowledge_index_id": index["id"],
            })
        embedding = (index_profile["config"].get("_snapshots") or {}).get("embedding_service") or {}
        vector_store = (index_profile["config"].get("_snapshots") or {}).get("vector_store") or {}
        validation = {
            "passed": True,
            "member_count": len(members),
            "knowledge_type_id": collection["knowledge_type_id"],
            "retrieval_profile_id": retrieval["id"],
            "index_profile_id": index_profile["id"],
            "compatibility": {
                "embedding_model": embedding.get("model"),
                "dimension": embedding.get("dimension"),
                "vector_store_kind": vector_store.get("kind"),
                "metric_type": index_profile["config"].get("metric_type") or "COSINE",
            },
        }
        return self.repository.create_version(
            collection_id, retrieval["id"], index_profile["id"], members, validation
        )

    def publish_version(self, version_id: str, make_current: bool = True) -> dict[str, Any]:
        version = self.repository.get_version(version_id)
        if version["status"] != "draft":
            raise ValidationError("只有草稿集合版本可以发布")
        invalid = []
        for member in version["members"]:
            index = self.dataforge.indexing.repository.get_knowledge_index(
                member["knowledge_index_id"]
            )
            if index["status"] != "available":
                invalid.append(member["knowledge_base_name"])
            if index["index_profile_id"] != version["index_profile_id"]:
                invalid.append(member["knowledge_base_name"])
        if invalid:
            raise ValidationError(f"集合成员索引已不可用：{'、'.join(sorted(set(invalid)))}")
        validation = {
            **version["validation"],
            "passed": True,
            "published_member_count": len(version["members"]),
        }
        return self.repository.publish_version(version_id, validation, make_current)

    def create_binding(self, payload: dict[str, Any]) -> dict[str, Any]:
        binding_key = str(payload.get("binding_key") or "").strip()
        if not BINDING_KEY.fullmatch(binding_key):
            raise ValidationError("应用标识需为 3-64 位小写字母、数字或连字符，且以字母开头")
        if not str(payload.get("name") or "").strip():
            raise ValidationError("请填写应用绑定名称")
        self._validate_binding_target(
            payload["collection_id"], payload.get("collection_version_id"),
            bool(payload.get("follow_latest", True)),
        )
        return self.repository.save_binding(payload)

    def repoint_binding(
        self,
        binding_id: str,
        *,
        collection_version_id: str | None,
        follow_latest: bool,
    ) -> dict[str, Any]:
        binding = self.repository.get_binding(binding_id)
        self._validate_binding_target(
            binding["collection_id"], collection_version_id, follow_latest
        )
        return self.repository.save_binding({
            "id": binding["id"],
            "binding_key": binding["binding_key"],
            "name": binding["name"],
            "description": binding["description"],
            "collection_id": binding["collection_id"],
            "collection_version_id": None if follow_latest else collection_version_id,
            "follow_latest": follow_latest,
        })

    def resolve_binding_version(self, binding: dict[str, Any]) -> dict[str, Any]:
        if not binding["active"]:
            raise ValidationError("应用绑定已停用")
        if binding["follow_latest"]:
            return self.repository.get_current_version(binding["collection_id"])
        if not binding.get("collection_version_id"):
            raise ValidationError("应用绑定未指定集合版本")
        version = self.repository.get_version(binding["collection_version_id"])
        if version["status"] != "published":
            raise ValidationError("应用绑定指向的集合版本尚未发布")
        return version

    def query_binding(
        self,
        binding_key: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        binding = self.repository.get_binding(binding_key)
        version = self.resolve_binding_version(binding)
        result = self.query_version(version["id"], query, filters=filters, top_k=top_k)
        return {
            **result,
            "application_binding": {
                "id": binding["id"],
                "key": binding["binding_key"],
                "name": binding["name"],
                "follow_latest": binding["follow_latest"],
            },
        }

    def query_version(
        self,
        version_id: str,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> dict[str, Any]:
        version = self.repository.get_version(version_id)
        if version["status"] != "published":
            raise ValidationError("只有已发布的集合版本可以检索")
        retrieval = self.dataforge.indexing.repository.get_retrieval_profile(
            version["retrieval_profile_id"]
        )
        configured_limit = max(1, min(100, int(retrieval["config"].get("top_k") or 5)))
        limit = min(configured_limit, max(1, int(top_k or configured_limit)))
        candidates = []
        reranker_executions = []
        for member in version["members"]:
            response = self.dataforge.indexing.query(
                version["retrieval_profile_id"], member["knowledge_base_id"], query,
                filters=filters or {}, top_k=limit,
                knowledge_index_id=member["knowledge_index_id"],
            )
            if response.get("reranker", {}).get("enabled"):
                reranker_executions.append({
                    **response["reranker"],
                    "knowledge_base_id": member["knowledge_base_id"],
                })
            for item in response["results"]:
                candidates.append({
                    **item,
                    "collection_member": {
                        "knowledge_base_id": member["knowledge_base_id"],
                        "knowledge_base_name": member["knowledge_base_name"],
                        "knowledge_index_id": member["knowledge_index_id"],
                    },
                })
        results = sorted(candidates, key=lambda item: item["score"], reverse=True)[:limit]
        separator = str(retrieval["config"].get("context_separator") or "\n\n---\n\n")
        return {
            "query": query,
            "collection": {
                "id": version["collection_id"],
                "name": version["collection_name"],
                "version_id": version["id"],
                "version": version["version"],
            },
            "retrieval_profile": {
                "id": retrieval["id"], "name": retrieval["name"],
                "version": retrieval["version"],
            },
            "reranker": {
                "enabled": bool(reranker_executions),
                "executions": reranker_executions,
            },
            "results": results,
            "context": separator.join(item["context"] for item in results),
        }

    def _validate_binding_target(
        self,
        collection_id: str,
        collection_version_id: str | None,
        follow_latest: bool,
    ) -> None:
        self.repository.get_collection(collection_id)
        if follow_latest:
            self.repository.get_current_version(collection_id)
            return
        if not collection_version_id:
            raise ValidationError("固定版本绑定必须选择集合版本")
        version = self.repository.get_version(collection_version_id)
        if version["collection_id"] != collection_id:
            raise ValidationError("集合版本不属于所选知识集合")
        if version["status"] != "published":
            raise ValidationError("应用只能绑定已发布的集合版本")
