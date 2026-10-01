"""Legacy singleton correlation is never inferred from an ambiguous Action set."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from forge.serial_correlation_projection import project_serial_correlation


def state(actions=None, correlation=None):
    return SimpleNamespace(
        mission_id="MISSION-1", revision=7,
        actions=({"id": "ACTION-A", "status": "WAITING_FOR_RESULT"},) if actions is None else actions,
        execution_correlation=correlation,
    )


class SerialCorrelationProjectionTests(unittest.TestCase):
    def test_absent_correlation_is_unavailable(self) -> None:
        result = project_serial_correlation(state())
        self.assertEqual((result["binding_status"], result["reason"]), ("UNAVAILABLE", "NO_CORRELATION"))
        self.assertEqual(result["mission_revision"], 7)

    def test_direct_and_nested_request_bind_only_safe_identifiers(self) -> None:
        direct = project_serial_correlation(state(correlation={
            "mission_id": "MISSION-1", "action_id": "ACTION-A",
            "correlation_id": "corr-a", "host_run_id": "run-a",
            "secret_token": "sensitive-value",
        }))
        self.assertEqual(direct["binding_status"], "BOUND")
        self.assertEqual(direct["action_id"], "ACTION-A")
        self.assertEqual(direct["host_run_id"], "run-a")
        self.assertNotIn("sensitive-value", repr(direct))
        nested = project_serial_correlation(state(correlation={
            "request": {"mission_id": "MISSION-1", "action_id": "ACTION-A",
                        "correlation_id": "corr-a", "runtime_prompt": "sensitive-prompt"},
            "host_run_id": None,
        }))
        self.assertEqual(nested["binding_status"], "BOUND")
        self.assertIsNone(nested["host_run_id"])
        self.assertNotIn("sensitive-prompt", repr(nested))

    def test_one_active_action_among_two_is_exactly_bound(self) -> None:
        actions = ({"id": "ACTION-A", "status": "COMPLETE"},
                   {"id": "ACTION-B", "status": "ACTIVE"})
        result = project_serial_correlation(state(actions, {
            "mission_id": "MISSION-1", "action_id": "ACTION-B", "correlation_id": "corr-b",
        }))
        self.assertEqual((result["binding_status"], result["action_id"]), ("BOUND", "ACTION-B"))

    def test_multiple_or_unselected_actions_are_unsupported(self) -> None:
        two = ({"id": "ACTION-A", "status": "ACTIVE"},
               {"id": "ACTION-B", "status": "WAITING_FOR_RESULT"})
        result = project_serial_correlation(state(two, {"action_id": "ACTION-A", "correlation_id": "corr"}))
        self.assertEqual(result["reason"], "MULTIPLE_IN_FLIGHT_ACTIONS")
        idle = ({"id": "ACTION-A", "status": "READY"}, {"id": "ACTION-B", "status": "READY"})
        self.assertEqual(project_serial_correlation(state(idle, {"action_id": "ACTION-A"}))["reason"],
                         "AMBIGUOUS_ACTION_SET")
        self.assertEqual(project_serial_correlation(state((), {"action_id": "ACTION-A"}))["reason"],
                         "AMBIGUOUS_ACTION_SET")

    def test_malformed_and_conflicting_identities_fail_closed(self) -> None:
        self.assertEqual(project_serial_correlation(state(correlation=[]))["reason"], "MALFORMED_CORRELATION")
        self.assertEqual(project_serial_correlation(state(correlation={"request": []}))["reason"],
                         "MALFORMED_REQUEST")
        self.assertEqual(project_serial_correlation(state(correlation={"action_id": "ACTION-A",
                                                               "correlation_id": "corr-a", "request": {}}))["reason"],
                         "MALFORMED_REQUEST")
        conflict = {"action_id": "ACTION-A", "correlation_id": "corr-a",
                    "request": {"mission_id": "MISSION-1", "action_id": "ACTION-B",
                                "correlation_id": "corr-a"}}
        self.assertEqual(project_serial_correlation(state(correlation=conflict))["reason"], "IDENTITY_CONFLICT")
        for correlation in (
            {"mission_id": "MISSION-X", "action_id": "ACTION-A", "correlation_id": "corr"},
            {"action_id": "ACTION-A", "correlation_id": "corr"},
            {"action_id": "ACTION-X", "correlation_id": "corr"},
            {"action_id": "ACTION-A", "correlation_id": ""},
            {"action_id": "ACTION-A", "correlation_id": "bad value"},
            {"action_id": "ACTION-A", "correlation_id": "corr", "host_run_id": []},
        ):
            with self.subTest(correlation=correlation):
                self.assertEqual(project_serial_correlation(state(correlation=correlation))["reason"],
                                 "IDENTITY_UNVERIFIED")
        duplicate = ({"id": "ACTION-A", "status": "ACTIVE"}, {"id": "ACTION-A", "status": "READY"})
        self.assertEqual(project_serial_correlation(state(duplicate, {}))["reason"], "AMBIGUOUS_ACTION_SET")


if __name__ == "__main__":
    unittest.main()
