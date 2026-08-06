"""Immutable, operator-facing Execution Context projections.

Execution Context deliberately projects Runtime state only.  It never retains
Runtime Prompts, decision reasoning, host reports, telemetry, or logs.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping


CONTEXT_SCHEMA_VERSION = "1"

_LIFECYCLE_PROJECTIONS = {
    "RECOMMENDATION": "Recommendation",
    "PROPOSED": "Recommendation",
    "RECOMMENDED": "Recommendation",
    "BUSINESS_REVIEW": "Business Review",
    "BUSINESS_APPROVED": "Business Review",
    "ARCHITECTURE_REVIEW": "Architecture Review",
    "ARCHITECTURE_APPROVED": "Architecture Review",
    "MISSION_CANDIDATE": "Mission Candidate",
    "ALLOCATED": "Allocated",
    "REGISTERED": "Allocated",
    "ACTIVE": "Active",
    "PAUSED": "Paused",
    "WAITING_FOR_GOVERNANCE": "Waiting For Governance",
    "AWAITING_APPROVAL": "Waiting For Governance",
    "WAITING_FOR_RECEIPT": "Waiting For Receipt",
    "WAITING_FOR_EVIDENCE": "Waiting For Receipt",
    "WAITING_FOR_EXECUTION": "Waiting For Receipt",
    "COMPLETE": "Mission Complete",
    "COMPLETED": "Mission Complete",
    "EXECUTION_COMPLETE": "Execution Complete",
    "INTEGRATION_COMPLETE": "Execution Complete",
}


def _safe_item(item: Mapping[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(item, Mapping):
        return None
    identifier = item.get("id")
    if not isinstance(identifier, str) or not identifier:
        return None
    result = {"id": identifier}
    for key in ("title", "objective", "status"):
        value = item.get(key)
        if isinstance(value, str) and value:
            result[key] = value
    return result


def _mission_lifecycle(state: Mapping[str, Any], projection: Mapping[str, Any]) -> str:
    explicit = state.get("mission_lifecycle_projection")
    if explicit in _LIFECYCLE_PROJECTIONS.values():
        return str(explicit)
    for value in (state.get("lifecycle"), state.get("status"), projection.get("mission_lifecycle")):
        projected = _LIFECYCLE_PROJECTIONS.get(str(value).upper())
        if projected:
            return projected
    return "Allocated"


def _phase(state: Mapping[str, Any], projection: Mapping[str, Any], mission_lifecycle: str) -> str:
    status = str(state.get("status", "")).upper()
    if mission_lifecycle == "Mission Complete":
        return "Mission Complete"
    if mission_lifecycle == "Execution Complete":
        return "Execution Complete"
    if status in {"WAITING_FOR_EVIDENCE", "WAITING_FOR_EXECUTION", "WAITING_FOR_RECEIPT"}:
        return "Waiting For Receipt"
    if status in {"AWAITING_APPROVAL", "WAITING_FOR_GOVERNANCE"}:
        return "Waiting For Governance"
    if status in {"PAUSED", "BLOCKED", "INTEGRATION_BLOCKED"}:
        return "Paused"
    if status in {"REGISTERED", "CREATED"}:
        return "Preparing"
    if status == "READY" or mission_lifecycle == "Allocated":
        return "Planning"
    if status == "VALIDATING":
        return "Validation"
    if projection.get("next_executable_engineering_action"):
        return "Engineering"
    return "Planning"


def _recommendation_status(state: Mapping[str, Any], mission_lifecycle: str) -> str:
    explicit = state.get("mission_recommendation_status")
    if isinstance(explicit, str) and explicit:
        return explicit
    return {
        "Recommendation": "RECOMMENDED",
        "Business Review": "BUSINESS_APPROVED",
        "Architecture Review": "ARCHITECTURE_APPROVED",
        "Mission Candidate": "RECOMMENDED",
    }.get(mission_lifecycle, "MISSION_ALLOCATED")


def _timestamp(state: Mapping[str, Any], projection: Mapping[str, Any], receipts: tuple[Mapping[str, Any], ...]) -> str:
    candidates = [value for value in (projection.get("last_runtime_update_timestamp"), state.get("last_runtime_update"), state.get("updated_at"), state.get("timestamp")) if isinstance(value, str) and value]
    candidates.extend(str(item["executed_at"]) for item in receipts if isinstance(item.get("executed_at"), str))
    return max(candidates) if candidates else "runtime-state"


def project_execution_context(*, state: Mapping[str, Any], projection: Mapping[str, Any], context_version: int) -> dict[str, Any]:
    """Create a deterministic, compact snapshot from a reconciled Runtime view."""
    mission_id = str(projection["mission_id"])
    receipts = tuple(projection.get("execution_receipts", ()))
    source = {"state": state, "projection": projection, "context_version": context_version}
    source_digest = "sha256:" + sha256(json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    completed = tuple(_safe_item(item) for item in projection.get("completed_intents", ()))
    running = tuple(_safe_item(item) for item in projection.get("running_intents", ()))
    ready = tuple(_safe_item(item) for item in projection.get("ready_intents", ()))
    blocked = tuple(_safe_item(item) for item in projection.get("blocked_intents", ()))
    discovered = tuple(_safe_item(item) for item in projection.get("discovered_intents", ()))
    mission_lifecycle = _mission_lifecycle(state, projection)
    completion = mission_lifecycle in {"Mission Complete", "Execution Complete"}
    completion_timestamp = state.get("completion_timestamp", state.get("completed_at"))
    if completion and not isinstance(completion_timestamp, str):
        completion_timestamp = _timestamp(state, projection, receipts)
    final_runtime_state = None
    if completion:
        final_runtime_state = {
            "mission_lifecycle": mission_lifecycle,
            "execution_phase": _phase(state, projection, mission_lifecycle),
            "remaining_engineering_action_count": len(projection.get("remaining_engineering_actions", ())),
            "execution_receipt_outcome": receipts[-1].get("outcome") if receipts else None,
        }
    return {
        "context_id": f"execution-context:{mission_id}:{context_version}",
        "context_version": context_version,
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "mission_id": mission_id,
        "mission_title": state.get("mission_title", state.get("title", mission_id)),
        "mission_lifecycle": mission_lifecycle,
        "mission_recommendation_status": _recommendation_status(state, mission_lifecycle),
        "business_summary": state.get("business_summary", f"Advance the approved Mission {mission_id}."),
        "engineering_summary": state.get("engineering_summary", "Forge is reconciling the current approved engineering plan."),
        "current_intent": _safe_item(projection.get("current_intent")) or {"message": "No active Intent."},
        "current_engineering_action": _safe_item(projection.get("next_executable_engineering_action")) or {"message": "No current Engineering Action."},
        "execution_phase": _phase(state, projection, mission_lifecycle),
        "planning_confidence": projection.get("planning_confidence"),
        "current_iteration": state.get("current_iteration", 1),
        "completed_intents": [item for item in completed if item],
        "running_intents": [item for item in running if item],
        "ready_intents": [item for item in ready if item],
        "blocked_intents": [item for item in blocked if item],
        "discovered_intents": [item for item in discovered if item],
        "discarded_intents": [item for item in (_safe_item(value) for value in projection.get("discarded_intents", ())) if item],
        "remaining_engineering_actions": [_safe_item(item) for item in projection.get("remaining_engineering_actions", ()) if _safe_item(item)],
        "last_execution_receipt": receipts[-1] if receipts else None,
        "last_runtime_update": state.get("resume", state.get("resume_point", {})),
        "last_updated_timestamp": _timestamp(state, projection, receipts),
        "mission_completion_summary": state.get("mission_completion_summary", f"Mission {mission_id} completed.") if completion else None,
        "completion_timestamp": completion_timestamp if completion else None,
        "final_runtime_state": final_runtime_state,
        "source_digest": source_digest,
    }


class ExecutionContextAPI:
    """Read-only canonical API projection for all Forge clients."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def get(self, mission_id: str) -> dict[str, Any]:
        return self._runtime.execution_context(mission_id)

    def history(self, mission_id: str) -> tuple[dict[str, Any], ...]:
        return self._runtime.execution_context_history(mission_id)
