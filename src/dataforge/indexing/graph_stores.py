from __future__ import annotations

import os
from typing import Any, Protocol

from ..errors import ValidationError


class GraphStore(Protocol):
    def test(self) -> dict[str, Any]: ...
    def upsert_triples(self, rows: list[dict[str, Any]]) -> int: ...


class Neo4jGraphStore:
    def __init__(self, config: dict[str, Any]):
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise ValidationError(
                "尚未安装 Neo4j 客户端，请使用 indexing 可选依赖启动 DataForge"
            ) from exc
        username_ref = str(config.get("username_env") or "").strip()
        password_ref = str(config.get("password_env") or "").strip()
        username = os.getenv(username_ref, "neo4j") if username_ref else "neo4j"
        password = os.getenv(password_ref, "") if password_ref else ""
        auth = (username, password) if password else None
        self.driver = GraphDatabase.driver(config["uri"], auth=auth)
        self.database = config.get("graph_space") or "neo4j"

    def test(self) -> dict[str, Any]:
        self.driver.verify_connectivity()
        return {"status": "ready", "database": self.database}

    def upsert_triples(self, rows: list[dict[str, Any]]) -> int:
        query = """
        UNWIND $rows AS row
        MERGE (subject:Entity {name: row.subject})
        MERGE (object:Entity {name: row.object})
        MERGE (fact:Fact {index_record_id: row.index_record_id})
        SET fact.predicate = row.predicate,
            fact.knowledge_record_id = row.knowledge_record_id,
            fact.knowledge_index_id = row.knowledge_index_id
        MERGE (subject)-[:SUBJECT_OF]->(fact)
        MERGE (fact)-[:OBJECT_OF]->(object)
        """
        with self.driver.session(database=self.database) as session:
            session.run(query, rows=rows).consume()
        return len(rows)


class MemoryGraphStore:
    _facts: dict[str, dict[str, Any]] = {}

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def test(self) -> dict[str, Any]:
        return {"status": "ready", "fact_count": len(self._facts)}

    def upsert_triples(self, rows: list[dict[str, Any]]) -> int:
        for row in rows:
            self._facts[row["index_record_id"]] = dict(row)
        return len(rows)


def create_graph_store(config: dict[str, Any]) -> GraphStore:
    if config.get("kind") == "memory":
        return MemoryGraphStore(config)
    if config.get("kind") == "neo4j":
        return Neo4jGraphStore(config)
    raise ValidationError(f"不支持的图存储：{config.get('kind')}")
