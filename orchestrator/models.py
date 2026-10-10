"""Pure models and state-transition policy for the v0 scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TaskState(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    REVIEW = "REVIEW"
    READY_FOR_PR = "READY_FOR_PR"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class LeaseStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"


ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.QUEUED: frozenset({TaskState.CLAIMED}),
    TaskState.CLAIMED: frozenset(
        {
            TaskState.RUNNING,
            TaskState.REVIEW,
            TaskState.BLOCKED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.RUNNING: frozenset(
        {TaskState.REVIEW, TaskState.BLOCKED, TaskState.FAILED}
    ),
    TaskState.REVIEW: frozenset(
        {
            TaskState.RUNNING,
            TaskState.READY_FOR_PR,
            TaskState.BLOCKED,
            TaskState.FAILED,
        }
    ),
}


def transition_allowed(prior: TaskState, next_state: TaskState) -> bool:
    return next_state in ALLOWED_TRANSITIONS.get(prior, frozenset())


@dataclass(frozen=True)
class Lease:
    id: int
    task_id: str
    owner: str
    reviewer: str
    lease_token: str
    issued_at: datetime
    expires_at: datetime
    heartbeat_at: datetime
    status: LeaseStatus


@dataclass(frozen=True)
class Task:
    id: str
    task_file: str
    issue_url: str
    state: TaskState
    created_at: datetime
    updated_at: datetime
    lease: Lease | None = None


@dataclass(frozen=True)
class Event:
    id: int
    task_id: str
    actor: str
    prior_state: TaskState
    next_state: TaskState
    reason: str | None
    created_at: datetime


@dataclass(frozen=True)
class Attempt:
    id: int
    task_id: str
    attempt_number: int
    worker: str
    phase: str
    started_at: datetime
    ended_at: datetime | None
    outcome: str | None
    log_location: str | None


class OrchestratorError(Exception):
    """Base class for expected scheduler failures."""


class TaskNotFoundError(OrchestratorError):
    pass


class DuplicateTaskError(OrchestratorError):
    pass


class InvalidTaskFileError(OrchestratorError):
    pass


class InvalidIssueUrlError(OrchestratorError):
    pass


class InvalidTransitionError(OrchestratorError):
    pass


class LeaseConflictError(OrchestratorError):
    pass


class WrongWorkerError(OrchestratorError):
    pass


class LeaseExpiredError(OrchestratorError):
    pass


class SchemaVersionError(OrchestratorError):
    pass


class InvalidInputError(OrchestratorError):
    pass


class WorktreeError(OrchestratorError):
    pass


class RunLoopError(OrchestratorError):
    pass

