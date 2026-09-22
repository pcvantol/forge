"""Production foreground Forge Server Runtime V1 composition.

The Server is a transport/supervision composition over existing Forge application
services.  It never creates a Runtime Instance implicitly and never becomes an
Execution Host or a second Mission engine.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import signal
import sqlite3
from threading import BoundedSemaphore, Event, Lock, Thread
import tempfile
import time
from typing import Any, Iterator, Mapping
from urllib.parse import unquote, urlsplit

try:
    import fcntl
except ImportError:  # pragma: no cover - product fails closed where locking is unavailable
    fcntl = None  # type: ignore[assignment]

from ._version import canonical_version
from .execution_host_configuration import (
    EngineeringPlatformPeerConfigurationService,
    PeerConfigurationError,
    read_peer_configuration,
)
from .mission_cli import (
    _require_ep_mission_capabilities,
    _verified_initial_truth,
    admit as mission_admit,
    approve as mission_approve,
    inspect as mission_inspect,
    status as mission_status,
)
from .models.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from .operations_read_api import APIResponse, InstalledOperationsReadService, OperationsReadAPI, read_bearer_credential
from .planner import (
    CodexCliSessionReadinessChecker,
    CodexCliSessionReadinessState,
)
from .provider_context import ProviderExecutionContextError, ProviderExecutionContextService
from .provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
    CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderInvocationPolicy,
    ProviderAuthenticationMode,
)
from .runtime import RUNTIME_SCHEMA_VERSION
from .runtime.data_root import DataRootResolver
from .runtime.dynamic_mission import DynamicMissionRunResult, InstalledDynamicMissionRuntime
from .runtime.service import ForgeRuntimeService, RuntimeServiceBusy, RuntimeServiceLock


SERVER_API_VERSION = "1"
SERVER_RUNTIME_CONTRACT_VERSION = "1.0"
DEFAULT_PROVIDER_ID = "codex-chatgpt-session"
_MAX_BODY = 1_048_576


class ForgeServerRuntimeError(RuntimeError):
    """The selected installed Forge Server instance cannot run safely."""


@dataclass(frozen=True)
class ExistingInstance:
    data_root: str
    instance_id: str
    storage_schema: int
    product_version: str


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def existing_instance(data_root: str | Path) -> ExistingInstance:
    """Verify one already-initialized current-schema instance without mutation."""
    root = DataRootResolver(cli_data_root=data_root).resolve()
    marker = root / "instance" / "runtime-instance.json"
    database = root / "forge.db"
    if not marker.is_file() or not database.is_file():
        raise ForgeServerRuntimeError("Forge Server requires an existing initialized instance")
    try:
        instance_id = marker.read_text(encoding="utf-8").strip()
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only = ON")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ForgeServerRuntimeError("Forge Server runtime database integrity check failed")
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            metadata = dict(connection.execute("SELECT key, value FROM runtime_metadata"))
        finally:
            connection.close()
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        raise ForgeServerRuntimeError("Forge Server instance readback failed") from error
    if (
        not instance_id
        or metadata.get("runtime_id") != instance_id
        or user_version != RUNTIME_SCHEMA_VERSION
        or metadata.get("schema_version") != str(RUNTIME_SCHEMA_VERSION)
        or metadata.get("migration_version") != str(RUNTIME_SCHEMA_VERSION)
    ):
        raise ForgeServerRuntimeError("Forge Server instance identity or schema is not current")
    return ExistingInstance(str(root), instance_id, user_version, canonical_version())


class ServerInstanceLease:
    """One Server process per data root; never a machine-global singleton."""

    def __init__(self, data_root: str | Path) -> None:
        self.root = DataRootResolver(cli_data_root=data_root).resolve()
        self.path = self.root / "locks" / "forge-server-runtime.lock"

    @contextmanager
    def acquire(self) -> Iterator[None]:
        if fcntl is None:
            raise ForgeServerRuntimeError("Forge Server process locking is unavailable")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ForgeServerRuntimeError("another Forge Server owns this instance") from error
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ServerRuntimeState:
    """Thread-safe, secret-free lifecycle/readiness projection."""

    def __init__(self, instance: ExistingInstance, provider_id: str) -> None:
        self._lock = Lock()
        self._document: dict[str, Any] = {
            "contract_version": SERVER_RUNTIME_CONTRACT_VERSION,
            "instance_id": instance.instance_id,
            "data_root": instance.data_root,
            "product_version": instance.product_version,
            "storage_schema": instance.storage_schema,
            "provider_id": provider_id,
            "process_id": os.getpid(),
            "started_at": _now(),
            "listener": None,
            "lifecycle": "STARTING",
            "scheduler": {"state": "STARTING", "last_tick_at": None, "last_error": None},
        }

    def update(self, **values: Any) -> None:
        with self._lock:
            self._document.update(values)

    def scheduler(self, state: str, *, error: str | None = None) -> None:
        with self._lock:
            self._document["scheduler"] = {
                "state": state,
                "last_tick_at": _now(),
                "last_error": error,
            }

    def document(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._document))


class _ResumeOnlyLoop:
    """Adapt the installed composition to the service's persisted-resume contract."""

    def __init__(self, runtime: InstalledDynamicMissionRuntime) -> None:
        self.runtime = runtime

    def run(self):
        # A Server does not invent/select an approved Mission.  A Mission enters
        # execution only through its explicit governed controller start.
        return None

    def resume(self, mission_id: str):
        return self.runtime.resume(mission_id)


