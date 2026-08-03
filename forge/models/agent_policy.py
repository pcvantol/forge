"""Forge-owned, provider-independent Agent Role and Model Selection Policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


AGENT_ROLE_POLICY_SCHEMA_VERSION = "1.0"
AGENT_ROLE_POLICY_VERSION = "1.0.0"


class AgentRole(str, Enum):
    BUSINESS_ADVISOR = "business_advisor"
    ARCHITECTURE_ADVISOR = "architecture_advisor"
    MISSION_PLANNER = "mission_planner"
    ENGINEERING_AGENT = "engineering_agent"
    DOCUMENTATION_AGENT = "documentation_agent"
    VALIDATION_AGENT = "validation_agent"
    QUALIFICATION_AGENT = "qualification_agent"
    GOVERNANCE_AGENT = "governance_agent"
    EXECUTION_OBSERVER = "execution_observer"


class ModelProfile(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    DEEP_REASONING = "deep_reasoning"
    LONG_CONTEXT = "long_context"
    CODE_GENERATION = "code_generation"
    DOCUMENTATION = "documentation"
    VALIDATION = "validation"
    REVIEW = "review"


class ReasoningProfile(str, Enum):
    LIGHT = "light"
    STANDARD = "standard"
    DEEP = "deep"


class EngineeringWorkKind(str, Enum):
    BUSINESS = "business"
    ARCHITECTURE = "architecture"
    PLANNING = "planning"
    ENGINEERING = "engineering"
    DOCUMENTATION = "documentation"
    VALIDATION = "validation"
    QUALIFICATION = "qualification"
    GOVERNANCE = "governance"
    OBSERVATION = "observation"


class ReasoningDepth(str, Enum):
    SIMPLE = "simple"
    STANDARD = "standard"
    COMPLEX = "complex"


class CostPolicy(str, Enum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    QUALITY = "quality"


class LatencyPolicy(str, Enum):
    LOW = "low"
    BALANCED = "balanced"
    THOROUGH = "thorough"


@dataclass(frozen=True)
class ExecutionConstraints:
    """Host-facing consequences of a Forge decision, without provider identity."""

    requires_validation: bool
    requires_human_review: bool
    maximum_parallel_actions: int = 1
    repository_evidence_required: bool = True

    def __post_init__(self) -> None:
        if self.maximum_parallel_actions != 1:
            raise ValueError("agent policy permits exactly one active execution action")

    def to_dict(self) -> dict[str, Any]:
        return {
            "requires_validation": self.requires_validation,
            "requires_human_review": self.requires_human_review,
            "maximum_parallel_actions": self.maximum_parallel_actions,
            "repository_evidence_required": self.repository_evidence_required,
        }

    def prompt_constraints(self) -> tuple[str, ...]:
        """Return the only policy consequences exposed to an Execution Host."""

        values = [
            "Execute exactly one active Engineering Action.",
            "Return repository evidence for the executed Engineering Action.",
        ]
        if self.requires_validation:
            values.append("Complete the declared validation before reporting completion.")
        if self.requires_human_review:
            values.append("Return evidence for Forge and human review; do not self-approve the work.")
        return tuple(values)


@dataclass(frozen=True)
class AgentPolicySelectionRequest:
    """Deterministic Forge input; it contains no provider or host selection."""

    mission_id: str
    action_id: str
    work_kind: EngineeringWorkKind
    reasoning_depth: ReasoningDepth
    repository_context: tuple[str, ...]
    long_context_required: bool = False
    validation_required: bool = False
    cost_policy: CostPolicy = CostPolicy.BALANCED
    latency_policy: LatencyPolicy = LatencyPolicy.BALANCED
    policy_version: str = AGENT_ROLE_POLICY_VERSION
    schema_version: str = AGENT_ROLE_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AGENT_ROLE_POLICY_SCHEMA_VERSION:
            raise ValueError("agent role policy schema version is unsupported")
        if self.policy_version != AGENT_ROLE_POLICY_VERSION:
            raise ValueError("agent role policy version is unsupported")
        if not self.mission_id or not self.action_id:
            raise ValueError("agent policy mission and action identity are required")
        if not self.repository_context or any(not item for item in self.repository_context):
            raise ValueError("agent policy repository context is required")
        if len(self.repository_context) != len(set(self.repository_context)):
            raise ValueError("agent policy repository context must be unique")
        object.__setattr__(self, "repository_context", tuple(sorted(self.repository_context)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "mission_id": self.mission_id,
            "action_id": self.action_id,
            "work_kind": self.work_kind.value,
            "reasoning_depth": self.reasoning_depth.value,
            "repository_context": list(self.repository_context),
            "long_context_required": self.long_context_required,
            "validation_required": self.validation_required,
            "cost_policy": self.cost_policy.value,
            "latency_policy": self.latency_policy.value,
        }


@dataclass(frozen=True)
class AgentPolicySelection:
    """Immutable Forge decision. Provider resolution is deliberately absent."""

    request: AgentPolicySelectionRequest
    agent_role: AgentRole
    model_profile: ModelProfile
    reasoning_profile: ReasoningProfile
    execution_constraints: ExecutionConstraints
    rationale: str

    def __post_init__(self) -> None:
        if not self.rationale:
            raise ValueError("agent policy selection rationale is required")

    @property
    def policy_version(self) -> str:
        return self.request.policy_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "agent_role": self.agent_role.value,
            "model_profile": self.model_profile.value,
            "reasoning_profile": self.reasoning_profile.value,
            "execution_constraints": self.execution_constraints.to_dict(),
            "rationale": self.rationale,
        }

    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()


class AgentRoleModelSelectionPolicy:
    """Select Forge policy outcomes deterministically; never select a provider."""

    _ROLES = {
        EngineeringWorkKind.BUSINESS: AgentRole.BUSINESS_ADVISOR,
        EngineeringWorkKind.ARCHITECTURE: AgentRole.ARCHITECTURE_ADVISOR,
        EngineeringWorkKind.PLANNING: AgentRole.MISSION_PLANNER,
        EngineeringWorkKind.ENGINEERING: AgentRole.ENGINEERING_AGENT,
        EngineeringWorkKind.DOCUMENTATION: AgentRole.DOCUMENTATION_AGENT,
        EngineeringWorkKind.VALIDATION: AgentRole.VALIDATION_AGENT,
        EngineeringWorkKind.QUALIFICATION: AgentRole.QUALIFICATION_AGENT,
        EngineeringWorkKind.GOVERNANCE: AgentRole.GOVERNANCE_AGENT,
        EngineeringWorkKind.OBSERVATION: AgentRole.EXECUTION_OBSERVER,
    }

    def select(self, request: AgentPolicySelectionRequest) -> AgentPolicySelection:
        role = self._ROLES[request.work_kind]
        reasoning = self._reasoning_profile(request)
        model = self._model_profile(request, role)
        constraints = ExecutionConstraints(
            requires_validation=request.validation_required or role in {
                AgentRole.VALIDATION_AGENT, AgentRole.QUALIFICATION_AGENT,
            },
            requires_human_review=role in {
                AgentRole.BUSINESS_ADVISOR, AgentRole.ARCHITECTURE_ADVISOR,
                AgentRole.GOVERNANCE_AGENT,
            },
        )
        rationale = (
            f"{request.work_kind.value} work deterministically selects {role.value}; "
            f"{request.reasoning_depth.value} reasoning and context requirements select "
            f"{model.value}/{reasoning.value}."
        )
        return AgentPolicySelection(request, role, model, reasoning, constraints, rationale)

    @staticmethod
    def _reasoning_profile(request: AgentPolicySelectionRequest) -> ReasoningProfile:
        if request.reasoning_depth is ReasoningDepth.COMPLEX:
            return ReasoningProfile.DEEP
        if request.reasoning_depth is ReasoningDepth.SIMPLE and request.latency_policy is LatencyPolicy.LOW:
            return ReasoningProfile.LIGHT
        return ReasoningProfile.STANDARD

    @staticmethod
    def _model_profile(request: AgentPolicySelectionRequest, role: AgentRole) -> ModelProfile:
        fixed = {
            AgentRole.DOCUMENTATION_AGENT: ModelProfile.DOCUMENTATION,
            AgentRole.VALIDATION_AGENT: ModelProfile.VALIDATION,
            AgentRole.QUALIFICATION_AGENT: ModelProfile.VALIDATION,
            AgentRole.ENGINEERING_AGENT: ModelProfile.CODE_GENERATION,
            AgentRole.GOVERNANCE_AGENT: ModelProfile.REVIEW,
            AgentRole.EXECUTION_OBSERVER: ModelProfile.FAST,
        }
        if role in fixed:
            return fixed[role]
        if request.long_context_required:
            return ModelProfile.LONG_CONTEXT
        if request.reasoning_depth is ReasoningDepth.COMPLEX:
            return ModelProfile.DEEP_REASONING
        if role is AgentRole.ARCHITECTURE_ADVISOR:
            return ModelProfile.REVIEW
        if request.cost_policy is CostPolicy.ECONOMY or request.latency_policy is LatencyPolicy.LOW:
            return ModelProfile.FAST
        return ModelProfile.BALANCED
