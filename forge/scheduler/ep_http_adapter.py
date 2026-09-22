"""Concrete, strict HTTP v1.2 readback / v1.4 evidence host adapter.

The runtime database remains the recovery authority. This adapter keeps only
the EP submission/run binding which follows from a persisted Forge request.
"""
from __future__ import annotations

import json
import re
from hashlib import sha256
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
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
    def execution_host_exchange_audit(self, correlation_id: str) -> tuple[dict[str, Any], ...]: ...
    def record_operational_event(self, **values: Any) -> dict[str, Any]: ...
    def operational_log_page(self, **values: Any) -> dict[str, Any]: ...


class _NoRedirectHandler(HTTPRedirectHandler):
    """Never replay a bearer credential to a redirected origin."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):  # type: ignore[no-untyped-def]
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler())
_TERMINAL_ARTIFACT_PUBLICATION_GRACE = timedelta(minutes=2)


def _terminal_artifact_publication_pending(readback: Mapping[str, Any]) -> bool:
    """Allow EP's completed run a bounded interval to publish its artifact."""
    run, result, evidence = (readback.get(key) for key in ("run", "result", "evidence"))
    if not all(isinstance(item, Mapping) for item in (run, result, evidence)):
        return False
    if (run.get("state"), result.get("outcome"), evidence.get("status")) != (
        "COMPLETE", "COMPLETE", "MISSING",
    ):
        return False
    # The dispatch row's updated_at may still describe the initial submission
    # when the terminal checkpoint becomes visible. EP's durable completion
    # timestamp, not dispatch age, starts the publication grace period.
    completed_at = run.get("execution_completed_at")
    if not isinstance(completed_at, str):
        return False
    try:
        completed_at = datetime.fromisoformat(completed_at)
    except ValueError:
        return False
    if completed_at.tzinfo is None:
        return False
    age = datetime.now(timezone.utc) - completed_at.astimezone(timezone.utc)
    return timedelta(0) <= age < _TERMINAL_ARTIFACT_PUBLICATION_GRACE


def _open(request: Request, timeout: float):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


@dataclass(frozen=True)
class EngineeringPlatformHttpConfiguration:
    base_url: str
    project_id: str
    bearer_token: str = field(repr=False)
    expected_instance_id: str = ""
    expected_consumer_id: str = ""
    repository_id: str = ""
    repository_identity: str = ""
    allow_loopback_http: bool = False
    host_id: str = "engineering-platform"
    timeout: float = 10
    peer_binding_id: str = ""
    peer_configuration_revision: int = 0
    peer_configuration_digest: str = ""
    producer_readback_contract: str = "1.2"
    terminal_evidence_contract: str = "1.4"


