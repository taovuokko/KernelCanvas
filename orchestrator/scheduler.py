"""Transactional scheduler operations over an open SQLite connection."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .models import (
    DuplicateTaskError,
    Event,
    InvalidInputError,
    InvalidIssueUrlError,
    InvalidTaskFileError,
    InvalidTransitionError,
    Lease,
    LeaseConflictError,
    LeaseExpiredError,
    LeaseStatus,
    Task,
    TaskNotFoundError,
    TaskState,
    WrongWorkerError,
    transition_allowed,
)

Clock = Callable[[], datetime]
MAX_LEASE_SECONDS = 7 * 24 * 60 * 60
MAX_LEASE_DURATION = timedelta(seconds=MAX_LEASE_SECONDS)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def add_task(
    connection: sqlite3.Connection,
    task_id: str,
    task_file: str | Path,
    issue_url: str,
    *,
    now_fn: Clock = utc_now,
) -> Task:
    task_id = _required_text(task_id, "task ID")
    task_path = Path(task_file)
    if not task_path.is_file():
        raise InvalidTaskFileError(f"task file does not exist or is not a file: {task_path}")
    _validate_issue_url(issue_url)
    now = _now(now_fn)
    stamp = _format_time(now)
    try:
        connection.execute(
            """
            INSERT INTO tasks(id, task_file, issue_url, state, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, str(task_path), issue_url, TaskState.QUEUED.value, stamp, stamp),
        )
    except sqlite3.IntegrityError as error:
        raise DuplicateTaskError(f"task already exists: {task_id}") from error
    return get_task(connection, task_id)


def get_task(connection: sqlite3.Connection, task_id: str) -> Task:
    row = connection.execute(
        """
        SELECT t.id, t.task_file, t.issue_url, t.state, t.created_at, t.updated_at,
               l.id AS lease_id, l.owner, l.reviewer, l.lease_token,
               l.issued_at, l.expires_at, l.heartbeat_at, l.status AS lease_status
        FROM tasks AS t
        LEFT JOIN leases AS l
          ON l.task_id = t.id AND l.status = 'ACTIVE'
        WHERE t.id = ?
        """,
        (task_id,),
    ).fetchone()
    if row is None:
        raise TaskNotFoundError(f"task not found: {task_id}")
    return _task_from_row(row)


def list_tasks(connection: sqlite3.Connection) -> list[Task]:
    rows = connection.execute(
        """
        SELECT t.id, t.task_file, t.issue_url, t.state, t.created_at, t.updated_at,
               l.id AS lease_id, l.owner, l.reviewer, l.lease_token,
               l.issued_at, l.expires_at, l.heartbeat_at, l.status AS lease_status
        FROM tasks AS t
        LEFT JOIN leases AS l
          ON l.task_id = t.id AND l.status = 'ACTIVE'
        ORDER BY t.created_at, t.id
        """
    ).fetchall()
    return [_task_from_row(row) for row in rows]