def _read_external_provider_policy(data_root: str | Path, provider_id: str) -> PlanningProviderInvocationPolicy:
    """Read the configured non-secret provider policy without opening/migrating Forge."""
    root = DataRootResolver(cli_data_root=data_root).resolve()
    context = ProviderExecutionContextService(root).read(provider_id)
    connection = sqlite3.connect((root / "forge.db").resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM planning_provider_external_session_config WHERE provider_id=?", (provider_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None or not row["enabled"]:
        raise ForgeServerRuntimeError("Forge Server planning provider is not configured")
    if (
        row["authentication_mode"] != ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION.value
        or row["provider_type"] != CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE
        or row["external_session_type"] != CODEX_CLI_CHATGPT_SESSION_TYPE
        or context.provider_type != row["provider_type"]
        or context.executable_path != row["executable_path"]
        or context.profile != row["profile"]
    ):
        raise ForgeServerRuntimeError("Forge Server provider policy and instance context differ")
    return PlanningProviderInvocationPolicy(
        provider_id=provider_id,
        model=row["model"],
        secret_reference=None,
        timeout_seconds=row["timeout_seconds"],
        input_token_bound=row["input_token_bound"],
        context_token_bound=row["context_token_bound"],
        output_token_bound=row["output_token_bound"],
        version=row["version"],
        authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
        provider_type=row["provider_type"],
        external_session_type=row["external_session_type"],
        executable_path=row["executable_path"],
        adapter_version=row["adapter_version"],
        profile=row["profile"],
        provider_home=context.provider_home,
        provider_config_home=context.provider_config_home,
        instance_id=context.instance_id,
        provider_context_digest=context.configuration_digest,
    )


@contextmanager
def _document_file(document: Mapping[str, Any]) -> Iterator[str]:
    """Bridge JSON transport to the existing file-based CLI application adapter."""
    descriptor, path = tempfile.mkstemp(prefix="forge-server-request-", suffix=".json")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True, separators=(",", ":"))
        os.chmod(path, 0o600)
        yield path
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _result_document(result: DynamicMissionRunResult) -> dict[str, Any]:
    return asdict(result)


