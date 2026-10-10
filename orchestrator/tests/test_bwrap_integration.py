from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.adapters.claude_cli import ClaudeCLI, _system_mount_arguments
from orchestrator.adapters.codex_cli import CodexCLI
from orchestrator.adapters.results import CLIResult

FIXTURES = Path(__file__).parent / "fixtures"
PROBE_CLI = FIXTURES / "bwrap_probe_cli.py"
BWRAP = Path("/usr/bin/bwrap")
OPT_IN_VARIABLE = "KERNELCANVAS_RUN_BWRAP_INTEGRATION"


class RealBubblewrapIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get(OPT_IN_VARIABLE) != "1":
            raise unittest.SkipTest(
                f"real Bubblewrap tests are opt-in; set {OPT_IN_VARIABLE}=1"
            )
        if not BWRAP.is_file() or not os.access(BWRAP, os.X_OK):
            raise unittest.SkipTest(
                "real Bubblewrap unavailable: /usr/bin/bwrap is missing"
            )

        probe = subprocess.run(
            [
                str(BWRAP),
                "--die-with-parent",
                "--new-session",
                "--unshare-pid",
                *_system_mount_arguments(),
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                "--",
                "/usr/bin/true",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        if probe.returncode != 0:
            reason = probe.stderr.strip() or "no diagnostic from /usr/bin/bwrap"
            raise unittest.SkipTest(
                f"real Bubblewrap cannot establish a sandbox on this host: {reason}"
            )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        (self.workspace / "visible.txt").write_text(
            "workspace-visible", encoding="utf-8"
        )
        self.probe_cli = self.workspace / "bwrap_probe_cli.py"
        shutil.copyfile(PROBE_CLI, self.probe_cli)
        self.probe_cli.chmod(0o700)

    def adapter(self) -> ClaudeCLI:
        return ClaudeCLI(
            self.workspace,
            executable=str(self.probe_cli),
            sandbox_executable=str(BWRAP),
        )

    def codex_adapter(self) -> CodexCLI:
        return CodexCLI(
            self.workspace,
            executable=str(self.probe_cli),
            sandbox_executable=str(BWRAP),
        )

    def test_workspace_is_read_only_and_unrelated_file_is_inaccessible(self) -> None:
        outside = self.base / "outside-secret.txt"
        outside.write_text("must not be visible", encoding="utf-8")
        result = self.adapter().review(
            json.dumps({"outside_path": str(outside)}),
            cwd=self.workspace,
            timeout_seconds=10,
            log_dir=self.base / "logs",
        )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertTrue(
            result.succeeded, result.stderr_path.read_text(encoding="utf-8")
        )
        self.assertEqual("workspace-visible", result.parsed["visible"])
        self.assertTrue(result.parsed["write_denied"])
        self.assertTrue(result.parsed["outside_inaccessible"])
        self.assertEqual("/workspace", result.parsed["cwd"])
        self.assertFalse((self.workspace / "forbidden-write.txt").exists())

    def test_codex_approved_worktree_write_succeeds(self) -> None:
        outside = self.base / "outside-secret.txt"
        outside.write_text("must not be visible", encoding="utf-8")
        result = self.codex_adapter().implement(
            json.dumps(
                {
                    "outside_path": str(outside),
                    "write_name": "approved-write.txt",
                }
            ),
            worktree=self.workspace,
            timeout_seconds=10,
            log_dir=self.base / "codex-write-logs",
        )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertTrue(
            result.succeeded, result.stderr_path.read_text(encoding="utf-8")
        )
        assert isinstance(result.parsed, list)
        probe = result.parsed[0]
        assert isinstance(probe, dict)
        self.assertTrue(probe["write_succeeded"])
        self.assertEqual("/workspace", probe["cwd"])
        self.assertEqual(
            "sandbox-write",
            (self.workspace / "approved-write.txt").read_text(encoding="utf-8"),
        )

    def test_codex_unrelated_host_file_is_inaccessible(self) -> None:
        unrelated = self.base / "unrelated-repository" / "private.txt"
        unrelated.parent.mkdir()
        unrelated.write_text("host-private", encoding="utf-8")
        result = self.codex_adapter().implement(
            json.dumps(
                {
                    "outside_path": str(unrelated),
                    "write_name": "approved-write.txt",
                }
            ),
            worktree=self.workspace,
            timeout_seconds=10,
            log_dir=self.base / "codex-unrelated-logs",
        )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertTrue(
            result.succeeded, result.stderr_path.read_text(encoding="utf-8")
        )
        assert isinstance(result.parsed, list)
        probe = result.parsed[0]
        assert isinstance(probe, dict)
        self.assertTrue(probe["outside_inaccessible"])

    def test_codex_path_outside_approved_mounts_is_denied(self) -> None:
        denied = self.base / "personal-credentials" / "auth.json"
        denied.parent.mkdir()
        denied.write_text('{"token":"must-not-leak"}', encoding="utf-8")
        (self.workspace / "credential-escape").symlink_to(denied)
        result = self.codex_adapter().implement(
            json.dumps(
                {
                    "outside_path": "/workspace/credential-escape",
                    "write_name": "approved-write.txt",
                }
            ),
            worktree=self.workspace,
            timeout_seconds=10,
            log_dir=self.base / "codex-denied-logs",
        )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertTrue(
            result.succeeded, result.stderr_path.read_text(encoding="utf-8")
        )
        assert isinstance(result.parsed, list)
        probe = result.parsed[0]
        assert isinstance(probe, dict)
        self.assertTrue(probe["outside_inaccessible"])

    def test_real_bwrap_startup_failure_is_reported_as_failure(self) -> None:
        with patch(
            "orchestrator.adapters.claude_cli._system_mount_arguments",
            return_value=("--ro-bind", "/kernelcanvas-does-not-exist", "/usr"),
        ):
            result = self.adapter().review(
                "{}",
                cwd=self.workspace,
                timeout_seconds=10,
                log_dir=self.base / "failure-logs",
            )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertNotEqual(0, result.exit_code)
        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.parse_error)

    def test_codex_real_bwrap_startup_failure_is_not_bypassed(self) -> None:
        with patch(
            "orchestrator.adapters.codex_cli._system_mount_arguments",
            return_value=("--ro-bind", "/kernelcanvas-does-not-exist", "/usr"),
        ):
            result = self.codex_adapter().implement(
                "{}",
                worktree=self.workspace,
                timeout_seconds=10,
                log_dir=self.base / "codex-failure-logs",
            )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertNotEqual(0, result.exit_code)
        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.parse_error)


if __name__ == "__main__":
    unittest.main()
