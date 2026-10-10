from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from orchestrator.adapters.auth import dedicated_auth_root, resolve_auth_profile
from orchestrator.adapters.results import InvocationError


class AuthProfileValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.auth_root = self.base / "kernelcanvas" / "auth"
        self.claude_root = self.auth_root / "claude"
        self.codex_root = self.auth_root / "codex"
        self.profile = self.claude_root / "supervised"
        for directory in (
            self.auth_root,
            self.claude_root,
            self.codex_root,
            self.profile,
        ):
            directory.mkdir(exist_ok=True, parents=True)
            directory.chmod(0o700)
        self.root_patch = patch(
            "orchestrator.adapters.auth.dedicated_auth_root",
            return_value=self.auth_root,
        )
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_explicit_private_direct_child_is_allowed(self) -> None:
        self.assertEqual(
            self.profile.resolve(),
            resolve_auth_profile(self.profile, provider="claude"),
        )

    def test_default_root_uses_account_home_not_environment_home(self) -> None:
        account_home = self.base / "account-home"
        with patch.dict("os.environ", {"HOME": "/"}), patch(
            "orchestrator.adapters.auth.pwd.getpwuid",
            return_value=SimpleNamespace(pw_dir=str(account_home)),
        ):
            self.assertEqual(
                account_home / ".local" / "share" / "kernelcanvas" / "auth",
                dedicated_auth_root(),
            )

    def test_relative_traversal_and_provider_root_are_rejected(self) -> None:
        cases = (
            Path("supervised"),
            self.profile / ".." / "supervised",
            self.claude_root,
            self.auth_root,
        )
        for selected in cases:
            with self.subTest(selected=selected), self.assertRaises(InvocationError):
                resolve_auth_profile(selected, provider="claude")

    def test_profile_for_the_other_provider_is_rejected(self) -> None:
        codex_profile = self.codex_root / "supervised"
        codex_profile.mkdir(mode=0o700)
        with self.assertRaisesRegex(InvocationError, "direct child"):
            resolve_auth_profile(codex_profile, provider="claude")

    def test_symlink_escape_is_resolved_and_rejected(self) -> None:
        outside = self.base / "outside-profile"
        outside.mkdir(mode=0o700)
        escape = self.claude_root / "escape"
        escape.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(InvocationError, "direct child"):
            resolve_auth_profile(escape, provider="claude")

    def test_symlink_loop_and_nul_are_typed_rejections(self) -> None:
        loop = self.claude_root / "loop"
        loop.symlink_to(loop)
        for selected in (loop, Path("/profile\x00name")):
            with self.subTest(selected=selected), self.assertRaises(InvocationError):
                resolve_auth_profile(selected, provider="claude")

    def test_mount_points_are_rejected(self) -> None:
        with patch("orchestrator.adapters.auth.os.path.ismount", return_value=True):
            with self.assertRaisesRegex(InvocationError, "mount points"):
                resolve_auth_profile(self.profile, provider="claude")

    def test_group_or_other_directory_permissions_are_rejected(self) -> None:
        for directory in (self.auth_root, self.claude_root, self.profile):
            with self.subTest(directory=directory):
                directory.chmod(0o750)
                with self.assertRaisesRegex(InvocationError, "group or other"):
                    resolve_auth_profile(self.profile, provider="claude")
                directory.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
