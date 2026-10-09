"""SQLite connection and schema management."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import CURRENT_SCHEMA_VERSION
from .models import SchemaVersionError


def resolve_db_path() -> Path:
    override = os.environ.get("KERNELCANVAS_ORCHESTRATOR_DB")
    if override:
        return Path(override).expanduser()

    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "kernelcanvas" / "orchestrator.sqlite3"


def connect(path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_schema(connection: sqlite3.Connection) -> None:
    """Initialize schema v1, or validate an already initialized database."""
    existing = _schema_versions(connection)
    if existing:
        _require_current_version(existing)

    connection.executescript(
        f"""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS schema_meta (
            version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            task_file TEXT NOT NULL,
            issue_url TEXT NOT NULL,
            state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS leases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            owner TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            lease_token TEXT NOT NULL UNIQUE,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            heartbeat_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RELEASED'))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_leases_one_active
            ON leases(task_id) WHERE status = 'ACTIVE';

        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            attempt_number INTEGER NOT NULL,
            worker TEXT NOT NULL,
            phase TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            outcome TEXT,
            log_location TEXT,
            UNIQUE(task_id, attempt_number)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            actor TEXT NOT NULL,
            prior_state TEXT NOT NULL,
            next_state TEXT NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TRIGGER IF NOT EXISTS events_are_append_only_update
        BEFORE UPDATE ON events
        BEGIN
            SELECT RAISE(ABORT, 'events are append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS events_are_append_only_delete
        BEFORE DELETE ON events
        BEGIN
            SELECT RAISE(ABORT, 'events are append-only');
        END;

        INSERT INTO schema_meta(version)
        SELECT {CURRENT_SCHEMA_VERSION}
        WHERE NOT EXISTS (SELECT 1 FROM schema_meta);
        COMMIT;
        """
    )
    check_schema_version(connection)


def check_schema_version(connection: sqlite3.Connection) -> None:
    try:
        versions = _schema_versions(connection)
    except sqlite3.OperationalError as error:
        raise SchemaVersionError(
            "database is not initialized; run 'python3 -m orchestrator init'"
        ) from error
    _require_current_version(versions)


def _schema_versions(connection: sqlite3.Connection) -> list[int]:
    try:
        rows = connection.execute("SELECT version FROM schema_meta").fetchall()
    except sqlite3.OperationalError as error:
        if "no such table" in str(error).lower():
            return []
        raise
    try:
        return [int(row["version"]) for row in rows]
    except (TypeError, ValueError) as error:
        raise SchemaVersionError("schema version is not a valid integer") from error


def _require_current_version(versions: list[int]) -> None:
    if len(versions) != 1:
        found = "none" if not versions else ", ".join(str(value) for value in versions)
        raise SchemaVersionError(
            f"expected exactly one schema version row; found {found}"
        )
    if versions[0] != CURRENT_SCHEMA_VERSION:
        raise SchemaVersionError(
            f"unsupported schema version {versions[0]}; expected {CURRENT_SCHEMA_VERSION}"
        )

