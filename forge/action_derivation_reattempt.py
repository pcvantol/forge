"""Canonical, explicitly authorized successor lineage for Action Derivation.

This module allocates no provider work.  It records the one durable authority
needed before a later, separately authorized token preflight may be attempted.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
import uuid

from forge.action_derivation_evidence import CanonicalActionDerivationEvidenceProducer
from forge.governance_authority import CanonicalGovernanceRepository
from forge.models.action_derivation import PlanningSnapshot
from forge.operator_identity import OperatorContext
from forge.planner.openai_responses import _G011PolicySnapshot, _digest
from forge.planner.provider_adapter import ProviderDerivationRequest
from forge.runtime.database import RuntimeIntegrityError, _timestamp


REQUEST_SEMANTICS_CHANGED = "REQUEST_SEMANTICS_CHANGED"


class NewPlanningRequired(RuntimeIntegrityError):
    """The candidate drifted beyond the narrow reattempt authority."""


class CanonicalActionDerivationReattemptService:
    """The sole application path for a governed Action-Derivation successor.

    It accepts a canonical adapter/configuration rather than caller-provided
    policy, evidence, database, or request digests.  Persisting authorization
    never calls a provider and never consumes a preflight receipt.
    """
    def __init__(self, adapter, governance_repository: CanonicalGovernanceRepository) -> None:
        database = adapter.configuration.policy_service.db
        if governance_repository.database is not database:
            raise PermissionError("reattempt lineage requires the canonical governance RuntimeDatabase")
        self.adapter, self.repository, self.database = adapter, governance_repository, database

    @staticmethod
    def _record_digest(value: dict[str, object]) -> str:
        return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def authorize_successor(self, *, predecessor_attempt_id: str, operator_context: OperatorContext,
                            rationale: str, reason: str = REQUEST_SEMANTICS_CHANGED) -> dict[str, object]:
        if reason != REQUEST_SEMANTICS_CHANGED:
            raise PermissionError("unsupported Action-Derivation reattempt reason")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 512:
            raise ValueError("a bounded explicit reattempt rationale is required")
        if not self.repository.operators.authorize(operator_context):
            raise PermissionError("trusted operator context is required for a reattempt")
        predecessor = self.database.get_document("action_derivations", predecessor_attempt_id)
        if predecessor.get("lifecycle") != "FAILED":
            raise PermissionError("only a terminal failed Action-Derivation attempt may have a successor")
        required = ("mission_id", "snapshot_digest", "effective_contract_digest", "evidence_digest",
                    "provider_configuration", "generation_request_digest", "main_head")
        if any(not isinstance(predecessor.get(field), str) or not predecessor[field] for field in required):
            raise RuntimeIntegrityError("predecessor lacks complete canonical reattempt provenance")

        mission_id = predecessor["mission_id"]
        producer = CanonicalActionDerivationEvidenceProducer(self.database, self.repository)
        planning_input = producer.planner_input(mission_id)
        snapshot = PlanningSnapshot.from_planner_input(planning_input)
        policy = self.adapter.configuration.current_policy()
        policy_digest = _G011PolicySnapshot.from_policy(policy).digest
        boundary = self.adapter.configuration.preflight_authority.boundary_for(mission_id)
        state = self.database.get_document("mission_state", mission_id)
        if state.get("status") != "APPROVED_PLANNABLE":
            raise NewPlanningRequired("Mission is no longer approved/plannable")
        if any((snapshot.digest != predecessor["snapshot_digest"],
                boundary.effective_contract_digest != predecessor["effective_contract_digest"],
                boundary.evidence_digest != predecessor["evidence_digest"],
                policy_digest != predecessor["provider_configuration"])):
            raise NewPlanningRequired("Mission, planning, effective contract, evidence, or G011 policy drift requires new planning")

        successor_attempt_id = f"reattempt-{uuid.uuid4()}"
        request = ProviderDerivationRequest(successor_attempt_id, snapshot, policy.provider_id, policy.model)
        request_digest = _digest(self.adapter._body(request, policy))
        if request_digest == predecessor["generation_request_digest"]:
            raise PermissionError("an unchanged request digest is an exact replay, not a successor attempt")
        sequence_row = self.database._connection.execute(
            "SELECT MAX(attempt_sequence) AS sequence FROM action_derivation_reattempt_authorizations WHERE predecessor_attempt_id=?",
            (predecessor_attempt_id,),
        ).fetchone()
        if sequence_row is not None and sequence_row["sequence"] is not None:
            # A second child of this predecessor is never silently given a new
            # sequence; its different reason needs separate governance semantics.
            raise PermissionError("a predecessor already has a governed successor attempt")
        operator_id = self.repository._operator_id(operator_context)
        document: dict[str, object] = {
            "authorization_id": f"action-derivation-reattempt-{uuid.uuid4()}",
            "successor_attempt_id": successor_attempt_id,
            "mission_id": mission_id,
            "predecessor_attempt_id": predecessor_attempt_id,
            "predecessor_terminal_state": predecessor["lifecycle"],
            "attempt_sequence": 2,
            "planning_snapshot_digest": snapshot.digest,
            "effective_contract_digest": boundary.effective_contract_digest,
            "evidence_digest": boundary.evidence_digest,
            "g011_policy_digest": policy_digest,
            "provider_request_digest": request_digest,
            "main_head": boundary.main_head,
            "reattempt_reason": reason,
            "rationale": rationale.strip(),
            "authorization_identity": operator_id,
            "installation_id": operator_context.installation_id,
            "created_at": _timestamp(),
        }
        document["digest"] = self._record_digest(document)
        return self.database.create_action_derivation_reattempt_authorization(document)

