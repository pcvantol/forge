"""Durable, fail-closed orchestration of one approved active Mission.

This composition boundary deliberately does not invoke an Execution Host.  It
selects one bounded action, records the hand-off, and accepts only a complete
host-issued receipt before continuing.  All durable state belongs to the
canonical :class:`RuntimeDatabase`.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from forge.runtime import RuntimeDatabase, RuntimeDatabaseError


class AutonomousOrchestrationError(RuntimeDatabaseError):
    """A Mission cannot be autonomously advanced without human intervention."""


@dataclass(frozen=True)
class ExecutionReceipt:
    """The minimal immutable identity Forge retains from an Execution Host."""

    receipt_id: str
    action_id: str
    execution_host: str
    execution_run_id: str
    engineering_report_id: str
    correlation_identity: str
    executed_at: str
    outcome: str

    def __post_init__(self) -> None:
        if self.outcome not in {"complete", "blocked", "failed"}:
            raise ValueError("execution receipt outcome is unsupported")
        if not all(getattr(self, field) for field in self.__dataclass_fields__):
            raise ValueError("execution receipt requires complete host-issued identity")


@dataclass(frozen=True)
class OrchestrationResult:
    mission_id: str
    state: str
    iteration_number: int
    current_intent_id: str | None
    current_action_id: str | None
    runtime_prompt_id: str | None
    decision_evidence_id: str | None


class AutonomousMissionOrchestrator:
    """Advance exactly one approved Mission through sequential host receipts."""

    def __init__(self, runtime: RuntimeDatabase, *, timestamp: str) -> None:
        self._runtime = runtime
        self._timestamp = timestamp

    def advance(self, mission_id: str, receipt: ExecutionReceipt | None = None) -> OrchestrationResult:
        state = self._runtime.get_document("mission_state", mission_id)
        self._assert_active_mission(mission_id)
        try:
            self._assert_governance(state)
        except AutonomousOrchestrationError as error:
            state["orchestration_state"] = ("WAITING_BUSINESS_APPROVAL" if "Business" in str(error)
                                            else "WAITING_ARCHITECTURE_APPROVAL")
            state["status"] = "WAITING"
            self._save(state)
            return self._result(state)
        if state.get("lifecycle") == "COMPLETE":
            return self._result(state)
        if state.get("orchestration_state") in {
            "WAITING_EXTERNAL_CAPABILITY", "WAITING_BUSINESS_APPROVAL",
            "WAITING_ARCHITECTURE_APPROVAL", "WAITING_EXECUTION_FAILURE",
        }:
            return self._result(state)
        if receipt is not None:
            state = self._apply_receipt(state, receipt)
            if state.get("lifecycle") == "COMPLETE" or state.get("orchestration_state") == "WAITING_EXECUTION_FAILURE":
                return self._result(state)
        return self._dispatch_next(state)

    def _assert_active_mission(self, mission_id: str) -> None:
        row = self._runtime._connection.execute(
            "SELECT status, active_mission_id FROM dispatcher_state WHERE singleton = 1"
        ).fetchone()
        if row is None or row["status"] != "ACTIVE" or row["active_mission_id"] != mission_id:
            raise AutonomousOrchestrationError("autonomous orchestration requires exactly one active Mission")

    @staticmethod
    def _assert_governance(state: dict[str, Any]) -> None:
        governance = state.get("governance", {})
        if governance.get("business_approval") != "approved":
            raise AutonomousOrchestrationError("Business approval is not valid for the next dispatch")
        if governance.get("architecture_approval") != "approved":
            raise AutonomousOrchestrationError("Architecture approval is not valid for the next dispatch")

    def _apply_receipt(self, state: dict[str, Any], receipt: ExecutionReceipt) -> dict[str, Any]:
        current = state.get("current_engineering_action") or {}
        if current.get("id") != receipt.action_id:
            raise AutonomousOrchestrationError("execution receipt does not match the current Engineering Action")
        if self._runtime.has_execution_receipt(receipt.receipt_id):
            return state
        self._runtime.record_execution_receipt(
            receipt_id=receipt.receipt_id, mission_id=state["mission_id"], execution_host=receipt.execution_host,
            execution_run_id=receipt.execution_run_id, engineering_report_id=receipt.engineering_report_id,
            correlation_identity=receipt.correlation_identity, executed_at=receipt.executed_at, outcome=receipt.outcome,
        )
        action_status = {"complete": "COMPLETED", "blocked": "BLOCKED", "failed": "FAILED"}[receipt.outcome]
        for action in state["engineering_actions"]:
            if action["id"] == receipt.action_id:
                action["status"] = action_status
        references = list(state.get("execution_receipt_references", []))
        references.append({"artifact_id": receipt.receipt_id, "kind": "execution_receipt"})
        state["execution_receipt_references"] = references
        state.setdefault("iteration_history", []).append({
            "iteration": state.get("iteration_number", 0), "action_id": receipt.action_id,
            "receipt_id": receipt.receipt_id, "outcome": receipt.outcome,
        })
        if receipt.outcome != "complete":
            state["orchestration_state"] = "WAITING_EXECUTION_FAILURE"
            state["status"] = "BLOCKED" if receipt.outcome == "blocked" else "FAILED"
            self._save(state)
            return state
        self._complete_intents(state)
        if all(action["status"] == "COMPLETED" for action in state["engineering_actions"]):
            state.update({"lifecycle": "COMPLETE", "status": "COMPLETE", "orchestration_state": "COMPLETE",
                          "current_engineering_action": None, "current_engineering_intent": None,
                          "runtime_prompts": [], "progress": self._progress(state)})
            self._runtime.save_dispatcher_state(status="IDLE", mission_sequence=(state["mission_id"],))
            self._save(state)
            self._runtime.record_mission_lifecycle(state["mission_id"], "complete", self._timestamp)
            return state
        self._save(state)
        return state

    def _dispatch_next(self, state: dict[str, Any]) -> OrchestrationResult:
        actions = {action["id"]: action for action in state.get("engineering_actions", [])}
        candidates = [action for action in actions.values() if action.get("status") in {"READY", "ACTIVE"}
                      and all(actions.get(dependency, {}).get("status") == "COMPLETED" for dependency in action.get("dependencies", []))]
        if len(candidates) != 1:
            raise AutonomousOrchestrationError("autonomous orchestration requires exactly one executable Engineering Action")
        action = candidates[0]
        action["status"] = "ACTIVE"
        intent = next((item for item in state["engineering_intents"] if item["id"] == action["intent_id"]), None)
        if intent is None:
            raise AutonomousOrchestrationError("Engineering Action has no persisted Engineering Intent")
        iteration = int(state.get("iteration_number", 0)) + 1
        prompt_id = "runtime-prompt:" + sha256(f"{state['mission_id']}:{action['id']}:{iteration}".encode()).hexdigest()
        decision_id = f"{state['mission_id']}-orchestration-decision-{iteration}"
        state.update({
            "iteration_number": iteration, "current_iteration": iteration, "current_engineering_action": action,
            "current_engineering_intent": intent, "runtime_prompts": [{"id": prompt_id, "action_id": action["id"],
                "intent_id": intent["id"], "status": "READY_FOR_ENGINEERING_PLATFORM"}],
            "orchestration_state": "WAITING_FOR_EXECUTION", "status": "ACTIVE", "lifecycle": "ACTIVE",
            "decision_evidence_ids": list(state.get("decision_evidence_ids", [])) + [decision_id], "progress": self._progress(state),
        })
        self._save(state)
        self._runtime.record_decision_evidence({
            "id": decision_id, "decision_type": "engineering_action_selection", "timestamp": self._timestamp,
            "mission_context": {"artifact_id": state["mission_id"]}, "repository_context": {"artifact_id": "forge-repository-truth"},
            "reasoning_summary": "Exactly one approved, dependency-satisfied action was selected for the next bounded execution.",
            "evidence_references": [{"artifact_id": "runtime:mission_state"}],
            "alternatives_considered": [{"id": "sequential", "reason": "Selected: preserves one-action execution and receipt correlation."}],
            "chosen_alternative": "sequential", "confidence": {"score": 100, "mission_state": {"artifact_id": state["mission_id"]}},
            "execution_receipt_references": [],
        })
        return self._result(state)

    def _save(self, state: dict[str, Any]) -> None:
        self._runtime.save_mission_state(state)
        remaining = [action["id"] for action in state["engineering_actions"] if action["status"] != "COMPLETED"]
        complete = state.get("lifecycle") == "COMPLETE"
        self._runtime.save_planning_state({"planner_version": "autonomous-mission-orchestrator-1", "current_queue": [] if complete else [state["mission_id"]],
            "pending_engineering_actions": [] if complete else remaining, "blocked_engineering_actions": [action["id"] for action in state["engineering_actions"] if action["status"] in {"BLOCKED", "FAILED"}],
            "execution_policy": state["execution_policy"], "planner_runtime_metadata": {"iteration_number": state.get("iteration_number", 0)}})

    @staticmethod
    def _complete_intents(state: dict[str, Any]) -> None:
        for intent in state["engineering_intents"]:
            relevant = [action for action in state["engineering_actions"] if action["intent_id"] == intent["id"]]
            if relevant and all(action["status"] == "COMPLETED" for action in relevant):
                intent["status"] = "COMPLETED"

    @staticmethod
    def _progress(state: dict[str, Any]) -> dict[str, int]:
        actions = state["engineering_actions"]
        completed = sum(action["status"] == "COMPLETED" for action in actions)
        return {"percent_complete": (completed * 100) // len(actions), "completed_engineering_actions": completed,
                "remaining_engineering_actions": len(actions) - completed}

    @staticmethod
    def _result(state: dict[str, Any]) -> OrchestrationResult:
        action = state.get("current_engineering_action") or {}
        intent = state.get("current_engineering_intent") or {}
        prompt = next(iter(state.get("runtime_prompts", [])), {})
        decisions = state.get("decision_evidence_ids", [])
        return OrchestrationResult(state["mission_id"], state.get("orchestration_state", state["status"]),
            int(state.get("iteration_number", 0)), intent.get("id"), action.get("id"), prompt.get("id"),
            decisions[-1] if decisions else None)
