from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import scheduler
from orchestrator.cli import ExitCode, build_parser, main
from orchestrator.database import connect
from orchestrator.models import TaskState


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

    def test_argparse_usage_error_exits_with_code_2(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "orchestrator", "claim"],
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(ExitCode.USAGE, result.returncode)
        self.assertIn("usage:", result.stderr)

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

    def test_claim_unknown_task_id_returns_not_found(self) -> None:
        self.assertEqual(ExitCode.SUCCESS, self.run_cli("init")[0])
        code, _, stderr = self.run_cli(
            "claim",
            "KC-404",
            "--worker",
            "worker",
            "--reviewer",
            "reviewer",
            "--lease-seconds",
            "60",
        )
        self.assertEqual(ExitCode.NOT_FOUND, code)
        self.assertIn("task not found: KC-404", stderr)

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

    def test_run_dry_run_has_no_database_or_log_side_effects(self) -> None:
        evidence = self.base / "evidence"
        code, output, stderr = self.run_cli(
            "run",
            "KC-106",
            "--worker",
            "worker",
            "--reviewer",
            "reviewer",
            "--workspace-root",
            str(self.base),
            "--worktree",
            str(self.base / "missing-worktree"),
            "--branch",
            "agent/KC-106-autonomous-loop",
            "--evidence-root",
            str(evidence),
            "--dry-run",
        )
        self.assertEqual(ExitCode.SUCCESS, code, stderr)
        self.assertIn("corrections<=2", output)
        self.assertIn("auth-profiles=disabled", output)
        self.assertIn("credentials-agent-readable=false", output)
        self.assertFalse(self.db_path.exists())
        self.assertFalse(evidence.exists())

    def test_run_parser_exposes_explicit_auth_profiles(self) -> None:
        args = build_parser().parse_args(
            [
                "run",
                "KC-107",
                "--worker",
                "worker",
                "--reviewer",
                "reviewer",
                "--workspace-root",
                str(self.base),
                "--worktree",
                str(self.base / "worktree"),
                "--branch",
                "agent/KC-107-live-auth",
                "--evidence-root",
                str(self.base / "evidence"),
                "--codex-auth-profile",
                "/home/user/.local/share/kernelcanvas/auth/codex/supervised",
                "--claude-auth-profile",
                "/home/user/.local/share/kernelcanvas/auth/claude/supervised",
                "--acknowledge-auth-profile-exposure",
                "--authorize-real-execution",
            ]
        )
        self.assertEqual("supervised", args.codex_auth_profile.name)
        self.assertEqual("supervised", args.claude_auth_profile.name)
        self.assertTrue(args.acknowledge_auth_profile_exposure)
        self.assertTrue(args.authorize_real_execution)

    def test_auth_profile_dry_run_stays_side_effect_free_and_reports_risk(self) -> None:
        evidence = self.base / "evidence"
        code, output, stderr = self.run_cli(
            "run",
            "KC-107",
            "--worker",
            "worker",
            "--reviewer",
            "reviewer",
            "--workspace-root",
            str(self.base),
            "--worktree",
            str(self.base / "missing-worktree"),
            "--branch",
            "agent/KC-107-live-auth",
            "--evidence-root",
            str(evidence),
            "--codex-auth-profile",
            str(self.base / "missing-codex-profile"),
            "--claude-auth-profile",
            str(self.base / "missing-claude-profile"),
            "--dry-run",
        )
        self.assertEqual(ExitCode.SUCCESS, code, stderr)
        self.assertIn("auth-profiles=codex,claude", output)
        self.assertIn("credentials-agent-readable=true", output)
        self.assertFalse(self.db_path.exists())
        self.assertFalse(evidence.exists())

    def test_live_auth_profile_requires_exposure_acknowledgement(self) -> None:
        self.init_and_add()
        code, _, stderr = self.run_cli(
            "run",
            "KC-104",
            "--worker",
            "worker",
            "--reviewer",
            "reviewer",
            "--workspace-root",
            str(self.base),
            "--worktree",
            str(self.base),
            "--branch",
            "agent/KC-107-live-auth",
            "--evidence-root",
            str(self.base / "evidence"),
            "--codex-auth-profile",
            str(self.base / "profile"),
            "--authorize-real-execution",
        )
        self.assertEqual(ExitCode.INVALID_INPUT, code)
        self.assertIn("potentially readable", stderr)

    def test_attempts_command_reports_persisted_outcome_and_evidence(self) -> None:
        self.init_and_add()
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
        connection = connect(self.db_path)
        try:
            lease = scheduler.get_task(connection, "KC-104").lease
            assert lease is not None
            scheduler.transition_active_task(
                connection,
                "KC-104",
                "worker",
                lease.lease_token,
                TaskState.RUNNING,
                "start",
            )
            attempt = scheduler.start_attempt(
                connection,
                "KC-104",
                "worker",
                lease.lease_token,
                "IMPLEMENTATION",
                "/tmp/evidence/attempt-1",
            )
            scheduler.finish_attempt(
                connection,
                attempt.id,
                "KC-104",
                "worker",
                lease.lease_token,
                "APPROVED",
            )
        finally:
            connection.close()
        code, output, stderr = self.run_cli("attempts", "KC-104")
        self.assertEqual(ExitCode.SUCCESS, code, stderr)
        self.assertIn("attempt=1 phase=IMPLEMENTATION", output)
        self.assertIn("outcome=APPROVED", output)
        self.assertIn("evidence=/tmp/evidence/attempt-1", output)


if __name__ == "__main__":
    unittest.main()
