from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.cli import ExitCode, main


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.db_path = self.base / "state" / "orchestrator.sqlite3"
        self.task_file = self.base / "task.md"
        self.task_file.write_text("# task\n", encoding="utf-8")
        self.environment = patch.dict(
            os.environ, {"KERNELCANVAS_ORCHESTRATOR_DB": str(self.db_path)}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def run_cli(self, *arguments: str):
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = main(arguments, stdout=stdout, stderr=stderr)
        return code, stdout.getvalue(), stderr.getvalue()

    def init_and_add(self) -> None:
        self.assertEqual(ExitCode.SUCCESS, self.run_cli("init")[0])
        self.assertEqual(
            ExitCode.SUCCESS,
            self.run_cli(
                "add",
                "KC-104",
                "--task-file",
                str(self.task_file),
                "--issue-url",
                "https://github.com/example/repo/issues/104",
            )[0],
        )

    def test_real_module_help_entry_point(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "orchestrator", "--help"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("local development-task scheduler", result.stdout)

    def test_missing_database_does_not_create_file(self) -> None:
        code, _, stderr = self.run_cli("status")
        self.assertEqual(ExitCode.NOT_FOUND, code)
        self.assertIn("database not found", stderr)
        self.assertFalse(self.db_path.exists())

    def test_command_lifecycle_and_human_readable_output(self) -> None:
        self.init_and_add()
        code, output, _ = self.run_cli("status", "KC-104")
        self.assertEqual(ExitCode.SUCCESS, code)
        self.assertIn("state=QUEUED", output)
        self.assertIn("owner=-", output)

        code, output, _ = self.run_cli(
            "claim",
            "KC-104",
            "--worker",
            "worker",
            "--reviewer",
            "reviewer",
            "--lease-seconds",
            "60",
        )
        self.assertEqual(ExitCode.SUCCESS, code)
        self.assertIn("owner=worker reviewer=reviewer", output)

        self.assertEqual(
            ExitCode.SUCCESS,
            self.run_cli("heartbeat", "KC-104", "--worker", "worker")[0],
        )
        code, output, _ = self.run_cli(
            "release",
            "KC-104",
            "--worker",
            "worker",
            "--to",
            "REVIEW",
            "--reason",
            "ready",
        )
        self.assertEqual(ExitCode.SUCCESS, code)
        self.assertIn("state=REVIEW", output)

        code, history, _ = self.run_cli("history", "KC-104")
        self.assertEqual(ExitCode.SUCCESS, code)
        self.assertIn("QUEUED->CLAIMED", history)
        self.assertIn("CLAIMED->REVIEW", history)

    def test_typed_failures_map_to_stable_exit_codes(self) -> None:
        self.init_and_add()
        duplicate = self.run_cli(
            "add",
            "KC-104",
            "--task-file",
            str(self.task_file),
            "--issue-url",
            "https://github.com/example/repo/issues/104",
        )
        self.assertEqual(ExitCode.INVALID_INPUT, duplicate[0])
        self.assertEqual(ExitCode.NOT_FOUND, self.run_cli("status", "KC-404")[0])
        self.assertEqual(
            ExitCode.INVALID_INPUT,
            self.run_cli(
                "claim",
                "KC-104",
                "--worker",
                "same",
                "--reviewer",
                "same",
                "--lease-seconds",
                "60",
            )[0],
        )

        self.assertEqual(
            ExitCode.SUCCESS,
            self.run_cli(
                "claim",
                "KC-104",
                "--worker",
                "worker",
                "--reviewer",
                "reviewer",
                "--lease-seconds",
                "60",
            )[0],
        )
        self.assertEqual(
            ExitCode.INVALID_TRANSITION,
            self.run_cli(
                "claim",
                "KC-104",
                "--worker",
                "other",
                "--reviewer",
                "other-reviewer",
                "--lease-seconds",
                "60",
            )[0],
        )
        self.assertEqual(
            ExitCode.LEASE_ERROR,
            self.run_cli("heartbeat", "KC-104", "--worker", "intruder")[0],
        )

    def test_unsupported_schema_maps_to_database_error(self) -> None:
        self.db_path.parent.mkdir(parents=True)
        import sqlite3

        connection = sqlite3.connect(self.db_path)
        connection.execute("CREATE TABLE schema_meta(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_meta VALUES (99)")
        connection.commit()
        connection.close()
        code, _, stderr = self.run_cli("status")
        self.assertEqual(ExitCode.DATABASE_ERROR, code)
        self.assertIn("unsupported schema version", stderr)


if __name__ == "__main__":
    unittest.main()
