"""Immutable, operator-facing Execution Context projections.

Execution Context deliberately projects Runtime state only.  It never retains
Runtime Prompts, decision reasoning, host reports, telemetry, or logs.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping


CONTEXT_SCHEMA_VERSION = "1"


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


def _phase(state: Mapping[str, Any], projection: Mapping[str, Any]) -> str:
    lifecycle = str(state.get("lifecycle", "")).upper()
    status = str(state.get("status", "")).upper()
    if lifecycle == "COMPLETE" or status == "COMPLETE":
        return "Mission Complete"
    if status in {"COMPLETED", "INTEGRATION_COMPLETE"}:
        return "Execution Complete"
    if status in {"WAITING_FOR_EVIDENCE", "WAITING_FOR_EXECUTION", "WAITING_FOR_RECEIPT"}:
        return "Waiting For Receipt"
    if status in {"AWAITING_APPROVAL", "WAITING_FOR_GOVERNANCE"}:
        return "Waiting For Governance"
    if status in {"PAUSED", "BLOCKED", "INTEGRATION_BLOCKED"}:
        return "Paused"
    if status in {"REGISTERED", "CREATED"}:
        return "Preparing"
    if status == "READY" or lifecycle == "REGISTERED":
        return "Planning"
    if status == "VALIDATING":
        return "Validation"
    if projection.get("next_executable_engineering_action"):
        return "Engineering"
    return "Planning"


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
    ready = tuple(_safe_item(item) for item in projection.get("ready_intents", ()))
    blocked = tuple(_safe_item(item) for item in projection.get("blocked_intents", ()))
    discovered = tuple(_safe_item(item) for item in projection.get("discovered_intents", ()))
    return {
        "context_id": f"execution-context:{mission_id}:{context_version}",
        "context_version": context_version,
        "context_schema_version": CONTEXT_SCHEMA_VERSION,
        "mission_id": mission_id,
        "mission_title": state.get("mission_title", state.get("title", mission_id)),
        "mission_lifecycle": projection.get("mission_lifecycle"),
        "business_summary": state.get("business_summary", f"Advance the approved Mission {mission_id}."),
        "engineering_summary": state.get("engineering_summary", "Forge is reconciling the current approved engineering plan."),
        "current_intent": _safe_item(projection.get("current_intent")) or {"message": "No active Intent."},
        "current_engineering_action": _safe_item(projection.get("next_executable_engineering_action")) or {"message": "No current Engineering Action."},
        "execution_phase": _phase(state, projection),
        "planning_confidence": projection.get("planning_confidence"),
        "current_iteration": state.get("current_iteration", 1),
        "completed_intents": [item for item in completed if item],
        "ready_intents": [item for item in ready if item],
        "blocked_intents": [item for item in blocked if item],
        "discovered_intents": [item for item in discovered if item],
        "discarded_intents": [item for item in (_safe_item(value) for value in projection.get("discarded_intents", ())) if item],
        "remaining_engineering_actions": [_safe_item(item) for item in projection.get("remaining_engineering_actions", ()) if _safe_item(item)],
        "last_execution_receipt": receipts[-1] if receipts else None,
        "last_runtime_update": state.get("resume", state.get("resume_point", {})),
        "last_updated_timestamp": _timestamp(state, projection, receipts),
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
