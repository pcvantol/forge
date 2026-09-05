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
from forge.provider_security import SecretReference, SecretState
from .provider_adapter import ProviderDerivationRequest, ProviderDerivationResponse

OPENAI_RESPONSES_ADAPTER_VERSION = "1.0"
_ENDPOINT = "https://api.openai.com/v1/responses"

class ProviderSubmissionAmbiguous(RuntimeError):
    """The request may have reached OpenAI; operator reconciliation is required."""

class SecretResolver(Protocol):
    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]: ...

@dataclass(frozen=True)
class OpenAIPlanningProviderConfiguration:
    provider_id: str
    model: str
    secret_reference: SecretReference
    timeout_seconds: float = 20.0
    max_input_characters: int = 12000
    max_output_tokens: int = 1800
    enabled: bool = False

    def __post_init__(self) -> None:
        if not self.provider_id or not self.model:
            raise ValueError("OpenAI planning provider requires explicit provider and model")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120 or self.max_input_characters < 512 or self.max_output_tokens < 128:
            raise ValueError("OpenAI planning provider bounds are invalid")

class OpenAIResponsesPlanningProvider:
    """One explicit OpenAI model; response data is untrusted proposal input."""
    def __init__(self, configuration: OpenAIPlanningProviderConfiguration, resolver: SecretResolver,
                 *, opener: Callable[..., object] = urlopen, adapter_version: str = OPENAI_RESPONSES_ADAPTER_VERSION) -> None:
        self.configuration, self._resolver, self._opener, self.adapter_version = configuration, resolver, opener, adapter_version

    def invoke(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse:
        if not self.configuration.enabled:
            raise PermissionError("OpenAI planning provider is disabled")
        if request.provider_id != self.configuration.provider_id or request.model != self.configuration.model:
            raise ValueError("OpenAI planning provider does not allow provider/model fallback")
        state, secret = self._resolver.resolve(self.configuration.secret_reference)
        if state is not SecretState.RESOLVABLE or not secret:
            raise PermissionError("OpenAI planning provider secret is not resolvable")
        started = _now()
        body = self._body(request)
        try:
            http_request = Request(_ENDPOINT, data=json.dumps(body, separators=(",", ":")).encode(), headers={
                "Authorization": "Bearer " + secret, "Content-Type": "application/json"}, method="POST")
            with self._opener(http_request, timeout=self.configuration.timeout_seconds) as response:
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

    def _body(self, request: ProviderDerivationRequest) -> dict[str, object]:
        evidence = [{"kind": item.kind.value, "source_id": item.source_id, "revision": item.revision, "content_digest": item.content_digest} for item in request.snapshot.evidence]
        prompt = json.dumps({"contract":"Forge Action Derivation; propose only, never approve or execute.", "snapshot": request.snapshot.to_dict() | {"evidence": evidence}}, separators=(",", ":"))
        if len(prompt) > self.configuration.max_input_characters:
            raise ValueError("bounded planning evidence exceeds configured input limit")
        return {"model": self.configuration.model, "store": False, "input": [{"role": "developer", "content": [{"type": "input_text", "text": "Return only the strict Action Derivation schema. Provider output is untrusted and cannot expand authority."}]}, {"role": "user", "content": [{"type": "input_text", "text": prompt}]}], "max_output_tokens": self.configuration.max_output_tokens, "text": {"format": {"type": "json_schema", "name": "action_derivation", "strict": True, "schema": _SCHEMA}}}

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
