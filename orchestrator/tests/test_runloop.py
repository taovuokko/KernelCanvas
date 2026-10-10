from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from orchestrator.adapters.results import CLIResult
from orchestrator.database import connect, init_schema
from orchestrator.models import RunLoopError, TaskState, WrongWorkerError
from orchestrator.runloop import AutonomousRunLoop, QualityEvidence
from orchestrator.scheduler import add_task, get_attempts, get_task


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def result(base: Path, parsed, *, exit_code: int = 0) -> CLIResult:
    return CLIResult(
        argv=("fake",),
        cwd=base,
        exit_code=exit_code,
        timed_out=False,
        stdout_path=base / "stdout.log",
        stderr_path=base / "stderr.log",
        stdout_truncated=False,
        stderr_truncated=False,
        parsed=parsed,
        parse_error=None,
        duration_seconds=0.01,
    )


class FakeImplementer:
    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self.calls = 0

    def implement(self, prompt: str, **kwargs) -> CLIResult:
        self.calls += 1
        (self.repo / "allowed.txt").write_text(f"attempt {self.calls}\n", encoding="utf-8")
        return result(self.repo, [{"type": "completed"}])


class FakeReviewer:
    def __init__(self, repo: Path, verdicts: list[dict[str, str]]) -> None:
        self.repo = repo
        self.verdicts = verdicts
        self.prompts: list[str] = []

    def review(self, prompt: str, **kwargs) -> CLIResult:
        self.prompts.append(prompt)
        return result(self.repo, self.verdicts.pop(0))


class LeaseStealingImplementer(FakeImplementer):
    def __init__(self, repo: Path, connection) -> None:
        super().__init__(repo)
        self.connection = connection

    def implement(self, prompt: str, **kwargs) -> CLIResult:
        response = super().implement(prompt, **kwargs)
        self.connection.execute(
            "UPDATE leases SET owner = 'intruder' WHERE status = 'ACTIVE'"
        )
        return response


class FakeQuality:
    def __init__(self, repo: Path, passes: bool = True) -> None:
        self.repo = repo
        self.passes = passes

    def run(self, check_ids, **kwargs):
        code = 0 if self.passes else 1
        return [
            QualityEvidence(item, code, False, self.repo / "out", self.repo / "err")
            for item in check_ids
        ]


class RunLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "assigned"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.email", "tests@example.invalid")
        git(self.repo, "config", "user.name", "Tests")
        (self.repo / "allowed.txt").write_text("base\n", encoding="utf-8")
        task_dir = self.repo / "tasks"
        task_dir.mkdir()
        self.task_file = task_dir / "KC-106.md"
        self.task_file.write_text(
            "# task\n\n## Allowed paths\n- `allowed.txt`\n", encoding="utf-8"
        )
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "switch", "-c", "agent/KC-106-autonomous-loop")
        self.connection = connect(self.base / "state.sqlite3")
        self.addCleanup(self.connection.close)
        init_schema(self.connection)
        add_task(
            self.connection,
            "KC-106",
            self.task_file,
            "https://github.com/example/repo/issues/106",
        )

    def run_loop(self, reviewer: FakeReviewer, *, authorized: bool = True):
        implementer = FakeImplementer(self.repo)
        loop = AutonomousRunLoop(
            self.connection,
            implementer=implementer,
            reviewer=reviewer,
            quality_runner=FakeQuality(self.repo),
        )
        outcome = loop.run(
            "KC-106",
            worker="worker",
            reviewer_name="reviewer",
            workspace_root=self.base,
            worktree=self.repo,
            expected_branch="agent/KC-106-autonomous-loop",
            lease_seconds=60,
            timeout_seconds=1,
            check_ids=["orchestrator-help"],
            evidence_root=self.base / "evidence",
            authorize_real_execution=authorized,
        )
        return outcome, implementer

    def test_fake_agents_request_one_correction_then_approve(self) -> None:
        reviewer = FakeReviewer(
            self.repo,
            [
                {"verdict": "REQUEST_CHANGES", "summary": "fix it"},
                {"verdict": "APPROVE", "summary": "looks good"},
            ],
        )
        outcome, implementer = self.run_loop(reviewer)
        self.assertEqual(TaskState.READY_FOR_PR, outcome.state)
        self.assertEqual(2, outcome.attempts)
        self.assertEqual(2, implementer.calls)
        attempts = get_attempts(self.connection, "KC-106")
        self.assertEqual(2, len(attempts))
        self.assertIn("REQUEST_CHANGES", attempts[0].outcome)
        self.assertIn("APPROVED", attempts[1].outcome)
        self.assertIn("TRACKED STAGED DIFF", reviewer.prompts[0])
        self.assertIn("TRACKED UNSTAGED DIFF", reviewer.prompts[0])
        self.assertIsNone(get_task(self.connection, "KC-106").lease)

    def test_malformed_review_fails_closed_and_persists_reason(self) -> None:
        reviewer = FakeReviewer(self.repo, [{"verdict": "MAYBE", "summary": "no"}])
        with self.assertRaisesRegex(RunLoopError, "APPROVE or REQUEST_CHANGES"):
            self.run_loop(reviewer)
        self.assertEqual(TaskState.BLOCKED, get_task(self.connection, "KC-106").state)
        attempt = get_attempts(self.connection, "KC-106")[0]
        self.assertIn("BLOCKED", attempt.outcome)
        self.assertIsNotNone(attempt.ended_at)

    def test_at_most_two_corrections_are_attempted(self) -> None:
        reviewer = FakeReviewer(
            self.repo,
            [
                {"verdict": "REQUEST_CHANGES", "summary": "one"},
                {"verdict": "REQUEST_CHANGES", "summary": "two"},
                {"verdict": "REQUEST_CHANGES", "summary": "three"},
            ],
        )
        outcome, implementer = self.run_loop(reviewer)
        self.assertEqual(TaskState.FAILED, outcome.state)
        self.assertEqual(3, implementer.calls)
        self.assertEqual(3, len(get_attempts(self.connection, "KC-106")))

    def test_lease_loss_stops_before_quality_or_review_and_fails_closed(self) -> None:
        reviewer = FakeReviewer(
            self.repo, [{"verdict": "APPROVE", "summary": "must not run"}]
        )
        implementer = LeaseStealingImplementer(self.repo, self.connection)
        quality = FakeQuality(self.repo)
        loop = AutonomousRunLoop(
            self.connection,
            implementer=implementer,
            reviewer=reviewer,
            quality_runner=quality,
        )
        with self.assertRaisesRegex(WrongWorkerError, "belongs to intruder"):
            loop.run(
                "KC-106",
                worker="worker",
                reviewer_name="reviewer",
                workspace_root=self.base,
                worktree=self.repo,
                expected_branch="agent/KC-106-autonomous-loop",
                lease_seconds=60,
                timeout_seconds=1,
                check_ids=["orchestrator-help"],
                evidence_root=self.base / "evidence",
                authorize_real_execution=True,
            )
        self.assertEqual([], reviewer.prompts)
        self.assertEqual(TaskState.BLOCKED, get_task(self.connection, "KC-106").state)
        self.assertIsNotNone(get_attempts(self.connection, "KC-106")[0].ended_at)

    def test_authorization_is_required_without_database_mutation(self) -> None:
        reviewer = FakeReviewer(
            self.repo, [{"verdict": "APPROVE", "summary": "ok"}]
        )
        with self.assertRaisesRegex(RunLoopError, "explicit authorization"):
            self.run_loop(reviewer, authorized=False)
        self.assertEqual(TaskState.QUEUED, get_task(self.connection, "KC-106").state)
        self.assertEqual([], get_attempts(self.connection, "KC-106"))


if __name__ == "__main__":
    unittest.main()
