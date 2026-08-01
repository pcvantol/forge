"""Tests for evidence-gated, sequential Bootstrap Mission Scheduler behavior."""

from __future__ import annotations

import unittest

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.scheduler import BootstrapMissionScheduler, RepositoryEvidence


def action(order: int, identifier: str, dependencies: tuple[str, ...] = ()) -> EngineeringAction:
    return EngineeringAction(order, identifier, "intent-1", "1", identifier, ("repository evidence",), dependencies)


def evidence(identifier: str) -> RepositoryEvidence:
    return RepositoryEvidence(identifier, "abc123", f"report-{identifier}", "sha256:" + "a" * 64)


class BootstrapMissionSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = BootstrapMissionScheduler()

    def test_sequential_actions_wait_for_repository_evidence(self) -> None:
        initial = (action(1, "action-1"), action(2, "action-2", ("action-1",)))
        active = self.scheduler.activate(initial)
        waiting = self.scheduler.await_result(active, "action-1")
        self.assertIsNone(self.scheduler.next_action(waiting))
        with self.assertRaisesRegex(ValueError, "repository evidence"):
            self.scheduler.complete(waiting, "action-1", ())
        complete = self.scheduler.complete(waiting, "action-1", (evidence("action-1"),))
        self.assertEqual(self.scheduler.next_action(complete).id, "action-2")
        self.assertEqual(self.scheduler.progress(complete).percent_complete, 50)

    def test_dependency_enforcement_and_deterministic_selection(self) -> None:
        actions = (action(2, "later"), action(1, "first"), action(3, "dependent", ("later",)))
        self.assertEqual(self.scheduler.next_action(actions).id, "first")
        active = self.scheduler.activate(actions)
        self.assertEqual(next(item for item in active if item.status is EngineeringActionStatus.ACTIVE).id, "first")
        with self.assertRaisesRegex(ValueError, "only one"):
            self.scheduler.next_action((
                EngineeringAction(1, "one", "intent", "1", "one", ("evidence",), status=EngineeringActionStatus.ACTIVE),
                EngineeringAction(2, "two", "intent", "1", "two", ("evidence",), status=EngineeringActionStatus.WAITING_FOR_RESULT),
            ))

    def test_blocked_predecessor_stops_progression(self) -> None:
        actions = self.scheduler.await_result(self.scheduler.activate((action(1, "one"), action(2, "two", ("one",)))), "one")
        stopped = self.scheduler.stop(actions, "one", EngineeringActionStatus.BLOCKED)
        self.assertIsNone(self.scheduler.next_action(stopped))
        self.assertEqual(self.scheduler.progress(stopped).terminal_state, EngineeringActionStatus.BLOCKED)

    def test_failed_predecessor_stops_progression(self) -> None:
        actions = self.scheduler.await_result(self.scheduler.activate((action(1, "one"), action(2, "two", ("one",)))), "one")
        stopped = self.scheduler.stop(actions, "one", EngineeringActionStatus.FAILED)
        self.assertIsNone(self.scheduler.next_action(stopped))
        self.assertEqual(self.scheduler.progress(stopped).terminal_state, EngineeringActionStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
