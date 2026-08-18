from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .errors import NotFoundError, ValidationError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    for key in (
        "metadata_json",
        "definition_json",
        "stats_json",
        "schema_json",
        "payload_json",
        "detail_json",
        "output_schema_json",
        "pipeline_snapshot_json",
        "source_version_ids_json",
        "validation_json",
        "source_locator_json",
        "data_json",
    ):
        if key in result:
            raw = result.pop(key)
            result[key.removesuffix("_json")] = json.loads(raw) if raw else {}
    return result


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_versions (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    version_no INTEGER NOT NULL,
    blob_uri TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_id, version_no),
    UNIQUE(source_id, sha256)
);

CREATE TABLE IF NOT EXISTS pipelines (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL,
    engine TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    pipeline_id TEXT NOT NULL REFERENCES pipelines(id),
    source_version_id TEXT NOT NULL REFERENCES source_versions(id),
    status TEXT NOT NULL,
    engine TEXT NOT NULL,
    work_dir TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    error TEXT,
    asset_version_id TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS run_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, sequence)
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    logical_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_versions (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(id),
    version_no INTEGER NOT NULL,
    run_id TEXT NOT NULL UNIQUE REFERENCES runs(id),
    blob_uri TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    record_count INTEGER NOT NULL,
    schema_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(asset_id, version_no)
);

CREATE TABLE IF NOT EXISTS lineage (
    id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_versions(id),
    run_id TEXT NOT NULL REFERENCES runs(id),
    asset_version_id TEXT NOT NULL REFERENCES asset_versions(id),
    relation_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_version_id, run_id, asset_version_id)
);

CREATE TABLE IF NOT EXISTS publications (
    id TEXT PRIMARY KEY,
    asset_version_id TEXT NOT NULL REFERENCES asset_versions(id),
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    published_uri TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(asset_version_id, channel)
);

