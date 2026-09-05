"""CLI-owned deterministic admission of one approved Mission into Mission State."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Sequence

from forge.models.action import EngineeringAction
from forge.models.intent import EngineeringIntent, IntentStatus
from forge.models.mission import EngineeringMission, MissionStatus
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.state import MissionExecutionState, MissionExecutionStatus, MissionStateStore, MissionStateStoreError
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
        source = "canonical-governance-envelope:" + envelope.digest
        allocation = repository.database._connection.execute(
            "SELECT mission_id FROM mission_id_allocations WHERE source = ?", (source,)
        ).fetchone()
        if allocation is None or allocation["mission_id"] != mission.id:
            raise MissionIntakeError("Mission Intake requires the matching canonical Mission allocation")
        try:
            existing = repository.database.get_document("mission_state", mission.id)
        except Exception:
            existing = None
        if existing is not None:
            resume = existing.get("resume", {})
            if (existing.get("mission_id") != mission.id
                    or resume.get("intake") != "canonical-governance-envelope-v1"
                    or resume.get("evidence_digest") != envelope.digest):
                raise MissionIntakeError("Mission Intake found a conflicting canonical Mission state")
            try:
                return MissionStateStore._decode(json.dumps(existing, sort_keys=True, separators=(",", ":")))
            except (MissionStateStoreError, ValueError) as error:
                raise MissionIntakeError("Mission Intake found a malformed canonical Mission state") from error
        document = {
            "schema_version": "1.4", "mission_id": mission.id, "mission": mission.to_dict(),
            "intents": [], "actions": [], "status": MissionExecutionStatus.APPROVED_PLANNABLE.value,
            "lifecycle": MissionExecutionStatus.APPROVED_PLANNABLE.value,
            "progress": {"total_actions": 0, "completed_actions": 0, "remaining_action_ids": [], "percent_complete": 0},
            "resume": {"intake": "canonical-governance-envelope-v1", "evidence_digest": envelope.digest},
            "execution_correlation": None, "execution_evidence": None,
            "current_engineering_intent": None, "current_engineering_action": None,
            "execution_history": [], "waiting_reason": None, "repository_truth": None,
            "completion": None,
            "execution_policy": {"write_scope": "NONE", "runtime_action_executed": False,
                                 "engineering_side_effects_allowed": False},
            "pause_reason": None, "approval_record": None, "delegations": [], "integration": None,
            "revision": 1,
        }
        repository.database.save_mission_state(document)
        return MissionStateStore._decode(json.dumps(document, sort_keys=True, separators=(",", ":")))

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
