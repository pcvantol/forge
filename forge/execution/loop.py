"""Deterministic orchestration for one Architecture-approved active Mission.

The loop composes existing independent boundaries.  It neither approves a
Mission nor selects a host implementation, and it never changes the approved
Mission or its scope.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Protocol

from forge.dispatcher import MissionDispatcher
from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.execution_host import ExecutionHost, ExecutionHostEvidence
from forge.models.mission_planner import MissionPlannerInput, MissionPlanningState
from forge.planner import MissionPlanner
from forge.runtime import BootstrapMissionRunner, RuntimePromptFactory
from forge.scheduler import BootstrapMissionScheduler
from forge.state import MissionExecutionState, MissionExecutionStatus, MissionStateStore


class ExecutionLoopError(ValueError):
    """Raised when a bounded Mission cannot advance deterministically."""


class PlanningInputFactory(Protocol):
    def __call__(self, state: MissionExecutionState) -> MissionPlannerInput: ...


class RepositoryTruthFactory(Protocol):
    def __call__(self, state: MissionExecutionState, evidence: ExecutionHostEvidence | None) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RecoveryAuthorization:
    """Explicit operator authority to retry one unresolved action exactly once."""

    mission_id: str
    action_id: str
    authorization_id: str
    reason: str

    def __post_init__(self) -> None:
        if not all((self.mission_id, self.action_id, self.authorization_id, self.reason)):
            raise ValueError("recovery authorization requires mission, action, identity, and reason")

    def to_dict(self) -> dict[str, str]:
        return {"mission_id": self.mission_id, "action_id": self.action_id,
                "authorization_id": self.authorization_id, "reason": self.reason}


@dataclass(frozen=True)
class ExecutionLoopObservability:
    """Read-only projection of the canonical Mission State."""

    mission_id: str
    lifecycle_state: str
    current_intent_id: str | None
    current_action_id: str | None
    completed_actions: int
    total_actions: int
    percent_complete: int
    execution_host_state: str
    waiting_reason: str | None


class ExecutionLoop:
    """Continuously advance one active Mission while preserving all boundaries."""

    def __init__(
        self,
        dispatcher: MissionDispatcher,
        states: MissionStateStore,
        planner: MissionPlanner,
        host: ExecutionHost,
        planning_input: PlanningInputFactory,
        prompt_factory: RuntimePromptFactory,
        repository_truth: RepositoryTruthFactory,
        *,
        host_id: str,
        workspace_id: str,
        repository_id: str,
        clock: Callable[[], str],
        correlation_id_factory: Callable[[], str],
    ) -> None:
        if not all((host_id, workspace_id, repository_id)):
            raise ExecutionLoopError("execution host, workspace, and repository identities are required")
        self._dispatcher, self._states, self._planner, self._host = dispatcher, states, planner, host
        self._planning_input, self._prompt_factory, self._repository_truth = planning_input, prompt_factory, repository_truth
        self._host_id, self._workspace_id, self._repository_id = host_id, workspace_id, repository_id
        self._clock, self._correlation_id_factory = clock, correlation_id_factory

    def run(self) -> MissionExecutionState | None:
        """Run the one dispatched Mission until terminal or awaiting host evidence."""
        record = self._dispatcher.dispatch()
        if record is None:
            return None
        state = self._states.get(record.mission_id)
        if state.status is MissionExecutionStatus.CREATED:
            state = self._plan(state)
        if state.status in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED}:
            self._dispatcher.hold(state.mission_id, state.status)
            return state
        result = self._runner().run(state.mission_id)
        if result.status in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED}:
            self._dispatcher.hold(result.mission_id, result.status)
        elif result.status is MissionExecutionStatus.COMPLETED:
            self._dispatcher.complete(result.mission_id)
        return result

    def resume(self, mission_id: str, authorization: RecoveryAuthorization | None = None) -> MissionExecutionState:
        """Resume durable work; a blocked or failed Action needs explicit authority."""
        state = self._states.get(mission_id)
        if state.status in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED}:
            if authorization is None:
                raise ExecutionLoopError("blocked or failed Mission requires explicit recovery authorization")
            state = self._recover(state, authorization)
            self._dispatcher.recover(mission_id)
        elif authorization is not None:
            raise ExecutionLoopError("recovery authorization is valid only for blocked or failed Missions")
        return self.run() if self._dispatcher.resume() else self._runner().run(mission_id)

    def observability(self, mission_id: str) -> ExecutionLoopObservability:
        state = self._states.get(mission_id)
        current_intent = state.current_engineering_intent or {}
        current_action = state.current_engineering_action or {}
        return ExecutionLoopObservability(
            mission_id, state.status.value, current_intent.get("id"), current_action.get("id"),
            int(state.progress["completed_actions"]), int(state.progress["total_actions"]),
            int(state.progress["percent_complete"]), state.status.value, state.waiting_reason,
        )

    def _plan(self, state: MissionExecutionState) -> MissionExecutionState:
        input_value = self._planning_input(state)
        if input_value.mission.id != state.mission_id:
            raise ExecutionLoopError("planner input must belong to the active Mission")
        plan = self._planner.replan(input_value)
        actions = tuple(action for intent in plan.intents for action in intent.actions)
        if not actions:
            raise ExecutionLoopError("approved Mission planning produced no executable Engineering Actions")
        truth = self._repository_truth(state, None)
        return self._states.transition(
            state.mission_id, MissionExecutionStatus.READY, occurred_at=self._clock(), reason="deterministic_plan_persisted",
            intents=plan.intents, actions=actions, repository_truth=truth,
        )

    def _recover(self, state: MissionExecutionState, authorization: RecoveryAuthorization) -> MissionExecutionState:
        if authorization.mission_id != state.mission_id:
            raise ExecutionLoopError("recovery authorization must match the Mission")
        unresolved = state.current_engineering_action
        if unresolved is None or unresolved.get("id") != authorization.action_id:
            raise ExecutionLoopError("recovery authorization must name the unresolved Engineering Action")
        actions = tuple(
            replace(self._action(item), status=EngineeringActionStatus.READY) if item["id"] == authorization.action_id else self._action(item)
            for item in state.actions
        )
        resume = dict(state.resume)
        resume["authorized_recovery"] = authorization.to_dict()
        return self._states.transition(state.mission_id, MissionExecutionStatus.READY, occurred_at=self._clock(),
                                       reason="authorized_recovery", actions=actions, resume=resume)

    def _runner(self) -> BootstrapMissionRunner:
        def completion(state: MissionExecutionState, evidence: ExecutionHostEvidence) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
            truth = self._repository_truth(state, evidence)
            completion_state = {"success_criteria_satisfied": True, "execution_evidence_complete": True,
                                "repository_truth_updated": True, "repository_truth_digest": truth.get("content_digest")}
            return truth, completion_state

        return BootstrapMissionRunner(self._states, BootstrapMissionScheduler(), self._host, self._prompt_factory,
                                      host_id=self._host_id, workspace_id=self._workspace_id, repository_id=self._repository_id,
                                      clock=self._clock, correlation_id_factory=self._correlation_id_factory,
                                      completion_context=completion, replan_after_evidence=self._replan_after_evidence)

    def _replan_after_evidence(self, state: MissionExecutionState, actions: tuple[EngineeringAction, ...], _evidence: ExecutionHostEvidence) -> None:
        """Re-evaluate only remaining approved work; the original plan stays canonical."""
        source = self._planning_input(state)
        completed = tuple(sorted(action.id for action in actions if action.status is EngineeringActionStatus.COMPLETE))
        replanning = replace(source, mission_state=MissionPlanningState(state.mission_id, state.revision + 1, completed))
        plan = self._planner.replan(replanning)
        remaining = tuple(sorted(action.id for action in actions if action.status is not EngineeringActionStatus.COMPLETE))
        planned = tuple(sorted(action.id for intent in plan.intents for action in intent.actions))
        if planned != remaining:
            raise ExecutionLoopError("replanning must preserve every unresolved approved Engineering Action")

    @staticmethod
    def _action(document: Mapping[str, Any]) -> EngineeringAction:
        return EngineeringAction(int(document["order"]), str(document["id"]), str(document["intent_id"]),
                                 str(document["intent_revision"]), str(document["objective"]),
                                 tuple(document["expected_evidence"]), tuple(document.get("dependencies", ())),
                                 EngineeringActionStatus(document["status"]), str(document["schema_version"]))
