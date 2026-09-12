"""Concrete, strict HTTP v1.2 Engineering Platform Execution Host adapter.

The runtime database remains the recovery authority. This adapter keeps only
the EP submission/run binding which follows from a persisted Forge request.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

from forge.execution_host_configuration import canonical_endpoint
from forge.models.execution_host import ExecutionDispatch, ExecutionHostEvidence, ExecutionHostTemporaryUnavailable, ExecutionRequest
from .ep_v12 import terminal_evidence


class ExecutionHostBindingStore(Protocol):
    def execution_host_binding(self, correlation_id: str) -> dict[str, Any] | None: ...
    def save_execution_host_binding(self, correlation_id: str, document: Mapping[str, Any]) -> dict[str, Any]: ...
    def record_execution_host_exchange_audit(self, correlation_id: str, *, direction: str,
                                             event_kind: str, document: Mapping[str, Any]) -> dict[str, Any]: ...
    def record_operational_event(self, **values: Any) -> dict[str, Any]: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    """Never replay a bearer credential to a redirected origin."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # type: ignore[no-untyped-def]
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler())


def _open(request: Request, timeout: float):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


@dataclass(frozen=True)
class EngineeringPlatformHttpConfiguration:
    base_url: str
    project_id: str
    bearer_token: str = field(repr=False)
    expected_instance_id: str = ""
    repository_id: str = ""
    repository_identity: str = ""
    allow_loopback_http: bool = False
    host_id: str = "engineering-platform"
    timeout: float = 10
    peer_binding_id: str = ""
    peer_configuration_revision: int = 0
    peer_configuration_digest: str = ""
    producer_readback_contract: str = "1.2"
    terminal_evidence_contract: str = "1.2"


