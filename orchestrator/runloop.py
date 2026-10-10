"""Bounded single-task implementation, check, and independent-review loop."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence, TypeVar

from . import scheduler
from .adapters.claude_cli import ClaudeCLI, _system_mount_arguments
from .adapters.codex_cli import CodexCLI
from .adapters.process import (
    ProcessOutput,
    ProcessRunner,
    build_safe_environment,
    resolve_executable,
)
from .adapters.results import CLIResult, InvocationError
from .models import RunLoopError, TaskState
from .worktree import (
    VerifiedWorktree,
    collect_review_input,
    parse_allowed_paths,
    verify_worktree,
)

MAX_CORRECTION_ROUNDS = 2
MAX_TASK_FILE_BYTES = 128 * 1024
LEASE_SAFETY_SECONDS = 5
PhaseResult = TypeVar("PhaseResult")

QUALITY_CHECKS: dict[str, tuple[str, ...]] = {
    "orchestrator-tests": (
        "/usr/bin/python3",
        "-B",
        "-m",
        "unittest",
        "discover",
        "-s",
        "orchestrator/tests",
        "-v",
    ),
    "orchestrator-help": ("/usr/bin/python3", "-B", "-m", "orchestrator", "--help"),
}


class Implementer(Protocol):
    def implement(
        self,
        assignment_prompt: str,
        *,
        worktree: Path,
        timeout_seconds: float,
        log_dir: Path,
        dry_run: bool = False,
    ) -> CLIResult: ...


class Reviewer(Protocol):
    def review(
        self,
        diff_context: str,
        *,
        cwd: Path,
        timeout_seconds: float,
        log_dir: Path,
        dry_run: bool = False,
    ) -> CLIResult: ...


@dataclass(frozen=True)
class QualityEvidence:
    check_id: str
    exit_code: int
    timed_out: bool
    stdout_path: Path
    stderr_path: Path

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass(frozen=True)
class RunResult:
    task_id: str
    state: TaskState
    attempts: int
    handover: str


class SandboxedQualityRunner:
    """Run only named checks inside a Bubblewrap filesystem/network boundary."""

    def __init__(
        self,
        *,
        sandbox_executable: str = "bwrap",
        runner: ProcessRunner | None = None,
        environment: dict[str, str] | None = None,
    ) -> None:
        self.sandbox_executable = sandbox_executable
        self.runner = runner or ProcessRunner()
        self.environment = build_safe_environment(environment)

    def run(
        self,
        check_ids: Sequence[str],
        *,
        worktree: Path,
        timeout_seconds: float,
        log_dir: Path,
    ) -> list[QualityEvidence]:
        if not check_ids:
            raise InvocationError("at least one quality check is required")
        bwrap = resolve_executable(self.sandbox_executable, self.environment)
        evidence: list[QualityEvidence] = []
        for check_id in check_ids:
            command = QUALITY_CHECKS.get(check_id)
            if command is None:
                raise InvocationError(f"quality check is not allowlisted: {check_id}")
            argv = (
                bwrap,
                "--die-with-parent",
                "--new-session",
                "--unshare-pid",
                "--unshare-ipc",
                "--unshare-uts",
                *_system_mount_arguments(),
                "--dev",
                "/dev",
                "--proc",
                "/proc",
                "--tmpfs",
                "/tmp",
                "--dir",
                "/home",
                "--dir",
                "/home/kernelcanvas",
                "--clearenv",
                "--setenv",
                "HOME",
                "/home/kernelcanvas",
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
                "PYTHONDONTWRITEBYTECODE",
                "1",
                "--setenv",
                "GIT_CONFIG_GLOBAL",
                os.devnull,
                "--setenv",
                "GIT_CONFIG_NOSYSTEM",
                "1",
                "--bind",
                str(worktree),
                "/workspace",
                "--chdir",
                "/workspace",
                "--",
                *command,
            )
            output: ProcessOutput = self.runner.run(
                argv,
                cwd=worktree,
                environment=self.environment,
                stdin_text="",
                timeout_seconds=timeout_seconds,
                log_dir=log_dir / check_id,
            )
            item = QualityEvidence(
                check_id,
                output.exit_code,
                output.timed_out,
                output.stdout_path,
                output.stderr_path,
            )
            evidence.append(item)
            if not item.passed:
                break
        return evidence


class AutonomousRunLoop:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        implementer: Implementer,
        reviewer: Reviewer,
        quality_runner: SandboxedQualityRunner,
    ) -> None:
        self.connection = connection
        self.implementer = implementer
        self.reviewer = reviewer
        self.quality_runner = quality_runner

    def run(
        self,
        task_id: str,
        *,
        worker: str,
        reviewer_name: str,
        workspace_root: Path,
        worktree: Path,
        expected_branch: str,
        lease_seconds: int,
        timeout_seconds: float,
        check_ids: Sequence[str],
        evidence_root: Path,
        authorize_real_execution: bool,
    ) -> RunResult:
        if not authorize_real_execution:
            raise RunLoopError("real model execution requires explicit authorization")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise RunLoopError("phase timeout must be positive")
        if re.fullmatch(r"KC-[0-9]{3,}", task_id) is None:
            raise RunLoopError("run task ID must use the KC-NNN form")
        task = scheduler.get_task(self.connection, task_id)
        task_file = Path(task.task_file)
        resolved_worktree = worktree.resolve()
        if (
            task_file.is_symlink()
            or not task_file.resolve().is_relative_to(resolved_worktree)
        ):
            raise RunLoopError("task file must be a non-symlink file inside the worktree")
        task_text = _bounded_task_text(task_file)
        allowed = parse_allowed_paths(task_file)
        verified = verify_worktree(
            worktree,
            workspace_root=workspace_root,
            expected_branch=expected_branch,
            allowed_paths=allowed,
        )
        resolved_evidence_root = evidence_root.resolve()
        if resolved_evidence_root.is_relative_to(verified.path):
            raise RunLoopError("execution evidence must be stored outside the Git worktree")
        # One model phase plus all checks must fit inside every renewed lease.
        required_window = max(timeout_seconds, timeout_seconds * len(check_ids))
        if lease_seconds < required_window + LEASE_SAFETY_SECONDS:
            raise RunLoopError("lease duration is too short for the bounded execution phases")

        lease = scheduler.claim_task(
            self.connection, task_id, worker, reviewer_name, lease_seconds
        )
        scheduler.transition_active_task(
            self.connection,
            task_id,
            worker,
            lease.lease_token,
            TaskState.RUNNING,
            "authorized autonomous run started",
        )
        correction_context = ""
        completed_attempts = 0
        try:
            for round_index in range(MAX_CORRECTION_ROUNDS + 1):
                phase = "IMPLEMENTATION" if round_index == 0 else f"CORRECTION_{round_index}"
                attempt_dir = resolved_evidence_root / task_id / f"attempt-{round_index + 1}"
                attempt = scheduler.start_attempt(
                    self.connection,
                    task_id,
                    worker,
                    lease.lease_token,
                    phase,
                    str(attempt_dir),
                )
                completed_attempts += 1
                prompt = _implementation_prompt(
                    task_id, task_text, verified.allowed_paths, correction_context
                )
                implementation = self._guarded_phase(
                    task_id,
                    worker,
                    lease.lease_token,
                    timeout_seconds,
                    lambda: self.implementer.implement(
                        prompt,
                        worktree=verified.path,
                        timeout_seconds=timeout_seconds,
                        log_dir=attempt_dir / "implementer",
                    ),
                )
                if not implementation.succeeded:
                    reason = _adapter_failure("implementer", implementation)
                    scheduler.finish_attempt(
                        self.connection, attempt.id, task_id, worker, lease.lease_token, reason
                    )
                    if round_index < MAX_CORRECTION_ROUNDS:
                        correction_context = reason
                        continue
                    return self._finish_failed(
                        task_id, worker, lease.lease_token, completed_attempts, reason
                    )

                verified = verify_worktree(
                    verified.path,
                    workspace_root=verified.repository_root,
                    expected_branch=verified.branch,
                    allowed_paths=verified.allowed_paths,
                )
                check_window = timeout_seconds * len(check_ids)
                quality = self._guarded_phase(
                    task_id,
                    worker,
                    lease.lease_token,
                    check_window,
                    lambda: self.quality_runner.run(
                        check_ids,
                        worktree=verified.path,
                        timeout_seconds=timeout_seconds,
                        log_dir=attempt_dir / "quality",
                    ),
                )
                failures = [item for item in quality if not item.passed]
                if failures or len(quality) != len(check_ids):
                    reason = _quality_failure(quality, check_ids)
                    scheduler.finish_attempt(
                        self.connection, attempt.id, task_id, worker, lease.lease_token, reason
                    )
                    if round_index < MAX_CORRECTION_ROUNDS:
                        correction_context = reason
                        continue
                    return self._finish_failed(
                        task_id, worker, lease.lease_token, completed_attempts, reason
                    )

                scheduler.transition_active_task(
                    self.connection,
                    task_id,
                    worker,
                    lease.lease_token,
                    TaskState.REVIEW,
                    f"attempt {attempt.attempt_number} checks passed",
                )
                review_input = collect_review_input(verified, max_bytes=768 * 1024)
                review_prompt = _review_prompt(task_id, task_text, quality, review_input)
                review = self._guarded_phase(
                    task_id,
                    worker,
                    lease.lease_token,
                    timeout_seconds,
                    lambda: self.reviewer.review(
                        review_prompt,
                        cwd=verified.path,
                        timeout_seconds=timeout_seconds,
                        log_dir=attempt_dir / "reviewer",
                    ),
                )
                verdict, summary = _strict_review_verdict(review)
                if verdict == "APPROVE":
                    scheduler.finish_attempt(
                        self.connection,
                        attempt.id,
                        task_id,
                        worker,
                        lease.lease_token,
                        "APPROVED: " + summary,
                    )
                    scheduler.require_live_lease(
                        self.connection, task_id, worker, lease.lease_token
                    )
                    scheduler.release_task(
                        self.connection,
                        task_id,
                        worker,
                        TaskState.READY_FOR_PR,
                        "independent reviewer approved bounded candidate",
                    )
                    return RunResult(
                        task_id,
                        TaskState.READY_FOR_PR,
                        completed_attempts,
                        _handover(task_id, verified, quality, completed_attempts, summary),
                    )

                reason = "REQUEST_CHANGES: " + summary
                scheduler.finish_attempt(
                    self.connection, attempt.id, task_id, worker, lease.lease_token, reason
                )
                if round_index == MAX_CORRECTION_ROUNDS:
                    return self._finish_failed(
                        task_id, worker, lease.lease_token, completed_attempts, reason
                    )
                scheduler.transition_active_task(
                    self.connection,
                    task_id,
                    worker,
                    lease.lease_token,
                    TaskState.RUNNING,
                    f"reviewer requested correction round {round_index + 1}",
                )
                correction_context = reason
        except Exception as error:
            self._fail_closed_if_owned(task_id, worker, lease.lease_token, str(error))
            raise
        raise RunLoopError("bounded run exhausted without a terminal result")

    def _renew_for_phase(
        self, task_id: str, worker: str, token: str, seconds: float
    ) -> None:
        scheduler.require_live_lease(self.connection, task_id, worker, token)
        scheduler.heartbeat_task(self.connection, task_id, worker)
        scheduler.require_live_lease(
            self.connection,
            task_id,
            worker,
            token,
            minimum_remaining_seconds=seconds + LEASE_SAFETY_SECONDS,
        )

    def _guarded_phase(
        self,
        task_id: str,
        worker: str,
        token: str,
        seconds: float,
        invoke: Callable[[], PhaseResult],
    ) -> PhaseResult:
        """Prevent concurrent lease mutation for one already bounded phase."""

        self._renew_for_phase(task_id, worker, token, seconds)
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            scheduler.require_live_lease(
                self.connection,
                task_id,
                worker,
                token,
                minimum_remaining_seconds=seconds + LEASE_SAFETY_SECONDS,
            )
            result = invoke()
            scheduler.require_live_lease(self.connection, task_id, worker, token)
            self.connection.execute("COMMIT")
            return result
        except Exception:
            if self.connection.in_transaction:
                self.connection.execute("ROLLBACK")
            raise

    def _finish_failed(
        self, task_id: str, worker: str, token: str, attempts: int, reason: str
    ) -> RunResult:
        scheduler.require_live_lease(self.connection, task_id, worker, token)
        scheduler.release_task(
            self.connection, task_id, worker, TaskState.FAILED, reason[:1000]
        )
        return RunResult(
            task_id,
            TaskState.FAILED,
            attempts,
            f"Task: {task_id}\nStatus: FAILED\nAttempts: {attempts}\nReason: {reason}",
        )

    def _fail_closed_if_owned(
        self, task_id: str, worker: str, token: str, reason: str
    ) -> None:
        try:
            scheduler.require_live_lease(self.connection, task_id, worker, token)
            attempts = scheduler.get_attempts(self.connection, task_id)
            if attempts and attempts[-1].ended_at is None:
                scheduler.finish_attempt(
                    self.connection,
                    attempts[-1].id,
                    task_id,
                    worker,
                    token,
                    ("BLOCKED: " + reason)[:1000],
                )
            scheduler.release_task(
                self.connection,
                task_id,
                worker,
                TaskState.BLOCKED,
                ("fail-closed execution error: " + reason)[:1000],
            )
        except Exception:
            # Lease loss forbids any further scheduler mutation.
            return


def build_default_loop(
    connection: sqlite3.Connection,
    *,
    workspace_root: Path,
    codex_executable: str,
    claude_executable: str,
    sandbox_executable: str,
    codex_runtime_root: Path | None,
    claude_runtime_root: Path | None,
) -> AutonomousRunLoop:
    return AutonomousRunLoop(
        connection,
        implementer=CodexCLI(
            workspace_root,
            executable=codex_executable,
            sandbox_executable=sandbox_executable,
            runtime_root=codex_runtime_root,
        ),
        reviewer=ClaudeCLI(
            workspace_root,
            executable=claude_executable,
            sandbox_executable=sandbox_executable,
            runtime_root=claude_runtime_root,
        ),
        quality_runner=SandboxedQualityRunner(sandbox_executable=sandbox_executable),
    )


def _bounded_task_text(path: Path) -> str:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise RunLoopError(f"cannot read task file: {path}") from error
    if len(payload) > MAX_TASK_FILE_BYTES or b"\0" in payload:
        raise RunLoopError("task file is unsafe or exceeds the bounded input limit")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RunLoopError("task file is not valid UTF-8") from error


def _implementation_prompt(
    task_id: str, task_text: str, allowed: Sequence[str], correction: str
) -> str:
    suffix = f"\nCorrection evidence:\n{correction}" if correction else ""
    return (
        f"Implement {task_id} in the assigned worktree. Edit only these paths:\n"
        + "\n".join(f"- {item}" for item in allowed)
        + "\nNever push, merge, publish, deploy, or access host credentials.\n"
        + task_text
        + suffix
    )


def _review_prompt(
    task_id: str,
    task_text: str,
    quality: Sequence[QualityEvidence],
    changes: str,
) -> str:
    checks = "\n".join(
        f"- {item.check_id}: exit={item.exit_code} timeout={item.timed_out}"
        for item in quality
    )
    return (
        f"Independently review {task_id}. The complete bounded change set follows.\n"
        "Return only JSON: {\"verdict\":\"APPROVE|REQUEST_CHANGES\","
        "\"summary\":\"bounded explanation\"}.\n"
        f"Task card:\n{task_text}\nQuality evidence:\n{checks}\n{changes}"
    )


def _strict_review_verdict(result: CLIResult) -> tuple[str, str]:
    if not result.succeeded:
        raise RunLoopError(_adapter_failure("reviewer", result))
    value = result.parsed
    if isinstance(value, dict) and set(value) == {"verdict", "summary"}:
        report = value
    elif isinstance(value, dict) and isinstance(value.get("result"), str):
        try:
            nested = json.loads(value["result"])
        except json.JSONDecodeError as error:
            raise RunLoopError("reviewer verdict is malformed") from error
        if not isinstance(nested, dict) or set(nested) != {"verdict", "summary"}:
            raise RunLoopError("reviewer verdict has an invalid schema")
        report = nested
    else:
        raise RunLoopError("reviewer verdict has an invalid schema")
    verdict = report.get("verdict")
    summary = report.get("summary")
    if verdict not in {"APPROVE", "REQUEST_CHANGES"}:
        raise RunLoopError("reviewer verdict must be APPROVE or REQUEST_CHANGES")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 2000:
        raise RunLoopError("reviewer summary is missing or exceeds its bound")
    return verdict, summary.strip()


def _adapter_failure(role: str, result: CLIResult) -> str:
    return (
        f"{role.upper()}_FAILED: exit={result.exit_code} timeout={result.timed_out} "
        f"truncated={result.stdout_truncated or result.stderr_truncated} "
        f"parse_error={result.parse_error or '-'}"
    )[:1000]


def _quality_failure(
    evidence: Sequence[QualityEvidence], expected: Sequence[str]
) -> str:
    completed = ", ".join(
        f"{item.check_id}(exit={item.exit_code},timeout={item.timed_out})"
        for item in evidence
    )
    return f"QUALITY_FAILED: completed=[{completed}] expected={list(expected)}"[:1000]


def _handover(
    task_id: str,
    verified: VerifiedWorktree,
    quality: Sequence[QualityEvidence],
    attempts: int,
    review_summary: str,
) -> str:
    checks = "\n".join(
        f"  PASS {item.check_id} (exit {item.exit_code})" for item in quality
    )
    return (
        f"Task: {task_id}\n"
        f"Owner / branch: autonomous lease owner / {verified.branch}\n"
        "Status: READY_FOR_REVIEW\n"
        f"Scope / changed paths: {', '.join(verified.allowed_paths)}\n"
        f"Implemented: bounded autonomous loop candidate in {attempts} attempt(s)\n"
        "Contracts changed: none outside assigned task scope\n"
        f"Checks:\n{checks}\n"
        "Yocto verification: not attempted\n"
        "Security / data / license considerations: sandboxed workers and checks; no push/merge/deploy\n"
        f"Independent review: APPROVE — {review_summary}\n"
        "Known issues and remaining work: maintainer-controlled PR and integration remain\n"
        "Suggested next task: independent maintainer verification and PR preparation"
    )
