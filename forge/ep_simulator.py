"""Deterministic stateful Engineering Platform HTTP simulator for Forge qualification.

The simulator owns no Forge business logic.  It implements the externally
observable EP HTTP seam used by :class:`EngineeringPlatformHttpExecutionHost`
and keeps a durable-in-memory request ledger that may be retained across
simulator process restarts in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Lock, Thread
import time
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit


SIMULATOR_CONTRACT_VERSION = "1.0"
_MAX_BODY = 1_048_576


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def accepted_request_digest(payload: Mapping[str, Any]) -> str:
    """Independently reproduce EP's accepted-request semantic binding."""
    accepted = {
        "repository_id": payload["repository_id"],
        "producer": payload["producer"],
        "prompt_digest": sha256(str(payload["prompt"]).encode("utf-8")).hexdigest(),
        "constraints": payload["constraints"],
        "correlation_id": payload["correlation_id"],
        "mission_id": payload["mission_id"],
        "engineering_action_id": payload["engineering_action_id"],
    }
    return "sha256:" + sha256(_canonical_bytes(accepted) + b"\n").hexdigest()


@dataclass(frozen=True)
class EpSimulatorScenario:
    """Scenario-controlled boundary behavior, never an application-layer mock."""

    name: str = "success"
    terminal_after_reads: int = 0
    preflight_http_status: int | None = None
    workspace_http_status: int | None = None
    submission_http_status: int | None = None
    readback_http_status: int | None = None
    artifact_http_status: int | None = None
    connection_loss_at: frozenset[str] = frozenset()
    response_delay_seconds: float = 0.0
    workspace_clean: bool = True
    workspace_busy: bool = False
    active_lease: bool = False
    workspace_status: str = "READY"
    workspace_blocker: str | None = None

    def __post_init__(self) -> None:
        if self.terminal_after_reads < 0 or self.response_delay_seconds < 0:
            raise ValueError("EP simulator timing controls must be non-negative")
        for value in (
            self.preflight_http_status, self.workspace_http_status, self.submission_http_status,
            self.readback_http_status, self.artifact_http_status,
        ):
            if value is not None and (value < 400 or value > 599):
                raise ValueError("EP simulator HTTP fault status must be an error status")


@dataclass
class _Submission:
    submission_id: str
    run_id: str
    payload: dict[str, Any]
    payload_digest: str
    accepted_digest: str
    receipt: dict[str, Any]
    read_count: int = 0
    terminal_readback: dict[str, Any] | None = None
    terminal_artifact: bytes | None = None
    terminal_artifact_id: str | None = None