class ForgeServerApplicationServices:
    """Thin HTTP-facing composition over existing Forge application services."""

    def __init__(self, data_root: str | Path, state: ServerRuntimeState,
                 *, provider_id: str = DEFAULT_PROVIDER_ID) -> None:
        self.root = DataRootResolver(cli_data_root=data_root).resolve()
        self.state = state
        self.provider_id = provider_id

    def instance(self) -> dict[str, Any]:
        current = existing_instance(self.root)
        provider = self.provider_context()
        try:
            peer = read_peer_configuration(self.root)
            peer_projection = {
                "status": peer.status,
                "binding_id": None if peer.configuration is None else peer.configuration.binding_id,
                "configuration_revision": (
                    None if peer.configuration is None else peer.configuration.configuration_revision
                ),
            }
        except PeerConfigurationError as error:
            peer_projection = {"status": "ERROR", "error": str(error)}
        return {
            "api_version": SERVER_API_VERSION,
            "contract_version": SERVER_RUNTIME_CONTRACT_VERSION,
            "instance": asdict(current),
            "listener": self.state.document().get("listener"),
            "provider_context": provider,
            "execution_host_peer": peer_projection,
            "read_only": True,
        }

    def provider_context(self) -> dict[str, Any]:
        try:
            context = ProviderExecutionContextService(self.root).read(self.provider_id)
            return {"state": "BOUND", **context.to_safe_dict()}
        except ProviderExecutionContextError as error:
            return {"state": "NOT_READY", "provider_id": self.provider_id, "error": str(error)}

    def provider_readiness(self) -> dict[str, Any]:
        try:
            policy = _read_external_provider_policy(self.root, self.provider_id)
            readiness = CodexCliSessionReadinessChecker().check(policy)
            return {
                "state": readiness.state.value,
                "ready": readiness.state is CodexCliSessionReadinessState.READY,
                "provider_id": self.provider_id,
                "executable_path": readiness.executable_path,
                "version": readiness.version,
                "model": readiness.model,
                "profile": readiness.profile,
                "instance_id": policy.instance_id,
                "provider_context_digest": policy.provider_context_digest,
            }
        except (ForgeServerRuntimeError, ProviderExecutionContextError, sqlite3.Error) as error:
            return {"state": "NOT_READY", "ready": False, "provider_id": self.provider_id, "error": str(error)}

    def readiness(self) -> dict[str, Any]:
        provider = self.provider_readiness()
        try:
            peer = read_peer_configuration(self.root)
            peer_ready = peer.configuration is not None and peer.status == "CURRENT"
            peer_state = peer.status
        except PeerConfigurationError as error:
            peer_ready, peer_state = False, "ERROR:" + str(error)
        scheduler = self.state.document()["scheduler"]
        ready = bool(provider.get("ready")) and peer_ready and scheduler.get("state") in {"READY", "IDLE"}
        return {
            "api_version": SERVER_API_VERSION,
            "ready": ready,
            "provider": provider,
            "execution_host_peer": {"ready": peer_ready, "state": peer_state},
            "scheduler": scheduler,
            "instance_id": existing_instance(self.root).instance_id,
        }

    def execution_host_preflight(self) -> dict[str, Any]:
        return EngineeringPlatformPeerConfigurationService(self.root).preflight()

    def configure_execution_host(self, document: Mapping[str, Any]) -> dict[str, Any]:
        service = EngineeringPlatformPeerConfigurationService(self.root)
        required = {
            "binding_id", "endpoint", "expected_instance_id", "consumer_id", "host_id",
            "project_id", "repository_id", "repository_identity", "credential_reference",
            "operator_id", "timeout_seconds", "allow_loopback_http", "replace",
            "expected_revision", "expected_digest",
        }
        if set(document) != required:
            raise ValueError("execution-host configuration request shape is invalid")
        replace = document["replace"]
        expected_revision, expected_digest = document["expected_revision"], document["expected_digest"]
        if bool(replace) != (expected_revision is not None and expected_digest is not None):
            raise ValueError("guarded replacement fields are inconsistent")
        with RuntimeServiceLock(self.root / "forge.db").acquire():
            configured = service.configure(
                binding_id=document["binding_id"], endpoint=document["endpoint"],
                expected_instance_id=document["expected_instance_id"], consumer_id=document["consumer_id"],
                host_id=document["host_id"], project_id=document["project_id"],
                repository_id=document["repository_id"], repository_identity=document["repository_identity"],
                credential_reference=document["credential_reference"], operator_id=document["operator_id"],
                timeout_seconds=document["timeout_seconds"], allow_loopback_http=bool(document["allow_loopback_http"]),
                replace=bool(replace), expected_revision=expected_revision, expected_digest=expected_digest,
            )
        return configured.to_safe_dict()

    def configure_provider_context(self, document: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "provider_id", "provider_type", "executable_path", "provider_home",
            "provider_config_home", "profile", "expected_digest",
        }
        if set(document) != required:
            raise ValueError("provider-context configuration request shape is invalid")
        with RuntimeServiceLock(self.root / "forge.db").acquire():
            context = ProviderExecutionContextService(self.root).configure(
                provider_id=document["provider_id"], provider_type=document["provider_type"],
                executable_path=document["executable_path"], provider_home=document["provider_home"],
                provider_config_home=document["provider_config_home"], profile=document["profile"],
                expected_digest=document["expected_digest"],
            )
        return context.to_safe_dict()

    def mission_document(self, operation: str, document: Mapping[str, Any]) -> dict[str, Any]:
        with _document_file(document) as path:
            if operation == "inspect":
                return mission_inspect(path)
            if operation == "approve-business":
                return mission_approve(str(self.root), path, "business")
            if operation == "approve-architecture":
                return mission_approve(str(self.root), path, "architecture")
            if operation == "admit":
                return mission_admit(str(self.root), path)
        raise ValueError("unsupported Mission governance operation")

    def mission_start(self, mission_id: str, truth: Mapping[str, Any]) -> dict[str, Any]:
        required = {"id", "repository_id", "repository_revision", "observed_at", "evidence", "schema_version"}
        if set(truth) != required or not isinstance(truth["evidence"], list):
            raise ValueError("Repository Truth request shape is invalid")
        snapshot = RepositoryTruthSnapshot(
            truth["id"], truth["repository_id"], truth["repository_revision"], truth["observed_at"],
            tuple(RepositoryTruthEvidence(**item) for item in truth["evidence"]),
            schema_version=truth["schema_version"],
        )
        with InstalledDynamicMissionRuntime.open(str(self.root), provider_id=self.provider_id) as runtime:
            if _require_ep_mission_capabilities(runtime, mission_id) is not True:
                raise ValueError("EP Mission capabilities are not active")
            verified = _verified_initial_truth(runtime, mission_id, snapshot)
            return _result_document(runtime.start(mission_id, verified))

    def mission_reopen(self, mission_id: str) -> dict[str, Any]:
        with InstalledDynamicMissionRuntime.open(str(self.root), provider_id=self.provider_id) as runtime:
            _require_ep_mission_capabilities(runtime, mission_id, allow_pending_readback=True)
            return _result_document(runtime.resume(mission_id))

    def mission_status(self, mission_id: str) -> dict[str, Any]:
        return mission_status(str(self.root), mission_id)


