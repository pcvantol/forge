"""Regression coverage for Forge-owned Integration Coordination."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.integration import IntegrationCoordinator, IntegrationEvidenceRepository
from forge.models.integration import IntegrationEventKind, IntegrationUnit
from forge.state import MissionExecutionStatus, MissionStateStore


def unit(identifier: str, *, scope: tuple[str, ...] = ("forge/models",), commit: str | None = None,
         validated: bool = True) -> IntegrationUnit:
    return IntegrationUnit(identifier, "mission-integration", f"action-{identifier}", f"receipt-{identifier}",
                           commit or f"commit-{identifier}", f"branch-{identifier}", scope,
                           (("host", "reference-host"), ("runtime", "local")), (f"decision-{identifier}",),
                           validation_passed=validated, required_approvals_satisfied=True)


class IntegrationCoordinationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        root = Path(self.directory.name)
        self.states = MissionStateStore(root / "mission-state.sqlite")
        self.states.create({"id": "mission-integration"}, ({"id": "intent"},), ({"id": "action", "status": "COMPLETE"},), occurred_at="2026-08-05T08:00:00Z")
        self.states.transition("mission-integration", MissionExecutionStatus.READY, occurred_at="2026-08-05T08:00:00Z", reason="planned")
        self.states.transition("mission-integration", MissionExecutionStatus.ACTIVE, occurred_at="2026-08-05T08:00:00Z", reason="execution_complete")
        self.evidence = IntegrationEvidenceRepository(root / "integration-evidence.sqlite")
        self.coordinator = IntegrationCoordinator(self.evidence, integration_id_factory=lambda mission_id, units: f"integration-{mission_id}-{'-'.join(item.id for item in units)}")

    def tearDown(self) -> None:
        self.evidence.close(); self.states.close(); self.directory.cleanup()

    def test_parallel_units_are_ordered_merge_ready_and_persist_immutable_evidence(self) -> None:
        result = self.coordinator.coordinate(self.states, "mission-integration", (unit("b", scope=("docs",)), unit("a", scope=("forge",))), timestamp="2026-08-05T08:01:00Z")
        self.assertEqual(result.event, IntegrationEventKind.INTEGRATION_COMPLETE)
        self.assertEqual(self.states.get("mission-integration").status, MissionExecutionStatus.INTEGRATION_COMPLETE)
        self.assertEqual(tuple(item.id for item in result.evidence.integration_units), ("a", "b"))
        self.assertEqual(tuple(item.id for item in self.evidence.list_for_mission("mission-integration")), (result.evidence.id,))
        with self.assertRaises(Exception):
            self.evidence._connection.execute("UPDATE integration_evidence SET document = '{}' ")  # noqa: SLF001

    def test_readiness_failure_pauses_integration_without_a_merge_attempt(self) -> None:
        result = self.coordinator.coordinate(self.states, "mission-integration", (unit("unverified", validated=False),), timestamp="2026-08-05T08:01:00Z")
        self.assertEqual(result.event, IntegrationEventKind.WAITING_INTEGRATION)
        self.assertEqual(result.evidence.merge_result, "not_merge_ready")
        self.assertEqual(self.states.get("mission-integration").status, MissionExecutionStatus.WAITING_INTEGRATION)

    def test_conflict_is_an_integration_event_and_requires_a_delegated_action(self) -> None:
        result = self.coordinator.coordinate(self.states, "mission-integration", (unit("one", commit="one"), unit("two", commit="two")), timestamp="2026-08-05T08:01:00Z")
        self.assertEqual(result.event, IntegrationEventKind.MERGE_CONFLICT)
        self.assertEqual(result.evidence.merge_result, "merge_conflict")
        self.assertEqual(result.delegated_action_id, "integration-resolution-integration-mission-integration-one-two")
        self.assertEqual(self.states.get("mission-integration").status, MissionExecutionStatus.INTEGRATION_BLOCKED)
        self.assertEqual(result.evidence.conflicts[0].required_capability, "merge_conflict_resolution")

    def test_decision_and_receipt_references_are_preserved(self) -> None:
        result = self.coordinator.coordinate(self.states, "mission-integration", (unit("evidence", scope=("docs",)),), timestamp="2026-08-05T08:01:00Z")
        self.assertEqual(result.evidence.decision_evidence_references, ("decision-evidence",))
        self.assertEqual(result.evidence.execution_receipt_references, ("receipt-evidence",))



if __name__ == "__main__":
    unittest.main()
