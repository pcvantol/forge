"""Deterministic Forge coordination of integration; never engineering execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from forge.integration.repository import IntegrationEvidenceRepository
from forge.models.integration import (ConflictResolutionKind, IntegrationConflict, IntegrationEventKind,
                                      IntegrationEvidence, IntegrationOutcome, IntegrationUnit)
from forge.state import MissionExecutionStatus, MissionStateStore


class IntegrationCoordinatorError(ValueError):
    pass


@dataclass(frozen=True)
class IntegrationResult:
    evidence: IntegrationEvidence
    event: IntegrationEventKind
    delegated_action_id: str | None = None


class IntegrationCoordinator:
    """Forge's deterministic merge-readiness and conflict-decision boundary.

    It records decisions and controls Mission pause/resume state.  It neither
    invokes an Execution Host nor modifies repository content.
    """

    def __init__(self, evidence: IntegrationEvidenceRepository, *, integration_id_factory: Callable[[str, Sequence[IntegrationUnit]], str]) -> None:
        self._evidence = evidence
        self._integration_id_factory = integration_id_factory

    def coordinate(self, states: MissionStateStore, mission_id: str, units: Sequence[IntegrationUnit], *, timestamp: str) -> IntegrationResult:
        ordered = tuple(sorted(units, key=lambda item: item.id))
        if not ordered or any(unit.mission_id != mission_id for unit in ordered):
            raise IntegrationCoordinatorError("integration units must be non-empty and belong to the Mission")
        state = states.get(mission_id)
        if state.status is MissionExecutionStatus.ACTIVE:
            state = states.transition(mission_id, MissionExecutionStatus.WAITING_INTEGRATION, occurred_at=timestamp,
                                      reason="execution_complete_waiting_integration", integration={"unit_ids": [unit.id for unit in ordered]})
        if state.status is not MissionExecutionStatus.WAITING_INTEGRATION:
            raise IntegrationCoordinatorError("Mission must be waiting for integration")
        states.transition(mission_id, MissionExecutionStatus.INTEGRATION_RUNNING, occurred_at=timestamp,
                          reason="integration_started", integration={"unit_ids": [unit.id for unit in ordered]})
        missing = self._readiness_failures(ordered)
        conflicts = self._conflicts(ordered)
        integration_id = self._integration_id_factory(mission_id, ordered)
        if missing:
            evidence = self._record(integration_id, mission_id, ordered, timestamp, IntegrationOutcome.WAITING,
                                    "not_merge_ready", (), "readiness_pending:" + ",".join(missing))
            states.transition(mission_id, MissionExecutionStatus.WAITING_INTEGRATION, occurred_at=timestamp,
                              reason="integration_readiness_pending", integration=evidence.to_dict())
            return IntegrationResult(evidence, IntegrationEventKind.WAITING_INTEGRATION)
        if conflicts:
            evidence = self._record(integration_id, mission_id, ordered, timestamp, IntegrationOutcome.BLOCKED,
                                    "merge_conflict", conflicts, "delegated_conflict_resolution")
            action_id = f"integration-resolution-{integration_id}"
            states.transition(mission_id, MissionExecutionStatus.INTEGRATION_BLOCKED, occurred_at=timestamp,
                              reason="merge_conflict_delegation_required", integration={**evidence.to_dict(), "delegated_action_id": action_id})
            return IntegrationResult(evidence, IntegrationEventKind.MERGE_CONFLICT, action_id)
        evidence = self._record(integration_id, mission_id, ordered, timestamp, IntegrationOutcome.COMPLETE,
                                "merge_ready", (), "no_conflicts_detected")
        states.transition(mission_id, MissionExecutionStatus.INTEGRATION_COMPLETE, occurred_at=timestamp,
                          reason="integration_complete", integration=evidence.to_dict())
        return IntegrationResult(evidence, IntegrationEventKind.INTEGRATION_COMPLETE)

    @staticmethod
    def _readiness_failures(units: Sequence[IntegrationUnit]) -> tuple[str, ...]:
        ids = {unit.id for unit in units}
        failures: list[str] = []
        for unit in units:
            if not unit.validation_passed:
                failures.append(f"validation:{unit.id}")
            if not unit.required_approvals_satisfied:
                failures.append(f"approval:{unit.id}")
            failures.extend(f"dependency:{unit.id}:{dependency}" for dependency in unit.dependencies if dependency not in ids)
        return tuple(sorted(failures))

    @staticmethod
    def _conflicts(units: Sequence[IntegrationUnit]) -> tuple[IntegrationConflict, ...]:
        conflicts: list[IntegrationConflict] = []
        for index, left in enumerate(units):
            for right in units[index + 1:]:
                scopes = tuple(sorted(set(left.repository_scope).intersection(right.repository_scope)))
                if scopes and left.repository_commit != right.repository_commit:
                    conflicts.append(IntegrationConflict(
                        f"conflict-{left.id}-{right.id}", (left.id, right.id), "repository_scope_overlap", scopes,
                        ConflictResolutionKind.DELEGATE, "merge_conflict_resolution",
                    ))
        return tuple(sorted(conflicts, key=lambda item: item.id))

    def _record(self, integration_id: str, mission_id: str, units: tuple[IntegrationUnit, ...], timestamp: str,
                outcome: IntegrationOutcome, merge_result: str, conflicts: tuple[IntegrationConflict, ...], resolution: str) -> IntegrationEvidence:
        evidence = IntegrationEvidence(integration_id, mission_id, units, timestamp, outcome, merge_result,
                                       tuple(reference for unit in units for reference in unit.decision_evidence_references),
                                       tuple(unit.execution_receipt_id for unit in units), conflicts, resolution)
        return self._evidence.append(evidence)
