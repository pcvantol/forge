"""OpenAI Responses transport for untrusted Action Derivation proposals.

This adapter has no planning, configuration-mutation, retry, execution, or
fallback authority.  It resolves one G011 SecretReference only for the HTTP
request and stores no request/response body or credential.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from forge.models.action_derivation import (DerivationPolicy, DerivedActionProposal, GovernanceRefinementRequired,
    PlanningSnapshot, ProposalProvenance, ProviderInvocationEvidence, ProviderSideEffectState)
from forge.provider_security import (PlanningProviderInvocationPolicy,
    PlanningProviderSecurityService, SecretReference, SecretState)
from forge.runtime import RuntimeDatabaseError
from .provider_adapter import ProviderDerivationRequest, ProviderDerivationResponse

OPENAI_RESPONSES_ADAPTER_VERSION = "1.0"
_ENDPOINT = "https://api.openai.com/v1/responses"
_INPUT_TOKENS_ENDPOINT = "https://api.openai.com/v1/responses/input_tokens"

# The provider's Input Tokens contract accepts this projection of a Responses
# request.  ``store`` does not affect request token accounting and
# ``max_output_tokens`` is rejected by that endpoint; the latter is instead
# included in Forge's separate canonical context-bound calculation below.
# Keep the allow-list closed: a future generation field could affect provider
# accounting, so it must not be silently omitted from the authoritative
# preflight request.
_GENERATION_REQUEST_FIELDS = frozenset((
    "model", "store", "truncation", "input", "max_output_tokens", "text",
))
_INPUT_TOKEN_REQUEST_FIELDS = frozenset(("model", "truncation", "input", "text"))
_PERSISTABLE_PREFLIGHT_ERROR_TYPES = frozenset((
    "invalid_request_error", "authentication_error", "permission_error", "rate_limit_error", "server_error",
))
_PERSISTABLE_PREFLIGHT_ERROR_CODES = frozenset((
    "unsupported_parameter", "invalid_parameter", "invalid_value", "invalid_schema", "invalid_json_schema", "model_not_found",
    "rate_limit_exceeded", "insufficient_quota", "server_error",
))
_PERSISTABLE_REQUEST_ID = re.compile(r"req_[A-Za-z0-9]{1,128}\Z")
_PERSISTABLE_TRANSPORT_KINDS = frozenset((
    "ConnectionRefusedError", "ConnectionResetError", "ConnectionAbortedError", "TimeoutError", "OSError", "gaierror",
))
_DEPENDENCY_CONTRACT_INSTRUCTION = (
    "Each dependencies item must exactly equal the logical_action_id of another proposal in the same "
    "proposals array. Use an empty dependencies array when no such proposal exists; never use a scope, "
    "capability, evidence reference, or undeclared label as a dependency."
)

class ProviderSubmissionAmbiguous(RuntimeError):
    """The request may have reached OpenAI; operator reconciliation is required."""

class ProviderTokenPreflightFailed(RuntimeError):
    """Provider-authoritative token preflight did not yield a usable count."""

    def __init__(self, message: str, *, status: int | None = None,
                 provider_type: str | None = None, provider_code: str | None = None,
                 request_id: str | None = None, layer: str = "OTHER",
                 transport_kind: str | None = None, transport_errno: int | None = None) -> None:
        super().__init__(message)
        # This is deliberately bounded diagnostic metadata, never a request,
        # response body, header value, or credential.
        self.status = status
        self.provider_type = provider_type
        self.provider_code = provider_code
        self.request_id = request_id
        self.layer = layer
        self.transport_kind = transport_kind
        self.transport_errno = transport_errno

class ProviderTokenPreflightBindingChanged(RuntimeError):
    """Canonical policy or request changed after token preflight."""

class SecretResolver(Protocol):
    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]: ...

@dataclass(frozen=True)
class _G011PolicySnapshot:
    """Redacted, immutable authority snapshot bound to one token preflight."""
    provider_id: str
    version: int
    enabled: bool
    model: str
    secret_reference_fingerprint: str
    timeout_seconds: int
    input_token_bound: int
    context_token_bound: int
    output_token_bound: int

    @classmethod
    def from_policy(cls, policy: PlanningProviderInvocationPolicy) -> "_G011PolicySnapshot":
        return cls(policy.provider_id, policy.version, True, policy.model,
                   policy.secret_reference.fingerprint, policy.timeout_seconds,
                   policy.input_token_bound, policy.context_token_bound,
                   policy.output_token_bound)

    @property
    def digest(self) -> str:
        return _digest({"provider_id": self.provider_id, "version": self.version,
                        "enabled": self.enabled, "model": self.model,
                        "secret_reference_fingerprint": self.secret_reference_fingerprint,
                        "timeout_seconds": self.timeout_seconds,
                        "input_token_bound": self.input_token_bound,
                        "context_token_bound": self.context_token_bound,
                        "output_token_bound": self.output_token_bound})

@dataclass(frozen=True)
class TokenPreflightBoundary:
    """Runtime-derived, non-secret bindings that make one token count reusable once."""
    main_head: str
    evidence_digest: str
    effective_contract_digest: str

    def values(self, *, policy_digest: str, request_digest: str) -> dict[str, str]:
        result = {"main_head": self.main_head, "policy_digest": policy_digest,
                  "request_digest": request_digest, "evidence_digest": self.evidence_digest,
                  "effective_contract_digest": self.effective_contract_digest}
        if any(not isinstance(value, str) or not value for value in result.values()):
            raise ValueError("complete canonical token-preflight boundary is required")
        return result

class CanonicalTokenPreflightAuthority:
    """Read-only resolver for the canonical generation boundary.

    The adapter never accepts these values from its caller.  This resolver
    obtains the head, existing pinned evidence, and Mission amendment lineage
    directly from the canonical RuntimeDatabase and repository.
    """
    def __init__(self, database, *, _head_reader: Callable[[Path], str] | None = None,
                 _boundary_reader: Callable[[str], TokenPreflightBoundary] | None = None,
                 _scope_reader: Callable[[str], tuple[str, ...]] | None = None,
                 _policy_reader: Callable[[str], tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] | None = None) -> None:
        self._database = database
        self._head_reader = _head_reader or _origin_main_head
        self._boundary_reader = _boundary_reader
        self._scope_reader = _scope_reader
        self._policy_reader = _policy_reader

    @classmethod
    def _for_test(cls, database, boundary_reader: Callable[[str], TokenPreflightBoundary],
                  scope_reader: Callable[[str], tuple[str, ...]],
                  policy_reader: Callable[[str], tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]]) -> "CanonicalTokenPreflightAuthority":
        return cls(database, _boundary_reader=boundary_reader, _scope_reader=scope_reader,
                   _policy_reader=policy_reader)

    def approved_scopes_for(self, mission_id: str) -> tuple[str, ...]:
        if self._scope_reader is not None:
            return self._scope_reader(mission_id)
        state = self._database.get_document("mission_state", mission_id)
        contract = state.get("admission_contract")
        mission = contract.get("mission") if isinstance(contract, dict) else None
        scopes = mission.get("scope") if isinstance(mission, dict) else None
        if state.get("status") != "APPROVED_PLANNABLE" or not isinstance(scopes, list):
            raise PermissionError("canonical approved Mission scopes are unavailable")
        resolved = tuple(sorted(set(scope for scope in scopes if isinstance(scope, str) and scope)))
        if not resolved or len(resolved) != len(scopes):
            raise PermissionError("canonical approved Mission scopes are invalid")
        return resolved

    def approved_derivation_policy_for(self, mission_id: str) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """Return only the persisted no-write derivation constraints for a Mission."""
        if self._policy_reader is not None:
            return self._policy_reader(mission_id)
        state = self._database.get_document("mission_state", mission_id)
        contract = state.get("admission_contract")
        planning = contract.get("planning") if isinstance(contract, dict) else None
        if state.get("status") != "APPROVED_PLANNABLE" or not isinstance(planning, dict):
            raise PermissionError("canonical approved Mission derivation policy is unavailable")
        raw_values = tuple(planning.get(field) for field in ("write_scopes", "human_gates", "risk_inputs"))
        if any(not isinstance(items, list) for items in raw_values):
            raise PermissionError("canonical approved Mission derivation policy is invalid")
        values = tuple(tuple(sorted(set(item for item in items if isinstance(item, str) and item)))
                       for items in raw_values)
        if any(not item for item in values) or any(len(item) != len(items)
                                                    for item, items in zip(values, raw_values)):
            raise PermissionError("canonical approved Mission derivation policy is invalid")
        if values[0] != ("NONE",):
            raise PermissionError("provider Action Derivation supports only canonical NONE write scope")
        return values

    def boundary_for(self, mission_id: str) -> TokenPreflightBoundary:
        if self._boundary_reader is not None:
            return self._boundary_reader(mission_id)
        state = self._database.get_document("mission_state", mission_id)
        if state.get("status") != "APPROVED_PLANNABLE":
            raise PermissionError("canonical Mission is not approved/plannable")
        evidence_row = self._database._connection.execute(
            "SELECT digest, document FROM action_derivation_evidence_sets WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if evidence_row is None:
            raise PermissionError("canonical Action-Derivation evidence is missing")
        evidence = json.loads(evidence_row["document"])
        if evidence.get("mission_id") != mission_id or evidence.get("digest") != evidence_row["digest"]:
            raise PermissionError("canonical Action-Derivation evidence is inconsistent")
        contract = state.get("admission_contract")
        if not isinstance(contract, dict):
            raise PermissionError("canonical Mission admission contract is missing")
        predecessor = _canonical_digest(contract)
        rows = self._database._connection.execute(
            "SELECT document FROM mission_amendments WHERE mission_id=? ORDER BY revision", (mission_id,)
        ).fetchall()
        for row in rows:
            amendment = json.loads(row["document"])
            if amendment.get("predecessor_digest") != predecessor:
                raise PermissionError("canonical Mission amendment lineage is stale or conflicting")
            predecessor = amendment.get("effective_contract_digest")
            if not isinstance(predecessor, str) or not predecessor.startswith("sha256:"):
                raise PermissionError("canonical Mission amendment digest is invalid")
        return TokenPreflightBoundary(self._head_reader(self._database.repository_root),
                                      str(evidence_row["digest"]), predecessor)

@dataclass(frozen=True)
class _TokenPreflightReceipt:
    policy_snapshot: _G011PolicySnapshot
    policy_digest: str
    request_digest: str
    input_tokens: int

@dataclass(frozen=True, init=False)
class OpenAIPlanningProviderConfiguration:
    """Adapter configuration that can only be built from canonical G011 policy."""
    policy_service: PlanningProviderSecurityService
    provider_id: str
    preflight_authority: CanonicalTokenPreflightAuthority

    def __init__(self, policy_service: PlanningProviderSecurityService, provider_id: str,
                 *, _from_canonical_g011: bool = False,
                 _preflight_authority: CanonicalTokenPreflightAuthority | None = None) -> None:
        if not _from_canonical_g011:
            raise TypeError("OpenAI planning configuration must be created from canonical G011 policy")
        if not isinstance(policy_service, PlanningProviderSecurityService) or not provider_id:
            raise ValueError("OpenAI planning provider requires canonical G011 authority")
        object.__setattr__(self, "policy_service", policy_service)
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "preflight_authority", _preflight_authority or CanonicalTokenPreflightAuthority(policy_service.db))

    @classmethod
    def from_canonical_g011(cls, service: PlanningProviderSecurityService,
                            provider_id: str) -> "OpenAIPlanningProviderConfiguration":
        # Validate readiness at configuration construction, then obtain a fresh
        # canonical policy snapshot immediately before every transport.
        service.invocation_policy(provider_id)
        return cls(service, provider_id, _from_canonical_g011=True)

    @classmethod
    def _for_test(cls, service: PlanningProviderSecurityService, provider_id: str,
                  authority: CanonicalTokenPreflightAuthority) -> "OpenAIPlanningProviderConfiguration":
        """Explicit isolated-fixture seam; production always resolves canonical state."""
        return cls(service, provider_id, _from_canonical_g011=True, _preflight_authority=authority)

    def current_policy(self) -> PlanningProviderInvocationPolicy:
        return self.policy_service.invocation_policy(self.provider_id)

class OpenAIResponsesPlanningProvider:
    """One explicit OpenAI model; response data is untrusted proposal input."""
    def __init__(self, configuration: OpenAIPlanningProviderConfiguration, resolver: SecretResolver,
                 *, opener: Callable[..., object] = urlopen, adapter_version: str = OPENAI_RESPONSES_ADAPTER_VERSION) -> None:
        self.configuration, self._resolver, self._opener, self.adapter_version = configuration, resolver, opener, adapter_version

    def preflight(self, request: ProviderDerivationRequest, *, operator_context) -> dict[str, object]:
        """Run one explicit provider count and durably record its PASS result.

        This performs no generation transport.  A subsequent generation is
        possible only through :meth:`invoke` with this exact persisted receipt.
        """
        if not self.configuration.policy_service.operator_service.authorize(operator_context):
            raise PermissionError("trusted operator authorization is required for provider token preflight")
        boundary = self.configuration.preflight_authority.boundary_for(request.snapshot.mission_id)
        preflight_policy = self.configuration.current_policy()
        if request.provider_id != preflight_policy.provider_id or request.model != preflight_policy.model:
            raise ValueError("OpenAI planning provider does not allow provider/model fallback")
        preflight_snapshot = _G011PolicySnapshot.from_policy(preflight_policy)
        preflight_body = self._body(request, preflight_policy)
        request_digest = _digest(preflight_body)
        # OpenAI's input-token endpoint is the authority for the same
        # Responses request semantics. Its authenticated preflight is not a
        # generation invocation and cannot produce an Action proposal.
        try:
            receipt = self._preflight_input_tokens(preflight_body, preflight_policy,
                                                   preflight_snapshot, request_digest)
        except ProviderTokenPreflightFailed as error:
            self._record_preflight_failure(request.snapshot.mission_id, preflight_policy.provider_id,
                                           boundary, preflight_snapshot.digest, request_digest, error)
            raise
        self._enforce_token_policy(preflight_body, preflight_policy, receipt.input_tokens)
        bindings = boundary.values(policy_digest=receipt.policy_digest, request_digest=receipt.request_digest)
        persisted = {"receipt_id": f"token-preflight-{uuid.uuid4()}", "mission_id": request.snapshot.mission_id,
                     **bindings, "provider_id": preflight_policy.provider_id,
                     "input_tokens": receipt.input_tokens,
                     "input_token_bound": preflight_policy.input_token_bound,
                     "context_token_bound": preflight_policy.context_token_bound,
                     "output_token_bound": preflight_policy.output_token_bound,
                     "context_with_requested_output": receipt.input_tokens + preflight_policy.output_token_bound,
                     "result": "PASS", "created_at": _now()}
        return self.configuration.policy_service.db.create_token_preflight_receipt(persisted)

    def _record_preflight_failure(self, mission_id: str, provider_id: str, boundary: TokenPreflightBoundary,
                                  policy_digest: str, request_digest: str,
                                  error: ProviderTokenPreflightFailed) -> None:
        """Record only bounded error classification; never provider text or credentials."""
        self.configuration.policy_service.db.record_token_preflight_failure({
            "failure_id": f"token-preflight-failure-{uuid.uuid4()}", "mission_id": mission_id,
            "provider_id": provider_id, **boundary.values(policy_digest=policy_digest, request_digest=request_digest),
            "layer": error.layer, "status": error.status,
            "provider_type": error.provider_type if error.provider_type in _PERSISTABLE_PREFLIGHT_ERROR_TYPES else None,
            "provider_code": error.provider_code if error.provider_code in _PERSISTABLE_PREFLIGHT_ERROR_CODES else None,
            "request_id": error.request_id if isinstance(error.request_id, str) and _PERSISTABLE_REQUEST_ID.fullmatch(error.request_id) else None,
            "transport_kind": error.transport_kind if error.transport_kind in _PERSISTABLE_TRANSPORT_KINDS else None,
            "transport_errno": error.transport_errno,
            "occurred_at": _now(),
        })

    def invoke(self, request: ProviderDerivationRequest, *, receipt_id: str) -> ProviderDerivationResponse:
        """Generate once from an atomically consumed, exact PASS receipt.

        There is intentionally no preflight fallback here: a missing, stale,
        failed, or already consumed receipt denies generation before secrets or
        generation transport are touched.
        """
        boundary = self.configuration.preflight_authority.boundary_for(request.snapshot.mission_id)
        generation_policy = self.configuration.current_policy()
        if request.provider_id != generation_policy.provider_id or request.model != generation_policy.model:
            raise ValueError("OpenAI planning provider does not allow provider/model fallback")
        generation_snapshot = _G011PolicySnapshot.from_policy(generation_policy)
        body = self._body(request, generation_policy)
        # Also fail closed if a future request field lacks a documented count
        # projection.  No local estimate or implicit provider fallback exists.
        _input_token_request_body(body)
        policy_digest, request_digest = generation_snapshot.digest, _digest(body)
        bindings = boundary.values(policy_digest=policy_digest, request_digest=request_digest)
        try:
            persisted = self.configuration.policy_service.db.consume_token_preflight_receipt(receipt_id, bindings)
        except RuntimeDatabaseError as error:
            raise ProviderTokenPreflightBindingChanged("persisted token-preflight receipt is missing, stale, or consumed") from error
        if (persisted.get("mission_id") != request.snapshot.mission_id
                or persisted.get("provider_id") != generation_policy.provider_id
                or persisted.get("input_token_bound") != generation_policy.input_token_bound
                or persisted.get("context_token_bound") != generation_policy.context_token_bound
                or persisted.get("output_token_bound") != generation_policy.output_token_bound):
            raise ProviderTokenPreflightBindingChanged("persisted token-preflight receipt does not bind generation authority")

        permit = self.configuration.policy_service._acquire_generation_permit(
            generation_policy, policy_digest, request_digest)
        try:
            state, secret = self._resolver.resolve(generation_policy.secret_reference)
            if state is not SecretState.RESOLVABLE or not secret:
                raise PermissionError("OpenAI planning provider secret is not resolvable")
            self.configuration.policy_service._commit_generation_transport(
                permit, generation_policy, policy_digest, request_digest)
            started = _now()
            try:
                http_request = Request(_ENDPOINT, data=json.dumps(body, separators=(",", ":")).encode(), headers={
                    "Authorization": "Bearer " + secret, "Content-Type": "application/json"}, method="POST")
                with self._opener(http_request, timeout=generation_policy.timeout_seconds) as response:
                    document = json.loads(response.read().decode("utf-8"))
            except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
                # A request may have reached the provider; never retry automatically.
                raise ProviderSubmissionAmbiguous("OpenAI submission may have happened; automatic retry is forbidden") from None
        finally:
            secret = None
            self.configuration.policy_service._release_generation_permit(permit)
        try:
            proposals, refinement = self._parse(request, document)
            return ProviderDerivationResponse(self._evidence(request, document, ProviderSideEffectState.HAPPENED_AND_CONFIRMED, started, str(document.get("status", "completed"))), proposals=proposals, governance_refinement=refinement)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            # A confirmed invalid response is never passed to deterministic validation.
            return ProviderDerivationResponse(self._evidence(request, document, ProviderSideEffectState.HAPPENED_AND_CONFIRMED, started, "contract_invalid"), governance_refinement=_refinement(request.snapshot, "provider structured output was invalid"))

    def reconcile(self, request: ProviderDerivationRequest) -> ProviderSideEffectState:
        return ProviderSideEffectState.MAY_HAVE_HAPPENED

    def invoke_and_validate(self, request: ProviderDerivationRequest, *, receipt_id: str,
                            governance_repository):
        """Perform the one permitted generation and its canonical non-executing validation boundary."""
        database = self.configuration.policy_service.db
        policy_digest = _G011PolicySnapshot.from_policy(self.configuration.current_policy()).digest
        existing = database._connection.execute(
            "SELECT 1 FROM action_derivations WHERE derivation_id=? OR "
            "(mission_id=? AND snapshot_digest=? AND contract_version='1.0' AND provider_configuration=?)",
            (request.derivation_id, request.snapshot.mission_id, request.snapshot.digest, policy_digest),
        ).fetchone()
        if existing is not None:
            raise PermissionError("canonical Action Derivation identity is already resolved")
        response = self.invoke(request, receipt_id=receipt_id)
        return self._validate_and_record(request, response, receipt_id=receipt_id,
                                         governance_repository=governance_repository)

    def _validate_and_record(self, request: ProviderDerivationRequest, response: ProviderDerivationResponse,
                             *, receipt_id: str, governance_repository):
        """Validate one confirmed response against canonical state and record only a bounded rejection.

        This post-generation boundary deliberately has no materialization or
        execution capability.  It accepts neither caller-provided digests nor
        a caller-selected database: every binding is re-derived from the
        canonical RuntimeDatabase and the consumed generation receipt.
        """
        from forge.action_derivation_evidence import CanonicalActionDerivationEvidenceProducer
        from forge.planner.action_derivation import (ActionDerivationValidator, ProposalValidationError,
                                                      _record_deterministic_validation_failure,
                                                      _record_deterministic_validation_success)

        database = self.configuration.policy_service.db
        if governance_repository.database is not database:
            raise PermissionError("canonical governance repository must own the provider RuntimeDatabase")
        receipt = database.consumed_token_preflight_receipt(receipt_id)
        policy = self.configuration.current_policy()
        snapshot = _G011PolicySnapshot.from_policy(policy)
        body = self._body(request, policy)
        boundary = self.configuration.preflight_authority.boundary_for(request.snapshot.mission_id)
        expected = boundary.values(policy_digest=snapshot.digest, request_digest=_digest(body))
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ProviderTokenPreflightBindingChanged("consumed receipt no longer binds canonical validation")
        producer = CanonicalActionDerivationEvidenceProducer(database, governance_repository)
        planning_input = producer.planner_input(request.snapshot.mission_id)
        if request.snapshot != PlanningSnapshot.from_planner_input(planning_input):
            raise ProviderTokenPreflightBindingChanged("canonical planning input no longer binds generation snapshot")
        if response.evidence.request_digest != request.digest or response.evidence.snapshot_digest != request.snapshot.digest:
            raise PermissionError("provider result does not bind the canonical generation request")
        result_digest = response.evidence.result_digest
        if not isinstance(result_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", result_digest):
            raise PermissionError("provider result lacks a bounded canonical result digest")
        if response.proposals is None:
            return response.governance_refinement
        write_scopes, human_gates, risk_inputs = self.configuration.preflight_authority.approved_derivation_policy_for(request.snapshot.mission_id)
        try:
            validated = ActionDerivationValidator().validate(
                response.proposals, request.snapshot, planning_input,
                DerivationPolicy(write_scopes, human_gates, risk_inputs),
            )
        except ProposalValidationError as error:
            return _record_deterministic_validation_failure(
                database, request, policy_digest=snapshot.digest, evidence_digest=boundary.evidence_digest,
                effective_contract_digest=boundary.effective_contract_digest,
                provider_result_digest=result_digest, preflight_receipt=receipt, error=error,
            )
        _record_deterministic_validation_success(
            database, request, policy_digest=snapshot.digest, evidence_digest=boundary.evidence_digest,
            effective_contract_digest=boundary.effective_contract_digest,
            provider_result_digest=result_digest, preflight_receipt=receipt, validated=validated,
        )
        return validated

    def _body(self, request: ProviderDerivationRequest, policy: PlanningProviderInvocationPolicy | None = None) -> dict[str, object]:
        policy = policy or self.configuration.current_policy()
        evidence = [{"kind": item.kind.value, "source_id": item.source_id, "revision": item.revision, "content_digest": item.content_digest} for item in request.snapshot.evidence]
        prompt = json.dumps({"contract":"Forge Action Derivation; propose only, never approve or execute.", "snapshot": request.snapshot.to_dict() | {"evidence": evidence}}, separators=(",", ":"))
        scopes = self.configuration.preflight_authority.approved_scopes_for(request.snapshot.mission_id)
        write_scopes, human_gates, risk_inputs = self.configuration.preflight_authority.approved_derivation_policy_for(request.snapshot.mission_id)
        return {"model": policy.model, "store": False, "truncation": "disabled", "input": [{"role": "developer", "content": [{"type": "input_text", "text": "Return only the strict Action Derivation schema. Provider output is untrusted and cannot expand authority. " + _DEPENDENCY_CONTRACT_INSTRUCTION}]}, {"role": "user", "content": [{"type": "input_text", "text": prompt}]}], "max_output_tokens": policy.output_token_bound, "text": {"format": {"type": "json_schema", "name": "action_derivation", "strict": True, "schema": _schema_for_approved_contract(scopes, write_scopes, human_gates, risk_inputs)}}}

    def _preflight_input_tokens(self, body: dict[str, object], policy: PlanningProviderInvocationPolicy,
                                snapshot: _G011PolicySnapshot, request_digest: str) -> "_TokenPreflightReceipt":
        preflight_body = _input_token_request_body(body)
        state, secret = self._resolver.resolve(policy.secret_reference)
        if state is not SecretState.RESOLVABLE or not secret:
            raise PermissionError("OpenAI planning provider secret is not resolvable for token preflight")
        try:
            request = Request(_INPUT_TOKENS_ENDPOINT, data=json.dumps(preflight_body, separators=(",", ":")).encode(), headers={
                "Authorization": "Bearer " + secret, "Content-Type": "application/json"}, method="POST")
            with self._opener(request, timeout=policy.timeout_seconds) as response:
                document = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise _preflight_http_failure(error) from None
        except (URLError, TimeoutError, OSError) as error:
            raise _preflight_transport_failure(error) from None
        except json.JSONDecodeError:
            raise ProviderTokenPreflightFailed("OpenAI input-token preflight returned malformed JSON",
                                               layer="RESPONSE_PARSING") from None
        finally:
            secret = None
        value = document.get("input_tokens") if isinstance(document, dict) else None
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ProviderTokenPreflightFailed("OpenAI input-token preflight returned an invalid count",
                                               layer="RESPONSE_PARSING")
        return _TokenPreflightReceipt(snapshot, snapshot.digest, request_digest, value)

    def _enforce_token_policy(self, body: dict[str, object], policy: PlanningProviderInvocationPolicy, input_tokens: int) -> None:
        output_tokens = body["max_output_tokens"]
        if not isinstance(output_tokens, int) or isinstance(output_tokens, bool) or output_tokens > policy.output_token_bound:
            raise ValueError("requested output exceeds canonical G011 output token bound")
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool) or input_tokens < 0:
            raise ProviderTokenPreflightFailed("OpenAI input-token preflight returned an invalid count",
                                               layer="RESPONSE_PARSING")
        if input_tokens > policy.input_token_bound:
            raise ValueError("bounded planning evidence exceeds canonical G011 input token bound")
        if input_tokens + output_tokens > policy.context_token_bound:
            raise ValueError("bounded planning request exceeds canonical G011 context token bound")

    def _parse(self, request: ProviderDerivationRequest, document: dict[str, object]) -> tuple[tuple[DerivedActionProposal, ...] | None, GovernanceRefinementRequired | None]:
        if document.get("status") != "completed": raise ValueError("response was not completed")
        text = _structured_output_text(document)
        parsed = json.loads(text)
        if parsed.get("kind") == "governance_refinement":
            return None, _refinement(request.snapshot, str(parsed["reason"]))
        items = parsed["proposals"]
        if not isinstance(items, list) or not items: raise ValueError("missing proposals")
        proposals = tuple(DerivedActionProposal(str(item["logical_action_id"]), str(item["scope"]), str(item["objective"]), tuple(item["dependencies"]), tuple(item["write_scopes"]), tuple(item["expected_evidence"]), tuple(item["validation_strategy"]), int(item["priority"]), bool(item["postponed"]), tuple(item["human_gates"]), tuple(item["risk_inputs"]), ProposalProvenance(request.derivation_id, request.snapshot.id, request.snapshot.digest, self.adapter_version, request.provider_id, request.model, tuple(item["source_evidence_refs"]))) for item in items)
        return proposals, None

    def _evidence(self, request, document, state, started, status):
        usage = document.get("usage", {}) if isinstance(document, dict) else {}
        return ProviderInvocationEvidence(request.provider_id, request.model, self.adapter_version, request.digest, request.snapshot.digest, _digest(document) if document else None, state, str(document.get("id")) if isinstance(document, dict) and document.get("id") else None, started, _now(), status, int(usage.get("input_tokens", 0)) if isinstance(usage, dict) else None, int(usage.get("output_tokens", 0)) if isinstance(usage, dict) else None)

def _digest(value: object) -> str: return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def _canonical_digest(value: object) -> str: return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def _structured_output_text(document: dict[str, object]) -> str:
    """Extract exactly one strict output-text part from a Responses result.

    Responses may place non-message output (for example reasoning) before the
    final message.  It is never valid to assume that array position zero is
    the schema-bearing message; conversely, multiple text parts are rejected
    rather than concatenated into a new, unvalidated representation.
    """
    output = document.get("output")
    if not isinstance(output, list):
        raise ValueError("response output is missing")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") not in (None, "message"):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if part.get("type") in (None, "output_text") and isinstance(text, str):
                texts.append(text)
    if len(texts) != 1:
        raise ValueError("response has no unambiguous strict structured output")
    return texts[0]

def _origin_main_head(root: Path) -> str:
    """Resolve the repository's canonical main head; never silently use a branch."""
    try:
        result = subprocess.run(("git", "-C", str(root), "rev-parse", "origin/main"), check=True,
                                capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        raise PermissionError("canonical origin/main head is unavailable for token preflight") from None
    head = result.stdout.strip()
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise PermissionError("canonical origin/main head is invalid for token preflight")
    return head

def _input_token_request_body(generation_body: dict[str, object]) -> dict[str, object]:
    """Project one known Responses request into the documented count endpoint.

    This is not a local token estimate.  The provider receives every field
    that can affect its input-token accounting, including the strict output
    schema.  Unsupported output/persistence controls are deliberately absent.
    """
    if set(generation_body) != _GENERATION_REQUEST_FIELDS:
        raise ValueError("Responses request cannot be bound to the token-count preflight contract")
    return {key: generation_body[key] for key in sorted(_INPUT_TOKEN_REQUEST_FIELDS)}

def _preflight_http_failure(error: HTTPError) -> ProviderTokenPreflightFailed:
    """Classify a provider rejection without retaining its body or credentials."""
    provider_type = provider_code = None
    request_id = error.headers.get("x-request-id") if error.headers else None
    try:
        # The documented error envelope carries a small error object.  Read at
        # most 4 KiB and retain only its type/code fields; a provider message
        # can contain request-derived material and is intentionally discarded.
        raw = error.read(4096)
        document = json.loads(raw.decode("utf-8"))
        details = document.get("error") if isinstance(document, dict) else None
        if isinstance(details, dict):
            candidate_type, candidate_code = details.get("type"), details.get("code")
            provider_type = candidate_type if isinstance(candidate_type, str) and len(candidate_type) <= 128 else None
            provider_code = candidate_code if isinstance(candidate_code, str) and len(candidate_code) <= 128 else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    finally:
        error.close()
    if not isinstance(request_id, str) or len(request_id) > 256:
        request_id = None
    return ProviderTokenPreflightFailed("OpenAI input-token preflight was rejected", status=error.code,
                                        provider_type=provider_type, provider_code=provider_code,
                                        request_id=request_id, layer="PROVIDER_AVAILABILITY")

def _preflight_transport_failure(error: URLError | TimeoutError | OSError) -> ProviderTokenPreflightFailed:
    """Expose only a bounded transport category, never a URL, header, or secret."""
    reason = error.reason if isinstance(error, URLError) else error
    errno = getattr(reason, "errno", None)
    return ProviderTokenPreflightFailed("OpenAI input-token preflight transport failed", layer="TRANSPORT",
                                        transport_kind=type(reason).__name__,
                                        transport_errno=errno if isinstance(errno, int) else None)
def _now() -> str: return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def _refinement(snapshot, reason): return GovernanceRefinementRequired(tuple(item.source_id for item in snapshot.evidence), "deterministic validation required", "provider-output", "blocked", reason)
_SCHEMA = {"type":"object","additionalProperties":False,"required":["kind","proposals"],"properties":{"kind":{"type":"string","enum":["proposals"]},"proposals":{"type":"array","minItems":1,"items":{"type":"object","additionalProperties":False,"required":["logical_action_id","scope","objective","dependencies","write_scopes","expected_evidence","validation_strategy","priority","postponed","human_gates","risk_inputs","source_evidence_refs"],"properties":{key: ({"type":"boolean"} if key == "postponed" else {"type":"integer","minimum":1} if key == "priority" else {"type":"array","items":{"type":"string"}} if key in {"dependencies","write_scopes","expected_evidence","validation_strategy","human_gates","risk_inputs","source_evidence_refs"} else {"type":"string","minLength":1}) for key in ["logical_action_id","scope","objective","dependencies","write_scopes","expected_evidence","validation_strategy","priority","postponed","human_gates","risk_inputs","source_evidence_refs"]}}}}}

def _schema_for_approved_contract(scopes: tuple[str, ...], write_scopes: tuple[str, ...],
                                  human_gates: tuple[str, ...], risk_inputs: tuple[str, ...]) -> dict[str, object]:
    """Bind strict output to canonical Mission scope and no-write governance constraints."""
    if not scopes or any(not isinstance(scope, str) or not scope for scope in scopes):
        raise ValueError("canonical approved Mission scopes are required")
    if write_scopes != ("NONE",) or not human_gates or not risk_inputs:
        raise ValueError("canonical no-write derivation policy is required")
    schema = json.loads(json.dumps(_SCHEMA))
    properties = schema["properties"]["proposals"]["items"]["properties"]
    properties["scope"] = {
        "type": "string", "enum": list(scopes),
    }
    # ``NONE`` is a governance state, never a provider grant to a write path.
    # Strict Responses schemas model every array with an explicit item schema.
    # ``maxItems: 0`` remains the authority boundary: an item can never occur.
    properties["write_scopes"] = {"type": "array", "items": {"type": "string"}, "maxItems": 0}
    properties["human_gates"] = _required_enum_array(human_gates)
    properties["risk_inputs"] = _required_enum_array(risk_inputs)
    return schema


def _required_enum_array(values: tuple[str, ...]) -> dict[str, object]:
    """Require exactly a finite canonical set using basic strict-schema keywords."""
    if not values or len(values) != len(set(values)) or any(not isinstance(value, str) or not value for value in values):
        raise ValueError("canonical derivation constraint set is invalid")
    return {"type": "array", "items": {"type": "string", "enum": list(values)},
            "minItems": len(values), "maxItems": len(values)}
