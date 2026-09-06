"""Canonical immutable closure for a bounded Action-Derivation qualification canary."""
from __future__ import annotations

from hashlib import sha256
import json

from forge.governance_authority import CanonicalGovernanceRepository, GovernanceCapability
from forge.operator_identity import OperatorContext
from forge.runtime.database import _timestamp


_NOT_QUALIFIED = (
    "ACTION_MATERIALIZATION", "AUTONOMOUS_NEXT_MISSION_LOOP", "EP_DISPATCH",
    "EP_RESULT_OBSERVATION", "EXECUTION_ADMISSION",
)


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class CanonicalActionDerivationCanaryClosureService:
    """Close a qualified planning-only canary without changing Mission lifecycle."""

    def __init__(self, repository: CanonicalGovernanceRepository) -> None:
        self.repository, self.database = repository, repository.database

    @staticmethod
    def _operator_id(context: OperatorContext) -> str:
        return sha256(context.generated_uid.encode()).hexdigest()[:16]

    def close(self, *, mission_id: str, successor_attempt_id: str,
              qualification_decision_id: str, operator_context: OperatorContext) -> dict[str, object]:
        if not self.repository.operators.authorize(operator_context):
            raise PermissionError("trusted operator context is required")
        state = self.database.get_document("mission_state", mission_id)
        successor = self.database.get_document("action_derivations", successor_attempt_id)
        required = (
            "predecessor_attempt_id", "authorization_id", "preflight_receipt_id", "main_head",
            "snapshot_digest", "evidence_digest", "effective_contract_digest",
            "provider_configuration", "generation_request_digest", "validation_digest",
        )
        if (state.get("status") != "APPROVED_PLANNABLE" or successor.get("mission_id") != mission_id
                or successor.get("lifecycle") != "VALIDATED" or successor.get("validation_result") != "PASS"
                or successor.get("provider_output_untrusted") is not True
                or successor.get("runtime_action_executed") is not False
                or successor.get("action_materialized") is not False
                or successor.get("engineering_side_effects", 0) != 0
                or any(not isinstance(successor.get(key), str) or not successor[key] for key in required)):
            raise PermissionError("canonical validated non-executing Action-Derivation evidence is incomplete")
        predecessor = self.database.get_document("action_derivations", successor["predecessor_attempt_id"])
        authorization = self.database.get_document(
            "action_derivation_reattempt_authorizations", successor["authorization_id"]
        )
        if (predecessor.get("mission_id") != mission_id or predecessor.get("lifecycle") != "FAILED"
                or authorization.get("successor_attempt_id") != successor_attempt_id
                or authorization.get("predecessor_attempt_id") != successor["predecessor_attempt_id"]
                or any(authorization.get(left) != successor.get(right) for left, right in (
                    ("planning_snapshot_digest", "snapshot_digest"), ("effective_contract_digest", "effective_contract_digest"),
                    ("evidence_digest", "evidence_digest"), ("g011_policy_digest", "provider_configuration"),
                    ("provider_request_digest", "generation_request_digest"), ("main_head", "main_head")))):
            raise PermissionError("canonical successor lineage is stale or conflicting")
        if self.database._connection.execute(
            "SELECT 1 FROM action_derivation_reattempt_consumptions WHERE authorization_id=?",
            (successor["authorization_id"],),
        ).fetchone() is None:
            raise PermissionError("validated successor lacks a consumed canonical reattempt authorization")
        receipt = self.database.consumed_token_preflight_receipt(successor["preflight_receipt_id"])
        if any(receipt.get(left) != successor.get(right) for left, right in (
            ("mission_id", "mission_id"), ("main_head", "main_head"), ("policy_digest", "provider_configuration"),
            ("request_digest", "generation_request_digest"), ("evidence_digest", "evidence_digest"),
            ("effective_contract_digest", "effective_contract_digest"),
        )):
            raise PermissionError("canonical token-preflight receipt is stale or conflicting")
        try:
            decision = self.repository.decision(qualification_decision_id)
        except ValueError as error:
            raise PermissionError("post-canary Security qualification is absent") from error
        summary = {
            "mission_id": mission_id, "successor_attempt_id": successor_attempt_id,
            "predecessor_attempt_id": successor["predecessor_attempt_id"],
            "authorization_id": successor["authorization_id"], "main_head": successor["main_head"],
            "snapshot_digest": successor["snapshot_digest"], "evidence_digest": successor["evidence_digest"],
            "effective_contract_digest": successor["effective_contract_digest"],
            "g011_policy_digest": successor["provider_configuration"],
            "request_digest": successor["generation_request_digest"],
            "preflight_receipt_id": successor["preflight_receipt_id"],
            "validation_digest": successor["validation_digest"],
        }
        if (decision.get("subject_id") != successor_attempt_id
                or decision.get("subject_revision") != successor["validation_digest"]
                or decision.get("capability") != GovernanceCapability.SECURITY_APPROVAL.value
                or decision.get("decision") != "approved"
                or decision.get("scope") != ["ACTION_DERIVATION_QUALIFICATION"]
                or decision.get("gates") != ["POST_CANARY_SECURITY_REVIEW"]
                or decision.get("predecessor_digest") != _digest(summary)):
            raise PermissionError("post-canary Security qualification is absent, stale, or conflicting")
        closure_id = f"action-derivation-canary-closure:{mission_id}:{successor_attempt_id}"
        document = {
            "closure_id": closure_id, "mission_id": mission_id,
            "successor_attempt_id": successor_attempt_id,
            "predecessor_attempt_id": successor["predecessor_attempt_id"],
            "qualification_decision_id": qualification_decision_id,
            "qualification_decision_digest": _digest(decision),
            "effective_contract_digest": successor["effective_contract_digest"],
            "evidence_digest": successor["evidence_digest"],
            "g011_policy_digest": successor["provider_configuration"],
            "provider_request_digest": successor["generation_request_digest"],
            "preflight_receipt_id": successor["preflight_receipt_id"],
            "reattempt_authorization_id": successor["authorization_id"],
            "main_head": successor["main_head"], "qualified_capability": "ACTION_DERIVATION",
            "not_qualified_capabilities": list(_NOT_QUALIFIED),
            "installation_id": operator_context.installation_id,
            "operator_id": self._operator_id(operator_context),
            "runtime_id": self.database.metadata["runtime_id"], "closed_at": _timestamp(),
        }
        existing = self.database._connection.execute(
            "SELECT document FROM action_derivation_canary_closures WHERE successor_attempt_id=?",
            (successor_attempt_id,),
        ).fetchone()
        if existing is not None:
            persisted = json.loads(existing["document"])
            expected = {key: value for key, value in document.items() if key != "closed_at"}
            actual = {key: value for key, value in persisted.items() if key not in ("closed_at", "digest")}
            if actual != expected:
                raise PermissionError("existing Action-Derivation canary closure is stale or conflicting")
            return persisted
        document["digest"] = _digest(document)
        return self.database.create_action_derivation_canary_closure(document)
