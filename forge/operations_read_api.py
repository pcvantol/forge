"""Authenticated, read-only HTTP projections for an installed Forge runtime.

The adapter deliberately exposes only already-authoritative installed status and
Mission projections.  It never opens the runtime through ``RuntimeBootstrap``
and therefore cannot initialize, migrate, dispatch, or otherwise mutate Forge.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
from threading import BoundedSemaphore
from typing import Any, Iterator, Mapping
from urllib.parse import quote, unquote, urlsplit

from .__main__ import _status
from .action_frontier import ActionFrontierError, project_action_frontier
from .execution_host_configuration import PeerConfigurationError, read_peer_configuration
from .installed_health import InstalledHealthError, InstalledHealthSnapshotService
from .mission_cli import _status_projection as mission_status_projection
from .models.action import EngineeringActionStatus
from .models.producer import redact_action_summary
from .parallel_action_contract import ParallelActionContractError, validate_peer_graph
from .runtime.data_root import DataRootResolver
from .root_identity import RootIdentity
from .serial_correlation_projection import project_serial_correlation


API_VERSION = "1"
DEFAULT_STALE_AFTER = timedelta(minutes=5)
_MISSION_PATH = re.compile(r"^/v1/missions/([^/]+)$")
_PROJECT_ROADMAP_PATH = re.compile(r"^/v1/projects/([^/]+)/roadmap$")
_PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_ACTION_STATUSES = frozenset(status.value for status in EngineeringActionStatus)
_SENSITIVE_KEY = re.compile(r"(?:authorization|bearer|credential|password|secret|token)", re.IGNORECASE)
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_KEYCHAIN_REFERENCE = re.compile(r"(?i)\bkeychain://[^\s,;]+")
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_TOKEN_VALUE = re.compile(
    r"(?i)\b(?:github_pat_[a-z0-9_]+|gh[pousr]_[a-z0-9]+|sk-[a-z0-9_-]{8,})\b"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[ _-]?key|authorization|bearer|client[ _-]?secret|password|secret|token)\b"
    r"\s*([:=])\s*[^\s,;]+"
)


class OperationsProjectionError(RuntimeError):
    """A safe public failure while reading an authoritative projection."""

    def __init__(self, code: str, message: str, *, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class APIResponse:
    status: int
    body: Mapping[str, Any]
    headers: Mapping[str, str]


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _freshness(observed_at: object, *, now: datetime, stale_after: timedelta) -> str:
    observed = _parse_time(observed_at)
    if observed is None:
        return "UNKNOWN"
    age = now - observed
    return "STALE" if age < timedelta(0) or age > stale_after else "CURRENT"


def _last_recorded_mission_transition(state: Any) -> str | None:
    """Use the persisted Mission timeline, never the runtime's reopen time."""
    history = state.state_history
    if not history or any(not isinstance(item, Mapping) or _parse_time(item.get("occurred_at")) is None
                          for item in history):
        return None
    return max((item["occurred_at"] for item in history),
               key=lambda item: _parse_time(item) or datetime.min.replace(tzinfo=UTC))


