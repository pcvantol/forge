"""Bootstrap adapter boundary for the existing Engineering Platform interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.runtime_prompt import RuntimePrompt
from .scheduler import BootstrapMissionScheduler, RepositoryEvidence


class EngineeringPlatformInbox(Protocol):
    def submit(self, prompt: RuntimePrompt) -> None: ...


class ReportOutcome(str, Enum):
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class EngineeringPlatformReport:
    action_id: str
    report_id: str
    outcome: ReportOutcome


class BootstrapAdapter:
    """Translate only prompt delivery and reported evidence across the bootstrap boundary."""

    def __init__(self, inbox: EngineeringPlatformInbox, scheduler: BootstrapMissionScheduler | None = None) -> None:
        self._inbox = inbox
        self._scheduler = scheduler or BootstrapMissionScheduler()

    def release(self, actions: tuple[EngineeringAction, ...], prompt: RuntimePrompt) -> tuple[EngineeringAction, ...]:
        active = next((action for action in actions if action.status is EngineeringActionStatus.ACTIVE), None)
        if active is None or active.id != prompt.source_action_id:
            raise ValueError("only the active Engineering Action may release its Runtime Prompt")
        self._inbox.submit(prompt)
        return self._scheduler.await_result(actions, active.id)

    def reconcile(self, actions: tuple[EngineeringAction, ...], report: EngineeringPlatformReport, evidence: tuple[RepositoryEvidence, ...]) -> tuple[EngineeringAction, ...]:
        if report.outcome is ReportOutcome.COMPLETE:
            if not any(item.action_id == report.action_id and item.report_id == report.report_id for item in evidence):
                raise ValueError("a successful Engineering Platform report requires matching repository evidence")
            return self._scheduler.complete(actions, report.action_id, evidence)
        status = EngineeringActionStatus.BLOCKED if report.outcome is ReportOutcome.BLOCKED else EngineeringActionStatus.FAILED
        return self._scheduler.stop(actions, report.action_id, status)