class EpSimulatorState:
    """Restart-retainable, thread-safe EP boundary ledger."""

    def __init__(
        self,
        *,
        project_id: str = "forge",
        repository_id: str = "forge",
        repository_identity: str = "pcvantol/forge",
        consumer_id: str = "forge-consumer",
        instance_id: str = "ep-simulator-instance",
        application_version: str = "simulator-1",
        bearer_token: str = "simulator-token",
        scenario: EpSimulatorScenario | None = None,
    ) -> None:
        self.project_id = project_id
        self.repository_id = repository_id
        self.repository_identity = repository_identity
        self.consumer_id = consumer_id
        self.instance_id = instance_id
        self.application_version = application_version
        self.bearer_token = bearer_token
        self.scenario = scenario or EpSimulatorScenario()
        self._lock = Lock()
        self._counter = 0
        self._by_key: dict[str, _Submission] = {}
        self._by_id: dict[str, _Submission] = {}
        self.audit: list[dict[str, Any]] = []

    def set_scenario(self, scenario: EpSimulatorScenario) -> None:
        with self._lock:
            self.scenario = scenario
            self.audit.append({"event": "scenario_changed", "scenario": scenario.name})

    def compatibility(self) -> dict[str, Any]:
        return {
            "contract_version": "1.1",
            "producer": {"id": "engineering-platform", "version": self.application_version},
            "instance": {"id": self.instance_id},
            "contracts": {
                "producer_readback": ["1.2", "1.3"],
                "terminal_evidence": ["1.4"],
                "validation_controls": ["1.0", "1.1"],
                "delivery_revision_validation": ["1.0"],
                "bounded_merge_delegation": ["1.0"],
            },
            "authentication": {
                "consumer_id": self.consumer_id,
                "consumer_status": "ACTIVE",
                "project_id": self.project_id,
                "project_status": "ACTIVE",
                "repository_id": self.repository_id,
                "repository_role": "authority",
                "local_repository_binding": "BOUND",
                "submission_authorization": "AUTHORIZED",
            },
        }

    def workspace_readiness(self) -> dict[str, Any]:
        scenario = self.scenario
        return {
            "contract_version": "1.0",
            "project_id": self.project_id,
            "repository_id": self.repository_id,
            "managed_workspace_id": f"{self.project_id}:{self.repository_id}",
            "execution_mode": "MANAGED",
            "repository_identity": self.repository_identity,
            "origin": self.repository_identity,
            "head_sha": "a" * 40,
            "branch": "main",
            "clean": scenario.workspace_clean,
            "busy": scenario.workspace_busy,
            "active_lease": scenario.active_lease,
            "preparation_capability": "EXACT_MAIN_FAST_FORWARD_V1",
            "status": scenario.workspace_status,
            "known_blocker": scenario.workspace_blocker,
            "observed_at": "2026-09-22T00:00:00+00:00",
        }

    def accept(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        required = {
            "repository_id", "producer", "prompt", "idempotency_key", "correlation_id",
            "mission_id", "engineering_action_id", "constraints",
        }
        if set(payload) != required or payload.get("repository_id") != self.repository_id:
            raise ValueError("EP simulator submission shape or repository is invalid")
        key = payload.get("idempotency_key")
        if not isinstance(key, str) or not key or key != payload.get("correlation_id"):
            raise ValueError("EP simulator idempotency identity is invalid")
        encoded = _canonical_bytes(payload)
        digest = "sha256:" + sha256(encoded).hexdigest()
        with self._lock:
            existing = self._by_key.get(key)
            if existing is not None:
                if existing.payload_digest != digest:
                    raise ValueError("EP simulator idempotency key was reused with different bytes")
                self.audit.append({"event": "submission_duplicate", "submission_id": existing.submission_id})
                return {"submission_id": existing.submission_id, "receipt": dict(existing.receipt)}
            self._counter += 1
            submission_id = f"sim-submission-{self._counter:04d}"
            run_id = f"sim-run-{self._counter:04d}"
            accepted_digest = accepted_request_digest(payload)
            forge_execution = payload["constraints"]["forge_execution"]
            receipt = {
                "contract_version": "1.0",
                "id": f"sim-receipt-{self._counter:04d}",
                "event": "FORGE_SUBMISSION_ACCEPTED",
                "issued_at": "2026-09-22T00:00:00+00:00",
                "submission_id": submission_id,
                "ep_instance_id": self.instance_id,
                "ep_application_version": self.application_version,
                "producer_contract_version": forge_execution["producer_contract_version"],
                "forge_provenance_contract_version": forge_execution["contract_version"],
                "forge_application_version": forge_execution["forge_application_version"],
                "producer_readback_contract_version": "1.2",
                "accepted_request_digest": accepted_digest,
            }
            item = _Submission(
                submission_id, run_id, dict(payload), digest, accepted_digest, receipt,
            )
            self._by_key[key] = item
            self._by_id[submission_id] = item
            self.audit.append({"event": "submission_accepted", "submission_id": submission_id})
            return {"submission_id": submission_id, "receipt": dict(receipt)}

    def pending_readback(self, submission_id: str) -> dict[str, Any]:
        with self._lock:
            item = self._by_id[submission_id]
            item.read_count += 1
            payload = item.payload
            forge_execution = payload["constraints"]["forge_execution"]
            readback = {
                "contract_version": "1.2",
                "submission": {
                    "id": item.submission_id,
                    "project_id": self.project_id,
                    "repository_id": self.repository_id,
                    "state": "QUEUED",
                    "transport": "HTTP",
                    "admission": "ADMITTED",
                    "created_at": "2026-09-22T00:00:00+00:00",
                    "accepted_request_digest": item.accepted_digest,
                },
                "producer": dict(payload["producer"]),
                "correlation": {
                    "correlation_id": payload["correlation_id"],
                    "mission_id": payload["mission_id"],
                    "engineering_action_id": payload["engineering_action_id"],
                },
                "provenance": {"status": "PERSISTED", "forge_execution": dict(forge_execution)},
                "disposition": {
                    "state": "QUEUED", "terminal": False, "execution_eligible": True,
                    "revision": 0, "operation_id": None, "event_reference": None,
                    "reason": "NOT_RECORDED", "actor_reference": "NOT_RECORDED", "recorded_at": None,
                },
                "run": None,
                "result": {"terminal": False, "outcome": None, "delivery_qualified": False},
                "evidence": {
                    "status": "PENDING",
                    "repository": {"id": self.repository_id, "revision": None},
                    "terminal_artifact": None,
                },
            }
            if (
                item.terminal_readback is not None
                and item.read_count > self.scenario.terminal_after_reads
            ):
                return json.loads(json.dumps(item.terminal_readback))
            return readback

    def complete(
        self,
        submission_id: str,
        *,
        outcome: str = "COMPLETE",
        assurance: str = "PASS",
        quality_review: str = "PASS",
        security_review: str = "PASS",
        delivery_revision: str | None = None,
    ) -> None:
        """Produce one strict v1.4 terminal result from the accepted Forge envelope.

        This builder is deliberately independent from Forge's terminal parser.
        It models only the externally versioned EP contract and is therefore
        suitable for success, provider/validation/assurance/delivery failures.
        """
        normalized_outcome = outcome.upper()
        if normalized_outcome not in {"COMPLETE", "FAILED", "BLOCKED"}:
            raise ValueError("EP simulator terminal outcome is unsupported")
        if assurance not in {"PASS", "FAIL", "UNRESOLVED", "NOT_RECORDED"}:
            raise ValueError("EP simulator assurance result is unsupported")
        if assurance == "NOT_RECORDED":
            quality_review = security_review = "NOT_RECORDED"
        elif quality_review not in {"PASS", "FAIL", "UNRESOLVED"} or security_review not in {
            "PASS", "FAIL", "UNRESOLVED"
        }:
            raise ValueError("EP simulator assurance review result is unsupported")

        with self._lock:
            item = self._by_id.get(submission_id)
            if item is None:
                raise ValueError("EP simulator submission does not exist")
            payload = item.payload
            forge_execution = payload["constraints"]["forge_execution"]
            revision_binding = payload["constraints"]["repository_revision_binding"]
            requested = revision_binding.get("requested_revision")
            allowed = revision_binding.get("allowed_baseline_revision")
            baseline = allowed or requested
            if not isinstance(baseline, str) or len(baseline) != 40:
                raise ValueError("EP simulator requires a bound repository baseline")
            candidate = sha256(("candidate:" + submission_id).encode()).hexdigest()[:40]
            if normalized_outcome == "COMPLETE":
                revision = delivery_revision or sha256(("delivery:" + submission_id).encode()).hexdigest()[:40]
                delivery_qualified = True
            else:
                revision = None
                delivery_qualified = False
            if assurance == "NOT_RECORDED":
                candidate_value = None
                assurance_document = {
                    "status": "NOT_RECORDED",
                    "profile": None,
                    "quality_review": "NOT_RECORDED",
                    "security_review": "NOT_RECORDED",
                    "repair_rounds": {"used": 0, "maximum": 3},
                    "findings": {"open_blocking": 0, "open_non_blocking": 0, "artifact": None},
                }
            else:
                candidate_value = candidate
                assurance_document = {
                    "status": assurance,
                    "profile": {
                        "version": "simulator-validation-profile@1",
                        "digest": "sha256:" + sha256(("profile:" + submission_id).encode()).hexdigest(),
                        "candidate_sha": candidate,
                    },
                    "quality_review": quality_review,
                    "security_review": security_review,
                    "repair_rounds": {"used": 0, "maximum": 3},
                    "findings": {
                        "open_blocking": int(quality_review == "FAIL" or security_review == "FAIL"),
                        "open_non_blocking": 0,
                        "artifact": None,
                    },
                }
            started = "2026-09-22T00:00:00+00:00"
            completed = "2026-09-22T00:00:01+00:00"
            transition = {
                "status": "ALLOWED" if allowed is not None else "EXACT",
                "from": requested,
                "to": baseline,
                "allowed_to": allowed,
            }
            artifact_id = "terminal-evidence:" + item.run_id
            artifact_document: dict[str, Any] = {
                "artifact_type": "EP_TERMINAL_EVIDENCE",
                "contract_version": "1.4",
                "submission": {
                    "id": item.submission_id,
                    "project_id": self.project_id,
                    "repository_id": self.repository_id,
                    "accepted_request_digest": item.accepted_digest,
                },
                "producer": dict(payload["producer"]),
                "correlation": {
                    "correlation_id": payload["correlation_id"],
                    "mission_id": payload["mission_id"],
                    "engineering_action_id": payload["engineering_action_id"],
                },
                "provenance": dict(forge_execution),
                "run": {
                    "id": item.run_id,
                    "outcome": normalized_outcome,
                    "delivery_qualified": delivery_qualified,
                    "execution_started_at": started,
                    "execution_completed_at": completed,
                    "execution_duration_ms": 1000,
                },
                "host_execution": {
                    "contract_version": "1.0",
                    "start": {
                        "status": "AVAILABLE",
                        "target_branch": "main",
                        "target_commit": baseline,
                        "checkout_identity_digest": "sha256:" + sha256(
                            ("checkout:" + submission_id).encode()
                        ).hexdigest(),
                        "tracked_file_count": 1,
                        "inventory_digest": "sha256:" + sha256(
                            ("inventory:start:" + submission_id).encode()
                        ).hexdigest(),
                    },
                    "terminal": {
                        "status": "AVAILABLE",
                        "tracked_file_count": 1,
                        "inventory_digest": "sha256:" + sha256(
                            ("inventory:end:" + submission_id).encode()
                        ).hexdigest(),
                        "worktree_state": "CLEAN",
                        "diff": {"modified": 1, "created": 0, "deleted": 0, "renamed": 0},
                        "activity": {"provider_invocations": 1, "host_validation_actions": 1},
                    },
                },
                "repository": {
                    "id": self.repository_id,
                    "requested_revision": requested,
                    "execution_baseline": baseline,
                    "baseline_transition": transition,
                    "candidate": candidate_value,
                    "revision": revision,
                    "revision_required": normalized_outcome == "COMPLETE",
                },
                "delivery": {
                    "status": "DELIVERED" if delivery_qualified else "NOT_DELIVERED",
                    "revision": revision,
                },
                "report": {"id": "report:" + item.run_id, "terminal_state": normalized_outcome},
                "references": {
                    "finalization": "finalization:" + item.run_id,
                    "quality": [],
                    "repair": [],
                    "validation": [{"command": "simulator:validation", "result": (
                        "PASS" if assurance == "PASS" else "FAIL"
                    )}],
                },
                "assurance": assurance_document,
            }
            raw = _canonical_bytes(artifact_document) + b"\n"
            readback: dict[str, Any] = {
                "contract_version": "1.2",
                "submission": {
                    "id": item.submission_id,
                    "project_id": self.project_id,
                    "repository_id": self.repository_id,
                    "state": normalized_outcome,
                    "transport": "HTTP",
                    "admission": "ADMITTED",
                    "created_at": "2026-09-22T00:00:00+00:00",
                    "accepted_request_digest": item.accepted_digest,
                },
                "producer": dict(payload["producer"]),
                "correlation": artifact_document["correlation"],
                "provenance": {"status": "PERSISTED", "forge_execution": dict(forge_execution)},
                "disposition": {
                    "state": normalized_outcome,
                    "terminal": True,
                    "execution_eligible": False,
                    "revision": 1,
                    "operation_id": None,
                    "event_reference": None,
                    "reason": "SIMULATED_TERMINAL",
                    "actor_reference": "EP_SIMULATOR",
                    "recorded_at": completed,
                },
                "run": {
                    "id": item.run_id,
                    "state": normalized_outcome,
                    "terminal": True,
                    "operator_resolution": "NONE",
                    "updated_at": completed,
                    "execution_started_at": started,
                    "execution_completed_at": completed,
                    "execution_duration_ms": 1000,
                },
                "result": {
                    "terminal": True,
                    "outcome": normalized_outcome,
                    "delivery_qualified": delivery_qualified,
                },
                "evidence": {
                    "status": "AVAILABLE",
                    "repository": {"id": self.repository_id, "revision": revision},
                    "terminal_artifact": {
                        "id": artifact_id,
                        "content_type": "application/json",
                        "digest_algorithm": "sha256",
                        "digest": "sha256:" + sha256(raw).hexdigest(),
                    },
                },
            }
            item.terminal_readback = readback
            item.terminal_artifact = raw
            item.terminal_artifact_id = artifact_id
            self.audit.append({
                "event": "terminal_produced",
                "submission_id": submission_id,
                "outcome": normalized_outcome,
                "assurance": assurance,
            })

    def seed_terminal(self, submission_id: str, readback: Mapping[str, Any], artifact: bytes) -> None:
        """Attach independently constructed terminal EP evidence to one accepted request."""
        if not isinstance(artifact, bytes) or not artifact:
            raise ValueError("EP simulator terminal artifact bytes are required")
        with self._lock:
            item = self._by_id.get(submission_id)
            if item is None:
                raise ValueError("EP simulator submission does not exist")
            document = json.loads(json.dumps(readback))
            submission = document.get("submission")
            if not isinstance(submission, dict) or submission.get("id") != submission_id:
                raise ValueError("EP simulator terminal readback does not bind its submission")
            if submission.get("accepted_request_digest") != item.accepted_digest:
                raise ValueError("EP simulator terminal readback accepted digest differs")
            terminal = document.get("evidence", {}).get("terminal_artifact")
            if not isinstance(terminal, dict) or not isinstance(terminal.get("id"), str):
                raise ValueError("EP simulator terminal readback lacks an artifact reference")
            terminal["digest"] = "sha256:" + sha256(artifact).hexdigest()
            item.terminal_readback = document
            item.terminal_artifact = bytes(artifact)
            item.terminal_artifact_id = terminal["id"]
            self.audit.append({"event": "terminal_seeded", "submission_id": submission_id})

    def readback(self, submission_id: str) -> dict[str, Any]:
        if submission_id not in self._by_id:
            raise KeyError(submission_id)
        return self.pending_readback(submission_id)

    def artifact(self, artifact_id: str) -> bytes:
        with self._lock:
            for item in self._by_id.values():
                if item.terminal_artifact_id == artifact_id and item.terminal_artifact is not None:
                    return bytes(item.terminal_artifact)
        raise KeyError(artifact_id)

    def submission_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._by_id))

    def terminal_documents(self, submission_id: str) -> tuple[dict[str, Any], bytes]:
        """Return copies for negative qualification without exposing request payloads."""
        with self._lock:
            item = self._by_id.get(submission_id)
            if item is None or item.terminal_readback is None or item.terminal_artifact is None:
                raise ValueError("EP simulator terminal evidence is not available")
            return json.loads(json.dumps(item.terminal_readback)), bytes(item.terminal_artifact)


