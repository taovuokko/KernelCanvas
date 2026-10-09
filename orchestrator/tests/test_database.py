from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import CURRENT_SCHEMA_VERSION
from orchestrator.database import (
    check_schema_version,
    connect,
    init_schema,
    resolve_db_path,
)
from orchestrator.models import SchemaVersionError


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db_path = Path(self.temporary.name) / "state.sqlite3"

    def test_init_creates_versioned_schema_and_is_idempotent(self) -> None:
        connection = connect(self.db_path)
        self.addCleanup(connection.close)

        init_schema(connection)
        init_schema(connection)

        version = connection.execute("SELECT version FROM schema_meta").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        self.assertEqual(CURRENT_SCHEMA_VERSION, version)
        self.assertTrue({"tasks", "leases", "attempts", "events"} <= tables)
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM schema_meta").fetchone()[0])

    def test_connection_pragmas_are_applied(self) -> None:
        connection = connect(self.db_path)
        self.addCleanup(connection.close)
        self.assertEqual(1, connection.execute("PRAGMA foreign_keys").fetchone()[0])
        self.assertEqual(5000, connection.execute("PRAGMA busy_timeout").fetchone()[0])
        self.assertEqual("wal", connection.execute("PRAGMA journal_mode").fetchone()[0])

    def test_schema_mismatch_fails_without_repair(self) -> None:
        connection = connect(self.db_path)
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE schema_meta(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_meta VALUES (99)")

        with self.assertRaises(SchemaVersionError):
            check_schema_version(connection)

        self.assertEqual(99, connection.execute("SELECT version FROM schema_meta").fetchone()[0])

    def test_malformed_schema_version_fails_clearly(self) -> None:
        connection = connect(self.db_path)
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE schema_meta(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_meta VALUES ('invalid')")

        with self.assertRaisesRegex(SchemaVersionError, "valid integer"):
            check_schema_version(connection)

    def test_missing_schema_fails_clearly(self) -> None:
        connection = connect(self.db_path)
        self.addCleanup(connection.close)
        with self.assertRaisesRegex(SchemaVersionError, "schema version"):
            check_schema_version(connection)

    def test_environment_override_wins(self) -> None:
        override = str(self.db_path)
        with patch.dict(os.environ, {"KERNELCANVAS_ORCHESTRATOR_DB": override}):
            self.assertEqual(self.db_path, resolve_db_path())

    def test_xdg_default_is_used_without_override(self) -> None:
        xdg = Path(self.temporary.name) / "xdg"
        with patch.dict(
            os.environ,
            {"XDG_STATE_HOME": str(xdg)},
            clear=True,
        ):
            self.assertEqual(
                xdg / "kernelcanvas" / "orchestrator.sqlite3", resolve_db_path()
            )


if __name__ == "__main__":
    unittest.main()

