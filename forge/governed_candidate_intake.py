"""Bind a canonical Candidate and its two decisions to installed Mission Intake.

The recommendation aggregate stays outside Runtime.  Only its exact approved
Candidate may be allocated into the already resolved installed Runtime Instance.
"""

from __future__ import annotations

from dataclasses import replace

from forge.architecture import ArchitectureWorkspace
from forge.business import BusinessWorkspace
from forge.governance import GovernanceRole, ResolvedGovernanceProfile
from forge.governance_authority import ArchitecturePlanningEvidence, MissionPlanningEvidenceEnvelope
from forge.intake import MissionIntake
from forge.lifecycle import MissionCandidate, RecommendationLifecycleStore, RecommendationStatus
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_observation import canonical_digest
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.runtime.database import RuntimeDatabaseError
from forge.state import MissionExecutionState


class GovernedCandidateIntakeError(ValueError):
    """A Candidate, approval, or installed Mission binding is not current."""


class GovernedCandidateIntake:
    """One public, replayable Candidate-to-installed-Mission composition."""

    def __init__(self, lifecycle: RecommendationLifecycleStore,
                 runtime: InstalledDynamicMissionRuntime,
                 profile: ResolvedGovernanceProfile) -> None:
        self.lifecycle, self.runtime, self.profile = lifecycle, runtime, profile

    def decision_ids(self, candidate_id: str) -> tuple[str, str, str]:
        """Return exact Candidate revision and the two stable decision identities."""
        _, revision = self._candidate(candidate_id)
        return (revision, self._decision_id("business", candidate_id, revision),
                self._decision_id("architecture", candidate_id, revision))

    def approve_business(self, candidate_id: str, *, actor: str, occurred_at: str,
                         rationale: str, human_gates: tuple[str, ...]) -> str:
        self._require_role(actor, GovernanceRole.BUSINESS_OWNER)
        candidate, revision = self._candidate(candidate_id)
        recommendation = self.lifecycle.get_recommendation(candidate.recommendation_id)
        if recommendation.status not in {RecommendationStatus.RECOMMENDED,
                                         RecommendationStatus.BUSINESS_APPROVED,
                                         RecommendationStatus.ARCHITECTURE_APPROVED,
                                         RecommendationStatus.MISSION_ALLOCATED}:
            raise GovernedCandidateIntakeError("Candidate is not eligible for Business approval")
        if recommendation.status is RecommendationStatus.MISSION_ALLOCATED:
            self._require_current_installation_allocation(candidate.recommendation_id)
        if not human_gates or any(not gate for gate in human_gates):
            raise GovernedCandidateIntakeError("Business approval requires exact human gates")
        decision_id = self._decision_id("business", candidate_id, revision)
        if recommendation.status is not RecommendationStatus.RECOMMENDED:
            self._require_lifecycle_decision(candidate.recommendation_id, "business_decision",
                                             candidate_id, revision, decision_id)
        self._record_business(decision_id, candidate, revision, human_gates)
        if recommendation.status is RecommendationStatus.RECOMMENDED:
            self.lifecycle.transition(candidate.recommendation_id, RecommendationStatus.BUSINESS_APPROVED,
                                      actor=actor, occurred_at=occurred_at, rationale=rationale,
                                      references=(candidate_id, revision, decision_id))
        self._require_lifecycle_decision(candidate.recommendation_id, "business_decision",
                                         candidate_id, revision, decision_id)
        return decision_id

    def approve_architecture(self, candidate_id: str, mission_preview: ArchitectureMission,
                             planning: ArchitecturePlanningEvidence, *, actor: str,
                             occurred_at: str, rationale: str) -> str:
        self._require_role(actor, GovernanceRole.PLATFORM_ARCHITECT)
        candidate, revision = self._candidate(candidate_id)
        recommendation = self.lifecycle.get_recommendation(candidate.recommendation_id)
        if recommendation.status not in {RecommendationStatus.BUSINESS_APPROVED,
                                         RecommendationStatus.ARCHITECTURE_APPROVED,
                                         RecommendationStatus.MISSION_ALLOCATED}:
            raise GovernedCandidateIntakeError("Business approval is required before Architecture approval")
        if recommendation.status is RecommendationStatus.MISSION_ALLOCATED:
            self._require_current_installation_allocation(candidate.recommendation_id)
        business_id = self._decision_id("business", candidate_id, revision)
        self._require_lifecycle_decision(candidate.recommendation_id, "business_decision",
                                         candidate_id, revision, business_id)
        business = self.runtime.repository.decision(business_id)
        self._validate_preview(candidate, mission_preview, planning, revision)
        if (business["subject_revision"] != revision
                or tuple(business["scope"]) != tuple(sorted(candidate.scope))
                or tuple(business["gates"]) != tuple(sorted(planning.human_gates))):
            raise GovernedCandidateIntakeError("Architecture planning differs from Business approval")
        decision_id = self._decision_id("architecture", candidate_id, revision)
        if mission_preview.architecture_review_reference != decision_id:
            raise GovernedCandidateIntakeError("Mission preview names a different Architecture decision")
        if recommendation.status is not RecommendationStatus.BUSINESS_APPROVED:
            self._require_lifecycle_decision(candidate.recommendation_id, "architecture_decision",
                                             candidate_id, revision, decision_id,
                                             planning.digest, planning.mission_spec_digest)
        self._record_architecture(decision_id, candidate_id, revision, planning)
        if recommendation.status is RecommendationStatus.BUSINESS_APPROVED:
            self.lifecycle.transition(candidate.recommendation_id, RecommendationStatus.ARCHITECTURE_APPROVED,
                                      actor=actor, occurred_at=occurred_at, rationale=rationale,
                                      references=(candidate_id, revision, decision_id,
                                                  planning.digest, planning.mission_spec_digest))
        self._require_lifecycle_decision(candidate.recommendation_id, "architecture_decision",
                                         candidate_id, revision, decision_id,
                                         planning.digest, planning.mission_spec_digest)
        return decision_id

    def admit(self, candidate_id: str, mission_preview: ArchitectureMission,
              planning: ArchitecturePlanningEvidence, *, occurred_at: str) -> MissionExecutionState:
        candidate, revision = self._candidate(candidate_id)
        recommendation = self.lifecycle.get_recommendation(candidate.recommendation_id)
        if recommendation.status not in {RecommendationStatus.ARCHITECTURE_APPROVED,
                                         RecommendationStatus.MISSION_ALLOCATED}:
            raise GovernedCandidateIntakeError("both Candidate approvals are required before allocation")
        self._validate_preview(candidate, mission_preview, planning, revision)
        business_id = self._decision_id("business", candidate_id, revision)
        architecture_id = self._decision_id("architecture", candidate_id, revision)
        self._require_lifecycle_decision(candidate.recommendation_id, "business_decision",
                                         candidate_id, revision, business_id)
        self._require_lifecycle_decision(candidate.recommendation_id, "architecture_decision",
                                         candidate_id, revision, architecture_id,
                                         planning.digest, planning.mission_spec_digest)
        envelope = MissionPlanningEvidenceEnvelope.compose(
            self.runtime.repository, subject_id=candidate_id, subject_revision=revision,
            business_decision_id=business_id, architecture_decision_id=architecture_id,
            planning=planning,
        )
        MissionIntake(self.runtime.states, self.runtime.clock).validate_canonical_mission_contract(
            mission_preview, envelope, self.runtime.repository,
        )
        allocation = self.lifecycle.allocation_for_recommendation(candidate.recommendation_id)
        if allocation is None:
            allocation = self.lifecycle.allocate(
                candidate_id, actor="forge", occurred_at=occurred_at,
                rationale="Exact Business and Architecture approvals permit canonical Mission Intake.",
                allocate_mission_id=lambda _source, timestamp: self.runtime.database.allocate_next_mission_id(
                    source="canonical-governance-envelope:" + envelope.digest, allocated_at=timestamp),
                installation_id=envelope.installation_id, envelope_digest=envelope.digest,
            )
        mission = replace(mission_preview, id=allocation.mission_id)
        if (allocation.candidate_id != candidate_id
                or allocation.installation_id != envelope.installation_id
                or allocation.envelope_digest != envelope.digest
                or allocation.business_decision_evidence_id != self._lifecycle_decision_id(
                    candidate.recommendation_id, "business_decision")
                or allocation.architecture_decision_evidence_id != self._lifecycle_decision_id(
                    candidate.recommendation_id, "architecture_decision")):
            raise GovernedCandidateIntakeError("allocation differs from the approved Candidate")
        source = "canonical-governance-envelope:" + envelope.digest
        allocated_id = self.runtime.database.allocate_next_mission_id(source=source, allocated_at=occurred_at)
        if allocated_id != mission.id:
            raise GovernedCandidateIntakeError("allocation differs from the installed Runtime Instance")
        try:
            existing = self.runtime.database.get_document("mission_state", mission.id)
        except RuntimeDatabaseError as error:
            if str(error) != f"unknown mission_state record: {mission.id}":
                raise
            existing = None
        if existing is not None:
            state = self.runtime.states.get(mission.id)
            contract = state.admission_contract or {}
            if (state.mission != mission.to_dict() or contract.get("envelope_digest") != envelope.digest
                    or contract.get("subject_revision") != revision
                    or contract.get("candidate_id") != candidate_id):
                raise GovernedCandidateIntakeError("existing Mission has conflicting Candidate lineage")
            return state
        return self.runtime.admit(mission, envelope)

    def _require_current_installation_allocation(self, recommendation_id: str) -> None:
        allocation = self.lifecycle.allocation_for_recommendation(recommendation_id)
        if (allocation is None
                or allocation.installation_id != self.runtime.repository.operators.installation_id()):
            raise GovernedCandidateIntakeError("Candidate allocation belongs to another installation")

    def _candidate(self, candidate_id: str) -> tuple[MissionCandidate, str]:
        candidate = self.lifecycle.get_candidate(candidate_id)
        return candidate, canonical_digest(candidate.to_dict())

    def _validate_preview(self, candidate: MissionCandidate, mission: ArchitectureMission,
                          planning: ArchitecturePlanningEvidence, revision: str) -> None:
        recommendation = self.lifecycle.get_recommendation(candidate.recommendation_id)
        mission_fields = {
            "id": "MISSION-PREVIEW",
            "status": ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
            "candidate_id": candidate.id,
            "title": candidate.title,
            "summary": candidate.objective,
            "business_objective": recommendation.business_summary,
            "business_value": recommendation.business_value,
            "mission_recommendation_reference": candidate.recommendation_id,
            "scope": candidate.scope,
            "acceptance_criteria": candidate.acceptance_criteria,
            "engineering_constraints": candidate.architecture_constraints,
            "dependencies": candidate.dependencies,
        }
        planning_fields = {
            "provenance_revision": revision,
            "scope": tuple(sorted(candidate.scope)),
            "dependencies": tuple(sorted(candidate.dependencies)),
            "mission_spec_digest": canonical_digest(mission.to_dict()),
        }
        actual_planning = {
            "provenance_revision": planning.provenance_revision,
            "scope": tuple(sorted(planning.scope)),
            "dependencies": tuple(sorted(planning.dependencies)),
            "mission_spec_digest": planning.mission_spec_digest,
        }
        if (any(getattr(mission, field) != expected for field, expected in mission_fields.items())
                or actual_planning != planning_fields):
            raise GovernedCandidateIntakeError("Mission preview or planning differs from exact Candidate")

    def _record_business(self, decision_id: str, candidate: MissionCandidate,
                         revision: str, gates: tuple[str, ...]) -> None:
        repository = self.runtime.repository
        try:
            existing = repository.decision(decision_id)
        except ValueError as error:
            if "unknown canonical governance decision" not in str(error):
                raise
            BusinessWorkspace.for_runtime(self.runtime.database, repository,
                                          repository.operators.context()).approve(
                decision_id=decision_id, candidate_id=candidate.id, revision=revision,
                scope=candidate.scope, gates=gates,
            )
            existing = repository.decision(decision_id)
        if (existing["subject_id"] != candidate.id or existing["subject_revision"] != revision
                or tuple(existing["scope"]) != tuple(sorted(candidate.scope))
                or tuple(existing["gates"]) != tuple(sorted(gates))
                or existing["capability"] != "BUSINESS_APPROVAL"):
            raise GovernedCandidateIntakeError("existing Business decision differs from Candidate")

    def _record_architecture(self, decision_id: str, candidate_id: str, revision: str,
                             planning: ArchitecturePlanningEvidence) -> None:
        repository = self.runtime.repository
        try:
            existing = repository.decision(decision_id)
        except ValueError as error:
            if "unknown canonical governance decision" not in str(error):
                raise
            ArchitectureWorkspace.for_runtime(self.runtime.database, repository,
                                              repository.operators.context()).approve(
                decision_id=decision_id, candidate_id=candidate_id, revision=revision,
                planning=planning,
            )
            existing = repository.decision(decision_id)
        if (existing["subject_id"] != candidate_id or existing["subject_revision"] != revision
                or existing["capability"] != "ARCHITECTURE_APPROVAL"
                or existing.get("evidence", {}).get("planning_digest") != planning.digest):
            raise GovernedCandidateIntakeError("existing Architecture decision differs from planning")

    def _require_role(self, actor: str, role: GovernanceRole) -> None:
        if not actor or actor not in self.profile.role_assignments.get(role, ()):
            raise PermissionError(f"{role.value} authority is required")

    def _require_lifecycle_decision(self, recommendation_id: str, kind: str,
                                    *references: str) -> None:
        decision = next((item for item in self.lifecycle.history(recommendation_id)
                         if item.kind == kind), None)
        if decision is None or not set(references).issubset(decision.references):
            raise GovernedCandidateIntakeError(f"{kind} does not bind the exact Candidate")

    def _lifecycle_decision_id(self, recommendation_id: str, kind: str) -> str:
        decision = next((item for item in self.lifecycle.history(recommendation_id)
                         if item.kind == kind), None)
        if decision is None:
            raise GovernedCandidateIntakeError(f"{kind} is missing")
        return decision.id

    @staticmethod
    def _decision_id(kind: str, candidate_id: str, revision: str) -> str:
        return f"candidate-{kind}-" + canonical_digest((candidate_id, revision))[7:31]
