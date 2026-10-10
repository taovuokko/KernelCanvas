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
NODE = Path("/usr/bin/node")
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

    def test_crypto_policy_symlink_and_target_are_available_to_both_clis(self) -> None:
        config = "/etc/crypto-policies/back-ends/opensslcnf.config"
        expected_target = str(Path(config).resolve(strict=True))
        cases = (
            (
                "claude",
                lambda: self.adapter().review(
                    json.dumps(
                        {
                            "outside_path": str(self.base / "not-mounted"),
                            "crypto_policy_path": config,
                        }
                    ),
                    cwd=self.workspace,
                    timeout_seconds=10,
                    log_dir=self.base / "claude-crypto-policy-logs",
                ),
            ),
            (
                "codex",
                lambda: self.codex_adapter().implement(
                    json.dumps(
                        {
                            "outside_path": str(self.base / "not-mounted"),
                            "crypto_policy_path": config,
                        }
                    ),
                    worktree=self.workspace,
                    timeout_seconds=10,
                    log_dir=self.base / "codex-crypto-policy-logs",
                ),
            ),
        )
        for provider, invoke in cases:
            with self.subTest(provider=provider):
                result = invoke()
                self.assertTrue(result.succeeded, result.parse_error)
                probe = result.parsed
                if provider == "codex":
                    assert isinstance(probe, list)
                    probe = probe[0]
                assert isinstance(probe, dict)
                self.assertTrue(probe["crypto_policy_is_symlink"])
                self.assertTrue(probe["crypto_policy_readable"])
                self.assertEqual(expected_target, probe["crypto_policy_target"])

    def test_fedora_node_starts_with_crypto_policy_inside_bubblewrap(self) -> None:
        if not NODE.is_file() or not os.access(NODE, os.X_OK):
            self.skipTest("Fedora Node.js unavailable: /usr/bin/node is missing")
        config = "/etc/crypto-policies/back-ends/opensslcnf.config"
        result = subprocess.run(
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
                str(NODE),
                "-e",
                (
                    'const fs=require("fs");'
                    f'const p="{config}";'
                    "console.log(fs.realpathSync(p));"
                    "fs.accessSync(p,fs.constants.R_OK);"
                ),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            str(Path(config).resolve(strict=True)), result.stdout.strip()
        )

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

    def test_explicit_profiles_are_visible_and_writable_for_cli_refresh(self) -> None:
        auth_root = self.base / "kernelcanvas-auth"
        cases = (
            ("claude", "CLAUDE_CONFIG_DIR", "/home/kernelcanvas/.claude"),
            ("codex", "CODEX_HOME", "/home/kernelcanvas/.codex"),
        )
        for provider, variable, sandbox_profile in cases:
            with self.subTest(provider=provider):
                profile = auth_root / provider / "supervised"
                profile.mkdir(parents=True)
                (profile / "profile-marker.txt").write_text(
                    "dedicated-profile", encoding="utf-8"
                )
                for directory in (auth_root, profile.parent, profile):
                    directory.chmod(0o700)
                with patch(
                    "orchestrator.adapters.auth.dedicated_auth_root",
                    return_value=auth_root,
                ):
                    if provider == "claude":
                        result = ClaudeCLI(
                            self.workspace,
                            executable=str(self.probe_cli),
                            sandbox_executable=str(BWRAP),
                            auth_profile=profile,
                        ).review(
                            json.dumps(
                                {
                                    "outside_path": str(self.base / "not-mounted"),
                                    "profile_environment": variable,
                                }
                            ),
                            cwd=self.workspace,
                            timeout_seconds=10,
                            log_dir=self.base / "claude-auth-logs",
                        )
                        probe = result.parsed
                    else:
                        result = CodexCLI(
                            self.workspace,
                            executable=str(self.probe_cli),
                            sandbox_executable=str(BWRAP),
                            auth_profile=profile,
                        ).implement(
                            json.dumps(
                                {
                                    "outside_path": str(self.base / "not-mounted"),
                                    "profile_environment": variable,
                                }
                            ),
                            worktree=self.workspace,
                            timeout_seconds=10,
                            log_dir=self.base / "codex-auth-logs",
                        )
                        assert isinstance(result.parsed, list)
                        probe = result.parsed[0]
                self.assertTrue(result.succeeded, result.parse_error)
                assert isinstance(probe, dict)
                self.assertEqual(sandbox_profile, probe["profile_directory"])
                self.assertEqual("dedicated-profile", probe["profile_read"])
                self.assertTrue(probe["profile_refresh_succeeded"])
                self.assertEqual(
                    "refreshed",
                    (profile / "refresh-marker.txt").read_text(encoding="utf-8"),
                )

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