def claim_task(
    connection: sqlite3.Connection,
    task_id: str,
    worker: str,
    reviewer: str,
    lease_seconds: int,
    *,
    now_fn: Clock = utc_now,
) -> Lease:
    worker = _required_text(worker, "worker")
    reviewer = _required_text(reviewer, "reviewer")
    if worker == reviewer:
        raise InvalidInputError("worker and reviewer must be different")
    duration = _validate_requested_lease_duration(lease_seconds)
    now = _now(now_fn)
    expires = _lease_expiry(now, duration)
    token = uuid.uuid4().hex

    connection.execute("BEGIN IMMEDIATE")
    try:
        row = connection.execute("SELECT state FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise TaskNotFoundError(f"task not found: {task_id}")
        prior = TaskState(row["state"])
        if not transition_allowed(prior, TaskState.CLAIMED):
            raise InvalidTransitionError(
                f"cannot transition task {task_id} from {prior.value} to CLAIMED"
            )
        cursor = connection.execute(
            """
            INSERT INTO leases(
                task_id, owner, reviewer, lease_token, issued_at,
                expires_at, heartbeat_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                worker,
                reviewer,
                token,
                _format_time(now),
                _format_time(expires),
                _format_time(now),
                LeaseStatus.ACTIVE.value,
            ),
        )
        connection.execute(
            "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
            (TaskState.CLAIMED.value, _format_time(now), task_id),
        )
        _insert_event(
            connection,
            task_id,
            worker,
            prior,
            TaskState.CLAIMED,
            "task claimed",
            now,
        )
        connection.execute("COMMIT")
    except sqlite3.IntegrityError as error:
        _rollback(connection)
        raise LeaseConflictError(f"task already has an active lease: {task_id}") from error
    except Exception:
        _rollback(connection)
        raise

    return Lease(
        id=int(cursor.lastrowid),
        task_id=task_id,
        owner=worker,
        reviewer=reviewer,
        lease_token=token,
        issued_at=now,
        expires_at=expires,
        heartbeat_at=now,
        status=LeaseStatus.ACTIVE,
    )


def heartbeat_task(
    connection: sqlite3.Connection,
    task_id: str,
    worker: str,
    *,
    now_fn: Clock = utc_now,
) -> Lease:
    worker = _required_text(worker, "worker")
    now = _now(now_fn)
    connection.execute("BEGIN IMMEDIATE")
    try:
        _require_task(connection, task_id)
        row = _active_lease_row(connection, task_id)
        _validate_live_owner(row, task_id, worker, now)
        old_heartbeat = _parse_time(row["heartbeat_at"])
        old_expiry = _parse_time(row["expires_at"])
        duration = old_expiry - old_heartbeat
        _validate_stored_lease_duration(duration, task_id)
        new_expiry = _lease_expiry(now, duration)
        connection.execute(
            "UPDATE leases SET heartbeat_at = ?, expires_at = ? WHERE id = ?",
            (_format_time(now), _format_time(new_expiry), row["id"]),
        )
        connection.execute("COMMIT")
    except Exception:
        _rollback(connection)
        raise
    return _lease_from_row(row, heartbeat_at=now, expires_at=new_expiry)


def release_task(
    connection: sqlite3.Connection,
    task_id: str,
    worker: str,
    next_state: TaskState | str,
    reason: str,
    *,
    now_fn: Clock = utc_now,
) -> Event:
    worker = _required_text(worker, "worker")
    reason = _required_text(reason, "reason")
    try:
        target = next_state if isinstance(next_state, TaskState) else TaskState(next_state)
    except ValueError as error:
        raise InvalidTransitionError(f"unknown target state: {next_state}") from error
    if target not in {TaskState.REVIEW, TaskState.BLOCKED, TaskState.FAILED}:
        raise InvalidTransitionError(f"release target is not allowed in v0: {target.value}")

    now = _now(now_fn)
    connection.execute("BEGIN IMMEDIATE")
    try:
        prior = _require_task(connection, task_id)
        row = _active_lease_row(connection, task_id)
        _validate_live_owner(row, task_id, worker, now)
        if not transition_allowed(prior, target):
            raise InvalidTransitionError(
                f"cannot transition task {task_id} from {prior.value} to {target.value}"
            )
        connection.execute(
            "UPDATE leases SET status = ? WHERE id = ?",
            (LeaseStatus.RELEASED.value, row["id"]),
        )
        connection.execute(
            "UPDATE tasks SET state = ?, updated_at = ? WHERE id = ?",
            (target.value, _format_time(now), task_id),
        )
        event_id = _insert_event(connection, task_id, worker, prior, target, reason, now)
        connection.execute("COMMIT")
    except Exception:
        _rollback(connection)
        raise
    return Event(event_id, task_id, worker, prior, target, reason, now)


def get_history(connection: sqlite3.Connection, task_id: str) -> list[Event]:
    _require_task(connection, task_id)
    rows = connection.execute(
        """
        SELECT id, task_id, actor, prior_state, next_state, reason, created_at
        FROM events WHERE task_id = ? ORDER BY id
        """,
        (task_id,),
    ).fetchall()
    return [
        Event(
            id=row["id"],
            task_id=row["task_id"],
            actor=row["actor"],
            prior_state=TaskState(row["prior_state"]),
            next_state=TaskState(row["next_state"]),
            reason=row["reason"],
            created_at=_parse_time(row["created_at"]),
        )
        for row in rows
    ]


def _validate_issue_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise InvalidIssueUrlError(f"malformed issue URL: {value}") from error
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise InvalidIssueUrlError("issue URL must be an HTTPS URL without embedded credentials")
    if port is not None and not 1 <= port <= 65535:
        raise InvalidIssueUrlError(f"malformed issue URL port: {port}")


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise InvalidInputError(f"{label} must not be empty")
    return normalized


def _validate_requested_lease_duration(lease_seconds: int) -> timedelta:
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool):
        raise InvalidInputError("lease seconds must be an integer")
    if not 1 <= lease_seconds <= MAX_LEASE_SECONDS:
        raise InvalidInputError(
            f"lease seconds must be between 1 and {MAX_LEASE_SECONDS}"
        )
    return timedelta(seconds=lease_seconds)


def _validate_stored_lease_duration(duration: timedelta, task_id: str) -> None:
    if not timedelta(0) < duration <= MAX_LEASE_DURATION:
        raise InvalidInputError(
            f"stored lease duration for {task_id} must be greater than zero "
            f"and no more than {MAX_LEASE_SECONDS} seconds"
        )


def _lease_expiry(now: datetime, duration: timedelta) -> datetime:
    try:
        return now + duration
    except OverflowError as error:
        raise InvalidInputError(
            "lease expiry is outside the supported datetime range"
        ) from error


def _now(now_fn: Clock) -> datetime:
    value = now_fn()
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidInputError("clock must return a timezone-aware UTC datetime")
    return value.astimezone(timezone.utc)


def _format_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("stored timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def _require_task(connection: sqlite3.Connection, task_id: str) -> TaskState:
    row = connection.execute("SELECT state FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise TaskNotFoundError(f"task not found: {task_id}")
    return TaskState(row["state"])


def _active_lease_row(connection: sqlite3.Connection, task_id: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM leases WHERE task_id = ? AND status = 'ACTIVE'",
        (task_id,),
    ).fetchone()
    if row is None:
        raise LeaseConflictError(f"task has no active lease: {task_id}")
    return row


def _validate_live_owner(
    row: sqlite3.Row, task_id: str, worker: str, now: datetime
) -> None:
    if row["owner"] != worker:
        raise WrongWorkerError(f"active lease for {task_id} belongs to {row['owner']}")
    if now > _parse_time(row["expires_at"]):
        raise LeaseExpiredError(
            f"lease for {task_id} expired at {row['expires_at']}; manual recovery required"
        )


def _insert_event(
    connection: sqlite3.Connection,
    task_id: str,
    actor: str,
    prior: TaskState,
    target: TaskState,
    reason: str | None,
    when: datetime,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO events(task_id, actor, prior_state, next_state, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, actor, prior.value, target.value, reason, _format_time(when)),
    )
    return int(cursor.lastrowid)


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")


def _task_from_row(row: sqlite3.Row) -> Task:
    lease = None
    if row["lease_id"] is not None:
        lease = Lease(
            id=row["lease_id"],
            task_id=row["id"],
            owner=row["owner"],
            reviewer=row["reviewer"],
            lease_token=row["lease_token"],
            issued_at=_parse_time(row["issued_at"]),
            expires_at=_parse_time(row["expires_at"]),
            heartbeat_at=_parse_time(row["heartbeat_at"]),
            status=LeaseStatus(row["lease_status"]),
        )
    return Task(
        id=row["id"],
        task_file=row["task_file"],
        issue_url=row["issue_url"],
        state=TaskState(row["state"]),
        created_at=_parse_time(row["created_at"]),
        updated_at=_parse_time(row["updated_at"]),
        lease=lease,
    )


def _lease_from_row(
    row: sqlite3.Row, *, heartbeat_at: datetime, expires_at: datetime
) -> Lease:
    return Lease(
        id=row["id"],
        task_id=row["task_id"],
        owner=row["owner"],
        reviewer=row["reviewer"],
        lease_token=row["lease_token"],
        issued_at=_parse_time(row["issued_at"]),
        expires_at=expires_at,
        heartbeat_at=heartbeat_at,
        status=LeaseStatus(row["status"]),
    )

