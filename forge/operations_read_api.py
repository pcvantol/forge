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
from time import monotonic
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import unquote, urlsplit

from .__main__ import _status
from ._version import canonical_version
from .execution_host_configuration import (
    EngineeringPlatformExecutionHostFactory,
    EngineeringPlatformPeerConfiguration,
    PeerConfigurationError,
    PeerObservationTimeout,
    read_peer_configuration_snapshot,
)
from .mission_cli import _status_projection as mission_status_projection
from .models.execution_host import ExecutionHostTemporaryUnavailable
from .models.producer import redact_action_summary
from .runtime.data_root import DataRootResolver
from .runtime.database import RUNTIME_SCHEMA_VERSION
from .runtime.health import (
    INSTALLED_HEALTH_CAPABILITIES,
    CheckPurpose,
    HealthIdentity,
    HealthObservation,
    ObservationState,
    evaluate_health,
    installed_health_registry,
)
from .secure_store import MacOSKeychainSecureStoreAdapter


API_VERSION = "1"
DEFAULT_STALE_AFTER = timedelta(minutes=5)
DEFAULT_QUERY_TIMEOUT_SECONDS = 1.0
_MISSION_PATH = re.compile(r"^/v1/missions/([^/]+)$")
_LIVENESS_PATH = "/v1/health/live"
_READINESS_PATH = "/v1/health/readiness"
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
PeerHealthObserver = Callable[
    [HealthIdentity, EngineeringPlatformPeerConfiguration, datetime, float],
    HealthObservation,
]


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
                 clock=lambda: datetime.now(UTC),
                 query_timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
                 query_clock=monotonic,
                 peer_observer: PeerHealthObserver | None = None) -> None:
        if stale_after.total_seconds() <= 0:
            raise ValueError("stale-after interval must be positive")
        if (
            not isinstance(query_timeout_seconds, (int, float))
            or isinstance(query_timeout_seconds, bool)
            or not 0 < float(query_timeout_seconds) <= 10
        ):
            raise ValueError("query timeout must be greater than zero and at most 10 seconds")
        self.root = DataRootResolver(cli_data_root=data_root).resolve()
        self.stale_after = stale_after
        self.clock = clock
        self.query_timeout_seconds = float(query_timeout_seconds)
        self.query_clock = query_clock
        self.peer_observer = peer_observer or self._observe_execution_peer

    @staticmethod
    def _caused_by_timeout(error: BaseException) -> bool:
        current: BaseException | None = error
        while current is not None:
            if isinstance(current, TimeoutError) or isinstance(getattr(current, "reason", None), TimeoutError):
                return True
            current = current.__cause__
        return False

    @staticmethod
    def _peer_observation(
        identity: HealthIdentity,
        state: ObservationState,
        observed_at: datetime,
        reason_code: str | None,
    ) -> HealthObservation:
        return HealthObservation(
            identity,
            "ep_peer",
            "execution_peer",
            CheckPurpose.READINESS,
            ("dispatch",),
            state,
            observed_at,
            reason_code=reason_code,
        )

    def _observe_execution_peer(
        self,
        identity: HealthIdentity,
        configuration: EngineeringPlatformPeerConfiguration,
        _requested_at: datetime,
        timeout_seconds: float,
    ) -> HealthObservation:
        """Collect one bounded authoritative EP compatibility observation."""
        factory = EngineeringPlatformExecutionHostFactory(
            MacOSKeychainSecureStoreAdapter(timeout=timeout_seconds),
        )
        try:
            factory.preflight_configuration(configuration, timeout_seconds=timeout_seconds)
        except PeerObservationTimeout:
            return self._peer_observation(
                identity, ObservationState.TIMED_OUT, self.clock(), "PEER_OBSERVATION_TIMED_OUT",
            )
        except ExecutionHostTemporaryUnavailable as error:
            if self._caused_by_timeout(error):
                return self._peer_observation(
                    identity, ObservationState.TIMED_OUT, self.clock(), "PEER_OBSERVATION_TIMED_OUT",
                )
            return self._peer_observation(
                identity, ObservationState.FAIL, self.clock(), "PEER_UNAVAILABLE",
            )
        except (PeerConfigurationError, OSError, ValueError):
            return self._peer_observation(
                identity, ObservationState.FAIL, self.clock(), "PEER_PREFLIGHT_FAILED",
            )
        return self._peer_observation(identity, ObservationState.PASS, self.clock(), None)

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

    @staticmethod
    def liveness() -> dict[str, Any]:
        """Return the deliberately minimal public process-liveness projection."""
        return {
            "api_version": API_VERSION,
            "product": "forge",
            "liveness": {"state": "ALIVE", "alive": True},
            "read_only": True,
        }

    def installed_health(self, capability_scope: tuple[str, ...] = INSTALLED_HEALTH_CAPABILITIES) -> dict[str, Any]:
        """Compose installed observations with the canonical deterministic evaluator."""
        if (
            not isinstance(capability_scope, tuple)
            or not capability_scope
            or len(capability_scope) != len(set(capability_scope))
            or not set(capability_scope).issubset(INSTALLED_HEALTH_CAPABILITIES)
        ):
            raise OperationsProjectionError(
                "HEALTH_SCOPE_INVALID", "Health capability scope is invalid", status=400,
            )
        with self._runtime_snapshot_details() as (_connection, metadata, peer):
            snapshot_observed_at = self.clock()
            if snapshot_observed_at.tzinfo is None or snapshot_observed_at.utcoffset() is None:
                raise OperationsProjectionError(
                    "HEALTH_CLOCK_INVALID", "Health evaluation clock is invalid", status=503,
                )
            runtime_id = metadata.get("runtime_id", "")
            identity = HealthIdentity(
                canonical_version(),
                runtime_id,
                metadata.get("installation_id") or runtime_id,
            )
            observations = [
                HealthObservation(
                    identity, "forge_server", "process", CheckPurpose.LIVENESS, (),
                    ObservationState.PASS, snapshot_observed_at,
                ),
            ]
            active = metadata.get("status") == "active"
            observations.append(HealthObservation(
                identity, "platform_database", "storage", CheckPurpose.READINESS,
                INSTALLED_HEALTH_CAPABILITIES,
                ObservationState.PASS if active else ObservationState.FAIL,
                snapshot_observed_at,
                reason_code=None if active else "RUNTIME_NOT_ACTIVE",
            ))
            peer_configuration = peer.configuration if peer.status == "CONFIGURED" else None
        if "dispatch" in capability_scope:
            observations.append(
                self.peer_observer(
                    identity,
                    peer_configuration,
                    snapshot_observed_at,
                    self.query_timeout_seconds,
                )
                if peer_configuration is not None
                else self._peer_observation(
                    identity, ObservationState.FAIL, snapshot_observed_at, "PEER_NOT_CONFIGURED",
                )
            )
        evaluated_at = self.clock()
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise OperationsProjectionError(
                "HEALTH_CLOCK_INVALID", "Health evaluation clock is invalid", status=503,
            )
        result = evaluate_health(
            identity,
            installed_health_registry(),
            observations,
            capability_scope=capability_scope,
            evaluated_at=evaluated_at,
        ).to_dict()
        return {"api_version": API_VERSION, "read_only": True, **result}

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
        return _redact({
            "api_version": API_VERSION,
            "availability": "AVAILABLE",
            "freshness": _freshness(observed_at, now=self.clock(), stale_after=self.stale_after),
            "source_observed_at": observed_at,
            "read_only": True,
            "mission": projection,
        })

    @contextmanager
    def _runtime_snapshot(self) -> Iterator[tuple[sqlite3.Connection, dict[str, str]]]:
        """Validate the installed identity, then hold one consistent read transaction."""
        with self._runtime_snapshot_details() as (connection, metadata, _peer):
            yield connection, metadata

    @contextmanager
    def _runtime_snapshot_details(self) -> Iterator[tuple[sqlite3.Connection, dict[str, str], Any]]:
        """Hold one identity-validated snapshot, including its peer-registry readback."""
        database = self.root / "forge.db"
        connection = None
        try:
            deadline = self.query_clock() + self.query_timeout_seconds
            connection = sqlite3.connect(
                database.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=self.query_timeout_seconds,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            connection.execute(f"PRAGMA busy_timeout = {int(self.query_timeout_seconds * 1000)}")
            connection.set_progress_handler(lambda: int(self.query_clock() >= deadline), 1)
            connection.execute("BEGIN")
            if connection.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                raise PeerConfigurationError("Forge runtime database integrity check failed")
            metadata = dict(connection.execute("SELECT key, value FROM runtime_metadata"))
            try:
                schema = int(metadata["schema_version"])
                migration = int(metadata["migration_version"])
                user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            except (KeyError, TypeError, ValueError):
                raise PeerConfigurationError("Forge runtime storage schema is unreadable") from None
            if schema > RUNTIME_SCHEMA_VERSION:
                raise PeerConfigurationError("Forge runtime storage schema is newer than this Forge version")
            marker_path = self.root / "instance" / "runtime-instance.json"
            marker = marker_path.read_text(encoding="utf-8").strip()
            readback = read_peer_configuration_snapshot(connection, metadata.get("runtime_id", ""), schema)
            if (
                metadata.get("runtime_id") != readback.runtime_id
                or marker != readback.runtime_id
                or schema != migration
                or schema != user_version
                or schema != readback.storage_schema
            ):
                raise PeerConfigurationError("Forge runtime identity or storage schema changed during readback")
            yield connection, metadata, readback
            if marker_path.read_text(encoding="utf-8").strip() != readback.runtime_id:
                raise PeerConfigurationError("Forge runtime identity changed during readback")
        finally:
            if connection is not None:
                connection.set_progress_handler(None, 0)
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
        parsed_target = urlsplit(target)
        path = parsed_target.path
        if method == "GET" and path == _LIVENESS_PATH:
            return APIResponse(200, self.service.liveness(), headers)
        if not self._authenticated(authorization):
            return APIResponse(401, self._error("AUTHENTICATION_REQUIRED", "Authentication is required"), headers)
        if method != "GET":
            return APIResponse(405, self._error("METHOD_NOT_ALLOWED", "Only read-only GET is supported"), {
                **headers, "Allow": "GET",
            })
        try:
            if path == "/v1/status":
                body = self.service.installed_status()
                status = 503 if body.get("availability") == "UNAVAILABLE" else 200
                return APIResponse(status, body, headers)
            if path == _READINESS_PATH:
                query = parsed_target.query
                requested = tuple(
                    unquote(item.split("=", 1)[1]) for item in query.split("&")
                    if item.startswith("capability=") and len(item.split("=", 1)) == 2
                ) if query else INSTALLED_HEALTH_CAPABILITIES
                if query and any(
                    not item.startswith("capability=") or len(item.split("=", 1)) != 2
                    for item in query.split("&")
                ):
                    raise OperationsProjectionError(
                        "HEALTH_SCOPE_INVALID", "Health capability scope is invalid", status=400,
                    )
                body = self.service.installed_health(requested)
                ready = all(item["ready"] for item in body["capabilities"] if item["capability_id"] in requested)
                return APIResponse(200 if ready else 503, body, headers)
            match = _MISSION_PATH.fullmatch(path)
            if match:
                return APIResponse(200, self.service.mission_detail(unquote(match.group(1))), headers)
            return APIResponse(404, self._error("ROUTE_NOT_FOUND", "Route was not found"), headers)
        except OperationsProjectionError as error:
            return APIResponse(error.status, self._error(error.code, str(error)), headers)
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