CREATE TABLE IF NOT EXISTS knowledge_types (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    logical_key TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    supersedes_id TEXT REFERENCES knowledge_types(id),
    schema_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS standard_pipelines (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    knowledge_type_id TEXT NOT NULL REFERENCES knowledge_types(id),
    pipeline_ref TEXT NOT NULL,
    engine TEXT NOT NULL,
    version INTEGER NOT NULL,
    description TEXT NOT NULL,
    output_schema_json TEXT NOT NULL,
    pipeline_snapshot_json TEXT NOT NULL DEFAULT '{}',
    pipeline_hash TEXT,
    sample_task_id TEXT,
    validation_status TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    knowledge_type_id TEXT NOT NULL REFERENCES knowledge_types(id),
    standard_pipeline_id TEXT NOT NULL REFERENCES standard_pipelines(id),
    source_version_ids_json TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    validation_json TEXT NOT NULL,
    error TEXT,
    knowledge_base_id TEXT,
    retry_of_job_id TEXT REFERENCES knowledge_jobs(id),
    attempt_no INTEGER NOT NULL DEFAULT 1,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    cancelled_at TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_job_items (
    job_id TEXT NOT NULL REFERENCES knowledge_jobs(id),
    source_version_id TEXT NOT NULL REFERENCES source_versions(id),
    status TEXT NOT NULL DEFAULT 'pending',
    run_id TEXT REFERENCES runs(id),
    asset_version_id TEXT REFERENCES asset_versions(id),
    dataflow_task_id TEXT,
    error TEXT,
    started_at TEXT,
    completed_at TEXT,
    PRIMARY KEY(job_id, source_version_id)
);

CREATE TABLE IF NOT EXISTS knowledge_job_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES knowledge_jobs(id),
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(job_id, sequence)
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    knowledge_type_id TEXT NOT NULL REFERENCES knowledge_types(id),
    standard_pipeline_id TEXT NOT NULL REFERENCES standard_pipelines(id),
    job_id TEXT NOT NULL UNIQUE REFERENCES knowledge_jobs(id),
    record_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_records (
    id TEXT PRIMARY KEY,
    knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(id),
    record_index INTEGER NOT NULL,
    source_version_id TEXT NOT NULL REFERENCES source_versions(id),
    run_id TEXT REFERENCES runs(id),
    asset_version_id TEXT REFERENCES asset_versions(id),
    source_locator_json TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(knowledge_base_id, record_index)
);

CREATE INDEX IF NOT EXISTS idx_source_versions_source ON source_versions(source_id, version_no);
CREATE INDEX IF NOT EXISTS idx_runs_source_version ON runs(source_version_id, created_at);
CREATE INDEX IF NOT EXISTS idx_run_events_run ON run_events(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_asset_versions_asset ON asset_versions(asset_id, version_no);
CREATE INDEX IF NOT EXISTS idx_knowledge_jobs_created ON knowledge_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_job_items_status ON knowledge_job_items(job_id, status);
CREATE INDEX IF NOT EXISTS idx_knowledge_job_events_job ON knowledge_job_events(job_id, sequence);
CREATE INDEX IF NOT EXISTS idx_knowledge_records_base ON knowledge_records(knowledge_base_id, record_index);
CREATE INDEX IF NOT EXISTS idx_knowledge_records_source ON knowledge_records(source_version_id);
"""


class MetadataStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(standard_pipelines)").fetchall()
            }
            if "is_default" not in columns:
                connection.execute(
                    "ALTER TABLE standard_pipelines ADD COLUMN is_default INTEGER NOT NULL DEFAULT 0"
                )
            if "pipeline_snapshot_json" not in columns:
                connection.execute(
                    "ALTER TABLE standard_pipelines ADD COLUMN pipeline_snapshot_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "pipeline_hash" not in columns:
                connection.execute("ALTER TABLE standard_pipelines ADD COLUMN pipeline_hash TEXT")
            if "sample_task_id" not in columns:
                connection.execute("ALTER TABLE standard_pipelines ADD COLUMN sample_task_id TEXT")
            type_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(knowledge_types)").fetchall()
            }
            if "logical_key" not in type_columns:
                connection.execute("ALTER TABLE knowledge_types ADD COLUMN logical_key TEXT")
            if "version" not in type_columns:
                connection.execute(
                    "ALTER TABLE knowledge_types ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
                )
            if "supersedes_id" not in type_columns:
                connection.execute("ALTER TABLE knowledge_types ADD COLUMN supersedes_id TEXT")
            connection.execute(
                "UPDATE knowledge_types SET logical_key = id WHERE logical_key IS NULL OR logical_key = ''"
            )
            job_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(knowledge_jobs)").fetchall()
            }
            if "retry_of_job_id" not in job_columns:
                connection.execute("ALTER TABLE knowledge_jobs ADD COLUMN retry_of_job_id TEXT")
            if "attempt_no" not in job_columns:
                connection.execute(
                    "ALTER TABLE knowledge_jobs ADD COLUMN attempt_no INTEGER NOT NULL DEFAULT 1"
                )
            if "cancel_requested" not in job_columns:
                connection.execute(
                    "ALTER TABLE knowledge_jobs ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0"
                )
            if "cancelled_at" not in job_columns:
                connection.execute("ALTER TABLE knowledge_jobs ADD COLUMN cancelled_at TEXT")
            existing_jobs = connection.execute(
                "SELECT id, source_version_ids_json, status, created_at FROM knowledge_jobs"
            ).fetchall()
            for job in existing_jobs:
                source_ids = json.loads(job["source_version_ids_json"] or "[]")
                item_status = job["status"] if job["status"] in {
                    "completed",
                    "failed",
                    "cancelled",
                } else "pending"
                connection.executemany(
                    """INSERT OR IGNORE INTO knowledge_job_items
                       (job_id, source_version_id, status) VALUES (?, ?, ?)""",
                    [(job["id"], source_id, item_status) for source_id in source_ids],
                )
                connection.execute(
                    """INSERT OR IGNORE INTO knowledge_job_events
                       VALUES (?, ?, 1, 'created', '处理任务已创建', '{}', ?)""",
                    (new_id("kjevt"), job["id"], job["created_at"]),
                )

    def create_source(self, name: str, kind: str, metadata: dict[str, Any]) -> dict[str, Any]:
        source_id = new_id("src")
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                (source_id, name, kind, _json(metadata), utc_now()),
            )
        return self.get_source(source_id)

    def get_source(self, source_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Source not found: {source_id}")
        return _decode_row(row) or {}

    def list_sources(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM sources ORDER BY created_at DESC").fetchall()
        return [_decode_row(row) or {} for row in rows]

    def find_source_version_by_hash(self, source_id: str, sha256: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_versions WHERE source_id = ? AND sha256 = ?",
                (source_id, sha256),
            ).fetchone()
        return _decode_row(row)

    def create_source_version(
        self,
        source_id: str,
        blob_uri: str,
        sha256: str,
        size_bytes: int,
        media_type: str,
        original_filename: str,
    ) -> dict[str, Any]:
        version_id = new_id("srcv")
        with self.connect() as connection:
            next_version = connection.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 FROM source_versions WHERE source_id = ?",
                (source_id,),
            ).fetchone()[0]
            connection.execute(
                """INSERT INTO source_versions
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    source_id,
                    next_version,
                    blob_uri,
                    sha256,
                    size_bytes,
                    media_type,
                    original_filename,
                    utc_now(),
                ),
            )
        return self.get_source_version(version_id)

    def get_source_version(self, version_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM source_versions WHERE id = ?", (version_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Source version not found: {version_id}")
        return _decode_row(row) or {}

    def list_source_versions(self, source_id: str) -> list[dict[str, Any]]:
        self.get_source(source_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM source_versions WHERE source_id = ? ORDER BY version_no DESC",
                (source_id,),
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def register_pipeline(
        self,
        pipeline_id: str,
        name: str,
        version: int,
        engine: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO pipelines (id, name, version, engine, definition_json, active, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name = excluded.name,
                     version = excluded.version,
                     engine = excluded.engine,
                     definition_json = excluded.definition_json,
                     active = 1""",
                (pipeline_id, name, version, engine, _json(definition), utc_now()),
            )
        return self.get_pipeline(pipeline_id)

    def get_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Pipeline not found: {pipeline_id}")
        return _decode_row(row) or {}

    def list_pipelines(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM pipelines ORDER BY name, version DESC").fetchall()
        return [_decode_row(row) or {} for row in rows]

    def create_run(
        self,
        pipeline_id: str,
        source_version_id: str,
        engine: str,
        work_dir: Path,
        *,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        run_id = run_id or new_id("run")
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO runs
                   (id, pipeline_id, source_version_id, status, engine, work_dir, stats_json, created_at)
                   VALUES (?, ?, ?, 'pending', ?, ?, '{}', ?)""",
                (run_id, pipeline_id, source_version_id, engine, str(work_dir), utc_now()),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Run not found: {run_id}")
        return _decode_row(row) or {}

    def list_runs(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
        return [_decode_row(row) or {} for row in rows]

    def transition_run(
        self,
        run_id: str,
        status: str,
        *,
        stats: dict[str, Any] | None = None,
        error: str | None = None,
        asset_version_id: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_run(run_id)
        allowed = {
            "pending": {"preparing", "failed"},
            "preparing": {"running", "failed"},
            "running": {"publishing", "failed"},
            "publishing": {"completed", "failed"},
            "completed": set(),
            "failed": set(),
        }
        if status not in allowed[current["status"]]:
            raise ValidationError(f"Invalid run transition: {current['status']} -> {status}")
        started_at = utc_now() if status == "running" and not current.get("started_at") else current.get("started_at")
        completed_at = utc_now() if status in {"completed", "failed"} else current.get("completed_at")
        with self.connect() as connection:
            connection.execute(
                """UPDATE runs SET status = ?, stats_json = ?, error = ?, asset_version_id = ?,
                   started_at = ?, completed_at = ? WHERE id = ?""",
                (
                    status,
                    _json(stats if stats is not None else current.get("stats", {})),
                    error,
                    asset_version_id or current.get("asset_version_id"),
                    started_at,
                    completed_at,
                    run_id,
                ),
            )
        return self.get_run(run_id)

    def add_run_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id = new_id("evt")
        with self.connect() as connection:
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO run_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_id, run_id, sequence, event_type, message, _json(payload or {}), utc_now()),
            )
            row = connection.execute("SELECT * FROM run_events WHERE id = ?", (event_id,)).fetchone()
        return _decode_row(row) or {}

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM run_events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def publish_asset(
        self,
        *,
        logical_key: str,
        name: str,
        asset_type: str,
        run_id: str,
        source_version_id: str,
        blob_uri: str,
        sha256: str,
        size_bytes: int,
        record_count: int,
        schema: dict[str, str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self.connect() as connection:
            asset_row = connection.execute("SELECT * FROM assets WHERE logical_key = ?", (logical_key,)).fetchone()
            if asset_row:
                asset_id = asset_row["id"]
            else:
                asset_id = new_id("asset")
                connection.execute(
                    "INSERT INTO assets VALUES (?, ?, ?, ?, ?)",
                    (asset_id, logical_key, name, asset_type, utc_now()),
                )
            next_version = connection.execute(
                "SELECT COALESCE(MAX(version_no), 0) + 1 FROM asset_versions WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()[0]
            asset_version_id = new_id("assetv")
            connection.execute(
                """INSERT INTO asset_versions
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'published', ?)""",
                (
                    asset_version_id,
                    asset_id,
                    next_version,
                    run_id,
                    blob_uri,
                    sha256,
                    size_bytes,
                    record_count,
                    _json(schema),
                    utc_now(),
                ),
            )
            connection.execute(
                "INSERT INTO lineage VALUES (?, ?, ?, ?, 'derived_from', ?)",
                (new_id("lin"), source_version_id, run_id, asset_version_id, utc_now()),
            )
            connection.execute(
                "INSERT INTO publications VALUES (?, ?, 'internal', 'published', ?, ?)",
                (new_id("pub"), asset_version_id, blob_uri, utc_now()),
            )
        return self.get_asset(asset_id), self.get_asset_version(asset_version_id)

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Asset not found: {asset_id}")
        return _decode_row(row) or {}

    def get_asset_version(self, version_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM asset_versions WHERE id = ?", (version_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Asset version not found: {version_id}")
        return _decode_row(row) or {}

    def list_asset_versions(self, asset_id: str) -> list[dict[str, Any]]:
        self.get_asset(asset_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM asset_versions WHERE asset_id = ? ORDER BY version_no DESC",
                (asset_id,),
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def list_assets(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT a.*, av.id AS latest_version_id, av.version_no AS latest_version_no,
                          av.record_count, av.status
                   FROM assets a
                   LEFT JOIN asset_versions av ON av.asset_id = a.id
                     AND av.version_no = (SELECT MAX(v.version_no) FROM asset_versions v WHERE v.asset_id = a.id)
                   ORDER BY a.created_at DESC"""
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def get_lineage(self, asset_version_id: str) -> dict[str, Any]:
        self.get_asset_version(asset_version_id)
        with self.connect() as connection:
            row = connection.execute(
                """SELECT l.*, sv.source_id, sv.version_no AS source_version_no,
                          r.pipeline_id, r.engine, r.stats_json,
                          av.asset_id, av.version_no AS asset_version_no
                   FROM lineage l
                   JOIN source_versions sv ON sv.id = l.source_version_id
                   JOIN runs r ON r.id = l.run_id
                   JOIN asset_versions av ON av.id = l.asset_version_id
                   WHERE l.asset_version_id = ?""",
                (asset_version_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Lineage not found for asset version: {asset_version_id}")
        return _decode_row(row) or {}

    def register_knowledge_type(
        self, type_id: str, name: str, description: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO knowledge_types
                   (id, name, description, logical_key, version, supersedes_id,
                    schema_json, active, created_at)
                   VALUES (?, ?, ?, ?, 1, NULL, ?, 1, ?)
                   ON CONFLICT(id) DO NOTHING""",
                (type_id, name, description, type_id, _json(schema), utc_now()),
            )
        return self.get_knowledge_type(type_id)

    def create_knowledge_type_version(
        self,
        base_type_id: str,
        type_id: str,
        name: str,
        description: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            base_row = connection.execute(
                "SELECT * FROM knowledge_types WHERE id = ?", (base_type_id,)
            ).fetchone()
            if not base_row:
                raise NotFoundError(f"Knowledge type not found: {base_type_id}")
            base = _decode_row(base_row) or {}
            if not base["active"]:
                raise ValidationError("只能基于当前生效的知识类型创建新版本")
            logical_key = base.get("logical_key") or base["id"]
            next_version = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM knowledge_types WHERE logical_key = ?",
                (logical_key,),
            ).fetchone()[0]
            connection.execute(
                "UPDATE knowledge_types SET active = 0 WHERE logical_key = ?",
                (logical_key,),
            )
            connection.execute(
                """INSERT INTO knowledge_types
                   (id, name, description, logical_key, version, supersedes_id,
                    schema_json, active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
                (
                    type_id,
                    name,
                    description,
                    logical_key,
                    next_version,
                    base_type_id,
                    _json(schema),
                    utc_now(),
                ),
            )
        return self.get_knowledge_type(type_id)

    def get_knowledge_type(self, type_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM knowledge_types WHERE id = ?", (type_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Knowledge type not found: {type_id}")
        return _decode_row(row) or {}

    def list_knowledge_types(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_types ORDER BY logical_key, version DESC, created_at"
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def register_standard_pipeline(
        self,
        pipeline_id: str,
        name: str,
        knowledge_type_id: str,
        pipeline_ref: str,
        engine: str,
        version: int,
        description: str,
        output_schema: dict[str, Any],
        validation_status: str,
        is_default: bool = False,
        pipeline_snapshot: dict[str, Any] | None = None,
        pipeline_hash: str | None = None,
        sample_task_id: str | None = None,
    ) -> dict[str, Any]:
        self.get_knowledge_type(knowledge_type_id)
        try:
            existing = self.get_standard_pipeline(pipeline_id)
        except NotFoundError:
            existing = None
        if (
            existing
            and existing.get("pipeline_snapshot")
            and existing.get("validation_status") in {"validated", "inactive"}
        ):
            immutable_values = {
                "name": name,
                "knowledge_type_id": knowledge_type_id,
                "pipeline_ref": pipeline_ref,
                "engine": engine,
                "version": version,
                "description": description,
                "output_schema": output_schema,
                "pipeline_snapshot": pipeline_snapshot or {},
                "pipeline_hash": pipeline_hash,
                "sample_task_id": sample_task_id,
                "validation_status": validation_status,
            }
            if any(existing.get(key) != value for key, value in immutable_values.items()):
                raise ValidationError("已发布的标准流程版本不可覆盖，请发布新的版本")
            if is_default and not existing.get("is_default"):
                return self.set_default_standard_pipeline(pipeline_id)
            return existing
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO standard_pipelines
                   (id, name, knowledge_type_id, pipeline_ref, engine, version, description,
                    output_schema_json, pipeline_snapshot_json, pipeline_hash, sample_task_id,
                    validation_status, active, is_default, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name = excluded.name,
                     knowledge_type_id = excluded.knowledge_type_id,
                     pipeline_ref = excluded.pipeline_ref,
                     engine = excluded.engine,
                     version = excluded.version,
                     description = excluded.description,
                     output_schema_json = excluded.output_schema_json,
                     pipeline_snapshot_json = excluded.pipeline_snapshot_json,
                     pipeline_hash = excluded.pipeline_hash,
                     sample_task_id = excluded.sample_task_id,
                     validation_status = excluded.validation_status,
                     active = 1,
                     is_default = CASE
                       WHEN excluded.is_default = 1 THEN 1
                       ELSE standard_pipelines.is_default
                     END,
                     updated_at = excluded.updated_at""",
                (
                    pipeline_id,
                    name,
                    knowledge_type_id,
                    pipeline_ref,
                    engine,
                    version,
                    description,
                    _json(output_schema),
                    _json(pipeline_snapshot or {}),
                    pipeline_hash,
                    sample_task_id,
                    validation_status,
                    int(is_default),
                    now,
                    now,
                ),
            )
            if is_default and validation_status == "validated":
                connection.execute(
                    """UPDATE standard_pipelines SET is_default = CASE WHEN id = ? THEN 1 ELSE 0 END
                       WHERE knowledge_type_id = ?""",
                    (pipeline_id, knowledge_type_id),
                )
        return self.get_standard_pipeline(pipeline_id)

    def set_default_standard_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        pipeline = self.get_standard_pipeline(pipeline_id)
        if pipeline["validation_status"] != "validated" or not pipeline["active"]:
            raise ValidationError("只有已验证并启用的标准流程才能设为默认流程")
        with self.connect() as connection:
            connection.execute(
                """UPDATE standard_pipelines SET is_default = CASE WHEN id = ? THEN 1 ELSE 0 END
                   WHERE knowledge_type_id = ?""",
                (pipeline_id, pipeline["knowledge_type_id"]),
            )
        return self.get_standard_pipeline(pipeline_id)

    def deactivate_standard_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        pipeline = self.get_standard_pipeline(pipeline_id)
        if not pipeline["active"]:
            return pipeline
        with self.connect() as connection:
            connection.execute(
                """UPDATE standard_pipelines SET active = 0, is_default = 0,
                   validation_status = 'inactive', updated_at = ? WHERE id = ?""",
                (utc_now(), pipeline_id),
            )
        return self.get_standard_pipeline(pipeline_id)

    def get_default_standard_pipeline(self, knowledge_type_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT * FROM standard_pipelines
                   WHERE knowledge_type_id = ? AND active = 1 AND validation_status = 'validated'
                   ORDER BY is_default DESC, updated_at DESC LIMIT 1""",
                (knowledge_type_id,),
            ).fetchone()
        if not row:
            raise ValidationError("当前生成内容尚未开放，请联系流程管理员")
        return _decode_row(row) or {}

    def get_standard_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM standard_pipelines WHERE id = ?", (pipeline_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Standard pipeline not found: {pipeline_id}")
        return _decode_row(row) or {}

    def list_standard_pipelines(self, knowledge_type_id: str | None = None) -> list[dict[str, Any]]:
        query = """SELECT p.*, k.name AS knowledge_type_name
                   FROM standard_pipelines p
                   JOIN knowledge_types k ON k.id = p.knowledge_type_id
                   WHERE 1 = 1"""
        params: tuple[Any, ...] = ()
        if knowledge_type_id:
            query += " AND p.knowledge_type_id = ?"
            params = (knowledge_type_id,)
        query += " ORDER BY k.created_at, p.name"
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def create_knowledge_job(
        self,
        name: str,
        knowledge_type_id: str,
        standard_pipeline_id: str,
        source_version_ids: list[str],
        retry_of_job_id: str | None = None,
        attempt_no: int = 1,
    ) -> dict[str, Any]:
        job_id = new_id("kjob")
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO knowledge_jobs
                   (id, name, knowledge_type_id, standard_pipeline_id, source_version_ids_json,
                    status, progress, validation_json, retry_of_job_id, attempt_no, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', 0, '{}', ?, ?, ?)""",
                (
                    job_id,
                    name,
                    knowledge_type_id,
                    standard_pipeline_id,
                    _json(source_version_ids),
                    retry_of_job_id,
                    max(1, attempt_no),
                    utc_now(),
                ),
            )
            connection.executemany(
                """INSERT INTO knowledge_job_items
                   (job_id, source_version_id, status) VALUES (?, ?, 'pending')""",
                [(job_id, source_id) for source_id in source_version_ids],
            )
            connection.execute(
                """INSERT INTO knowledge_job_events
                   VALUES (?, ?, 1, 'created', '处理任务已创建', '{}', ?)""",
                (new_id("kjevt"), job_id, utc_now()),
            )
        return self.get_knowledge_job(job_id)

    def get_knowledge_job_retry(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT * FROM knowledge_jobs WHERE retry_of_job_id = ?
                   ORDER BY attempt_no DESC, created_at DESC LIMIT 1""",
                (job_id,),
            ).fetchone()
        return _decode_row(row)

    def update_knowledge_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        validation: dict[str, Any] | None = None,
        error: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if not row:
                raise NotFoundError(f"Knowledge job not found: {job_id}")
            current = _decode_row(row) or {}
            new_status = status or current["status"]
            if current.get("cancel_requested") and new_status in {"running", "completed"}:
                new_status = "cancelled"
            started_at = current.get("started_at")
            completed_at = current.get("completed_at")
            if new_status == "running" and not started_at:
                started_at = utc_now()
            if new_status in {"completed", "failed", "cancelled"}:
                completed_at = utc_now()
            connection.execute(
                """UPDATE knowledge_jobs SET status = ?, progress = ?, validation_json = ?,
                   error = ?, knowledge_base_id = ?, started_at = ?, completed_at = ? WHERE id = ?""",
                (
                    new_status,
                    progress if progress is not None else current["progress"],
                    _json(validation if validation is not None else current.get("validation", {})),
                    error,
                    knowledge_base_id or current.get("knowledge_base_id"),
                    started_at,
                    completed_at,
                    job_id,
                ),
            )
        return self.get_knowledge_job(job_id)

    def request_knowledge_job_cancel(self, job_id: str) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT status FROM knowledge_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if not current:
                raise NotFoundError(f"Knowledge job not found: {job_id}")
            if current["status"] not in {"pending", "running"}:
                raise ValidationError("只有等待中或处理中的任务可以取消")
            connection.execute(
                """UPDATE knowledge_jobs SET status = 'cancelled', cancel_requested = 1,
                   cancelled_at = ?, completed_at = ? WHERE id = ?""",
                (now, now, job_id),
            )
            connection.execute(
                """UPDATE knowledge_job_items SET status = 'cancelled', completed_at = ?
                   WHERE job_id = ? AND status IN ('pending', 'running')""",
                (now, job_id),
            )
        return self.get_knowledge_job(job_id)

    def is_knowledge_job_cancel_requested(self, job_id: str) -> bool:
        job = self.get_knowledge_job(job_id)
        return bool(job.get("cancel_requested")) or job["status"] == "cancelled"

    def update_knowledge_job_item(
        self,
        job_id: str,
        source_version_id: str,
        *,
        status: str | None = None,
        run_id: str | None = None,
        asset_version_id: str | None = None,
        dataflow_task_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        job = self.get_knowledge_job(job_id)
        with self.connect() as connection:
            row = connection.execute(
                """SELECT * FROM knowledge_job_items
                   WHERE job_id = ? AND source_version_id = ?""",
                (job_id, source_version_id),
            ).fetchone()
            if not row:
                raise NotFoundError(
                    f"Knowledge job item not found: {job_id}/{source_version_id}"
                )
            current = dict(row)
            next_status = status or current["status"]
            if job["status"] == "cancelled" and next_status not in {"failed", "cancelled"}:
                next_status = "cancelled"
            started_at = current.get("started_at")
            completed_at = current.get("completed_at")
            if next_status == "running" and not started_at:
                started_at = utc_now()
            if next_status in {"completed", "failed", "cancelled"}:
                completed_at = utc_now()
            connection.execute(
                """UPDATE knowledge_job_items SET status = ?, run_id = ?, asset_version_id = ?,
                   dataflow_task_id = ?, error = ?, started_at = ?, completed_at = ?
                   WHERE job_id = ? AND source_version_id = ?""",
                (
                    next_status,
                    run_id or current.get("run_id"),
                    asset_version_id or current.get("asset_version_id"),
                    dataflow_task_id or current.get("dataflow_task_id"),
                    error,
                    started_at,
                    completed_at,
                    job_id,
                    source_version_id,
                ),
            )
            updated = connection.execute(
                """SELECT * FROM knowledge_job_items
                   WHERE job_id = ? AND source_version_id = ?""",
                (job_id, source_version_id),
            ).fetchone()
        return dict(updated) if updated else {}

    def list_knowledge_job_items(self, job_id: str) -> list[dict[str, Any]]:
        self.get_knowledge_job(job_id)
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT i.*, s.name AS source_name, sv.original_filename,
                          sv.version_no AS source_version_no
                   FROM knowledge_job_items i
                   JOIN source_versions sv ON sv.id = i.source_version_id
                   JOIN sources s ON s.id = sv.source_id
                   WHERE i.job_id = ? ORDER BY i.started_at, i.source_version_id""",
                (job_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_knowledge_job_event(
        self,
        job_id: str,
        event_type: str,
        message: str,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id = new_id("kjevt")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute(
                "SELECT 1 FROM knowledge_jobs WHERE id = ?", (job_id,)
            ).fetchone():
                raise NotFoundError(f"Knowledge job not found: {job_id}")
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM knowledge_job_events WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO knowledge_job_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    job_id,
                    sequence,
                    event_type,
                    message,
                    _json(detail or {}),
                    utc_now(),
                ),
            )
            row = connection.execute(
                "SELECT * FROM knowledge_job_events WHERE id = ?", (event_id,)
            ).fetchone()
        return _decode_row(row) or {}

    def list_knowledge_job_events(self, job_id: str) -> list[dict[str, Any]]:
        self.get_knowledge_job(job_id)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_job_events WHERE job_id = ? ORDER BY sequence",
                (job_id,),
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def recover_interrupted_knowledge_jobs(self) -> list[str]:
        """Fail attempts that could only belong to a previous app process."""
        now = utc_now()
        reason = "服务进程在任务完成前退出，请创建新的重试尝试"
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT id FROM knowledge_jobs WHERE status IN ('pending', 'running')"
            ).fetchall()
            job_ids = [row["id"] for row in rows]
            if not job_ids:
                return []
            placeholders = ",".join("?" for _ in job_ids)
            connection.execute(
                f"""UPDATE knowledge_jobs SET status = 'failed', error = ?, completed_at = ?
                    WHERE id IN ({placeholders})""",
                (reason, now, *job_ids),
            )
            connection.execute(
                f"""UPDATE knowledge_job_items SET status = 'failed', error = ?, completed_at = ?
                    WHERE job_id IN ({placeholders}) AND status IN ('pending', 'running')""",
                (reason, now, *job_ids),
            )
            for job_id in job_ids:
                sequence = connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM knowledge_job_events WHERE job_id = ?",
                    (job_id,),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO knowledge_job_events VALUES (?, ?, ?, 'recovered', ?, '{}', ?)",
                    (new_id("kjevt"), job_id, sequence, reason, now),
                )
        return job_ids

    def get_knowledge_job(self, job_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM knowledge_jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Knowledge job not found: {job_id}")
        return _decode_row(row) or {}

    def list_knowledge_jobs(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT j.*, k.name AS knowledge_type_name, p.name AS standard_pipeline_name,
                          p.engine AS standard_pipeline_engine, p.pipeline_ref,
                          p.version AS standard_pipeline_version
                   FROM knowledge_jobs j
                   JOIN knowledge_types k ON k.id = j.knowledge_type_id
                   JOIN standard_pipelines p ON p.id = j.standard_pipeline_id
                   ORDER BY j.created_at DESC"""
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def list_knowledge_job_executions(self, knowledge_base_id: str | None) -> list[dict[str, Any]]:
        if not knowledge_base_id:
            return []
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT kr.source_version_id, kr.run_id, kr.asset_version_id,
                          COUNT(*) AS record_count, MIN(kr.source_locator_json) AS locator_json,
                          r.engine
                   FROM knowledge_records kr
                   LEFT JOIN runs r ON r.id = kr.run_id
                   WHERE kr.knowledge_base_id = ?
                   GROUP BY kr.source_version_id, kr.run_id, kr.asset_version_id, r.engine
                   ORDER BY MIN(kr.record_index)""",
                (knowledge_base_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            locator = json.loads(item.pop("locator_json") or "{}")
            item["dataflow_task_id"] = locator.get("dataflow_task_id")
            result.append(item)
        return result

    def create_knowledge_base(
        self,
        name: str,
        knowledge_type_id: str,
        standard_pipeline_id: str,
        job_id: str,
        records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        base_id = new_id("kb")
        now = utc_now()
        with self.connect() as connection:
            # Serialize the final cancellation check and publication so a job
            # cannot become cancelled while its knowledge base is committed.
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                "SELECT status, cancel_requested FROM knowledge_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if not job:
                raise NotFoundError(f"Knowledge job not found: {job_id}")
            if job["status"] != "running" or job["cancel_requested"]:
                raise ValidationError("任务已取消或不再处于可发布状态")
            connection.execute(
                "INSERT INTO knowledge_bases VALUES (?, ?, ?, ?, ?, ?, 'available', ?)",
                (base_id, name, knowledge_type_id, standard_pipeline_id, job_id, len(records), now),
            )
            for index, record in enumerate(records):
                connection.execute(
                    """INSERT INTO knowledge_records
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        new_id("krec"),
                        base_id,
                        index,
                        record["source_version_id"],
                        record.get("run_id"),
                        record.get("asset_version_id"),
                        _json(record.get("source_locator", {})),
                        _json(record["data"]),
                        now,
                    ),
                )
            connection.execute(
                """UPDATE knowledge_jobs SET status = 'completed', progress = 100,
                   knowledge_base_id = ?, completed_at = ? WHERE id = ?""",
                (base_id, now, job_id),
            )
        return self.get_knowledge_base(base_id)

    def get_knowledge_base(self, base_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT b.*, k.name AS knowledge_type_name, p.name AS standard_pipeline_name
                   FROM knowledge_bases b
                   JOIN knowledge_types k ON k.id = b.knowledge_type_id
                   JOIN standard_pipelines p ON p.id = b.standard_pipeline_id
                   WHERE b.id = ?""",
                (base_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Knowledge base not found: {base_id}")
        return _decode_row(row) or {}

    def list_knowledge_bases(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT b.*, k.name AS knowledge_type_name, p.name AS standard_pipeline_name
                   FROM knowledge_bases b
                   JOIN knowledge_types k ON k.id = b.knowledge_type_id
                   JOIN standard_pipelines p ON p.id = b.standard_pipeline_id
                   ORDER BY b.created_at DESC"""
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def list_knowledge_records(
        self, base_id: str, limit: int = 50, offset: int = 0, query: str = ""
    ) -> list[dict[str, Any]]:
        self.get_knowledge_base(base_id)
        where = "r.knowledge_base_id = ?"
        params: list[Any] = [base_id]
        if query.strip():
            where += " AND (r.data_json LIKE ? OR s.name LIKE ? OR sv.original_filename LIKE ?)"
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern, pattern])
        params.extend([max(1, min(limit, 200)), max(0, offset)])
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT r.*, s.name AS source_name, sv.original_filename, sv.version_no AS source_version_no
                   FROM knowledge_records r
                   JOIN source_versions sv ON sv.id = r.source_version_id
                   JOIN sources s ON s.id = sv.source_id
                   WHERE """ + where + " ORDER BY r.record_index LIMIT ? OFFSET ?",
                tuple(params),
            ).fetchall()
        return [_decode_row(row) or {} for row in rows]

    def count_knowledge_records(self, base_id: str, query: str = "") -> int:
        self.get_knowledge_base(base_id)
        where = "r.knowledge_base_id = ?"
        params: list[Any] = [base_id]
        if query.strip():
            where += " AND (r.data_json LIKE ? OR s.name LIKE ? OR sv.original_filename LIKE ?)"
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern, pattern])
        with self.connect() as connection:
            return int(
                connection.execute(
                    """SELECT COUNT(*) FROM knowledge_records r
                       JOIN source_versions sv ON sv.id = r.source_version_id
                       JOIN sources s ON s.id = sv.source_id
                       WHERE """ + where,
                    tuple(params),
                ).fetchone()[0]
            )

    def get_knowledge_record_lineage(self, record_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT r.*, b.name AS knowledge_base_name, k.name AS knowledge_type_name,
                          p.name AS standard_pipeline_name, s.name AS source_name,
                          sv.original_filename, sv.version_no AS source_version_no
                   FROM knowledge_records r
                   JOIN knowledge_bases b ON b.id = r.knowledge_base_id
                   JOIN knowledge_types k ON k.id = b.knowledge_type_id
                   JOIN standard_pipelines p ON p.id = b.standard_pipeline_id
                   JOIN source_versions sv ON sv.id = r.source_version_id
                   JOIN sources s ON s.id = sv.source_id
                   WHERE r.id = ?""",
                (record_id,),
            ).fetchone()
        if not row:
            raise NotFoundError(f"Knowledge record not found: {record_id}")
        return _decode_row(row) or {}
