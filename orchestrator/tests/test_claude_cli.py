from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.adapters.claude_cli import ClaudeCLI, _system_mount_arguments
from orchestrator.adapters.process import ProcessRunner
from orchestrator.adapters.results import (
    CLIResult,
    ExecutableNotFoundError,
    InvocationError,
    InvocationPreview,
)


FIXTURES = Path(__file__).parent / "fixtures"
FAKE_CLI = FIXTURES / "fake_model_cli.py"
FAKE_BWRAP = FIXTURES / "fake_bwrap.py"


class ClaudeCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.worktree = self.base / "worktree"
        self.worktree.mkdir()

    def adapter(self, **environment: str) -> ClaudeCLI:
        return ClaudeCLI(
            self.base,
            executable=str(FAKE_CLI),
            sandbox_executable=str(FAKE_BWRAP),
            runtime_root=FIXTURES,
            environment=environment,
        )

    def auth_profile(self) -> Path:
        auth_root = self.base / "kernelcanvas-auth"
        profile = auth_root / "claude" / "supervised"
        profile.mkdir(parents=True)
        for directory in (auth_root, profile.parent, profile):
            directory.chmod(0o700)
        return profile

    def test_review_uses_os_read_only_and_tool_restrictions(self) -> None:
        record = self.base / "cli.json"
        bwrap_record = self.base / "bwrap.json"
        result = self.adapter(
            KC_FAKE_RECORD=str(record),
            KC_FAKE_BWRAP_RECORD=str(bwrap_record),
        ).review(
            "review this diff",
            cwd=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "logs",
        )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertTrue(result.succeeded, result.parse_error)
        recorded = json.loads(record.read_text(encoding="utf-8"))
        self.assertEqual("review this diff", recorded["stdin"])
        self.assertIn("--permission-mode", recorded["argv"])
        self.assertIn("plan", recorded["argv"])
        schema_index = recorded["argv"].index("--json-schema")
        schema = json.loads(recorded["argv"][schema_index + 1])
        self.assertEqual(
            ["APPROVE", "REQUEST_CHANGES"],
            schema["properties"]["verdict"]["enum"],
        )
        self.assertEqual(False, schema["additionalProperties"])
        self.assertIn("--tools", recorded["argv"])
        self.assertIn("Read", recorded["argv"])
        self.assertIn("mcp__*", " ".join(recorded["argv"]))
        self.assertNotIn("--dangerously-skip-permissions", recorded["argv"])
        sandbox_argv = json.loads(bwrap_record.read_text(encoding="utf-8"))
        self.assertIn("--ro-bind", sandbox_argv)
        self.assertIn("--tmpfs", sandbox_argv)
        self.assertIn("--chdir", sandbox_argv)
        self.assertIn("--unshare-pid", sandbox_argv)
        self.assertNotIn("--unshare-net", sandbox_argv)
        root_bind = ["--ro-bind", "/", "/"]
        self.assertFalse(
            any(sandbox_argv[index : index + 3] == root_bind for index in range(len(sandbox_argv) - 2))
        )
        self.assertIn(str(self.worktree), sandbox_argv)
        self.assertNotIn(str(self.base), sandbox_argv)
        read_only_sources = {
            sandbox_argv[index + 1]
            for index, value in enumerate(sandbox_argv[:-2])
            if value == "--ro-bind"
        }
        self.assertNotIn(str(Path.home()), read_only_sources)

    def test_plan_does_not_require_reviewer_structured_output(self) -> None:
        record = self.base / "plan-cli.json"
        result = self.adapter(KC_FAKE_RECORD=str(record)).plan(
            "plan this task",
            cwd=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "plan-logs",
        )
        self.assertIsInstance(result, CLIResult)
        recorded = json.loads(record.read_text(encoding="utf-8"))
        self.assertNotIn("--json-schema", recorded["argv"])

    def test_cwd_outside_workspace_and_symlink_escape_are_rejected(self) -> None:
        outside = self.base.parent / f"{self.base.name}-outside"
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        escape = self.base / "escape"
        escape.symlink_to(outside, target_is_directory=True)
        for cwd in (outside, escape):
            with self.subTest(cwd=cwd), patch.object(ProcessRunner, "run") as run:
                with self.assertRaises(InvocationError):
                    self.adapter().review(
                        "prompt",
                        cwd=cwd,
                        timeout_seconds=2,
                        log_dir=self.base / "logs",
                    )
                run.assert_not_called()

    def test_dry_run_launches_no_process_and_writes_no_logs(self) -> None:
        log_dir = self.base / "never-created"
        adapter = self.adapter()
        with patch.object(ProcessRunner, "run") as run:
            preview = adapter.plan(
                "token=secret-value",
                cwd=self.worktree,
                timeout_seconds=2,
                log_dir=log_dir,
                dry_run=True,
            )
        self.assertIsInstance(preview, InvocationPreview)
        assert isinstance(preview, InvocationPreview)
        run.assert_not_called()
        self.assertFalse(log_dir.exists())
        self.assertNotIn("secret-value", preview.stdin_preview)

        with self.assertRaises(InvocationError):
            adapter.plan(
                "prompt",
                cwd=self.worktree,
                timeout_seconds=0,
                log_dir=log_dir,
                dry_run=True,
            )

    def test_explicit_auth_profile_is_writable_mounted_and_sets_claude_environment(self) -> None:
        profile = self.auth_profile()
        bwrap_record = self.base / "auth-bwrap.json"
        with patch(
            "orchestrator.adapters.auth.dedicated_auth_root",
            return_value=profile.parents[1],
        ):
            result = ClaudeCLI(
                self.base,
                executable=str(FAKE_CLI),
                sandbox_executable=str(FAKE_BWRAP),
                runtime_root=FIXTURES,
                auth_profile=profile,
                environment={"KC_FAKE_BWRAP_RECORD": str(bwrap_record)},
            ).review(
                "prompt",
                cwd=self.worktree,
                timeout_seconds=2,
                log_dir=self.base / "logs",
            )
        self.assertIsInstance(result, CLIResult)
        assert isinstance(result, CLIResult)
        self.assertTrue(result.succeeded, result.parse_error)
        argv = json.loads(bwrap_record.read_text(encoding="utf-8"))
        mount = argv.index(str(profile.resolve()))
        self.assertEqual("--bind", argv[mount - 1])
        self.assertEqual("/home/kernelcanvas/.claude", argv[mount + 1])
        variable = argv.index("CLAUDE_CONFIG_DIR")
        self.assertEqual("--setenv", argv[variable - 1])
        self.assertEqual("/home/kernelcanvas/.claude", argv[variable + 1])

    def test_default_does_not_select_host_claude_profile(self) -> None:
        preview = self.adapter().review(
            "prompt",
            cwd=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "logs",
            dry_run=True,
        )
        self.assertIsInstance(preview, InvocationPreview)
        assert isinstance(preview, InvocationPreview)
        self.assertNotIn("CLAUDE_CONFIG_DIR", preview.argv)
        self.assertNotIn(str(Path.home() / ".claude"), preview.argv)

    def test_system_mounts_preserve_verified_openssl_crypto_policy_link(self) -> None:
        arguments = _system_mount_arguments()
        config = Path("/etc/crypto-policies/back-ends/opensslcnf.config")
        link = arguments.index(str(config))
        self.assertEqual("--symlink", arguments[link - 2])
        self.assertEqual(str(config.readlink()), arguments[link - 1])
        self.assertTrue(config.resolve(strict=True).is_file())

    def test_missing_openssl_crypto_policy_config_fails_before_launch(self) -> None:
        missing = self.base / "missing-opensslcnf.config"
        with patch(
            "orchestrator.adapters.claude_cli._OPENSSL_CRYPTO_POLICY_CONFIG",
            missing,
        ), patch.object(ProcessRunner, "run") as run:
            with self.assertRaisesRegex(
                InvocationError, "crypto-policy configuration is unavailable"
            ):
                self.adapter().review(
                    "prompt",
                    cwd=self.worktree,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()

    def test_openssl_crypto_policy_symlink_outside_approved_root_fails_before_launch(
        self,
    ) -> None:
        outside_target = self.base / "unapproved-opensslcnf.config"
        outside_target.write_text("unapproved policy", encoding="utf-8")
        config = self.base / "opensslcnf.config"
        config.symlink_to(outside_target)
        bwrap_record = self.base / "must-not-launch-bwrap.json"
        log_dir = self.base / "must-not-create-logs"

        with patch(
            "orchestrator.adapters.claude_cli._OPENSSL_CRYPTO_POLICY_CONFIG",
            config,
        ), patch.object(ProcessRunner, "run") as run:
            with self.assertRaisesRegex(
                InvocationError, "outside approved system roots"
            ):
                self.adapter(KC_FAKE_BWRAP_RECORD=str(bwrap_record)).review(
                    "prompt",
                    cwd=self.worktree,
                    timeout_seconds=2,
                    log_dir=log_dir,
                )

        run.assert_not_called()
        self.assertFalse(bwrap_record.exists())
        self.assertFalse(log_dir.exists())

    def test_malformed_json_and_nonzero_exit_never_succeed(self) -> None:
        malformed = self.adapter(KC_FAKE_MODE="malformed").plan(
            "prompt",
            cwd=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "malformed",
        )
        self.assertIsInstance(malformed, CLIResult)
        assert isinstance(malformed, CLIResult)
        self.assertFalse(malformed.succeeded)
        self.assertIsNotNone(malformed.parse_error)

        failed = self.adapter(KC_FAKE_MODE="nonzero").plan(
            "prompt",
            cwd=self.worktree,
            timeout_seconds=2,
            log_dir=self.base / "nonzero",
        )
        self.assertIsInstance(failed, CLIResult)
        assert isinstance(failed, CLIResult)
        self.assertEqual(17, failed.exit_code)
        self.assertFalse(failed.succeeded)

    def test_missing_claude_and_sandbox_executables_are_typed(self) -> None:
        missing_claude = ClaudeCLI(
            self.base,
            executable="missing-claude-kc105",
            sandbox_executable=str(FAKE_BWRAP),
        )
        with self.assertRaises(ExecutableNotFoundError):
            missing_claude.plan(
                "prompt",
                cwd=self.worktree,
                timeout_seconds=2,
                log_dir=self.base / "missing-claude",
                dry_run=True,
            )
        missing_sandbox = ClaudeCLI(
            self.base,
            executable=str(FAKE_CLI),
            sandbox_executable="missing-bwrap-kc105",
            runtime_root=FIXTURES,
        )
        with self.assertRaises(ExecutableNotFoundError):
            missing_sandbox.review(
                "prompt",
                cwd=self.worktree,
                timeout_seconds=2,
                log_dir=self.base / "missing-bwrap",
                dry_run=True,
            )

    def test_non_system_runtime_requires_explicit_narrow_approval(self) -> None:
        adapter = ClaudeCLI(
            self.base,
            executable=str(FAKE_CLI),
            sandbox_executable=str(FAKE_BWRAP),
        )
        with patch.object(ProcessRunner, "run") as run:
            with self.assertRaisesRegex(InvocationError, "explicit runtime_root"):
                adapter.review(
                    "prompt",
                    cwd=self.worktree,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()

    def test_runtime_root_must_contain_resolved_executable(self) -> None:
        unrelated = self.base / "unrelated-runtime"
        unrelated.mkdir()
        adapter = ClaudeCLI(
            self.base,
            executable=str(FAKE_CLI),
            sandbox_executable=str(FAKE_BWRAP),
            runtime_root=unrelated,
        )
        with patch.object(ProcessRunner, "run") as run:
            with self.assertRaisesRegex(
                InvocationError, "outside approved runtime root"
            ):
                adapter.review(
                    "prompt",
                    cwd=self.worktree,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()

    def test_runtime_root_must_be_an_existing_directory(self) -> None:
        missing = self.base / "missing-runtime"
        with patch(
            "orchestrator.adapters.claude_cli.resolve_executable",
            return_value=str(missing / "claude"),
        ), patch.object(ProcessRunner, "run") as run:
            adapter = ClaudeCLI(
                self.base,
                executable="claude",
                sandbox_executable=str(FAKE_BWRAP),
                runtime_root=missing,
            )
            with self.assertRaisesRegex(InvocationError, "not a directory"):
                adapter.review(
                    "prompt",
                    cwd=self.worktree,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()

    def test_runtime_root_cannot_expose_home_credentials_or_broad_roots(self) -> None:
        fake_home = self.base / "personal-home"
        (fake_home / ".claude").mkdir(parents=True)
        cases = (fake_home, fake_home / ".claude", Path("/"), Path("/tmp"))
        for runtime_root in cases:
            with self.subTest(runtime_root=runtime_root), patch(
                "orchestrator.adapters.claude_cli.resolve_executable",
                return_value=str(runtime_root / "claude"),
            ), patch.object(Path, "home", return_value=fake_home), patch.object(
                ProcessRunner, "run"
            ) as run:
                adapter = ClaudeCLI(
                    self.base,
                    executable="claude",
                    sandbox_executable=str(FAKE_BWRAP),
                    runtime_root=runtime_root,
                )
                with self.assertRaisesRegex(InvocationError, "broad or sensitive"):
                    adapter.review(
                        "prompt",
                        cwd=self.worktree,
                        timeout_seconds=2,
                        log_dir=self.base / "logs",
                    )
            run.assert_not_called()

    def test_runtime_root_symlink_is_resolved_before_validation(self) -> None:
        fake_home = self.base / "personal-home"
        sensitive = fake_home / ".config" / "claude"
        sensitive.mkdir(parents=True)
        alias = self.base / "runtime-alias"
        alias.symlink_to(sensitive, target_is_directory=True)
        with patch(
            "orchestrator.adapters.claude_cli.resolve_executable",
            return_value=str(sensitive / "claude"),
        ), patch.object(Path, "home", return_value=fake_home), patch.object(
            ProcessRunner, "run"
        ) as run:
            adapter = ClaudeCLI(
                self.base,
                executable="claude",
                sandbox_executable=str(FAKE_BWRAP),
                runtime_root=alias,
            )
            with self.assertRaisesRegex(InvocationError, "broad or sensitive"):
                adapter.review(
                    "prompt",
                    cwd=self.worktree,
                    timeout_seconds=2,
                    log_dir=self.base / "logs",
                )
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