class ForgeServerAPI:
    """Authenticated versioned HTTP transport; application semantics stay elsewhere."""

    def __init__(self, services: ForgeServerApplicationServices, bearer_credential: str) -> None:
        if not bearer_credential:
            raise ValueError("Forge Server bearer credential is required")
        self.services = services
        self._credential = bearer_credential
        self._read_api = OperationsReadAPI(InstalledOperationsReadService(services.root), bearer_credential)

    @staticmethod
    def _headers() -> dict[str, str]:
        return {
            "Cache-Control": "no-store",
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        }

    def _authenticated(self, authorization: str | None) -> bool:
        return (
            isinstance(authorization, str)
            and authorization.startswith("Bearer ")
            and bool(authorization[7:])
            and secrets.compare_digest(authorization[7:], self._credential)
        )

    def handle(self, method: str, target: str, authorization: str | None,
               body: Mapping[str, Any] | None = None) -> APIResponse:
        headers = self._headers()
        if not self._authenticated(authorization):
            return APIResponse(401, {"api_version": SERVER_API_VERSION, "error": {
                "code": "AUTHENTICATION_REQUIRED", "message": "Authentication is required",
            }}, headers)
        path = urlsplit(target).path
        if method == "GET" and (
            path in {"/v1/status", "/v1/health"} or path.startswith("/v1/missions/")
            and not path.endswith(("/controller/start", "/controller/reopen"))
        ):
            return self._read_api.handle(method, target, authorization)
        try:
            if method == "GET" and path == "/v1/instance":
                return APIResponse(200, self.services.instance(), headers)
            if method == "GET" and path == "/v1/readiness":
                value = self.services.readiness()
                return APIResponse(200 if value["ready"] else 503, value, headers)
            if method == "GET" and path == "/v1/version":
                instance = existing_instance(self.services.root)
                return APIResponse(200, {
                    "api_version": SERVER_API_VERSION,
                    "product": "forge-autonomy",
                    "product_version": instance.product_version,
                    "storage_schema": instance.storage_schema,
                    "instance_id": instance.instance_id,
                }, headers)
            if method == "GET" and path == "/v1/provider-context":
                return APIResponse(200, self.services.provider_context(), headers)
            if method == "GET" and path == "/v1/execution-host/preflight":
                return APIResponse(200, self.services.execution_host_preflight(), headers)
            if method == "POST" and path == "/v1/provider-context":
                return APIResponse(200, self.services.configure_provider_context(body or {}), headers)
            if method == "POST" and path == "/v1/execution-host/configure":
                return APIResponse(200, self.services.configure_execution_host(body or {}), headers)
            if method == "POST" and path in {
                "/v1/missions/inspect", "/v1/missions/approve-business",
                "/v1/missions/approve-architecture", "/v1/missions/admit",
            }:
                return APIResponse(200, self.services.mission_document(path.rsplit("/", 1)[1], body or {}), headers)
            if method == "POST" and path.startswith("/v1/missions/"):
                parts = path.split("/")
                if len(parts) == 6 and parts[4] == "controller":
                    mission_id = unquote(parts[3])
                    if parts[5] == "start":
                        truth = (body or {}).get("repository_truth")
                        if not isinstance(truth, Mapping):
                            raise ValueError("controller start requires Repository Truth")
                        return APIResponse(200, self.services.mission_start(mission_id, truth), headers)
                    if parts[5] == "reopen":
                        return APIResponse(200, self.services.mission_reopen(mission_id), headers)
            return APIResponse(404, {"api_version": SERVER_API_VERSION, "error": {
                "code": "ROUTE_NOT_FOUND", "message": "Route was not found",
            }}, headers)
        except RuntimeServiceBusy as error:
            return APIResponse(409, {"api_version": SERVER_API_VERSION, "error": {
                "code": "RUNTIME_BUSY", "message": str(error),
            }}, headers)
        except (ForgeServerRuntimeError, ProviderExecutionContextError, PeerConfigurationError,
                OSError, ValueError, KeyError, sqlite3.Error, RuntimeError, PermissionError) as error:
            return APIResponse(409, {"api_version": SERVER_API_VERSION, "error": {
                "code": type(error).__name__.upper(), "message": str(error),
            }}, headers)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._slots = BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(10.0)
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