def _redact(value: Any) -> Any:
    """Return a JSON-compatible projection with credential-shaped data removed."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        redacted = _BEARER_VALUE.sub("Bearer [REDACTED]", value)
        redacted = _KEYCHAIN_REFERENCE.sub("[REDACTED_CREDENTIAL_REFERENCE]", redacted)
        redacted = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", redacted)
        redacted = _TOKEN_VALUE.sub("[REDACTED]", redacted)
        return _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", redacted)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _safe_text(value: object) -> str:
    """Project one governed text field through the bounded producer redactor."""
    if not isinstance(value, str):
        return ""
    return redact_action_summary(value)


def _selected(document: object, fields: tuple[str, ...]) -> dict[str, Any] | None:
    """Copy only named public lineage fields; arbitrary host mappings never cross the API."""
    if not isinstance(document, Mapping):
        return None
    return {field: _redact(document[field]) for field in fields if field in document}


_REPOSITORY_TRUTH_FIELDS = ("source_id", "revision", "locator", "content_digest")
_REPOSITORY_EVIDENCE_FIELDS = (
    "mission_id", "intent_id", "intent_revision", "action_id", "runtime_prompt_id",
    "correlation_id", "host_run_id", "repository_id", "repository_revision",
    "candidate_revision", "report_id", "content_digest",
)
_EXECUTION_EVIDENCE_FIELDS = (
    "host_id", "receipt_id", "host_run_id", "correlation_id", "report_id", "outcome",
    "retry_of_correlation_id", "execution_started_at", "execution_completed_at", "execution_duration_ms",
)


def _project_repository_evidence(document: object) -> dict[str, Any] | None:
    return _selected(document, _REPOSITORY_EVIDENCE_FIELDS)


def _project_execution_evidence(document: object) -> dict[str, Any] | None:
    projected = _selected(document, _EXECUTION_EVIDENCE_FIELDS)
    if projected is None:
        return None
    repository = document.get("repository_evidence") if isinstance(document, Mapping) else None
    projected["repository_evidence"] = _project_repository_evidence(repository)
    return projected


def _project_action(document: object) -> dict[str, Any]:
    if not isinstance(document, Mapping):
        return {}
    projected = _selected(document, (
        "schema_version", "order", "id", "intent_id", "intent_revision", "dependencies", "status",
    )) or {}
    projected["objective"] = _safe_text(document.get("objective"))
    expected = document.get("expected_evidence", ())
    projected["expected_evidence"] = [
        _safe_text(item) for item in expected if isinstance(item, str)
    ] if isinstance(expected, (list, tuple)) else []
    return projected


def _mission_detail_url(mission_id: str) -> str:
    """Link to the existing authenticated read route using one encoded segment."""
    if mission_id in {".", ".."}:
        raise OperationsProjectionError("PROJECT_AMBIGUOUS", "Mission identity is inconsistent", status=409)
    return "/v1/missions/" + quote(mission_id, safe="")


def _planning_slots_match_current_mission(document: Mapping[str, Any], state: Any) -> bool:
    """Never label a pinned proposal current after same-revision graph drift."""
    mission = state.mission
    if (not isinstance(mission, Mapping)
            or mission.get("status") != "approved_for_engineering"
            or not isinstance(mission.get("scope"), list)
            or any(not isinstance(item, str) for item in mission["scope"])
            or len(set(mission["scope"])) != len(mission["scope"])
            or document.get("approved_scope") != sorted(mission["scope"])):
        return False
    scope = set(mission["scope"])
    actions = state.actions
    proposed = document["actions"]
    if (len(actions) != len(proposed)
            or any(not isinstance(item, Mapping) or not isinstance(item.get("id"), str)
                   for item in actions)
            or len({item["id"] for item in actions}) != len(actions)
            or {item["id"] for item in actions} != {item["action_id"] for item in proposed}):
        return False
    by_id = {item["action_id"]: item for item in proposed}
    for action in actions:
        dependencies = action.get("dependencies")
        if (not isinstance(dependencies, (list, tuple))
                or any(not isinstance(item, str) for item in dependencies)
                or len(set(dependencies)) != len(dependencies)
                or set(dependencies) != {
                    edge["predecessor_action_id"] for edge in by_id[action["id"]]["dependencies"]
                }):
            return False
    return all(item["target"]["repository_id"] in scope for item in proposed)


def _project_serial_execution_slots(rows: list[sqlite3.Row], state: Any) -> dict[str, Any]:
    """Expose only proven identities from the immutable legacy migration record."""
    from types import SimpleNamespace

    base = {"contract_version": "serial-execution-slot-migration/v1", "read_only": True,
            "dispatch_authorized": False, "status": "UNAVAILABLE", "reason": "NOT_MIGRATED",
            "actions": []}
    if not rows:
        serial = project_serial_correlation(state)
        if serial["binding_status"] == "UNSUPPORTED":
            return {**base, "status": "UNSUPPORTED", "reason": serial["reason"]}
        return base
    if len(rows) != 1:
        raise OperationsProjectionError("MISSION_EXECUTION_SLOTS_INVALID", "Mission execution slots are inconsistent", status=409)
    row = rows[0]
    encoded = row[5]
    try:
        document = json.loads(encoded)
    except (TypeError, ValueError):
        document = None
    expected_digest = "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()
    if (not isinstance(document, dict)
            or set(document) != {"contract_version", "mission_id", "action_id", "source_revision",
                                 "source_digest", "action_status", "correlation", "dispatch_authorized"}
            or document["contract_version"] != base["contract_version"]
            or document["mission_id"] != state.mission_id or document["mission_id"] != row[0]
            or document["action_id"] != row[1]
            or not isinstance(document["source_revision"], int)
            or isinstance(document["source_revision"], bool)
            or document["source_revision"] < 1
            or document["source_revision"] != row[2]
            or not isinstance(document["action_status"], str)
            or not document["action_status"]
            or document["source_digest"] != row[3]
            or row[4] != expected_digest or document["dispatch_authorized"] is not False
            or not isinstance(document["correlation"], dict)
            or document["source_digest"] != "sha256:" + sha256(json.dumps(
                document["correlation"], sort_keys=True, separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")).hexdigest()):
        raise OperationsProjectionError("MISSION_EXECUTION_SLOTS_INVALID", "Mission execution slots are inconsistent", status=409)
    binding = project_serial_correlation(SimpleNamespace(
        mission_id=row[0], revision=row[2],
        actions=({"id": row[1], "status": document["action_status"]},),
        execution_correlation=document["correlation"],
    ))
    if binding["binding_status"] != "BOUND" or binding["action_id"] != row[1]:
        raise OperationsProjectionError("MISSION_EXECUTION_SLOTS_INVALID", "Mission execution slots are inconsistent", status=409)
    return {**base, "status": "MIGRATED", "reason": None, "actions": [{
        "action_id": row[1], "correlation_id": binding["correlation_id"],
        "host_run_id": binding["host_run_id"], "source_revision": row[2],
        "dispatch_authorized": False,
    }]}


def _project_assessment(document: object) -> dict[str, Any] | None:
    if not isinstance(document, Mapping):
        return None
    projected = _selected(document, (
        "schema_version", "mission_id", "mission_digest", "evidence_digest",
        "all_required_criteria_proven", "evaluator_version",
    )) or {}
    criteria = []
    for item in document.get("criteria", ()):
        if not isinstance(item, Mapping):
            continue
        criterion = _selected(item, ("criterion_id", "status", "contract_digest")) or {}
        criterion["criterion"] = _safe_text(item.get("criterion"))
        criterion["reason"] = _safe_text(item.get("reason"))
        criterion["execution_evidence"] = [
            _selected(reference, (
                "receipt_id", "action_id", "report_id", "repository_revision",
                "candidate_revision", "repository_evidence_digest",
            ))
            for reference in item.get("execution_evidence", ()) if isinstance(reference, Mapping)
        ]
        criterion["repository_truth"] = _selected(item.get("repository_truth"), _REPOSITORY_TRUTH_FIELDS)
        criteria.append(criterion)
    projected["criteria"] = criteria
    return projected


class InstalledOperationsReadService:
    """Read the exact installed root with SQLite's read-only connection mode."""

    def __init__(self, data_root: str | Path, *, stale_after: timedelta = DEFAULT_STALE_AFTER,
                 clock=lambda: datetime.now(UTC)) -> None:
        if stale_after.total_seconds() <= 0:
            raise ValueError("stale-after interval must be positive")
        self.root = DataRootResolver(cli_data_root=data_root).resolve()
        self.root_identity = RootIdentity(self.root)
        self.stale_after = stale_after
        self.clock = clock

    def installed_status(self) -> dict[str, Any]:
        projection = _status(str(self.root))
        peer = projection.get("execution_host_peer")
        peer_status = peer.get("status") if isinstance(peer, Mapping) else None
        availability = (
            "AVAILABLE"
            if (
                projection.get("initialized") is True
                and projection.get("runtime_status") != "unavailable"
                and peer_status != "ERROR"
            )
            else "UNAVAILABLE"
        )
        observed_at = None
        if availability == "AVAILABLE":
            try:
                with self._runtime_snapshot() as (_connection, metadata):
                    observed_at = metadata.get("last_access_at")
            except (PeerConfigurationError, OSError, sqlite3.Error):
                availability = "UNAVAILABLE"
        return _redact({
            "api_version": API_VERSION,
            "availability": availability,
            "freshness": "UNAVAILABLE" if availability == "UNAVAILABLE" else _freshness(
                observed_at, now=self.clock(), stale_after=self.stale_after,
            ),
            "source_observed_at": observed_at,
            "read_only": True,
            "runtime": projection,
        })

    def mission_detail(self, mission_id: str) -> dict[str, Any]:
        if not mission_id or len(mission_id) > 128 or any(ord(character) < 33 for character in mission_id):
            raise OperationsProjectionError("MISSION_REFERENCE_INVALID", "Mission reference is invalid", status=400)
        try:
            with self._runtime_snapshot() as (connection, metadata):
                projection, state = mission_status_projection(connection, mission_id)
                slot_row = connection.execute(
                    "SELECT mission_revision,document_digest,document FROM mission_action_slot_snapshots "
                    "WHERE mission_id=? ORDER BY mission_revision DESC LIMIT 1", (mission_id,)
                ).fetchone()
                execution_rows = connection.execute(
                    "SELECT mission_id,action_id,source_revision,source_digest,document_digest,document "
                    "FROM mission_action_execution_slots WHERE mission_id=? ORDER BY action_id", (mission_id,)
                ).fetchall()
                binding = self._project_binding(connection, metadata) if slot_row is not None else None
        except ValueError as error:
            if str(error) == "unknown Mission":
                raise OperationsProjectionError("MISSION_MISSING", "Mission was not found", status=404) from None
            raise OperationsProjectionError("MISSION_UNAVAILABLE", "Mission projection is unavailable", status=503) from error
        except (PeerConfigurationError, OSError, sqlite3.Error):
            raise OperationsProjectionError("MISSION_UNAVAILABLE", "Mission projection is unavailable", status=503) from None
        stored_mission_id = state.mission.get("id") if isinstance(state.mission, Mapping) else None
        if state.mission_id != mission_id or stored_mission_id != mission_id or projection.get("mission_id") != mission_id:
            raise OperationsProjectionError(
                "MISSION_AMBIGUOUS", "Mission identity is inconsistent", status=409,
            )
        planning_slots: dict[str, Any] | None = None
        if slot_row is not None:
            encoded = slot_row[2]
            expected_digest = "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()
            try:
                document = json.loads(encoded)
            except (TypeError, ValueError):
                document = None
            try:
                validated = validate_peer_graph({key: value for key, value in document.items()
                                                 if key not in {"dispatch_authorized", "approved_scope"}}) if isinstance(document, dict) else None
            except ParallelActionContractError:
                validated = None
            if (slot_row[1] != expected_digest or not isinstance(document, dict)
                    or {key: value for key, value in document.items() if key != "approved_scope"} != validated
                    or ("approved_scope" in document and
                        (not isinstance(document["approved_scope"], list)
                         or any(not isinstance(item, str) for item in document["approved_scope"])
                         or document["approved_scope"] != sorted(set(document["approved_scope"]))))
                    or document.get("mission_id") != mission_id
                    or document.get("mission_revision") != slot_row[0]
                    or document.get("dispatch_authorized") is not False):
                raise OperationsProjectionError(
                    "MISSION_ACTION_SLOTS_INVALID", "Mission Action slots are inconsistent", status=409,
                )
            if (slot_row[0] == state.revision
                    and not _planning_slots_match_current_mission(document, state)):
                raise OperationsProjectionError(
                    "MISSION_ACTION_SLOTS_DRIFT", "Mission Action slots no longer match the Mission", status=409,
                )
            slot_freshness = "CURRENT" if slot_row[0] == state.revision else "STALE"
            actions = []
            for action in document["actions"]:
                target = action["target"]
                if slot_freshness != "CURRENT":
                    resolution = "STALE"
                elif binding is None:
                    resolution = "UNCONFIGURED"
                elif (target["ep_instance_id"] == binding.expected_ep_instance_id
                      and target["project_id"] == binding.ep_project_id
                      and target["repository_id"] == binding.ep_repository_id):
                    resolution = "MATCHED_SELECTED_BINDING"
                else:
                    resolution = "MISMATCH"
                actions.append({**action, "selected_binding_resolution": resolution,
                                "baseline_verification": "UNVERIFIED"})
            resolutions = {action["selected_binding_resolution"] for action in actions}
            planning_slots = {
                "contract_version": document.get("contract_version"),
                "mission_revision": slot_row[0],
                "document_digest": expected_digest,
                "freshness": slot_freshness,
                "target_verification": "UNVERIFIED",
                "selected_binding_resolution": resolutions.pop() if len(resolutions) == 1 else "MIXED",
                "dispatch_authorized": False,
                "actions": actions,
            }
        observed_at = _last_recorded_mission_transition(state)
        projection.update({
            "criteria": [_safe_text(item) for item in state.mission.get("acceptance_criteria", ())],
            "actions": [_project_action(item) for item in state.actions],
            "planning_slots": planning_slots,
            "execution_slots": _project_serial_execution_slots(execution_rows, state),
            "serial_correlation": project_serial_correlation(state),
            "evidence_lineage": {
                "execution_evidence": _project_execution_evidence(state.execution_evidence),
                "execution_attempts": [_project_execution_evidence(item) for item in state.execution_history],
                "repository_truth": _selected(state.repository_truth, _REPOSITORY_TRUTH_FIELDS),
                "criterion_assessment": _project_assessment(state.completion),
                "criterion_assessment_history": [_project_assessment(item) for item in state.completion_history],
            },
        })
        try:
            projection["action_frontier"] = project_action_frontier(
                state.actions, mission_revision=state.revision,
                pinned_slots=planning_slots if planning_slots is not None
                and planning_slots["freshness"] == "CURRENT" else None,
            )
        except ActionFrontierError:
            raise OperationsProjectionError(
                "MISSION_ACTION_GRAPH_INVALID", "Mission Action graph is inconsistent", status=409,
            ) from None
        return _redact({
            "api_version": API_VERSION,
            "availability": "AVAILABLE",
            "freshness": _freshness(observed_at, now=self.clock(), stale_after=self.stale_after),
            "source_observed_at": observed_at,
            "read_only": True,
            "mission": projection,
        })

    def project_index(self) -> dict[str, Any]:
        """Expose only the project selected by this exact Forge instance binding."""
        with self._runtime_snapshot() as (connection, metadata):
            binding = self._project_binding(connection, metadata)
            if binding is not None and (
                not isinstance(binding.ep_project_id, str)
                or _PROJECT_ID.fullmatch(binding.ep_project_id) is None
                or binding.ep_project_id in {".", ".."}
            ):
                raise OperationsProjectionError("PROJECT_UNAVAILABLE", "Project binding is unavailable", status=503)
            return {
                "api_version": API_VERSION,
                "contract_version": "project-roadmap-read/v1",
                "instance_id": metadata["runtime_id"],
                "availability": "AVAILABLE" if binding is not None else "UNCONFIGURED",
                "projects": [] if binding is None else [{
                    "project_id": binding.ep_project_id,
                    "repository_id": binding.ep_repository_id,
                    "roadmap_url": f"/v1/projects/{quote(binding.ep_project_id, safe='')}/roadmap",
                }],
                "read_only": True,
            }

    def project_roadmap(self, project_id: str) -> dict[str, Any]:
        """Project the installed Mission/Action subset from one SQLite snapshot."""
        if _PROJECT_ID.fullmatch(project_id) is None:
            raise OperationsProjectionError("PROJECT_REFERENCE_INVALID", "Project reference is invalid", status=400)
        with self._runtime_snapshot() as (connection, metadata):
            binding = self._project_binding(connection, metadata)
            if binding is None:
                raise OperationsProjectionError("PROJECT_UNCONFIGURED", "Project binding is not configured", status=503)
            if (not isinstance(binding.ep_project_id, str)
                    or _PROJECT_ID.fullmatch(binding.ep_project_id) is None
                    or binding.ep_project_id in {".", ".."}):
                raise OperationsProjectionError("PROJECT_UNAVAILABLE", "Project binding is unavailable", status=503)
            if project_id != binding.ep_project_id:
                raise OperationsProjectionError("PROJECT_MISSING", "Project was not found", status=404)
            rows = connection.execute("SELECT mission_id FROM mission_state ORDER BY mission_id LIMIT 257").fetchall()
            if len(rows) > 256:
                raise OperationsProjectionError("PROJECT_TOO_LARGE", "Project projection exceeds the bounded read limit", status=503)
            missions: list[dict[str, Any]] = []
            mission_observations: list[str | None] = []
            now = self.clock()
            for (mission_id,) in rows:
                projection, state = mission_status_projection(connection, mission_id)
                if (not isinstance(mission_id, str) or not mission_id
                        or len(mission_id) > 128
                        or any(ord(character) < 33 for character in mission_id)
                        or state.mission_id != mission_id or state.mission.get("id") != mission_id):
                    raise OperationsProjectionError("PROJECT_AMBIGUOUS", "Mission identity is inconsistent", status=409)
                source = state.mission.get("repository_evidence_source")
                if not isinstance(source, Mapping) or source.get("repository_id") != binding.ep_repository_id:
                    raise OperationsProjectionError("PROJECT_AMBIGUOUS", "Mission repository binding is inconsistent", status=409)
                actions = [_project_action(item) for item in state.actions]
                if (len(actions) > 256
                        or any(not isinstance(item.get("id"), str) or not item["id"]
                               or not isinstance(item.get("status"), str)
                               or item["status"] not in _ACTION_STATUSES
                               or not isinstance(item.get("dependencies"), list)
                               for item in actions)):
                    raise OperationsProjectionError("PROJECT_DAG_INVALID", "Mission Action graph is inconsistent", status=409)
                ids = {item.get("id") for item in actions}
                if (len(ids) != len(actions) or any(
                    not isinstance(dependency, str) or dependency not in ids
                    for item in actions for dependency in item["dependencies"]
                )):
                    raise OperationsProjectionError("PROJECT_DAG_INVALID", "Mission Action graph is inconsistent", status=409)
                dependencies = {item["id"]: tuple(item.get("dependencies", ())) for item in actions}
                active: set[str] = set()
                complete: set[str] = set()

                def visit(action_id: str) -> None:
                    if action_id in active:
                        raise OperationsProjectionError("PROJECT_DAG_INVALID", "Mission Action graph has a cycle", status=409)
                    if action_id in complete:
                        return
                    active.add(action_id)
                    for predecessor in dependencies[action_id]:
                        visit(predecessor)
                    active.remove(action_id)
                    complete.add(action_id)

                for action_id in dependencies:
                    visit(action_id)
                status = str(projection["status"])
                group = ("APPROVED_PENDING" if status == "APPROVED_PLANNABLE" else
                         "HISTORY" if status in {"COMPLETED", "ARCHIVED"} else "ACTIVE")
                observed_at = _last_recorded_mission_transition(state)
                mission_observations.append(observed_at)
                missions.append({
                    "mission_id": mission_id, "mission_detail_url": _mission_detail_url(mission_id),
                    "group": group, "status": status,
                    "revision": projection["revision"],
                    "source_observed_at": observed_at,
                    "freshness": _freshness(observed_at, now=now, stale_after=self.stale_after),
                    "actions": [{key: item[key] for key in ("id", "status", "dependencies") if key in item}
                                for item in actions],
                })
            complete_observations = bool(mission_observations) and all(
                item is not None for item in mission_observations
            )
            source_observed_at = (
                min(mission_observations, key=lambda item: _parse_time(item) or datetime.max.replace(tzinfo=UTC))
                if complete_observations else None
            )
            freshness = (
                "UNKNOWN" if not complete_observations else
                "STALE" if any(item["freshness"] == "STALE" for item in missions) else "CURRENT"
            )
            active_mission_ids = [item["mission_id"] for item in missions if item["group"] == "ACTIVE"]
            active_multiplicity = (
                "NONE" if not active_mission_ids else
                "SINGLE" if len(active_mission_ids) == 1 else "UNSUPPORTED_MULTIPLE"
            )
            return {
                "api_version": API_VERSION,
                "contract_version": "project-roadmap-read/v1",
                "instance_id": metadata["runtime_id"],
                "project_id": project_id,
                "repository_id": binding.ep_repository_id,
                "availability": "AVAILABLE",
                "freshness": freshness,
                "source_observed_at": source_observed_at,
                "graph_kind": "REPOSITORY_MISSION_ACTION_SUBSET",
                "project_mission_attribution": "UNAVAILABLE",
                "project_capability_graph": "UNAVAILABLE",
                "candidate_and_expected_views": "UNAVAILABLE",
                "repository_scope": {
                    "repository_id": binding.ep_repository_id,
                    "active_mission_ids": active_mission_ids,
                    "active_mission_count": len(active_mission_ids),
                    "active_mission_multiplicity": active_multiplicity,
                    "missions": missions,
                },
                "read_only": True,
            }

    def _project_binding(self, connection: sqlite3.Connection, metadata: Mapping[str, str]):
        """Join peer readback to the same storage generation as Mission state."""
        readback = read_peer_configuration(self.root)
        if readback.runtime_id != metadata.get("runtime_id") or readback.status not in {
            "CONFIGURED", "NOT_CONFIGURED", "DETACHED",
        }:
            raise OperationsProjectionError("PROJECT_UNAVAILABLE", "Project binding is unavailable", status=503)
        row = connection.execute(
            "SELECT configuration_digest FROM execution_host_peer_configuration WHERE singleton=1"
        ).fetchone()
        expected = readback.configuration.configuration_digest if readback.configuration is not None else None
        if (row[0] if row is not None else None) != expected:
            raise OperationsProjectionError("PROJECT_UNAVAILABLE", "Project binding changed during readback", status=503)
        return readback.configuration

    def installed_health_snapshot(self) -> dict[str, Any]:
        """Return the canonical bounded installed-health assessment."""
        return InstalledHealthSnapshotService(
            self.root, clock=self.clock,
        ).installed_health_snapshot()

    @contextmanager
    def _runtime_snapshot(self) -> Iterator[tuple[sqlite3.Connection, dict[str, str]]]:
        """Validate the installed identity, then hold one consistent read transaction."""
        readback = read_peer_configuration(self.root)
        database = self.root / "forge.db"
        connection = None
        try:
            connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise PeerConfigurationError("Forge runtime database integrity check failed")
            metadata = dict(connection.execute("SELECT key, value FROM runtime_metadata"))
            try:
                schema = int(metadata["schema_version"])
                migration = int(metadata["migration_version"])
                user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            except (KeyError, TypeError, ValueError):
                raise PeerConfigurationError("Forge runtime storage schema is unreadable") from None
            marker_path = self.root / "instance" / "runtime-instance.json"
            marker = marker_path.read_text(encoding="utf-8").strip()
            if (
                metadata.get("runtime_id") != readback.runtime_id
                or marker != readback.runtime_id
                or schema != migration
                or schema != user_version
                or schema != readback.storage_schema
            ):
                raise PeerConfigurationError("Forge runtime identity or storage schema changed during readback")
            yield connection, metadata
            if marker_path.read_text(encoding="utf-8").strip() != readback.runtime_id:
                raise PeerConfigurationError("Forge runtime identity changed during readback")
        finally:
            if connection is not None:
                connection.close()


