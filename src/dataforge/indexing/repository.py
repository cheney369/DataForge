from __future__ import annotations

import json
from typing import Any

from ..database import MetadataStore, new_id, utc_now
from ..errors import NotFoundError, ValidationError


INDEXING_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    timeout_seconds REAL NOT NULL DEFAULT 60,
    max_retries INTEGER NOT NULL DEFAULT 1,
    api_key_env TEXT,
    status TEXT NOT NULL DEFAULT 'configured',
    last_test_json TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS embedding_services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    dimension INTEGER NOT NULL DEFAULT 0,
    batch_size INTEGER NOT NULL DEFAULT 32,
    concurrency INTEGER NOT NULL DEFAULT 1,
    timeout_seconds REAL NOT NULL DEFAULT 30,
    max_retries INTEGER NOT NULL DEFAULT 2,
    api_key_env TEXT,
    status TEXT NOT NULL DEFAULT 'configured',
    last_test_json TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reranker_services (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    timeout_seconds REAL NOT NULL DEFAULT 30,
    max_retries INTEGER NOT NULL DEFAULT 1,
    api_key_env TEXT,
    status TEXT NOT NULL DEFAULT 'configured',
    last_test_json TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vector_stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    uri TEXT NOT NULL,
    database_name TEXT NOT NULL DEFAULT 'default',
    collection_prefix TEXT NOT NULL DEFAULT 'dataforge',
    token_env TEXT,
    status TEXT NOT NULL DEFAULT 'configured',
    last_test_json TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_stores (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    uri TEXT NOT NULL,
    graph_space TEXT NOT NULL DEFAULT 'neo4j',
    username_env TEXT,
    password_env TEXT,
    status TEXT NOT NULL DEFAULT 'configured',
    last_test_json TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_profiles (
    id TEXT PRIMARY KEY,
    logical_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    supersedes_id TEXT REFERENCES index_profiles(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    knowledge_type_id TEXT NOT NULL REFERENCES knowledge_types(id),
    embedding_service_id TEXT NOT NULL REFERENCES embedding_services(id),
    vector_store_id TEXT NOT NULL REFERENCES vector_stores(id),
    graph_store_id TEXT REFERENCES graph_stores(id),
    config_json TEXT NOT NULL,
    validation_json TEXT NOT NULL DEFAULT '{}',
    validation_status TEXT NOT NULL DEFAULT 'configured',
    active INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(logical_key, version)
);

CREATE TABLE IF NOT EXISTS knowledge_indexes (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id),
    index_profile_id TEXT NOT NULL REFERENCES index_profiles(id),
    version INTEGER NOT NULL,
    collection_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    expected_count INTEGER NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    dimension INTEGER NOT NULL,
    validation_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    is_current INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE(knowledge_base_id, index_profile_id, version)
);

CREATE TABLE IF NOT EXISTS index_jobs (
    id TEXT PRIMARY KEY,
    knowledge_index_id TEXT NOT NULL REFERENCES knowledge_indexes(id),
    status TEXT NOT NULL DEFAULT 'pending',
    progress INTEGER NOT NULL DEFAULT 0,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    retry_of_job_id TEXT REFERENCES index_jobs(id),
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    stats_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS index_batches (
    id TEXT PRIMARY KEY,
    index_job_id TEXT NOT NULL REFERENCES index_jobs(id),
    batch_no INTEGER NOT NULL,
    record_offset INTEGER NOT NULL,
    record_limit INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    record_count INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    started_at TEXT,
    completed_at TEXT,
    UNIQUE(index_job_id, batch_no)
);

CREATE TABLE IF NOT EXISTS index_records (
    id TEXT PRIMARY KEY,
    knowledge_index_id TEXT NOT NULL REFERENCES knowledge_indexes(id),
    knowledge_record_id TEXT NOT NULL REFERENCES knowledge_records(id),
    external_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(knowledge_index_id, knowledge_record_id)
);

CREATE TABLE IF NOT EXISTS retrieval_profiles (
    id TEXT PRIMARY KEY,
    logical_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    supersedes_id TEXT REFERENCES retrieval_profiles(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    index_profile_id TEXT NOT NULL REFERENCES index_profiles(id),
    config_json TEXT NOT NULL,
    validation_json TEXT NOT NULL DEFAULT '{}',
    validation_status TEXT NOT NULL DEFAULT 'configured',
    active INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(logical_key, version)
);

CREATE INDEX IF NOT EXISTS idx_index_profiles_type ON index_profiles(knowledge_type_id, active);
CREATE INDEX IF NOT EXISTS idx_knowledge_indexes_base ON knowledge_indexes(knowledge_base_id, created_at);
CREATE INDEX IF NOT EXISTS idx_index_jobs_index ON index_jobs(knowledge_index_id, created_at);
CREATE INDEX IF NOT EXISTS idx_index_batches_job ON index_batches(index_job_id, batch_no);
CREATE INDEX IF NOT EXISTS idx_index_records_index ON index_records(knowledge_index_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_profiles_index ON retrieval_profiles(index_profile_id, active);
"""


JSON_COLUMNS = {
    "last_test_json": "last_test",
    "config_json": "config",
    "validation_json": "validation",
    "stats_json": "stats",
    "metadata_json": "metadata",
}


def decode(row: Any) -> dict[str, Any]:
    result = dict(row)
    for column, target in JSON_COLUMNS.items():
        if column in result:
            raw = result.pop(column)
            result[target] = json.loads(raw) if raw else {}
    for column in ("active", "is_default", "is_current", "cancel_requested"):
        if column in result:
            result[column] = bool(result[column])
    return result


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class IndexingRepository:
    def __init__(self, store: MetadataStore):
        self.store = store

    def initialize(self) -> None:
        with self.store.connect() as connection:
            connection.executescript(INDEXING_SCHEMA)

    def save_llm_service(self, payload: dict[str, Any]) -> dict[str, Any]:
        service_id = payload.get("id") or new_id("llm")
        now = utc_now()
        values = (
            payload["name"].strip(),
            payload.get("provider") or "openai-compatible",
            payload["base_url"].rstrip("/"),
            payload["model"].strip(),
            max(1.0, float(payload.get("timeout_seconds") or 60)),
            max(0, int(payload.get("max_retries") or 1)),
            (payload.get("api_key_env") or "").strip() or None,
            now,
        )
        with self.store.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM llm_services WHERE id=?", (service_id,)
            ).fetchone()
            if exists:
                connection.execute(
                    """UPDATE llm_services SET name=?,provider=?,base_url=?,model=?,
                       timeout_seconds=?,max_retries=?,api_key_env=?,status='configured',
                       updated_at=? WHERE id=?""",
                    (*values, service_id),
                )
            else:
                connection.execute(
                    """INSERT INTO llm_services
                       (id,name,provider,base_url,model,timeout_seconds,max_retries,
                        api_key_env,status,last_test_json,active,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,'configured','{}',1,?,?)""",
                    (service_id, *values[:-1], now, now),
                )
        return self.get_llm_service(service_id)

    def get_llm_service(self, service_id: str) -> dict[str, Any]:
        return self._get("llm_services", service_id, "LLM service")

    def list_llm_services(self) -> list[dict[str, Any]]:
        return self._list("llm_services")

    def record_llm_test(self, service_id: str, result: dict[str, Any]) -> dict[str, Any]:
        self.get_llm_service(service_id)
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE llm_services SET status=?,last_test_json=?,updated_at=? WHERE id=?",
                (
                    "ready" if result.get("status") == "ready" else "failed",
                    encode(result), utc_now(), service_id,
                ),
            )
        return self.get_llm_service(service_id)

    def save_embedding_service(self, payload: dict[str, Any]) -> dict[str, Any]:
        service_id = payload.get("id") or new_id("emb")
        now = utc_now()
        with self.store.connect() as connection:
            exists = connection.execute(
                "SELECT created_at FROM embedding_services WHERE id = ?", (service_id,)
            ).fetchone()
            values = (
                payload["name"].strip(),
                payload.get("provider") or "openai-compatible",
                payload["base_url"].rstrip("/"),
                payload["model"].strip(),
                int(payload.get("dimension") or 0),
                max(1, int(payload.get("batch_size") or 32)),
                max(1, int(payload.get("concurrency") or 1)),
                max(1.0, float(payload.get("timeout_seconds") or 30)),
                max(0, int(payload.get("max_retries") or 2)),
                (payload.get("api_key_env") or "").strip() or None,
                now,
            )
            if exists:
                connection.execute(
                    """UPDATE embedding_services SET name=?, provider=?, base_url=?, model=?,
                       dimension=?, batch_size=?, concurrency=?, timeout_seconds=?, max_retries=?,
                       api_key_env=?, status='configured', updated_at=? WHERE id=?""",
                    (*values, service_id),
                )
            else:
                connection.execute(
                    """INSERT INTO embedding_services
                       (id,name,provider,base_url,model,dimension,batch_size,concurrency,
                        timeout_seconds,max_retries,api_key_env,status,last_test_json,active,
                        created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,'configured','{}',1,?,?)""",
                    (service_id, *values[:-1], now, now),
                )
        return self.get_embedding_service(service_id)

    def get_embedding_service(self, service_id: str) -> dict[str, Any]:
        return self._get("embedding_services", service_id, "Embedding service")

    def list_embedding_services(self) -> list[dict[str, Any]]:
        return self._list("embedding_services")

    def record_embedding_test(self, service_id: str, result: dict[str, Any]) -> dict[str, Any]:
        self.get_embedding_service(service_id)
        status = "ready" if result.get("status") == "ready" else "failed"
        with self.store.connect() as connection:
            connection.execute(
                """UPDATE embedding_services SET status=?, last_test_json=?,
                   dimension=CASE WHEN ? > 0 THEN ? ELSE dimension END, updated_at=? WHERE id=?""",
                (
                    status,
                    encode(result),
                    int(result.get("dimension") or 0),
                    int(result.get("dimension") or 0),
                    utc_now(),
                    service_id,
                ),
            )
        return self.get_embedding_service(service_id)

    def save_reranker_service(self, payload: dict[str, Any]) -> dict[str, Any]:
        service_id = payload.get("id") or new_id("reranker")
        now = utc_now()
        values = (
            payload["name"].strip(),
            payload.get("provider") or "openai-compatible",
            payload["base_url"].rstrip("/"),
            payload["model"].strip(),
            max(1.0, float(payload.get("timeout_seconds") or 30)),
            max(0, int(payload.get("max_retries") or 1)),
            (payload.get("api_key_env") or "").strip() or None,
            now,
        )
        with self.store.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM reranker_services WHERE id=?", (service_id,)
            ).fetchone()
            if exists:
                connection.execute(
                    """UPDATE reranker_services SET name=?,provider=?,base_url=?,model=?,
                       timeout_seconds=?,max_retries=?,api_key_env=?,status='configured',
                       updated_at=? WHERE id=?""",
                    (*values, service_id),
                )
            else:
                connection.execute(
                    """INSERT INTO reranker_services
                       (id,name,provider,base_url,model,timeout_seconds,max_retries,
                        api_key_env,status,last_test_json,active,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,'configured','{}',1,?,?)""",
                    (service_id, *values[:-1], now, now),
                )
        return self.get_reranker_service(service_id)

    def get_reranker_service(self, service_id: str) -> dict[str, Any]:
        return self._get("reranker_services", service_id, "Reranker service")

    def list_reranker_services(self) -> list[dict[str, Any]]:
        return self._list("reranker_services")

    def record_reranker_test(
        self, service_id: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        self.get_reranker_service(service_id)
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE reranker_services SET status=?,last_test_json=?,updated_at=? WHERE id=?",
                (
                    "ready" if result.get("status") == "ready" else "failed",
                    encode(result), utc_now(), service_id,
                ),
            )
        return self.get_reranker_service(service_id)

    def save_vector_store(self, payload: dict[str, Any]) -> dict[str, Any]:
        store_id = payload.get("id") or new_id("vstore")
        now = utc_now()
        with self.store.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM vector_stores WHERE id = ?", (store_id,)
            ).fetchone()
            values = (
                payload["name"].strip(),
                payload.get("kind") or "milvus",
                payload["uri"].strip(),
                payload.get("database_name") or "default",
                payload.get("collection_prefix") or "dataforge",
                (payload.get("token_env") or "").strip() or None,
                now,
            )
            if exists:
                connection.execute(
                    """UPDATE vector_stores SET name=?,kind=?,uri=?,database_name=?,
                       collection_prefix=?,token_env=?,status='configured',updated_at=? WHERE id=?""",
                    (*values, store_id),
                )
            else:
                connection.execute(
                    """INSERT INTO vector_stores
                       (id,name,kind,uri,database_name,collection_prefix,token_env,status,
                        last_test_json,active,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,'configured','{}',1,?,?)""",
                    (store_id, *values[:-1], now, now),
                )
        return self.get_vector_store(store_id)

    def get_vector_store(self, store_id: str) -> dict[str, Any]:
        return self._get("vector_stores", store_id, "Vector store")

    def list_vector_stores(self) -> list[dict[str, Any]]:
        return self._list("vector_stores")

    def record_vector_store_test(self, store_id: str, result: dict[str, Any]) -> dict[str, Any]:
        self.get_vector_store(store_id)
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE vector_stores SET status=?,last_test_json=?,updated_at=? WHERE id=?",
                (
                    "ready" if result.get("status") == "ready" else "failed",
                    encode(result),
                    utc_now(),
                    store_id,
                ),
            )
        return self.get_vector_store(store_id)

    def save_graph_store(self, payload: dict[str, Any]) -> dict[str, Any]:
        store_id = payload.get("id") or new_id("gstore")
        now = utc_now()
        with self.store.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM graph_stores WHERE id = ?", (store_id,)
            ).fetchone()
            values = (
                payload["name"].strip(),
                payload.get("kind") or "neo4j",
                payload["uri"].strip(),
                payload.get("graph_space") or "neo4j",
                (payload.get("username_env") or "").strip() or None,
                (payload.get("password_env") or "").strip() or None,
                now,
            )
            if exists:
                connection.execute(
                    """UPDATE graph_stores SET name=?,kind=?,uri=?,graph_space=?,username_env=?,
                       password_env=?,status='configured',updated_at=? WHERE id=?""",
                    (*values, store_id),
                )
            else:
                connection.execute(
                    """INSERT INTO graph_stores
                       (id,name,kind,uri,graph_space,username_env,password_env,status,
                        last_test_json,active,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,'configured','{}',1,?,?)""",
                    (store_id, *values[:-1], now, now),
                )
        return self.get_graph_store(store_id)

    def get_graph_store(self, store_id: str) -> dict[str, Any]:
        return self._get("graph_stores", store_id, "Graph store")

    def list_graph_stores(self) -> list[dict[str, Any]]:
        return self._list("graph_stores")

    def record_graph_store_test(self, store_id: str, result: dict[str, Any]) -> dict[str, Any]:
        self.get_graph_store(store_id)
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE graph_stores SET status=?,last_test_json=?,updated_at=? WHERE id=?",
                (
                    "ready" if result.get("status") == "ready" else "failed",
                    encode(result), utc_now(), store_id,
                ),
            )
        return self.get_graph_store(store_id)

    def create_index_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = new_id("idxp")
        logical_key = payload.get("logical_key") or profile_id
        with self.store.connect() as connection:
            prior = connection.execute(
                "SELECT id,version FROM index_profiles WHERE logical_key=? ORDER BY version DESC LIMIT 1",
                (logical_key,),
            ).fetchone()
            version = int(prior["version"] + 1) if prior else 1
            connection.execute(
                """INSERT INTO index_profiles
                   (id,logical_key,version,supersedes_id,name,description,knowledge_type_id,
                    embedding_service_id,vector_store_id,graph_store_id,config_json,
                    validation_json,validation_status,active,is_default,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'{}','configured',1,0,?)""",
                (
                    profile_id, logical_key, version, prior["id"] if prior else None,
                    payload["name"].strip(), (payload.get("description") or "").strip(),
                    payload["knowledge_type_id"], payload["embedding_service_id"],
                    payload["vector_store_id"], payload.get("graph_store_id"),
                    encode(payload["config"]), utc_now(),
                ),
            )
        return self.get_index_profile(profile_id)

    def get_index_profile(self, profile_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT p.*,k.name AS knowledge_type_name,e.name AS embedding_service_name,
                          v.name AS vector_store_name,g.name AS graph_store_name
                   FROM index_profiles p JOIN knowledge_types k ON k.id=p.knowledge_type_id
                   JOIN embedding_services e ON e.id=p.embedding_service_id
                   JOIN vector_stores v ON v.id=p.vector_store_id
                   LEFT JOIN graph_stores g ON g.id=p.graph_store_id WHERE p.id=?""",
                (profile_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Index profile not found: {profile_id}")
        return decode(row)

    def list_index_profiles(self, knowledge_type_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE p.knowledge_type_id=?" if knowledge_type_id else ""
        params = (knowledge_type_id,) if knowledge_type_id else ()
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT p.*,k.name AS knowledge_type_name,e.name AS embedding_service_name,
                           v.name AS vector_store_name,g.name AS graph_store_name
                    FROM index_profiles p JOIN knowledge_types k ON k.id=p.knowledge_type_id
                    JOIN embedding_services e ON e.id=p.embedding_service_id
                    JOIN vector_stores v ON v.id=p.vector_store_id
                    LEFT JOIN graph_stores g ON g.id=p.graph_store_id {where}
                    ORDER BY p.created_at DESC""",
                params,
            ).fetchall()
        return [decode(row) for row in rows]

    def publish_index_profile(
        self, profile_id: str, config: dict[str, Any], validation: dict[str, Any], make_default: bool
    ) -> dict[str, Any]:
        profile = self.get_index_profile(profile_id)
        if profile["validation_status"] == "validated":
            raise ValidationError("已发布的索引方案不可覆盖")
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if make_default:
                connection.execute(
                    "UPDATE index_profiles SET is_default=0 WHERE knowledge_type_id=?",
                    (profile["knowledge_type_id"],),
                )
            connection.execute(
                """UPDATE index_profiles SET config_json=?,validation_json=?,
                   validation_status='validated',is_default=?,published_at=? WHERE id=?""",
                (encode(config), encode(validation), int(make_default), utc_now(), profile_id),
            )
        return self.get_index_profile(profile_id)

    def deactivate_index_profile(self, profile_id: str) -> dict[str, Any]:
        self.get_index_profile(profile_id)
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE index_profiles SET active=0,is_default=0,validation_status='inactive' WHERE id=?",
                (profile_id,),
            )
        return self.get_index_profile(profile_id)

    def get_default_index_profile(self, knowledge_type_id: str) -> dict[str, Any] | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT id FROM index_profiles WHERE knowledge_type_id=? AND active=1
                   AND is_default=1 AND validation_status='validated'""",
                (knowledge_type_id,),
            ).fetchone()
        return self.get_index_profile(row["id"]) if row else None

    def create_knowledge_index(self, base: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        index_id = new_id("kidx")
        prefix = (profile.get("config") or {}).get("_snapshots", {}).get("vector_store", {}).get(
            "collection_prefix", "dataforge"
        )
        safe_prefix = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in prefix)
        collection = f"{safe_prefix}_{base['id'].replace('-', '_')}_{index_id[-8:]}"
        dimension = int(
            (profile.get("config") or {}).get("_snapshots", {}).get("embedding_service", {}).get(
                "dimension", 0
            )
        )
        with self.store.connect() as connection:
            version = connection.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM knowledge_indexes WHERE knowledge_base_id=?",
                (base["id"],),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO knowledge_indexes
                   (id,knowledge_base_id,index_profile_id,version,collection_name,status,
                    expected_count,record_count,dimension,validation_json,error,is_current,created_at)
                   VALUES (?,?,?,?,?,'pending',?,0,?,'{}',NULL,0,?)""",
                (
                    index_id, base["id"], profile["id"], version, collection,
                    int(base["record_count"]), dimension, utc_now(),
                ),
            )
        return self.get_knowledge_index(index_id)

    def get_knowledge_index(self, index_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT i.*,b.name AS knowledge_base_name,p.name AS index_profile_name,
                          p.knowledge_type_id
                   FROM knowledge_indexes i JOIN knowledge_bases b ON b.id=i.knowledge_base_id
                   JOIN index_profiles p ON p.id=i.index_profile_id WHERE i.id=?""",
                (index_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Knowledge index not found: {index_id}")
        return decode(row)

    def list_knowledge_indexes(self, base_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE i.knowledge_base_id=?" if base_id else ""
        params = (base_id,) if base_id else ()
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT i.*,b.name AS knowledge_base_name,p.name AS index_profile_name,
                           p.knowledge_type_id
                    FROM knowledge_indexes i JOIN knowledge_bases b ON b.id=i.knowledge_base_id
                    JOIN index_profiles p ON p.id=i.index_profile_id {where}
                    ORDER BY i.created_at DESC""",
                params,
            ).fetchall()
        return [decode(row) for row in rows]

    def summarize_knowledge_base(self, base_id: str) -> dict[str, Any]:
        """Return the latest derived-index state without changing the factual asset."""
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT id,status,version,record_count,expected_count,error,is_current,completed_at
                   FROM knowledge_indexes WHERE knowledge_base_id=?
                   ORDER BY is_current DESC,version DESC,created_at DESC LIMIT 1""",
                (base_id,),
            ).fetchone()
        if not row:
            return {
                "index_status": "unindexed",
                "index_version": None,
                "knowledge_index_id": None,
                "index_error": None,
            }
        item = decode(row)
        return {
            "index_status": item["status"],
            "index_version": item["version"],
            "knowledge_index_id": item["id"],
            "index_record_count": item["record_count"],
            "index_expected_count": item["expected_count"],
            "index_error": item.get("error"),
        }

    def update_knowledge_index(self, index_id: str, **changes: Any) -> dict[str, Any]:
        current = self.get_knowledge_index(index_id)
        allowed = {"status", "record_count", "validation", "error", "is_current"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValidationError(f"Unknown knowledge index fields: {sorted(unknown)}")
        values = {
            "status": changes.get("status", current["status"]),
            "record_count": changes.get("record_count", current["record_count"]),
            "validation_json": encode(changes.get("validation", current["validation"])),
            "error": changes.get("error", current.get("error")),
            "is_current": int(changes.get("is_current", current["is_current"])),
        }
        completed = utc_now() if values["status"] in {"available", "failed", "cancelled"} else None
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if values["is_current"]:
                connection.execute(
                    "UPDATE knowledge_indexes SET is_current=0 WHERE knowledge_base_id=?",
                    (current["knowledge_base_id"],),
                )
            connection.execute(
                """UPDATE knowledge_indexes SET status=?,record_count=?,validation_json=?,error=?,
                   is_current=?,completed_at=COALESCE(?,completed_at) WHERE id=?""",
                (*values.values(), completed, index_id),
            )
        return self.get_knowledge_index(index_id)

    def create_index_job(
        self, index_id: str, *, retry_of_job_id: str | None = None, attempt_no: int = 1
    ) -> dict[str, Any]:
        self.get_knowledge_index(index_id)
        job_id = new_id("ijob")
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO index_jobs
                   (id,knowledge_index_id,status,progress,attempt_no,retry_of_job_id,
                    cancel_requested,stats_json,created_at)
                   VALUES (?,?,'pending',0,?,?,0,'{}',?)""",
                (job_id, index_id, attempt_no, retry_of_job_id, utc_now()),
            )
        return self.get_index_job(job_id)

    def get_index_job(self, job_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT j.*,i.knowledge_base_id,i.index_profile_id,i.collection_name,
                          i.expected_count,i.dimension
                   FROM index_jobs j JOIN knowledge_indexes i ON i.id=j.knowledge_index_id
                   WHERE j.id=?""",
                (job_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Index job not found: {job_id}")
        return decode(row)

    def list_index_jobs(self) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT j.*,i.knowledge_base_id,i.index_profile_id,i.collection_name,
                          i.expected_count,i.dimension,b.name AS knowledge_base_name,
                          p.name AS index_profile_name
                   FROM index_jobs j JOIN knowledge_indexes i ON i.id=j.knowledge_index_id
                   JOIN knowledge_bases b ON b.id=i.knowledge_base_id
                   JOIN index_profiles p ON p.id=i.index_profile_id
                   ORDER BY j.created_at DESC"""
            ).fetchall()
        return [decode(row) for row in rows]

    def update_index_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        current = self.get_index_job(job_id)
        status = changes.get("status", current["status"])
        progress = int(changes.get("progress", current["progress"]))
        stats = changes.get("stats", current["stats"])
        error = changes.get("error", current.get("error"))
        started = current.get("started_at") or (utc_now() if status == "running" else None)
        completed = utc_now() if status in {"completed", "failed", "cancelled"} else None
        with self.store.connect() as connection:
            connection.execute(
                """UPDATE index_jobs SET status=?,progress=?,stats_json=?,error=?,started_at=?,
                   completed_at=COALESCE(?,completed_at) WHERE id=?""",
                (status, progress, encode(stats), error, started, completed, job_id),
            )
        return self.get_index_job(job_id)

    def request_index_job_cancel(self, job_id: str) -> dict[str, Any]:
        job = self.get_index_job(job_id)
        if job["status"] not in {"pending", "running"}:
            raise ValidationError("只有等待中或执行中的索引任务可以取消")
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE index_jobs SET cancel_requested=1,status='cancelled',completed_at=? WHERE id=?",
                (utc_now(), job_id),
            )
        self.update_knowledge_index(job["knowledge_index_id"], status="cancelled")
        return self.get_index_job(job_id)

    def create_batches(self, job_id: str, total: int, batch_size: int) -> list[dict[str, Any]]:
        self.get_index_job(job_id)
        with self.store.connect() as connection:
            for batch_no, offset in enumerate(range(0, total, batch_size), start=1):
                connection.execute(
                    """INSERT OR IGNORE INTO index_batches
                       (id,index_job_id,batch_no,record_offset,record_limit,status)
                       VALUES (?,?,?,?,?,'pending')""",
                    (new_id("ibatch"), job_id, batch_no, offset, min(batch_size, total-offset)),
                )
        return self.list_batches(job_id)

    def list_batches(self, job_id: str) -> list[dict[str, Any]]:
        self.get_index_job(job_id)
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM index_batches WHERE index_job_id=? ORDER BY batch_no",
                (job_id,),
            ).fetchall()
        return [decode(row) for row in rows]

    def update_batch(self, batch_id: str, **changes: Any) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute("SELECT * FROM index_batches WHERE id=?", (batch_id,)).fetchone()
            if not row:
                raise NotFoundError(f"Index batch not found: {batch_id}")
            current = decode(row)
            status = changes.get("status", current["status"])
            started = current.get("started_at") or (utc_now() if status == "running" else None)
            completed = utc_now() if status in {"completed", "failed", "cancelled"} else None
            connection.execute(
                """UPDATE index_batches SET status=?,record_count=?,token_count=?,error=?,
                   started_at=?,completed_at=COALESCE(?,completed_at) WHERE id=?""",
                (
                    status, int(changes.get("record_count", current["record_count"])),
                    int(changes.get("token_count", current["token_count"])),
                    changes.get("error", current.get("error")), started, completed, batch_id,
                ),
            )
            updated = connection.execute("SELECT * FROM index_batches WHERE id=?", (batch_id,)).fetchone()
        return decode(updated)

    def list_records_for_indexing(
        self, base_id: str, *, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT id,knowledge_base_id,source_version_id,source_locator_json,data_json
                   FROM knowledge_records WHERE knowledge_base_id=? ORDER BY record_index
                   LIMIT ? OFFSET ?""",
                (base_id, limit, offset),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["source_locator"] = json.loads(item.pop("source_locator_json") or "{}")
            item["data"] = json.loads(item.pop("data_json") or "{}")
            result.append(item)
        return result

    def save_index_records(self, index_id: str, records: list[dict[str, Any]]) -> None:
        now = utc_now()
        with self.store.connect() as connection:
            connection.executemany(
                """INSERT INTO index_records
                   (id,knowledge_index_id,knowledge_record_id,external_id,content_hash,
                    indexed_text,metadata_json,created_at)
                   VALUES (?,?,?,?,?,?,?,?)
                   ON CONFLICT(knowledge_index_id,knowledge_record_id) DO UPDATE SET
                   external_id=excluded.external_id,content_hash=excluded.content_hash,
                   indexed_text=excluded.indexed_text,metadata_json=excluded.metadata_json""",
                [
                    (
                        item.get("id") or new_id("irec"), index_id,
                        item["knowledge_record_id"], item["external_id"], item["content_hash"],
                        item["indexed_text"], encode(item["metadata"]), now,
                    )
                    for item in records
                ],
            )

    def count_index_records(self, index_id: str) -> int:
        with self.store.connect() as connection:
            return int(connection.execute(
                "SELECT COUNT(*) FROM index_records WHERE knowledge_index_id=?", (index_id,)
            ).fetchone()[0])

    def get_index_record_hashes(self, index_id: str) -> dict[str, str]:
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT knowledge_record_id,content_hash FROM index_records WHERE knowledge_index_id=?",
                (index_id,),
            ).fetchall()
        return {row["knowledge_record_id"]: row["content_hash"] for row in rows}

    def get_index_record_lineage(self, index_id: str, external_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT ir.*,kr.source_locator_json,kr.data_json,kb.name AS knowledge_base_name,
                          sv.original_filename,s.name AS source_name
                   FROM index_records ir JOIN knowledge_records kr ON kr.id=ir.knowledge_record_id
                   JOIN knowledge_bases kb ON kb.id=kr.knowledge_base_id
                   JOIN source_versions sv ON sv.id=kr.source_version_id
                   JOIN sources s ON s.id=sv.source_id
                   WHERE ir.knowledge_index_id=? AND ir.external_id=?""",
                (index_id, external_id),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Index record not found: {index_id}/{external_id}")
        result = decode(row)
        result["source_locator"] = json.loads(result.pop("source_locator_json") or "{}")
        result["data"] = json.loads(result.pop("data_json") or "{}")
        return result

    def create_retrieval_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile_id = new_id("retp")
        logical_key = payload.get("logical_key") or profile_id
        with self.store.connect() as connection:
            prior = connection.execute(
                "SELECT id,version FROM retrieval_profiles WHERE logical_key=? ORDER BY version DESC LIMIT 1",
                (logical_key,),
            ).fetchone()
            version = int(prior["version"] + 1) if prior else 1
            connection.execute(
                """INSERT INTO retrieval_profiles
                   (id,logical_key,version,supersedes_id,name,description,index_profile_id,
                    config_json,validation_json,validation_status,active,is_default,created_at)
                   VALUES (?,?,?,?,?,?,?,?,'{}','configured',1,0,?)""",
                (
                    profile_id, logical_key, version, prior["id"] if prior else None,
                    payload["name"].strip(), (payload.get("description") or "").strip(),
                    payload["index_profile_id"], encode(payload["config"]), utc_now(),
                ),
            )
        return self.get_retrieval_profile(profile_id)

    def get_retrieval_profile(self, profile_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT r.*,p.name AS index_profile_name,p.knowledge_type_id
                   FROM retrieval_profiles r JOIN index_profiles p ON p.id=r.index_profile_id
                   WHERE r.id=?""",
                (profile_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Retrieval profile not found: {profile_id}")
        return decode(row)

    def list_retrieval_profiles(self) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT r.*,p.name AS index_profile_name,p.knowledge_type_id
                   FROM retrieval_profiles r JOIN index_profiles p ON p.id=r.index_profile_id
                   ORDER BY r.created_at DESC"""
            ).fetchall()
        return [decode(row) for row in rows]

    def publish_retrieval_profile(
        self, profile_id: str, validation: dict[str, Any], make_default: bool
    ) -> dict[str, Any]:
        profile = self.get_retrieval_profile(profile_id)
        if profile["validation_status"] == "validated":
            raise ValidationError("已发布的检索方案不可覆盖")
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if make_default:
                connection.execute(
                    "UPDATE retrieval_profiles SET is_default=0 WHERE index_profile_id=?",
                    (profile["index_profile_id"],),
                )
            connection.execute(
                """UPDATE retrieval_profiles SET validation_json=?,validation_status='validated',
                   is_default=?,published_at=? WHERE id=?""",
                (encode(validation), int(make_default), utc_now(), profile_id),
            )
        return self.get_retrieval_profile(profile_id)

    def get_available_index(self, base_id: str, profile_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT id FROM knowledge_indexes WHERE knowledge_base_id=? AND index_profile_id=?
                   AND status='available' ORDER BY is_current DESC,version DESC LIMIT 1""",
                (base_id, profile_id),
            ).fetchone()
        if not row:
            raise ValidationError("该知识库尚无与检索方案兼容的可用索引")
        return self.get_knowledge_index(row["id"])

    def recover_interrupted_jobs(self) -> list[str]:
        now = utc_now()
        reason = "服务重启中断；可从已完成批次继续重试"
        with self.store.connect() as connection:
            rows = connection.execute(
                "SELECT id,knowledge_index_id FROM index_jobs WHERE status='running'"
            ).fetchall()
            ids = [row["id"] for row in rows]
            for row in rows:
                connection.execute(
                    "UPDATE index_jobs SET status='failed',error=?,completed_at=? WHERE id=?",
                    (reason, now, row["id"]),
                )
                connection.execute(
                    "UPDATE index_batches SET status='pending',error=NULL WHERE index_job_id=? AND status='running'",
                    (row["id"],),
                )
                connection.execute(
                    "UPDATE knowledge_indexes SET status='failed',error=? WHERE id=?",
                    (reason, row["knowledge_index_id"]),
                )
        return ids

    def _get(self, table: str, item_id: str, label: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(f"SELECT * FROM {table} WHERE id=?", (item_id,)).fetchone()
        if not row:
            raise NotFoundError(f"{label} not found: {item_id}")
        return decode(row)

    def _list(self, table: str) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(f"SELECT * FROM {table} ORDER BY created_at DESC").fetchall()
        return [decode(row) for row in rows]
