"""Logical frontier validation does not promote stored Actions to executable work."""
from __future__ import annotations

import unittest

from forge.action_frontier import ActionFrontierError, project_action_frontier


def action(order: int, action_id: str, *, status: str = "READY",
           dependencies: tuple[str, ...] = ()) -> dict:
    return {"order": order, "id": action_id, "status": status, "dependencies": dependencies}


class ActionFrontierTests(unittest.TestCase):
    def test_zero_one_and_independent_multiple_actions_are_logical_only(self) -> None:
        empty = project_action_frontier((), mission_revision=1)
        self.assertEqual(empty["logical_frontier_action_ids"], [])
        one = project_action_frontier((action(1, "A"),), mission_revision=2)
        self.assertEqual(one["logical_frontier_action_ids"], ["A"])
        multiple = project_action_frontier((action(2, "B"), action(1, "A")), mission_revision=3)
        self.assertEqual(multiple["logical_frontier_action_ids"], ["A", "B"])
        self.assertEqual([item["action_id"] for item in multiple["actions"]], ["A", "B"])
        self.assertTrue(all(not item["dispatchable"] for item in multiple["actions"]))
        self.assertTrue(all(item["target_resolution"] == "UNAVAILABLE" for item in multiple["actions"]))
        self.assertEqual(multiple["parallel_execution"], "NOT_QUALIFIED")

    def test_hard_edges_wait_for_completion_and_verified_evidence(self) -> None:
        waiting = project_action_frontier((action(1, "A", status="ACTIVE"),
                                           action(2, "B", dependencies=("A",))), mission_revision=1)
        self.assertEqual(waiting["actions"][1]["logical_state"], "WAITING_FOR_PREDECESSOR")
        completed = project_action_frontier((action(1, "A", status="COMPLETE"),
                                             action(2, "B", dependencies=("A",))), mission_revision=2)
        self.assertEqual(completed["actions"][1]["logical_state"], "WAITING_FOR_VERIFIED_EVIDENCE")
        self.assertEqual(completed["logical_frontier_action_ids"], [])
        failed = project_action_frontier((action(1, "A", status="FAILED"),
                                          action(2, "B", dependencies=("A",))), mission_revision=3)
        self.assertEqual(failed["actions"][1]["logical_state"], "BLOCKED_BY_PREDECESSOR")

    def test_malformed_or_cyclic_graph_fails_closed(self) -> None:
        invalid = (
            (action(1, "A"), action(2, "A")),
            (action(1, "A"), action(1, "B")),
            (action(1, "A", dependencies=("B",)),),
            (action(1, "A", dependencies=("B",)), action(2, "B", dependencies=("A",))),
            (action(1, "A", dependencies=("A",)),),
            (action(1, "A", status="UNKNOWN"),),
            (action(1, "A", status=[]),),
        )
        for graph in invalid:
            with self.subTest(graph=graph), self.assertRaises(ActionFrontierError):
                project_action_frontier(graph, mission_revision=1)
        with self.assertRaises(ActionFrontierError):
            project_action_frontier((action(1, "A"),) * 257, mission_revision=1)
        with self.assertRaises(ActionFrontierError):
            project_action_frontier((), mission_revision=0)
