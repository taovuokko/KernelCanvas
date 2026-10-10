from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.adapters.codex_cli import CodexCLI
from orchestrator.adapters.process import ProcessRunner
from orchestrator.adapters.results import (
    CLIResult,
    ExecutableNotFoundError,
    InvocationError,
    InvocationPreview,
)

FIXTURES = Path(__file__).parent / "fixtures"
FAKE_CLI = FIXTURES / "fake_codex_cli.py"
FAKE_BWRAP = FIXTURES / "fake_bwrap.py"


class CodexCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.workspace = self.base / "workspace"
        self.worktree = self.workspace / "task-worktree"
        self.worktree.mkdir(parents=True)

    def adapter(self, **environment: str) -> CodexCLI:
        return CodexCLI(
            self.workspace,
            executable=str(FAKE_CLI),
            sandbox_executable=str(FAKE_BWRAP),
            runtime_root=FIXTURES,
            environment=environment,
        )

    def auth_profile(self) -> Path:
        auth_root = self.base / "kernelcanvas-auth"
        profile = auth_root / "codex" / "supervised"
        profile.mkdir(parents=True)
        for directory in (auth_root, profile.parent, profile):
            directory.chmod(0o700)
        return profile

    def test_implement_uses_exact_scoped_argv_cwd_and_stdin(self) -> None:
        record = self.base / "record.json"
        bwrap_record = self.base / "bwrap.json"
        adapter = self.adapter(
            KC_FAKE_RECORD=str(record),
            KC_FAKE_BWRAP_RECORD=str(bwrap_record),
        )
        with patch(
            "orchestrator.adapters.codex_cli._system_mount_arguments",
            return_value=("--ro-bind", "/approved-system", "/approved-system"),
        ):
            result = adapter.implement(
                "implement only allowed files",
                worktree=self.worktree,
                timeout_seconds=2,
                log_dir=self.base / "logs",
            )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertTrue(result.succeeded, result.parse_error)
        recorded = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual(str(self.worktree), recorded["cwd"])
        self.assertEqual("implement only allowed files", recorded["stdin"])
        self.assertEqual(
            [
                "exec",
                "--sandbox",
                "workspace-write",
                "--json",
                "-c",
                "mcp_servers={}",
                "-",
            ],
            recorded["argv"],
        )
        self.assertEqual(sorted(adapter.environment), recorded["environment_keys"])
        self.assertEqual(adapter.environment, recorded["environment"])
        sandbox_argv = json.loads(bwrap_record.read_text(encoding="utf-8"))
        self.assertNotIn("--unshare-net", sandbox_argv)
        self.assertNotIn("network_access=false", " ".join(recorded["argv"]))
        self.assertEqual(
            [
                "--die-with-parent",
                "--new-session",
                "--unshare-pid",
                "--unshare-ipc",
                "--unshare-uts",
                "--ro-bind",
                "/approved-system",
                "/approved-system",
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                "--dir",
                "/tmp/cache",
                "--dir",
                "/home",
                "--dir",
                "/home/kernelcanvas",
                "--clearenv",
                "--setenv",
                "HOME",
                "/home/kernelcanvas",
                "--setenv",
                "XDG_CONFIG_HOME",
                "/home/kernelcanvas/.config",
                "--setenv",
                "XDG_CACHE_HOME",
                "/tmp/cache",
                "--setenv",
                "TMPDIR",
                "/tmp",
                "--setenv",
                "PATH",
                "/usr/bin:/bin",
                "--setenv",
                "LANG",
                "C.UTF-8",
                "--setenv",
                "LC_ALL",
                "C.UTF-8",
                "--setenv",
                "GIT_CONFIG_GLOBAL",
                "/dev/null",
                "--setenv",
                "GIT_CONFIG_NOSYSTEM",
                "1",
                "--setenv",
                "GIT_TERMINAL_PROMPT",
                "0",
                "--bind",
                str(self.worktree),
                "/workspace",
                "--dir",
                "/run",
                "--dir",
                "/run/kernelcanvas",
                "--ro-bind",
                str(FIXTURES.resolve()),
                "/run/kernelcanvas/codex-runtime",
                "--chdir",
                "/workspace",
                "--",
                "/run/kernelcanvas/codex-runtime/fake_codex_cli.py",
                "exec",
                "--sandbox",
                "workspace-write",
                "--json",
                "-c",
                "mcp_servers={}",
                "-",
            ],
            json.loads(bwrap_record.read_text(encoding="utf-8")),
        )
        self.assertEqual(2, len(result.parsed))

    def test_worktree_outside_root_is_rejected_before_launch(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        with patch.object(ProcessRunner, "run") as run:
            with self.assertRaises(InvocationError):
                self.adapter().implement(
                    "prompt",
                    worktree=outside,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()

    def test_symlinked_worktree_escape_is_rejected_before_launch(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        escape = self.workspace / "escape"
        escape.symlink_to(outside, target_is_directory=True)
        with patch.object(ProcessRunner, "run") as run:
            with self.assertRaises(InvocationError):
                self.adapter().implement(
                    "prompt",
                    worktree=escape,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()

    def test_dry_run_has_no_process_or_file_side_effects(self) -> None:
        log_dir = self.base / "never-created"
        with patch.object(ProcessRunner, "run") as run:
            preview = self.adapter().implement(
                "password=hunter2",
                worktree=self.worktree,
                timeout_seconds=2,
                log_dir=log_dir,
                dry_run=True,
            )
        self.assertIsInstance(preview, InvocationPreview)
        assert isinstance(preview, InvocationPreview)
        run.assert_not_called()
        self.assertFalse(log_dir.exists())
        self.assertNotIn("hunter2", preview.stdin_preview)

        with self.assertRaises(InvocationError):
            self.adapter().implement(
                "prompt",
                worktree=self.worktree,
                timeout_seconds=0,
                log_dir=log_dir,
                dry_run=True,
            )

    def test_explicit_auth_profile_is_writable_mounted_and_sets_codex_environment(self) -> None:
        profile = self.auth_profile()
        bwrap_record = self.base / "auth-bwrap.json"
        with patch(
            "orchestrator.adapters.auth.dedicated_auth_root",
            return_value=profile.parents[1],
        ):
            result = CodexCLI(
                self.workspace,
                executable=str(FAKE_CLI),
                sandbox_executable=str(FAKE_BWRAP),
                runtime_root=FIXTURES,
                auth_profile=profile,
                environment={"KC_FAKE_BWRAP_RECORD": str(bwrap_record)},
            ).implement(
                "prompt",
                worktree=self.worktree,
                timeout_seconds=2,
                log_dir=self.base / "logs",
            )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertTrue(result.succeeded, result.parse_error)
        argv = json.loads(bwrap_record.read_text(encoding="utf-8"))
        mount = argv.index(str(profile.resolve()))
        self.assertEqual("--bind", argv[mount - 1])
        self.assertEqual("/home/kernelcanvas/.codex", argv[mount + 1])
        variable = argv.index("CODEX_HOME")
        self.assertEqual("--setenv", argv[variable - 1])
        self.assertEqual("/home/kernelcanvas/.codex", argv[variable + 1])

    def test_default_does_not_select_host_codex_profile(self) -> None:
        preview = self.adapter().implement(
            "prompt",
            worktree=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "logs",
            dry_run=True,
        )
        self.assertIsInstance(preview, InvocationPreview)
        assert isinstance(preview, InvocationPreview)
        self.assertNotIn("CODEX_HOME", preview.argv)
        self.assertNotIn(str(Path.home() / ".codex"), preview.argv)

    def test_missing_openssl_crypto_policy_config_fails_before_launch(self) -> None:
        missing = self.base / "missing-opensslcnf.config"
        with patch(
            "orchestrator.adapters.claude_cli._OPENSSL_CRYPTO_POLICY_CONFIG",
            missing,
        ), patch.object(ProcessRunner, "run") as run:
            with self.assertRaisesRegex(
                InvocationError, "crypto-policy configuration is unavailable"
            ):
                self.adapter().implement(
                    "prompt",
                    worktree=self.worktree,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()

    def test_malformed_jsonl_and_nonzero_exit_never_succeed(self) -> None:
        malformed = self.adapter(KC_FAKE_MODE="malformed").implement(
            "prompt",
            worktree=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "malformed",
        )
        self.assertIsInstance(malformed, CLIResult)
        assert isinstance(malformed, CLIResult)
        self.assertFalse(malformed.succeeded)
        self.assertIsNotNone(malformed.parse_error)

        failed = self.adapter(KC_FAKE_MODE="nonzero").implement(
            "prompt",
            worktree=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "nonzero",
        )
        self.assertIsInstance(failed, CLIResult)
        assert isinstance(failed, CLIResult)
        self.assertEqual(17, failed.exit_code)
        self.assertFalse(failed.succeeded)

    def test_missing_codex_executable_is_typed(self) -> None:
        adapter = CodexCLI(
            self.workspace,
            executable="missing-codex-kc105",
            sandbox_executable=str(FAKE_BWRAP),
        )
        with self.assertRaises(ExecutableNotFoundError):
            adapter.implement(
                "prompt",
                worktree=self.worktree,
                timeout_seconds=2,
                log_dir=self.base / "missing",
                dry_run=True,
            )

    def test_missing_bubblewrap_is_typed_and_never_falls_back(self) -> None:
        adapter = CodexCLI(
            self.workspace,
            executable=str(FAKE_CLI),
            sandbox_executable="missing-bwrap-kc105",
            runtime_root=FIXTURES,
        )
        with patch.object(ProcessRunner, "run") as run:
            with self.assertRaises(ExecutableNotFoundError):
                adapter.implement(
                    "prompt",
                    worktree=self.worktree,
                    timeout_seconds=2,
                    log_dir=self.base / "missing-bwrap",
                )
        run.assert_not_called()

    def test_non_system_runtime_requires_explicit_narrow_approval(self) -> None:
        adapter = CodexCLI(
            self.workspace,
            executable=str(FAKE_CLI),
            sandbox_executable=str(FAKE_BWRAP),
        )
        with patch.object(ProcessRunner, "run") as run:
            with self.assertRaisesRegex(InvocationError, "explicit runtime_root"):
                adapter.implement(
                    "prompt",
                    worktree=self.worktree,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()

    def test_runtime_root_cannot_expose_home_or_credentials(self) -> None:
        fake_home = self.base / "personal-home"
        (fake_home / ".codex").mkdir(parents=True)
        for runtime_root in (fake_home, fake_home / ".codex"):
            with self.subTest(runtime_root=runtime_root):
                with patch(
                    "orchestrator.adapters.codex_cli.resolve_executable",
                    return_value=str(runtime_root / "codex"),
                ), patch.object(Path, "home", return_value=fake_home), patch.object(
                    ProcessRunner, "run"
                ) as run:
                    adapter = CodexCLI(
                        self.workspace,
                        executable="codex",
                        sandbox_executable=str(FAKE_BWRAP),
                        runtime_root=runtime_root,
                    )
                    with self.assertRaisesRegex(InvocationError, "broad or sensitive"):
                        adapter.implement(
                            "prompt",
                            worktree=self.worktree,
                            timeout_seconds=2,
                            log_dir=self.base / "logs",
                        )
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
