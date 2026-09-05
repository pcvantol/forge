"""Provider-neutral, non-authoritative proposals for AI Mission planning.

This module deliberately separates an immutable approved Mission (authority),
pinned repository evidence (facts), and an AI/provider proposal (untrusted
input).  Only deterministic validation can project a proposal into the
existing deterministic Mission Planner input.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any

from .mission_planner import MissionPlannerInput, PlanningEvidence


ACTION_DERIVATION_SCHEMA_VERSION = "1.0"


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class PlanningSnapshot:
    """Digest-pinned, immutable evidence available to one derivation attempt."""

    id: str
    mission_id: str
    mission_revision: int
    mission_digest: str
    mission_state_digest: str
    evidence: tuple[PlanningEvidence, ...]
    digest: str
    schema_version: str = ACTION_DERIVATION_SCHEMA_VERSION

    @classmethod
    def from_planner_input(cls, planning_input: MissionPlannerInput) -> "PlanningSnapshot":
        mission_digest = _digest(planning_input.mission.to_dict())
        state_digest = _digest(asdict(planning_input.mission_state))
        document = {
            "schema_version": ACTION_DERIVATION_SCHEMA_VERSION,
            "mission_id": planning_input.mission.id,
            "mission_revision": planning_input.mission_state.revision,
            "mission_digest": mission_digest,
            "mission_state_digest": state_digest,
            "evidence": [item.to_dict() for item in planning_input.evidence],
        }
        digest = _digest(document)
        return cls(f"planning-snapshot-{digest[7:23]}", planning_input.mission.id,
                   planning_input.mission_state.revision, mission_digest, state_digest,
                   planning_input.evidence, digest)

    def is_current_for(self, planning_input: MissionPlannerInput) -> bool:
        return self == self.from_planner_input(planning_input)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id, "mission_id": self.mission_id,
                "mission_revision": self.mission_revision, "mission_digest": self.mission_digest,
                "mission_state_digest": self.mission_state_digest,
                "evidence": [item.to_dict() for item in self.evidence], "digest": self.digest}


@dataclass(frozen=True)
class ProposalProvenance:
    derivation_id: str
    planning_snapshot_id: str
    planning_snapshot_digest: str
    implementation_version: str
    provider_id: str
    provider_model: str | None
    source_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not all((self.derivation_id, self.planning_snapshot_id, self.planning_snapshot_digest, self.implementation_version, self.provider_id, self.source_evidence_refs)):
            raise ValueError("proposal provenance requires derivation, snapshot, implementation, provider, and source evidence")
        if len(self.source_evidence_refs) != len(set(self.source_evidence_refs)) or any(not item for item in self.source_evidence_refs):
            raise ValueError("proposal provenance evidence references must be unique and non-empty")
        object.__setattr__(self, "source_evidence_refs", tuple(sorted(self.source_evidence_refs)))


@dataclass(frozen=True)
class DerivedActionProposal:
    """Rich proposed work.  It is never an EngineeringAction or authority."""

    logical_action_id: str
    scope: str
    objective: str
    dependencies: tuple[str, ...]
    write_scopes: tuple[str, ...]
    expected_evidence: tuple[str, ...]
    validation_strategy: tuple[str, ...]
    priority: int
    postponed: bool
    human_gates: tuple[str, ...]
    risk_inputs: tuple[str, ...]
    provenance: ProposalProvenance

    def __post_init__(self) -> None:
        if not all((self.logical_action_id, self.scope, self.objective, self.expected_evidence, self.validation_strategy, self.priority >= 1)):
            raise ValueError("derived action proposal requires identity, scope, objective, evidence, validation, and positive priority")
        for name in ("dependencies", "write_scopes", "expected_evidence", "validation_strategy", "human_gates", "risk_inputs"):
            values = getattr(self, name)
            if len(values) != len(set(values)) or any(not item for item in values):
                raise ValueError(f"derived action proposal {name} must be unique and non-empty when supplied")
            object.__setattr__(self, name, tuple(sorted(values)))
        if self.logical_action_id in self.dependencies:
            raise ValueError("derived action proposal cannot depend on itself")

    def semantic_digest(self) -> str:
        """Stable identity comparison excludes provider-specific provenance."""
        return _digest({"logical_action_id": self.logical_action_id, "scope": self.scope,
                        "objective": self.objective, "dependencies": self.dependencies,
                        "write_scopes": self.write_scopes, "expected_evidence": self.expected_evidence,
                        "validation_strategy": self.validation_strategy, "priority": self.priority,
                        "postponed": self.postponed, "human_gates": self.human_gates,
                        "risk_inputs": self.risk_inputs})


def classify_replan_identity(previous: DerivedActionProposal | None, current: DerivedActionProposal,
                              *, completed: bool = False) -> DerivedActionIdentityState:
    """Classify one logical action without rewriting historical completed evidence."""
    if previous is None:
        return DerivedActionIdentityState.NEW
    if previous.logical_action_id != current.logical_action_id:
        return DerivedActionIdentityState.SUPERSEDED
    if current.postponed:
        return DerivedActionIdentityState.DEFERRED
    if previous.semantic_digest() == current.semantic_digest():
        return DerivedActionIdentityState.UNCHANGED
    return DerivedActionIdentityState.SUPERSEDED if completed else DerivedActionIdentityState.MODIFIED_UNEXECUTED


@dataclass(frozen=True)
class GovernanceRefinementRequired:
    """Fail-closed result where a valid decomposition needs new authority."""

    triggering_evidence: tuple[str, ...]
    missing_authority: str
    affected_scope: str
    impact_classification: str
    reason: str

    def __post_init__(self) -> None:
        if not all((self.triggering_evidence, self.missing_authority, self.affected_scope, self.impact_classification, self.reason)):
            raise ValueError("governance refinement result requires complete evidence and impact")
        object.__setattr__(self, "triggering_evidence", tuple(sorted(self.triggering_evidence)))


class ProposalValidationStatus(str, Enum):
    PASS = "PASS"
    STALE_REDERIVE_REQUIRED = "STALE_REDERIVE_REQUIRED"
    GOVERNANCE_REFINEMENT_REQUIRED = "GOVERNANCE_REFINEMENT_REQUIRED"


class DerivationLifecycle(str, Enum):
    SNAPSHOT_CREATED = "SNAPSHOT_CREATED"
    DERIVATION_REQUESTED = "DERIVATION_REQUESTED"
    PROVIDER_RUNNING = "PROVIDER_RUNNING"
    PROPOSAL_RECEIVED = "PROPOSAL_RECEIVED"
    VALIDATION_RUNNING = "VALIDATION_RUNNING"
    VALIDATED = "VALIDATED"
    MATERIALIZED = "MATERIALIZED"
    GOVERNANCE_REFINEMENT_REQUIRED = "GOVERNANCE_REFINEMENT_REQUIRED"
    FAILED = "FAILED"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"


class ProviderSideEffectState(str, Enum):
    DID_NOT_HAPPEN = "DID_NOT_HAPPEN"
    HAPPENED_AND_CONFIRMED = "HAPPENED_AND_CONFIRMED"
    MAY_HAVE_HAPPENED = "MAY_HAVE_HAPPENED"


class DerivedActionIdentityState(str, Enum):
    UNCHANGED = "UNCHANGED"
    MODIFIED_UNEXECUTED = "MODIFIED_UNEXECUTED"
    SUPERSEDED = "SUPERSEDED"
    DEFERRED = "DEFERRED"
    NEW = "NEW"


@dataclass(frozen=True)
class ProviderInvocationEvidence:
    """Bounded provider evidence; raw payloads and credentials never belong here."""

    provider_id: str
    model: str | None
    adapter_version: str
    request_digest: str
    snapshot_digest: str
    result_digest: str | None
    side_effect_state: ProviderSideEffectState

    def __post_init__(self) -> None:
        if not all((self.provider_id, self.adapter_version, self.request_digest, self.snapshot_digest)):
            raise ValueError("provider invocation evidence requires provider, adapter, request, and snapshot provenance")
        for digest in (self.request_digest, self.snapshot_digest, self.result_digest):
            if digest is not None and (not digest.startswith("sha256:") or len(digest) != 71):
                raise ValueError("provider invocation evidence digests must be sha256 values")


_LIFECYCLE_TRANSITIONS = {
    DerivationLifecycle.SNAPSHOT_CREATED: {DerivationLifecycle.DERIVATION_REQUESTED, DerivationLifecycle.STALE},
    DerivationLifecycle.DERIVATION_REQUESTED: {DerivationLifecycle.PROVIDER_RUNNING, DerivationLifecycle.FAILED},
    DerivationLifecycle.PROVIDER_RUNNING: {DerivationLifecycle.PROPOSAL_RECEIVED, DerivationLifecycle.FAILED},
    DerivationLifecycle.PROPOSAL_RECEIVED: {DerivationLifecycle.VALIDATION_RUNNING, DerivationLifecycle.STALE},
    DerivationLifecycle.VALIDATION_RUNNING: {DerivationLifecycle.VALIDATED, DerivationLifecycle.GOVERNANCE_REFINEMENT_REQUIRED, DerivationLifecycle.FAILED, DerivationLifecycle.STALE},
    DerivationLifecycle.VALIDATED: {DerivationLifecycle.MATERIALIZED, DerivationLifecycle.STALE},
    DerivationLifecycle.MATERIALIZED: {DerivationLifecycle.SUPERSEDED},
    DerivationLifecycle.GOVERNANCE_REFINEMENT_REQUIRED: set(),
    DerivationLifecycle.FAILED: set(),
    DerivationLifecycle.STALE: set(),
    DerivationLifecycle.SUPERSEDED: set(),
}


@dataclass(frozen=True)
class DerivationRecord:
    """Durable operational projection; raw provider payloads are intentionally absent."""

    derivation_id: str
    mission_id: str
    snapshot_digest: str
    contract_version: str
    provider_configuration: str
    lifecycle: DerivationLifecycle
    proposal_digest: str | None = None
    validation_digest: str | None = None
    materialization_digest: str | None = None
    parent_derivation_id: str | None = None

    def transition(self, lifecycle: DerivationLifecycle, **digests: str | None) -> "DerivationRecord":
        if lifecycle not in _LIFECYCLE_TRANSITIONS[self.lifecycle]:
            raise ValueError(f"invalid action derivation transition: {self.lifecycle.value} -> {lifecycle.value}")
        values = {**asdict(self), **digests, "lifecycle": lifecycle}
        return DerivationRecord(**values)

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["lifecycle"] = self.lifecycle.value
        return document


@dataclass(frozen=True)
class DerivationPolicy:
    """Architecture-approved allow-lists, supplied by Forge rather than a provider."""

    allowed_write_scopes: tuple[str, ...]
    required_human_gates: tuple[str, ...] = ()
    required_risk_inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("allowed_write_scopes", "required_human_gates", "required_risk_inputs"):
            values = getattr(self, name)
            if len(values) != len(set(values)) or any(not item for item in values):
                raise ValueError(f"derivation policy {name} must be unique and non-empty when supplied")
            object.__setattr__(self, name, tuple(sorted(values)))


@dataclass(frozen=True)
class ValidatedDerivation:
    snapshot: PlanningSnapshot
    proposals: tuple[DerivedActionProposal, ...]
    status: ProposalValidationStatus = ProposalValidationStatus.PASS

    def __post_init__(self) -> None:
        if self.status is not ProposalValidationStatus.PASS or not self.proposals:
            raise ValueError("validated derivation requires a passing status and proposals")
        if len({proposal.logical_action_id for proposal in self.proposals}) != len(self.proposals):
            raise ValueError("derived proposal identities must be unique")
        object.__setattr__(self, "proposals", tuple(sorted(self.proposals, key=lambda item: (item.priority, item.logical_action_id))))
