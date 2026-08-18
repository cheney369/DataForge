from __future__ import annotations

import json
import math
import os
import re
from threading import Lock
from typing import Any, Protocol

from ..errors import ValidationError


FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


class VectorStore(Protocol):
    def test(self) -> dict[str, Any]: ...
    def ensure_collection(
        self, name: str, dimension: int, filter_fields: list[dict[str, Any]], metric: str
    ) -> None: ...
    def upsert(self, name: str, rows: list[dict[str, Any]]) -> None: ...
    def count(self, name: str) -> int: ...
    def search(
        self,
        name: str,
        vector: list[float],
        *,
        limit: int,
        filter_expression: str = "",
        output_fields: list[str] | None = None,
        metric: str = "COSINE",
    ) -> list[dict[str, Any]]: ...


class MilvusVectorStore:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise ValidationError(
                "尚未安装 Milvus 客户端，请使用 indexing 可选依赖启动 DataForge"
            ) from exc
        token_ref = str(config.get("token_env") or "").strip()
        token = os.getenv(token_ref) if token_ref else None
        kwargs: dict[str, Any] = {"uri": config["uri"]}
        if token:
            kwargs["token"] = token
        if config.get("database_name"):
            kwargs["db_name"] = config["database_name"]
        self.client = MilvusClient(**kwargs)

    def test(self) -> dict[str, Any]:
        collections = self.client.list_collections()
        return {"status": "ready", "collection_count": len(collections)}

    def ensure_collection(
        self,
        name: str,
        dimension: int,
        filter_fields: list[dict[str, Any]],
        metric: str,
    ) -> None:
        if self.client.has_collection(name):
            return
        from pymilvus import DataType

        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=128)
        for field in (
            "knowledge_record_id",
            "knowledge_base_id",
            "knowledge_index_id",
            "source_version_id",
            "content_hash",
        ):
            schema.add_field(field, DataType.VARCHAR, max_length=128)
        schema.add_field("indexed_text", DataType.VARCHAR, max_length=65535)
        schema.add_field("metadata", DataType.JSON, nullable=True)
        for mapping in filter_fields:
            name_ = str(mapping.get("target") or mapping.get("source") or "").strip()
            validate_field_name(name_)
            if name_ in {field.name for field in schema.fields}:
                continue
            kind = str(mapping.get("type") or "string")
            data_type = {
                "integer": DataType.INT64,
                "int": DataType.INT64,
                "number": DataType.DOUBLE,
                "float": DataType.DOUBLE,
                "boolean": DataType.BOOL,
                "bool": DataType.BOOL,
            }.get(kind, DataType.VARCHAR)
            kwargs = {"max_length": 2048} if data_type == DataType.VARCHAR else {}
            schema.add_field(name_, data_type, nullable=True, **kwargs)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_name="embedding_index",
            index_type="AUTOINDEX",
            metric_type=metric,
        )
        self.client.create_collection(
            collection_name=name,
            schema=schema,
            index_params=index_params,
        )

    def upsert(self, name: str, rows: list[dict[str, Any]]) -> None:
        if rows:
            self.client.upsert(collection_name=name, data=rows)

    def count(self, name: str) -> int:
        # Milvus writes are eventually visible by default. Flush before the
        # publication integrity check so a just-finished batch cannot be
        # mistaken for missing vectors.
        self.client.flush(collection_name=name)
        result = self.client.query(
            collection_name=name,
            filter="",
            output_fields=["count(*)"],
        )
        return int((result[0] if result else {}).get("count(*)") or 0)

    def search(
        self,
        name: str,
        vector: list[float],
        *,
        limit: int,
        filter_expression: str = "",
        output_fields: list[str] | None = None,
        metric: str = "COSINE",
    ) -> list[dict[str, Any]]:
        result = self.client.search(
            collection_name=name,
            data=[vector],
            anns_field="embedding",
            limit=limit,
            filter=filter_expression,
            output_fields=output_fields or ["*"],
            search_params={"metric_type": metric, "params": {}},
        )
        hits: list[dict[str, Any]] = []
        for hit in result[0] if result else []:
            entity = dict(hit.get("entity") or {})
            distance = float(hit.get("distance") or hit.get("score") or 0)
            hits.append(
                {
                    **entity,
                    "id": hit.get("id") or entity.get("id"),
                    # Keep the public threshold contract "higher is better".
                    "score": 1.0 / (1.0 + max(0.0, distance)) if metric == "L2" else distance,
                }
            )
        return hits


class MemoryVectorStore:
    """Deterministic test adapter with the same projection contract as Milvus."""

    _collections: dict[str, dict[str, dict[str, Any]]] = {}
    _lock = Lock()

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def test(self) -> dict[str, Any]:
        return {"status": "ready", "collection_count": len(self._collections)}

    def ensure_collection(
        self,
        name: str,
        dimension: int,
        filter_fields: list[dict[str, Any]],
        metric: str,
    ) -> None:
        with self._lock:
            self._collections.setdefault(name, {})

    def upsert(self, name: str, rows: list[dict[str, Any]]) -> None:
        with self._lock:
            target = self._collections.setdefault(name, {})
            for row in rows:
                target[row["id"]] = dict(row)

    def count(self, name: str) -> int:
        return len(self._collections.get(name, {}))

    def search(
        self,
        name: str,
        vector: list[float],
        *,
        limit: int,
        filter_expression: str = "",
        output_fields: list[str] | None = None,
        metric: str = "COSINE",
    ) -> list[dict[str, Any]]:
        rows = [
            row for row in self._collections.get(name, {}).values()
            if matches_filter_expression(row, filter_expression)
        ]
        scored = [{**row, "score": similarity(vector, row["embedding"], metric)} for row in rows]
        return sorted(scored, key=lambda row: row["score"], reverse=True)[:limit]


def create_vector_store(config: dict[str, Any]) -> VectorStore:
    if config.get("kind") == "memory":
        return MemoryVectorStore(config)
    if config.get("kind") == "milvus":
        return MilvusVectorStore(config)
    raise ValidationError(f"不支持的向量存储：{config.get('kind')}")


def validate_field_name(name: str) -> None:
    if not FIELD_NAME.fullmatch(name):
        raise ValidationError(f"Milvus 字段名不合法：{name}")


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def similarity(left: list[float], right: list[float], metric: str) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    if metric == "IP":
        return sum(a * b for a, b in zip(left, right))
    if metric == "L2":
        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))
        return 1.0 / (1.0 + distance)
    return cosine(left, right)


def matches_filter_expression(row: dict[str, Any], expression: str) -> bool:
    """Evaluate the restricted equality grammar emitted by DataForge in tests."""
    if not expression:
        return True
    for clause in expression.split(" and "):
        field, separator, raw = clause.partition(" == ")
        if not separator:
            return False
        try:
            expected = json.loads(raw)
        except ValueError:
            return False
        if row.get(field.strip()) != expected:
            return False
    return True
