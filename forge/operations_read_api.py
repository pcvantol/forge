"""Authenticated, read-only HTTP projections for an installed Forge runtime.

The adapter deliberately exposes only already-authoritative installed status and
Mission projections.  It never opens the runtime through ``RuntimeBootstrap``
and therefore cannot initialize, migrate, dispatch, or otherwise mutate Forge.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
from threading import BoundedSemaphore
from typing import Any, Iterator, Mapping
from urllib.parse import unquote, urlsplit

from .__main__ import _status
from .action_frontier import ActionFrontierError, project_action_frontier
from .execution_host_configuration import PeerConfigurationError, read_peer_configuration
from .installed_health import InstalledHealthError, InstalledHealthSnapshotService
from .mission_cli import _status_projection as mission_status_projection
from .models.producer import redact_action_summary
from .runtime.data_root import DataRootResolver


API_VERSION = "1"
DEFAULT_STALE_AFTER = timedelta(minutes=5)
_MISSION_PATH = re.compile(r"^/v1/missions/([^/]+)$")
_PROJECT_ROADMAP_PATH = re.compile(r"^/v1/projects/([^/]+)/roadmap$")
_PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
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
            with self._runtime_snapshot() as (connection, _metadata):
                projection, state = mission_status_projection(connection, mission_id)
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
        times = [item.get("occurred_at") for item in state.state_history if isinstance(item, Mapping)]
        valid_times = [item for item in times if _parse_time(item) is not None]
        observed_at = max(
            valid_times, key=lambda item: _parse_time(item) or datetime.min.replace(tzinfo=UTC),
        ) if valid_times else None
        projection.update({
            "criteria": [_safe_text(item) for item in state.mission.get("acceptance_criteria", ())],
            "actions": [_project_action(item) for item in state.actions],
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
            return {
                "api_version": API_VERSION,
                "contract_version": "project-roadmap-read/v1",
                "instance_id": metadata["runtime_id"],
                "availability": "AVAILABLE" if binding is not None else "UNCONFIGURED",
                "projects": [] if binding is None else [{
                    "project_id": binding.ep_project_id,
                    "repository_id": binding.ep_repository_id,
                    "roadmap_url": f"/v1/projects/{binding.ep_project_id}/roadmap",
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
            if project_id != binding.ep_project_id:
                raise OperationsProjectionError("PROJECT_MISSING", "Project was not found", status=404)
            rows = connection.execute("SELECT mission_id FROM mission_state ORDER BY mission_id LIMIT 257").fetchall()
            if len(rows) > 256:
                raise OperationsProjectionError("PROJECT_TOO_LARGE", "Project projection exceeds the bounded read limit", status=503)
            missions: list[dict[str, Any]] = []
            for (mission_id,) in rows:
                projection, state = mission_status_projection(connection, mission_id)
                if state.mission_id != mission_id or state.mission.get("id") != mission_id:
                    raise OperationsProjectionError("PROJECT_AMBIGUOUS", "Mission identity is inconsistent", status=409)
                source = state.mission.get("repository_evidence_source")
                if not isinstance(source, Mapping) or source.get("repository_id") != binding.ep_repository_id:
                    raise OperationsProjectionError("PROJECT_AMBIGUOUS", "Mission repository binding is inconsistent", status=409)
                actions = [_project_action(item) for item in state.actions]
                ids = {item.get("id") for item in actions}
                if len(ids) != len(actions) or None in ids or any(
                    dependency not in ids
                    for item in actions for dependency in item.get("dependencies", ())
                ):
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
                missions.append({
                    "mission_id": mission_id, "group": group, "status": status,
                    "revision": projection["revision"],
                    "actions": [{key: item[key] for key in ("id", "status", "dependencies") if key in item}
                                for item in actions],
                })
            return {
                "api_version": API_VERSION,
                "contract_version": "project-roadmap-read/v1",
                "instance_id": metadata["runtime_id"],
                "project_id": project_id,
                "repository_id": binding.ep_repository_id,
                "availability": "AVAILABLE",
                "freshness": _freshness(metadata.get("last_access_at"), now=self.clock(), stale_after=self.stale_after),
                "graph_kind": "REPOSITORY_MISSION_ACTION_SUBSET",
                "project_mission_attribution": "UNAVAILABLE",
                "project_capability_graph": "UNAVAILABLE",
                "candidate_and_expected_views": "UNAVAILABLE",
                "repository_scope": {"repository_id": binding.ep_repository_id, "missions": missions},
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
        path = urlsplit(target).path
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

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._respond(api.handle("GET", self.path, self.headers.get("Authorization")))

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._respond(api.handle("POST", self.path, self.headers.get("Authorization")))

        def do_PUT(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._respond(api.handle("PUT", self.path, self.headers.get("Authorization")))

        def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._respond(api.handle("DELETE", self.path, self.headers.get("Authorization")))

        def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._respond(api.handle("PATCH", self.path, self.headers.get("Authorization")))

        def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._respond(api.handle("HEAD", self.path, self.headers.get("Authorization")), body=False)

        def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            self._respond(api.handle("OPTIONS", self.path, self.headers.get("Authorization")))

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
