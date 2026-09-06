"""Canonical post-canary qualification decision for validated derivations."""
from __future__ import annotations

from hashlib import sha256
import json

from forge.governance_authority import CanonicalGovernanceRepository, GovernanceCapability, GovernanceDecision
from forge.operator_identity import OperatorContext


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CanonicalActionDerivationQualificationService:
    """Records no new authority: a typed projection of SECURITY_APPROVAL only."""
    def __init__(self, repository: CanonicalGovernanceRepository) -> None:
        self.repository, self.database = repository, repository.database

    def qualify(self, *, mission_id: str, successor_attempt_id: str,
                operator_context: OperatorContext, decision_id: str) -> str:
        if not self.repository.operators.authorize(operator_context):
            raise PermissionError("trusted operator context is required")
        state = self.database.get_document("mission_state", mission_id)
        successor = self.database.get_document("action_derivations", successor_attempt_id)
        required = ("predecessor_attempt_id", "authorization_id", "preflight_receipt_id", "main_head", "evidence_digest",
                    "effective_contract_digest", "provider_configuration", "generation_request_digest",
                    "validation_digest")
        if (state.get("status") != "APPROVED_PLANNABLE" or successor.get("mission_id") != mission_id
                or successor.get("lifecycle") != "VALIDATED" or successor.get("validation_result") != "PASS"
                or successor.get("provider_output_untrusted") is not True
                or successor.get("runtime_action_executed") is not False
                or successor.get("action_materialized") is not False
                or any(not isinstance(successor.get(key), str) or not successor[key] for key in required)):
            raise PermissionError("canonical validated non-executing Action-Derivation evidence is incomplete")
        predecessor = self.database.get_document("action_derivations", successor["predecessor_attempt_id"])
        authorization = self.database.get_document("action_derivation_reattempt_authorizations", successor["authorization_id"])
        if (predecessor.get("lifecycle") != "FAILED"
                or authorization.get("successor_attempt_id") != successor_attempt_id
                or authorization.get("predecessor_attempt_id") != successor["predecessor_attempt_id"]
                or any(authorization.get(left) != successor.get(right) for left, right in (
                    ("planning_snapshot_digest", "snapshot_digest"), ("g011_policy_digest", "provider_configuration"),
                    ("evidence_digest", "evidence_digest"), ("effective_contract_digest", "effective_contract_digest"),
                    ("provider_request_digest", "generation_request_digest"), ("main_head", "main_head")))):
            raise PermissionError("canonical successor lineage is stale or conflicting")
        consumed_authorization = self.database._connection.execute(
            "SELECT 1 FROM action_derivation_reattempt_consumptions WHERE authorization_id = ?",
            (successor["authorization_id"],),
        ).fetchone()
        if consumed_authorization is None:
            raise PermissionError("validated successor lacks a consumed canonical reattempt authorization")
        receipt = self.database.consumed_token_preflight_receipt(successor["preflight_receipt_id"])
        if any(receipt.get(left) != successor.get(right) for left, right in (
            ("mission_id", "mission_id"), ("main_head", "main_head"), ("policy_digest", "provider_configuration"),
            ("request_digest", "generation_request_digest"), ("evidence_digest", "evidence_digest"),
            ("effective_contract_digest", "effective_contract_digest"),
        )):
            raise PermissionError("canonical token-preflight receipt is stale or conflicting")
        summary = {"mission_id": mission_id, "successor_attempt_id": successor_attempt_id,
                   "predecessor_attempt_id": successor["predecessor_attempt_id"],
                   "authorization_id": successor["authorization_id"],
                   "main_head": successor["main_head"], "snapshot_digest": successor["snapshot_digest"],
                   "evidence_digest": successor["evidence_digest"],
                   "effective_contract_digest": successor["effective_contract_digest"],
                   "g011_policy_digest": successor["provider_configuration"],
                   "request_digest": successor["generation_request_digest"],
                   "preflight_receipt_id": successor["preflight_receipt_id"],
                   "validation_digest": successor["validation_digest"]}
        return self.repository.record(GovernanceDecision(
            decision_id, successor_attempt_id, successor["validation_digest"], GovernanceCapability.SECURITY_APPROVAL,
            "approved", ("ACTION_DERIVATION_QUALIFICATION",), ("POST_CANARY_SECURITY_REVIEW",), _digest(summary)), operator_context)
