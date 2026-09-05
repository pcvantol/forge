"""CLI-owned deterministic admission of one approved Mission into Mission State."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from forge.models.action import EngineeringAction
from forge.models.intent import EngineeringIntent, IntentStatus
from forge.models.mission import EngineeringMission, MissionStatus
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.state import MissionExecutionState, MissionStateStore
from forge.governance_authority import CanonicalGovernanceRepository, MissionPlanningEvidenceEnvelope


class MissionIntakeError(ValueError):
    """Raised when a Mission is not an approved, executable bounded contract."""


@dataclass(frozen=True)
class MissionIntake:
    """Validate one human-approved Mission and create its durable state once.

    Intake is deliberately a boundary: it creates no Mission, Intent, Action,
    approval, or Runtime Prompt.  Planning remains an injected, bounded input.
    """

    store: MissionStateStore
    clock: Callable[[], str]

    def validate_approved_evidence(
        self, envelope: MissionPlanningEvidenceEnvelope, repository: CanonicalGovernanceRepository
    ) -> MissionPlanningEvidenceEnvelope:
        """Validate canonical approvals before any Mission allocation is attempted."""
        try:
            return envelope.validate(repository)
        except ValueError as error:
            raise MissionIntakeError("Mission Intake requires valid canonical approval/planning evidence") from error

    def admit_canonical_approved_mission(
        self,
        mission: ArchitectureMission,
        envelope: MissionPlanningEvidenceEnvelope,
        repository: CanonicalGovernanceRepository,
    ) -> MissionExecutionState:
        """Admit only after validating the complete canonical evidence envelope.

        This is the canonical governance bridge.  It preserves the legacy
        bootstrap admission method below for its separately-versioned contract.
        """
        self.validate_approved_evidence(envelope, repository)
        if mission.status is not ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING:
            raise MissionIntakeError("Mission Intake requires an engineering-approved Architecture Mission")
        return self.store.create_pending(
            mission, occurred_at=self.clock(), resume={"intake": "canonical-governance-envelope-v1", "evidence_digest": envelope.digest}
        )

    def admit(
        self,
        mission: EngineeringMission,
        intents: Sequence[EngineeringIntent],
        actions: Sequence[EngineeringAction],
    ) -> MissionExecutionState:
        if mission.status is not MissionStatus.ACTIVE:
            raise MissionIntakeError("Mission Intake requires an approved active Mission")
        memberships = {(item.intent_id, item.intent_revision) for item in mission.intents}
        supplied = {(item.id, item.revision) for item in intents}
        if memberships != supplied or len(intents) != 1 or len(actions) != 1:
            raise MissionIntakeError("Bootstrap Mission Intake requires exactly one pinned Intent and Action")
        intent = intents[0]
        action = actions[0]
        if intent.status is not IntentStatus.APPROVED:
            raise MissionIntakeError("Mission Intake requires an approved Engineering Intent")
        if (action.intent_id, action.intent_revision) != (intent.id, intent.revision):
            raise MissionIntakeError("Mission Intake Action must belong to the admitted Intent")
        return self.store.create(mission, intents, actions, occurred_at=self.clock(), resume={"intake": "forge-cli-v1"})

    def admit_approved_mission(self, mission: ArchitectureMission) -> MissionExecutionState:
        """Admit the architecture-approved Mission without performing planning."""
        if mission.status is not ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING:
            raise MissionIntakeError("Mission Intake requires an engineering-approved Architecture Mission")
        return self.store.create_pending(mission, occurred_at=self.clock(), resume={"intake": "approved-mission-dispatcher-v1"})
