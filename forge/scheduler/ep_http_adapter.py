"""Concrete, strict HTTP v1.2 Engineering Platform Execution Host adapter.

The runtime database remains the recovery authority. This adapter keeps only
the EP submission/run binding which follows from a persisted Forge request.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from forge.models.execution_host import ExecutionDispatch, ExecutionHostEvidence, ExecutionHostTemporaryUnavailable, ExecutionRequest
from .ep_v12 import terminal_evidence


class ExecutionHostBindingStore(Protocol):
    def execution_host_binding(self, correlation_id: str) -> dict[str, Any] | None: ...
    def save_execution_host_binding(self, correlation_id: str, document: Mapping[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class EngineeringPlatformHttpConfiguration:
    base_url: str
    project_id: str
    bearer_token: str
    host_id: str = "engineering-platform"
    timeout: float = 10


class EngineeringPlatformHttpExecutionHost:
    """EP v1.2 transport with compatibility preflight and durable idempotency."""

    SUPPORTED_PRODUCER_READBACK_CONTRACTS = ("1.2",)
    _COMPATIBILITY_KEYS = frozenset({"contract_version", "producer", "instance", "contracts"})

    def __init__(self, config: EngineeringPlatformHttpConfiguration, bindings: ExecutionHostBindingStore) -> None:
        if not config.base_url or not config.project_id or not config.bearer_token:
            raise ValueError("EP HTTP configuration requires endpoint, project, and credential")
        self.config = config
        self._bindings = bindings

    def _json(self, path: str, *, method: str = "GET", body: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        request = Request(self.config.base_url.rstrip("/") + path, data=data, method=method,
                          headers={"Authorization": "Bearer " + self.config.bearer_token, "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                value = json.loads(response.read())
                if not isinstance(value, dict):
                    raise ValueError("EP response must be a JSON object")
                return value
        except HTTPError as error:
            if error.code >= 500:
                raise ExecutionHostTemporaryUnavailable("EP temporarily unavailable") from error
            raise ValueError(f"EP rejected request: {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise ExecutionHostTemporaryUnavailable("EP transport unavailable") from error

    def _bytes(self, path: str) -> bytes:
        request = Request(self.config.base_url.rstrip("/") + path, headers={"Authorization": "Bearer " + self.config.bearer_token})
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                raw = response.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise ValueError("EP artifact exceeds consumer size limit")
                return raw
        except HTTPError as error:
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

    def _request_binding(self, request: ExecutionRequest) -> dict[str, Any]:
        contract = request.producer_contract
        return {"correlation_id": request.correlation_id, "host_id": request.host_id, "project_id": self.config.project_id,
                "repository_id": request.repository_id, "mission_id": request.mission_id,
                "mission_revision": self._mission_revision(request), "intent_id": request.intent_id,
                "intent_revision": request.intent_revision, "action_id": request.action_id,
                "runtime_prompt_id": contract.runtime_prompt.id, "runtime_prompt_digest": contract.runtime_prompt.content_digest,
                "producer": contract.producer.identity.to_dict(), "producer_contract_digest": contract.digest(),
                "retry_of_correlation_id": request.retry_of_correlation_id}

    def _binding(self, request: ExecutionRequest) -> dict[str, Any]:
        # Saved before POST: an ambiguous send is retried with the exact same
        # idempotency key, never a fresh correlation.
        return self._bindings.save_execution_host_binding(request.correlation_id, self._request_binding(request))

    def _payload(self, request: ExecutionRequest) -> dict[str, Any]:
        binding, contract = self._request_binding(request), request.producer_contract
        return {"repository_id": request.repository_id, "producer": contract.producer.identity.to_dict(),
                "prompt": contract.runtime_prompt.content, "idempotency_key": request.correlation_id,
                "correlation_id": request.correlation_id, "mission_id": request.mission_id,
                "engineering_action_id": request.action_id, "constraints": {"forge_execution": {
                    "contract_version": "1.0", "host_id": request.host_id, "repository_id": request.repository_id,
                    "correlation_id": request.correlation_id, "mission_id": request.mission_id,
                    "mission_revision": binding["mission_revision"], "intent_id": request.intent_id,
                    "intent_revision": request.intent_revision, "action_id": request.action_id,
                    "runtime_prompt": {"id": contract.runtime_prompt.id, "content_digest": contract.runtime_prompt.content_digest},
                    "retry_of_correlation_id": request.retry_of_correlation_id}}}

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
        if (not isinstance(producer, Mapping) or producer.get("id") != "engineering-platform"
                or not isinstance(producer.get("version"), str) or not producer["version"]
                or not isinstance(instance, Mapping) or not isinstance(instance.get("id"), str) or not instance["id"]
                or not isinstance(contracts, Mapping)):
            raise ValueError("EP_CAPABILITY_DECLARATION_MALFORMED")
        versions = contracts.get("producer_readback")
        if not isinstance(versions, list) or versions != ["1.2"]:
            raise ValueError("EP_READBACK_CONTRACT_INCOMPATIBLE")
        terminal_versions = contracts.get("terminal_evidence")
        if not isinstance(terminal_versions, list) or terminal_versions != ["1.2"]:
            raise ValueError("EP_TERMINAL_CONTRACT_INCOMPATIBLE")
        return declaration

    def _readback(self, request: ExecutionRequest, binding: Mapping[str, Any]) -> dict[str, Any] | None:
        submission_id = binding.get("submission_id")
        if not isinstance(submission_id, str) or not submission_id:
            return None
        readback = self._json(f"/v1/projects/{self.config.project_id}/submissions/{submission_id}")
        self._validate_readback(request, binding, readback)
        if readback.get("submission", {}).get("id") != submission_id:
            raise ValueError("EP readback submission identity changed")
        return readback

    def dispatch(self, request: ExecutionRequest) -> ExecutionDispatch | None:
        # A compatibility failure has no EP submission/action/repair side effect.
        self.preflight()
        binding = self._binding(request)
        readback = self._readback(request, binding)
        if readback is None:
            accepted = self._json(f"/v1/projects/{self.config.project_id}/submissions", method="POST", body=self._payload(request))
            submission_id = accepted.get("submission_id")
            if not isinstance(submission_id, str) or not submission_id:
                raise ValueError("EP submission acknowledgement lacks submission_id")
            binding = self._bindings.save_execution_host_binding(request.correlation_id,
                {"correlation_id": request.correlation_id, "submission_id": submission_id})
            readback = self._readback(request, binding)
        return self._dispatch_from_readback(request, binding, readback)

    def recover_dispatch(self, request: ExecutionRequest) -> ExecutionDispatch | None:
        binding = self._binding(request)
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
        terminal = readback.get("evidence", {}).get("terminal_artifact")
        if not isinstance(terminal, Mapping) or not isinstance(terminal.get("id"), str):
            return None
        raw = self._bytes(f"/v1/projects/{self.config.project_id}/artifacts/{terminal['id']}")
        evidence = terminal_evidence(readback, raw, host_id=self.config.host_id)
        observed_identity = (evidence.correlation_id, evidence.host_run_id, evidence.repository_evidence.runtime_prompt_id,
            evidence.repository_evidence.mission_id, evidence.repository_evidence.intent_id,
            evidence.repository_evidence.intent_revision, evidence.repository_evidence.action_id, evidence.repository_evidence.repository_id)
        request_identity = (request.correlation_id, dispatch.host_run_id, request.producer_contract.runtime_prompt.id,
            request.mission_id, request.intent_id, request.intent_revision, request.action_id, request.repository_id)
        if observed_identity != request_identity:
            raise ValueError("EP terminal artifact does not bind persisted request and dispatch")
        return evidence
