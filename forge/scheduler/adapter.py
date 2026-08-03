"""The sole Bootstrap Engineering Platform integration boundary.

This module translates an immutable Codex CLI Runtime Prompt into an opaque
Engineering Platform 1.5 transaction.  It owns only deterministic mapping,
admission delegation, inbox transport, and evidence translation.  It does not
plan, render prompts, execute work, or interpret repository observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from forge.models.codex_runtime_prompt import CodexCliRuntimePrompt, ExecutionHostCompatibility
from forge.models.execution_host import (
    ExecutionDispatch,
    ExecutionEvidenceOutcome,
    ExecutionHostEvidence,
    ExecutionRepositoryEvidence,
    ExecutionRequest,
)


class EngineeringPlatformReportOutcome(str, Enum):
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ExecutionHostConfiguration:
    """Canonical, resolver-owned configuration for one execution host."""

    host_id: str
    host_contract_version: str
    supported_execution_modes: tuple[str, ...]
    supported_capabilities: tuple[str, ...]
    supported_runtime: str
    inbox_location: str

    def __post_init__(self) -> None:
        if not all((self.host_id, self.host_contract_version, self.supported_runtime, self.inbox_location)):
            raise ValueError("execution host configuration identity and transport location are required")
        for values, label in ((self.supported_execution_modes, "execution mode"), (self.supported_capabilities, "capability")):
            if not values or any(not value for value in values):
                raise ValueError(f"execution host configuration {label} values are required")
            if len(values) != len(set(values)):
                raise ValueError(f"execution host configuration {label} values must be unique")
            object.__setattr__(self, "supported_execution_modes" if label == "execution mode" else "supported_capabilities", tuple(sorted(values)))


class ExecutionHostConfigurationResolver(Protocol):
    """The canonical configuration authority; adapters never infer locations."""

    def resolve(self, host_id: str) -> ExecutionHostConfiguration: ...


class CapabilityPreflight(Protocol):
    """Host admission authority for compatibility, workspace, and capability gates."""

    def admit(self, compatibility: ExecutionHostCompatibility, configuration: ExecutionHostConfiguration) -> None: ...


@dataclass(frozen=True)
class EngineeringPlatformInboxRequest:
    """Adapter-local Engineering Platform transaction, never a Forge core contract."""

    engineering_prompt: str
    runtime_prompt_id: str
    runtime_prompt_digest: str
    mission_id: str
    mission_revision: str
    intent_id: str
    intent_revision: str
    action_id: str
    correlation_id: str
    original_correlation_id: str
    retry_of_correlation_id: str | None
    constraints: tuple[str, ...]
    validation: tuple[str, ...]
    compatibility: ExecutionHostCompatibility
    execution_host_id: str
    inbox_location: str


@dataclass(frozen=True)
class EngineeringPlatformInboxReceipt:
    run_id: str

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("Engineering Platform Inbox receipt requires a run identity")


@dataclass(frozen=True)
class EngineeringPlatformReport:
    """Adapter-local host report translated before it reaches Forge core."""

    run_id: str
    report_id: str
    outcome: EngineeringPlatformReportOutcome
    repository_revision: str
    content_digest: str
    validation_references: tuple[str, ...] = ()
    diagnostic_references: tuple[str, ...] = ()
    execution_started_at: str | None = None
    execution_completed_at: str | None = None


class EngineeringPlatformInbox(Protocol):
    def submit(self, request: EngineeringPlatformInboxRequest) -> EngineeringPlatformInboxReceipt: ...

    def receipt_for(self, correlation_id: str) -> EngineeringPlatformInboxReceipt | None: ...


class EngineeringPlatformReportSource(Protocol):
    def report_for(self, run_id: str) -> EngineeringPlatformReport | None: ...


class BootstrapExecutionHostAdapter:
    """Translate one Codex CLI Runtime Prompt through admission and inbox transport."""

    def __init__(
        self,
        configuration_resolver: ExecutionHostConfigurationResolver,
        preflight: CapabilityPreflight,
        inbox: EngineeringPlatformInbox,
        reports: EngineeringPlatformReportSource,
    ) -> None:
        self._configuration_resolver = configuration_resolver
        self._preflight = preflight
        self._inbox = inbox
        self._reports = reports

    @staticmethod
    def _prompt(request: ExecutionRequest) -> CodexCliRuntimePrompt:
        if not isinstance(request.runtime_prompt, CodexCliRuntimePrompt):
            raise ValueError("Bootstrap Execution Host Adapter requires a Codex CLI Runtime Prompt")
        prompt = request.runtime_prompt
        if (prompt.mission_id, prompt.intent_id, prompt.intent_revision, prompt.action_id) != (
            request.mission_id, request.intent_id, request.intent_revision, request.action_id,
        ):
            raise ValueError("Codex CLI Runtime Prompt must match the exact execution request")
        return prompt

    def dispatch(self, request: ExecutionRequest) -> ExecutionDispatch:
        prompt = self._prompt(request)
        recovered = self.recover_dispatch(request)
        if recovered is not None:
            return recovered
        configuration = self._configuration_resolver.resolve(request.host_id)
        self._preflight.admit(prompt.compatibility, configuration)
        original_correlation = request.original_correlation_id or request.correlation_id
        receipt = self._inbox.submit(EngineeringPlatformInboxRequest(
            engineering_prompt=prompt.rendered_text,
            runtime_prompt_id=prompt.id,
            runtime_prompt_digest=prompt.source_digest,
            mission_id=prompt.mission_id,
            mission_revision=prompt.mission_revision,
            intent_id=prompt.intent_id,
            intent_revision=prompt.intent_revision,
            action_id=prompt.action_id,
            correlation_id=request.correlation_id,
            original_correlation_id=original_correlation,
            retry_of_correlation_id=request.retry_of_correlation_id,
            constraints=prompt.constraints,
            validation=prompt.validation,
            compatibility=prompt.compatibility,
            execution_host_id=configuration.host_id,
            inbox_location=configuration.inbox_location,
        ))
        return ExecutionDispatch(request=request, host_run_id=receipt.run_id)

    def recover_dispatch(self, request: ExecutionRequest) -> ExecutionDispatch | None:
        """Recover a durable host acknowledgement without process-local state."""
        self._prompt(request)
        receipt = self._inbox.receipt_for(request.correlation_id)
        if receipt is None:
            return None
        return ExecutionDispatch(request=request, host_run_id=receipt.run_id)

    def retrieve_evidence(self, dispatch: ExecutionDispatch) -> ExecutionHostEvidence | None:
        prompt = self._prompt(dispatch.request)
        report = self._reports.report_for(dispatch.host_run_id)
        if report is None:
            return None
        if report.run_id != dispatch.host_run_id:
            raise ValueError("Engineering Platform report does not match its dispatched run")
        request = dispatch.request
        repository = ExecutionRepositoryEvidence(
            mission_id=request.mission_id,
            intent_id=request.intent_id,
            intent_revision=request.intent_revision,
            action_id=request.action_id,
            runtime_prompt_id=prompt.id,
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
            outcome=ExecutionEvidenceOutcome(report.outcome.value.lower()),
            repository_evidence=repository,
            validation_references=report.validation_references,
            diagnostic_references=report.diagnostic_references,
            retry_of_correlation_id=request.retry_of_correlation_id,
            original_correlation_id=request.original_correlation_id,
            execution_started_at=report.execution_started_at,
            execution_completed_at=report.execution_completed_at,
        )
