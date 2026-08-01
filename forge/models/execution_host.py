"""Immutable, non-executing contracts for replaceable Execution Hosts.

Forge owns the engineering reasoning that produces a Runtime Prompt.  An
Execution Host owns the operational work around delivery to an execution
runtime and returns evidence for Forge to interpret.  These declarations do
not implement a host, transport, runtime, repository operation, or telemetry
service.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


EXECUTION_HOST_CONTRACT_SCHEMA_VERSION = "2.1"


class ExecutionHostResponsibility(str, Enum):
    """Operational responsibilities owned by every conforming host."""

    EXECUTION = "execution"
    PROMPT_DELIVERY = "prompt_delivery"
    RUNTIME_INVOCATION = "runtime_invocation"
    CHECKPOINTS = "checkpoints"
    REPORTS = "reports"
    LOGS = "logs"
    OBSERVABILITY = "observability"
    RETRIES = "retries"
    CLEANUP = "cleanup"
    QUALIFICATION = "qualification"
    EXECUTION_EVIDENCE = "execution_evidence"


class ExecutionHostForbiddenResponsibility(str, Enum):
    """Concerns a host must never own or interpret."""

    ARCHITECTURE = "architecture"
    ENGINEERING_KNOWLEDGE = "engineering_knowledge"
    ENGINEERING_INTENT = "engineering_intent"
    ROADMAP = "roadmap"
    CAPABILITY_EVOLUTION = "capability_evolution"
    GOVERNANCE = "governance"


class ExecutionHostLifecycleStage(str, Enum):
    """The host-owned operational lifecycle, independent of its transport."""

    QUALIFIED = "qualified"
    PROMPT_RECEIVED = "prompt_received"
    PROMPT_DELIVERED = "prompt_delivered"
    RUNTIME_INVOKED = "runtime_invoked"
    CHECKPOINT_RECORDED = "checkpoint_recorded"
    EVIDENCE_COLLECTED = "evidence_collected"
    EVIDENCE_RETURNED = "evidence_returned"
    CLEANED_UP = "cleaned_up"


class ExecutionEvidenceOutcome(str, Enum):
    """Host-reported operational outcome; Forge determines its meaning."""

    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionHostContract:
    """A self-declared, complete host contract without a host implementation."""

    host_id: str
    version: str
    responsibilities: tuple[ExecutionHostResponsibility, ...]
    forbidden_responsibilities: tuple[ExecutionHostForbiddenResponsibility, ...]
    lifecycle: tuple[ExecutionHostLifecycleStage, ...]
    schema_version: str = EXECUTION_HOST_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTION_HOST_CONTRACT_SCHEMA_VERSION:
            raise ValueError("execution host contract schema version is unsupported")
        if not self.host_id or not self.version:
            raise ValueError("execution host contract identity and version are required")
        if set(self.responsibilities) != set(ExecutionHostResponsibility):
            raise ValueError("execution host contract must declare every required responsibility")
        if set(self.forbidden_responsibilities) != set(ExecutionHostForbiddenResponsibility):
            raise ValueError("execution host contract must declare every forbidden responsibility")
        if set(self.lifecycle) != set(ExecutionHostLifecycleStage):
            raise ValueError("execution host contract must declare every lifecycle stage")
        object.__setattr__(self, "responsibilities", tuple(sorted(self.responsibilities, key=lambda item: item.value)))
        object.__setattr__(self, "forbidden_responsibilities", tuple(sorted(self.forbidden_responsibilities, key=lambda item: item.value)))
        object.__setattr__(self, "lifecycle", tuple(sorted(self.lifecycle, key=lambda item: item.value)))


@dataclass(frozen=True)
class ExecutionRepositoryEvidence:
    """The repository observation a host returns; it never interprets it."""

    action_id: str
    runtime_prompt_id: str
    execution_id: str
    repository_id: str
    repository_revision: str
    report_id: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((
            self.action_id, self.runtime_prompt_id, self.execution_id,
            self.repository_id, self.repository_revision, self.report_id,
            self.content_digest,
        )):
            raise ValueError("repository evidence identity, provenance, revision, report, and digest are required")
        digest = self.content_digest.removeprefix("sha256:")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64:
            raise ValueError("repository evidence digest must be sha256")


@dataclass(frozen=True)
class ExecutionHostEvidence:
    """A host-owned report envelope returned to Forge for interpretation."""

    host_id: str
    execution_id: str
    report_id: str
    outcome: ExecutionEvidenceOutcome
    repository_evidence: ExecutionRepositoryEvidence
    log_references: tuple[str, ...]
    diagnostic_references: tuple[str, ...]
    metric_references: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.host_id or not self.execution_id or not self.report_id:
            raise ValueError("execution host evidence identity and report are required")
        if self.repository_evidence.execution_id != self.execution_id:
            raise ValueError("execution host evidence must match its repository evidence execution")
        if self.repository_evidence.report_id != self.report_id:
            raise ValueError("execution host evidence must match its repository evidence report")
        for references, label in (
            (self.log_references, "log"),
            (self.diagnostic_references, "diagnostic"),
            (self.metric_references, "metric"),
        ):
            if any(not reference for reference in references) or len(references) != len(set(references)):
                raise ValueError(f"execution host evidence {label} references must be unique and non-empty")
        object.__setattr__(self, "log_references", tuple(sorted(self.log_references)))
        object.__setattr__(self, "diagnostic_references", tuple(sorted(self.diagnostic_references)))
        object.__setattr__(self, "metric_references", tuple(sorted(self.metric_references)))
