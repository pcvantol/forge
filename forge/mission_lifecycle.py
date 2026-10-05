"""Guarded administrative lifecycle operations for canonical Missions."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from forge.governance_authority import CanonicalGovernanceRepository, GovernanceCapability
from forge.runtime.action_intents import ActionIntentLedger
from forge.state import MissionExecutionStatus, MissionStateStore


_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}\Z")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")


class MissionLifecycleError(ValueError):
    """Raised when an administrative Mission lifecycle operation is unsafe."""


def _digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _reference(value: object, label: str) -> str:
    if not isinstance(value, str) or _REFERENCE.fullmatch(value) is None:
        raise MissionLifecycleError(f"{label} is invalid")
    return value


@dataclass(frozen=True)
class MissionArchiveResult:
    mission_id: str
    instance_id: str
    previous_status: str
    status: str
    previous_revision: int
    revision: int
    correlation_id: str
    operator_reference: str
    authenticated_principal_reference: str
    preserved_lineage_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": "archive-quiescent-no-dispatch-mission",
            "mission_id": self.mission_id,
            "instance_id": self.instance_id,
            "previous_status": self.previous_status,
            "status": self.status,
            "previous_revision": self.previous_revision,
            "revision": self.revision,
            "correlation_id": self.correlation_id,
            "operator_reference": self.operator_reference,
            "authenticated_principal_reference": self.authenticated_principal_reference,
            "preserved_lineage_digest": self.preserved_lineage_digest,
            "archived_is_completion": False,
            "provider_invoked": False,
            "host_dispatched": False,
            "target_written": False,
        }


class MissionLifecycleService:
    """Archive one proven-quiescent no-dispatch Mission through the product domain."""

    def __init__(self, repository: CanonicalGovernanceRepository) -> None:
        self.repository = repository
        self.database = repository.database
        placement = self.database.runtime_placement
        data_root = None if placement is None else str(placement.data_root)
        self.states = MissionStateStore(self.database, data_root=data_root)

    @staticmethod
    def _lineage(state: Any) -> dict[str, Any]:
        state_history = state.state_history
        if (state.status is MissionExecutionStatus.ARCHIVED and state_history
                and state_history[-1].get("from_status")
                == MissionExecutionStatus.ACTIONS_MATERIALIZED_NO_DISPATCH.value
                and state_history[-1].get("administrative_audit", {}).get("operation")
                == "archive_quiescent_no_dispatch"):
            state_history = state_history[:-1]
        return {
            "schema_version": state.schema_version,
            "mission": state.mission,
            "admission_contract": state.admission_contract,
            "actions": state.actions,
            "intents": state.intents,
            "progress": state.progress,
            "resume": state.resume,
            "current_engineering_intent": state.current_engineering_intent,
            "current_engineering_action": state.current_engineering_action,
            "planning_history": state.planning_history,
            "repository_truth": state.repository_truth,
            "execution_correlation": state.execution_correlation,
            "execution_evidence": state.execution_evidence,
            "execution_history": state.execution_history,
            "execution_policy": state.execution_policy,
            "pause_reason": state.pause_reason,
            "approval_record": state.approval_record,
            "delegations": state.delegations,
            "integration": state.integration,
            "completion": state.completion,
            "completion_history": state.completion_history,
            "waiting_reason": state.waiting_reason,
            "state_history": state_history,
        }

    def _operator_reference(self) -> str:
        context = self.repository.operators.context()
        if not self.repository.operators.authorize(context):
            raise PermissionError("trusted bound operator is required")
        operator = self.repository._operator_id(context)
        authorized = self.database._connection.execute(
            "SELECT 1 FROM governance_authority WHERE installation_id=? AND operator_id=? AND capability=?",
            (context.installation_id, operator, GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION.value),
        ).fetchone()
        if authorized is None:
            raise PermissionError("owner programme authorization capability is required")
        return operator

    def _assert_quiescent(self, mission_id: str, state: Any, *, replay: bool = False) -> None:
        self.database.validate_integrity(record_status=False)
        expected_status = (MissionExecutionStatus.ARCHIVED if replay
                           else MissionExecutionStatus.ACTIONS_MATERIALIZED_NO_DISPATCH)
        if state.status is not expected_status:
            raise MissionLifecycleError("only a materialized no-dispatch Mission may be administratively archived")
        if not state.actions or len(state.actions) != len(state.intents):
            raise MissionLifecycleError("no-dispatch Mission Action lineage is incomplete")
        if any(action.get("status") != "READY" for action in state.actions):
            raise MissionLifecycleError("Mission contains an active or uncertain Action")
        if (state.current_engineering_action is not None or state.current_engineering_intent is not None
                or state.execution_correlation is not None or state.execution_evidence is not None
                or state.execution_history or state.completion is not None or state.integration is not None
                or state.completion_history or state.delegations or state.pause_reason is not None
                or state.approval_record is not None or state.waiting_reason is not None):
            raise MissionLifecycleError("Mission has execution, completion, delegation, or integration activity")
        if self.database.has_active_mission_dispatch(mission_id):
            raise MissionLifecycleError("Mission has active dispatch lineage")
        dispatcher = self.database._connection.execute(
            "SELECT status,active_mission_id FROM dispatcher_state WHERE singleton=1"
        ).fetchone()
        if dispatcher is not None and (dispatcher["status"] != "IDLE" or dispatcher["active_mission_id"] is not None):
            raise MissionLifecycleError("Forge dispatcher is not quiescent")
        for label, query in (
            ("execution_context_snapshots", "SELECT 1 FROM execution_context_snapshots WHERE mission_id=? LIMIT 1"),
            ("execution_receipts", "SELECT 1 FROM execution_receipts WHERE mission_id=? LIMIT 1"),
            ("scheduler_submissions", "SELECT 1 FROM scheduler_submissions WHERE mission_id=? LIMIT 1"),
            ("mission_action_execution_slots", "SELECT 1 FROM mission_action_execution_slots WHERE mission_id=? LIMIT 1"),
            ("delegation_requests", "SELECT 1 FROM delegation_requests WHERE mission_id=? LIMIT 1"),
            ("integration_evidence", "SELECT 1 FROM integration_evidence WHERE mission_id=? LIMIT 1"),
        ):
            if self.database._connection.execute(query, (mission_id,)).fetchone() is not None:
                raise MissionLifecycleError(f"Mission has active or historical runtime evidence in {label}")
        planning = self.database._connection.execute("SELECT document FROM planning_state WHERE singleton=1").fetchone()
        if planning is not None and mission_id in str(planning["document"]):
            raise MissionLifecycleError("Mission remains referenced by planner state")
        attempts = self.database.durable_action_derivation_readback(mission_id)
        if (len(attempts) != 1 or attempts[0].get("lifecycle") != "MATERIALIZED"
                or attempts[0].get("processing_phase") != "MATERIALIZED"
                or attempts[0].get("result_available") is not True):
            raise MissionLifecycleError("Mission materialization provenance is incomplete or uncertain")
        intent_view = ActionIntentLedger(self.database._connection).read(mission_id)
        action_ids = {str(action.get("id")) for action in state.actions}
        intent_ids = {str(action.get("action_id")) for action in intent_view["actions"]}
        expected_freshness = "STALE" if replay else "CURRENT"
        if (intent_view.get("source_freshness") != expected_freshness
                or intent_view.get("dispatch_authorized") is not False
                or action_ids != intent_ids
                or any(action.get("correlation_status") != "BOUND"
                       or action.get("target_verification") != "PINNED_CURRENT_UNCHECKED"
                       or action.get("dispatch_authorized") is not False
                       for action in intent_view["actions"])):
            raise MissionLifecycleError("Mission Action intents are incomplete, active, or stale")

    def archive_quiescent_no_dispatch(
        self, mission_id: str, *, expected_instance_id: str, expected_revision: int,
        reason_code: str, correlation_id: str, occurred_at: str,
        authenticated_principal_reference: str | None = None,
    ) -> MissionArchiveResult:
        mission_id = _reference(mission_id, "Mission identity")
        expected_instance_id = _reference(expected_instance_id, "Runtime Instance identity")
        reason_code = _reference(reason_code, "archive reason code")
        correlation_id = _reference(correlation_id, "archive correlation identity")
        if not isinstance(occurred_at, str) or _TIMESTAMP.fullmatch(occurred_at) is None:
            raise MissionLifecycleError("archive occurrence time is invalid")
        if type(expected_revision) is not int or expected_revision < 1:
            raise MissionLifecycleError("expected Mission revision is invalid")
        if self.database.runtime_identity.runtime_id != expected_instance_id:
            raise MissionLifecycleError("Runtime Instance identity differs from the expected instance")
        operator = self._operator_reference()
        principal = _reference(
            authenticated_principal_reference or f"local-operator:v1:{operator}",
            "authenticated principal reference",
        )
        state = self.states.get(mission_id)
        audit_identity = {
            "operation": "archive_quiescent_no_dispatch",
            "operator_reference": operator,
            "reason_code": reason_code,
            "correlation_id": correlation_id,
            "authenticated_principal_reference": principal,
        }
        if state.status is MissionExecutionStatus.ARCHIVED:
            latest = state.state_history[-1] if state.state_history else {}
            recorded_audit = latest.get("administrative_audit")
            recorded_identity = (
                {key: recorded_audit.get(key) for key in audit_identity}
                if isinstance(recorded_audit, dict) else {}
            )
            recorded_lineage = (
                recorded_audit.get("preserved_lineage_digest")
                if isinstance(recorded_audit, dict) else None
            )
            receipt_payload = {
                "sequence": latest.get("sequence"),
                "from_status": latest.get("from_status"),
                "to_status": latest.get("to_status"),
                "occurred_at": latest.get("occurred_at"),
                "reason": latest.get("reason"),
                "administrative_audit": {
                    **recorded_identity,
                    "preserved_lineage_digest": recorded_lineage,
                },
            }
            if (state.revision == expected_revision + 1 and isinstance(recorded_audit, dict)
                    and recorded_identity == audit_identity
                    and set(recorded_audit) == {
                        *audit_identity, "preserved_lineage_digest", "transition_receipt_digest",
                    }
                    and latest.get("sequence") == state.revision
                    and latest.get("from_status") == MissionExecutionStatus.ACTIONS_MATERIALIZED_NO_DISPATCH.value
                    and latest.get("to_status") == MissionExecutionStatus.ARCHIVED.value
                    and latest.get("reason") == reason_code
                    and isinstance(latest.get("occurred_at"), str)
                    and _TIMESTAMP.fullmatch(latest["occurred_at"]) is not None
                    and recorded_audit.get("transition_receipt_digest") == _digest(receipt_payload)):
                recorded_digest = recorded_lineage
                self._assert_quiescent(mission_id, state, replay=True)
                if (not isinstance(recorded_digest, str)
                        or recorded_digest != _digest(self._lineage(state))):
                    raise MissionLifecycleError("archived Mission lineage differs from its preserved receipt")
                return self._result(
                    state, expected_revision, correlation_id, operator, principal, recorded_digest,
                )
            raise MissionLifecycleError("Mission is already archived by a different operation")
        if state.revision != expected_revision:
            raise MissionLifecycleError("Mission revision differs from the expected revision")
        before = _digest(self._lineage(state))
        audit_without_receipt = {**audit_identity, "preserved_lineage_digest": before}
        transition_payload = {
            "sequence": expected_revision + 1,
            "from_status": MissionExecutionStatus.ACTIONS_MATERIALIZED_NO_DISPATCH.value,
            "to_status": MissionExecutionStatus.ARCHIVED.value,
            "occurred_at": occurred_at,
            "reason": reason_code,
            "administrative_audit": audit_without_receipt,
        }
        audit = {
            **audit_without_receipt,
            "transition_receipt_digest": _digest(transition_payload),
        }
        self._assert_quiescent(mission_id, state)
        archived = self.states.transition(
            mission_id, MissionExecutionStatus.ARCHIVED, occurred_at=occurred_at,
            reason=reason_code, expected_revision=expected_revision, transition_audit=audit,
        )
        if _digest(self._lineage(archived)) != before:
            raise MissionLifecycleError("administrative archive changed immutable Mission lineage")
        return self._result(archived, expected_revision, correlation_id, operator, principal, before)

    def _result(self, state: Any, previous_revision: int, correlation_id: str,
                operator: str, authenticated_principal_reference: str,
                preserved_lineage_digest: str) -> MissionArchiveResult:
        return MissionArchiveResult(
            mission_id=state.mission_id,
            instance_id=self.database.runtime_identity.runtime_id,
            previous_status=MissionExecutionStatus.ACTIONS_MATERIALIZED_NO_DISPATCH.value,
            status=state.status.value,
            previous_revision=previous_revision,
            revision=state.revision,
            correlation_id=correlation_id,
            operator_reference=operator,
            authenticated_principal_reference=authenticated_principal_reference,
            preserved_lineage_digest=preserved_lineage_digest,
        )
