from __future__ import annotations

import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from orchestrator.database import connect, init_schema
from orchestrator.models import InvalidTransitionError, LeaseConflictError, TaskState
from orchestrator.scheduler import add_task, claim_task, get_history, get_task


class ConcurrencyTests(unittest.TestCase):
    def test_two_connections_racing_to_claim_have_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            db_path = base / "orchestrator.sqlite3"
            task_file = base / "task.md"
            task_file.write_text("# task\n", encoding="utf-8")
            setup = connect(db_path)
            init_schema(setup)
            add_task(
                setup,
                "KC-104",
                task_file,
                "https://github.com/example/repo/issues/104",
            )
            setup.close()
            barrier = threading.Barrier(2)

            def contender(worker: str) -> str:
                connection = connect(db_path)
                try:
                    barrier.wait(timeout=5)
                    claim_task(
                        connection,
                        "KC-104",
                        worker,
                        f"reviewer-{worker}",
                        300,
                    )
                    return "won"
                except (InvalidTransitionError, LeaseConflictError):
                    return "lost"
                finally:
                    connection.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(contender, ("worker-a", "worker-b")))

            verify = connect(db_path)
            try:
                self.assertEqual(["lost", "won"], sorted(results))
                self.assertEqual(TaskState.CLAIMED, get_task(verify, "KC-104").state)
                self.assertEqual(
                    1,
                    verify.execute(
                        "SELECT COUNT(*) FROM leases WHERE status = 'ACTIVE'"
                    ).fetchone()[0],
                )
                self.assertEqual(1, len(get_history(verify, "KC-104")))
            finally:
                verify.close()


if __name__ == "__main__":
    unittest.main()

