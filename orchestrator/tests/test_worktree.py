from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from orchestrator.models import WorktreeError
from orchestrator.worktree import collect_review_input, verify_worktree


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class WorktreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "assigned"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.email", "tests@example.invalid")
        git(self.repo, "config", "user.name", "Tests")
        (self.repo / "allowed.txt").write_text("original\n", encoding="utf-8")
        git(self.repo, "add", "allowed.txt")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "switch", "-c", "agent/KC-106-autonomous-loop")

    def verify(self):
        return verify_worktree(
            self.repo,
            workspace_root=self.base,
            expected_branch="agent/KC-106-autonomous-loop",
            allowed_paths=("allowed.txt", "new/**"),
        )

    def test_complete_review_contains_tracked_and_new_files(self) -> None:
        (self.repo / "allowed.txt").write_text("changed\n", encoding="utf-8")
        (self.repo / "new").mkdir()
        (self.repo / "new" / "note.txt").write_text("new evidence\n", encoding="utf-8")
        review = collect_review_input(self.verify())
        self.assertIn("TRACKED STAGED DIFF", review)
        self.assertIn("TRACKED UNSTAGED DIFF", review)
        self.assertIn("-original", review)
        self.assertIn("+changed", review)
        self.assertIn("+++ b/new/note.txt", review)
        self.assertIn("new evidence", review)

    def test_wrong_branch_main_checkout_and_scope_violation_are_rejected(self) -> None:
        with self.assertRaisesRegex(WorktreeError, "wrong branch"):
            verify_worktree(
                self.repo,
                workspace_root=self.base,
                expected_branch="agent/wrong",
                allowed_paths=("allowed.txt",),
            )
        git(self.repo, "switch", "main")
        with self.assertRaisesRegex(WorktreeError, "main checkout"):
            verify_worktree(
                self.repo,
                workspace_root=self.base,
                expected_branch="main",
                allowed_paths=("allowed.txt",),
            )
        git(self.repo, "switch", "agent/KC-106-autonomous-loop")
        (self.repo / "outside.txt").write_text("no\n", encoding="utf-8")
        with self.assertRaisesRegex(WorktreeError, "outside permitted"):
            self.verify()

    def test_path_escape_and_untracked_symlink_are_rejected(self) -> None:
        with self.assertRaisesRegex(WorktreeError, "escapes"):
            verify_worktree(
                self.repo,
                workspace_root=self.base / "unrelated",
                expected_branch="agent/KC-106-autonomous-loop",
                allowed_paths=("allowed.txt",),
            )
        (self.repo / "new").mkdir()
        (self.repo / "new" / "escape").symlink_to(self.base)
        with self.assertRaisesRegex(WorktreeError, "symlink"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
