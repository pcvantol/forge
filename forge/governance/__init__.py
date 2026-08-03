"""Declarative governance policy; it is not an identity or workflow system."""

from .profiles import (
    GOVERNANCE_PROFILE_DEFINITION_VERSION,
    ApprovalStage,
    CanonicalGovernanceProfile,
    GovernanceRole,
    ResolvedGovernanceProfile,
    resolve_governance_profile,
)

__all__ = [
    "GOVERNANCE_PROFILE_DEFINITION_VERSION",
    "ApprovalStage",
    "CanonicalGovernanceProfile",
    "GovernanceRole",
    "ResolvedGovernanceProfile",
    "resolve_governance_profile",
]
