"""Pure deterministic scheduling; no runtime, I/O, or execution host."""

from __future__ import annotations

from dataclasses import dataclass, replace

from forge.models.action import EngineeringAction, EngineeringActionStatus


@dataclass(frozen=True, order=True)
class RepositoryEvidence:
    """Repository-backed confirmation associated with exactly one Action."""

    action_id: str
    repository_revision: str
    report_id: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.action_id, self.repository_revision, self.report_id, self.content_digest)):
            raise ValueError("repository evidence action, revision, report, and digest are required")
        digest = self.content_digest.removeprefix("sha256:")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64:
            raise ValueError("repository evidence digest must be sha256")


@dataclass(frozen=True)
class MissionProgress:
    """Evidence-derived Mission progress; no inferred completion is permitted."""

    total_actions: int
    completed_actions: int
    current_intent_id: str | None
    current_action_id: str | None
    terminal_state: EngineeringActionStatus | None

    @property
    def percent_complete(self) -> int:
        return (self.completed_actions * 100) // self.total_actions


class BootstrapMissionScheduler:
    """Select and advance Actions in a stable order, without performing work."""

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
        by_id = {action.id: action for action in actions}
        for action in sorted(actions):
            if action.status is EngineeringActionStatus.READY and all(
                by_id[dependency].status is EngineeringActionStatus.COMPLETE for dependency in action.dependencies
            ):
                return action
        return None

    def activate(self, actions: tuple[EngineeringAction, ...]) -> tuple[EngineeringAction, ...]:
        action = self.next_action(actions)
        if action is None:
            raise ValueError("no evidence-eligible Engineering Action is ready")
        return self._replace(actions, action.id, EngineeringActionStatus.ACTIVE)

    def await_result(self, actions: tuple[EngineeringAction, ...], action_id: str) -> tuple[EngineeringAction, ...]:
        action = self._by_id(actions, action_id)
        if action.status is not EngineeringActionStatus.ACTIVE:
            raise ValueError("only the active Engineering Action can await a result")
        return self._replace(actions, action_id, EngineeringActionStatus.WAITING_FOR_RESULT)

    def complete(self, actions: tuple[EngineeringAction, ...], action_id: str, evidence: tuple[RepositoryEvidence, ...]) -> tuple[EngineeringAction, ...]:
        action = self._by_id(actions, action_id)
        if action.status is not EngineeringActionStatus.WAITING_FOR_RESULT:
            raise ValueError("only a waiting Engineering Action can complete")
        if not any(item.action_id == action_id for item in evidence):
            raise ValueError("repository evidence must confirm the Engineering Action before progression")
        return self._replace(actions, action_id, EngineeringActionStatus.COMPLETE)

    def stop(self, actions: tuple[EngineeringAction, ...], action_id: str, status: EngineeringActionStatus) -> tuple[EngineeringAction, ...]:
        if status not in {EngineeringActionStatus.BLOCKED, EngineeringActionStatus.FAILED}:
            raise ValueError("only blocked or failed results stop a Mission")
        action = self._by_id(actions, action_id)
        if action.status is not EngineeringActionStatus.WAITING_FOR_RESULT:
            raise ValueError("only a waiting Engineering Action can stop a Mission")
        return self._replace(actions, action_id, status)

    def progress(self, actions: tuple[EngineeringAction, ...]) -> MissionProgress:
        self._validate(actions)
        current = next((action for action in actions if action.status in {EngineeringActionStatus.ACTIVE, EngineeringActionStatus.WAITING_FOR_RESULT}), None)
        terminal = next((action.status for action in actions if action.status in {EngineeringActionStatus.BLOCKED, EngineeringActionStatus.FAILED}), None)
        return MissionProgress(len(actions), sum(action.status is EngineeringActionStatus.COMPLETE for action in actions), None if current is None else current.intent_id, None if current is None else current.id, terminal)

    @staticmethod
    def _by_id(actions: tuple[EngineeringAction, ...], action_id: str) -> EngineeringAction:
        for action in actions:
            if action.id == action_id:
                return action
        raise ValueError("Engineering Action is not in the Mission")

    @staticmethod
    def _replace(actions: tuple[EngineeringAction, ...], action_id: str, status: EngineeringActionStatus) -> tuple[EngineeringAction, ...]:
        return tuple(replace(action, status=status) if action.id == action_id else action for action in actions)
