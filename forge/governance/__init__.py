"""Declarative governance policy; it is not an identity or workflow system."""

from .profiles import (
    GOVERNANCE_PROFILE_DEFINITION_VERSION,
    ApprovalStage,
    CanonicalGovernanceProfile,
    GovernanceRole,
    ResolvedGovernanceProfile,
    execution_policy_for_profile,
    resolve_governance_profile,
)
from .execution_policy import ApprovalRecord, ExecutionPolicy, ExecutionPolicyKind, PauseBoundary

__all__ = [
    "GOVERNANCE_PROFILE_DEFINITION_VERSION",
    "ApprovalStage",
    "CanonicalGovernanceProfile",
    "GovernanceRole",
    "ResolvedGovernanceProfile",
    "ApprovalRecord",
    "ExecutionPolicy",
    "ExecutionPolicyKind",
    "PauseBoundary",
    "execution_policy_for_profile",
    "resolve_governance_profile",
]
