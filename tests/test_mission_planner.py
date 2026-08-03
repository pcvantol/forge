"""Regression coverage for deterministic, bounded AI Mission planning."""

from __future__ import annotations

import unittest

from forge.models import (
    ApprovedScope, ArchitectureMission, ArchitectureMissionStatus, EngineeringEffort, IntentReference,
    MissionPlannerInput, MissionPlanningState, PlannedActionDefinition, PlanningEvidence, PlanningInputKind,
    RecommendationConfidenceLevel, RequiredDiscipline,
)
from forge.planner import MissionPlanner


def digest(char: str) -> str:
    return f"sha256:{char * 64}"


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1", f"local://{identifier}")


def mission() -> ArchitectureMission:
    return ArchitectureMission(
        "mission-1", "candidate-1", "Planner", "Plan only.", "Build a bounded planner.", "Safe engineering.",
        "architecture-review-1", "recommendation-1", ("planner-contract", "planner-docs"),
        ("Planning never executes.",), ("Deterministic plans are generated.",), ("Local data only.",),
        ("architecture-approved",), ("mission-planner", "documentation"),
        (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("Scope drift.",), ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
    )


def evidence(*, reverse: bool = False, extra: tuple[PlanningEvidence, ...] = ()) -> tuple[PlanningEvidence, ...]:
    records = tuple(PlanningEvidence(kind, kind.value, "1", f"local://{kind.value}", digest("a")) for kind in (
        PlanningInputKind.MISSION_STATE, PlanningInputKind.REPOSITORY_TRUTH,
        PlanningInputKind.ARCHITECTURE_REVIEW, PlanningInputKind.CAPABILITY_CATALOGUE,
    )) + extra
    return tuple(reversed(records)) if reverse else records


def input_model(**overrides: object) -> MissionPlannerInput:
    scopes = (
        ApprovedScope("planner-contract", "mission-planner", (reference("architecture"),), (
            PlannedActionDefinition("action-contract", "Implement planner contract.", ("contract tests",), ("unit tests",), 10),
            PlannedActionDefinition("action-deferred", "Document deferred strategy.", ("docs",), ("cross references",), 20, True),
        )),
        ApprovedScope("planner-docs", "documentation", (reference("architecture"),), (
            PlannedActionDefinition("action-docs", "Document planner boundaries.", ("docs",), ("cross references",), 30),
        )),
    )
    values: dict[str, object] = {"mission": mission(), "mission_state": MissionPlanningState("mission-1", 1),
                                 "evidence": evidence(), "approved_scopes": scopes}
    values.update(overrides)
    return MissionPlannerInput(**values)  # type: ignore[arg-type]


class MissionPlannerTests(unittest.TestCase):
    def test_generates_intents_and_atomic_actions_with_required_tactical_fields(self) -> None:
        plan = MissionPlanner().plan(input_model())
        self.assertEqual(len(plan.intents), 2)
        self.assertEqual([action.id for intent in plan.intents for action in intent.actions], ["action-contract", "action-docs"])
        self.assertEqual(plan.intents[0].capability_impact, ("mission-planner",))
        self.assertEqual(plan.deferred_action_ids, ("action-deferred",))

    def test_continuous_replanning_uses_mission_state_and_execution_evidence(self) -> None:
        state = MissionPlanningState("mission-1", 2, ("action-contract",))
        plan = MissionPlanner().replan(input_model(mission_state=state, evidence=evidence(extra=(PlanningEvidence(PlanningInputKind.EXECUTION_EVIDENCE, "run-1", "2", "local://run-1", digest("b")),))))
        self.assertEqual([action.id for intent in plan.intents for action in intent.actions], ["action-docs"])

    def test_declared_actions_can_be_merged_deterministically(self) -> None:
        first = PlannedActionDefinition("action-a", "Add model.", ("model evidence",), ("model tests",), merge_key="contract")
        second = PlannedActionDefinition("action-b", "Add validation.", ("validation evidence",), ("validation tests",), merge_key="contract")
        scope = ApprovedScope("planner-contract", "mission-planner", (reference("architecture"),), (first, second))
        plan = MissionPlanner().plan(input_model(approved_scopes=(scope, input_model().approved_scopes[1])))
        self.assertEqual(len(plan.intents[0].actions), 1)
        self.assertIn(":merged:contract", plan.intents[0].actions[0].id)

    def test_planning_fails_closed_outside_mission_or_architecture_boundaries(self) -> None:
        with self.assertRaisesRegex(ValueError, "cover exactly"):
            input_model(approved_scopes=input_model().approved_scopes[:1])
        invalid = ApprovedScope("planner-contract", "not-approved", (reference("architecture"),), (
            PlannedActionDefinition("action-x", "Outside capability.", ("evidence",), ("tests",)),
        ))
        with self.assertRaisesRegex(ValueError, "Mission-required capabilities"):
            input_model(approved_scopes=(invalid, input_model().approved_scopes[1]))

    def test_only_engineering_approved_missions_and_repository_only_inputs_are_admitted(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved_for_engineering"):
            input_model(mission=ArchitectureMission(**{**mission().__dict__, "status": ArchitectureMissionStatus.ARCHITECTURE_REVIEW}))
        with self.assertRaisesRegex(ValueError, "Repository Truth"):
            input_model(evidence=tuple(item for item in evidence() if item.kind is not PlanningInputKind.REPOSITORY_TRUTH))
        self.assertFalse(any("conversation" in item.value or "prompt" in item.value or "host" in item.value for item in PlanningInputKind))

    def test_identical_inputs_generate_identical_plans_independent_of_input_order(self) -> None:
        planner = MissionPlanner()
        self.assertEqual(planner.plan(input_model()).to_dict(), planner.plan(input_model(evidence=evidence(reverse=True))).to_dict())


if __name__ == "__main__":
    unittest.main()
