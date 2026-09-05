"""Provider adapter boundary for Action Derivation.

The adapter deliberately transports a digest-pinned snapshot only. It records
bounded evidence and never makes a provider result authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Protocol

from forge.models.action_derivation import (
    DerivedActionProposal, GovernanceRefinementRequired, PlanningSnapshot,
    ProviderInvocationEvidence, ProviderSideEffectState,
)


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class ProviderDerivationRequest:
    derivation_id: str
    snapshot: PlanningSnapshot
    provider_id: str
    model: str | None

    @property
    def digest(self) -> str:
        return _digest({"derivation_id": self.derivation_id, "snapshot": self.snapshot.to_dict(),
                        "provider_id": self.provider_id, "model": self.model})


@dataclass(frozen=True)
class ProviderDerivationResponse:
    evidence: ProviderInvocationEvidence
    proposals: tuple[DerivedActionProposal, ...] | None = None
    governance_refinement: GovernanceRefinementRequired | None = None

    def __post_init__(self) -> None:
        if (self.proposals is None) == (self.governance_refinement is None):
            raise ValueError("provider response must contain exactly proposals or governance refinement")
        if self.evidence.side_effect_state is not ProviderSideEffectState.HAPPENED_AND_CONFIRMED:
            raise ValueError("only a confirmed provider result may carry proposal data")


class ProviderExecutor(Protocol):
    def invoke(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse: ...
    def reconcile(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse | ProviderSideEffectState: ...


class BoundedActionDerivationProvider:
    """Adapter with no retry path: ambiguity is explicitly returned to Forge."""

    def __init__(self, executor: ProviderExecutor, *, adapter_version: str = "1.0") -> None:
        self._executor = executor
        self.adapter_version = adapter_version

    def invoke(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse:
        response = self._executor.invoke(request)
        evidence = response.evidence
        if evidence.adapter_version != self.adapter_version or evidence.request_digest != request.digest:
            raise ValueError("provider response does not bind the requested adapter/version/digest")
        if evidence.snapshot_digest != request.snapshot.digest or evidence.provider_id != request.provider_id or evidence.model != request.model:
            raise ValueError("provider response provenance does not bind the requested provider/snapshot")
        return response

    def reconcile(self, request: ProviderDerivationRequest) -> ProviderDerivationResponse | ProviderSideEffectState:
        result = self._executor.reconcile(request)
        if isinstance(result, ProviderDerivationResponse):
            return self.invoke_reconciled(request, result)
        return result

    def invoke_reconciled(self, request: ProviderDerivationRequest, response: ProviderDerivationResponse) -> ProviderDerivationResponse:
        evidence = response.evidence
        if evidence.request_digest != request.digest or evidence.snapshot_digest != request.snapshot.digest:
            raise ValueError("reconciled provider response does not bind the original request")
        return response
