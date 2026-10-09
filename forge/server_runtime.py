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
from urllib.parse import unquote

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
from .mission_lifecycle_cli import archive_no_dispatch as mission_archive_no_dispatch
from .repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from .operations_read_api import (
    APIResponse, InstalledOperationsReadService, OperationsReadAPI, origin_form_path, raw_request_target,
    read_bearer_credential,
)
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
from .secure_store import SecretReference
from .runtime.data_root import DataRootResolver
from .root_identity import RootIdentity
from .runtime.dynamic_mission import DynamicMissionRunResult, InstalledDynamicMissionRuntime
from .state import MissionExecutionStatus
from .runtime.service import ForgeRuntimeService, RuntimeServiceBusy, RuntimeServiceLock
from .workspace_read_grant import WorkspaceReadGrant
from .workspace_review_grant import ReviewPrincipal, WorkspaceReviewGrant
from .workspace_worklist_grant import WorkspaceWorklistGrant
from .workspace_worklist_control_grant import WorkspaceWorklistControlGrant
from .advisory_grant import AdvisoryGrant
from .advisory_service import AdvisoryService
from .mission_concept_service import MissionConceptService
from .advisory_candidate_grant import AdvisoryCandidateGrant
from .advisory_candidate_service import AdvisoryCandidateService
from .candidate_decision_grant import CandidateDecisionGrant
from .candidate_decision_service import CandidateDecisionService
from .worklist_control import WorklistControlService
from .approved_worklist import projection as worklist_projection
from .workspace_review_inbox import (
    OPERATION_VERSION as REVIEW_OPERATION_CONTRACT,
    canonical_decision_request, scoped_item, scoped_list,
)


SERVER_API_VERSION = "1"
SERVER_RUNTIME_CONTRACT_VERSION = "1.0"
SERVER_ROUTE_INVENTORY = (
    ('GET', '/v1/candidate-decisions/capability'),
    ('GET', '/v1/candidate-decisions/{candidate_id}'),
    ('POST', '/v1/candidate-decisions/{candidate_id}/business'),
    ('POST', '/v1/candidate-decisions/{candidate_id}/architecture'),
    ('GET', '/v1/candidate-decisions/{candidate_id}/operations/{operation_id}'),

    ("GET", "/v1/project-dag/capability"),
    ('GET', '/v1/advisory-candidates/capability'),
    ('GET', '/v1/advisory-candidates/{conversation_id}/source/{turn_id}'),
    ('POST', '/v1/advisory-candidates/{conversation_id}/proposals'),
    ('GET', '/v1/advisory-candidates/{conversation_id}/proposals/{proposal_id}'),
    ('POST', '/v1/advisory-candidates/{conversation_id}/proposals/{proposal_id}/registrations'),
    ('GET', '/v1/advisory-candidates/{conversation_id}/proposals/{proposal_id}/registrations/{operation_id}'),
    ('GET', '/v1/advisory/capability'),
    ('POST', '/v1/advisory/{conversation_id}/turns'),
    ('GET', '/v1/advisory/{conversation_id}'),
    ('GET', '/v1/advisory/{conversation_id}/turns/{turn_id}'),
    ('POST', '/v1/advisory/{conversation_id}/turns/{turn_id}/cancel'),
    ("GET", "/v1/status"),
    ("GET", "/v1/health"),
    ("GET", "/v1/readiness"),
    ("GET", "/v1/readiness/standalone"),
    ("GET", "/v1/readiness/installation"),
    ("GET", "/v1/installation-peer"),
    ("GET", "/v1/installation-peer/preflight"),
    ("POST", "/v1/installation-peer/configure"),
    ("GET", "/v1/instance"),
    ("GET", "/v1/version"),
    ("GET", "/v1/provider-context"),
    ("GET", "/v1/projects"),
    ("GET", "/v1/projects/{project_id}/roadmap"),
    ("POST", "/v1/provider-context"),
    ("GET", "/v1/execution-host/preflight"),
    ("POST", "/v1/execution-host/configure"),
    ("POST", "/v1/execution-host/detach"),
    ("GET", "/v1/execution-host/detach/{operation_id}"),
    ("POST", "/v1/missions/inspect"),
    ("POST", "/v1/missions/approve-business"),
    ("POST", "/v1/missions/approve-architecture"),
    ("POST", "/v1/missions/admit"),
    ("GET", "/v1/missions/{mission_id}"),
    ("GET", "/v1/missions/{mission_id}/progression"),
    ("POST", "/v1/missions/{mission_id}/progression-policy"),
    ("POST", "/v1/missions/{mission_id}/progression-decisions"),
    ("POST", "/v1/missions/{mission_id}/controller/start"),
    ("POST", "/v1/missions/{mission_id}/controller/reopen"),
    ("POST", "/v1/missions/{mission_id}/lifecycle/archive-no-dispatch"),
    ("GET", "/v1/worksets"),
    ("GET", "/v1/worksets/{workset_id}"),
    ("GET", "/v1/workset-controls/{workset_id}"),
    ("POST", "/v1/workset-controls/{workset_id}/commands"),
    ("GET", "/v1/workset-controls/{workset_id}/commands/{operation_id}"),
    ("POST", "/v1/worksets/{workset_id}/propose"),
    ("POST", "/v1/worksets/{workset_id}/decide"),
    ("POST", "/v1/worksets/{workset_id}/arm"),
    ("POST", "/v1/worksets/{workset_id}/disarm"),
    ("POST", "/v1/worksets/{workset_id}/hold"),
    ("POST", "/v1/worksets/{workset_id}/unhold"),
    ("POST", "/v1/worksets/{workset_id}/revoke"),
    ("GET", "/v1/reviews"),
    ("GET", "/v1/reviews/missions/{mission_id}"),
    ("POST", "/v1/reviews/missions/{mission_id}/decisions"),
    ("GET", "/v1/reviews/missions/{mission_id}/decisions/{operation_id}"),
)
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