def origin_form_path(target: str) -> str:
    """Accept only an unambiguous HTTP origin-form request target."""
    if (
        not isinstance(target, str)
        or not target.isascii()
        or not target.startswith("/")
        or target.startswith("//")
        or "#" in target
        or "\\" in target
        or any(ord(character) < 32 or ord(character) == 127 for character in target)
    ):
        raise ValueError("request target is not origin-form")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/") or parsed.path.startswith("//"):
        raise ValueError("request target is not origin-form")
    return parsed.path


def raw_request_target(requestline: bytes) -> str:
    """Extract an ASCII target without Unicode whitespace normalization."""
    parts = requestline.rstrip(b"\r\n").split(b" ")
    if len(parts) != 3 or not all(parts):
        raise ValueError("request line is invalid")
    try:
        return parts[1].decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("request target is not ASCII") from error


class OperationsReadAPI:
    """Small transport adapter with constant-time bearer authentication."""

    def __init__(self, service: InstalledOperationsReadService, bearer_credential: str) -> None:
        if not isinstance(bearer_credential, str) or not bearer_credential:
            raise ValueError("operations API bearer credential must be non-empty")
        self.service = service
        self._credential = bearer_credential

    def handle(self, method: str, target: str, authorization: str | None) -> APIResponse:
        headers = {
            "Cache-Control": "no-store",
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        }
        if not self._authenticated(authorization):
            return APIResponse(401, self._error("AUTHENTICATION_REQUIRED", "Authentication is required"), headers)
        if self.service.root_identity.drifted():
            return APIResponse(503, self._error("INSTANCE_UNAVAILABLE", "Selected instance is unavailable"), headers)
        try:
            path = origin_form_path(target)
        except ValueError:
            return APIResponse(400, self._error("REQUEST_INVALID", "Request target must be origin-form"), headers)
        if method != "GET":
            return APIResponse(405, self._error("METHOD_NOT_ALLOWED", "Only read-only GET is supported"), {
                **headers, "Allow": "GET",
            })
        try:
            if path == "/v1/status":
                body = self.service.installed_status()
                status = 503 if body.get("availability") == "UNAVAILABLE" else 200
                return APIResponse(status, body, headers)
            if path == "/v1/health":
                body = self.service.installed_health_snapshot()
                return APIResponse(200 if body.get("outcome") == "HEALTHY" else 503, body, headers)
            if path == "/v1/projects":
                return APIResponse(200, self.service.project_index(), headers)
            project_match = _PROJECT_ROADMAP_PATH.fullmatch(path)
            if project_match:
                return APIResponse(200, self.service.project_roadmap(unquote(project_match.group(1))), headers)
            match = _MISSION_PATH.fullmatch(path)
            if match:
                return APIResponse(200, self.service.mission_detail(unquote(match.group(1))), headers)
            return APIResponse(404, self._error("ROUTE_NOT_FOUND", "Route was not found"), headers)
        except OperationsProjectionError as error:
            return APIResponse(error.status, self._error(error.code, str(error)), headers)
        except InstalledHealthError as error:
            return APIResponse(503, self._error(error.code, str(error)), headers)
        except Exception:
            return APIResponse(503, self._error("PROJECTION_UNAVAILABLE", "Read-only projection is unavailable"), headers)

    def _authenticated(self, authorization: str | None) -> bool:
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            return False
        supplied = authorization[7:]
        return bool(supplied) and secrets.compare_digest(supplied, self._credential)

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"api_version": API_VERSION, "error": {"code": code, "message": message}, "read_only": True}


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._slots = BoundedSemaphore(16)
        super().__init__(*args, **kwargs)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(5.0)
        return request, address

    def process_request(self, request, client_address) -> None:
        self._slots.acquire()
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def make_server(host: str, port: int, api: OperationsReadAPI) -> ThreadingHTTPServer:
    """Create the foreground local HTTP server without starting a background writer."""
    if host != "127.0.0.1":
        raise ValueError("operations read API is restricted to IPv4 loopback")
    if isinstance(port, bool) or port < 0 or port > 65535:
        raise ValueError("operations read API port is invalid")

    class Handler(BaseHTTPRequestHandler):
        server_version = "ForgeOperationsReadAPI/1"
        sys_version = ""

        def send_error(self, code: int, message: str | None = None,
                       explain: str | None = None) -> None:
            # Parser errors can include the raw request line or method.
            self.close_connection = True
            response = APIResponse(code, OperationsReadAPI._error(
                "REQUEST_INVALID", "HTTP request was rejected",
            ), {
                "Cache-Control": "no-store",
                "Content-Type": "application/json; charset=utf-8",
                "X-Content-Type-Options": "nosniff",
                "Connection": "close",
            })
            self._respond(response, body=getattr(self, "command", None) != "HEAD")

        def _dispatch(self, method: str, *, body: bool = True) -> None:
            authorizations = self.headers.get_all("Authorization", [])
            try:
                target = raw_request_target(self.raw_requestline)
            except ValueError:
                target = None
            if len(authorizations) > 1 or target is None:
                response = APIResponse(400, OperationsReadAPI._error(
                    "REQUEST_INVALID", "request Authorization or target is invalid",
                ), {"Cache-Control": "no-store",
                    "Content-Type": "application/json; charset=utf-8",
                    "X-Content-Type-Options": "nosniff"})
            else:
                response = api.handle(method, target,
                                      authorizations[0] if authorizations else None)
            self._respond(response, body=body)

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._dispatch("POST")

        def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._dispatch("PUT")

        def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._dispatch("DELETE")

        def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._dispatch("PATCH")

        def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._dispatch("HEAD", body=False)

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._dispatch("OPTIONS")

        def log_message(self, _format: str, *_args: object) -> None:
            # Request targets and headers are intentionally not logged here.
            return

        def _respond(self, response: APIResponse, *, body: bool = True) -> None:
            payload = json.dumps(response.body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if body:
                self.wfile.write(payload)

    return _Server((host, port), Handler)


def read_bearer_credential(path: str | Path) -> str:
    """Read one private credential file without returning its contents in errors."""
    credential_path = Path(path).expanduser().resolve()
    try:
        stat = credential_path.stat()
        if not credential_path.is_file() or stat.st_mode & 0o077:
            raise ValueError("operations API credential file must be private")
        value = credential_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ValueError("operations API credential file is unavailable") from error
    if not value or "\n" in value or "\r" in value:
        raise ValueError("operations API credential file is invalid")
    return value


def serve(data_root: str | Path, credential_file: str | Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    credential = read_bearer_credential(credential_file)
    api = OperationsReadAPI(InstalledOperationsReadService(data_root), credential)
    with make_server(host, port, api) as server:
        server.serve_forever()
