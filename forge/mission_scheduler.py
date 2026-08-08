"""Canonical, restart-safe autonomous Mission Runtime Scheduler.

Forge selects a single already-approved Action and publishes a complete
Producer Submission Envelope.  This module deliberately has no Execution
Platform policy, retry, liveness, or repository-operation logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Protocol

from forge.runtime import RuntimeDatabase, RuntimeDatabaseError


SCHEDULER_STATES = frozenset((
    "IDLE", "EVALUATING", "READY", "SUBMITTING", "WAITING_EXECUTION",
    "RECONCILING", "CONTINUING", "WAITING_GOVERNANCE", "WAITING_CAPABILITY",
    "WAITING_OPERATOR", "COMPLETE", "BLOCKED", "FAILED",
))


class MissionSchedulerError(RuntimeDatabaseError):
    """The scheduler encountered a fail-closed Mission Runtime boundary."""


@dataclass(frozen=True)
class SubmissionAcceptance:
    submission_id: str
    run_id: str


class ProducerSubmissionTransport(Protocol):
    """The EP-owned atomic ingress adapter for a complete envelope."""

    def submit(self, envelope: dict[str, Any]) -> SubmissionAcceptance: ...


@dataclass(frozen=True)
class ExecutionReceipt:
    """Compact, host-issued receipt validated before Runtime progression."""

    receipt_id: str
    submission_id: str
    run_id: str
    mission_id: str
    intent_id: str
    action_id: str
    outcome: str
    executed_at: str
    integrity: str

    def __post_init__(self) -> None:
        if self.outcome not in {"COMPLETE", "BLOCKED", "FAILED"}:
            raise ValueError("execution receipt outcome is unsupported")
        if not all(getattr(self, field) for field in self.__dataclass_fields__):
            raise ValueError("execution receipt requires complete correlation and integrity")

    @staticmethod
    def integrity_for(*, receipt_id: str, submission_id: str, run_id: str, mission_id: str,
                      intent_id: str, action_id: str, outcome: str, executed_at: str) -> str:
        source = (receipt_id, submission_id, run_id, mission_id, intent_id, action_id, outcome, executed_at)
        return "sha256:" + sha256("|".join(source).encode()).hexdigest()


@dataclass(frozen=True)
class SchedulerResult:
    mission_id: str
    state: str
    submission_id: str | None
    action_id: str | None
    pause_reason: str | None


class MissionRuntimeScheduler:
    """Advance one ACTIVE Mission only after an exact validated receipt."""

    def __init__(self, runtime: RuntimeDatabase, transport: ProducerSubmissionTransport, *, timestamp: str) -> None:
        self._runtime = runtime
        self._transport = transport
        self._timestamp = timestamp

    def evaluate(self, mission_id: str, receipt: ExecutionReceipt | None = None) -> SchedulerResult:
        """Reconcile one receipt or publish at most one next bounded Action."""
        state = self._runtime.get_document("mission_state", mission_id)
        if state.get("lifecycle") == "COMPLETE":
            return self._result(state)
        try:
            self._assert_eligibility(state)
        except MissionSchedulerError as error:
            wait_state = "WAITING_GOVERNANCE" if "approval" in str(error) else (
                "WAITING_CAPABILITY" if "capability" in str(error).lower() else "WAITING_OPERATOR")
            return self._pause(state, wait_state, str(error))
        outstanding = self._runtime.outstanding_scheduler_submission(mission_id)
        if outstanding is not None:
            if receipt is None:
                return self._set_scheduler(state, "WAITING_EXECUTION", outstanding.get("submission_id"), None)
            return self._reconcile(state, outstanding, receipt)
        if receipt is not None:
            return self._pause(state, "WAITING_OPERATOR", "Receipt has no outstanding Producer Submission.")
        try:
            return self._select_and_submit(state)
        except MissionSchedulerError as error:
            return self._pause(state, "WAITING_OPERATOR", str(error))

    def _assert_eligibility(self, state: dict[str, Any]) -> None:
        row = self._runtime._connection.execute(
            "SELECT status, active_mission_id FROM dispatcher_state WHERE singleton = 1"
        ).fetchone()
        if row is None or row["status"] != "ACTIVE" or row["active_mission_id"] != state["mission_id"]:
            raise MissionSchedulerError("Exactly one ACTIVE Mission is required.")
        governance = state.get("governance", {})
        if governance.get("business_approval") != "approved":
            raise MissionSchedulerError("Business approval is not valid.")
        if governance.get("architecture_approval") != "approved":
            raise MissionSchedulerError("Architecture approval is not valid.")
        if state.get("operator_intervention_pending"):
            raise MissionSchedulerError("Operator intervention is pending.")
        if state.get("external_capability_pending"):
            raise MissionSchedulerError("External capability is awaited.")

    def _select_and_submit(self, state: dict[str, Any]) -> SchedulerResult:
        action = self._next_action(state)
        if action is None:
            return self._complete(state)
        intent = next((item for item in state.get("engineering_intents", ()) if item.get("id") == action.get("intent_id")), None)
        if intent is None:
            return self._pause(state, "WAITING_OPERATOR", "Selected Engineering Action has no Intent.")
        iteration = int(state.get("current_iteration", state.get("iteration_number", 0))) + 1
        state.update({"current_iteration": iteration, "iteration_number": iteration,
                      "current_engineering_action": action, "current_engineering_intent": intent,
                      "scheduler_state": "SUBMITTING", "status": "ACTIVE",
                      "runtime_prompts": [{"id": f"scheduler-prompt:{action['id']}:{iteration}", "action_id": action["id"],
                                           "intent_id": intent["id"], "status": "READY_FOR_ENGINEERING_PLATFORM"}]})
        self._save(state)
        # The projection is immutable and copied unchanged into the envelope.
        self._runtime.runtime_evidence().mission_runtime_projection(state["mission_id"])
        context = self._runtime.execution_context(state["mission_id"])
        submission_id = self._submission_id(state["mission_id"], action["id"], iteration)
        envelope = {
            "schema_version": "1.0", "submission_id": submission_id,
            "producer": {"id": "forge", "type": "FORGE", "contract_version": "1.0"},
            "target_repository": state.get("target_repository", "forge"),
            "engineering_prompt": {"action_id": action["id"], "objective": action.get("objective", "")},
            "execution_context": context,
            "mission": {"id": state["mission_id"], "intent_id": intent["id"], "action_id": action["id"], "iteration": iteration},
        }
        record = {"submission_id": submission_id, "mission_id": state["mission_id"], "intent_id": intent["id"],
                  "action_id": action["id"], "iteration": iteration, "state": "CREATED", "envelope": envelope,
                  "state_history": [{"state": "CREATED"}]}
        record = self._runtime.create_scheduler_submission(record)
        try:
            accepted = self._transport.submit(envelope)
        except Exception:
            return self._pause(state, "WAITING_OPERATOR", "Producer Submission publication was not accepted.", submission_id)
        if accepted.submission_id != submission_id or not accepted.run_id:
            return self._pause(state, "WAITING_OPERATOR", "Producer Submission acknowledgement is invalid.", submission_id)
        self._runtime.update_scheduler_submission(submission_id, state="SUBMITTED", execution_run_id=accepted.run_id)
        self._runtime.update_scheduler_submission(submission_id, state="ACCEPTED", execution_run_id=accepted.run_id)
        self._record_decision(state, "autonomous_continuation_allowed", "A single READY Action was selected and submitted.")
        return self._set_scheduler(state, "WAITING_EXECUTION", submission_id, None)

    def _reconcile(self, state: dict[str, Any], submission: dict[str, Any], receipt: ExecutionReceipt) -> SchedulerResult:
        if not self._valid_receipt(submission, receipt):
            return self._pause(state, "WAITING_OPERATOR", "Execution Receipt validation failed.", submission["submission_id"])
        if not self._runtime.has_execution_receipt(receipt.receipt_id):
            self._runtime.record_execution_receipt(receipt_id=receipt.receipt_id, mission_id=receipt.mission_id,
                execution_host="engineering-platform", execution_run_id=receipt.run_id,
                engineering_report_id=receipt.receipt_id, correlation_identity=receipt.submission_id,
                executed_at=receipt.executed_at, outcome=receipt.outcome.lower())
        action = next(item for item in state["engineering_actions"] if item["id"] == receipt.action_id)
        action["status"] = {"COMPLETE": "COMPLETED", "BLOCKED": "BLOCKED", "FAILED": "FAILED"}[receipt.outcome]
        state.setdefault("execution_receipt_references", []).append({"artifact_id": receipt.receipt_id, "kind": "execution_receipt"})
        state.setdefault("iteration_history", []).append({"iteration": submission["iteration"], "submission_id": receipt.submission_id,
            "action_id": receipt.action_id, "receipt_id": receipt.receipt_id, "outcome": receipt.outcome})
        if receipt.outcome != "COMPLETE":
            terminal = "BLOCKED" if receipt.outcome == "BLOCKED" else "FAILED"
            self._runtime.update_scheduler_submission(receipt.submission_id, state=terminal, receipt_id=receipt.receipt_id)
            return self._pause(state, terminal, f"Engineering Platform reported {receipt.outcome}.", receipt.submission_id)
        self._runtime.update_scheduler_submission(receipt.submission_id, state="RECONCILED", receipt_id=receipt.receipt_id)
        self._complete_intents(state)
        state["current_engineering_action"] = None; state["current_engineering_intent"] = None
        self._record_decision(state, "receipt_reconciled", "A validated Execution Receipt advanced the bounded Action.", receipt.receipt_id)
        self._save(state)
        return self._select_and_submit(state)

    def _valid_receipt(self, submission: dict[str, Any], receipt: ExecutionReceipt) -> bool:
        expected = ExecutionReceipt.integrity_for(receipt_id=receipt.receipt_id, submission_id=receipt.submission_id,
            run_id=receipt.run_id, mission_id=receipt.mission_id, intent_id=receipt.intent_id,
            action_id=receipt.action_id, outcome=receipt.outcome, executed_at=receipt.executed_at)
        return (receipt.integrity == expected and receipt.submission_id == submission.get("submission_id") and
                receipt.run_id == submission.get("execution_run_id") and receipt.mission_id == submission.get("mission_id") and
                receipt.intent_id == submission.get("intent_id") and receipt.action_id == submission.get("action_id"))

    @staticmethod
    def _next_action(state: dict[str, Any]) -> dict[str, Any] | None:
        actions = {item.get("id"): item for item in state.get("engineering_actions", ()) if item.get("id")}
        ready = [item for item in actions.values() if item.get("status") == "READY" and all(
            actions.get(dependency, {}).get("status") == "COMPLETED" for dependency in item.get("dependencies", ()))]
        if len(ready) > 1:
            raise MissionSchedulerError("Mission Graph is ambiguous: multiple READY Actions.")
        return ready[0] if ready else None

    def _complete(self, state: dict[str, Any]) -> SchedulerResult:
        if any(item.get("status") not in {"COMPLETED", "DISCARDED", "SUPERSEDED"} for item in state.get("engineering_intents", ())):
            return self._pause(state, "WAITING_OPERATOR", "No Action is executable but Mission work remains.")
        state.update({"lifecycle": "COMPLETE", "status": "COMPLETE", "scheduler_state": "COMPLETE",
                      "completion_timestamp": self._timestamp, "mission_completion_summary": "All canonical Mission work is reconciled."})
        self._record_decision(state, "mission_completion", "No ACTIVE, READY, or executable Engineering Action remains.")
        self._save(state); self._runtime.save_dispatcher_state(status="IDLE", mission_sequence=(state["mission_id"],))
        self._runtime.record_mission_lifecycle(state["mission_id"], "complete", self._timestamp)
        self._runtime.runtime_evidence().mission_runtime_projection(state["mission_id"])
        return self._result(state)

    @staticmethod
    def _complete_intents(state: dict[str, Any]) -> None:
        for intent in state.get("engineering_intents", ()):
            actions = [action for action in state.get("engineering_actions", ()) if action.get("intent_id") == intent.get("id")]
            if actions and all(action.get("status") == "COMPLETED" for action in actions):
                intent["status"] = "COMPLETED"

    def _pause(self, state: dict[str, Any], scheduler_state: str, reason: str, submission_id: str | None = None) -> SchedulerResult:
        state.update({"scheduler_state": scheduler_state, "pause_reason": reason,
                      "status": "BLOCKED" if scheduler_state == "BLOCKED" else "WAITING"})
        self._record_decision(state, "autonomous_continuation_paused", reason); self._save(state)
        return self._result(state, submission_id)

    def _set_scheduler(self, state: dict[str, Any], scheduler_state: str, submission_id: str | None, reason: str | None) -> SchedulerResult:
        state["scheduler_state"] = scheduler_state; self._save(state)
        return self._result(state, submission_id, reason)

    def _save(self, state: dict[str, Any]) -> None:
        self._runtime.save_mission_state(state)
        remaining = [item["id"] for item in state.get("engineering_actions", ()) if item.get("status") != "COMPLETED"]
        self._runtime.save_planning_state({"planner_version": "mission-runtime-scheduler-1", "current_queue": [] if state.get("lifecycle") == "COMPLETE" else [state["mission_id"]],
            "pending_engineering_actions": remaining, "blocked_engineering_actions": [item["id"] for item in state.get("engineering_actions", ()) if item.get("status") in {"BLOCKED", "FAILED"}],
            "execution_policy": state["execution_policy"], "planner_runtime_metadata": {"scheduler_state": state.get("scheduler_state", "IDLE")}})

    def _record_decision(self, state: dict[str, Any], kind: str, summary: str, receipt_id: str | None = None) -> None:
        prefix = f"{state['mission_id']}-scheduler-{kind}-"
        number = self._runtime._connection.execute(
            "SELECT COUNT(*) FROM decision_evidence WHERE decision_id LIKE ?", (prefix + "%",)
        ).fetchone()[0] + 1
        identifier = f"{prefix}{number}"
        state.setdefault("decision_evidence_ids", []).append(identifier)
        refs = [] if receipt_id is None else [{"artifact_id": receipt_id, "kind": "execution_receipt"}]
        self._runtime.record_decision_evidence({"id": identifier, "decision_type": "engineering_action_selection", "timestamp": self._timestamp,
            "mission_context": {"artifact_id": state["mission_id"]}, "repository_context": {"artifact_id": "forge-repository-truth"},
            "reasoning_summary": summary, "evidence_references": [{"artifact_id": "runtime:mission_state"}],
            "alternatives_considered": [{"id": "fail_closed", "reason": "Only canonical Runtime state is used."}],
            "chosen_alternative": "canonical_runtime", "confidence": {"score": 100, "mission_state": {"artifact_id": state["mission_id"]}},
            "execution_receipt_references": refs})

    @staticmethod
    def _submission_id(mission_id: str, action_id: str, iteration: int) -> str:
        return "submission:" + sha256(f"{mission_id}:{action_id}:{iteration}".encode()).hexdigest()

    @staticmethod
    def _result(state: dict[str, Any], submission_id: str | None = None, reason: str | None = None) -> SchedulerResult:
        action = state.get("current_engineering_action") or {}
        return SchedulerResult(state["mission_id"], state.get("scheduler_state", "IDLE"), submission_id,
                               action.get("id"), reason or state.get("pause_reason"))
