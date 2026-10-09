from __future__ import annotations

import tempfile
import unittest
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator.database import connect, init_schema
from orchestrator.models import (
    DuplicateTaskError,
    InvalidInputError,
    InvalidIssueUrlError,
    InvalidTaskFileError,
    InvalidTransitionError,
    LeaseConflictError,
    LeaseExpiredError,
    LeaseStatus,
    TaskNotFoundError,
    TaskState,
    WrongWorkerError,
)
from orchestrator.scheduler import (
    MAX_LEASE_SECONDS,
    add_task,
    claim_task,
    get_history,
    get_task,
    heartbeat_task,
    list_tasks,
    release_task,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.connection = connect(base / "orchestrator.sqlite3")
        self.addCleanup(self.connection.close)
        init_schema(self.connection)
        self.task_file = base / "KC-104.md"
        self.task_file.write_text("# test task\n", encoding="utf-8")
        self.clock = FakeClock()

    def add(self, task_id: str = "KC-104"):
        return add_task(
            self.connection,
            task_id,
            self.task_file,
            "https://github.com/example/KernelCanvas/issues/104",
            now_fn=self.clock,
        )

    def claim(self, task_id: str = "KC-104", worker: str = "worker"):
        return claim_task(
            self.connection,
            task_id,
            worker,
            "reviewer",
            60,
            now_fn=self.clock,
        )

    def test_add_get_and_list_round_trip(self) -> None:
        added = self.add()
        loaded = get_task(self.connection, "KC-104")
        self.assertEqual(added, loaded)
        self.assertEqual([loaded], list_tasks(self.connection))
        self.assertEqual(TaskState.QUEUED, loaded.state)

    def test_duplicate_id_is_rejected(self) -> None:
        self.add()
        with self.assertRaises(DuplicateTaskError):
            self.add()

    def test_missing_task_file_is_rejected(self) -> None:
        with self.assertRaises(InvalidTaskFileError):
            add_task(
                self.connection,
                "KC-404",
                self.task_file.parent / "missing.md",
                "https://github.com/example/repo/issues/404",
            )

    def test_malformed_or_credentialed_issue_url_is_rejected(self) -> None:
        for url in (
            "not-a-url",
            "http://github.com/example/repo/issues/1",
            "https://token@github.com/example/repo/issues/1",
            "https://github.com:99999/example/repo/issues/1",
        ):
            with self.subTest(url=url), self.assertRaises(InvalidIssueUrlError):
                add_task(self.connection, "KC-X", self.task_file, url)

    def test_unknown_task_is_rejected(self) -> None:
        with self.assertRaises(TaskNotFoundError):
            get_task(self.connection, "KC-404")
        with self.assertRaises(TaskNotFoundError):
            claim_task(self.connection, "KC-404", "worker", "reviewer", 60)

    def test_claim_creates_exactly_one_active_lease_and_event(self) -> None:
        self.add()
        lease = self.claim()
        task = get_task(self.connection, "KC-104")
        history = get_history(self.connection, "KC-104")
        self.assertEqual(TaskState.CLAIMED, task.state)
        self.assertEqual(LeaseStatus.ACTIVE, lease.status)
        self.assertEqual("worker", task.lease.owner)
        self.assertEqual(1, len(history))
        self.assertEqual(TaskState.QUEUED, history[0].prior_state)
        self.assertEqual(TaskState.CLAIMED, history[0].next_state)

    def test_worker_reviewer_and_duration_are_validated_before_transaction(self) -> None:
        self.add()
        for worker, reviewer, seconds in (
            ("same", "same", 60),
            ("", "reviewer", 60),
            ("worker", "", 60),
            ("worker", "reviewer", 0),
        ):
            with self.subTest(
                worker=worker, reviewer=reviewer, seconds=seconds
            ), self.assertRaises(InvalidInputError):
                claim_task(
                    self.connection,
                    "KC-104",
                    worker,
                    reviewer,
                    seconds,
                    now_fn=self.clock,
                )
        self.assertFalse(self.connection.in_transaction)
        self.assertEqual(TaskState.QUEUED, get_task(self.connection, "KC-104").state)

    def test_oversized_lease_duration_is_rejected_without_overflow(self) -> None:
        self.add()
        for seconds in (MAX_LEASE_SECONDS + 1, 10**100):
            with self.subTest(seconds=seconds), self.assertRaisesRegex(
                InvalidInputError, "lease seconds"
            ):
                claim_task(
                    self.connection,
                    "KC-104",
                    "worker",
                    "reviewer",
                    seconds,
                    now_fn=self.clock,
                )
        self.assertFalse(self.connection.in_transaction)
        self.assertEqual(TaskState.QUEUED, get_task(self.connection, "KC-104").state)

    def test_claim_rejects_expiry_outside_datetime_range(self) -> None:
        self.add()
        self.clock.value = datetime.max.replace(tzinfo=timezone.utc)
        with self.assertRaisesRegex(InvalidInputError, "datetime range"):
            claim_task(
                self.connection,
                "KC-104",
                "worker",
                "reviewer",
                1,
                now_fn=self.clock,
            )
        self.assertFalse(self.connection.in_transaction)
        self.assertEqual(TaskState.QUEUED, get_task(self.connection, "KC-104").state)

    def test_second_claim_is_rejected_without_partial_write(self) -> None:
        self.add()
        self.claim()
        with self.assertRaises(InvalidTransitionError):
            claim_task(
                self.connection,
                "KC-104",
                "other-worker",
                "other-reviewer",
                60,
                now_fn=self.clock,
            )
        self.assertFalse(self.connection.in_transaction)
        self.assertEqual(1, self.connection.execute("SELECT COUNT(*) FROM leases").fetchone()[0])
        self.assertEqual(1, self.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def test_heartbeat_extends_expiry_by_original_period(self) -> None:
        self.add()
        original = self.claim()
        self.clock.advance(30)
        renewed = heartbeat_task(
            self.connection, "KC-104", "worker", now_fn=self.clock
        )
        self.assertEqual(original.expires_at + timedelta(seconds=30), renewed.expires_at)
        self.assertEqual(self.clock.value, renewed.heartbeat_at)

    def test_heartbeat_rejects_oversized_stored_duration(self) -> None:
        self.add()
        self.claim()
        oversized_expiry = self.clock.value + timedelta(
            seconds=MAX_LEASE_SECONDS + 1
        )
        self.connection.execute(
            "UPDATE leases SET expires_at = ? WHERE task_id = ?",
            (oversized_expiry.isoformat(), "KC-104"),
        )

        with self.assertRaisesRegex(InvalidInputError, "stored lease duration"):
            heartbeat_task(
                self.connection, "KC-104", "worker", now_fn=self.clock
            )
        self.assertFalse(self.connection.in_transaction)

    def test_heartbeat_rejects_expiry_outside_datetime_range(self) -> None:
        self.add()
        self.clock.value = datetime.max.replace(tzinfo=timezone.utc) - timedelta(
            seconds=60
        )
        self.claim()
        self.clock.advance(30)

        with self.assertRaisesRegex(InvalidInputError, "datetime range"):
            heartbeat_task(
                self.connection, "KC-104", "worker", now_fn=self.clock
            )
        self.assertFalse(self.connection.in_transaction)

    def test_timezone_naive_clock_is_rejected(self) -> None:
        with self.assertRaisesRegex(InvalidInputError, "timezone-aware"):
            add_task(
                self.connection,
                "KC-NAIVE",
                self.task_file,
                "https://github.com/example/repo/issues/105",
                now_fn=lambda: datetime(2026, 1, 2, 3, 4, 5),
            )
        with self.assertRaises(TaskNotFoundError):
            get_task(self.connection, "KC-NAIVE")

    def test_wrong_worker_and_expired_heartbeat_are_rejected(self) -> None:
        self.add()
        self.claim()
        with self.assertRaises(WrongWorkerError):
            heartbeat_task(
                self.connection, "KC-104", "intruder", now_fn=self.clock
            )
        self.clock.advance(61)
        with self.assertRaises(LeaseExpiredError):
            heartbeat_task(self.connection, "KC-104", "worker", now_fn=self.clock)
        self.assertEqual(TaskState.CLAIMED, get_task(self.connection, "KC-104").state)
        self.assertEqual(LeaseStatus.ACTIVE, get_task(self.connection, "KC-104").lease.status)

    def test_release_updates_state_lease_and_ordered_history(self) -> None:
        self.add()
        self.claim()
        self.clock.advance(10)
        event = release_task(
            self.connection,
            "KC-104",
            "worker",
            TaskState.REVIEW,
            "candidate ready",
            now_fn=self.clock,
        )
        task = get_task(self.connection, "KC-104")
        history = get_history(self.connection, "KC-104")
        lease_status = self.connection.execute(
            "SELECT status FROM leases WHERE task_id = 'KC-104'"
        ).fetchone()[0]
        self.assertEqual(TaskState.REVIEW, task.state)
        self.assertIsNone(task.lease)
        self.assertEqual(LeaseStatus.RELEASED.value, lease_status)
        self.assertEqual(event, history[-1])
        self.assertEqual([1, 2], [item.id for item in history])
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.connection.execute("UPDATE events SET reason = 'changed' WHERE id = 1")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.connection.execute("DELETE FROM events WHERE id = 1")

    def test_release_rejects_wrong_owner_expiry_invalid_target_and_double_release(self) -> None:
        self.add()
        self.claim()
        with self.assertRaises(WrongWorkerError):
            release_task(
                self.connection,
                "KC-104",
                "intruder",
                TaskState.REVIEW,
                "no",
                now_fn=self.clock,
            )
        with self.assertRaises(InvalidTransitionError):
            release_task(
                self.connection,
                "KC-104",
                "worker",
                TaskState.DONE,
                "no",
                now_fn=self.clock,
            )
        self.clock.advance(61)
        with self.assertRaises(LeaseExpiredError):
            release_task(
                self.connection,
                "KC-104",
                "worker",
                TaskState.REVIEW,
                "too late",
                now_fn=self.clock,
            )

        self.clock.value -= timedelta(seconds=2)
        heartbeat_row = self.connection.execute(
            "SELECT expires_at FROM leases WHERE task_id = 'KC-104'"
        ).fetchone()[0]
        # Use the exact expiry boundary, which remains a live lease.
        self.clock.value = datetime.fromisoformat(heartbeat_row)
        release_task(
            self.connection,
            "KC-104",
            "worker",
            TaskState.REVIEW,
            "ready",
            now_fn=self.clock,
        )
        with self.assertRaises(LeaseConflictError):
            release_task(
                self.connection,
                "KC-104",
                "worker",
                TaskState.FAILED,
                "again",
                now_fn=self.clock,
            )

    def test_history_unknown_task_is_rejected(self) -> None:
        with self.assertRaises(TaskNotFoundError):
            get_history(self.connection, "KC-404")


if __name__ == "__main__":
    unittest.main()