class EpSimulatorServer:
    """Real loopback HTTP server around :class:`EpSimulatorState`."""

    def __init__(self, state: EpSimulatorState, *, host: str = "127.0.0.1", port: int = 0) -> None:
        if host != "127.0.0.1":
            raise ValueError("EP simulator is restricted to loopback")
        self.state = state
        state_ref = state

        class Handler(BaseHTTPRequestHandler):
            server_version = "ForgeEpSimulator/1"
            sys_version = ""

            def _authorized(self) -> bool:
                return self.headers.get("Authorization") == "Bearer " + state_ref.bearer_token

            def _delay_or_drop(self, stage: str) -> bool:
                scenario = state_ref.scenario
                if scenario.response_delay_seconds:
                    time.sleep(scenario.response_delay_seconds)
                if stage in scenario.connection_loss_at:
                    self.close_connection = True
                    return True
                return False

            def _send_json(self, status: int, document: Mapping[str, Any]) -> None:
                payload = _canonical_bytes(document)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _error(self, status: int, code: str) -> None:
                self._send_json(status, {"error": {"code": code}})

            def _body(self) -> dict[str, Any]:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError as error:
                    raise ValueError("invalid Content-Length") from error
                if length <= 0 or length > _MAX_BODY:
                    raise ValueError("invalid request body size")
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise ValueError("request must be a JSON object")
                return value

            def do_GET(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._error(401, "AUTHENTICATION_REQUIRED")
                    return
                path = urlsplit(self.path).path
                scenario = state_ref.scenario
                if path == "/v1/producer-compatibility":
                    if self._delay_or_drop("preflight"):
                        return
                    if scenario.preflight_http_status:
                        self._error(scenario.preflight_http_status, "PREFLIGHT_FAULT")
                    else:
                        self._send_json(200, state_ref.compatibility())
                    return
                workspace = f"/v1/projects/{state_ref.project_id}/managed-workspace-readiness"
                if path == workspace:
                    if self._delay_or_drop("workspace"):
                        return
                    if scenario.workspace_http_status:
                        self._error(scenario.workspace_http_status, "WORKSPACE_FAULT")
                    else:
                        self._send_json(200, state_ref.workspace_readiness())
                    return
                prefix = f"/v1/projects/{state_ref.project_id}/submissions/"
                if path.startswith(prefix):
                    if self._delay_or_drop("readback"):
                        return
                    if scenario.readback_http_status:
                        self._error(scenario.readback_http_status, "READBACK_FAULT")
                        return
                    submission_id = unquote(path[len(prefix):])
                    try:
                        self._send_json(200, state_ref.readback(submission_id))
                    except KeyError:
                        self._error(404, "SUBMISSION_MISSING")
                    return
                artifact_prefix = f"/v1/projects/{state_ref.project_id}/artifacts/"
                if path.startswith(artifact_prefix):
                    if self._delay_or_drop("artifact"):
                        return
                    if scenario.artifact_http_status:
                        self._error(scenario.artifact_http_status, "ARTIFACT_FAULT")
                        return
                    artifact_id = unquote(path[len(artifact_prefix):])
                    try:
                        payload = state_ref.artifact(artifact_id)
                    except KeyError:
                        self._error(404, "ARTIFACT_MISSING")
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return
                self._error(404, "ROUTE_NOT_FOUND")

            def do_POST(self) -> None:  # noqa: N802
                if not self._authorized():
                    self._error(401, "AUTHENTICATION_REQUIRED")
                    return
                path = urlsplit(self.path).path
                expected = f"/v1/projects/{state_ref.project_id}/submissions"
                if path != expected:
                    self._error(404, "ROUTE_NOT_FOUND")
                    return
                if self._delay_or_drop("submission"):
                    return
                scenario = state_ref.scenario
                if scenario.submission_http_status:
                    self._error(scenario.submission_http_status, "SUBMISSION_FAULT")
                    return
                try:
                    self._send_json(202, state_ref.accept(self._body()))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    self._error(409, "SUBMISSION_REJECTED")

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.thread: Thread | None = None

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def start(self) -> "EpSimulatorServer":
        if self.thread is not None:
            raise RuntimeError("EP simulator is already running")
        self.thread = Thread(target=self.server.serve_forever, name="forge-ep-simulator", daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        if self.thread is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.thread = None

    def __enter__(self) -> "EpSimulatorServer":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()
