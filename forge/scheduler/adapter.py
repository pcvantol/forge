"""The sole Bootstrap Engineering Platform integration boundary.

All Inbox transport, host run identifiers, report retrieval, and terminal-state
translation remain here.  Forge's scheduler consumes only ``ExecutionHost``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from forge.models.execution_host import (
    ExecutionDispatch,
    ExecutionEvidenceOutcome,
    ExecutionHostEvidence,
    ExecutionRepositoryEvidence,
    ExecutionRequest,
)
from forge.models.runtime_prompt import RuntimePrompt


class EngineeringPlatformReportOutcome(str, Enum):
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class EngineeringPlatformInboxRequest:
    """Bootstrap transport payload, intentionally not part of the Forge contract."""

    prompt: RuntimePrompt
    correlation_id: str
    retry_of_correlation_id: str | None


@dataclass(frozen=True)
class EngineeringPlatformInboxReceipt:
    run_id: str

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("Engineering Platform Inbox receipt requires a run identity")


@dataclass(frozen=True)
class EngineeringPlatformReport:
    """Bootstrap-host report format; it is translated before scheduler use."""

    run_id: str
    report_id: str
    outcome: EngineeringPlatformReportOutcome
    repository_revision: str
    content_digest: str
    diagnostic_references: tuple[str, ...] = ()


class EngineeringPlatformInbox(Protocol):
    def submit(self, request: EngineeringPlatformInboxRequest) -> EngineeringPlatformInboxReceipt: ...


class EngineeringPlatformReportSource(Protocol):
    def report_for(self, run_id: str) -> EngineeringPlatformReport | None: ...


class BootstrapExecutionHostAdapter:
    """Translate the canonical host contract to Bootstrap Engineering Platform 1.5."""

    def __init__(self, inbox: EngineeringPlatformInbox, reports: EngineeringPlatformReportSource) -> None:
        self._inbox = inbox
        self._reports = reports
        self._dispatches: dict[str, ExecutionRequest] = {}

    def dispatch(self, request: ExecutionRequest) -> ExecutionDispatch:
        receipt = self._inbox.submit(EngineeringPlatformInboxRequest(
            prompt=request.runtime_prompt,
            correlation_id=request.correlation_id,
            retry_of_correlation_id=request.retry_of_correlation_id,
        ))
        if receipt.run_id in self._dispatches:
            raise ValueError("Engineering Platform run identity was already dispatched")
        self._dispatches[receipt.run_id] = request
        return ExecutionDispatch(request=request, host_run_id=receipt.run_id)

    def retrieve_evidence(self, dispatch: ExecutionDispatch) -> ExecutionHostEvidence | None:
        request = self._dispatches.get(dispatch.host_run_id)
        if request != dispatch.request:
            raise ValueError("unknown Bootstrap Engineering Platform dispatch")
        report = self._reports.report_for(dispatch.host_run_id)
        if report is None:
            return None
        if report.run_id != dispatch.host_run_id:
            raise ValueError("Engineering Platform report does not match its dispatched run")
        outcome = ExecutionEvidenceOutcome(report.outcome.value.lower())
        repository = ExecutionRepositoryEvidence(
            mission_id=request.mission_id,
            intent_id=request.intent_id,
            intent_revision=request.intent_revision,
            action_id=request.action_id,
            runtime_prompt_id=request.runtime_prompt.id,
            correlation_id=request.correlation_id,
            host_run_id=dispatch.host_run_id,
            repository_id=request.repository_id,
            repository_revision=report.repository_revision,
            report_id=report.report_id,
            content_digest=report.content_digest,
        )
        return ExecutionHostEvidence(
            host_id=request.host_id,
            correlation_id=request.correlation_id,
            host_run_id=dispatch.host_run_id,
            report_id=report.report_id,
            outcome=outcome,
            repository_evidence=repository,
            diagnostic_references=report.diagnostic_references,
            retry_of_correlation_id=request.retry_of_correlation_id,
        )
