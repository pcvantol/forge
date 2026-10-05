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
        return {
            "mission": state.mission,
            "admission_contract": state.admission_contract,
            "actions": state.actions,
            "intents": state.intents,
            "planning_history": state.planning_history,
            "repository_truth": state.repository_truth,
            "execution_history": state.execution_history,
            "completion_history": state.completion_history,
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

    def _assert_quiescent(self, mission_id: str, state: Any) -> None:
        self.database.validate_integrity(record_status=False)
        if state.status is not MissionExecutionStatus.ACTIONS_MATERIALIZED_NO_DISPATCH:
            raise MissionLifecycleError("only a materialized no-dispatch Mission may be administratively archived")
        if not state.actions or len(state.actions) != len(state.intents):
            raise MissionLifecycleError("no-dispatch Mission Action lineage is incomplete")
        if any(action.get("status") != "READY" for action in state.actions):
            raise MissionLifecycleError("Mission contains an active or uncertain Action")
        if (state.current_engineering_action is not None or state.current_engineering_intent is not None
                or state.execution_correlation is not None or state.execution_evidence is not None
                or state.execution_history or state.completion is not None or state.integration is not None
                or state.completion_history or state.delegations):
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
        if (intent_view.get("source_freshness") != "CURRENT"
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
    ) -> MissionArchiveResult:
        mission_id = _reference(mission_id, "Mission identity")
        expected_instance_id = _reference(expected_instance_id, "Runtime Instance identity")
        reason_code = _reference(reason_code, "archive reason code")
        correlation_id = _reference(correlation_id, "archive correlation identity")
        if type(expected_revision) is not int or expected_revision < 1:
            raise MissionLifecycleError("expected Mission revision is invalid")
        if self.database.runtime_identity.runtime_id != expected_instance_id:
            raise MissionLifecycleError("Runtime Instance identity differs from the expected instance")
        operator = self._operator_reference()
        state = self.states.get(mission_id)
        audit_identity = {
            "operation": "archive_quiescent_no_dispatch",
            "operator_reference": operator,
            "reason_code": reason_code,
            "correlation_id": correlation_id,
        }
        if state.status is MissionExecutionStatus.ARCHIVED:
            latest = state.state_history[-1] if state.state_history else {}
            recorded_audit = latest.get("administrative_audit")
            if (state.revision == expected_revision + 1 and isinstance(recorded_audit, dict)
                    and {key: recorded_audit.get(key) for key in audit_identity} == audit_identity
                    and set(recorded_audit) == {*audit_identity, "preserved_lineage_digest"}
                    and latest.get("from_status") == MissionExecutionStatus.ACTIONS_MATERIALIZED_NO_DISPATCH.value):
                recorded_digest = recorded_audit.get("preserved_lineage_digest")
                if (not isinstance(recorded_digest, str)
                        or recorded_digest != _digest(self._lineage(state))):
                    raise MissionLifecycleError("archived Mission lineage differs from its preserved receipt")
                return self._result(state, expected_revision, correlation_id, operator, recorded_digest)
            raise MissionLifecycleError("Mission is already archived by a different operation")
        if state.revision != expected_revision:
            raise MissionLifecycleError("Mission revision differs from the expected revision")
        before = _digest(self._lineage(state))
        audit = {**audit_identity, "preserved_lineage_digest": before}
        self._assert_quiescent(mission_id, state)
        archived = self.states.transition(
            mission_id, MissionExecutionStatus.ARCHIVED, occurred_at=occurred_at,
            reason=reason_code, expected_revision=expected_revision, transition_audit=audit,
        )
        if _digest(self._lineage(archived)) != before:
            raise MissionLifecycleError("administrative archive changed immutable Mission lineage")
        return self._result(archived, expected_revision, correlation_id, operator, before)

    def _result(self, state: Any, previous_revision: int, correlation_id: str,
                operator: str, preserved_lineage_digest: str) -> MissionArchiveResult:
        return MissionArchiveResult(
            mission_id=state.mission_id,
            instance_id=self.database.runtime_identity.runtime_id,
            previous_status=MissionExecutionStatus.ACTIONS_MATERIALIZED_NO_DISPATCH.value,
            status=state.status.value,
            previous_revision=previous_revision,
            revision=state.revision,
            correlation_id=correlation_id,
            operator_reference=operator,
            preserved_lineage_digest=preserved_lineage_digest,
        )
