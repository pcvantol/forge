"""Durable Forge-owned policy and decisions for post-Action continuation.

Execution Hosts report terminal Action evidence.  This module decides whether
Forge may derive a successor from that evidence.  It grants no host authority
and never invokes a planning provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping

from forge.governance import (
    ApprovalStage, CanonicalGovernanceProfile, ExecutionPolicy, ExecutionPolicyKind,
    GovernanceRole, execution_policy_for_profile, resolve_governance_profile,
)
from forge.governance_authority import GovernanceCapability, GovernanceDecision
from forge.state import MissionExecutionState, MissionExecutionStatus, MissionStateStore


POLICY_ASSIGNMENT_CONTRACT = "forge-progression-policy-assignment/v1"
DECISION_REQUIREMENT_CONTRACT = "forge-decision-requirement/v1"
CONTINUATION_INTENT_CONTRACT = "forge-continuation-intent/v1"
DECISION_CONTRACT = "forge-progression-decision/v1"
FINAL_ACCEPTANCE_REQUIREMENT_CONTRACT = "forge-final-acceptance-requirement/v1"
PROFILE_DEFINITION_REVISION = "1"
PROGRESSION_POLICY_REVISION = "1"


class GovernedContinuationError(ValueError):
    """The requested continuation operation is not authorized or current."""


class ProgressionMode(str, Enum):
    CONTINUOUS = "continuous"
    AFTER_ACTION = "after_action"


class ProgressionDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    AMEND = "amend"
    DEFER = "defer"


_ROLE_CAPABILITIES = {
    "business_owner": GovernanceCapability.BUSINESS_APPROVAL,
    "platform_architect": GovernanceCapability.ARCHITECTURE_APPROVAL,
    "engineering_lead": GovernanceCapability.ARCHITECTURE_APPROVAL,
    "security_advisor": GovernanceCapability.SECURITY_APPROVAL,
    "portfolio_steward": GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION,
}


def _resolved_policy(profile_id: str, mode: str, required_role: str) -> tuple[ProgressionMode, str]:
    """Resolve the supported GP-F subset from the canonical profile catalogue.

    The installed serial subset is intentionally limited to the Solo profile,
    whose primary operator is the exact Platform Architect actor.  After-Action
    is a stricter Mission override; a weaker or ambiguous override is rejected.
    """
    try:
        profile = resolve_governance_profile(profile_id)
        selected = ProgressionMode(mode)
    except (KeyError, ValueError) as error:
        raise GovernedContinuationError("governance profile or progression mode is unsupported") from error
    if profile.profile is not CanonicalGovernanceProfile.SOLO:
        raise GovernedContinuationError(
            "selected serial progression subset requires the canonical Solo profile"
        )
    default = execution_policy_for_profile(profile.profile)
    if default.kind is not ExecutionPolicyKind.CONTINUOUS:
        raise GovernedContinuationError("canonical project profile default is unsupported")
    engineering_roles = profile.approval_matrix[ApprovalStage.ENGINEERING]
    if engineering_roles != (GovernanceRole.PLATFORM_ARCHITECT,) or required_role != engineering_roles[0].value:
        raise GovernedContinuationError("progression decision role conflicts with the canonical profile")
    actors = profile.role_assignments.get(engineering_roles[0], ())
    if actors != ("primary_operator",):
        raise GovernedContinuationError("canonical profile lacks an exact primary-operator role assignment")
    return selected, actors[0]


def _digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\n" in value or "\r" in value:
        raise GovernedContinuationError(field + " is invalid")
    return value


def _mission_subject_revision(state: MissionExecutionState) -> str:
    contract = state.admission_contract
    revision = contract.get("subject_revision") if isinstance(contract, Mapping) else None
    return _text(revision, "Mission subject revision")


def validate_policy_assignment(state: MissionExecutionState) -> dict[str, Any]:
    """Return one exact Mission-bound assignment or fail closed."""
    value = state.execution_policy
    required = {
        "schema_version", "kind", "custom_boundaries", "assignment_contract",
        "assignment_id", "mission_id", "mission_subject_revision", "profile_id",
        "profile_revision", "policy_revision", "mode", "required_decision_role",
        "required_decision_capability", "required_role_actor",
        "higher_scope_obligations", "decision_digest",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise GovernedContinuationError("Mission progression policy assignment is missing or malformed")
    document = dict(value)
    if (document["assignment_contract"] != POLICY_ASSIGNMENT_CONTRACT
            or document["mission_id"] != state.mission_id
            or document["mission_subject_revision"] != _mission_subject_revision(state)
            or document["profile_revision"] != PROFILE_DEFINITION_REVISION
            or document["policy_revision"] != PROGRESSION_POLICY_REVISION
            or document["mode"] not in {item.value for item in ProgressionMode}
            or document["required_decision_role"] not in _ROLE_CAPABILITIES
            or document["required_decision_capability"]
            != _ROLE_CAPABILITIES[document["required_decision_role"]].value
            or not isinstance(document["higher_scope_obligations"], list)
            or any(not isinstance(item, str) or not item for item in document["higher_scope_obligations"])):
        raise GovernedContinuationError("Mission progression policy assignment conflicts with its Mission")
    _, actor = _resolved_policy(
        str(document["profile_id"]), str(document["mode"]), str(document["required_decision_role"]),
    )
    if document["required_role_actor"] != actor:
        raise GovernedContinuationError("Mission progression policy role actor is not canonical")
    expected_kind = (ExecutionPolicyKind.CONTINUOUS if document["mode"] == ProgressionMode.CONTINUOUS.value
                     else ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW)
    policy = ExecutionPolicy.from_dict(document)
    if policy.kind is not expected_kind:
        raise GovernedContinuationError("Mission progression mode conflicts with its execution policy")
    return document


@dataclass
class GovernedContinuationService:
    database: Any
    repository: Any
    states: MissionStateStore
    clock: Any

    def assign_policy(
        self, mission_id: str, *, assignment_id: str, profile_id: str,
        profile_revision: str, policy_revision: str, mode: str,
        required_decision_role: str, higher_scope_obligations: tuple[str, ...],
        expected_state_revision: int,
    ) -> dict[str, Any]:
        state = self.states.get(mission_id)
        if (isinstance(state.execution_policy, Mapping)
                and state.execution_policy.get("assignment_contract") == POLICY_ASSIGNMENT_CONTRACT):
            policy = self.validate_assignment(state)
            replay = {
                "assignment_id": assignment_id, "profile_id": profile_id,
                "profile_revision": profile_revision, "policy_revision": policy_revision,
                "mode": mode, "required_decision_role": required_decision_role,
                "higher_scope_obligations": list(higher_scope_obligations),
            }
            if (all(policy.get(key) == value for key, value in replay.items())
                    and expected_state_revision == state.revision - 1):
                return {
                    "status": "REPLAYED", "mission_id": mission_id,
                    "mission_revision": state.revision, "assignment_id": assignment_id,
                    "policy_digest": _digest(policy), "mode": policy["mode"],
                }
            raise GovernedContinuationError("progression policy conflicts with the existing assignment")
        placeholder = {"write_scope": "NONE", "runtime_action_executed": False,
                       "engineering_side_effects_allowed": False}
        if (state.status is not MissionExecutionStatus.APPROVED_PLANNABLE
                or state.actions or state.intents or state.revision != expected_state_revision
                or state.execution_policy != placeholder):
            raise GovernedContinuationError("progression policy requires the current zero-Action admitted Mission")
        selected, required_actor = _resolved_policy(profile_id, mode, required_decision_role)
        capability = _ROLE_CAPABILITIES[required_decision_role]
        if profile_revision != PROFILE_DEFINITION_REVISION:
            raise GovernedContinuationError("governance profile revision is unsupported")
        if policy_revision != PROGRESSION_POLICY_REVISION:
            raise GovernedContinuationError("progression policy revision is unsupported")
        contract = state.admission_contract or {}
        planning = contract.get("planning") if isinstance(contract, Mapping) else None
        gates = planning.get("human_gates") if isinstance(planning, Mapping) else None
        if (not isinstance(gates, list) or sorted(gates) != sorted(higher_scope_obligations)
                or len(gates) != len(set(gates))):
            raise GovernedContinuationError("higher-scope obligations differ from the approved Mission")
        context = self.repository.operators.context()
        evidence = {
            "assignment_contract": POLICY_ASSIGNMENT_CONTRACT,
            "mission_id": mission_id,
            "mission_subject_revision": _mission_subject_revision(state),
            "profile_id": _text(profile_id, "profile id"),
            "profile_revision": profile_revision,
            "policy_revision": _text(policy_revision, "policy revision"),
            "mode": selected.value,
            "required_decision_role": required_decision_role,
            "required_decision_capability": capability.value,
            "required_role_actor": required_actor,
            "higher_scope_obligations": list(higher_scope_obligations),
        }
        decision = GovernanceDecision(
            _text(assignment_id, "assignment id"), mission_id, _mission_subject_revision(state),
            GovernanceCapability.ARCHITECTURE_APPROVAL, "progression_policy_assigned",
            tuple(str(item) for item in state.mission.get("scope", ())), tuple(higher_scope_obligations),
            evidence=evidence,
        )
        existing = self._existing_decision(assignment_id)
        if existing is None:
            decision_digest = self.repository.record(decision, context)
        else:
            existing_evidence = existing.get("evidence") if isinstance(existing, Mapping) else None
            operator_id = sha256(context.generated_uid.encode()).hexdigest()[:16]
            if (existing.get("subject_id") != mission_id
                    or existing.get("subject_revision") != _mission_subject_revision(state)
                    or existing.get("capability") != GovernanceCapability.ARCHITECTURE_APPROVAL.value
                    or existing.get("decision") != "progression_policy_assigned"
                    or existing.get("operator_id") != operator_id
                    or not isinstance(existing_evidence, Mapping)
                    or any(existing_evidence.get(key) != value for key, value in evidence.items())):
                raise GovernedContinuationError(
                    "assignment identity conflicts with an existing canonical decision"
                )
            decision_digest = _digest(existing)
        policy = ExecutionPolicy(
            ExecutionPolicyKind.CONTINUOUS if selected is ProgressionMode.CONTINUOUS
            else ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW
        ).to_dict()
        document = {**policy, **evidence, "assignment_id": assignment_id,
                    "decision_digest": decision_digest}
        updated = self.states.assign_progression_policy(
            mission_id, document, occurred_at=self.clock(), expected_revision=expected_state_revision,
        )
        return {"status": "ASSIGNED", "mission_id": mission_id, "mission_revision": updated.revision,
                "assignment_id": assignment_id, "policy_digest": _digest(document), "mode": selected.value}

    def validate_assignment(self, state: MissionExecutionState) -> dict[str, Any]:
        """Verify both Mission state and its canonical Architecture decision."""
        policy = validate_policy_assignment(state)
        row = self.database._connection.execute(
            "SELECT document,digest FROM governance_decisions WHERE decision_id=?",
            (policy["assignment_id"],),
        ).fetchone()
        if row is None or row["digest"] != policy["decision_digest"]:
            raise GovernedContinuationError("progression policy lacks its canonical assignment decision")
        decision = json.loads(row["document"])
        evidence = decision.get("evidence") if isinstance(decision, Mapping) else None
        expected = {key: policy[key] for key in (
            "assignment_contract", "mission_id", "mission_subject_revision", "profile_id",
            "profile_revision", "policy_revision", "mode", "required_decision_role",
            "required_decision_capability", "required_role_actor", "higher_scope_obligations",
        )}
        if (_digest(decision) != row["digest"]
                or decision.get("subject_id") != state.mission_id
                or decision.get("subject_revision") != _mission_subject_revision(state)
                or decision.get("capability") != GovernanceCapability.ARCHITECTURE_APPROVAL.value
                or decision.get("decision") != "progression_policy_assigned"
                or not isinstance(evidence, Mapping)
                or any(evidence.get(key) != value for key, value in expected.items())):
            raise GovernedContinuationError("canonical progression policy decision is invalid")
        return policy

    def requirement(
        self, state: MissionExecutionState, *, completed_action_id: str,
        evidence_digest: str, project_id: str, reason: str,
    ) -> dict[str, Any]:
        policy = self.validate_assignment(state)
        if policy["mode"] != ProgressionMode.AFTER_ACTION.value:
            raise GovernedContinuationError("continuous progression does not create a DecisionRequirement")
        subject = {
            "instance_id": self.database.runtime_identity.runtime_id,
            "project_id": _text(project_id, "project id"),
            "mission_id": state.mission_id,
            "mission_subject_revision": _mission_subject_revision(state),
            "mission_state_revision": state.revision,
            "completed_action_id": _text(completed_action_id, "completed Action id"),
            "evidence_digest": _text(evidence_digest, "terminal evidence digest"),
            "policy_revision": policy["policy_revision"],
            "policy_digest": _digest(policy),
            "required_role": policy["required_decision_role"],
            "required_role_actor": policy["required_role_actor"],
            "required_capability": policy["required_decision_capability"],
            "reason": _text(reason, "decision reason"),
            "continuation_scope": list(state.mission.get("scope", ())),
        }
        requirement_id = "decision-requirement-" + _digest(subject)[7:39]
        return {"schema_version": DECISION_REQUIREMENT_CONTRACT, "requirement_id": requirement_id,
                **subject, "subject_digest": _digest(subject), "status": "PENDING"}

    def validate_requirement(
        self, state: MissionExecutionState, requirement: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Verify a persisted fence against this instance, Mission and terminal Action."""
        subject_keys = {
            "instance_id", "project_id", "mission_id", "mission_subject_revision",
            "mission_state_revision", "completed_action_id", "evidence_digest",
            "policy_revision", "policy_digest", "required_role", "required_capability",
            "required_role_actor", "reason", "continuation_scope",
        }
        required = {"schema_version", "requirement_id", "subject_digest", "status", *subject_keys}
        if (set(requirement) != required
                or requirement.get("schema_version") != DECISION_REQUIREMENT_CONTRACT
                or requirement.get("status") != "PENDING"):
            raise GovernedContinuationError("DecisionRequirement is malformed")
        subject = {key: requirement[key] for key in subject_keys}
        expected_digest = _digest(subject)
        expected_id = "decision-requirement-" + expected_digest[7:39]
        policy = self.validate_assignment(state)
        marker = state.resume.get("terminal_continuation")
        action = next((item for item in state.actions
                       if item.get("id") == requirement.get("completed_action_id")), None)
        if (requirement.get("instance_id") != self.database.runtime_identity.runtime_id
                or requirement.get("mission_id") != state.mission_id
                or requirement.get("mission_subject_revision") != _mission_subject_revision(state)
                or requirement.get("mission_state_revision") != state.revision - 1
                or requirement.get("subject_digest") != expected_digest
                or requirement.get("requirement_id") != expected_id
                or requirement.get("policy_revision") != policy["policy_revision"]
                or requirement.get("policy_digest") != _digest(policy)
                or requirement.get("required_role") != policy["required_decision_role"]
                or requirement.get("required_role_actor") != policy["required_role_actor"]
                or requirement.get("required_capability") != policy["required_decision_capability"]
                or requirement.get("continuation_scope") != list(state.mission.get("scope", ()))
                or not isinstance(marker, Mapping)
                or marker.get("action_id") != requirement.get("completed_action_id")
                or marker.get("execution_digest") != requirement.get("evidence_digest")
                or not isinstance(action, Mapping) or action.get("status") != "COMPLETE"):
            raise GovernedContinuationError(
                "DecisionRequirement is stale or bound to another instance, Mission, or Action"
            )
        return dict(requirement)

    def decide(
        self, mission_id: str, document: Mapping[str, Any], *,
        authenticated_principal_reference: str,
    ) -> dict[str, Any]:
        required = {
            "schema_version", "decision_id", "requirement_id", "subject_digest",
            "mission_state_revision", "evidence_digest", "policy_revision", "decision", "reason",
        }
        if set(document) != required or document.get("schema_version") != DECISION_CONTRACT:
            raise GovernedContinuationError("progression decision request shape is invalid")
        decision_id = _text(document["decision_id"], "decision id")
        state = self.states.get(mission_id)
        requirement = state.pause_reason
        existing = self._existing_decision(decision_id)
        if existing is not None:
            try:
                replay_capability = GovernanceCapability(str(existing.get("capability")))
            except ValueError as error:
                raise GovernedContinuationError("stored progression decision capability is invalid") from error
            replay_evidence = existing.get("evidence") if isinstance(existing, Mapping) else None
            replay_role = replay_evidence.get("required_role") if isinstance(replay_evidence, Mapping) else None
            replay_actor = replay_evidence.get("required_role_actor") if isinstance(replay_evidence, Mapping) else None
            self._assert_current_authority(
                replay_capability, str(replay_role), str(replay_actor),
                authenticated_principal_reference=authenticated_principal_reference,
            )
            self._assert_replay(existing, mission_id, document, authenticated_principal_reference)
            return {"status": "REPLAYED", "mission_id": mission_id, "decision_id": decision_id,
                    "decision": document["decision"], "resume_authorized": document["decision"] == "approve"}
        if (state.status is not MissionExecutionStatus.AWAITING_APPROVAL
                or not isinstance(requirement, Mapping)
                or requirement.get("schema_version") != DECISION_REQUIREMENT_CONTRACT):
            raise GovernedContinuationError("Mission has no current DecisionRequirement")
        requirement = self.validate_requirement(state, requirement)
        checks = {
            "requirement_id": document["requirement_id"],
            "subject_digest": document["subject_digest"],
            "mission_state_revision": document["mission_state_revision"],
            "evidence_digest": document["evidence_digest"],
            "policy_revision": document["policy_revision"],
        }
        if any(requirement.get(key) != value for key, value in checks.items()):
            raise GovernedContinuationError("progression decision is stale or bound to another subject")
        prior = self.database._connection.execute(
            "SELECT decision_id FROM governance_decisions WHERE subject_id=? LIMIT 1",
            (requirement["requirement_id"],),
        ).fetchone()
        if prior is not None:
            raise GovernedContinuationError(
                "DecisionRequirement already has a canonical decision; reconciliation is required"
            )
        try:
            outcome = ProgressionDecision(str(document["decision"]))
            capability = GovernanceCapability(str(requirement["required_capability"]))
        except ValueError as error:
            raise GovernedContinuationError("progression decision or required capability is unsupported") from error
        self._assert_current_authority(
            capability, str(requirement["required_role"]), str(requirement["required_role_actor"]),
            authenticated_principal_reference=authenticated_principal_reference,
        )
        context = self.repository.operators.context()
        evidence = {
            "schema_version": DECISION_CONTRACT, "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"], "mission_id": mission_id,
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": requirement["policy_revision"], "decision": outcome.value,
            "reason": _text(document["reason"], "decision reason"),
            "authenticated_principal_reference": _text(authenticated_principal_reference, "authenticated principal"),
            "required_role": requirement["required_role"],
            "required_role_actor": requirement["required_role_actor"],
        }
        canonical = GovernanceDecision(
            decision_id, requirement["requirement_id"], requirement["subject_digest"], capability,
            outcome.value, tuple(requirement["continuation_scope"]), (requirement["reason"],), evidence=evidence,
        )
        digest = self.repository.record(canonical, context)
        return {"status": "RECORDED", "mission_id": mission_id, "decision_id": decision_id,
                "decision_digest": digest, "decision": outcome.value,
                "resume_authorized": outcome is ProgressionDecision.APPROVE}

    def _existing_decision(self, decision_id: str) -> dict[str, Any] | None:
        row = self.database._connection.execute(
            "SELECT document,digest FROM governance_decisions WHERE decision_id=?", (decision_id,)
        ).fetchone()
        if row is None:
            return None
        value = json.loads(row["document"])
        if _digest(value) != row["digest"]:
            raise GovernedContinuationError("stored progression decision digest is invalid")
        return value

    def decision_for_requirement(self, requirement_id: str) -> dict[str, Any] | None:
        """Read one immutable decision for a fence without causing progression."""
        rows = self.database._connection.execute(
            "SELECT document,digest FROM governance_decisions WHERE subject_id=? LIMIT 2",
            (requirement_id,),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise GovernedContinuationError("DecisionRequirement has conflicting canonical decisions")
        row = rows[0]
        value = json.loads(row["document"])
        if _digest(value) != row["digest"]:
            raise GovernedContinuationError("stored progression decision digest is invalid")
        evidence = value.get("evidence") if isinstance(value, Mapping) else None
        if (value.get("subject_id") != requirement_id or not isinstance(evidence, Mapping)
                or evidence.get("requirement_id") != requirement_id):
            raise GovernedContinuationError("stored progression decision is not bound to its requirement")
        return {"decision_id": value["decision_id"], "decision": value["decision"],
                "decision_digest": row["digest"], "occurred_at": value["occurred_at"]}

    def _assert_current_authority(
        self, capability: GovernanceCapability, required_role: str, required_role_actor: str,
        *, authenticated_principal_reference: str | None = None,
    ) -> None:
        if self.repository is None:
            raise GovernedContinuationError("current progression authority repository is unavailable")
        _, actor = _resolved_policy("solo", ProgressionMode.CONTINUOUS.value, required_role)
        if required_role_actor != actor:
            raise GovernedContinuationError("current progression actor does not hold the exact required role")
        context = self.repository.operators.context()
        if not self.repository.operators.authorize(context):
            raise GovernedContinuationError("current progression decision actor is not authorized")
        operator_id = sha256(context.generated_uid.encode()).hexdigest()[:16]
        if authenticated_principal_reference is not None:
            accepted_principals = {
                "local-operator:v1:" + operator_id,
                "forge-server-admin-principal:v1:" + self.database.runtime_identity.runtime_id,
            }
            if authenticated_principal_reference not in accepted_principals:
                raise GovernedContinuationError(
                    "authenticated principal does not bind the current required-role actor"
                )
        row = self.database._connection.execute(
            "SELECT 1 FROM governance_authority WHERE installation_id=? AND operator_id=? AND capability=?",
            (context.installation_id, operator_id, capability.value),
        ).fetchone()
        if row is None:
            raise GovernedContinuationError("required progression decision capability is absent")

    def assert_intent_authority(
        self, state: MissionExecutionState, intent: Mapping[str, Any],
    ) -> None:
        """Recheck exact current role and capability at successor release."""
        policy = self.validate_assignment(state)
        if (intent.get("required_role") != policy["required_decision_role"]
                or intent.get("required_role_actor") != policy["required_role_actor"]
                or intent.get("required_capability") != policy["required_decision_capability"]):
            raise GovernedContinuationError("continuation intent authority binding is stale")
        try:
            capability = GovernanceCapability(str(intent["required_capability"]))
        except ValueError as error:
            raise GovernedContinuationError("continuation intent capability is unsupported") from error
        self._assert_current_authority(
            capability, str(intent["required_role"]), str(intent["required_role_actor"]),
        )
        decision = self._existing_decision(str(intent.get("decision_id")))
        evidence = decision.get("evidence") if isinstance(decision, Mapping) else None
        context = self.repository.operators.context()
        operator_id = sha256(context.generated_uid.encode()).hexdigest()[:16]
        if (not isinstance(decision, Mapping) or not isinstance(evidence, Mapping)
                or decision.get("operator_id") != operator_id
                or evidence.get("authenticated_principal_reference")
                != intent.get("authenticated_principal_reference")):
            raise GovernedContinuationError("continuation intent actor binding is no longer current")

    @staticmethod
    def _assert_replay(
        existing: Mapping[str, Any], mission_id: str, request: Mapping[str, Any],
        authenticated_principal_reference: str,
    ) -> None:
        evidence = existing.get("evidence")
        if (existing.get("subject_id") != request["requirement_id"]
                or existing.get("subject_revision") != request["subject_digest"]
                or existing.get("decision") != request["decision"]
                or not isinstance(evidence, Mapping) or evidence.get("mission_id") != mission_id
                or evidence.get("authenticated_principal_reference") != authenticated_principal_reference
                or any(evidence.get(key) != request[key] for key in (
                    "requirement_id", "subject_digest", "mission_state_revision",
                    "evidence_digest", "policy_revision", "decision", "reason",
                ))):
            raise GovernedContinuationError("decision identity conflicts with an existing canonical decision")


def final_acceptance_requirement(
    state: MissionExecutionState, *, instance_id: str, project_id: str,
) -> dict[str, Any]:
    """Create a durable Mission-end obligation separate from progression approval."""
    policy = validate_policy_assignment(state)
    marker = state.resume.get("terminal_continuation")
    if (not isinstance(marker, Mapping) or marker.get("mission_complete") is not True
            or not isinstance(state.completion, Mapping)
            or state.completion.get("all_required_criteria_proven") is not True):
        raise GovernedContinuationError("final acceptance requires proven Mission completion evidence")
    subject = {
        "instance_id": _text(instance_id, "instance id"),
        "project_id": _text(project_id, "project id"),
        "mission_id": state.mission_id,
        "mission_subject_revision": _mission_subject_revision(state),
        "mission_state_revision": state.revision,
        "completion_digest": _digest(state.completion),
        "terminal_evidence_digest": str(marker["execution_digest"]),
        "policy_revision": policy["policy_revision"],
        "policy_digest": _digest(policy),
        "required_role": "business_owner",
        "required_capability": GovernanceCapability.BUSINESS_APPROVAL.value,
        "reason": "mission_end_acceptance_required",
    }
    digest = _digest(subject)
    return {
        "schema_version": FINAL_ACCEPTANCE_REQUIREMENT_CONTRACT,
        "requirement_id": "final-acceptance-requirement-" + digest[7:39],
        **subject, "subject_digest": digest, "status": "PENDING",
    }
