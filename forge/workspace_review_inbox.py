"""Safe Mission-review projections for the scoped Workspace HTTP capability."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping
import re

from .governed_continuation import DECISION_CONTRACT, ProgressionDecision
from .operations_read_api import _redact
from .workspace_review_grant import ReviewPrincipal


CONTRACT_VERSION = "forge-workspace-review-inbox/v1"
DECISION_REQUEST_VERSION = "forge-workspace-review-decision/v1"
OPERATION_VERSION = "forge-workspace-review-operation/v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def _bounded(value: object, limit: int) -> str | None:
    if not isinstance(value, str) or not value or any(ord(item) < 32 for item in value):
        return None
    safe = _redact(value)
    return safe[:limit] if isinstance(safe, str) else None


def _reference(value: object) -> str | None:
    if (not isinstance(value, str) or _OPERATION_ID.fullmatch(value) is None
            or _redact(value) != value):
        return None
    return value


def scoped_item(runtime: Any, principal: ReviewPrincipal, mission_id: str) -> dict[str, Any]:
    """Read canonical state and expose only bounded, typed review facts."""
    if mission_id not in principal.mission_ids:
        raise PermissionError("review grant does not include this Mission")
    state = runtime.states.get(mission_id)
    intake_placeholder = {"write_scope": "NONE", "runtime_action_executed": False,
                          "engineering_side_effects_allowed": False}
    # Canonical Intake admits an approved Mission before policy assignment.
    # It is a valid scoped inbox item with no review. Other missing or altered
    # policies still fail through the authoritative progression validator.
    status = ({"decision_requirement": None, "final_acceptance_requirement": None,
               "decision": None}
              if (state.status.value == "APPROVED_PLANNABLE"
                  and state.execution_policy == intake_placeholder
                  and not state.actions and not state.intents)
              else runtime.progression_status(mission_id))
    requirement = status["decision_requirement"]
    final = status["final_acceptance_requirement"]
    if isinstance(requirement, Mapping):
        review_kind = "PROGRESSION"
        scope = requirement["continuation_scope"]
        if (not isinstance(scope, (list, tuple)) or len(scope) > 64
                or any(not isinstance(item, str) or len(item) > 256
                       or _bounded(item, 256) is None for item in scope)):
            raise ValueError("review blocker scope cannot be safely projected")
        safe_scope = [_bounded(item, 256) for item in scope]
        decision = status["decision"]
        permitted = (decision is None and state.status.value == "AWAITING_APPROVAL"
                     and requirement["required_role"] == principal.role
                     and requirement["required_role_actor"] == principal.role_actor
                     and requirement["required_capability"] == principal.capability)
        outcomes = [item.value for item in ProgressionDecision] if permitted else []
        reviewed = {
            "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "subject_revision": _bounded(requirement["mission_subject_revision"], 128),
            "mission_state_revision": requirement["mission_state_revision"],
            "completed_action_id": _reference(requirement["completed_action_id"]),
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": _bounded(requirement["policy_revision"], 128),
            "policy_digest": requirement["policy_digest"],
            "required_role": requirement["required_role"],
            "required_role_actor": requirement["required_role_actor"],
            "required_capability": requirement["required_capability"],
            "reason": _bounded(requirement["reason"], 512),
            "blocking_scope": safe_scope,
            "blocking_scope_redacted": safe_scope != list(scope),
            "status": requirement["status"],
        }
    elif isinstance(final, Mapping):
        review_kind = "FINAL_ACCEPTANCE"
        decision = None
        outcomes = []  # A progression decision is never Mission-end acceptance.
        reviewed = {
            "requirement_id": final.get("requirement_id"),
            "subject_digest": final.get("subject_digest"),
            "subject_revision": _bounded(final.get("mission_subject_revision"), 128),
            "mission_state_revision": final.get("mission_state_revision"),
            "completed_action_id": None,
            "evidence_digest": final.get("evidence_digest"),
            "policy_revision": _bounded(final.get("policy_revision"), 128),
            "policy_digest": final.get("policy_digest"),
            "required_role": final.get("required_role"),
            "required_role_actor": final.get("required_role_actor"),
            "required_capability": final.get("required_capability"),
            "reason": "Mission-end acceptance is a separate owner decision",
            "blocking_scope": [mission_id], "blocking_scope_redacted": False,
            "status": final.get("status"),
        }
    else:
        review_kind = ("EXTERNAL_GATE" if state.status.value.startswith("WAITING_EXTERNAL")
                       else "NONE")
        decision = None
        outcomes = []
        reviewed = None
    action_id = requirement["completed_action_id"] if isinstance(requirement, Mapping) else None
    safe_action_id = _reference(action_id)
    action = next((item for item in state.actions if item.get("id") == action_id), None)
    result = next((item for item in reversed(state.execution_history)
                   if isinstance(item.get("repository_evidence"), Mapping)
                   and item["repository_evidence"].get("mission_id") == mission_id
                   and item["repository_evidence"].get("action_id") == action_id), None)
    receipt_id = _reference(result.get("receipt_id")) if result else None
    outcome = _bounded(result.get("outcome"), 32) if result else None
    evidence_digest = reviewed["evidence_digest"] if reviewed else None
    evidence_reference = (
        {"kind": "FORGE_EXECUTION_EVIDENCE", "digest": evidence_digest,
         "receipt_id": receipt_id}
        if isinstance(evidence_digest, str) and _DIGEST.fullmatch(evidence_digest) else None
    )
    return {
        "contract_version": CONTRACT_VERSION,
        "instance_id": principal.instance_id,
        "mission_id": mission_id,
        "authority": {"principal_id": principal.principal_id, "role": principal.role,
                      "role_actor": principal.role_actor, "capability": principal.capability,
                      "expires_at": principal.expires_at},
        "title": _bounded(state.mission.get("title"), 160),
        "lifecycle_state": state.status.value,
        "mission_state_revision": state.revision,
        "review_kind": review_kind,
        "decision": ({"decision_id": _reference(decision["decision_id"]),
                      "outcome": decision["decision"],
                      "decision_digest": decision["decision_digest"]}
                     if isinstance(decision, Mapping) else None),
        "requirement": reviewed,
        "action_result": ({"action_id": safe_action_id,
                           "status": _bounded(action.get("status"), 32) if action else None,
                           "outcome": outcome, "evidence_reference": evidence_reference}
                          if safe_action_id is not None else None),
        "allowed_outcomes": outcomes,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "freshness": "CURRENT_FORGE_RUNTIME_READBACK",
    }


def scoped_list(runtime: Any, principal: ReviewPrincipal) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "instance_id": principal.instance_id,
        "scope": {"kind": "EXPLICIT_MISSION_SET", "principal_id": principal.principal_id,
                  "mission_ids": list(principal.mission_ids), "complete_within_scope": True},
        "items": [scoped_item(runtime, principal, item) for item in principal.mission_ids],
        "read_only": True,
    }


def canonical_decision_request(document: Mapping[str, Any]) -> dict[str, Any]:
    """Drop no client fields: actors and roles cannot be supplied by JSON."""
    required = {"contract_version", "operation_id", "requirement_id", "subject_digest",
                "mission_state_revision", "evidence_digest", "policy_revision",
                "decision", "reason"}
    if set(document) != required or document.get("contract_version") != DECISION_REQUEST_VERSION:
        raise ValueError("review decision request shape is invalid")
    operation_id = document["operation_id"]
    if _reference(operation_id) is None:
        raise ValueError("review operation identifier is invalid")
    if _reference(document["requirement_id"]) is None:
        raise ValueError("review requirement identifier is invalid")
    if (not isinstance(document["subject_digest"], str)
            or _DIGEST.fullmatch(document["subject_digest"]) is None
            or not isinstance(document["evidence_digest"], str)
            or _DIGEST.fullmatch(document["evidence_digest"]) is None):
        raise ValueError("review subject or evidence digest is invalid")
    revision = document["mission_state_revision"]
    if type(revision) is not int or revision < 1:
        raise ValueError("review Mission state revision is invalid")
    policy_revision = document["policy_revision"]
    if (not isinstance(policy_revision, str) or not policy_revision
            or len(policy_revision) > 128 or any(ord(item) < 32 for item in policy_revision)
            or _redact(policy_revision) != policy_revision):
        raise ValueError("review policy revision is invalid")
    if (not isinstance(document["decision"], str)
            or document["decision"] not in {item.value for item in ProgressionDecision}):
        raise ValueError("review decision outcome is unsupported")
    if (not isinstance(document["reason"], str) or not document["reason"]
            or len(document["reason"]) > 512
            or any(ord(item) < 32 for item in document["reason"])):
        raise ValueError("review decision reason is invalid")
    return {
        "schema_version": DECISION_CONTRACT,
        "decision_id": operation_id,
        "requirement_id": document["requirement_id"],
        "subject_digest": document["subject_digest"],
        "mission_state_revision": document["mission_state_revision"],
        "evidence_digest": document["evidence_digest"],
        "policy_revision": document["policy_revision"],
        "decision": document["decision"], "reason": document["reason"],
    }