class _ServerLog:
    """Append secret-free Server lifecycle diagnostics below the instance data root."""

    def __init__(self, data_root: Path, root_identity: RootIdentity) -> None:
        self.root_identity = root_identity
        self.path = data_root / "logs" / "server-runtime.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)

    def write(self, event: str, **details: Any) -> None:
        if self.root_identity.drifted():
            return
        document = {"at": _now(), "event": event, **details}
        payload = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        descriptor = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


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
        # Resume an interrupted start through the same dynamic runtime before
        # selecting any separately approved and released next Candidate.
        for state in self.runtime.states.resumable():
            if state.status in {MissionExecutionStatus.CREATED,MissionExecutionStatus.READY_TO_CONTINUE}:
                return self.runtime.resume(state.mission_id)
        from .worklist_activation import activate_selected
        return activate_selected(self.runtime)

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

    def project_dag_capability(self) -> dict[str, Any]:
        """Describe only the installed project-DAG read subset, without probing peers."""
        current = existing_instance(self.root)
        return {
            "api_version": SERVER_API_VERSION,
            "contract_version": "forge-project-dag-http-capability/v1",
            "instance_id": current.instance_id,
            "server_product_version": canonical_version(),
            "capability_id": "PROJECT_DAG_READ_V1",
            "support": "SUPPORTED_NOT_READINESS",
            "authentication": "INSTANCE_BEARER",
            "project_scope": "CONFIGURED_PROJECT_ID_ONLY",
            "adapter": "HTTP",
            "operations": [
                {"method": "GET", "path": "/v1/projects"},
                {"method": "GET", "path": "/v1/projects/{project_id}/roadmap"},
            ],
            "project_mission_attribution": "UNAVAILABLE",
            "project_capability_graph": "UNAVAILABLE",
            "candidate_and_expected_views": "UNAVAILABLE",
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
            peer_state = peer.status
            peer_ready = False
            if peer.configuration is not None:
                preflight = self.execution_host_preflight()
                peer_ready = preflight.get("status") == "PASS"
                peer_state = "CURRENT" if peer_ready else "NOT_READY"
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

    def standalone_readiness(self) -> dict[str, Any]:
        """Opt-in service readiness for an instance with no selected EP peer.

        The legacy endpoint retains its peer-required meaning. A configured,
        stale or malformed peer never qualifies for this standalone projection.
        """
        strict = self.readiness()
        peer = strict["execution_host_peer"]
        standalone = peer["state"] == "NOT_CONFIGURED"
        scheduler_ready = strict["scheduler"].get("state") in {"READY", "IDLE"}
        service_ready = bool(strict["provider"].get("ready")) and scheduler_ready and standalone
        return {
            **strict,
            "contract_version": "forge-server-standalone-readiness/v1",
            "ready": service_ready,
            "service_ready": service_ready,
            "execution_ready": False,
            "mode": "STANDALONE" if standalone else "PEER_REQUIRED",
        }

    def installation_readiness(self) -> dict[str, Any]:
        """Separate component/service qualification; never project execution."""
        from .installation_pairing import InstallationPairingService
        provider = self.provider_readiness()
        scheduler = self.state.document()["scheduler"]
        service_ready = bool(provider.get("ready")) and scheduler.get("state") in {"READY", "IDLE"}
        try:
            pairing = InstallationPairingService(self.root).preflight()
            connected = pairing.get("status") == "CONNECTED"
        except (RuntimeError, OSError, ValueError, sqlite3.Error):
            pairing, connected = {"status": "NOT_READY"}, False
        return {
            "api_version": SERVER_API_VERSION,
            "contract_version": "forge-server-installation-readiness/v1",
            "ready": service_ready and connected, "service_ready": service_ready,
            "component_connected": connected, "project_authorized": False,
            "execution_ready": False, "provider": provider, "scheduler": scheduler,
            "installation_peer": pairing, "instance_id": existing_instance(self.root).instance_id,
        }

    def installation_peer(self) -> dict[str, Any]:
        from .installation_pairing import InstallationPairingService
        return InstallationPairingService(self.root).show()

    def installation_peer_preflight(self) -> dict[str, Any]:
        from .installation_pairing import InstallationPairingService
        return InstallationPairingService(self.root).preflight()

    def configure_installation_peer(self, document: Mapping[str, Any]) -> dict[str, Any]:
        from .installation_pairing import InstallationPairingService
        required = {"operation_id", "binding_id", "endpoint", "ep_instance_id", "consumer_id",
                    "credential_reference", "allow_loopback_http", "timeout_seconds"}
        if set(document) != required:
            raise ValueError("installation-peer request shape is invalid")
        return InstallationPairingService(self.root).configure(**document)

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
        configured = service.configure(
            binding_id=document["binding_id"], endpoint=document["endpoint"],
            expected_ep_instance_id=document["expected_instance_id"],
            ep_consumer_id=document["consumer_id"],
            execution_host_id=document["host_id"], ep_project_id=document["project_id"],
            ep_repository_id=document["repository_id"], repository_identity=document["repository_identity"],
            credential_reference=SecretReference.parse(document["credential_reference"]),
            operator_id=document["operator_id"], timeout_seconds=document["timeout_seconds"],
            allow_loopback_http=bool(document["allow_loopback_http"]),
            replace=bool(replace), expected_revision=expected_revision, expected_digest=expected_digest,
        )
        return configured.to_dict()

    def detach_execution_host(self, document: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "operation_id", "instance_id", "expected_binding_id",
            "expected_revision", "expected_digest", "operator_id",
        }
        if set(document) != required:
            raise ValueError("execution-host detach request shape is invalid")
        return EngineeringPlatformPeerConfigurationService(self.root).detach(**document)

    def detach_execution_host_status(self, operation_id: str) -> dict[str, Any]:
        return EngineeringPlatformPeerConfigurationService(self.root).detach_status(operation_id)

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

    def mission_progression_status(self, mission_id: str) -> dict[str, Any]:
        with InstalledDynamicMissionRuntime.open(str(self.root), provider_id=self.provider_id) as runtime:
            return runtime.progression_status(mission_id)

    def mission_progression_policy(self, mission_id: str, document: Mapping[str, Any]) -> dict[str, Any]:
        from forge.runtime.mission_controller import require_no_controller
        with InstalledDynamicMissionRuntime.open(str(self.root), provider_id=self.provider_id) as runtime:
            with require_no_controller(runtime.database.path), RuntimeServiceLock(runtime.database.path).acquire():
                return runtime.assign_progression_policy(mission_id, document)

    def mission_progression_decide(
        self, mission_id: str, document: Mapping[str, Any], *,
        authenticated_principal_reference: str,
    ) -> tuple[dict[str, Any], bool]:
        from forge.runtime.mission_controller import require_no_controller
        with InstalledDynamicMissionRuntime.open(str(self.root), provider_id=self.provider_id) as runtime:
            with require_no_controller(runtime.database.path):
                result, recording_status = runtime.decide_progression_with_recording_status(
                    mission_id, document,
                    authenticated_principal_reference=authenticated_principal_reference,
                )
                return _result_document(result), recording_status == "RECORDED"

    def workset_command(self, workset_id, operation, document):
        from .approved_worklist import ApprovedWorklistService,candidate_source
        from .lifecycle import RecommendationLifecycleStore
        source=candidate_source(self.root)
        with InstalledDynamicMissionRuntime.open(str(self.root),provider_id=self.provider_id) as runtime:
            with RecommendationLifecycleStore(source) as lifecycle:
                service=ApprovedWorklistService(runtime,lifecycle)
                if operation=='propose':
                    if document.get('workset_id')!=workset_id:raise ValueError('workset identity mismatch')
                    return service.propose(dict(document))
                if operation=='decide':
                    if set(document)!={'expected_revision','role','actor'}:raise ValueError('invalid workset decision')
                    return service.decide(workset_id,**document)
                if set(document)!={'expected_revision'}:raise ValueError('invalid workset control')
                return service.control(workset_id,operation=operation,**document)

    def workspace_review_list(self, principal: ReviewPrincipal) -> dict[str, Any]:
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
            return scoped_list(runtime, principal)

    def workspace_review_detail(self, principal: ReviewPrincipal, mission_id: str) -> dict[str, Any]:
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
            return scoped_item(runtime, principal, mission_id)

    def workspace_review_decide(
        self, principal: ReviewPrincipal, mission_id: str, document: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        canonical = canonical_decision_request(document)
        existing = self.workspace_review_operation(principal, mission_id, canonical["decision_id"])
        if existing is None:
            current = self.workspace_review_detail(principal, mission_id)
            if canonical["decision"] not in current["allowed_outcomes"]:
                raise PermissionError("review principal lacks the current required role")
        result, recorded = self.mission_progression_decide(
            mission_id, canonical,
            authenticated_principal_reference=principal.reference,
        )
        operation = self.workspace_review_operation(principal, mission_id,
                                                    canonical["decision_id"])
        if operation is None:
            raise RuntimeError("recorded review decision is unavailable")
        return {"contract_version": REVIEW_OPERATION_CONTRACT,
                "operation": operation["operation"], "current": operation["current"],
                "runtime_status": result.get("status"), "recorded": recorded}, recorded

    def workspace_review_operation(
        self, principal: ReviewPrincipal, mission_id: str, operation_id: str,
    ) -> dict[str, Any] | None:
        if mission_id not in principal.mission_ids:
            raise PermissionError("review grant does not include this Mission")
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
            from .governed_continuation import GovernedContinuationService
            operation = GovernedContinuationService(
                runtime.database, runtime.repository, runtime.states, runtime.clock,
            ).decision_operation_status(
                mission_id, operation_id,
                authenticated_principal_reference=principal.reference,
            )
            if operation is None:
                return None
            return {"contract_version": REVIEW_OPERATION_CONTRACT,
                    "operation": operation,
                    "current": scoped_item(runtime, principal, mission_id),
                    "read_only": True}

    def mission_archive_no_dispatch(
        self, mission_id: str, document: Mapping[str, Any], *,
        authenticated_principal_reference: str,
    ) -> dict[str, Any]:
        required = {"expected_instance_id", "expected_revision", "reason_code", "correlation_id"}
        if set(document) != required:
            raise ValueError("Mission archive request shape is invalid")
        return mission_archive_no_dispatch(
            str(self.root), mission_id,
            expected_instance_id=document["expected_instance_id"],
            expected_revision=document["expected_revision"],
            reason_code=document["reason_code"],
            correlation_id=document["correlation_id"],
            authenticated_principal_reference=authenticated_principal_reference,
        )


class ForgeServerAPI:
    """Authenticated versioned HTTP transport; application semantics stay elsewhere."""

    def __init__(self, services: ForgeServerApplicationServices, bearer_credential: str,
                 *, root_identity: RootIdentity | None = None,
                 read_grant: WorkspaceReadGrant | None = None,
                 review_grant: WorkspaceReviewGrant | None = None,
                 worklist_grant: WorkspaceWorklistGrant | None = None,
                 worklist_control_grant: WorkspaceWorklistControlGrant | None = None,
                 advisory_grant: AdvisoryGrant | None = None,
                 candidate_grant: AdvisoryCandidateGrant | None = None,
                 decision_grant: CandidateDecisionGrant | None = None) -> None:
        if not bearer_credential:
            raise ValueError("Forge Server bearer credential is required")
        self.services = services
        self._credential = bearer_credential
        instance = existing_instance(services.root)
        self._admin_principal = "forge-server-admin-principal:v1:" + instance.instance_id
        self.root_identity = root_identity or RootIdentity(services.root)
        self.read_grant = read_grant
        self.review_grant = review_grant
        self.worklist_grant = worklist_grant
        self.worklist_control_grant = worklist_control_grant
        self.advisory_grant = advisory_grant
        self.candidate_grant = candidate_grant
        self.decision_grant = decision_grant
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

    def _authentication_kind(self, authorization: str | None) -> str | None:
        if self._authenticated(authorization):
            return "ADMIN"
        if self.read_grant is not None and self.read_grant.authenticate(authorization):
            return "WORKSPACE_READ"
        if self.review_grant is not None and self.review_grant.authenticate(authorization):
            return "WORKSPACE_REVIEW"
        if self.worklist_grant is not None and self.worklist_grant.authenticate(authorization):
            return "WORKSPACE_WORKLIST"
        if self.worklist_control_grant is not None and self.worklist_control_grant.authenticate(authorization):
            return "WORKSPACE_WORKLIST_CONTROL"
        if self.decision_grant is not None and self.decision_grant.authenticate(authorization):
            return "CANDIDATE_DECISION"
        if self.candidate_grant is not None and self.candidate_grant.authenticate(authorization):
            return "ADVISORY_CANDIDATE"
        if self.advisory_grant is not None and self.advisory_grant.authenticate(authorization):
            return "ADVISORY"
        return None

    def _admin_principal_reference(self, authorization: str | None) -> str:
        if not self._authenticated(authorization):
            raise PermissionError("authenticated admin principal is required")
        return self._admin_principal

    @staticmethod
    def _read_scope_denied() -> APIResponse:
        return APIResponse(403, {"api_version": SERVER_API_VERSION, "error": {
            "code": "READ_SCOPE_DENIED", "message": "Read grant does not authorize this route",
        }}, ForgeServerAPI._headers())

    def _workspace_worklist(self, method, path, authorization):
        principal = self.worklist_grant.authenticate(authorization) if self.worklist_grant else None
        if principal is None: return self._authentication_required()
        if method=='GET' and path=='/v1/worksets':
            return APIResponse(200,{'contract_version':'forge-workspace-worklist-scopes/v1',
                'instance_id':principal.instance_id,'principal_id':principal.principal_id,
                'workset_ids':list(principal.workset_ids),'read_only':True},self._headers())
        parts = path.split('/')
        if len(parts)==4:parts[3]=unquote(parts[3])
        if method != 'GET' or len(parts) != 4 or parts[:3] != ['', 'v1', 'worksets'] or parts[3] not in principal.workset_ids:
            return APIResponse(403, {'error':{'code':'WORKLIST_SCOPE_DENIED'}}, self._headers())
        try:
            value=worklist_projection(self.services.root,principal.instance_id,parts[3],principal.principal_id)
            return APIResponse(200,value,self._headers())
        except PermissionError:
            return APIResponse(403,{'error':{'code':'WORKLIST_SCOPE_DENIED'}},self._headers())
        except (ValueError,OSError,sqlite3.Error,RuntimeError,TypeError,KeyError,AttributeError):
            return APIResponse(503,{'error':{'code':'WORKLIST_SOURCE_UNAVAILABLE'}},self._headers())

    def _workspace_read(self, method: str, path: str) -> APIResponse:
        if method != "GET" or path not in {"/v1/instance", "/v1/status"}:
            return self._read_scope_denied()
        try:
            document = (self.services.instance() if path == "/v1/instance"
                        else InstalledOperationsReadService(self.services.root).installed_status())
            if self.read_grant is None:
                raise ValueError("read grant is unavailable")
            document["workspace_read_scope"] = self.read_grant.scope()
            return APIResponse(200, document, self._headers())
        except (ForgeServerRuntimeError, PeerConfigurationError, OSError, ValueError,
                sqlite3.Error, RuntimeError) as error:
            return APIResponse(503, {"api_version": SERVER_API_VERSION, "error": {
                "code": "READ_UNAVAILABLE", "message": type(error).__name__,
            }}, self._headers())

    @staticmethod
    def _review_scope_denied() -> APIResponse:
        return APIResponse(403, {"api_version": SERVER_API_VERSION, "error": {
            "code": "REVIEW_SCOPE_DENIED", "message": "Review grant does not authorize this route or Mission",
        }}, ForgeServerAPI._headers())

    def _review_mission_for_decision(self, method: str, path: str,
                                     authorization: str | None) -> str | None:
        if method != "POST" or self.review_grant is None:
            return None
        parts = path.split("/")
        if len(parts) != 6 or parts[:4] != ["", "v1", "reviews", "missions"] or parts[5] != "decisions":
            return None
        mission_id = unquote(parts[4])
        principal = self.review_grant.authenticate(authorization)
        return mission_id if principal is not None and mission_id in principal.mission_ids else None

    def _workspace_review(self, method: str, path: str, authorization: str | None,
                          body: Mapping[str, Any] | None) -> APIResponse:
        principal = self.review_grant.authenticate(authorization) if self.review_grant else None
        if principal is None:
            return self._authentication_required()
        try:
            if method == "GET" and path == "/v1/reviews":
                return APIResponse(200, self.services.workspace_review_list(principal), self._headers())
            parts = path.split("/")
            if len(parts) < 5 or parts[:4] != ["", "v1", "reviews", "missions"]:
                return self._review_scope_denied()
            mission_id = unquote(parts[4])
            if mission_id not in principal.mission_ids:
                return self._review_scope_denied()
            if method == "GET" and len(parts) == 5:
                return APIResponse(200, self.services.workspace_review_detail(principal, mission_id),
                                   self._headers())
            if len(parts) == 6 and parts[5] == "decisions" and method == "POST":
                result, recorded = self.services.workspace_review_decide(principal, mission_id, body or {})
                return APIResponse(201 if recorded else 200, result, self._headers())
            if (len(parts) == 7 and parts[5] == "decisions" and method == "GET"):
                operation = self.services.workspace_review_operation(
                    principal, mission_id, unquote(parts[6]),
                )
                if operation is None:
                    return APIResponse(404, {"api_version": SERVER_API_VERSION, "error": {
                        "code": "REVIEW_OPERATION_NOT_FOUND", "message": "Review operation was not found",
                    }}, self._headers())
                return APIResponse(200, operation, self._headers())
            return self._review_scope_denied()
        except PermissionError:
            return self._review_scope_denied()
        except RuntimeServiceBusy:
            return APIResponse(503, {"api_version": SERVER_API_VERSION, "error": {
                "code": "REVIEW_BUSY", "message": "Retry the same operation ID after readback",
            }}, self._headers() | {"Retry-After": "1"})
        except (OSError, RuntimeError, sqlite3.Error) as error:
            return APIResponse(503, {"api_version": SERVER_API_VERSION, "error": {
                "code": "REVIEW_UNAVAILABLE", "message": type(error).__name__,
            }}, self._headers())
        except (ValueError, KeyError) as error:
            return APIResponse(409, {"api_version": SERVER_API_VERSION, "error": {
                "code": "REVIEW_CONFLICT", "message": type(error).__name__,
            }}, self._headers())

    @staticmethod
    def _authentication_required() -> APIResponse:
        return APIResponse(401, {"api_version": SERVER_API_VERSION, "error": {
            "code": "AUTHENTICATION_REQUIRED", "message": "Authentication is required",
        }}, ForgeServerAPI._headers())

    @staticmethod
    def _root_unavailable() -> APIResponse:
        return APIResponse(503, {"api_version": SERVER_API_VERSION, "error": {
            "code": "INSTANCE_UNAVAILABLE", "message": "Selected instance is unavailable",
        }}, ForgeServerAPI._headers())

    def handle(self, method: str, target: str, authorization: str | None,
               body: Mapping[str, Any] | None = None) -> APIResponse:
        headers = self._headers()
        kind = self._authentication_kind(authorization)
        if kind is None:
            return self._authentication_required()
        if self.root_identity.drifted():
            return self._root_unavailable()
        try:
            path = origin_form_path(target)
        except ValueError:
            return APIResponse(400, {"api_version": SERVER_API_VERSION, "error": {
                "code": "REQUEST_INVALID", "message": "Request target must be origin-form",
            }}, headers)
        if kind == "CANDIDATE_DECISION":
            status,document=CandidateDecisionService(self.services.root,self.decision_grant).handle(method,target,authorization,body)
            return APIResponse(status,document,headers)
        if path=="/v1/candidate-decisions" or path.startswith("/v1/candidate-decisions/"):
            return APIResponse(403,{"contract_version":"forge-candidate-decisions/v1","error":{"code":"DECISION_SCOPE_DENIED"}},headers)
        if kind == "ADVISORY_CANDIDATE":
            status,document=AdvisoryCandidateService(self.services.root,self.candidate_grant).handle(method,target,authorization,body)
            return APIResponse(status,document,headers)
        if path=="/v1/advisory-candidates" or path.startswith("/v1/advisory-candidates/"):
            return APIResponse(403,{"contract_version":"forge-advisory-candidate/v1","error":{"code":"CANDIDATE_SCOPE_DENIED"}},headers)
        if kind == "ADVISORY":
            service_type = MissionConceptService if path=="/v1/mission-concepts" or path.startswith("/v1/mission-concepts/") else AdvisoryService
            status,document=service_type(self.services.root,self.advisory_grant,self.services.provider_id).handle(method,target,authorization,body)
            return APIResponse(status,document,headers)
        if path=="/v1/mission-concepts" or path.startswith("/v1/mission-concepts/"):
            return APIResponse(403,{"contract_version":"forge-chat-first-mission/v1","error":{"code":"CONCEPT_SCOPE_DENIED"}},headers)
        if path=="/v1/advisory" or path.startswith("/v1/advisory/"):
            return APIResponse(403,{"contract_version":"forge-advisory-conversation/v1","error":{"code":"ADVISORY_SCOPE_DENIED"}},headers)
        if kind == "WORKSPACE_WORKLIST_CONTROL":
            status,document=WorklistControlService(self.services.root,self.worklist_control_grant,
                self.services.provider_id).handle(method,path,authorization,body)
            return APIResponse(status,document,headers)
        if path == '/v1/workset-controls' or path.startswith('/v1/workset-controls/'):
            return APIResponse(403,{'error':{'code':'CONTROL_SCOPE_DENIED'}},headers)
        if kind == "WORKSPACE_WORKLIST":
            return self._workspace_worklist(method,path,authorization)
        if kind == "WORKSPACE_READ":
            return self._workspace_read(method, path)
        if kind == "WORKSPACE_REVIEW":
            return self._workspace_review(method, path, authorization, body)
        if method=="GET" and (path=="/v1/worksets" or path.startswith("/v1/worksets/")):
            return APIResponse(403,{"error":{"code":"WORKLIST_SCOPE_DENIED"}},headers)
        if path == "/v1/reviews" or path.startswith("/v1/reviews/"):
            return self._review_scope_denied()
        if path == "/v1/projects" or path.startswith("/v1/projects/"):
            return self._read_api.handle(method, target, authorization)
        if method == "GET" and (
            path in {"/v1/status", "/v1/health"} or path.startswith("/v1/missions/")
            and not path.endswith(("/controller/start", "/controller/reopen", "/progression"))
        ):
            return self._read_api.handle(method, target, authorization)
        try:
            if method == "GET":
                response = self._admin_get(path, headers)
            elif method == "POST":
                response = self._admin_post(
                    path, body or {}, headers,
                    authenticated_principal_reference=self._admin_principal_reference(authorization),
                )
            else:
                response = None
            if response is not None:
                return response
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

    def _admin_get(self, path: str, headers: dict[str, str]) -> APIResponse | None:
        if path == "/v1/project-dag/capability":
            return APIResponse(200, self.services.project_dag_capability(), headers)
        if path == "/v1/instance":
            return APIResponse(200, self.services.instance(), headers)
        if path == "/v1/readiness":
            value = self.services.readiness()
            return APIResponse(200 if value["ready"] else 503, value, headers)
        if path == "/v1/readiness/standalone":
            value = self.services.standalone_readiness()
            return APIResponse(200 if value["ready"] else 503, value, headers)
        if path == "/v1/readiness/installation":
            value = self.services.installation_readiness()
            return APIResponse(200 if value["ready"] else 503, value, headers)
        if path in {"/v1/installation-peer", "/v1/installation-peer/preflight"}:
            value = self.services.installation_peer() if path == "/v1/installation-peer" else self.services.installation_peer_preflight()
            return APIResponse(200, value, headers)
        if path == "/v1/version":
            instance = existing_instance(self.services.root)
            return APIResponse(200, {
                "api_version": SERVER_API_VERSION,
                "product": "forge-autonomy",
                "product_version": instance.product_version,
                "storage_schema": instance.storage_schema,
                "instance_id": instance.instance_id,
            }, headers)
        if path == "/v1/provider-context":
            return APIResponse(200, self.services.provider_context(), headers)
        if path == "/v1/execution-host/preflight":
            return APIResponse(200, self.services.execution_host_preflight(), headers)
        if path.startswith("/v1/execution-host/detach/"):
            operation_id = unquote(path.removeprefix("/v1/execution-host/detach/"))
            return APIResponse(200, self.services.detach_execution_host_status(operation_id), headers)
        if path.startswith("/v1/missions/") and path.endswith("/progression"):
            parts = path.split("/")
            if len(parts) == 5:
                return APIResponse(200, self.services.mission_progression_status(unquote(parts[3])), headers)
        return None

    def _admin_post(
        self, path: str, body: Mapping[str, Any], headers: dict[str, str], *,
        authenticated_principal_reference: str,
    ) -> APIResponse | None:
        if path.startswith('/v1/worksets/'):
            parts=path.split('/')
            if len(parts)==5:
                return APIResponse(200,self.services.workset_command(parts[3],parts[4],body),headers)
        if path == "/v1/provider-context":
            return APIResponse(200, self.services.configure_provider_context(body), headers)
        if path == "/v1/installation-peer/configure":
            return APIResponse(200, self.services.configure_installation_peer(body), headers)
        if path == "/v1/execution-host/configure":
            return APIResponse(200, self.services.configure_execution_host(body), headers)
        if path == "/v1/execution-host/detach":
            return APIResponse(200, self.services.detach_execution_host(body), headers)
        if path in {
            "/v1/missions/inspect", "/v1/missions/approve-business",
            "/v1/missions/approve-architecture", "/v1/missions/admit",
        }:
            return APIResponse(200, self.services.mission_document(path.rsplit("/", 1)[1], body), headers)
        if path.startswith("/v1/missions/"):
            parts = path.split("/")
            if len(parts) == 5 and parts[4] == "progression-policy":
                result = self.services.mission_progression_policy(unquote(parts[3]), body)
                return APIResponse(201 if result.get("status") == "ASSIGNED" else 200, result, headers)
            if len(parts) == 5 and parts[4] == "progression-decisions":
                result, recorded = self.services.mission_progression_decide(
                    unquote(parts[3]), body,
                    authenticated_principal_reference=authenticated_principal_reference,
                )
                return APIResponse(201 if recorded else 200, result, headers)
            if len(parts) == 6 and parts[4] == "controller":
                mission_id = unquote(parts[3])
                if parts[5] == "start":
                    truth = body.get("repository_truth")
                    if not isinstance(truth, Mapping):
                        raise ValueError("controller start requires Repository Truth")
                    return APIResponse(200, self.services.mission_start(mission_id, truth), headers)
                if parts[5] == "reopen":
                    return APIResponse(200, self.services.mission_reopen(mission_id), headers)
            if len(parts) == 6 and parts[4] == "lifecycle" and parts[5] == "archive-no-dispatch":
                return APIResponse(200, self.services.mission_archive_no_dispatch(
                    unquote(parts[3]), body,
                    authenticated_principal_reference=authenticated_principal_reference,
                ), headers)
        return None


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

        def send_error(self, code: int, message: str | None = None,
                       explain: str | None = None) -> None:
            # Parser errors can include the raw request line or method.
            self.close_connection = True
            payload = json.dumps({"api_version": SERVER_API_VERSION, "error": {
                "code": "REQUEST_INVALID", "message": "HTTP request was rejected",
            }}, sort_keys=True, separators=(",", ":")).encode("utf-8")
            self.send_response(code)
            for name, value in ForgeServerAPI._headers().items():
                self.send_header(name, value)
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if getattr(self, "command", None) != "HEAD":
                self.wfile.write(payload)

        def _body(self) -> Mapping[str, Any] | None:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) > 1:
                raise ValueError("request Content-Length is ambiguous")
            if self.headers.get_all("Transfer-Encoding", []):
                raise ValueError("request Transfer-Encoding is unsupported")
            if self.command == "GET":
                return None
            length_text = lengths[0] if lengths else "0"
            if not length_text.isascii() or not length_text.isdigit():
                raise ValueError("request Content-Length is invalid")
            try:
                length = int(length_text)
            except ValueError as error:
                raise ValueError("request Content-Length is invalid") from error
            if length < 0 or length > _MAX_BODY:
                raise ValueError("request body exceeds Forge Server limit")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("request body is shorter than Content-Length")
            if not raw:
                return {}
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("request body must be a JSON object")
            return value

        def _dispatch(self) -> None:
            try:
                authorizations = self.headers.get_all("Authorization", [])
                if len(authorizations) > 1:
                    raise ValueError("request Authorization is ambiguous")
                authorization = authorizations[0] if authorizations else None
                kind = api._authentication_kind(authorization)
                if kind is None:
                    response = api._authentication_required()
                elif api.root_identity.drifted():
                    response = api._root_unavailable()
                else:
                    target = raw_request_target(self.raw_requestline)
                    path = origin_form_path(target)
                    review_mission = api._review_mission_for_decision(
                        self.command, path, authorization,
                    ) if kind == "WORKSPACE_REVIEW" else None
                    body = self._body() if kind in {"ADMIN", "WORKSPACE_WORKLIST_CONTROL", "ADVISORY", "ADVISORY_CANDIDATE", "CANDIDATE_DECISION"} or review_mission is not None else None
                    response = api.handle(self.command, target, authorization, body)
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
                 tick_interval: float = 0.25,
                 read_grant_file: str | Path | None = None) -> None:
        if not str(data_root):
            raise ValueError("Forge Server requires an explicit data root")
        if tick_interval <= 0:
            raise ValueError("Forge Server tick interval must be positive")
        self.instance = existing_instance(data_root)
        self.root = Path(self.instance.data_root)
        self.root_identity = RootIdentity(self.root)
        self.provider_id = provider_id
        self.tick_interval = tick_interval
        self._credential = read_bearer_credential(credential_file)
        self.state = ServerRuntimeState(self.instance, provider_id)
        self.services = ForgeServerApplicationServices(self.root, self.state, provider_id=provider_id)
        grant_path = (Path(read_grant_file) if read_grant_file is not None
                      else self.root / "credentials" / "workspace-read-grant.json")
        read_grant = WorkspaceReadGrant(self.root, self.instance.instance_id, grant_path)
        review_grant = WorkspaceReviewGrant(self.root, self.instance.instance_id)
        self.api = ForgeServerAPI(self.services, self._credential, root_identity=self.root_identity,
                                  read_grant=read_grant, review_grant=review_grant,
                                  worklist_grant=WorkspaceWorklistGrant(self.root,self.instance.instance_id),
                                  worklist_control_grant=WorkspaceWorklistControlGrant(self.root,self.instance.instance_id),
                                  advisory_grant=AdvisoryGrant(self.root,self.instance.instance_id),
                                  candidate_grant=AdvisoryCandidateGrant(self.root,self.instance.instance_id),
                                  decision_grant=CandidateDecisionGrant(self.root,self.instance.instance_id))
        self.server = make_server(host, port, self.api)
        address, actual_port = self.server.server_address
        self.state.update(listener={"host": address, "port": actual_port}, lifecycle="STARTING")
        self._stop = Event()
        self._lease = ServerInstanceLease(self.root)
        self._log = _ServerLog(self.root, self.root_identity)

    def stop(self) -> None:
        self._stop.set()

    def _tick(self) -> None:
        if self.root_identity.drifted():
            raise ForgeServerRuntimeError("Forge Server selected instance root changed")
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
        if self.root_identity.drifted():
            raise ForgeServerRuntimeError("Forge Server selected instance root changed")
        with self._lease.acquire():
            self._log.write(
                "server_starting", instance_id=self.instance.instance_id,
                host=self.server.server_address[0], port=self.server.server_address[1],
                product_version=self.instance.product_version, storage_schema=self.instance.storage_schema,
            )
            thread = Thread(target=self.server.serve_forever, name="forge-server-http", daemon=True)
            thread.start()
            previous_int = signal.getsignal(signal.SIGINT)
            previous_term = signal.getsignal(signal.SIGTERM)

            def request_stop(*_: object) -> None:
                self._stop.set()

            signal.signal(signal.SIGINT, request_stop)
            signal.signal(signal.SIGTERM, request_stop)
            self.state.update(lifecycle="RUNNING")
            self._log.write("server_running", instance_id=self.instance.instance_id)
            try:
                while not self._stop.is_set():
                    try:
                        self._tick()
                    except RuntimeServiceBusy:
                        self.state.scheduler("BUSY")
                    except Exception as error:
                        self.state.scheduler("NOT_READY", error=type(error).__name__)
                        self._log.write(
                            "scheduler_not_ready", instance_id=self.instance.instance_id,
                            error_type=type(error).__name__,
                        )
                    self._stop.wait(self.tick_interval)
            finally:
                self.state.update(lifecycle="STOPPING")
                self.server.shutdown()
                self.server.server_close()
                thread.join(timeout=5)
                self.state.update(lifecycle="STOPPED")
                self._log.write("server_stopped", instance_id=self.instance.instance_id)
                signal.signal(signal.SIGINT, previous_int)
                signal.signal(signal.SIGTERM, previous_term)
