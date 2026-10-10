from __future__ import annotations

import unittest

from orchestrator.models import LeaseStatus, TaskState, transition_allowed


class ModelTests(unittest.TestCase):
    def test_enum_values_round_trip(self) -> None:
        for state in TaskState:
            self.assertIs(state, TaskState(state.value))
        for status in LeaseStatus:
            self.assertIs(status, LeaseStatus(status.value))

    def test_v0_transition_table(self) -> None:
        self.assertTrue(transition_allowed(TaskState.QUEUED, TaskState.CLAIMED))
        self.assertTrue(transition_allowed(TaskState.CLAIMED, TaskState.REVIEW))
        self.assertTrue(transition_allowed(TaskState.CLAIMED, TaskState.BLOCKED))
        self.assertTrue(transition_allowed(TaskState.CLAIMED, TaskState.FAILED))
        self.assertTrue(transition_allowed(TaskState.CLAIMED, TaskState.RUNNING))
        self.assertTrue(transition_allowed(TaskState.RUNNING, TaskState.REVIEW))
        self.assertTrue(transition_allowed(TaskState.REVIEW, TaskState.RUNNING))
        self.assertTrue(transition_allowed(TaskState.REVIEW, TaskState.READY_FOR_PR))
        self.assertFalse(transition_allowed(TaskState.QUEUED, TaskState.REVIEW))
        self.assertFalse(transition_allowed(TaskState.CLAIMED, TaskState.DONE))
        self.assertFalse(transition_allowed(TaskState.REVIEW, TaskState.DONE))


if __name__ == "__main__":
    unittest.main()

