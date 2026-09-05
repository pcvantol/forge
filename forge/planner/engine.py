"""Pure deterministic planning; this module deliberately has no execution dependencies."""

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.mission_planner import MissionPlan, MissionPlannerInput, PlannedEngineeringIntent, planning_digest


class MissionPlanner:
    """Transform one approved Mission and pinned repository evidence into pending Actions."""

    def plan(self, planning_input: MissionPlannerInput) -> MissionPlan:
        digest = planning_digest(planning_input)
        intents: list[PlannedEngineeringIntent] = []
        deferred: list[str] = []
        order = 1
        for scope in planning_input.approved_scopes:
            intent_id = f"{planning_input.mission.id}:intent:{scope.scope}"
            revision = digest[7:19]
            actions: list[EngineeringAction] = []
            validation: set[str] = set()
            expected: set[str] = set()
            grouped = {}
            for item in scope.actions:
                grouped.setdefault(item.merge_key or item.id, []).append(item)
            for group_key, definitions in sorted(grouped.items(), key=lambda item: (min(value.priority for value in item[1]), item[0])):
                definition = definitions[0]
                action_ids = {item.id for item in definitions}
                if definition.postponed:
                    deferred.extend(action_ids)
                    continue
                if action_ids <= set(planning_input.mission_state.completed_action_ids):
                    continue
                validation.update(value for item in definitions for value in item.validation_strategy)
                expected.update(value for item in definitions for value in item.expected_evidence)
                action_id = definition.id if len(definitions) == 1 else f"{intent_id}:merged:{group_key}"
                objective = definition.objective if len(definitions) == 1 else " / ".join(item.objective for item in definitions)
                evidence = tuple(value for item in definitions for value in item.expected_evidence)
                dependencies = tuple(sorted({dependency for item in definitions for dependency in item.dependencies} - action_ids))
                actions.append(EngineeringAction(order, action_id, intent_id, revision, objective, evidence, dependencies,
                                                 status=EngineeringActionStatus.BLOCKED if action_ids & set(planning_input.mission_state.blocked_action_ids) else EngineeringActionStatus.READY))
                order += 1
            if actions:
                intents.append(PlannedEngineeringIntent(intent_id, revision, f"Deliver approved scope: {scope.scope}",
                    "Generated only from the approved Mission boundary and digest-pinned repository evidence.",
                    scope.architecture_references, (scope.capability_id,), tuple(validation), tuple(expected), tuple(actions)))
        return MissionPlan(f"mission-plan-{digest[7:23]}", planning_input.mission.id, digest, tuple(intents), tuple(sorted(deferred)))

    def replan(self, planning_input: MissionPlannerInput) -> MissionPlan:
        """Explicit continuous-planning entry point; identical input remains identical output."""
        return self.plan(planning_input)