class EngineeringPlatformHttpExecutionHost:
    """EP v1.2/v1.4 transport with compatibility preflight and durable idempotency."""

    SUPPORTED_PRODUCER_READBACK_CONTRACTS = ("1.2", "1.3")
    FORGE_PROVENANCE_CONTRACT_VERSION = "1.3"
    EP_SUBMISSION_RECEIPT_CONTRACT_VERSION = "1.0"
    _COMPATIBILITY_KEYS = frozenset({
        "contract_version", "producer", "instance", "contracts", "authentication",
    })

    def __init__(self, config: EngineeringPlatformHttpConfiguration, bindings: ExecutionHostBindingStore) -> None:
        required = (
            config.base_url, config.project_id, config.bearer_token, config.expected_instance_id,
            config.expected_consumer_id, config.repository_id, config.repository_identity,
            config.host_id, config.peer_binding_id,
            config.peer_configuration_digest,
        )
        if (not all(required) or config.peer_configuration_revision < 1
                or any(character in "\r\n" for character in config.bearer_token)
                or config.producer_readback_contract != "1.2" or config.terminal_evidence_contract != "1.4"):
            raise ValueError("EP HTTP configuration requires a complete persisted v1.2/v1.4 peer binding")
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
        # The digest persisted with a correlation binds the exact serialized
        # submission.  Reuse the transport serializer so non-ASCII prompt text
        # cannot make the audited digest differ from the bytes sent to EP.
        data = None if body is None else self._canonical_json_bytes(body)
        request = Request(self.config.base_url.rstrip("/") + path, data=data, method=method,
                          headers={"Authorization": "Bearer " + self.config.bearer_token,
                                   "Content-Type": "application/json",
                                   "EP-Project-ID": self.config.project_id,
                                   "EP-Repository-ID": self.config.repository_id,
                                   "EP-Producer-Readback-Contract": "1.3"})
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
        except (URLError, TimeoutError, ConnectionError) as error:
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
        except (URLError, TimeoutError, ConnectionError) as error:
            raise ExecutionHostTemporaryUnavailable("EP artifact transport unavailable") from error

    @staticmethod
    def _metadata(request: ExecutionRequest) -> dict[str, str]:
        return dict(request.producer_contract.execution_metadata)

    @staticmethod
    def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")

    @classmethod
    def _payload_digest(cls, value: Mapping[str, Any]) -> str:
        return "sha256:" + sha256(cls._canonical_json_bytes(value)).hexdigest()

    def _expected_ep_accepted_request_digest(self, request: ExecutionRequest) -> str:
        """Recompute EP #222's accepted-request binding for a new request.

        This is deliberately distinct from ``submission_payload_digest``:
        EP's versioned receipt covers its accepted request semantics, while
        Forge's digest covers the exact bytes it sent.  Both must remain bound
        to the persisted correlation.
        """
        contract = request.producer_contract
        accepted = {
            "repository_id": request.repository_id,
            "producer": contract.producer.identity.to_dict(),
            # EP records the SHA-256 of the exact prompt text it received,
            # rather than Forge's distinct Runtime Prompt provenance digest.
            "prompt_digest": sha256(contract.runtime_prompt.content.encode("utf-8")).hexdigest(),
            "constraints": self._payload(request)["constraints"],
            "correlation_id": request.correlation_id,
            "mission_id": request.mission_id,
            "engineering_action_id": request.action_id,
        }
        return "sha256:" + sha256(self._canonical_json_bytes(accepted) + b"\n").hexdigest()

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
        action_context = contract.action_context
        planning_context = contract.planning_context
        if action_context is None or planning_context is None:
            raise ValueError("Forge Producer Contract lacks immutable Action or planning context")
        revision_binding = request.repository_revision_binding
        if revision_binding is None:
            raise ValueError("EP_REQUEST_REPOSITORY_REVISION_BINDING_REQUIRED")
        if request.origin_identity is None:
            raise ValueError("EP_REQUEST_APPROVED_ORIGIN_IDENTITY_REQUIRED")
        payload = self._payload(request)
        return {"correlation_id": request.correlation_id, "host_id": request.host_id, "project_id": self.config.project_id,
                "repository_id": request.repository_id, "mission_id": request.mission_id,
                "repository_identity": request.repository_identity,
                "peer_binding_id": self.config.peer_binding_id,
                "peer_configuration_revision": self.config.peer_configuration_revision,
                "peer_configuration_digest": self.config.peer_configuration_digest,
                "expected_ep_instance_id": self.config.expected_instance_id,
                "expected_ep_consumer_id": self.config.expected_consumer_id,
                "mission_revision": self._mission_revision(request), "intent_id": request.intent_id,
                "intent_revision": request.intent_revision, "action_id": request.action_id,
                "runtime_prompt_id": contract.runtime_prompt.id, "runtime_prompt_digest": contract.runtime_prompt.content_digest,
                "producer": contract.producer.identity.to_dict(), "producer_contract_digest": contract.digest(),
                "action_context_envelope_digest": action_context.envelope_digest,
                "planning_context_envelope_digest": planning_context.envelope_digest,
                "repository_revision_binding": revision_binding.to_dict(),
                "repository_revision_binding_digest": revision_binding.digest(),
                "submission_payload_digest": self._payload_digest(payload),
                "retry_of_correlation_id": request.retry_of_correlation_id}

    def _historical_configuration_adoption_verified(
        self, existing: Mapping[str, Any], *, consumer_was_missing: bool,
    ) -> bool:
        previous_digest = existing.get("peer_configuration_digest")
        previous_revision = existing.get("peer_configuration_revision")
        if (
            previous_digest == self.config.peer_configuration_digest
            and previous_revision == self.config.peer_configuration_revision
        ):
            return not consumer_was_missing
        if (
            not isinstance(previous_digest, str)
            or not isinstance(previous_revision, int)
            or self.config.peer_configuration_revision != previous_revision + 1
        ):
            return False
        try:
            page = self._bindings.operational_log_page(
                events=("execution_host_configuration_replaced",), page_size=200,
            )
        except (AttributeError, RuntimeError, ValueError):
            return False
        items = page.get("items") if isinstance(page, Mapping) else None
        if not isinstance(items, (tuple, list)):
            return False
        expected_adoption = (
            "LEGACY_CONSUMER_IDENTITY_ADOPTION_V1"
            if consumer_was_missing else "TARGET_IDENTITY_PRESERVED_V1"
        )
        matches = []
        for item in items:
            details = item.get("details") if isinstance(item, Mapping) else None
            if not isinstance(details, Mapping):
                continue
            if (
                details.get("operation") == "replaced"
                and details.get("binding_id") == self.config.peer_binding_id
                and details.get("ep_instance_id") == self.config.expected_instance_id
                and details.get("ep_consumer_id") == self.config.expected_consumer_id
                and details.get("previous_configuration_revision") == previous_revision
                and details.get("request_digest") == previous_digest
                and details.get("configuration_revision") == self.config.peer_configuration_revision
                and details.get("configuration_digest") == self.config.peer_configuration_digest
                and details.get("historical_readback_adoption") == expected_adoption
                and isinstance(details.get("historical_target_identity_digest"), str)
                and len(details["historical_target_identity_digest"]) == 71
                and details["historical_target_identity_digest"].startswith("sha256:")
                and all(character in "0123456789abcdef"
                        for character in details["historical_target_identity_digest"][7:])
            ):
                matches.append(item)
        return len(matches) == 1

    def _binding(self, request: ExecutionRequest, *, allow_historical_readback: bool = False) -> dict[str, Any]:
        # Saved before any network request: an ambiguous send is retried with
        # the exact same configuration and idempotency key, never retargeted.
        existing = self._bindings.execution_host_binding(request.correlation_id)
        if (allow_historical_readback and request.repository_revision_binding is None
                and existing is not None):
            self._validate_request_scope(request)
            contract = request.producer_contract
            action_context, planning_context = contract.action_context, contract.planning_context
            if action_context is None or planning_context is None:
                raise ValueError("Forge Producer Contract lacks immutable Action or planning context")
            historical_identity = {
                "correlation_id": request.correlation_id, "host_id": request.host_id,
                "project_id": self.config.project_id, "repository_id": request.repository_id,
                "mission_id": request.mission_id, "repository_identity": request.repository_identity,
                "mission_revision": self._mission_revision(request), "intent_id": request.intent_id,
                "intent_revision": request.intent_revision, "action_id": request.action_id,
                "runtime_prompt_id": contract.runtime_prompt.id,
                "runtime_prompt_digest": contract.runtime_prompt.content_digest,
                "producer": contract.producer.identity.to_dict(),
                "producer_contract_digest": contract.digest(),
                "action_context_envelope_digest": action_context.envelope_digest,
                "planning_context_envelope_digest": planning_context.envelope_digest,
                "retry_of_correlation_id": request.retry_of_correlation_id,
            }
            if any(key not in existing or existing.get(key) != value
                   for key, value in historical_identity.items()):
                raise ValueError("EP_HISTORICAL_REQUEST_BINDING_MISMATCH")
            historical_consumer_adoption = "expected_ep_consumer_id" not in existing
            stable_configuration = {
                "peer_binding_id": self.config.peer_binding_id,
                "expected_ep_instance_id": self.config.expected_instance_id,
                "expected_ep_consumer_id": self.config.expected_consumer_id,
                "project_id": self.config.project_id,
                "repository_id": self.config.repository_id,
                "repository_identity": self.config.repository_identity,
                "host_id": self.config.host_id,
            }
            if any(
                key != "expected_ep_consumer_id" or not historical_consumer_adoption
                for key in stable_configuration
                if key not in existing or existing.get(key) != stable_configuration[key]
            ):
                raise ValueError("EP_CORRELATION_CONFIGURATION_RETARGETING_BLOCKED")
            if not self._historical_configuration_adoption_verified(
                existing, consumer_was_missing=historical_consumer_adoption,
            ):
                raise ValueError("EP_HISTORICAL_CONFIGURATION_ADOPTION_UNVERIFIED")
            return existing
        expected = self._request_binding(request)
        configuration_keys = {
            "peer_binding_id", "peer_configuration_revision", "peer_configuration_digest",
            "expected_ep_instance_id", "expected_ep_consumer_id", "project_id",
            "repository_id", "repository_identity", "host_id",
        }
        if existing is not None:
            missing_configuration = configuration_keys - set(existing)
            historical_consumer_adoption = (
                allow_historical_readback
                and missing_configuration == {"expected_ep_consumer_id"}
            )
            if missing_configuration and not historical_consumer_adoption:
                raise ValueError("EP_HISTORICAL_BINDING_CONFIGURATION_IDENTITY_MISSING")
            stable_configuration_keys = configuration_keys - {
                "peer_configuration_revision", "peer_configuration_digest",
            }
            if historical_consumer_adoption:
                stable_configuration_keys.remove("expected_ep_consumer_id")
            if any(existing.get(key) != expected[key] for key in stable_configuration_keys):
                raise ValueError("EP_CORRELATION_CONFIGURATION_RETARGETING_BLOCKED")
            if (
                allow_historical_readback
                and not self._historical_configuration_adoption_verified(
                    existing, consumer_was_missing=historical_consumer_adoption,
                )
            ):
                raise ValueError("EP_HISTORICAL_CONFIGURATION_ADOPTION_UNVERIFIED")
            if (not allow_historical_readback
                    and any(existing.get(key) != expected[key] for key in configuration_keys)):
                raise ValueError("EP_CORRELATION_CONFIGURATION_RETARGETING_BLOCKED")
            request_keys = frozenset(expected) - configuration_keys
            if any(key not in existing or existing.get(key) != expected[key] for key in request_keys):
                raise ValueError("EP_CORRELATION_REQUEST_RETARGETING_BLOCKED")
            if allow_historical_readback:
                return existing
        return self._bindings.save_execution_host_binding(request.correlation_id, expected)

    def _payload(self, request: ExecutionRequest) -> dict[str, Any]:
        self._validate_request_scope(request)
        if request.origin_identity is None:
            raise ValueError("EP_REQUEST_APPROVED_ORIGIN_IDENTITY_REQUIRED")
        contract = request.producer_contract
        action_context = contract.action_context
        planning_context = contract.planning_context
        revision_binding = request.repository_revision_binding
        if action_context is None or planning_context is None:  # Guarded by _request_binding; keeps this payload total.
            raise ValueError("Forge Producer Contract lacks immutable Action or planning context")
        if revision_binding is None:
            raise ValueError("EP_REQUEST_REPOSITORY_REVISION_BINDING_REQUIRED")
        forge_execution = {
            "contract_version": self.FORGE_PROVENANCE_CONTRACT_VERSION, "host_id": request.host_id,
            "repository_id": request.repository_id, "correlation_id": request.correlation_id,
            "mission_id": request.mission_id, "mission_revision": self._mission_revision(request),
            "intent_id": request.intent_id, "intent_revision": request.intent_revision,
            "action_id": request.action_id,
            "runtime_prompt": {"id": contract.runtime_prompt.id,
                               "content_digest": contract.runtime_prompt.content_digest},
            "retry_of_correlation_id": request.retry_of_correlation_id,
            "producer_contract_version": contract.contract_version,
            "forge_application_version": contract.producer.identity.version,
            "action_context_envelope": action_context.to_dict(),
            "planning_context_envelope": planning_context.to_dict(),
        }
        if any(value.startswith("ep-merge-delegation:") or value == "ep-delivery-control-validation:1"
               for value in contract.execution_constraints):
            forge_execution["execution_constraints"] = list(contract.execution_constraints)
        return {"repository_id": request.repository_id, "producer": contract.producer.identity.to_dict(),
                "prompt": contract.runtime_prompt.content, "idempotency_key": request.correlation_id,
                "correlation_id": request.correlation_id, "mission_id": request.mission_id,
                "engineering_action_id": request.action_id, "constraints": {"forge_execution": forge_execution,
                    "repository_revision_binding": revision_binding.ep_constraint(
                        request.origin_identity)}}

    def _audit_document(self, request: ExecutionRequest, binding: Mapping[str, Any], *, receipt: Mapping[str, Any] | None = None) -> dict[str, object]:
        contract = request.producer_contract
        return {
            "contract_version": "1.0",
            "producer_id": contract.producer.identity.id,
            "producer_type": str(contract.producer.identity.type),
            "forge_application_version": contract.producer.identity.version,
            "producer_contract_version": contract.contract_version,
            "forge_provenance_contract_version": self.FORGE_PROVENANCE_CONTRACT_VERSION,
            "action_context_envelope_version": None if contract.action_context is None else contract.action_context.envelope_version,
            "action_context_generator_id": None if contract.action_context is None else contract.action_context.generator_id,
            "action_context_generator_model": None if contract.action_context is None else contract.action_context.generator_model,
            "action_context_generator_version": None if contract.action_context is None else contract.action_context.generator_version,
            "action_context_summary_digest": None if contract.action_context is None else contract.action_context.summary_digest,
            "action_context_envelope_digest": None if contract.action_context is None else contract.action_context.envelope_digest,
            "planning_context_envelope_version": None if contract.planning_context is None else contract.planning_context.envelope_version,
            "planning_context_envelope_digest": None if contract.planning_context is None else contract.planning_context.envelope_digest,
            "planning_context_decision_evidence_reference_digest": (
                None if contract.planning_context is None else contract.planning_context.decision_evidence_reference_digest
            ),
            "repository_revision_binding": binding.get("repository_revision_binding"),
            "repository_revision_binding_digest": binding.get("repository_revision_binding_digest"),
            "submission_payload_digest": binding.get("submission_payload_digest"),
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
        if (request.repository_revision_binding is not None
                and digest != self._expected_ep_accepted_request_digest(request)):
            raise ValueError("EP submission receipt accepted-request digest does not bind persisted request")
        return receipt

    def _submission_receipt_id(self, request: ExecutionRequest, binding: Mapping[str, Any]) -> str:
        """Recover the already-validated EP receipt that binds terminal evidence.

        New bindings persist the complete receipt.  Bindings written before
        that durability fix deliberately fall back only to the existing,
        immutable EP-to-Forge audit fact; no remote receipt is invented and a
        duplicate or mismatched audit record fails closed.
        """
        persisted = binding.get("submission_receipt")
        if persisted is not None:
            if not isinstance(persisted, Mapping):
                raise ValueError("EP persisted submission receipt is malformed")
            receipt = self._validate_submission_receipt(request, binding, {"receipt": persisted})
            return str(receipt["id"])

        records = self._bindings.execution_host_exchange_audit(request.correlation_id)
        candidates = [item for item in records
                      if item.get("direction") == "EP_TO_FORGE"
                      and item.get("event_kind") == "EP_SUBMISSION_RECEIPT_RECEIVED"]
        if len(candidates) != 1:
            raise ValueError("EP persisted submission receipt audit is missing or ambiguous")
        document = candidates[0].get("document")
        if not isinstance(document, Mapping):
            raise ValueError("EP persisted submission receipt audit is malformed")
        expected_keys = {
            "contract_version", "producer_id", "producer_type", "forge_application_version",
            "producer_contract_version", "forge_provenance_contract_version", "correlation_id",
            "action_context_envelope_version", "action_context_generator_id", "action_context_generator_model",
            "action_context_generator_version", "action_context_summary_digest", "action_context_envelope_digest",
            "planning_context_envelope_version", "planning_context_envelope_digest",
            "planning_context_decision_evidence_reference_digest",
            "repository_revision_binding", "repository_revision_binding_digest",
            "submission_payload_digest",
            "ep_project_id", "ep_repository_id", "ep_instance_id", "submission_id", "receipt_id",
            "receipt_contract_version", "ep_application_version", "producer_readback_contract_version",
            "accepted_request_digest",
        }
        contract = request.producer_contract
        expected = {
            "contract_version": "1.0", "producer_id": contract.producer.identity.id,
            "producer_type": str(contract.producer.identity.type),
            "forge_application_version": contract.producer.identity.version,
            "producer_contract_version": contract.contract_version,
            "forge_provenance_contract_version": self.FORGE_PROVENANCE_CONTRACT_VERSION,
            "action_context_envelope_version": contract.action_context.envelope_version if contract.action_context else None,
            "action_context_generator_id": contract.action_context.generator_id if contract.action_context else None,
            "action_context_generator_model": contract.action_context.generator_model if contract.action_context else None,
            "action_context_generator_version": contract.action_context.generator_version if contract.action_context else None,
            "action_context_summary_digest": contract.action_context.summary_digest if contract.action_context else None,
            "action_context_envelope_digest": contract.action_context.envelope_digest if contract.action_context else None,
            "planning_context_envelope_version": contract.planning_context.envelope_version if contract.planning_context else None,
            "planning_context_envelope_digest": contract.planning_context.envelope_digest if contract.planning_context else None,
            "planning_context_decision_evidence_reference_digest": (
                contract.planning_context.decision_evidence_reference_digest if contract.planning_context else None
            ),
            "repository_revision_binding": binding.get("repository_revision_binding"),
            "repository_revision_binding_digest": binding.get("repository_revision_binding_digest"),
            "submission_payload_digest": binding.get("submission_payload_digest"),
            "correlation_id": request.correlation_id, "ep_project_id": self.config.project_id,
            "ep_repository_id": request.repository_id, "ep_instance_id": self.config.expected_instance_id,
            "submission_id": binding.get("submission_id"), "receipt_contract_version": "1.0",
            "producer_readback_contract_version": self.config.producer_readback_contract,
        }
        if request.repository_revision_binding is None:
            # The older immutable audit fact has no v1.4 constraint digest;
            # retain its original contract shape instead of backfilling it.
            historical_keys = {
                "repository_revision_binding", "repository_revision_binding_digest",
                "submission_payload_digest",
            }
            expected_keys -= historical_keys
            for key in historical_keys:
                expected.pop(key)
        if set(document) != expected_keys or any(document.get(key) != value for key, value in expected.items()):
            raise ValueError("EP persisted submission receipt audit does not bind the submitted Forge envelope")
        receipt_id = document.get("receipt_id")
        ep_version = document.get("ep_application_version")
        digest = document.get("accepted_request_digest")
        if (not isinstance(receipt_id, str) or not receipt_id
                or not isinstance(ep_version, str) or not ep_version
                or not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71
                or any(character not in "0123456789abcdef" for character in digest[7:])):
            raise ValueError("EP persisted submission receipt audit identity is invalid")
        return receipt_id

    @staticmethod
    def _readback_accepted_request_digest(submission: Mapping[str, Any]) -> str:
        digest = submission.get("accepted_request_digest")
        if (not isinstance(digest, str) or not digest.startswith("sha256:") or len(digest) != 71
                or any(character not in "0123456789abcdef" for character in digest[7:])):
            raise ValueError("EP readback accepted-request digest is invalid")
        return digest

    def _validate_readback(
        self,
        request: ExecutionRequest,
        binding: Mapping[str, Any],
        readback: Mapping[str, Any],
        *,
        host_retry_successor: bool = False,
    ) -> None:
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
        accepted_request_digest = self._readback_accepted_request_digest(submission)
        # Forge can recompute only the request it submitted.  An EP-owned,
        # explicitly parent-bound operator retry is a distinct accepted
        # attempt and therefore has its own digest.  Its remaining request
        # identity is still checked below and its digest must agree with the
        # immutable terminal artifact before evidence can be returned.
        if (request.repository_revision_binding is not None and not host_retry_successor
                and accepted_request_digest != self._expected_ep_accepted_request_digest(request)):
            raise ValueError("EP readback accepted-request digest does not bind persisted request")
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
        action_context = request.producer_contract.action_context
        if action_context is None or provenance.get("action_context_envelope") != action_context.to_dict():
            raise ValueError("EP readback Action context does not bind persisted request")
        planning_context = request.producer_contract.planning_context
        if planning_context is None or provenance.get("planning_context_envelope") != planning_context.to_dict():
            raise ValueError("EP readback planning context does not bind persisted request")

    def preflight(self) -> dict[str, Any]:
        """Verify EP identity and v1.2 support without submitting anything."""
        declaration = self._json("/v1/producer-compatibility")
        if set(declaration) != self._COMPATIBILITY_KEYS or declaration.get("contract_version") != "1.1":
            raise ValueError("EP_CAPABILITY_DECLARATION_MALFORMED")
        producer, instance, contracts = declaration.get("producer"), declaration.get("instance"), declaration.get("contracts")
        authentication = declaration.get("authentication")
        if (not isinstance(producer, Mapping) or set(producer) != {"id", "version"}
                or producer.get("id") != "engineering-platform"
                or not isinstance(producer.get("version"), str) or not producer["version"]
                or not isinstance(instance, Mapping) or set(instance) != {"id"}
                or not isinstance(instance.get("id"), str) or not instance["id"]
                or not isinstance(contracts, Mapping)
                or not {"producer_readback", "terminal_evidence"}.issubset(contracts)
                or not set(contracts).issubset({
                    "producer_readback", "terminal_evidence", "validation_controls",
                    "delivery_revision_validation", "bounded_merge_delegation",
                })
                or not isinstance(authentication, Mapping)
                or set(authentication) != {
                    "consumer_id", "consumer_status", "project_id", "project_status",
                    "repository_id", "repository_role", "local_repository_binding",
                    "submission_authorization",
                }):
            raise ValueError("EP_CAPABILITY_DECLARATION_MALFORMED")
        if instance["id"] != self.config.expected_instance_id:
            raise ValueError("EP_INSTANCE_IDENTITY_MISMATCH")
        if authentication.get("consumer_id") != self.config.expected_consumer_id:
            raise ValueError("EP_AUTHENTICATED_CONSUMER_IDENTITY_MISMATCH")
        if (
            authentication.get("consumer_status") != "ACTIVE"
            or authentication.get("project_id") != self.config.project_id
            or authentication.get("project_status") != "ACTIVE"
            or authentication.get("repository_id") != self.config.repository_id
            or authentication.get("repository_role") != "authority"
            or authentication.get("local_repository_binding") != "BOUND"
            or authentication.get("submission_authorization") != "AUTHORIZED"
        ):
            raise ValueError("EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH")
        versions = contracts.get("producer_readback")
        if (not isinstance(versions, list) or not versions
                or len(versions) != len(set(versions))
                or self.config.producer_readback_contract not in versions
                or any(version not in self.SUPPORTED_PRODUCER_READBACK_CONTRACTS for version in versions)):
            raise ValueError("EP_READBACK_CONTRACT_INCOMPATIBLE")
        terminal_versions = contracts.get("terminal_evidence")
        if not isinstance(terminal_versions, list) or terminal_versions != [self.config.terminal_evidence_contract]:
            raise ValueError("EP_TERMINAL_CONTRACT_INCOMPATIBLE")
        if ("validation_controls" in contracts
                and contracts["validation_controls"] not in (["1.0"], ["1.0", "1.1"])):
            raise ValueError("EP_CAPABILITY_DECLARATION_MALFORMED")
        for capability in ("delivery_revision_validation", "bounded_merge_delegation"):
            if capability in contracts and contracts[capability] != ["1.0"]:
                raise ValueError("EP_CAPABILITY_DECLARATION_MALFORMED")
        return declaration

    def managed_workspace_readiness(self) -> dict[str, Any]:
        """Read EP's current Managed workspace capability without submission."""
        document = self._json(
            f"/v1/projects/{self._segment(self.config.project_id)}/managed-workspace-readiness"
        )
        required = {
            "contract_version", "project_id", "repository_id", "managed_workspace_id",
            "execution_mode", "repository_identity", "origin", "head_sha", "branch",
            "clean", "busy", "active_lease", "preparation_capability", "status",
            "known_blocker", "observed_at",
        }
        if (set(document) != required or document["contract_version"] != "1.0"
                or document["project_id"] != self.config.project_id
                or document["repository_id"] != self.config.repository_id
                or document["execution_mode"] != "MANAGED"
                or ("/" in self.config.repository_identity
                    and document["repository_identity"] != self.config.repository_identity)
                or document["preparation_capability"] != "EXACT_MAIN_FAST_FORWARD_V1"):
            raise ValueError("EP_MANAGED_WORKSPACE_READINESS_MALFORMED")
        return document

    def merge_delegation_status(self, delegation_id: str) -> dict[str, Any]:
        """Read the authenticated EP-owned grant; this endpoint cannot mutate it."""
        if re.fullmatch(r"[0-9a-f]{32}", delegation_id) is None:
            raise ValueError("EP merge delegation reference is invalid")
        document = self._json(
            f"/v1/projects/{self._segment(self.config.project_id)}/merge-delegations/{delegation_id}"
        )
        expected = {"contract_version", "delegation_id", "actor_reference", "project_id",
                    "repository_id", "github_repository", "mission_id", "mission_revision",
                    "base_branch", "roles", "expires_at", "activated_at", "revoked_at", "status"}
        version = document.get("contract_version")
        if version == "1.1":
            expected |= {"assurance_profile_id", "assurance_profile_revision",
                         "assurance_policy_digest"}
            profile_id = document.get("assurance_profile_id")
            profile_revision = document.get("assurance_profile_revision")
            policy_digest = document.get("assurance_policy_digest")
            if (not isinstance(profile_id, str) or not isinstance(profile_revision, str)
                    or not isinstance(policy_digest, str)
                    or (profile_id == "") != (profile_revision == "")
                    or (profile_id == "") != (policy_digest == "")
                    or (profile_id and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", profile_id) is None)
                    or (profile_revision and re.fullmatch(r"[1-9][0-9]*", profile_revision) is None)
                    or (policy_digest and re.fullmatch(r"sha256:[0-9a-f]{64}", policy_digest) is None)):
                raise ValueError("EP merge delegation assurance profile is malformed")
        if (version not in {"1.0", "1.1"} or set(document) != expected
                or document.get("delegation_id") != delegation_id
                or document.get("project_id") != self.config.project_id
                or document.get("repository_id") != self.config.repository_id):
            raise ValueError("EP merge delegation readback scope differs")
        return document

    def _readback(self, request: ExecutionRequest, binding: Mapping[str, Any]) -> dict[str, Any] | None:
        submission_id = binding.get("submission_id")
        if not isinstance(submission_id, str) or not submission_id:
            return None
        return self._readback_for_submission(request, binding, submission_id)

    def _readback_for_submission(self, request: ExecutionRequest, binding: Mapping[str, Any],
                                 submission_id: str, *, host_retry_successor: bool = False) -> dict[str, Any]:
        readback = self._json(
            f"/v1/projects/{self._segment(self.config.project_id)}/submissions/{self._segment(submission_id)}"
        )
        self._validate_readback(
            request, binding, readback, host_retry_successor=host_retry_successor,
        )
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
            successor = self._readback_for_submission(
                request, binding, successor_id, host_retry_successor=True,
            )
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
        accepted_request_digest = self._readback_accepted_request_digest(submission)
        resolution = {
            "submission_id": submission_id,
            "retry_parent_run_id": resolved_from_host_run_id,
            "run_id": evidence.host_run_id,
            "accepted_request_digest": accepted_request_digest,
        }
        persisted = binding.get("operator_retry_resolution")
        if persisted is not None:
            legacy_resolution = {
                key: value for key, value in resolution.items() if key != "accepted_request_digest"
            }
            if persisted not in (resolution, legacy_resolution):
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
                "accepted_request_digest": accepted_request_digest,
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
            binding = self._bindings.save_execution_host_binding(
                request.correlation_id,
                {"correlation_id": request.correlation_id, "submission_receipt": dict(receipt)},
            )
            self._bindings.record_execution_host_exchange_audit(
                request.correlation_id, direction="EP_TO_FORGE", event_kind="EP_SUBMISSION_RECEIPT_RECEIVED",
                document=self._audit_document(request, binding, receipt=receipt),
            )
            readback = self._readback(request, binding)
        return self._dispatch_from_readback(request, binding, readback)

    def recover_dispatch(self, request: ExecutionRequest) -> ExecutionDispatch | None:
        # A persisted pre-v1.4 correlation is read back exactly as it was
        # stored.  It is never backfilled with the new constraint or retried
        # as a new submission; absent binding storage still fails closed.
        binding = self._binding(request, allow_historical_readback=True)
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
        request, binding = dispatch.request, self._binding(
            dispatch.request, allow_historical_readback=True,
        )
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
            if _terminal_artifact_publication_pending(readback):
                return None
            if (isinstance(run, Mapping) and run.get("terminal") is True
                    or state in {"BLOCKED", "FAILED"} and outcome == state):
                raise ValueError("EP_TERMINAL_WITHOUT_IMMUTABLE_EVIDENCE")
            return None
        raw = self._bytes(
            f"/v1/projects/{self._segment(self.config.project_id)}/artifacts/{self._segment(terminal['id'])}"
        )
        evidence = terminal_evidence(
            readback, raw, host_id=self.config.host_id,
            repository_revision_binding=request.repository_revision_binding,
            resolved_from_host_run_id=resolved_from_host_run_id,
        )
        evidence = replace(evidence, receipt_id=self._submission_receipt_id(request, binding))
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
