"""Authenticated, read-only HTTP projections for an installed Forge runtime.

The adapter deliberately exposes only already-authoritative installed status and
Mission projections.  It never opens the runtime through ``RuntimeBootstrap``
and therefore cannot initialize, migrate, dispatch, or otherwise mutate Forge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

from .__main__ import _status
from .mission_cli import _status_projection as mission_status_projection
from .runtime.data_root import DataRootResolver


API_VERSION = "1"
DEFAULT_STALE_AFTER = timedelta(minutes=5)
_MISSION_PATH = re.compile(r"^/v1/missions/([^/]+)$")
_SENSITIVE_KEY = re.compile(r"(?:authorization|bearer|credential|password|secret|token)", re.IGNORECASE)
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_KEYCHAIN_REFERENCE = re.compile(r"(?i)\bkeychain://[^\s,;]+")


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
    return "STALE" if now - observed > stale_after else "CURRENT"


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
        return _KEYCHAIN_REFERENCE.sub("[REDACTED_CREDENTIAL_REFERENCE]", _BEARER_VALUE.sub("Bearer [REDACTED]", value))
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


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
        availability = (
            "AVAILABLE"
            if projection.get("initialized") is True and projection.get("runtime_status") != "unavailable"
            else "UNAVAILABLE"
        )
        observed_at = self._runtime_observed_at() if projection.get("initialized") else None
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
        database = self.root / "forge.db"
        connection = None
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            connection.execute("PRAGMA query_only = ON")
            projection, state = mission_status_projection(connection, mission_id)
        except ValueError as error:
            if str(error) == "unknown Mission":
                raise OperationsProjectionError("MISSION_MISSING", "Mission was not found", status=404) from None
            raise OperationsProjectionError("MISSION_UNAVAILABLE", "Mission projection is unavailable", status=503) from error
        except (OSError, sqlite3.Error):
            raise OperationsProjectionError("MISSION_UNAVAILABLE", "Mission projection is unavailable", status=503) from None
        finally:
            if connection is not None:
                connection.close()
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
            "criteria": list(state.mission.get("acceptance_criteria", ())),
            "actions": [dict(item) for item in state.actions],
            "evidence_lineage": {
                "execution_evidence": state.execution_evidence,
                "execution_attempts": [dict(item) for item in state.execution_history],
                "repository_truth": state.repository_truth,
                "criterion_assessment": state.completion,
                "criterion_assessment_history": [dict(item) for item in state.completion_history],
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

    def _runtime_observed_at(self) -> str | None:
        database = self.root / "forge.db"
        if not database.is_file():
            return None
        connection = None
        try:
            connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            row = connection.execute(
                "SELECT value FROM runtime_metadata WHERE key = 'last_access_at'"
            ).fetchone()
        except sqlite3.Error:
            return None
        finally:
            if connection is not None:
                connection.close()
        return row[0] if row and isinstance(row[0], str) else None

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
