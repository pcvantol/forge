"""Regression coverage for Forge-owned Agent Role and Model Selection Policy."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from forge.models import (
    AgentPolicySelectionRequest,
    AgentRole,
    AgentRoleModelSelectionPolicy,
    CostPolicy,
    EngineeringWorkKind,
    LatencyPolicy,
    ModelProfile,
    ReasoningDepth,
    ReasoningProfile,
)


def request(**overrides: object) -> AgentPolicySelectionRequest:
    values: dict[str, object] = {
        "mission_id": "mission-1",
        "action_id": "action-1",
        "work_kind": EngineeringWorkKind.ENGINEERING,
        "reasoning_depth": ReasoningDepth.STANDARD,
        "repository_context": ("architecture", "repository_truth"),
    }
    values.update(overrides)
    return AgentPolicySelectionRequest(**values)  # type: ignore[arg-type]


class AgentRoleModelSelectionPolicyTests(unittest.TestCase):
    def test_all_canonical_work_kinds_select_their_canonical_agent_role(self) -> None:
        policy = AgentRoleModelSelectionPolicy()
        expected = {
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
        self.assertEqual({kind: policy.select(request(work_kind=kind)).agent_role for kind in expected}, expected)

    def test_model_and_reasoning_profiles_follow_deterministic_policy(self) -> None:
        policy = AgentRoleModelSelectionPolicy()
        self.assertEqual(policy.select(request()).model_profile, ModelProfile.CODE_GENERATION)
        self.assertEqual(policy.select(request(work_kind=EngineeringWorkKind.DOCUMENTATION)).model_profile, ModelProfile.DOCUMENTATION)
        self.assertEqual(policy.select(request(work_kind=EngineeringWorkKind.VALIDATION)).model_profile, ModelProfile.VALIDATION)
        planning = policy.select(request(work_kind=EngineeringWorkKind.PLANNING, long_context_required=True))
        self.assertEqual(planning.model_profile, ModelProfile.LONG_CONTEXT)
        self.assertEqual(policy.select(request(reasoning_depth=ReasoningDepth.COMPLEX)).reasoning_profile, ReasoningProfile.DEEP)
        self.assertEqual(
            policy.select(request(work_kind=EngineeringWorkKind.OBSERVATION, reasoning_depth=ReasoningDepth.SIMPLE,
                                  latency_policy=LatencyPolicy.LOW)).reasoning_profile,
            ReasoningProfile.LIGHT,
        )

    def test_policy_canonicalizes_input_and_produces_a_stable_digest(self) -> None:
        policy = AgentRoleModelSelectionPolicy()
        first = policy.select(request(repository_context=("repository_truth", "architecture")))
        second = policy.select(request(repository_context=("architecture", "repository_truth")))
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.digest(), second.digest())
        with self.assertRaises(FrozenInstanceError):
            first.agent_role = AgentRole.BUSINESS_ADVISOR  # type: ignore[misc]

    def test_policy_is_versioned_and_has_no_provider_or_host_resolution(self) -> None:
        selection = AgentRoleModelSelectionPolicy().select(request(cost_policy=CostPolicy.ECONOMY))
        self.assertEqual(selection.policy_version, "1.0.0")
        self.assertNotIn("provider", selection.to_dict())
        self.assertNotIn("host", selection.to_dict())
        with self.assertRaisesRegex(ValueError, "version"):
            replace(request(), policy_version="other")

    def test_constraints_preserve_validation_and_human_review_boundaries(self) -> None:
        policy = AgentRoleModelSelectionPolicy()
        validation = policy.select(request(work_kind=EngineeringWorkKind.VALIDATION))
        architecture = policy.select(request(work_kind=EngineeringWorkKind.ARCHITECTURE))
        self.assertTrue(validation.execution_constraints.requires_validation)
        self.assertTrue(architecture.execution_constraints.requires_human_review)
        self.assertEqual(validation.execution_constraints.maximum_parallel_actions, 1)


if __name__ == "__main__":
    unittest.main()
