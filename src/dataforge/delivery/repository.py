from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..database import MetadataStore, new_id, utc_now
from ..errors import NotFoundError, ValidationError


DELIVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_collections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    knowledge_type_id TEXT NOT NULL REFERENCES knowledge_types(id),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_versions (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES knowledge_collections(id),
    version INTEGER NOT NULL,
    retrieval_profile_id TEXT NOT NULL REFERENCES retrieval_profiles(id),
    index_profile_id TEXT NOT NULL REFERENCES index_profiles(id),
    status TEXT NOT NULL DEFAULT 'draft',
    validation_json TEXT NOT NULL DEFAULT '{}',
    is_current INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(collection_id, version)
);

CREATE TABLE IF NOT EXISTS collection_members (
    id TEXT PRIMARY KEY,
    collection_version_id TEXT NOT NULL REFERENCES collection_versions(id),
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id),
    knowledge_index_id TEXT NOT NULL REFERENCES knowledge_indexes(id),
    ordinal INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(collection_version_id, knowledge_base_id)
);

CREATE TABLE IF NOT EXISTS application_bindings (
    id TEXT PRIMARY KEY,
    binding_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    collection_id TEXT NOT NULL REFERENCES knowledge_collections(id),
    collection_version_id TEXT REFERENCES collection_versions(id),
    follow_latest INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_binding_events (
    id TEXT PRIMARY KEY,
    application_binding_id TEXT NOT NULL REFERENCES application_bindings(id),
    event_type TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_collection_versions_collection
ON collection_versions(collection_id, version);
CREATE INDEX IF NOT EXISTS idx_collection_members_version
ON collection_members(collection_version_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_application_bindings_collection
ON application_bindings(collection_id, active);
CREATE INDEX IF NOT EXISTS idx_application_binding_events_binding
ON application_binding_events(application_binding_id, created_at);
"""


def _decode(row: Any) -> dict[str, Any]:
    result = dict(row)
    if "validation_json" in result:
        result["validation"] = json.loads(result.pop("validation_json") or "{}")
    if "detail_json" in result:
        result["detail"] = json.loads(result.pop("detail_json") or "{}")
    for field in ("active", "is_current", "follow_latest"):
        if field in result:
            result[field] = bool(result[field])
    return result


class DeliveryRepository:
    def __init__(self, store: MetadataStore):
        self.store = store

    def initialize(self) -> None:
        with self.store.connect() as connection:
            connection.executescript(DELIVERY_SCHEMA)

    def create_collection(self, name: str, description: str, knowledge_type_id: str) -> dict[str, Any]:
        self.store.get_knowledge_type(knowledge_type_id)
        collection_id = new_id("kcol")
        now = utc_now()
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO knowledge_collections
                   (id,name,description,knowledge_type_id,active,created_at,updated_at)
                   VALUES (?,?,?,?,1,?,?)""",
                (collection_id, name.strip(), description.strip(), knowledge_type_id, now, now),
            )
        return self.get_collection(collection_id)

    def get_collection(self, collection_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT c.*,k.name AS knowledge_type_name
                   FROM knowledge_collections c JOIN knowledge_types k ON k.id=c.knowledge_type_id
                   WHERE c.id=?""",
                (collection_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Knowledge collection not found: {collection_id}")
        return _decode(row)

    def list_collections(self) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT c.*,k.name AS knowledge_type_name,
                          COUNT(DISTINCT v.id) AS version_count,
                          MAX(CASE WHEN v.is_current=1 THEN v.id END) AS current_version_id,
                          MAX(CASE WHEN v.is_current=1 THEN v.version END) AS current_version,
                          MAX(CASE WHEN v.is_current=1 THEN v.status END) AS current_status
                   FROM knowledge_collections c JOIN knowledge_types k ON k.id=c.knowledge_type_id
                   LEFT JOIN collection_versions v ON v.collection_id=c.id
                   GROUP BY c.id ORDER BY c.created_at DESC"""
            ).fetchall()
        return [_decode(row) for row in rows]

    def create_version(
        self,
        collection_id: str,
        retrieval_profile_id: str,
        index_profile_id: str,
        members: list[dict[str, str]],
        validation: dict[str, Any],
    ) -> dict[str, Any]:
        collection = self.get_collection(collection_id)
        if not collection["active"]:
            raise ValidationError("知识集合已停用")
        version_id = new_id("kcolv")
        now = utc_now()
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            version = int(connection.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM collection_versions WHERE collection_id=?",
                (collection_id,),
            ).fetchone()[0])
            connection.execute(
                """INSERT INTO collection_versions
                   (id,collection_id,version,retrieval_profile_id,index_profile_id,status,
                    validation_json,is_current,created_at)
                   VALUES (?,?,?,?,?,'draft',?,0,?)""",
                (
                    version_id, collection_id, version, retrieval_profile_id, index_profile_id,
                    json.dumps(validation, ensure_ascii=False, sort_keys=True), now,
                ),
            )
            connection.executemany(
                """INSERT INTO collection_members
                   (id,collection_version_id,knowledge_base_id,knowledge_index_id,ordinal,created_at)
                   VALUES (?,?,?,?,?,?)""",
                [
                    (
                        new_id("kcolm"), version_id, member["knowledge_base_id"],
                        member["knowledge_index_id"], position, now,
                    )
                    for position, member in enumerate(members, start=1)
                ],
            )
        return self.get_version(version_id)

    def get_version(self, version_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT v.*,c.name AS collection_name,c.knowledge_type_id,
                          k.name AS knowledge_type_name,r.name AS retrieval_profile_name,
                          p.name AS index_profile_name
                   FROM collection_versions v
                   JOIN knowledge_collections c ON c.id=v.collection_id
                   JOIN knowledge_types k ON k.id=c.knowledge_type_id
                   JOIN retrieval_profiles r ON r.id=v.retrieval_profile_id
                   JOIN index_profiles p ON p.id=v.index_profile_id WHERE v.id=?""",
                (version_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Collection version not found: {version_id}")
        result = _decode(row)
        result["members"] = self.list_members(version_id)
        return result

    def list_versions(self, collection_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE v.collection_id=?" if collection_id else ""
        params = (collection_id,) if collection_id else ()
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT v.*,c.name AS collection_name,c.knowledge_type_id,
                           k.name AS knowledge_type_name,r.name AS retrieval_profile_name,
                           p.name AS index_profile_name,COUNT(m.id) AS member_count
                    FROM collection_versions v JOIN knowledge_collections c ON c.id=v.collection_id
                    JOIN knowledge_types k ON k.id=c.knowledge_type_id
                    JOIN retrieval_profiles r ON r.id=v.retrieval_profile_id
                    JOIN index_profiles p ON p.id=v.index_profile_id
                    LEFT JOIN collection_members m ON m.collection_version_id=v.id
                    {where} GROUP BY v.id ORDER BY v.created_at DESC""",
                params,
            ).fetchall()
        return [_decode(row) for row in rows]

    def list_members(self, version_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT m.*,b.name AS knowledge_base_name,b.record_count,
                          i.version AS knowledge_index_version,i.status AS index_status,
                          i.collection_name
                   FROM collection_members m JOIN knowledge_bases b ON b.id=m.knowledge_base_id
                   JOIN knowledge_indexes i ON i.id=m.knowledge_index_id
                   WHERE m.collection_version_id=? ORDER BY m.ordinal""",
                (version_id,),
            ).fetchall()
        return [_decode(row) for row in rows]

    def publish_version(self, version_id: str, validation: dict[str, Any], make_current: bool) -> dict[str, Any]:
        version = self.get_version(version_id)
        if version["status"] != "draft":
            raise ValidationError("只有草稿集合版本可以发布")
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if make_current:
                connection.execute(
                    "UPDATE collection_versions SET is_current=0 WHERE collection_id=?",
                    (version["collection_id"],),
                )
            connection.execute(
                """UPDATE collection_versions SET status='published',validation_json=?,
                   is_current=?,published_at=? WHERE id=?""",
                (
                    json.dumps(validation, ensure_ascii=False, sort_keys=True),
                    int(make_current), utc_now(), version_id,
                ),
            )
        return self.get_version(version_id)

    def get_current_version(self, collection_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT id FROM collection_versions WHERE collection_id=?
                   AND status='published' AND is_current=1""",
                (collection_id,),
            ).fetchone()
        if not row:
            raise ValidationError("知识集合尚无当前发布版本")
        return self.get_version(row["id"])

    def save_binding(self, payload: dict[str, Any]) -> dict[str, Any]:
        binding_id = payload.get("id") or new_id("appb")
        now = utc_now()
        try:
            with self.store.connect() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM application_bindings WHERE id=?", (binding_id,)
                ).fetchone()
                values = (
                    payload["binding_key"].strip(), payload["name"].strip(),
                    (payload.get("description") or "").strip(), payload["collection_id"],
                    payload.get("collection_version_id"), int(payload.get("follow_latest", True)), now,
                )
                if exists:
                    connection.execute(
                        """UPDATE application_bindings SET binding_key=?,name=?,description=?,
                           collection_id=?,collection_version_id=?,follow_latest=?,updated_at=? WHERE id=?""",
                        (*values, binding_id),
                    )
                    event_type = "repointed"
                else:
                    connection.execute(
                        """INSERT INTO application_bindings
                           (id,binding_key,name,description,collection_id,collection_version_id,
                            follow_latest,active,created_at,updated_at)
                           VALUES (?,?,?,?,?,?,?,1,?,?)""",
                        (binding_id, *values[:-1], now, now),
                    )
                    event_type = "created"
                connection.execute(
                    """INSERT INTO application_binding_events
                       (id,application_binding_id,event_type,detail_json,created_at)
                       VALUES (?,?,?,?,?)""",
                    (
                        new_id("appbe"), binding_id, event_type,
                        json.dumps({
                            "collection_id": payload["collection_id"],
                            "collection_version_id": payload.get("collection_version_id"),
                            "follow_latest": bool(payload.get("follow_latest", True)),
                        }, ensure_ascii=False, sort_keys=True), now,
                    ),
                )
        except sqlite3.IntegrityError as error:
            if "application_bindings.binding_key" in str(error):
                raise ValidationError("应用标识已存在，请使用新的唯一标识") from error
            raise
        return self.get_binding(binding_id)

    def get_binding(self, binding_id_or_key: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT a.*,c.name AS collection_name,c.knowledge_type_id,
                          v.version AS pinned_version,v.status AS pinned_version_status
                   FROM application_bindings a JOIN knowledge_collections c ON c.id=a.collection_id
                   LEFT JOIN collection_versions v ON v.id=a.collection_version_id
                   WHERE a.id=? OR a.binding_key=?""",
                (binding_id_or_key, binding_id_or_key),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Application binding not found: {binding_id_or_key}")
        return _decode(row)

    def list_bindings(self) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT a.*,c.name AS collection_name,c.knowledge_type_id,
                          v.version AS pinned_version,v.status AS pinned_version_status
                   FROM application_bindings a JOIN knowledge_collections c ON c.id=a.collection_id
                   LEFT JOIN collection_versions v ON v.id=a.collection_version_id
                   ORDER BY a.created_at DESC"""
            ).fetchall()
        return [_decode(row) for row in rows]

    def list_binding_events(self, binding_id: str) -> list[dict[str, Any]]:
        self.get_binding(binding_id)
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM application_binding_events WHERE application_binding_id=?
                   ORDER BY created_at DESC""",
                (binding_id,),
            ).fetchall()
        return [_decode(row) for row in rows]
