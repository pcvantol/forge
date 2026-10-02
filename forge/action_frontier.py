"""Bounded, read-only logical Action frontier for an installed Mission.

This projection never decides host admission. A stored Action has no durable
per-Action target or predecessor evidence predicate in the serial schema, so
the result must not be interpreted as a dispatchable parallel workset.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any


FRONTIER_CONTRACT_VERSION = "parallel-action-frontier/v2"
MAX_FRONTIER_ACTIONS = 256
_STATUSES = frozenset({"READY", "ACTIVE", "WAITING_FOR_RESULT", "COMPLETE", "BLOCKED", "FAILED"})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_BINDING_RESOLUTIONS = frozenset({"MATCHED_SELECTED_BINDING", "MISMATCH", "UNCONFIGURED"})


class ActionFrontierError(ValueError):
    """The installed Action graph cannot be safely represented as a DAG."""


def project_action_frontier(actions: Sequence[Mapping[str, Any]], *, mission_revision: int,
                            pinned_slots: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a deterministic logical frontier without claiming execution eligibility."""
    if len(actions) > MAX_FRONTIER_ACTIONS:
        raise ActionFrontierError("Mission Action graph exceeds the bounded read limit")
    if not isinstance(mission_revision, int) or isinstance(mission_revision, bool) or mission_revision < 1:
        raise ActionFrontierError("Mission graph revision is invalid")
    nodes: dict[str, dict[str, Any]] = {}
    orders: set[int] = set()
    for action in actions:
        if not isinstance(action, Mapping):
            raise ActionFrontierError("Mission Action record is invalid")
        action_id = action.get("id")
        order = action.get("order")
        status = action.get("status")
        edges = action.get("dependencies", ())
        if (not isinstance(action_id, str) or not action_id or action_id in nodes
                or not isinstance(order, int) or isinstance(order, bool) or order < 1 or order in orders
                or not isinstance(status, str) or status not in _STATUSES
                or not isinstance(edges, (list, tuple))
                or any(not isinstance(edge, str) or not edge for edge in edges)
                or len(edges) != len(set(edges))):
            raise ActionFrontierError("Mission Action identity, order, status or edges are invalid")
        orders.add(order)
        nodes[action_id] = {"action_id": action_id, "order": order, "status": status,
                            "dependencies": tuple(edges)}
    for node in nodes.values():
        if node["action_id"] in node["dependencies"] or any(
            edge not in nodes for edge in node["dependencies"]
        ):
            raise ActionFrontierError("Mission Action graph has an unresolved edge")
    active: set[str] = set()
    complete: set[str] = set()

    def visit(action_id: str) -> None:
        if action_id in active:
            raise ActionFrontierError("Mission Action graph has a cycle")
        if action_id in complete:
            return
        active.add(action_id)
        for predecessor in nodes[action_id]["dependencies"]:
            visit(predecessor)
        active.remove(action_id)
        complete.add(action_id)

    for action_id in nodes:
        visit(action_id)
    target_slots: dict[str, Mapping[str, Any]] = {}
    source_slot_digest = None
    if pinned_slots is not None:
        if not isinstance(pinned_slots, Mapping):
            raise ActionFrontierError("Mission Action target slots are invalid")
        entries = pinned_slots.get("actions")
        digest = pinned_slots.get("document_digest")
        if (pinned_slots.get("freshness") != "CURRENT"
                or not isinstance(pinned_slots.get("mission_revision"), int)
                or isinstance(pinned_slots["mission_revision"], bool)
                or pinned_slots["mission_revision"] != mission_revision
                or pinned_slots.get("target_verification") != "UNVERIFIED"
                or pinned_slots.get("dispatch_authorized") is not False
                or not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None
                or not isinstance(entries, list) or len(entries) != len(nodes)):
            raise ActionFrontierError("Mission Action target slots are not current and pinned")
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ActionFrontierError("Mission Action target slot is invalid")
            action_id = entry.get("action_id")
            target = entry.get("target")
            if (not isinstance(action_id, str) or action_id not in nodes or action_id in target_slots
                    or not isinstance(target, Mapping)
                    or not isinstance(target.get("repository_id"), str)
                    or not target["repository_id"]
                    or entry.get("baseline_verification") != "UNVERIFIED"
                    or not isinstance(entry.get("selected_binding_resolution"), str)
                    or entry["selected_binding_resolution"] not in _BINDING_RESOLUTIONS):
                raise ActionFrontierError("Mission Action target slot is invalid")
            target_slots[action_id] = entry
        source_slot_digest = digest
    ordered = sorted(nodes.values(), key=lambda node: (node["order"], node["action_id"]))
    frontier: list[str] = []
    projected: list[dict[str, Any]] = []
    for node in ordered:
        dependencies = node["dependencies"]
        if node["status"] != "READY":
            logical_state = node["status"]
        elif any(nodes[edge]["status"] in {"FAILED", "BLOCKED"} for edge in dependencies):
            logical_state = "BLOCKED_BY_PREDECESSOR"
        elif any(nodes[edge]["status"] != "COMPLETE" for edge in dependencies):
            logical_state = "WAITING_FOR_PREDECESSOR"
        elif dependencies:
            # Serial storage does not bind a verified predicate to each edge.
            logical_state = "WAITING_FOR_VERIFIED_EVIDENCE"
        else:
            logical_state = "LOGICALLY_ELIGIBLE"
            frontier.append(node["action_id"])
        slot = target_slots.get(node["action_id"])
        projected.append({
            "action_id": node["action_id"], "order": node["order"], "status": node["status"],
            "dependencies": list(dependencies), "logical_state": logical_state,
            "target_repository_id": slot["target"]["repository_id"] if slot else None,
            "target_resolution": "PINNED_UNVERIFIED" if slot else "UNAVAILABLE",
            "selected_binding_resolution": slot["selected_binding_resolution"] if slot else "UNAVAILABLE",
            "baseline_verification": "UNVERIFIED" if slot else "UNAVAILABLE",
            "dependency_evidence_resolution": "UNAVAILABLE" if dependencies else "NOT_REQUIRED",
            "dispatchable": False,
        })
    return {
        "contract_version": FRONTIER_CONTRACT_VERSION,
        "source_mission_revision": mission_revision,
        "source_slot_digest": source_slot_digest,
        "graph_kind": "STORED_ACTION_LOGICAL_DAG",
        "logical_frontier_action_ids": frontier,
        "actions": projected,
        "parallel_execution": "NOT_QUALIFIED",
        "read_only": True,
    }
