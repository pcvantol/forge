"""Resolved Governance Profiles for business-facing Forge policy consumers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .execution_policy import ExecutionPolicy, ExecutionPolicyKind, PauseBoundary


GOVERNANCE_PROFILE_DEFINITION_VERSION = "1.0"


class CanonicalGovernanceProfile(str, Enum):
    SOLO = "solo"
    DUO = "duo"
    STARTUP = "startup"
    ENTERPRISE = "enterprise"
    PROFESSIONAL = "professional"


class GovernanceRole(str, Enum):
    BUSINESS_OWNER = "business_owner"
    PLATFORM_ARCHITECT = "platform_architect"
    ENGINEERING_LEAD = "engineering_lead"
    PORTFOLIO_STEWARD = "portfolio_steward"
    SECURITY_ADVISOR = "security_advisor"
    COMPLIANCE_ADVISOR = "compliance_advisor"


class ApprovalStage(str, Enum):
    BUSINESS = "business_approval"
    ARCHITECTURE = "architecture_approval"
    ENGINEERING = "engineering_approval"


@dataclass(frozen=True)
class ResolvedGovernanceProfile:
    profile: CanonicalGovernanceProfile
    source_profile: str
    role_assignments: dict[GovernanceRole, tuple[str, ...]]
    approval_matrix: dict[ApprovalStage, tuple[GovernanceRole, ...]]
    workspace_visibility: tuple[str, ...]
    advisor_roles: tuple[GovernanceRole, ...]
    compatibility_note: str | None = None
    schema_version: str = GOVERNANCE_PROFILE_DEFINITION_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GOVERNANCE_PROFILE_DEFINITION_VERSION:
            raise ValueError("governance profile definition version is unsupported")
        if self.approval_matrix[ApprovalStage.BUSINESS] != (GovernanceRole.BUSINESS_OWNER,):
            raise ValueError("business approval must remain with the Business Owner")
        if self.approval_matrix[ApprovalStage.ARCHITECTURE] != (GovernanceRole.PLATFORM_ARCHITECT,):
            raise ValueError("architecture approval must remain with the Platform Architect")
        if "business" not in self.workspace_visibility or "architecture" not in self.workspace_visibility:
            raise ValueError("Business and Architecture Workspaces must remain visible")


_LEGACY_PROFILE_MAP = {"two_person": CanonicalGovernanceProfile.DUO, "team": CanonicalGovernanceProfile.STARTUP}


def execution_policy_for_profile(profile: str | CanonicalGovernanceProfile) -> ExecutionPolicy:
    """Resolve a governance default while keeping explicit policy override possible."""
    source = profile.value if isinstance(profile, CanonicalGovernanceProfile) else profile
    canonical = _LEGACY_PROFILE_MAP.get(source, CanonicalGovernanceProfile(source))
    defaults = {
        CanonicalGovernanceProfile.SOLO: ExecutionPolicyKind.CONTINUOUS,
        CanonicalGovernanceProfile.DUO: ExecutionPolicyKind.ENGINEERING_INTENT_REVIEW,
        CanonicalGovernanceProfile.STARTUP: ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW,
        CanonicalGovernanceProfile.PROFESSIONAL: ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW,
        CanonicalGovernanceProfile.ENTERPRISE: ExecutionPolicyKind.CUSTOM,
    }
    kind = defaults[canonical]
    return ExecutionPolicy(kind, (PauseBoundary.ENGINEERING_ACTION,) if kind is ExecutionPolicyKind.CUSTOM else ())


def resolve_governance_profile(profile: str | CanonicalGovernanceProfile) -> ResolvedGovernanceProfile:
    """Resolve canonical and legacy stored values without changing the lifecycle."""
    source = profile.value if isinstance(profile, CanonicalGovernanceProfile) else profile
    canonical = _LEGACY_PROFILE_MAP[source] if source in _LEGACY_PROFILE_MAP else CanonicalGovernanceProfile(source)
    note = None if source == canonical.value else f"legacy profile '{source}' resolved explicitly as '{canonical.value}'"
    assignments: dict[CanonicalGovernanceProfile, dict[GovernanceRole, tuple[str, ...]]] = {
        CanonicalGovernanceProfile.SOLO: {GovernanceRole.BUSINESS_OWNER: ("primary_operator",), GovernanceRole.PLATFORM_ARCHITECT: ("primary_operator",)},
        CanonicalGovernanceProfile.DUO: {GovernanceRole.BUSINESS_OWNER: ("business_owner",), GovernanceRole.PLATFORM_ARCHITECT: ("platform_architect",)},
        CanonicalGovernanceProfile.STARTUP: {GovernanceRole.BUSINESS_OWNER: ("business_owner",), GovernanceRole.PLATFORM_ARCHITECT: ("platform_architect",), GovernanceRole.ENGINEERING_LEAD: ("engineering_lead",)},
        CanonicalGovernanceProfile.ENTERPRISE: {GovernanceRole.BUSINESS_OWNER: ("business_owner",), GovernanceRole.PLATFORM_ARCHITECT: ("platform_architect",), GovernanceRole.ENGINEERING_LEAD: ("engineering_lead",), GovernanceRole.PORTFOLIO_STEWARD: ("portfolio_steward",), GovernanceRole.SECURITY_ADVISOR: ("security_advisor",), GovernanceRole.COMPLIANCE_ADVISOR: ("compliance_advisor",)},
    }
    advisors = tuple(role for role in assignments[canonical] if role not in {GovernanceRole.BUSINESS_OWNER, GovernanceRole.PLATFORM_ARCHITECT})
    return ResolvedGovernanceProfile(
        canonical, source, assignments[canonical],
        {ApprovalStage.BUSINESS: (GovernanceRole.BUSINESS_OWNER,), ApprovalStage.ARCHITECTURE: (GovernanceRole.PLATFORM_ARCHITECT,), ApprovalStage.ENGINEERING: (GovernanceRole.PLATFORM_ARCHITECT,)},
        ("business", "architecture", "execution", "analytics"), advisors, note,
    )
