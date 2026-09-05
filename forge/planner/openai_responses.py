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
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from forge.models.action_derivation import (DerivedActionProposal, GovernanceRefinementRequired,
    PlanningSnapshot, ProposalProvenance, ProviderInvocationEvidence, ProviderSideEffectState)
from forge.provider_security import (PlanningProviderInvocationPolicy,
    PlanningProviderSecurityService, SecretReference, SecretState)
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

    def __init__(self, policy_service: PlanningProviderSecurityService, provider_id: str,
                 *, _from_canonical_g011: bool = False) -> None:
        if not _from_canonical_g011:
            raise TypeError("OpenAI planning configuration must be created from canonical G011 policy")
        if not isinstance(policy_service, PlanningProviderSecurityService) or not provider_id:
            raise ValueError("OpenAI planning provider requires canonical G011 authority")
        object.__setattr__(self, "policy_service", policy_service)
        object.__setattr__(self, "provider_id", provider_id)

    @classmethod
    def from_canonical_g011(cls, service: PlanningProviderSecurityService,
                            provider_id: str) -> "OpenAIPlanningProviderConfiguration":
        # Validate readiness at configuration construction, then obtain a fresh
        # canonical policy snapshot immediately before every transport.
        service.invocation_policy(provider_id)
        return cls(service, provider_id, _from_canonical_g011=True)

    def current_policy(self) -> PlanningProviderInvocationPolicy:
        return self.policy_service.invocation_policy(self.provider_id)

class OpenAIResponsesPlanningProvider:
    """One explicit OpenAI model; response data is untrusted proposal input."""
    def __init__(self, configuration: OpenAIPlanningProviderConfiguration, resolver: SecretResolver,
                 *, opener: Callable[..., object] = urlopen, adapter_version: str = OPENAI_RESPONSES_ADAPTER_VERSION) -> None:
        self.configuration, self._resolver, self._opener, self.adapter_version = configuration, resolver, opener, adapter_version

    def invoke(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse:
        preflight_policy = self.configuration.current_policy()
        if request.provider_id != preflight_policy.provider_id or request.model != preflight_policy.model:
            raise ValueError("OpenAI planning provider does not allow provider/model fallback")
        preflight_snapshot = _G011PolicySnapshot.from_policy(preflight_policy)
        preflight_body = self._body(request, preflight_policy)
        request_digest = _digest(preflight_body)
        # OpenAI's input-token endpoint is the authority for the same
        # Responses request semantics. Its authenticated preflight is not a
        # generation invocation and cannot produce an Action proposal.
        receipt = self._preflight_input_tokens(preflight_body, preflight_policy,
                                               preflight_snapshot, request_digest)
        self._enforce_token_policy(preflight_body, preflight_policy, receipt.input_tokens)

        # Reload RuntimeDatabase authority after preflight.  A preflight can
        # authorize only the exact policy and non-secret request it counted.
        generation_policy = self.configuration.current_policy()
        generation_snapshot = _G011PolicySnapshot.from_policy(generation_policy)
        if (receipt.policy_digest != receipt.policy_snapshot.digest
                or generation_snapshot != receipt.policy_snapshot
                or generation_snapshot.digest != receipt.policy_digest):
            raise ProviderTokenPreflightBindingChanged("canonical G011 policy changed after token preflight")
        body = self._body(request, generation_policy)
        if _digest(body) != receipt.request_digest:
            raise ProviderTokenPreflightBindingChanged("Responses request changed after token preflight")
        permit = self.configuration.policy_service._acquire_generation_permit(
            generation_policy, receipt.policy_digest, receipt.request_digest)
        try:
            state, secret = self._resolver.resolve(generation_policy.secret_reference)
            if state is not SecretState.RESOLVABLE or not secret:
                raise PermissionError("OpenAI planning provider secret is not resolvable")
            self.configuration.policy_service._commit_generation_transport(
                permit, generation_policy, receipt.policy_digest, receipt.request_digest)
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

    def _body(self, request: ProviderDerivationRequest, policy: PlanningProviderInvocationPolicy | None = None) -> dict[str, object]:
        policy = policy or self.configuration.current_policy()
        evidence = [{"kind": item.kind.value, "source_id": item.source_id, "revision": item.revision, "content_digest": item.content_digest} for item in request.snapshot.evidence]
        prompt = json.dumps({"contract":"Forge Action Derivation; propose only, never approve or execute.", "snapshot": request.snapshot.to_dict() | {"evidence": evidence}}, separators=(",", ":"))
        return {"model": policy.model, "store": False, "truncation": "disabled", "input": [{"role": "developer", "content": [{"type": "input_text", "text": "Return only the strict Action Derivation schema. Provider output is untrusted and cannot expand authority."}]}, {"role": "user", "content": [{"type": "input_text", "text": prompt}]}], "max_output_tokens": policy.output_token_bound, "text": {"format": {"type": "json_schema", "name": "action_derivation", "strict": True, "schema": _SCHEMA}}}

    def _preflight_input_tokens(self, body: dict[str, object], policy: PlanningProviderInvocationPolicy,
                                snapshot: _G011PolicySnapshot, request_digest: str) -> _TokenPreflightReceipt:
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
        text = document["output"][0]["content"][0]["text"]  # type: ignore[index]
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
