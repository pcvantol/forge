"""Pure, deterministic Mission scheduling through the Execution Host contract."""

from __future__ import annotations

from dataclasses import dataclass, replace

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.execution_host import (
    ExecutionDispatch,
    ExecutionEvidenceOutcome,
    ExecutionHost,
    ExecutionHostEvidence,
    ExecutionRequest,
)


@dataclass(frozen=True)
class IntentProgress:
    """Intent progress derived solely from the terminal state of its Actions."""

    intent_id: str
    intent_revision: str
    total_actions: int
    completed_actions: int

    @property
    def is_complete(self) -> bool:
        return self.total_actions > 0 and self.completed_actions == self.total_actions


@dataclass(frozen=True)
class MissionProgress:
    """Evidence-derived Mission progress; no inferred completion is permitted."""

    total_actions: int
    completed_actions: int
    current_intent_id: str | None
    current_action_id: str | None
    terminal_state: EngineeringActionStatus | None
    total_intents: int
    completed_intents: int

    @property
    def percent_complete(self) -> int:
        return (self.completed_actions * 100) // self.total_actions

    @property
    def is_complete(self) -> bool:
        return self.total_actions == self.completed_actions and self.total_intents == self.completed_intents


class BootstrapMissionScheduler:
    """Release one Action at a time and accept only exact, run-bound evidence."""

    @staticmethod
    def _validate(actions: tuple[EngineeringAction, ...]) -> None:
        if not actions:
            raise ValueError("mission scheduler requires Engineering Actions")
        ordered = tuple(sorted(actions))
        if tuple(action.order for action in ordered) != tuple(range(1, len(ordered) + 1)):
            raise ValueError("engineering action orders must be consecutive")
        ids = {action.id for action in actions}
        if len(ids) != len(actions):
            raise ValueError("engineering action identities must be unique")
        if any(dependency not in ids for action in actions for dependency in action.dependencies):
            raise ValueError("engineering action dependencies must be in the Mission")
        in_flight = [action for action in actions if action.status in {EngineeringActionStatus.ACTIVE, EngineeringActionStatus.WAITING_FOR_RESULT}]
        if len(in_flight) > 1:
            raise ValueError("only one Engineering Action may be active or awaiting a result")

    def next_action(self, actions: tuple[EngineeringAction, ...]) -> EngineeringAction | None:
        self._validate(actions)
        if any(action.status in {EngineeringActionStatus.ACTIVE, EngineeringActionStatus.WAITING_FOR_RESULT} for action in actions):
            return None
        if any(action.status in {EngineeringActionStatus.BLOCKED, EngineeringActionStatus.FAILED} for action in actions):
            return None
        by_id = {action.id: action for action in actions}
        for action in sorted(actions):
            if action.status is EngineeringActionStatus.READY and all(by_id[item].status is EngineeringActionStatus.COMPLETE for item in action.dependencies):
                return action
        return None

    def activate(self, actions: tuple[EngineeringAction, ...]) -> tuple[EngineeringAction, ...]:
        action = self.next_action(actions)
        if action is None:
            raise ValueError("no evidence-eligible Engineering Action is ready")
        return self._replace(actions, action.id, EngineeringActionStatus.ACTIVE)

    def dispatch(self, actions: tuple[EngineeringAction, ...], request: ExecutionRequest, host: ExecutionHost) -> tuple[tuple[EngineeringAction, ...], ExecutionDispatch]:
        action = self._by_id(actions, request.action_id)
        if action.status is not EngineeringActionStatus.ACTIVE:
            raise ValueError("only the active Engineering Action can dispatch")
        if (action.intent_id, action.intent_revision) != (request.intent_id, request.intent_revision):
            raise ValueError("execution request Intent provenance does not match its active Action")
        dispatch = host.dispatch(request)
        if dispatch.request != request:
            raise ValueError("execution host must acknowledge the exact dispatch request")
        return self.acknowledge(actions, dispatch), dispatch

    def acknowledge(self, actions: tuple[EngineeringAction, ...], dispatch: ExecutionDispatch) -> tuple[EngineeringAction, ...]:
        """Persist the host acknowledgement after a Runner-owned safe dispatch."""
        request = dispatch.request
        action = self._by_id(actions, request.action_id)
        if action.status is not EngineeringActionStatus.ACTIVE:
            raise ValueError("only the active Engineering Action can acknowledge dispatch")
        if (action.intent_id, action.intent_revision) != (request.intent_id, request.intent_revision):
            raise ValueError("execution request Intent provenance does not match its active Action")
        return self._replace(actions, action.id, EngineeringActionStatus.WAITING_FOR_RESULT)

    def reconcile_from_host(self, actions: tuple[EngineeringAction, ...], dispatch: ExecutionDispatch, host: ExecutionHost) -> tuple[EngineeringAction, ...]:
        evidence = host.retrieve_evidence(dispatch)
        if evidence is None:
            raise ValueError("execution host has not returned terminal evidence")
        return self.reconcile(actions, dispatch, evidence)

    def reconcile(self, actions: tuple[EngineeringAction, ...], dispatch: ExecutionDispatch, evidence: ExecutionHostEvidence) -> tuple[EngineeringAction, ...]:
        request = dispatch.request
        action = self._by_id(actions, request.action_id)
        if action.status is not EngineeringActionStatus.WAITING_FOR_RESULT:
            raise ValueError("only a waiting Engineering Action can reconcile terminal evidence")
        if (action.intent_id, action.intent_revision) != (request.intent_id, request.intent_revision):
            raise ValueError("dispatch Intent provenance does not match its waiting Action")
        repository = evidence.repository_evidence
        expected = (request.host_id, request.correlation_id, dispatch.host_run_id, request.retry_of_correlation_id,
                    request.mission_id, request.intent_id, request.intent_revision, request.action_id,
                    request.runtime_prompt.id, request.repository_id)
        actual = (evidence.host_id, evidence.correlation_id, evidence.host_run_id, evidence.retry_of_correlation_id,
                  repository.mission_id, repository.intent_id, repository.intent_revision, repository.action_id,
                  repository.runtime_prompt_id, repository.repository_id)
        if actual != expected:
            raise ValueError("terminal evidence does not exactly match the dispatched execution run")
        if evidence.outcome is ExecutionEvidenceOutcome.COMPLETE:
            return self._replace(actions, action.id, EngineeringActionStatus.COMPLETE)
        if evidence.outcome is ExecutionEvidenceOutcome.BLOCKED:
            return self._replace(actions, action.id, EngineeringActionStatus.BLOCKED)
        if evidence.outcome is ExecutionEvidenceOutcome.FAILED:
            return self._replace(actions, action.id, EngineeringActionStatus.FAILED)
        raise ValueError("unknown terminal evidence outcome fails closed")

    def progress(self, actions: tuple[EngineeringAction, ...]) -> MissionProgress:
        self._validate(actions)
        current = next((action for action in actions if action.status in {EngineeringActionStatus.ACTIVE, EngineeringActionStatus.WAITING_FOR_RESULT}), None)
        terminal = next((action.status for action in actions if action.status in {EngineeringActionStatus.BLOCKED, EngineeringActionStatus.FAILED}), None)
        intents = self.intent_progress(actions)
        return MissionProgress(
            len(actions),
            sum(action.status is EngineeringActionStatus.COMPLETE for action in actions),
            None if current is None else current.intent_id,
            None if current is None else current.id,
            terminal,
            len(intents),
            sum(intent.is_complete for intent in intents),
        )

    def intent_progress(self, actions: tuple[EngineeringAction, ...]) -> tuple[IntentProgress, ...]:
        """Return only Action-derived completion; an Intent never executes itself."""
        self._validate(actions)
        grouped: dict[tuple[str, str], list[EngineeringAction]] = {}
        for action in actions:
            grouped.setdefault((action.intent_id, action.intent_revision), []).append(action)
        return tuple(
            IntentProgress(
                intent_id=intent_id,
                intent_revision=intent_revision,
                total_actions=len(items),
                completed_actions=sum(item.status is EngineeringActionStatus.COMPLETE for item in items),
            )
            for (intent_id, intent_revision), items in sorted(grouped.items())
        )

    @staticmethod
    def _by_id(actions: tuple[EngineeringAction, ...], action_id: str) -> EngineeringAction:
        for action in actions:
            if action.id == action_id:
                return action
        raise ValueError("Engineering Action is not in the Mission")

    @staticmethod
    def _replace(actions: tuple[EngineeringAction, ...], action_id: str, status: EngineeringActionStatus) -> tuple[EngineeringAction, ...]:
        return tuple(replace(action, status=status) if action.id == action_id else action for action in actions)
