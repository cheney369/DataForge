from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..database import MetadataStore, new_id, utc_now
from ..errors import NotFoundError, ValidationError


APPLICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_applications (
    id TEXT PRIMARY KEY,
    app_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_application_versions (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES ai_applications(id),
    version INTEGER NOT NULL,
    application_binding_id TEXT NOT NULL REFERENCES application_bindings(id),
    llm_service_id TEXT NOT NULL REFERENCES llm_services(id),
    config_json TEXT NOT NULL,
    validation_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    is_current INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    published_at TEXT,
    UNIQUE(application_id, version)
);

CREATE TABLE IF NOT EXISTS ai_application_runs (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES ai_applications(id),
    application_version_id TEXT NOT NULL REFERENCES ai_application_versions(id),
    collection_version_id TEXT REFERENCES collection_versions(id),
    status TEXT NOT NULL,
    question TEXT NOT NULL,
    request_json TEXT NOT NULL DEFAULT '{}',
    retrieval_json TEXT NOT NULL DEFAULT '{}',
    response_json TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS ai_application_credentials (
    id TEXT PRIMARY KEY,
    application_id TEXT NOT NULL REFERENCES ai_applications(id),
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ai_application_versions_app
ON ai_application_versions(application_id, version);
CREATE INDEX IF NOT EXISTS idx_ai_application_runs_app
ON ai_application_runs(application_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_application_credentials_app
ON ai_application_credentials(application_id, created_at);
"""


def _decode(row: Any) -> dict[str, Any]:
    result = dict(row)
    for source, target in (
        ("config_json", "config"),
        ("validation_json", "validation"),
        ("request_json", "request"),
        ("retrieval_json", "retrieval"),
        ("response_json", "response"),
    ):
        if source in result:
            result[target] = json.loads(result.pop(source) or "{}")
    for field in ("active", "is_current"):
        if field in result:
            result[field] = bool(result[field])
    return result


class AIApplicationRepository:
    def __init__(self, store: MetadataStore):
        self.store = store

    def initialize(self) -> None:
        with self.store.connect() as connection:
            connection.executescript(APPLICATION_SCHEMA)

    def create_application(self, app_key: str, name: str, description: str) -> dict[str, Any]:
        application_id = new_id("aiapp")
        now = utc_now()
        try:
            with self.store.connect() as connection:
                connection.execute(
                    """INSERT INTO ai_applications
                       (id,app_key,name,description,active,created_at,updated_at)
                       VALUES (?,?,?,?,1,?,?)""",
                    (application_id, app_key, name.strip(), description.strip(), now, now),
                )
        except sqlite3.IntegrityError as error:
            if "ai_applications.app_key" in str(error):
                raise ValidationError("AI 应用标识已存在") from error
            raise
        return self.get_application(application_id)

    def get_application(self, application_id_or_key: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT a.*,
                          MAX(CASE WHEN v.is_current=1 THEN v.id END) AS current_version_id,
                          MAX(CASE WHEN v.is_current=1 THEN v.version END) AS current_version,
                          COUNT(v.id) AS version_count
                   FROM ai_applications a
                   LEFT JOIN ai_application_versions v ON v.application_id=a.id
                   WHERE a.id=? OR a.app_key=? GROUP BY a.id""",
                (application_id_or_key, application_id_or_key),
            ).fetchone()
        if not row:
            raise NotFoundError(f"AI application not found: {application_id_or_key}")
        return _decode(row)

    def list_applications(self) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT a.*,
                          MAX(CASE WHEN v.is_current=1 THEN v.id END) AS current_version_id,
                          MAX(CASE WHEN v.is_current=1 THEN v.version END) AS current_version,
                          COUNT(v.id) AS version_count
                   FROM ai_applications a
                   LEFT JOIN ai_application_versions v ON v.application_id=a.id
                   GROUP BY a.id ORDER BY a.created_at DESC"""
            ).fetchall()
        return [_decode(row) for row in rows]

    def create_version(
        self,
        application_id: str,
        binding_id: str,
        llm_service_id: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        application = self.get_application(application_id)
        if not application["active"]:
            raise ValidationError("AI 应用已停用")
        version_id = new_id("aiappv")
        now = utc_now()
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            version = int(connection.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM ai_application_versions WHERE application_id=?",
                (application_id,),
            ).fetchone()[0])
            connection.execute(
                """INSERT INTO ai_application_versions
                   (id,application_id,version,application_binding_id,llm_service_id,
                    config_json,validation_json,status,is_current,created_at)
                   VALUES (?,?,?,?,?,?,'{}','draft',0,?)""",
                (
                    version_id, application_id, version, binding_id, llm_service_id,
                    json.dumps(config, ensure_ascii=False, sort_keys=True), now,
                ),
            )
        return self.get_version(version_id)

    def get_version(self, version_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT v.*,a.name AS application_name,a.app_key,
                          b.name AS binding_name,b.binding_key,c.name AS collection_name,
                          l.name AS llm_service_name,l.model AS llm_model
                   FROM ai_application_versions v
                   JOIN ai_applications a ON a.id=v.application_id
                   JOIN application_bindings b ON b.id=v.application_binding_id
                   JOIN knowledge_collections c ON c.id=b.collection_id
                   JOIN llm_services l ON l.id=v.llm_service_id WHERE v.id=?""",
                (version_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"AI application version not found: {version_id}")
        return _decode(row)

    def list_versions(self, application_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE v.application_id=?" if application_id else ""
        params = (application_id,) if application_id else ()
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT v.*,a.name AS application_name,a.app_key,
                           b.name AS binding_name,b.binding_key,c.name AS collection_name,
                           l.name AS llm_service_name,l.model AS llm_model
                    FROM ai_application_versions v
                    JOIN ai_applications a ON a.id=v.application_id
                    JOIN application_bindings b ON b.id=v.application_binding_id
                    JOIN knowledge_collections c ON c.id=b.collection_id
                    JOIN llm_services l ON l.id=v.llm_service_id
                    {where} ORDER BY v.created_at DESC""",
                params,
            ).fetchall()
        return [_decode(row) for row in rows]

    def publish_version(self, version_id: str, validation: dict[str, Any]) -> dict[str, Any]:
        version = self.get_version(version_id)
        if version["status"] != "draft":
            raise ValidationError("只有草稿应用版本可以发布")
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE ai_application_versions SET is_current=0 WHERE application_id=?",
                (version["application_id"],),
            )
            connection.execute(
                """UPDATE ai_application_versions SET status='published',is_current=1,
                   validation_json=?,published_at=? WHERE id=?""",
                (json.dumps(validation, ensure_ascii=False, sort_keys=True), utc_now(), version_id),
            )
        return self.get_version(version_id)

    def get_current_version(self, application_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT id FROM ai_application_versions WHERE application_id=?
                   AND status='published' AND is_current=1""",
                (application_id,),
            ).fetchone()
        if not row:
            raise ValidationError("AI 应用尚无当前发布版本")
        return self.get_version(row["id"])

    def get_published_version(self, application_id: str, version: int) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT id FROM ai_application_versions WHERE application_id=?
                   AND version=? AND status='published'""",
                (application_id, version),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Published AI application version not found: {version}")
        return self.get_version(row["id"])

    def create_credential(
        self,
        application_id: str,
        name: str,
        key_prefix: str,
        key_hash: str,
    ) -> dict[str, Any]:
        self.get_application(application_id)
        credential_id = new_id("aiapp_key")
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO ai_application_credentials
                   (id,application_id,name,key_prefix,key_hash,status,created_at)
                   VALUES (?,?,?,?,?,'active',?)""",
                (credential_id, application_id, name.strip(), key_prefix, key_hash, utc_now()),
            )
        return self.get_credential(credential_id)

    def get_credential(self, credential_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT c.id,c.application_id,c.name,c.key_prefix,c.status,c.created_at,
                          c.last_used_at,c.revoked_at,a.app_key,a.name AS application_name
                   FROM ai_application_credentials c
                   JOIN ai_applications a ON a.id=c.application_id WHERE c.id=?""",
                (credential_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"AI application credential not found: {credential_id}")
        return _decode(row)

    def list_credentials(self, application_id: str) -> list[dict[str, Any]]:
        self.get_application(application_id)
        with self.store.connect() as connection:
            rows = connection.execute(
                """SELECT c.id,c.application_id,c.name,c.key_prefix,c.status,c.created_at,
                          c.last_used_at,c.revoked_at,a.app_key,a.name AS application_name
                   FROM ai_application_credentials c
                   JOIN ai_applications a ON a.id=c.application_id
                   WHERE c.application_id=? ORDER BY c.created_at DESC""",
                (application_id,),
            ).fetchall()
        return [_decode(row) for row in rows]

    def authenticate_credential(self, key_hash: str) -> dict[str, Any] | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT c.id,c.application_id,c.name,c.key_prefix,c.status,c.created_at,
                          c.last_used_at,c.revoked_at,a.app_key,a.name AS application_name,
                          a.active AS application_active
                   FROM ai_application_credentials c
                   JOIN ai_applications a ON a.id=c.application_id
                   WHERE c.key_hash=? AND c.status='active'""",
                (key_hash,),
            ).fetchone()
            if row:
                connection.execute(
                    "UPDATE ai_application_credentials SET last_used_at=? WHERE id=?",
                    (utc_now(), row["id"]),
                )
        return _decode(row) if row else None

    def revoke_credential(self, credential_id: str) -> dict[str, Any]:
        credential = self.get_credential(credential_id)
        if credential["status"] == "revoked":
            return credential
        with self.store.connect() as connection:
            connection.execute(
                """UPDATE ai_application_credentials SET status='revoked',revoked_at=?
                   WHERE id=?""",
                (utc_now(), credential_id),
            )
        return self.get_credential(credential_id)

    def create_run(
        self,
        application_id: str,
        version_id: str,
        question: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = new_id("aiapp_run")
        with self.store.connect() as connection:
            connection.execute(
                """INSERT INTO ai_application_runs
                   (id,application_id,application_version_id,status,question,request_json,
                    retrieval_json,response_json,created_at)
                   VALUES (?,?,?,'running',?,?,'{}','{}',?)""",
                (
                    run_id, application_id, version_id, question,
                    json.dumps(request, ensure_ascii=False, sort_keys=True), utc_now(),
                ),
            )
        return self.get_run(run_id)

    def complete_run(
        self,
        run_id: str,
        collection_version_id: str,
        retrieval: dict[str, Any],
        response: dict[str, Any],
    ) -> dict[str, Any]:
        with self.store.connect() as connection:
            connection.execute(
                """UPDATE ai_application_runs SET status='completed',collection_version_id=?,
                   retrieval_json=?,response_json=?,completed_at=? WHERE id=?""",
                (
                    collection_version_id,
                    json.dumps(retrieval, ensure_ascii=False, sort_keys=True),
                    json.dumps(response, ensure_ascii=False, sort_keys=True),
                    utc_now(), run_id,
                ),
            )
        return self.get_run(run_id)

    def fail_run(self, run_id: str, error: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE ai_application_runs SET status='failed',error=?,completed_at=? WHERE id=?",
                (error, utc_now(), run_id),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.store.connect() as connection:
            row = connection.execute(
                """SELECT r.*,a.name AS application_name,v.version AS application_version
                   FROM ai_application_runs r JOIN ai_applications a ON a.id=r.application_id
                   JOIN ai_application_versions v ON v.id=r.application_version_id WHERE r.id=?""",
                (run_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"AI application run not found: {run_id}")
        return _decode(row)

    def list_runs(self, application_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        where = "WHERE r.application_id=?" if application_id else ""
        params: tuple[Any, ...] = (application_id, limit) if application_id else (limit,)
        with self.store.connect() as connection:
            rows = connection.execute(
                f"""SELECT r.*,a.name AS application_name,v.version AS application_version
                    FROM ai_application_runs r JOIN ai_applications a ON a.id=r.application_id
                    JOIN ai_application_versions v ON v.id=r.application_version_id
                    {where} ORDER BY r.created_at DESC LIMIT ?""",
                params,
            ).fetchall()
        return [_decode(row) for row in rows]
