"""Versioned, authority-free compatibility contract for parallel Action graphs.

This validates a producer document for peer compatibility testing. It does not
resolve an EP binding, prove a grant, materialize Actions, or admit execution.
"""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


PEER_GRAPH_CONTRACT_VERSION = "parallel-action-graph/v1"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_EVIDENCE_KINDS = frozenset({"QUALIFIED_ARTIFACT", "REPOSITORY_REVISION"})


class ParallelActionContractError(ValueError):
    """A peer compatibility graph is malformed or self-contradictory."""


def _identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


def validate_peer_graph(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize an explicit-target test vector, never a grant."""
    if (not isinstance(document, Mapping)
            or set(document) != {"contract_version", "mission_id", "mission_revision", "actions"}
            or document.get("contract_version") != PEER_GRAPH_CONTRACT_VERSION
            or not _identifier(document.get("mission_id"))
            or not isinstance(document.get("mission_revision"), int)
            or isinstance(document["mission_revision"], bool) or document["mission_revision"] < 1
            or not isinstance(document.get("actions"), list)
            or not 1 <= len(document["actions"]) <= 256):
        raise ParallelActionContractError("parallel Action graph envelope is invalid")
    actions: dict[str, dict[str, Any]] = {}
    for item in document["actions"]:
        if (not isinstance(item, Mapping)
                or set(item) != {"action_id", "target", "dependencies"}
                or not _identifier(item.get("action_id"))
                or item["action_id"] in actions
                or not isinstance(item.get("target"), Mapping)
                or set(item["target"]) != {
                    "ep_instance_id", "project_id", "repository_id", "baseline_revision",
                }
                or any(not _identifier(item["target"].get(key)) for key in item["target"])
                or not isinstance(item.get("dependencies"), list)):
            raise ParallelActionContractError("parallel Action or target is invalid")
        dependencies: list[dict[str, Any]] = []
        seen: set[str] = set()
        for edge in item["dependencies"]:
            if (not isinstance(edge, Mapping)
                    or set(edge) != {"predecessor_action_id", "required_evidence"}
                    or not _identifier(edge.get("predecessor_action_id"))
                    or edge["predecessor_action_id"] == item["action_id"]
                    or edge["predecessor_action_id"] in seen
                    or not isinstance(edge.get("required_evidence"), Mapping)
                    or set(edge["required_evidence"]) != {"kind", "repository_id", "content_digest"}
                    or not isinstance(edge["required_evidence"].get("kind"), str)
                    or edge["required_evidence"]["kind"] not in _EVIDENCE_KINDS
                    or not _identifier(edge["required_evidence"].get("repository_id"))
                    or not isinstance(edge["required_evidence"].get("content_digest"), str)
                    or _DIGEST.fullmatch(edge["required_evidence"]["content_digest"]) is None):
                raise ParallelActionContractError("parallel Action predecessor evidence is invalid")
            seen.add(edge["predecessor_action_id"])
            dependencies.append({
                "predecessor_action_id": edge["predecessor_action_id"],
                "required_evidence": dict(edge["required_evidence"]),
            })
        actions[item["action_id"]] = {
            "action_id": item["action_id"], "target": dict(item["target"]),
            "dependencies": dependencies,
        }
    for action in actions.values():
        for edge in action["dependencies"]:
            predecessor = actions.get(edge["predecessor_action_id"])
            if (predecessor is None or edge["required_evidence"]["repository_id"]
                    != predecessor["target"]["repository_id"]):
                raise ParallelActionContractError("parallel Action evidence target is inconsistent")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(action_id: str) -> None:
        if action_id in visiting:
            raise ParallelActionContractError("parallel Action graph has a cycle")
        if action_id in visited:
            return
        visiting.add(action_id)
        for edge in actions[action_id]["dependencies"]:
            visit(edge["predecessor_action_id"])
        visiting.remove(action_id)
        visited.add(action_id)

    for action_id in actions:
        visit(action_id)
    return {
        "contract_version": PEER_GRAPH_CONTRACT_VERSION,
        "mission_id": document["mission_id"], "mission_revision": document["mission_revision"],
        "actions": [actions[key] for key in sorted(actions)],
        "dispatch_authorized": False,
    }
