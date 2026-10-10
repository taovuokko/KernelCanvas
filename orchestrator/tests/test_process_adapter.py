from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.adapters.process import (
    ProcessRunner,
    build_safe_environment,
    redact_text,
    resolve_executable,
)
from orchestrator.adapters.results import ExecutableNotFoundError, InvocationError


FIXTURES = Path(__file__).parent / "fixtures"
FAKE_CLI = FIXTURES / "fake_model_cli.py"


class ProcessRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.cwd = self.base / "worktree"
        self.cwd.mkdir()

    def environment(self, **extra: str) -> dict[str, str]:
        return build_safe_environment(extra)

    def test_exact_cwd_stdin_and_environment_are_used(self) -> None:
        record = self.base / "record.json"
        output = ProcessRunner().run(
            [str(FAKE_CLI), "one", "two"],
            cwd=self.cwd,
            environment=self.environment(KC_FAKE_RECORD=str(record)),
            stdin_text="assignment text",
            timeout_seconds=2,
            log_dir=self.base / "logs",
        )
        recorded = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(["one", "two"], recorded["argv"])
        self.assertEqual(str(self.cwd), recorded["cwd"])
        self.assertEqual("assignment text", recorded["stdin"])
        self.assertEqual(0, output.exit_code)
        self.assertFalse(output.timed_out)
        self.assertNotIn("GITHUB_TOKEN", recorded["environment_keys"])

    def test_output_is_bounded_while_streaming(self) -> None:
        output = ProcessRunner(max_output_bytes=1024).run(
            [str(FAKE_CLI)],
            cwd=self.cwd,
            environment=self.environment(KC_FAKE_MODE="large"),
            stdin_text="",
            timeout_seconds=2,
            log_dir=self.base / "large-logs",
        )
        self.assertTrue(output.stdout_truncated)
        self.assertTrue(output.stderr_truncated)
        self.assertLess(output.stdout_path.stat().st_size, 1100)
        self.assertLess(output.stderr_path.stat().st_size, 1100)
        self.assertIn("[output truncated]", output.stdout_path.read_text(encoding="utf-8"))
        self.assertEqual(0o600, output.stdout_path.stat().st_mode & 0o777)
        self.assertEqual(0o600, output.stderr_path.stat().st_mode & 0o777)
        self.assertEqual(0o700, output.stdout_path.parent.stat().st_mode & 0o777)

    def test_timeout_terminates_the_owned_process_group(self) -> None:
        child_pid_path = self.base / "child.pid"
        output = ProcessRunner(terminate_grace_seconds=0.05).run(
            [str(FAKE_CLI)],
            cwd=self.cwd,
            environment=self.environment(
                KC_FAKE_MODE="timeout-child",
                KC_FAKE_CHILD_PID=str(child_pid_path),
            ),
            stdin_text="",
            timeout_seconds=0.2,
            log_dir=self.base / "timeout-logs",
        )
        self.assertTrue(output.timed_out)
        self.assertNotEqual(0, output.exit_code)
        child_pid = int(child_pid_path.read_text(encoding="ascii"))
        for _ in range(100):
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            self.fail("child process remained alive after process-group cancellation")

    def test_logs_are_redacted_before_writing(self) -> None:
        output = ProcessRunner().run(
            [str(FAKE_CLI)],
            cwd=self.cwd,
            environment=self.environment(KC_FAKE_MODE="secret"),
            stdin_text="",
            timeout_seconds=2,
            log_dir=self.base / "secret-logs",
        )
        logs = output.stdout_path.read_text() + output.stderr_path.read_text()
        self.assertNotIn("very-secret-value", logs)
        self.assertNotIn("private-password", logs)
        self.assertIn("[redacted]", logs)

    def test_json_formatted_token_fields_are_redacted(self) -> None:
        source = (
            '{"access_token":"alpha", "refresh_token": "bravo", '
            '"nested":{"api_key":"charlie"}, "ordinary":"visible"}'
        )
        redacted = redact_text(source)
        for secret in ("alpha", "bravo", "charlie"):
            self.assertNotIn(secret, redacted)
        self.assertIn('"ordinary":"visible"', redacted)
        self.assertEqual(3, redacted.count('"[redacted]"'))

    def test_environment_rejects_credentials_and_does_not_inherit_them(self) -> None:
        environment = build_safe_environment(
            source={"PATH": os.defpath, "GITHUB_TOKEN": "secret", "HOME": "/tmp"}
        )
        self.assertNotIn("GITHUB_TOKEN", environment)
        with self.assertRaises(InvocationError):
            build_safe_environment({"GH_TOKEN": "secret"})

    def test_missing_executable_is_typed(self) -> None:
        with self.assertRaises(ExecutableNotFoundError):
            resolve_executable("kernelcanvas-definitely-missing", {"PATH": os.defpath})

    def test_oversized_stdin_is_rejected_before_launch(self) -> None:
        with patch("orchestrator.adapters.process.subprocess.Popen") as popen:
            with self.assertRaisesRegex(InvocationError, "stdin exceeds"):
                ProcessRunner(max_stdin_bytes=3).run(
                    [str(FAKE_CLI)],
                    cwd=self.cwd,
                    environment=self.environment(),
                    stdin_text="four",
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        popen.assert_not_called()

    def test_nul_in_argv_is_rejected_before_launch(self) -> None:
        with patch("orchestrator.adapters.process.subprocess.Popen") as popen:
            with self.assertRaisesRegex(InvocationError, "no NUL"):
                ProcessRunner().run(
                    [str(FAKE_CLI), "bad\x00argument"],
                    cwd=self.cwd,
                    environment=self.environment(),
                    stdin_text="",
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        popen.assert_not_called()

    def test_symlinked_log_directory_parent_is_rejected_before_launch(self) -> None:
        real_parent = self.base / "real-logs"
        real_parent.mkdir()
        symlinked_parent = self.base / "linked-logs"
        symlinked_parent.symlink_to(real_parent, target_is_directory=True)
        with patch("orchestrator.adapters.process.subprocess.Popen") as popen:
            with self.assertRaisesRegex(InvocationError, "unsafe component"):
                ProcessRunner().run(
                    [str(FAKE_CLI)],
                    cwd=self.cwd,
                    environment=self.environment(),
                    stdin_text="",
                    timeout_seconds=2,
                    log_dir=symlinked_parent / "attempt",
                )
        popen.assert_not_called()

    def test_symlinked_final_log_file_is_rejected_without_overwrite(self) -> None:
        log_dir = self.base / "logs"
        log_dir.mkdir()
        outside = self.base / "outside.log"
        outside.write_text("preserve me", encoding="utf-8")
        (log_dir / "stdout.log").symlink_to(outside)
        with self.assertRaisesRegex(InvocationError, "could not write bounded log"):
            ProcessRunner().run(
                [str(FAKE_CLI)],
                cwd=self.cwd,
                environment=self.environment(),
                stdin_text="",
                timeout_seconds=2,
                log_dir=log_dir,
            )
        self.assertEqual("preserve me", outside.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
