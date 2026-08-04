"""Provider-neutral, immutable contracts for replaceable Execution Hosts.

Forge owns Mission scheduling and engineering reasoning.  An Execution Host
owns delivery, runtime execution, operational retries, and evidence return.
Nothing in this module describes a particular host transport or report format.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .producer import DEFAULT_FORGE_PRODUCER, Producer, ProducerContract, RuntimePromptEnvelope


EXECUTION_HOST_CONTRACT_SCHEMA_VERSION = "3.0"


class ExecutionHostResponsibility(str, Enum):
    EXECUTION = "execution"
    EXECUTION_RECEIPTS = "execution_receipts"
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
    MISSION_PLANNING = "mission_planning"
    BUSINESS_GOVERNANCE = "business_governance"
    ARCHITECTURE_GOVERNANCE = "architecture_governance"
    PRODUCER_IMPLEMENTATION = "producer_implementation"
    FORGE_IMPLEMENTATION = "forge_implementation"
    ARCHITECTURE = "architecture"
    ENGINEERING_KNOWLEDGE = "engineering_knowledge"
    ENGINEERING_INTENT = "engineering_intent"
    ROADMAP = "roadmap"
    CAPABILITY_EVOLUTION = "capability_evolution"
    GOVERNANCE = "governance"
    AGENT_ROLE_SELECTION = "agent_role_selection"
    MODEL_PROFILE_SELECTION = "model_profile_selection"
    REASONING_PROFILE_SELECTION = "reasoning_profile_selection"
    EXECUTION_HOST_SELECTION = "execution_host_selection"


class ExecutionHostLifecycleStage(str, Enum):
    QUALIFIED = "qualified"
    PROMPT_RECEIVED = "prompt_received"
    PROMPT_DELIVERED = "prompt_delivered"
    RUNTIME_INVOKED = "runtime_invoked"
    CHECKPOINT_RECORDED = "checkpoint_recorded"
    EVIDENCE_COLLECTED = "evidence_collected"
    EVIDENCE_RETURNED = "evidence_returned"
    CLEANED_UP = "cleaned_up"


class ExecutionEvidenceOutcome(str, Enum):
    COMPLETE = "complete"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class ExecutionHostContract:
    """A complete host declaration without a host implementation."""

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
class ExecutionRequest:
    """One exact Producer-to-host request.  Hosts consume its Producer Contract."""

    host_id: str
    mission_id: str
    intent_id: str
    intent_revision: str
    action_id: str
    runtime_prompt: Any
    workspace_id: str
    repository_id: str
    correlation_id: str
    dispatched_at: str
    retry_of_correlation_id: str | None = None
    original_correlation_id: str | None = None
    producer_contract: ProducerContract | None = None

    def __post_init__(self) -> None:
        if not all((self.host_id, self.mission_id, self.intent_id, self.intent_revision,
                    self.action_id, self.workspace_id, self.repository_id,
                    self.correlation_id, self.dispatched_at)):
            raise ValueError("execution request identity, context, correlation, and dispatch time are required")
        prompt_identity = (
            getattr(self.runtime_prompt, "source_intent_id", getattr(self.runtime_prompt, "intent_id", None)),
            getattr(self.runtime_prompt, "source_intent_revision", getattr(self.runtime_prompt, "intent_revision", None)),
            getattr(self.runtime_prompt, "source_action_id", getattr(self.runtime_prompt, "action_id", None)),
        )
        if prompt_identity != (self.intent_id, self.intent_revision, self.action_id):
            raise ValueError("execution request Runtime Prompt must match its Intent and Action")
        if self.retry_of_correlation_id == self.correlation_id:
            raise ValueError("execution request cannot retry its own correlation")
        if self.original_correlation_id == self.correlation_id:
            raise ValueError("execution request original correlation must precede a retry")
        if self.retry_of_correlation_id and not self.original_correlation_id:
            object.__setattr__(self, "original_correlation_id", self.retry_of_correlation_id)
        if self.original_correlation_id and not self.retry_of_correlation_id:
            raise ValueError("execution request original correlation requires a retry predecessor")
        contract = self.producer_contract or self._default_producer_contract()
        if (contract.correlation_id, contract.mission_id, contract.engineering_action_id) != (
            self.correlation_id, self.mission_id, self.action_id,
        ):
            raise ValueError("execution request Producer Contract must match its mission, action, and correlation")
        if contract.runtime_prompt.id != getattr(self.runtime_prompt, "id", None):
            raise ValueError("execution request Producer Contract must match its Runtime Prompt")
        object.__setattr__(self, "producer_contract", contract)

    def _default_producer_contract(self) -> ProducerContract:
        """Bridge legacy in-process prompt objects into the canonical envelope."""
        content = getattr(self.runtime_prompt, "rendered_text", None)
        if content is None:
            content = self.runtime_prompt.to_markdown()
        digest = getattr(self.runtime_prompt, "source_digest", None) or getattr(
            self.runtime_prompt, "generation_request_digest", None
        )
        constraints = tuple(getattr(self.runtime_prompt, "constraints", ()))
        if not constraints:
            constraints = tuple(self.runtime_prompt.to_dict().get("execution_constraints", ()))
        constraints = constraints or ("Execute only the supplied Runtime Prompt.",)
        prompt_producer = getattr(self.runtime_prompt, "producer_identity", DEFAULT_FORGE_PRODUCER.identity)
        metadata = tuple(getattr(self.runtime_prompt, "execution_metadata", ())) + (
            ("intent_id", self.intent_id),
            ("intent_revision", self.intent_revision),
            ("repository_id", self.repository_id),
            ("workspace_id", self.workspace_id),
        )
        return ProducerContract(
            producer=Producer(prompt_producer),
            correlation_id=self.correlation_id,
            mission_id=self.mission_id,
            engineering_action_id=self.action_id,
            runtime_prompt=RuntimePromptEnvelope(
                id=str(getattr(self.runtime_prompt, "id")),
                version=str(getattr(self.runtime_prompt, "schema_version", "1.0")),
                format="text/markdown",
                content=content,
                content_digest=str(digest),
            ),
            execution_constraints=constraints,
            execution_metadata=metadata,
        )


@dataclass(frozen=True)
class ExecutionDispatch:
    """The host acknowledgement binding a request to one immutable host run."""

    request: ExecutionRequest
    host_run_id: str

    def __post_init__(self) -> None:
        if not self.host_run_id:
            raise ValueError("execution dispatch host run identity is required")


@dataclass(frozen=True)
class ExecutionRepositoryEvidence:
    """Repository observation bound to one request correlation and host run."""

    mission_id: str
    intent_id: str
    intent_revision: str
    action_id: str
    runtime_prompt_id: str
    correlation_id: str
    host_run_id: str
    repository_id: str
    repository_revision: str
    report_id: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.mission_id, self.intent_id, self.intent_revision, self.action_id,
                    self.runtime_prompt_id, self.correlation_id, self.host_run_id,
                    self.repository_id, self.repository_revision, self.report_id,
                    self.content_digest)):
            raise ValueError("repository evidence identity, provenance, revision, report, and digest are required")
        digest = self.content_digest.removeprefix("sha256:")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64:
            raise ValueError("repository evidence digest must be sha256")


@dataclass(frozen=True)
class ExecutionHostEvidence:
    """Terminal host evidence; all identity must match the exact dispatched run."""

    host_id: str
    correlation_id: str
    host_run_id: str
    report_id: str
    outcome: ExecutionEvidenceOutcome
    repository_evidence: ExecutionRepositoryEvidence
    log_references: tuple[str, ...] = ()
    diagnostic_references: tuple[str, ...] = ()
    metric_references: tuple[str, ...] = ()
    validation_references: tuple[str, ...] = ()
    retry_of_correlation_id: str | None = None
    original_correlation_id: str | None = None
    execution_started_at: str | None = None
    execution_completed_at: str | None = None
    receipt_id: str | None = None
    execution_duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not all((self.host_id, self.correlation_id, self.host_run_id, self.report_id)):
            raise ValueError("execution host evidence identity and report are required")
        repository = self.repository_evidence
        if (repository.correlation_id, repository.host_run_id, repository.report_id) != (
            self.correlation_id, self.host_run_id, self.report_id,
        ):
            raise ValueError("execution host evidence must match its repository evidence run and report")
        for references, label in ((self.log_references, "log"), (self.diagnostic_references, "diagnostic"), (self.metric_references, "metric"), (self.validation_references, "validation")):
            if any(not reference for reference in references) or len(references) != len(set(references)):
                raise ValueError(f"execution host evidence {label} references must be unique and non-empty")
            object.__setattr__(self, f"{label}_references", tuple(sorted(references)))
        if self.retry_of_correlation_id and not self.original_correlation_id:
            object.__setattr__(self, "original_correlation_id", self.retry_of_correlation_id)
        if self.execution_completed_at and not self.execution_started_at:
            raise ValueError("execution completion time requires an execution start time")
        if self.receipt_id is not None and not self.receipt_id:
            raise ValueError("execution host evidence receipt identity cannot be empty")
        if self.execution_duration_ms is not None and self.execution_duration_ms < 0:
            raise ValueError("execution host evidence duration cannot be negative")


class ExecutionHost(Protocol):
    """The sole provider-neutral operational boundary used by the runtime.

    ``dispatch`` is idempotent for an exact request correlation.  A host must
    retain sufficient operational state for ``recover_dispatch`` to return the
    original acknowledgement after a Runner restart.  This lets Forge persist
    a request before dispatching it without treating process memory as state.
    """

    def dispatch(self, request: ExecutionRequest) -> ExecutionDispatch: ...

    def recover_dispatch(self, request: ExecutionRequest) -> ExecutionDispatch | None: ...

    def retrieve_evidence(self, dispatch: ExecutionDispatch) -> ExecutionHostEvidence | None: ...
