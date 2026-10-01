"""Read-only compatibility view of one legacy Mission execution correlation.

This never migrates state or infers an EP admission, target or execution grant.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


CONTRACT_VERSION = "serial-action-correlation-compat/v1"
_IN_FLIGHT = frozenset({"ACTIVE", "WAITING_FOR_RESULT"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def _safe_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def project_serial_correlation(state: Any) -> dict[str, Any]:
    """Bind a singleton correlation only when its Action identity is provable."""
    base = {"contract_version": CONTRACT_VERSION, "mission_revision": state.revision,
            "read_only": True, "binding_status": "UNAVAILABLE", "reason": "NO_CORRELATION"}
    correlation = state.execution_correlation
    if correlation is None:
        return base
    if not isinstance(correlation, Mapping):
        return {**base, "binding_status": "UNSUPPORTED", "reason": "MALFORMED_CORRELATION"}
    actions = state.actions
    if (not isinstance(actions, (tuple, list)) or not actions
            or any(not isinstance(action, Mapping) or not isinstance(action.get("id"), str)
                   or not action["id"] or not isinstance(action.get("status"), str)
                   for action in actions)
            or len({action["id"] for action in actions}) != len(actions)):
        return {**base, "binding_status": "UNSUPPORTED", "reason": "AMBIGUOUS_ACTION_SET"}
    in_flight = [action for action in actions if action.get("status") in _IN_FLIGHT]
    if len(in_flight) > 1:
        return {**base, "binding_status": "UNSUPPORTED", "reason": "MULTIPLE_IN_FLIGHT_ACTIONS"}
    if len(in_flight) == 1:
        expected_action = in_flight[0]
    elif len(actions) == 1:
        expected_action = actions[0]
    else:
        return {**base, "binding_status": "UNSUPPORTED", "reason": "AMBIGUOUS_ACTION_SET"}
    request = correlation.get("request")
    if request is not None and not isinstance(request, Mapping):
        return {**base, "binding_status": "UNSUPPORTED", "reason": "MALFORMED_REQUEST"}
    if request is not None and any(not _safe_identifier(request.get(key))
                                   for key in ("mission_id", "action_id", "correlation_id")):
        return {**base, "binding_status": "UNSUPPORTED", "reason": "MALFORMED_REQUEST"}
    request = request or {}
    for key in ("mission_id", "action_id", "correlation_id"):
        direct, nested = correlation.get(key), request.get(key)
        if direct is not None and nested is not None and direct != nested:
            return {**base, "binding_status": "UNSUPPORTED", "reason": "IDENTITY_CONFLICT"}
    mission_id = correlation.get("mission_id") or request.get("mission_id")
    action_id = correlation.get("action_id") or request.get("action_id")
    correlation_id = correlation.get("correlation_id") or request.get("correlation_id")
    host_run_id = correlation.get("host_run_id")
    if (mission_id != state.mission_id or not _safe_identifier(mission_id)
            or action_id != expected_action["id"]
            or not _safe_identifier(action_id)
            or not _safe_identifier(correlation_id)
            or host_run_id is not None and not _safe_identifier(host_run_id)):
        return {**base, "binding_status": "UNSUPPORTED", "reason": "IDENTITY_UNVERIFIED"}
    return {**base, "binding_status": "BOUND", "reason": None,
            "action_id": action_id, "action_status": expected_action.get("status"),
            "correlation_id": correlation_id, "host_run_id": host_run_id}
