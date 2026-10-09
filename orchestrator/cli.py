"""Command-line interface for the v0 local scheduler."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Sequence, TextIO

from . import database, scheduler
from .models import (
    DuplicateTaskError,
    InvalidInputError,
    InvalidIssueUrlError,
    InvalidTaskFileError,
    InvalidTransitionError,
    LeaseConflictError,
    LeaseExpiredError,
    OrchestratorError,
    SchemaVersionError,
    Task,
    TaskNotFoundError,
    TaskState,
    WrongWorkerError,
)


class ExitCode(IntEnum):
    SUCCESS = 0
    USAGE = 2
    NOT_FOUND = 3
    INVALID_INPUT = 4
    INVALID_TRANSITION = 5
    LEASE_ERROR = 6
    DATABASE_ERROR = 7


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m orchestrator",
        description="KernelCanvas local development-task scheduler (v0)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="initialize the local scheduler database")

    add = commands.add_parser("add", help="register a task in QUEUED state")
    add.add_argument("task_id", metavar="TASK_ID")
    add.add_argument("--task-file", required=True)
    add.add_argument("--issue-url", required=True)

    status = commands.add_parser("status", help="show one task or list all tasks")
    status.add_argument("task_id", metavar="TASK_ID", nargs="?")

    claim = commands.add_parser("claim", help="atomically claim a queued task")
    claim.add_argument("task_id", metavar="TASK_ID")
    claim.add_argument("--worker", required=True)
    claim.add_argument("--reviewer", required=True)
    claim.add_argument("--lease-seconds", type=int, required=True)

    heartbeat = commands.add_parser("heartbeat", help="renew the owner's live lease")
    heartbeat.add_argument("task_id", metavar="TASK_ID")
    heartbeat.add_argument("--worker", required=True)

    release = commands.add_parser("release", help="release a task to a v0 terminal state")
    release.add_argument("task_id", metavar="TASK_ID")
    release.add_argument("--worker", required=True)
    release.add_argument(
        "--to",
        required=True,
        choices=[TaskState.REVIEW.value, TaskState.BLOCKED.value, TaskState.FAILED.value],
    )
    release.add_argument("--reason", required=True)

    history = commands.add_parser("history", help="show ordered transition history")
    history.add_argument("task_id", metavar="TASK_ID")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    db_path = database.resolve_db_path()
    try:
        if args.command == "init":
            db_path.parent.mkdir(parents=True, exist_ok=True)
            connection = database.connect(db_path)
            try:
                database.init_schema(connection)
            finally:
                connection.close()
            print(f"initialized schema v1 at {db_path}", file=output)
            return ExitCode.SUCCESS

        connection = _open_existing_database(db_path)
        try:
            database.check_schema_version(connection)
            return _run_command(args, connection, output)
        finally:
            connection.close()
    except (TaskNotFoundError, FileNotFoundError) as error:
        print(f"error: {error}", file=errors)
        return ExitCode.NOT_FOUND
    except (
        DuplicateTaskError,
        InvalidTaskFileError,
        InvalidIssueUrlError,
        InvalidInputError,
    ) as error:
        print(f"error: {error}", file=errors)
        return ExitCode.INVALID_INPUT
    except InvalidTransitionError as error:
        print(f"error: {error}", file=errors)
        return ExitCode.INVALID_TRANSITION
    except (LeaseConflictError, WrongWorkerError, LeaseExpiredError) as error:
        print(f"error: {error}", file=errors)
        return ExitCode.LEASE_ERROR
    except (SchemaVersionError, sqlite3.Error, OSError) as error:
        print(f"database error: {error}", file=errors)
        return ExitCode.DATABASE_ERROR
    except OrchestratorError as error:
        print(f"error: {error}", file=errors)
        return ExitCode.INVALID_INPUT


def _open_existing_database(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(
            f"database not found at {path}; run 'python3 -m orchestrator init'"
        )
    return database.connect(path)


def _run_command(
    args: argparse.Namespace, connection: sqlite3.Connection, output: TextIO
) -> int:
    if args.command == "add":
        task = scheduler.add_task(
            connection, args.task_id, args.task_file, args.issue_url
        )
        print(f"added {task.id} state={task.state.value}", file=output)
    elif args.command == "status":
        tasks = (
            [scheduler.get_task(connection, args.task_id)]
            if args.task_id
            else scheduler.list_tasks(connection)
        )
        if not tasks:
            print("no tasks", file=output)
        for task in tasks:
            print(_format_task(task), file=output)
    elif args.command == "claim":
        lease = scheduler.claim_task(
            connection,
            args.task_id,
            args.worker,
            args.reviewer,
            args.lease_seconds,
        )
        print(
            f"claimed {lease.task_id} owner={lease.owner} reviewer={lease.reviewer} "
            f"expires={lease.expires_at.isoformat()}",
            file=output,
        )
    elif args.command == "heartbeat":
        lease = scheduler.heartbeat_task(connection, args.task_id, args.worker)
        print(
            f"heartbeat {lease.task_id} owner={lease.owner} "
            f"expires={lease.expires_at.isoformat()}",
            file=output,
        )
    elif args.command == "release":
        event = scheduler.release_task(
            connection, args.task_id, args.worker, args.to, args.reason
        )
        print(
            f"released {event.task_id} state={event.next_state.value} actor={event.actor}",
            file=output,
        )
    elif args.command == "history":
        events = scheduler.get_history(connection, args.task_id)
        if not events:
            print(f"no events for {args.task_id}", file=output)
        for event in events:
            reason = f" reason={event.reason}" if event.reason else ""
            print(
                f"{event.created_at.isoformat()} {event.actor} "
                f"{event.prior_state.value}->{event.next_state.value}{reason}",
                file=output,
            )
    return ExitCode.SUCCESS


def _format_task(task: Task) -> str:
    age = max(0, int((datetime.now(timezone.utc) - task.updated_at).total_seconds()))
    owner = task.lease.owner if task.lease else "-"
    reviewer = task.lease.reviewer if task.lease else "-"
    return (
        f"{task.id} state={task.state.value} owner={owner} reviewer={reviewer} "
        f"age={age}s"
    )

