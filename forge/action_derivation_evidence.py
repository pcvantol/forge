"""Canonical, pre-planning evidence producer for Action Derivation.

It deliberately derives only from a Mission's immutable admission contract;
it neither observes repositories, creates approvals, nor grants execution.
"""
from __future__ import annotations

from hashlib import sha256
import json

from forge.governance_authority import CanonicalGovernanceRepository
from forge.models.architecture_mission import ArchitectureMission
from forge.models.intent import IntentReference
from forge.models.mission_planner import (ApprovedScope, MissionPlannerInput, MissionPlanningState,
    PlanningEvidence, PlanningInputKind)
from forge.runtime.database import RuntimeDatabase, RuntimeIntegrityError


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class ActionDerivationEvidenceError(ValueError):
    """The immutable admission contract cannot produce a complete evidence set."""


class CanonicalActionDerivationEvidenceProducer:
    """The sole runtime-owned producer for generic pre-planning evidence."""

    _NO_REPOSITORY_TARGET = "NO_REPOSITORY_TARGET=TRUE"
    _CAPABILITIES = ("action-derivation-planning", "deterministic-action-materialization")

    def __init__(self, database: RuntimeDatabase, repository: CanonicalGovernanceRepository) -> None:
        if repository.database is not database:
            raise ValueError("evidence producer requires the canonical governance Runtime Database")
        self.database, self.repository = database, repository

    def produce(self, mission_id: str) -> dict[str, object]:
        state = self.database.get_document("mission_state", mission_id)
        contract = state.get("admission_contract")
        if not isinstance(contract, dict) or state.get("status") != "APPROVED_PLANNABLE":
            raise ActionDerivationEvidenceError("Mission is not canonically approved/plannable")
        required = ("installation_id", "candidate_id", "subject_revision", "business_decision_id",
                    "architecture_decision_id", "planning", "envelope_digest", "write_scope", "mission")
        if any(item not in contract for item in required) or contract["write_scope"] != "NONE":
            raise ActionDerivationEvidenceError("Mission admission contract is incomplete or has non-NONE write scope")
        mission = ArchitectureMission.from_dict(contract["mission"])
        if mission.id != mission_id or mission.candidate_id != contract["candidate_id"]:
            raise RuntimeIntegrityError("Mission admission contract identity mismatch")
        if contract["installation_id"] != self.repository.operators.installation_id():
            raise ActionDerivationEvidenceError("Mission admission contract is cross-installation")
        planning = contract["planning"]
        if not isinstance(planning, dict) or planning.get("provenance_revision") != contract["subject_revision"]:
            raise ActionDerivationEvidenceError("Mission planning evidence revision is stale")
        for decision_id in (contract["business_decision_id"], contract["architecture_decision_id"]):
            decision = self.repository.decision(decision_id)
            if decision["subject_id"] != contract["candidate_id"] or decision["subject_revision"] != contract["subject_revision"]:
                raise ActionDerivationEvidenceError("Mission approval lineage is inconsistent")
        if self._NO_REPOSITORY_TARGET not in mission.engineering_constraints:
            raise ActionDerivationEvidenceError("Mission lacks explicit approved NO_REPOSITORY_TARGET evidence")
        context = {"kind": "NO_REPOSITORY_TARGET", "mission_id": mission_id,
                   "installation_id": contract["installation_id"], "candidate_id": contract["candidate_id"],
                   "subject_revision": contract["subject_revision"], "write_scope": contract["write_scope"],
                   "classification": "planning_only_no_repository_target",
                   "provenance": {"envelope_digest": contract["envelope_digest"], "mission_constraint": self._NO_REPOSITORY_TARGET}}
        context["digest"] = _digest(context)
        projection = {"kind": "PRE_PLANNING_CANONICAL_PROJECTION", "mission_id": mission_id,
                      "installation_id": contract["installation_id"], "candidate_id": contract["candidate_id"],
                      "subject_revision": contract["subject_revision"], "architecture_decision_id": contract["architecture_decision_id"],
                      "envelope_digest": contract["envelope_digest"], "planning": planning}
        projection["digest"] = _digest(projection)
        catalogue = {"kind": "RUNTIME_CAPABILITY_CATALOGUE", "mission_id": mission_id,
                     "installation_id": contract["installation_id"], "candidate_id": contract["candidate_id"],
                     "subject_revision": contract["subject_revision"], "envelope_digest": contract["envelope_digest"],
                     "capabilities": list(self._CAPABILITIES), "effective_write_scope": "NONE", "grants_authority": False}
        catalogue["digest"] = _digest(catalogue)
        mission_evidence = {"kind": "MISSION_STATE", "mission_id": mission_id, "digest": _digest(state)}
        value = {"evidence_set_id": "action-derivation-evidence-" + contract["envelope_digest"][7:23],
                 "mission_id": mission_id, "installation_id": contract["installation_id"],
                 "candidate_id": contract["candidate_id"], "subject_revision": contract["subject_revision"],
                 "envelope_digest": contract["envelope_digest"], "mission_state": mission_evidence,
                 "repository_context": context, "architecture_review": projection, "capability_catalogue": catalogue}
        value["digest"] = _digest(value)
        return self.database.create_action_derivation_evidence_set(value)

    def planner_input(self, mission_id: str) -> MissionPlannerInput:
        evidence_set = self.produce(mission_id)
        mission = ArchitectureMission.from_dict(self.database.get_document("mission_state", mission_id)["admission_contract"]["mission"])
        reference = IntentReference("architecture-decision", str(evidence_set["subject_revision"]),
                                    "runtime://governance/" + str(evidence_set["architecture_review"]["architecture_decision_id"]))
        documents = ((PlanningInputKind.MISSION_STATE, evidence_set["mission_state"]),
                     (PlanningInputKind.REPOSITORY_CONTEXT, evidence_set["repository_context"]),
                     (PlanningInputKind.ARCHITECTURE_REVIEW, evidence_set["architecture_review"]),
                     (PlanningInputKind.CAPABILITY_CATALOGUE, evidence_set["capability_catalogue"]))
        evidence = tuple(PlanningEvidence(kind, str(document["kind"]).lower(), str(evidence_set["subject_revision"]),
                                          "runtime://action-derivation-evidence/" + str(evidence_set["evidence_set_id"]), str(document["digest"]))
                         for kind, document in documents)
        capability = mission.required_capabilities[0]
        scopes = tuple(ApprovedScope(scope, capability, (reference,), (), allow_provider_derivation=True) for scope in mission.scope)
        return MissionPlannerInput(mission, MissionPlanningState(mission.id, int(self.database.get_document("mission_state", mission_id)["revision"])), evidence, scopes)
