"""Deterministic orchestration for one Architecture-approved active Mission.

The loop composes existing independent boundaries.  It neither approves a
Mission nor selects a host implementation, and it never changes the approved
Mission or its scope.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
from typing import Any, Callable, Mapping, Protocol

from forge.capabilities import (CapabilityRegistry, DelegationApprovalState,
                                DelegationRequest, DelegationResultState)
from forge.completion import MissionCompletionEvaluator
from forge.dispatcher import MissionDispatcher
from forge.governance import ApprovalRecord, ExecutionPolicy, ExecutionPolicyKind, PauseBoundary, execution_policy_for_profile
from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.architecture_mission import ArchitectureMission
from forge.models.execution_host import ExecutionHost, ExecutionHostEvidence
from forge.models.mission_completion import (MissionCompletionEvidence,
                                              MissionCriterionEvaluationStatus)
from forge.models.action_derivation import DerivationPolicy
from forge.models.mission_planner import (MissionCriterionPlanningState, MissionPlan,
                                          MissionPlannerInput, MissionPlanningState,
                                          PlanningInputKind)
from forge.planner import AIMissionPlanner, DerivationResult, MissionPlanner
from forge.runtime import BootstrapMissionRunner, RuntimePromptFactory
from forge.scheduler import BootstrapMissionScheduler
from forge.state import MissionExecutionState, MissionExecutionStatus, MissionStateStore


class ExecutionLoopError(ValueError):
    """Raised when a bounded Mission cannot advance deterministically."""


class PlanningInputFactory(Protocol):
    def __call__(self, state: MissionExecutionState) -> MissionPlannerInput: ...


class RepositoryTruthFactory(Protocol):
    def __call__(self, state: MissionExecutionState, evidence: ExecutionHostEvidence | None) -> Mapping[str, Any]: ...


class MissionCompletionEvidenceFactory(Protocol):
    """Forge-owned association of approved criteria with canonical evidence."""

    def __call__(self, state: MissionExecutionState, evidence: ExecutionHostEvidence,
                 repository_truth: Mapping[str, Any]) -> MissionCompletionEvidence | None: ...


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
        repository_identity: str | None = None,
        clock: Callable[[], str],
        correlation_id_factory: Callable[[], str],
        execution_policy: ExecutionPolicy | None = None,
        governance_profile: str = "solo",
        capability_registry: CapabilityRegistry | None = None,
        ai_planner: AIMissionPlanner | None = None,
        derivation_policy: DerivationPolicy | None = None,
        completion_evidence: MissionCompletionEvidenceFactory | None = None,
        completion_evaluator: MissionCompletionEvaluator | None = None,
    ) -> None:
        if not all((host_id, workspace_id, repository_id)):
            raise ExecutionLoopError("execution host, workspace, and repository identities are required")
        self._dispatcher, self._states, self._planner, self._host = dispatcher, states, planner, host
        self._planning_input, self._prompt_factory, self._repository_truth = planning_input, prompt_factory, repository_truth
        self._host_id, self._workspace_id, self._repository_id = host_id, workspace_id, repository_id
        self._repository_identity = repository_identity or repository_id
        self._clock, self._correlation_id_factory = clock, correlation_id_factory
        self._execution_policy = execution_policy or execution_policy_for_profile(governance_profile)
        self._capability_registry = capability_registry
        self._ai_planner = ai_planner
        self._derivation_policy = derivation_policy
        self._completion_evidence = completion_evidence
        self._completion_evaluator = completion_evaluator or MissionCompletionEvaluator()

    def run(self) -> MissionExecutionState | None:
        """Run the one dispatched Mission until terminal or awaiting host evidence."""
        record = self._dispatcher.dispatch()
        if record is None:
            return None
        state = self._states.get(record.mission_id)
        state = self._states.set_execution_policy(state.mission_id, self._execution_policy.to_dict(), occurred_at=self._clock())
        if state.status is MissionExecutionStatus.CREATED:
            state = self._plan(state)
        if state.status is MissionExecutionStatus.READY_TO_CONTINUE:
            self._replan_after_delegation(state)
            state = self._states.transition(state.mission_id, MissionExecutionStatus.READY, occurred_at=self._clock(),
                                            reason="verified_delegation_ready_to_continue")
        if state.status is MissionExecutionStatus.READY:
            state = self._delegate_if_required(state)
        if state.status in {MissionExecutionStatus.WAITING_EXTERNAL_CAPABILITY,
                            MissionExecutionStatus.WAITING_EXTERNAL_APPROVAL,
                            MissionExecutionStatus.WAITING_EXTERNAL_RESULT}:
            self._dispatcher.hold(state.mission_id, state.status)
            return state
        if state.status in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED}:
            self._dispatcher.hold(state.mission_id, state.status)
            return state
        if state.status is MissionExecutionStatus.AWAITING_APPROVAL:
            return state
        result = self._runner().run(state.mission_id)
        if result.status in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED}:
            self._dispatcher.hold(result.mission_id, result.status)
        elif result.status is MissionExecutionStatus.COMPLETED:
            self._dispatcher.complete(result.mission_id)
        return result

    def resume(self, mission_id: str, authorization: RecoveryAuthorization | None = None,
               approval: ApprovalRecord | None = None) -> MissionExecutionState:
        """Resume durable work; a blocked or failed Action needs explicit authority."""
        state = self._states.get(mission_id)
        if state.status is MissionExecutionStatus.AWAITING_APPROVAL:
            if approval is None:
                raise ExecutionLoopError("governance-paused Mission requires an approval record")
            if authorization is not None:
                raise ExecutionLoopError("recovery authorization is not valid for a governance-paused Mission")
            boundary = str((state.pause_reason or {}).get("boundary"))
            target = MissionExecutionStatus.COMPLETED if boundary == PauseBoundary.MISSION.value else MissionExecutionStatus.ACTIVE
            state = self._states.transition(mission_id, target, occurred_at=self._clock(), reason="governance_approval_recorded",
                                            approval_record=approval.to_dict())
            if target is MissionExecutionStatus.COMPLETED:
                self._dispatcher.complete(mission_id)
                return state
            return self.run() if self._dispatcher.resume() else self._runner().run(mission_id)
        if approval is not None:
            raise ExecutionLoopError("approval record is valid only for a governance-paused Mission")
        if state.status in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED}:
            if authorization is None:
                raise ExecutionLoopError("blocked or failed Mission requires explicit recovery authorization")
            state = self._recover(state, authorization)
            self._dispatcher.recover(mission_id)
        elif authorization is not None:
            raise ExecutionLoopError("recovery authorization is valid only for blocked or failed Missions")
        return self.run() if self._dispatcher.resume() else self._runner().run(mission_id)

    def approve_delegation(self, mission_id: str, delegation_id: str, approval: ApprovalRecord) -> MissionExecutionState:
        """Record governance approval for one exact delegation without invoking a provider."""
        state = self._states.get(mission_id)
        if state.status is not MissionExecutionStatus.WAITING_EXTERNAL_APPROVAL:
            raise ExecutionLoopError("delegation is not awaiting external approval")
        delegation = self._delegation(state, delegation_id)
        updated = {**delegation, "approval_state": DelegationApprovalState.APPROVED.value}
        return self._states.transition(mission_id, MissionExecutionStatus.WAITING_EXTERNAL_RESULT,
                                       occurred_at=self._clock(), reason="delegation_approval_recorded",
                                       delegations=self._replace_delegation(state, updated), approval_record=approval.to_dict())

    def receive_delegation_result(self, mission_id: str, delegation_id: str, *, accepted: bool,
                                  verification: Mapping[str, Any]) -> MissionExecutionState:
        """Accept only verified external work and preserve the Mission-owned Action lineage."""
        state = self._states.get(mission_id)
        if state.status is not MissionExecutionStatus.WAITING_EXTERNAL_RESULT:
            raise ExecutionLoopError("delegation is not awaiting an external result")
        if not verification or not verification.get("verified"):
            raise ExecutionLoopError("delegated result requires explicit verification")
        delegation = self._delegation(state, delegation_id)
        result = DelegationResultState.ACCEPTED if accepted else DelegationResultState.REJECTED
        updated = {**delegation, "result_state": result.value, "verification": dict(verification)}
        if not accepted:
            return self._states.transition(mission_id, MissionExecutionStatus.WAITING_EXTERNAL_CAPABILITY,
                                           occurred_at=self._clock(), reason="delegated_result_rejected",
                                           delegations=self._replace_delegation(state, updated))
        actions = tuple(replace(self._action(item), status=EngineeringActionStatus.COMPLETE)
                        if item["id"] == delegation["action_id"] else self._action(item) for item in state.actions)
        return self._states.transition(mission_id, MissionExecutionStatus.READY_TO_CONTINUE,
                                       occurred_at=self._clock(), reason="delegated_result_verified",
                                       actions=actions, delegations=self._replace_delegation(state, updated),
                                       execution_evidence={"delegation_id": delegation_id, "outcome": "verified_external_completion"})

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
        input_value = self._current_planning_input(state)
        if input_value.mission.id != state.mission_id:
            raise ExecutionLoopError("planner input must belong to the active Mission")
        plan, derivation = self._select_plan(input_value, state)
        actions = tuple(action for intent in plan.intents for action in intent.actions)
        if not actions:
            raise ExecutionLoopError("approved Mission planning produced no executable Engineering Actions")
        truth = self._repository_truth(state, None)
        return self._states.transition(
            state.mission_id, MissionExecutionStatus.READY, occurred_at=self._clock(),
            reason="dynamic_derivation_materialized" if derivation is not None else "deterministic_plan_persisted",
            intents=plan.intents, actions=actions, repository_truth=truth,
            planning_history=state.planning_history if derivation is None else (*state.planning_history, derivation),
        )

    def _current_planning_input(self, state: MissionExecutionState) -> MissionPlannerInput:
        source = self._planning_input(state)
        if source.mission.id != state.mission_id or source.mission.to_dict() != dict(state.mission):
            raise ExecutionLoopError("planner input must bind the exact approved Mission")
        completed = tuple(sorted(str(action["id"]) for action in state.actions
                                 if action["status"] == EngineeringActionStatus.COMPLETE.value))
        blocked = tuple(sorted(str(action["id"]) for action in state.actions
                               if action["status"] in {EngineeringActionStatus.BLOCKED.value, EngineeringActionStatus.FAILED.value}))
        completion_criteria = state.completion.get("criteria", ()) if state.completion else ()
        criterion_states = tuple(MissionCriterionPlanningState(
            str(item["criterion_id"]), MissionCriterionEvaluationStatus(str(item["status"])),
        ) for item in completion_criteria if isinstance(item, Mapping))
        return replace(source, mission_state=MissionPlanningState(
            state.mission_id, state.revision, completed, blocked, criterion_states,
        ))

    @staticmethod
    def _dynamic_mode(planning_input: MissionPlannerInput) -> bool:
        flags = tuple(scope.allow_provider_derivation for scope in planning_input.approved_scopes)
        if any(flags) and not all(flags):
            raise ExecutionLoopError("mixed static and provider-derived Mission scopes are not supported")
        if any(flags) and any(scope.actions for scope in planning_input.approved_scopes):
            raise ExecutionLoopError("provider-derived Mission scopes cannot contain preconfigured Actions")
        return all(flags)

    def _select_plan(self, planning_input: MissionPlannerInput,
                     state: MissionExecutionState) -> tuple[MissionPlan, Mapping[str, Any] | None]:
        if not self._dynamic_mode(planning_input):
            return self._planner.replan(planning_input), None
        if self._ai_planner is None or self._derivation_policy is None:
            raise ExecutionLoopError("provider-derived Mission has no authorized derivation composition")
        result = self._ai_planner.plan(planning_input, self._derivation_policy)
        if result.governance_refinement is not None:
            raise ExecutionLoopError("provider-derived Mission requires governance refinement")
        if result.plan is None or result.validated is None:
            raise ExecutionLoopError("provider-derived Mission produced no validated materialization")
        return result.plan, self._derivation_record(result, planning_input, state)

    def _derivation_record(self, result: DerivationResult, planning_input: MissionPlannerInput,
                           state: MissionExecutionState) -> Mapping[str, Any]:
        assert result.validated is not None and result.plan is not None and self._derivation_policy is not None
        proposals = result.validated.proposals
        provenance = proposals[0].provenance
        proposal_documents = tuple({
            "logical_action_id": proposal.logical_action_id,
            "semantic_digest": proposal.semantic_digest(),
            "provenance": asdict(proposal.provenance),
            "mission_gap": None if proposal.mission_gap is None else proposal.mission_gap.to_dict(),
        } for proposal in proposals)
        validation_source = {
            "snapshot_digest": result.snapshot.digest,
            "policy": asdict(self._derivation_policy),
            "proposals": proposal_documents,
        }
        validation_digest = "sha256:" + sha256(json.dumps(
            validation_source, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")).hexdigest()
        return {
            "schema_version": "1.1",
            "derivation_id": provenance.derivation_id,
            "mission_id": planning_input.mission.id,
            "parent_derivation_id": None if not state.planning_history else state.planning_history[-1]["derivation_id"],
            "lifecycle": "MATERIALIZED",
            "planning_snapshot": result.snapshot.to_dict(),
            "planning_snapshot_digest": result.snapshot.digest,
            "provider_id": provenance.provider_id,
            "provider_model": provenance.provider_model,
            "implementation_version": provenance.implementation_version,
            "policy_digest": "sha256:" + sha256(json.dumps(
                asdict(self._derivation_policy), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest(),
            "validation_status": "PASS",
            "validation_digest": validation_digest,
            "validated_before_materialization": True,
            "materialized_plan_id": result.plan.id,
            "materialized_plan_digest": result.plan.input_digest,
            "materialized_action_ids": [proposal.logical_action_id for proposal in proposals],
            "proposals": list(proposal_documents),
            "completed_action_ids_at_derivation": list(planning_input.mission_state.completed_action_ids),
        }

    def _delegate_if_required(self, state: MissionExecutionState) -> MissionExecutionState:
        if self._capability_registry is None:
            return state
        action = next((item for item in state.actions if item["status"] == EngineeringActionStatus.READY.value), None)
        if action is None:
            return state
        intent = next(item for item in state.intents if item["id"] == action["intent_id"] and item["revision"] == action["intent_revision"])
        impacts = tuple(intent.get("capability_impact", ()))
        if not impacts:
            raise ExecutionLoopError("Engineering Action has no required capability for assessment")
        assessment = self._capability_registry.assess(str(impacts[0]))
        if assessment.available:
            return state
        request = DelegationRequest(
            f"delegation-{state.mission_id}-{action['id']}", state.mission_id, str(action["id"]), assessment.capability_id,
            assessment.selected_provider, assessment.rationale, tuple(action["expected_evidence"]), self._clock(),
            DelegationApprovalState.PENDING if assessment.approval_required else DelegationApprovalState.NOT_REQUIRED,
            assessment.alternatives_considered, assessment.confidence,
        ).to_dict()
        waiting = self._states.transition(state.mission_id, MissionExecutionStatus.WAITING_EXTERNAL_CAPABILITY,
                                          occurred_at=self._clock(), reason="capability_unavailable",
                                          delegations=(*state.delegations, request))
        target = MissionExecutionStatus.WAITING_EXTERNAL_APPROVAL if assessment.approval_required else MissionExecutionStatus.WAITING_EXTERNAL_RESULT
        return self._states.transition(waiting.mission_id, target, occurred_at=self._clock(), reason="capability_delegated")

    @staticmethod
    def _delegation(state: MissionExecutionState, delegation_id: str) -> Mapping[str, Any]:
        delegation = next((item for item in state.delegations if item.get("id") == delegation_id), None)
        if delegation is None:
            raise ExecutionLoopError("delegation does not belong to this Mission")
        return delegation

    @staticmethod
    def _replace_delegation(state: MissionExecutionState, updated: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
        return tuple(updated if item.get("id") == updated["id"] else item for item in state.delegations)

    def _replan_after_delegation(self, state: MissionExecutionState) -> None:
        source = self._current_planning_input(state)
        if self._dynamic_mode(source):
            raise ExecutionLoopError("provider-derived Mission continuation requires canonical terminal Host evidence")
        plan = self._planner.replan(source)
        remaining = tuple(sorted(action["id"] for action in state.actions if action["status"] != EngineeringActionStatus.COMPLETE.value))
        planned = tuple(sorted(action.id for intent in plan.intents for action in intent.actions))
        if planned != remaining:
            raise ExecutionLoopError("delegation continuation must preserve every unresolved approved Engineering Action")

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
        def completion(state: MissionExecutionState, evidence: ExecutionHostEvidence):
            truth = self._repository_truth(state, evidence)
            mission = ArchitectureMission.from_dict(dict(state.mission))
            evidence_contract = (None if self._completion_evidence is None
                                 else self._completion_evidence(state, evidence, truth))
            current = asdict(evidence)
            current["outcome"] = evidence.outcome.value
            evaluation = self._completion_evaluator.evaluate(
                mission, truth, (*state.execution_history, current), evidence_contract,
            )
            return truth, evaluation

        return BootstrapMissionRunner(self._states, BootstrapMissionScheduler(), self._host, self._prompt_factory,
                                      host_id=self._host_id, workspace_id=self._workspace_id, repository_id=self._repository_id,
                                      repository_identity=self._repository_identity,
                                      clock=self._clock, correlation_id_factory=self._correlation_id_factory,
                                      completion_context=completion, replan_after_evidence=self._replan_after_evidence,
                                      evidence_progression_gate=self._pause_after_evidence)

    def _pause_after_evidence(self, state: MissionExecutionState, actions: tuple[EngineeringAction, ...],
                              evidence: ExecutionHostEvidence, mission_complete: bool) -> MissionExecutionState | None:
        """Apply policy only after exact evidence, never by altering host execution."""
        policy = ExecutionPolicy.from_dict(state.execution_policy if state.execution_policy and state.execution_policy.get("kind") else self._execution_policy.to_dict())
        current = next(item for item in actions if item.id == evidence.repository_evidence.action_id)
        boundary: PauseBoundary | None = None
        identity = current.id
        if PauseBoundary.MISSION in policy.boundaries and mission_complete:
            boundary, identity = PauseBoundary.MISSION, state.mission_id
        elif PauseBoundary.CAPABILITY in policy.boundaries and self._capability_complete(state, actions, current):
            boundary, identity = PauseBoundary.CAPABILITY, self._capability_identity(state, current)
        elif PauseBoundary.ENGINEERING_INTENT in policy.boundaries and all(
            item.status is EngineeringActionStatus.COMPLETE for item in actions
            if (item.intent_id, item.intent_revision) == (current.intent_id, current.intent_revision)
        ):
            boundary, identity = PauseBoundary.ENGINEERING_INTENT, current.intent_id
        elif PauseBoundary.ENGINEERING_ACTION in policy.boundaries:
            boundary = PauseBoundary.ENGINEERING_ACTION
        if boundary is None:
            return None
        next_action = next((item.id for item in actions if item.status is not EngineeringActionStatus.COMPLETE), None)
        reason = {"policy_kind": policy.kind.value, "boundary": boundary.value, "boundary_identity": identity,
                  "completed_action_id": current.id}
        return self._states.transition(state.mission_id, MissionExecutionStatus.AWAITING_APPROVAL,
                                       occurred_at=self._clock(), reason="execution_policy_pause", actions=actions,
                                       pause_reason=reason,
                                       resume={**state.resume, "next_action_id": next_action, "pause_boundary": boundary.value})

    @staticmethod
    def _capability_identity(state: MissionExecutionState, action: EngineeringAction) -> str:
        intent = next(item for item in state.intents if item["id"] == action.intent_id and item["revision"] == action.intent_revision)
        return str(intent["capability_impact"][0])

    def _capability_complete(self, state: MissionExecutionState, actions: tuple[EngineeringAction, ...], action: EngineeringAction) -> bool:
        capability = self._capability_identity(state, action)
        intent_ids = {item["id"] for item in state.intents if capability in item.get("capability_impact", ())}
        return all(item.status is EngineeringActionStatus.COMPLETE for item in actions if item.intent_id in intent_ids)

    def _replan_after_evidence(self, state: MissionExecutionState,
                               evidence: ExecutionHostEvidence) -> MissionExecutionState:
        """Validate static work or derive new immutable successor work."""
        replanning = self._current_planning_input(state)
        actions = tuple(self._action(item) for item in state.actions)
        remaining = tuple(sorted(action.id for action in actions if action.status is not EngineeringActionStatus.COMPLETE))
        if not self._dynamic_mode(replanning):
            plan = self._planner.replan(replanning)
            planned = tuple(sorted(action.id for intent in plan.intents for action in intent.actions))
            if planned != remaining:
                raise ExecutionLoopError("replanning must preserve every unresolved approved Engineering Action")
            if not remaining:
                raise ExecutionLoopError("Mission criteria remain unmet and static planning has no successor")
            return state

        self._assert_current_replan_evidence(state, replanning, evidence)
        plan, derivation = self._select_plan(replanning, state)
        assert derivation is not None
        existing_ids = {action.id for action in actions}
        proposed = tuple(action for intent in plan.intents for action in intent.actions)
        if not proposed:
            raise ExecutionLoopError("Mission criteria remain unmet and derivation produced no successor")
        if existing_ids & {action.id for action in proposed}:
            raise ExecutionLoopError("derived successor cannot reuse a materialized Engineering Action identity")
        next_order = max((action.order for action in actions), default=0) + 1
        renumbered: dict[tuple[str, str], tuple[EngineeringAction, ...]] = {}
        for intent in plan.intents:
            current: list[EngineeringAction] = []
            for action in intent.actions:
                current.append(replace(action, order=next_order))
                next_order += 1
            renumbered[(intent.id, intent.revision)] = tuple(current)
        new_intents = tuple(replace(intent, actions=renumbered[(intent.id, intent.revision)]) for intent in plan.intents)
        new_actions = tuple(action for intent in new_intents for action in intent.actions)
        return self._states.transition(
            state.mission_id, MissionExecutionStatus.ACTIVE, occurred_at=self._clock(),
            reason="dynamic_successor_materialized", intents=(*state.intents, *new_intents),
            actions=(*actions, *new_actions), planning_history=(*state.planning_history, derivation),
        )

    @staticmethod
    def _assert_current_replan_evidence(state: MissionExecutionState,
                                        planning_input: MissionPlannerInput,
                                        evidence: ExecutionHostEvidence) -> None:
        truth = state.repository_truth or {}
        truth_digest = truth.get("content_digest")
        if not isinstance(truth_digest, str):
            raise ExecutionLoopError("dynamic replan requires persisted current Repository Truth")
        truth_evidence = tuple(item for item in planning_input.evidence
                               if item.kind is PlanningInputKind.REPOSITORY_TRUTH)
        execution_evidence = tuple(item for item in planning_input.evidence
                                   if item.kind is PlanningInputKind.EXECUTION_EVIDENCE)
        mission_state_evidence = tuple(item for item in planning_input.evidence
                                       if item.kind is PlanningInputKind.MISSION_STATE)
        if (not any(item.content_digest == truth_digest for item in truth_evidence)
                or not any(item.content_digest == evidence.repository_evidence.content_digest for item in execution_evidence)
                or not any(item.revision == str(state.revision) for item in mission_state_evidence)):
            raise ExecutionLoopError("dynamic replan input does not bind current evidence and Repository Truth")

    @staticmethod
    def _action(document: Mapping[str, Any]) -> EngineeringAction:
        return EngineeringAction(int(document["order"]), str(document["id"]), str(document["intent_id"]),
                                 str(document["intent_revision"]), str(document["objective"]),
                                 tuple(document["expected_evidence"]), tuple(document.get("dependencies", ())),
                                 EngineeringActionStatus(document["status"]), str(document["schema_version"]))