class EngineeringPlatformHttpExecutionHost:
    """EP v1.2 transport with compatibility preflight and durable idempotency."""

    SUPPORTED_PRODUCER_READBACK_CONTRACTS = ("1.2",)
    FORGE_PROVENANCE_CONTRACT_VERSION = "1.1"
    EP_SUBMISSION_RECEIPT_CONTRACT_VERSION = "1.0"
    _COMPATIBILITY_KEYS = frozenset({"contract_version", "producer", "instance", "contracts"})

    def __init__(self, config: EngineeringPlatformHttpConfiguration, bindings: ExecutionHostBindingStore) -> None:
        required = (
            config.base_url, config.project_id, config.bearer_token, config.expected_instance_id,
            config.repository_id, config.repository_identity, config.host_id, config.peer_binding_id,
            config.peer_configuration_digest,
        )
        if (not all(required) or config.peer_configuration_revision < 1
                or any(character in "\r\n" for character in config.bearer_token)
                or config.producer_readback_contract != "1.2" or config.terminal_evidence_contract != "1.2"):
            raise ValueError("EP HTTP configuration requires a complete persisted v1.2 peer binding")
        # The product factory already canonicalizes this.  Revalidate direct
        # construction without ever permitting HTTP except for loopback.
        if canonical_endpoint(config.base_url, allow_loopback_http=config.allow_loopback_http) != config.base_url:
            raise ValueError("EP HTTP configuration endpoint is not canonical")
        if not 0 < config.timeout <= 60:
            raise ValueError("EP HTTP configuration timeout is invalid")
        self.config = config
        self._bindings = bindings

    @staticmethod
    def _segment(value: str) -> str:
        return quote(value, safe="")

    def _json(self, path: str, *, method: str = "GET", body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = Request(self.config.base_url.rstrip("/") + path, data=data, method=method,
                          headers={"Authorization": "Bearer " + self.config.bearer_token, "Content-Type": "application/json"})
        try:
            with _open(request, timeout=self.config.timeout) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise ValueError("EP response exceeds consumer size limit")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("EP response must be a JSON object")
                return value
        except HTTPError as error:
            error.close()
            if error.code >= 500:
                raise ExecutionHostTemporaryUnavailable("EP temporarily unavailable") from error
            raise ValueError(f"EP rejected request: {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise ExecutionHostTemporaryUnavailable("EP transport unavailable") from error

    def _bytes(self, path: str) -> bytes:
        request = Request(self.config.base_url.rstrip("/") + path, headers={"Authorization": "Bearer " + self.config.bearer_token})
        try:
            with _open(request, timeout=self.config.timeout) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise ValueError("EP artifact exceeds consumer size limit")
                return raw
        except HTTPError as error:
            error.close()
            if error.code >= 500:
                raise ExecutionHostTemporaryUnavailable("EP artifact temporarily unavailable") from error
            raise ValueError(f"EP artifact request rejected: {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise ExecutionHostTemporaryUnavailable("EP artifact transport unavailable") from error

    @staticmethod
    def _metadata(request: ExecutionRequest) -> dict[str, str]:
        return dict(request.producer_contract.execution_metadata)

    def _mission_revision(self, request: ExecutionRequest) -> str:
        revision = self._metadata(request).get("mission_revision")
        if not revision:
            raise ValueError("persisted Producer Contract lacks mission_revision provenance")
        return revision

    def _validate_request_scope(self, request: ExecutionRequest) -> None:
        repository_identity = getattr(request, "repository_identity", request.repository_id)
        if request.host_id != self.config.host_id:
            raise ValueError("EP_REQUEST_HOST_SCOPE_MISMATCH")
        if request.repository_id != self.config.repository_id or repository_identity != self.config.repository_identity:
            raise ValueError("EP_REQUEST_REPOSITORY_SCOPE_MISMATCH")

    def _request_binding(self, request: ExecutionRequest) -> dict[str, Any]:
        self._validate_request_scope(request)
        contract = request.producer_contract
        return {"correlation_id": request.correlation_id, "host_id": request.host_id, "project_id": self.config.project_id,
                "repository_id": request.repository_id, "mission_id": request.mission_id,
                "repository_identity": request.repository_identity,
                "peer_binding_id": self.config.peer_binding_id,
                "peer_configuration_revision": self.config.peer_configuration_revision,
                "peer_configuration_digest": self.config.peer_configuration_digest,
                "expected_ep_instance_id": self.config.expected_instance_id,
                "mission_revision": self._mission_revision(request), "intent_id": request.intent_id,
                "intent_revision": request.intent_revision, "action_id": request.action_id,
                "runtime_prompt_id": contract.runtime_prompt.id, "runtime_prompt_digest": contract.runtime_prompt.content_digest,
                "producer": contract.producer.identity.to_dict(), "producer_contract_digest": contract.digest(),
                "retry_of_correlation_id": request.retry_of_correlation_id}

    def _binding(self, request: ExecutionRequest) -> dict[str, Any]:
        # Saved before any network request: an ambiguous send is retried with
        # the exact same configuration and idempotency key, never retargeted.
        expected = self._request_binding(request)
        existing = self._bindings.execution_host_binding(request.correlation_id)
        configuration_keys = {
            "peer_binding_id", "peer_configuration_revision", "peer_configuration_digest",
            "expected_ep_instance_id", "project_id", "repository_id", "repository_identity", "host_id",
        }
        if existing is not None:
            if not configuration_keys <= set(existing):
                raise ValueError("EP_HISTORICAL_BINDING_CONFIGURATION_IDENTITY_MISSING")
            if any(existing.get(key) != expected[key] for key in configuration_keys):
                raise ValueError("EP_CORRELATION_CONFIGURATION_RETARGETING_BLOCKED")
        return self._bindings.save_execution_host_binding(request.correlation_id, expected)

    def _payload(self, request: ExecutionRequest) -> dict[str, Any]:
        binding, contract = self._request_binding(request), request.producer_contract
        return {"repository_id": request.repository_id, "producer": contract.producer.identity.to_dict(),
                "prompt": contract.runtime_prompt.content, "idempotency_key": request.correlation_id,
                "correlation_id": request.correlation_id, "mission_id": request.mission_id,
                "engineering_action_id": request.action_id, "constraints": {"forge_execution": {
                "contract_version": self.FORGE_PROVENANCE_CONTRACT_VERSION, "host_id": request.host_id, "repository_id": request.repository_id,
                "correlation_id": request.correlation_id, "mission_id": request.mission_id,
                "mission_revision": binding["mission_revision"], "intent_id": request.intent_id,
                "intent_revision": request.intent_revision, "action_id": request.action_id,
                "runtime_prompt": {"id": contract.runtime_prompt.id, "content_digest": contract.runtime_prompt.content_digest},
                    "retry_of_correlation_id": request.retry_of_correlation_id,
                    "producer_contract_version": contract.contract_version,
                    "forge_application_version": contract.producer.identity.version}}}

    def _audit_document(self, request: ExecutionRequest, binding: Mapping[str, Any], *, receipt: Mapping[str, Any] | None = None) -> dict[str, object]:
        contract = request.producer_contract
        return {
            "contract_version": "1.0",
            "producer_id": contract.producer.identity.id,
            "producer_type": str(contract.producer.identity.type),
            "forge_application_version": contract.producer.identity.version,
            "producer_contract_version": contract.contract_version,
            "forge_provenance_contract_version": self.FORGE_PROVENANCE_CONTRACT_VERSION,
            "correlation_id": request.correlation_id,
            "ep_project_id": self.config.project_id,
            "ep_repository_id": request.repository_id,
            "ep_instance_id": self.config.expected_instance_id,
            "submission_id": binding.get("submission_id"),
            "receipt_id": None if receipt is None else receipt.get("id"),
            "receipt_contract_version": None if receipt is None else receipt.get("contract_version"),
            "ep_application_version": None if receipt is None else receipt.get("ep_application_version"),
            "producer_readback_contract_version": None if receipt is None else receipt.get("producer_readback_contract_version"),
            "accepted_request_digest": None if receipt is None else receipt.get("accepted_request_digest"),
        }

    def _validate_submission_receipt(self, request: ExecutionRequest, binding: Mapping[str, Any], accepted: Mapping[str, Any]) -> Mapping[str, Any]:
        receipt = accepted.get("receipt")
        expected = {"contract_version", "id", "event", "issued_at", "submission_id", "ep_instance_id",
                    "ep_application_version", "producer_contract_version", "forge_provenance_contract_version",
                    "forge_application_version", "producer_readback_contract_version", "accepted_request_digest"}
        if not isinstance(receipt, Mapping) or set(receipt) != expected:
            raise ValueError("EP submission acknowledgement omits a versioned receipt")
        if (receipt.get("contract_version") != self.EP_SUBMISSION_RECEIPT_CONTRACT_VERSION
                or receipt.get("event") != "FORGE_SUBMISSION_ACCEPTED"
                or receipt.get("submission_id") != binding.get("submission_id")
                or receipt.get("ep_instance_id") != self.config.expected_instance_id
                or receipt.get("producer_contract_version") != request.producer_contract.contract_version
                or receipt.get("forge_provenance_contract_version") != self.FORGE_PROVENANCE_CONTRACT_VERSION
                or receipt.get("forge_application_version") != request.producer_contract.producer.identity.version
                or receipt.get("producer_readback_contract_version") != self.config.producer_readback_contract):
            raise ValueError("EP submission receipt does not bind the submitted Forge envelope")
        if not all(isinstance(receipt.get(field), str) and receipt.get(field) for field in ("id", "issued_at", "ep_application_version", "accepted_request_digest")):
            raise ValueError("EP submission receipt identity is invalid")
        digest = str(receipt["accepted_request_digest"])
        if (not digest.startswith("sha256:") or len(digest) != 71
                or any(character not in "0123456789abcdef" for character in digest[7:])):
            raise ValueError("EP submission receipt accepted-request digest is invalid")
        return receipt

    def _validate_readback(self, request: ExecutionRequest, binding: Mapping[str, Any], readback: Mapping[str, Any]) -> None:
        if readback.get("contract_version") not in self.SUPPORTED_PRODUCER_READBACK_CONTRACTS:
            raise ValueError("EP_READBACK_CONTRACT_INCOMPATIBLE")
        required = {"contract_version", "submission", "producer", "correlation", "provenance", "disposition", "run", "result", "evidence"}
        if set(readback) != required:
            raise ValueError("EP_READBACK_SCHEMA_INVALID")
        correlation, submission, producer = readback.get("correlation"), readback.get("submission"), readback.get("producer")
        root_provenance = readback.get("provenance")
        provenance = root_provenance.get("forge_execution") if isinstance(root_provenance, Mapping) else None
        if not all(isinstance(value, Mapping) for value in (correlation, submission, provenance, producer)):
            raise ValueError("EP readback omits required request binding")
        expected_correlation = {"correlation_id": request.correlation_id, "mission_id": request.mission_id,
                                "engineering_action_id": request.action_id}
        if any(correlation.get(key) != value for key, value in expected_correlation.items()):
            raise ValueError("EP readback correlation does not bind persisted request")
        if submission.get("repository_id") != request.repository_id or submission.get("project_id") != self.config.project_id:
            raise ValueError("EP readback submission does not bind project and repository")
        if dict(producer) != binding["producer"]:
            raise ValueError("EP readback producer does not bind persisted request")
        expected_provenance = {"host_id": request.host_id, "repository_id": request.repository_id,
                               "correlation_id": request.correlation_id, "mission_id": request.mission_id,
                               "mission_revision": binding["mission_revision"], "intent_id": request.intent_id,
                               "intent_revision": request.intent_revision, "action_id": request.action_id,
                               "retry_of_correlation_id": request.retry_of_correlation_id}
        if any(provenance.get(key) != value for key, value in expected_provenance.items()):
            raise ValueError("EP readback provenance does not bind persisted request")
        prompt = provenance.get("runtime_prompt")
        if not isinstance(prompt, Mapping) or dict(prompt) != {"id": binding["runtime_prompt_id"], "content_digest": binding["runtime_prompt_digest"]}:
            raise ValueError("EP readback Runtime Prompt does not bind persisted request")

    def preflight(self) -> dict[str, Any]:
        """Verify EP identity and v1.2 support without submitting anything."""
        declaration = self._json("/v1/producer-compatibility")
        if set(declaration) != self._COMPATIBILITY_KEYS or declaration.get("contract_version") != "1.0":
            raise ValueError("EP_CAPABILITY_DECLARATION_MALFORMED")
        producer, instance, contracts = declaration.get("producer"), declaration.get("instance"), declaration.get("contracts")
        if (not isinstance(producer, Mapping) or set(producer) != {"id", "version"}
                or producer.get("id") != "engineering-platform"
                or not isinstance(producer.get("version"), str) or not producer["version"]
                or not isinstance(instance, Mapping) or set(instance) != {"id"}
                or not isinstance(instance.get("id"), str) or not instance["id"]
                or not isinstance(contracts, Mapping)
                or set(contracts) != {"producer_readback", "terminal_evidence"}):
            raise ValueError("EP_CAPABILITY_DECLARATION_MALFORMED")
        if instance["id"] != self.config.expected_instance_id:
            raise ValueError("EP_INSTANCE_IDENTITY_MISMATCH")
        versions = contracts.get("producer_readback")
        if not isinstance(versions, list) or versions != [self.config.producer_readback_contract]:
            raise ValueError("EP_READBACK_CONTRACT_INCOMPATIBLE")
        terminal_versions = contracts.get("terminal_evidence")
        if not isinstance(terminal_versions, list) or terminal_versions != [self.config.terminal_evidence_contract]:
            raise ValueError("EP_TERMINAL_CONTRACT_INCOMPATIBLE")
        return declaration

    def _readback(self, request: ExecutionRequest, binding: Mapping[str, Any]) -> dict[str, Any] | None:
        submission_id = binding.get("submission_id")
        if not isinstance(submission_id, str) or not submission_id:
            return None
        return self._readback_for_submission(request, binding, submission_id)

    def _readback_for_submission(self, request: ExecutionRequest, binding: Mapping[str, Any],
                                 submission_id: str) -> dict[str, Any]:
        readback = self._json(
            f"/v1/projects/{self._segment(self.config.project_id)}/submissions/{self._segment(submission_id)}"
        )
        self._validate_readback(request, binding, readback)
        if readback.get("submission", {}).get("id") != submission_id:
            raise ValueError("EP readback submission identity changed")
        return readback

    def _operator_retry_resolution(self, request: ExecutionRequest, binding: Mapping[str, Any],
                                   readback: Mapping[str, Any], dispatch: ExecutionDispatch,
                                   ) -> tuple[Mapping[str, Any], str | None]:
        """Follow only EP's explicit, parent-bound internal operator retry chain."""
        current: Mapping[str, Any] = readback
        expected_parent_run = dispatch.host_run_id
        seen_submissions = {str(binding.get("submission_id"))}
        resolved = False
        while True:
            run, disposition = current.get("run"), current.get("disposition")
            if not isinstance(run, Mapping):
                return current, dispatch.host_run_id if resolved else None
            run_id = run.get("id")
            if not isinstance(run_id, str) or not run_id:
                raise ValueError("EP retry resolution run identity is invalid")
            if run_id != expected_parent_run:
                raise ValueError("EP retry resolution parent run differs from persisted dispatch")
            if run.get("operator_resolution") != "RETRIED":
                return current, dispatch.host_run_id if resolved else None
            if not isinstance(disposition, Mapping):
                raise ValueError("EP retry resolution disposition is invalid")
            successor_id = disposition.get("resolution_submission_id")
            if not isinstance(successor_id, str) or not successor_id or successor_id in seen_submissions:
                raise ValueError("EP retry resolution successor identity is invalid")
            seen_submissions.add(successor_id)
            successor = self._readback_for_submission(request, binding, successor_id)
            successor_disposition = successor.get("disposition")
            if (not isinstance(successor_disposition, Mapping)
                    or successor_disposition.get("retry_parent_run_id") != expected_parent_run):
                raise ValueError("EP retry resolution lineage does not bind its parent run")
            successor_run = successor.get("run")
            if successor_run is None:
                return successor, dispatch.host_run_id
            if not isinstance(successor_run, Mapping) or not isinstance(successor_run.get("id"), str):
                raise ValueError("EP retry resolution successor run is invalid")
            current, expected_parent_run, resolved = successor, successor_run["id"], True

    def _record_operator_retry_resolution(
        self,
        request: ExecutionRequest,
        binding: Mapping[str, Any],
        readback: Mapping[str, Any],
        evidence: ExecutionHostEvidence,
        resolved_from_host_run_id: str | None,
    ) -> None:
        """Persist one redacted Forge fact after successor evidence is verified.

        The EP retry is an EP-only operator action.  Forge therefore records
        the accepted, host-proven result rather than representing it as a new
        Forge submission or a Forge-owned retry.
        """
        if resolved_from_host_run_id is None:
            return
        submission = readback.get("submission")
        submission_id = submission.get("id") if isinstance(submission, Mapping) else None
        if not isinstance(submission_id, str) or not submission_id:
            raise ValueError("EP retry resolution submission identity is invalid")
        resolution = {
            "submission_id": submission_id,
            "retry_parent_run_id": resolved_from_host_run_id,
            "run_id": evidence.host_run_id,
        }
        persisted = binding.get("operator_retry_resolution")
        if persisted is not None:
            if persisted != resolution:
                raise ValueError("EP retry resolution conflicts with the persisted Forge audit binding")
            return
        self._bindings.save_execution_host_binding(
            request.correlation_id,
            {"correlation_id": request.correlation_id, "operator_retry_resolution": resolution},
        )
        self._bindings.record_operational_event(
            component="forge_execution_host", level="INFO",
            event="ep_operator_retry_resolution_evidence_accepted",
            mission_id=request.mission_id, action_id=request.action_id,
            correlation_id=request.correlation_id, run_id=evidence.host_run_id,
            details={
                "operation": "operator_retry_resolution",
                "outcome": "accepted",
                "resolution_submission_id": submission_id,
                "retry_parent_run_id": resolved_from_host_run_id,
                "resolved_from_host_run_id": resolved_from_host_run_id,
                "result_state": evidence.outcome.value,
            },
        )

    def dispatch(self, request: ExecutionRequest) -> ExecutionDispatch | None:
        # A compatibility failure has no EP submission/action/repair side effect.
        self._validate_request_scope(request)
        binding = self._binding(request)
        self.preflight()
        readback = self._readback(request, binding)
        if readback is None:
            self._bindings.record_execution_host_exchange_audit(
                request.correlation_id, direction="FORGE_TO_EP", event_kind="FORGE_SUBMISSION_SENT",
                document=self._audit_document(request, binding),
            )
            accepted = self._json(
                f"/v1/projects/{self._segment(self.config.project_id)}/submissions",
                method="POST", body=self._payload(request),
            )
            submission_id = accepted.get("submission_id")
            if not isinstance(submission_id, str) or not submission_id:
                raise ValueError("EP submission acknowledgement lacks submission_id")
            binding = self._bindings.save_execution_host_binding(request.correlation_id,
                {"correlation_id": request.correlation_id, "submission_id": submission_id})
            receipt = self._validate_submission_receipt(request, binding, accepted)
            self._bindings.record_execution_host_exchange_audit(
                request.correlation_id, direction="EP_TO_FORGE", event_kind="EP_SUBMISSION_RECEIPT_RECEIVED",
                document=self._audit_document(request, binding, receipt=receipt),
            )
            readback = self._readback(request, binding)
        return self._dispatch_from_readback(request, binding, readback)

    def recover_dispatch(self, request: ExecutionRequest) -> ExecutionDispatch | None:
        binding = self._binding(request)
        self.preflight()
        return self._dispatch_from_readback(request, binding, self._readback(request, binding))

    def _dispatch_from_readback(self, request: ExecutionRequest, binding: Mapping[str, Any], readback: Mapping[str, Any] | None) -> ExecutionDispatch | None:
        if readback is None:
            return None
        run = readback.get("run")
        if run is None:
            return None  # accepted but not yet claimed: ordinary resumable waiting
        if not isinstance(run, Mapping) or not isinstance(run.get("id"), str) or not run["id"]:
            raise ValueError("EP readback run identity is invalid")
        known_run = binding.get("host_run_id")
        if known_run is not None and known_run != run["id"]:
            raise ValueError("EP readback run conflicts with persisted dispatch")
        self._bindings.save_execution_host_binding(request.correlation_id,
            {"correlation_id": request.correlation_id, "host_run_id": run["id"]})
        return ExecutionDispatch(request, run["id"])

    def retrieve_evidence(self, dispatch: ExecutionDispatch) -> ExecutionHostEvidence | None:
        request, binding = dispatch.request, self._binding(dispatch.request)
        self.preflight()
        if binding.get("host_run_id") not in (None, dispatch.host_run_id):
            raise ValueError("persisted dispatch run differs from requested evidence run")
        readback = self._readback(request, binding)
        if readback is None:
            raise ValueError("missing persisted EP submission identity")
        observed = self._dispatch_from_readback(request, binding, readback)
        if observed is None:
            return None
        if observed.host_run_id != dispatch.host_run_id:
            raise ValueError("EP readback run differs from persisted dispatch")
        readback, resolved_from_host_run_id = self._operator_retry_resolution(request, binding, readback, dispatch)
        evidence = readback.get("evidence")
        terminal = evidence.get("terminal_artifact") if isinstance(evidence, Mapping) else None
        if not isinstance(terminal, Mapping) or not isinstance(terminal.get("id"), str):
            run = readback.get("run")
            # A terminal EP run without its immutable artifact is neither
            # ordinary pending work nor Forge-owned evidence.  Fail closed so
            # the persisted Mission can be explicitly recovered, rather than
            # waiting forever or manufacturing a terminal result.
            result = readback.get("result")
            state = run.get("state") if isinstance(run, Mapping) else None
            outcome = result.get("outcome") if isinstance(result, Mapping) else None
            # EP may retain ``terminal: false`` while recording a separately
            # retried operator resolution.  Forge must not follow that new EP
            # chain under the original correlation: a matching BLOCKED/FAILED
            # run and result is terminal for this persisted request.
            if (isinstance(run, Mapping) and run.get("terminal") is True
                    or state in {"BLOCKED", "FAILED"} and outcome == state):
                raise ValueError("EP_TERMINAL_WITHOUT_IMMUTABLE_EVIDENCE")
            return None
        raw = self._bytes(
            f"/v1/projects/{self._segment(self.config.project_id)}/artifacts/{self._segment(terminal['id'])}"
        )
        evidence = terminal_evidence(
            readback, raw, host_id=self.config.host_id,
            resolved_from_host_run_id=resolved_from_host_run_id,
        )
        observed_identity = (evidence.correlation_id, evidence.host_run_id, evidence.repository_evidence.runtime_prompt_id,
            evidence.repository_evidence.mission_id, evidence.repository_evidence.intent_id,
            evidence.repository_evidence.intent_revision, evidence.repository_evidence.action_id, evidence.repository_evidence.repository_id)
        expected_run = evidence.host_run_id if resolved_from_host_run_id is not None else dispatch.host_run_id
        request_identity = (request.correlation_id, expected_run, request.producer_contract.runtime_prompt.id,
            request.mission_id, request.intent_id, request.intent_revision, request.action_id, request.repository_id)
        if observed_identity != request_identity:
            raise ValueError("EP terminal artifact does not bind persisted request and dispatch")
        self._record_operator_retry_resolution(request, binding, readback, evidence, resolved_from_host_run_id)
        return evidence
