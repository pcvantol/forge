"""CLI-owned deterministic admission of one approved Mission into Mission State."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from forge.models.action import EngineeringAction
from forge.models.intent import EngineeringIntent, IntentStatus
from forge.models.mission import EngineeringMission, MissionStatus
from forge.state import MissionExecutionState, MissionStateStore


class MissionIntakeError(ValueError):
    """Raised when a Mission is not an approved, executable bounded contract."""


@dataclass(frozen=True)
class MissionIntake:
    """Validate one human-approved Mission and create its durable state once.

    Intake is deliberately a boundary: it creates no Mission, Intent, Action,
    approval, or Runtime Prompt.  Planning remains an injected, bounded input.
    """

    store: MissionStateStore
    clock: Callable[[], str]

    def admit(
        self,
        mission: EngineeringMission,
        intents: Sequence[EngineeringIntent],
        actions: Sequence[EngineeringAction],
    ) -> MissionExecutionState:
        if mission.status is not MissionStatus.ACTIVE:
            raise MissionIntakeError("Mission Intake requires an approved active Mission")
        memberships = {(item.intent_id, item.intent_revision) for item in mission.intents}
        supplied = {(item.id, item.revision) for item in intents}
        if memberships != supplied or len(intents) != 1 or len(actions) != 1:
            raise MissionIntakeError("Bootstrap Mission Intake requires exactly one pinned Intent and Action")
        intent = intents[0]
        action = actions[0]
        if intent.status is not IntentStatus.APPROVED:
            raise MissionIntakeError("Mission Intake requires an approved Engineering Intent")
        if (action.intent_id, action.intent_revision) != (intent.id, intent.revision):
            raise MissionIntakeError("Mission Intake Action must belong to the admitted Intent")
        return self.store.create(mission, intents, actions, occurred_at=self.clock(), resume={"intake": "forge-cli-v1"})