def make_server(host: str, port: int, api: ForgeServerAPI) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise ValueError("Forge Server V1 listener is restricted to explicit IPv4 loopback")
    if isinstance(port, bool) or port < 0 or port > 65535:
        raise ValueError("Forge Server port is invalid")

    class Handler(BaseHTTPRequestHandler):
        server_version = "ForgeServerRuntime/1"
        sys_version = ""

        def _body(self) -> Mapping[str, Any] | None:
            if self.command == "GET":
                return None
            length_text = self.headers.get("Content-Length", "0")
            try:
                length = int(length_text)
            except ValueError as error:
                raise ValueError("request Content-Length is invalid") from error
            if length < 0 or length > _MAX_BODY:
                raise ValueError("request body exceeds Forge Server limit")
            raw = self.rfile.read(length)
            if not raw:
                return {}
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("request body must be a JSON object")
            return value

        def _dispatch(self) -> None:
            try:
                body = self._body()
                response = api.handle(self.command, self.path, self.headers.get("Authorization"), body)
            except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
                response = APIResponse(400, {"api_version": SERVER_API_VERSION, "error": {
                    "code": "REQUEST_INVALID", "message": str(error),
                }}, ForgeServerAPI._headers())
            payload = json.dumps(response.body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(response.status)
            for name, value in response.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        do_GET = _dispatch  # noqa: N815
        do_POST = _dispatch  # noqa: N815
        do_PUT = _dispatch  # noqa: N815
        do_PATCH = _dispatch  # noqa: N815
        do_DELETE = _dispatch  # noqa: N815
        do_HEAD = _dispatch  # noqa: N815
        do_OPTIONS = _dispatch  # noqa: N815

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return _Server((host, port), Handler)


class ForgeServerRuntime:
    """One foreground Server process for exactly one existing Forge instance."""

    def __init__(self, *, data_root: str | Path, credential_file: str | Path,
                 host: str, port: int, provider_id: str = DEFAULT_PROVIDER_ID,
                 tick_interval: float = 0.25) -> None:
        if not str(data_root):
            raise ValueError("Forge Server requires an explicit data root")
        if tick_interval <= 0:
            raise ValueError("Forge Server tick interval must be positive")
        self.instance = existing_instance(data_root)
        self.root = Path(self.instance.data_root)
        self.provider_id = provider_id
        self.tick_interval = tick_interval
        self._credential = read_bearer_credential(credential_file)
        self.state = ServerRuntimeState(self.instance, provider_id)
        self.services = ForgeServerApplicationServices(self.root, self.state, provider_id=provider_id)
        self.api = ForgeServerAPI(self.services, self._credential)
        self.server = make_server(host, port, self.api)
        address, actual_port = self.server.server_address
        self.state.update(listener={"host": address, "port": actual_port}, lifecycle="STARTING")
        self._stop = Event()
        self._lease = ServerInstanceLease(self.root)

    def stop(self) -> None:
        self._stop.set()

    def _tick(self) -> None:
        # Server mode is deliberately stricter than legacy interactive CLI use:
        # the scheduler will not inherit an ambient user provider context.
        provider = self.services.provider_readiness()
        if not provider.get("ready"):
            raise ForgeServerRuntimeError("instance-owned planning provider is not ready")
        with InstalledDynamicMissionRuntime.open(str(self.root), provider_id=self.provider_id) as runtime:
            service = ForgeRuntimeService(_ResumeOnlyLoop(runtime), runtime.states, runtime_database=runtime.database)
            tick = service.tick()
            self.state.scheduler("READY" if tick.progressed else "IDLE")

    def serve_forever(self) -> None:
        """Run in the foreground and terminate cleanly on SIGINT/SIGTERM."""
        with self._lease.acquire():
            thread = Thread(target=self.server.serve_forever, name="forge-server-http", daemon=True)
            thread.start()
            previous_int = signal.getsignal(signal.SIGINT)
            previous_term = signal.getsignal(signal.SIGTERM)

            def request_stop(*_: object) -> None:
                self._stop.set()

            signal.signal(signal.SIGINT, request_stop)
            signal.signal(signal.SIGTERM, request_stop)
            self.state.update(lifecycle="RUNNING")
            try:
                while not self._stop.is_set():
                    try:
                        self._tick()
                    except RuntimeServiceBusy:
                        self.state.scheduler("BUSY")
                    except Exception as error:
                        self.state.scheduler("NOT_READY", error=type(error).__name__)
                    self._stop.wait(self.tick_interval)
            finally:
                self.state.update(lifecycle="STOPPING")
                self.server.shutdown()
                self.server.server_close()
                thread.join(timeout=5)
                self.state.update(lifecycle="STOPPED")
                signal.signal(signal.SIGINT, previous_int)
                signal.signal(signal.SIGTERM, previous_term)
