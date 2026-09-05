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
from .token_accounting import ModelTokenCounter, TokenCountingUnavailable

OPENAI_RESPONSES_ADAPTER_VERSION = "1.0"
_ENDPOINT = "https://api.openai.com/v1/responses"

class ProviderSubmissionAmbiguous(RuntimeError):
    """The request may have reached OpenAI; operator reconciliation is required."""

class SecretResolver(Protocol):
    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]: ...

@dataclass(frozen=True, init=False)
class OpenAIPlanningProviderConfiguration:
    """Adapter configuration that can only be built from canonical G011 policy."""
    policy_service: PlanningProviderSecurityService
    provider_id: str
    token_counter: ModelTokenCounter

    def __init__(self, policy_service: PlanningProviderSecurityService, provider_id: str,
                 token_counter: ModelTokenCounter, *, _from_canonical_g011: bool = False) -> None:
        if not _from_canonical_g011:
            raise TypeError("OpenAI planning configuration must be created from canonical G011 policy")
        if not isinstance(policy_service, PlanningProviderSecurityService) or not provider_id:
            raise ValueError("OpenAI planning provider requires canonical G011 authority")
        object.__setattr__(self, "policy_service", policy_service)
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "token_counter", token_counter)

    @classmethod
    def from_canonical_g011(cls, service: PlanningProviderSecurityService, provider_id: str,
                            token_counter: ModelTokenCounter) -> "OpenAIPlanningProviderConfiguration":
        # Validate readiness at configuration construction, then obtain a fresh
        # canonical policy snapshot immediately before every transport.
        service.invocation_policy(provider_id)
        return cls(service, provider_id, token_counter, _from_canonical_g011=True)

    def current_policy(self) -> PlanningProviderInvocationPolicy:
        return self.policy_service.invocation_policy(self.provider_id)

class OpenAIResponsesPlanningProvider:
    """One explicit OpenAI model; response data is untrusted proposal input."""
    def __init__(self, configuration: OpenAIPlanningProviderConfiguration, resolver: SecretResolver,
                 *, opener: Callable[..., object] = urlopen, adapter_version: str = OPENAI_RESPONSES_ADAPTER_VERSION) -> None:
        self.configuration, self._resolver, self._opener, self.adapter_version = configuration, resolver, opener, adapter_version

    def invoke(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse:
        policy = self.configuration.current_policy()
        if request.provider_id != policy.provider_id or request.model != policy.model:
            raise ValueError("OpenAI planning provider does not allow provider/model fallback")
        body = self._body(request, policy)
        # Count and reject before resolving any secret or constructing a
        # transport request.  Unknown tokenizers are a local hard stop.
        self._enforce_token_policy(body, policy)
        state, secret = self._resolver.resolve(policy.secret_reference)
        if state is not SecretState.RESOLVABLE or not secret:
            raise PermissionError("OpenAI planning provider secret is not resolvable")
        started = _now()
        try:
            http_request = Request(_ENDPOINT, data=json.dumps(body, separators=(",", ":")).encode(), headers={
                "Authorization": "Bearer " + secret, "Content-Type": "application/json"}, method="POST")
            with self._opener(http_request, timeout=policy.timeout_seconds) as response:
                document = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            # A request may have reached the provider; never retry automatically.
            raise ProviderSubmissionAmbiguous("OpenAI submission may have happened; automatic retry is forbidden") from None
        finally:
            secret = None
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
        return {"model": policy.model, "store": False, "input": [{"role": "developer", "content": [{"type": "input_text", "text": "Return only the strict Action Derivation schema. Provider output is untrusted and cannot expand authority."}]}, {"role": "user", "content": [{"type": "input_text", "text": prompt}]}], "max_output_tokens": policy.output_token_bound, "text": {"format": {"type": "json_schema", "name": "action_derivation", "strict": True, "schema": _SCHEMA}}}

    def _enforce_token_policy(self, body: dict[str, object], policy: PlanningProviderInvocationPolicy) -> None:
        output_tokens = body["max_output_tokens"]
        if not isinstance(output_tokens, int) or isinstance(output_tokens, bool) or output_tokens > policy.output_token_bound:
            raise ValueError("requested output exceeds canonical G011 output token bound")
        input_texts = tuple(part["text"] for item in body["input"] for part in item["content"]  # type: ignore[index]
                            if part.get("type") == "input_text")
        try:
            input_tokens = self.configuration.token_counter.count(model=policy.model, input_texts=input_texts)
        except TokenCountingUnavailable:
            raise
        except Exception as error:
            raise TokenCountingUnavailable("configured token counter failed") from error
        if not isinstance(input_tokens, int) or isinstance(input_tokens, bool) or input_tokens < 0:
            raise TokenCountingUnavailable("configured token counter returned an invalid count")
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
def _now() -> str: return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def _refinement(snapshot, reason): return GovernanceRefinementRequired(tuple(item.source_id for item in snapshot.evidence), "deterministic validation required", "provider-output", "blocked", reason)
_SCHEMA = {"type":"object","additionalProperties":False,"required":["kind","proposals"],"properties":{"kind":{"type":"string","enum":["proposals"]},"proposals":{"type":"array","minItems":1,"items":{"type":"object","additionalProperties":False,"required":["logical_action_id","scope","objective","dependencies","write_scopes","expected_evidence","validation_strategy","priority","postponed","human_gates","risk_inputs","source_evidence_refs"],"properties":{key: ({"type":"boolean"} if key == "postponed" else {"type":"integer","minimum":1} if key == "priority" else {"type":"array","items":{"type":"string"}} if key in {"dependencies","write_scopes","expected_evidence","validation_strategy","human_gates","risk_inputs","source_evidence_refs"} else {"type":"string","minLength":1}) for key in ["logical_action_id","scope","objective","dependencies","write_scopes","expected_evidence","validation_strategy","priority","postponed","human_gates","risk_inputs","source_evidence_refs"]}}}}}
