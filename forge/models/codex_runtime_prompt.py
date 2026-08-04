"""Immutable contracts for deterministic Codex CLI Runtime Prompt rendering.

This module is a presentation boundary only.  It validates a Mission-pinned
Engineering Action and records exactly the data an Execution Host needs to
preflight and deliver a Codex CLI prompt; it performs no planning, I/O, or
execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .action import EngineeringAction, EngineeringActionStatus
from .intent import EngineeringIntent, IntentStatus
from .mission import EngineeringMission
from .agent_policy import AgentPolicySelection
from .producer import DEFAULT_FORGE_PRODUCER, ProducerIdentity


CODEX_CLI_RUNTIME_PROMPT_SCHEMA_VERSION = "3.3"
CODEX_CLI_RENDERER_VERSION = "3.3.0"


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class RepositoryState:
    """The caller-captured immutable repository snapshot used for rendering."""

    repository_id: str
    revision: str
    state_digest: str
    captured_at: str

    def __post_init__(self) -> None:
        if not all((self.repository_id, self.revision, self.state_digest, self.captured_at)):
            raise ValueError("repository state identity, revision, digest, and timestamp are required")
        if not self.state_digest.startswith("sha256:"):
            raise ValueError("repository state digest must be a sha256 digest")

    def to_dict(self) -> dict[str, str]:
        return {
            "repository_id": self.repository_id,
            "revision": self.revision,
            "state_digest": self.state_digest,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True)
class ExecutionHostCompatibility:
    """Preflight requirements, declared without selecting a host implementation."""

    execution_host_contract_version: str
    execution_mode: str
    required_capabilities: tuple[str, ...]
    minimum_supported_runtime: str

    def __post_init__(self) -> None:
        if not all((self.execution_host_contract_version, self.execution_mode, self.minimum_supported_runtime)):
            raise ValueError("execution host compatibility metadata is required")
        if not self.required_capabilities or any(not item for item in self.required_capabilities):
            raise ValueError("execution host compatibility requires capabilities")
        if len(self.required_capabilities) != len(set(self.required_capabilities)):
            raise ValueError("execution host compatibility capabilities must be unique")
        object.__setattr__(self, "required_capabilities", tuple(sorted(self.required_capabilities)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_host_contract_version": self.execution_host_contract_version,
            "execution_mode": self.execution_mode,
            "required_capabilities": list(self.required_capabilities),
            "minimum_supported_runtime": self.minimum_supported_runtime,
        }


@dataclass(frozen=True)
class CodexCliRuntimePromptRequest:
    """All deterministic source material for one Codex CLI Runtime Prompt."""

    mission: EngineeringMission
    intent: EngineeringIntent
    action: EngineeringAction
    repository_state: RepositoryState
    constraints: tuple[str, ...]
    validation: tuple[str, ...]
    compatibility: ExecutionHostCompatibility
    policy_selection: AgentPolicySelection | None = None
    renderer_version: str = CODEX_CLI_RENDERER_VERSION
    schema_version: str = CODEX_CLI_RUNTIME_PROMPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CODEX_CLI_RUNTIME_PROMPT_SCHEMA_VERSION:
            raise ValueError("Codex CLI Runtime Prompt schema version is unsupported")
        if self.renderer_version != CODEX_CLI_RENDERER_VERSION:
            raise ValueError("Codex CLI Runtime Prompt renderer version is unsupported")
        if self.intent.status is not IntentStatus.APPROVED:
            raise ValueError("Codex CLI Runtime Prompt source intent must be approved")
        if self.action.status is not EngineeringActionStatus.ACTIVE:
            raise ValueError("Codex CLI Runtime Prompt source action must be active")
        if (self.action.intent_id, self.action.intent_revision) != (self.intent.id, self.intent.revision):
            raise ValueError("Codex CLI Runtime Prompt action must belong to the source intent revision")
        if (self.intent.id, self.intent.revision) not in {
            (membership.intent_id, membership.intent_revision) for membership in self.mission.intents
        }:
            raise ValueError("Codex CLI Runtime Prompt intent must be pinned by the source mission")
        if self.policy_selection and (self.policy_selection.request.mission_id, self.policy_selection.request.action_id) != (self.mission.id, self.action.id):
            raise ValueError("Codex CLI Runtime Prompt policy selection must match its Mission and Action")
        for values, label in ((self.constraints, "constraint"), (self.validation, "validation")):
            if not values or any(not item for item in values):
                raise ValueError(f"Codex CLI Runtime Prompt {label} values are required")
            if len(values) != len(set(values)):
                raise ValueError(f"Codex CLI Runtime Prompt {label} values must be unique")
            object.__setattr__(self, f"{label}s" if label != "validation" else label, tuple(sorted(values)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "renderer_version": self.renderer_version,
            "mission": self.mission.to_dict(),
            "intent": self.intent.to_dict(),
            "action": self.action.to_dict(),
            "repository_state": self.repository_state.to_dict(),
            "constraints": list(self.constraints),
            "validation": list(self.validation),
            "compatibility": self.compatibility.to_dict(),
            "policy_selection_digest": self.policy_selection.digest() if self.policy_selection else None,
        }

    def digest(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True)
class CodexCliRuntimePrompt:
    """One immutable, execution-ready Codex CLI presentation of one Action."""

    id: str
    correlation_id: str
    renderer_version: str
    schema_version: str
    generated_at: str
    mission_id: str
    mission_revision: str
    intent_id: str
    intent_revision: str
    action_id: str
    repository_state: RepositoryState
    compatibility: ExecutionHostCompatibility
    policy_version: str | None
    policy_digest: str | None
    policy_execution_constraints: tuple[str, ...]
    objective: str
    expected_repository_evidence: tuple[str, ...]
    constraints: tuple[str, ...]
    validation: tuple[str, ...]
    source_digest: str
    rendered_text: str
    producer_identity: ProducerIdentity = DEFAULT_FORGE_PRODUCER.identity
    execution_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != CODEX_CLI_RUNTIME_PROMPT_SCHEMA_VERSION:
            raise ValueError("Codex CLI Runtime Prompt schema version is unsupported")
        if self.renderer_version != CODEX_CLI_RENDERER_VERSION:
            raise ValueError("Codex CLI Runtime Prompt renderer version is unsupported")
        if not all((self.id, self.correlation_id, self.generated_at, self.mission_id, self.mission_revision,
                    self.intent_id, self.intent_revision, self.action_id, self.objective, self.source_digest,
                    self.rendered_text)):
            raise ValueError("Codex CLI Runtime Prompt identity, provenance, and content are required")
        if not self.source_digest.startswith("sha256:"):
            raise ValueError("Codex CLI Runtime Prompt source digest must be a sha256 digest")
        if (self.policy_version is None) != (self.policy_digest is None):
            raise ValueError("Codex CLI Runtime Prompt policy version and digest must be paired")
        if self.policy_digest and not self.policy_digest.startswith("sha256:"):
            raise ValueError("Codex CLI Runtime Prompt policy digest must be a sha256 digest")
        if self.policy_execution_constraints and any(not item for item in self.policy_execution_constraints):
            raise ValueError("Codex CLI Runtime Prompt policy constraints must be non-empty")
        object.__setattr__(self, "policy_execution_constraints", tuple(sorted(self.policy_execution_constraints)))
        for values, label in ((self.expected_repository_evidence, "expected repository evidence"),
                              (self.constraints, "constraint"), (self.validation, "validation")):
            if not values or any(not item for item in values) or len(values) != len(set(values)):
                raise ValueError(f"Codex CLI Runtime Prompt {label} values must be unique and non-empty")
            object.__setattr__(self, "expected_repository_evidence" if label == "expected repository evidence" else ("constraints" if label == "constraint" else "validation"), tuple(sorted(values)))
        metadata = tuple(sorted(self.execution_metadata)) or (
            ("renderer_version", self.renderer_version),
            ("runtime_prompt_format", "codex_cli"),
        )
        if any(not key or not value for key, value in metadata) or len({key for key, _ in metadata}) != len(metadata):
            raise ValueError("Codex CLI Runtime Prompt execution metadata keys and values must be unique and non-empty")
        object.__setattr__(self, "execution_metadata", metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "renderer_version": self.renderer_version,
            "id": self.id,
            "correlation_id": self.correlation_id,
            "generated_at": self.generated_at,
            "mission": {"id": self.mission_id, "revision": self.mission_revision},
            "intent": {"id": self.intent_id, "revision": self.intent_revision},
            "action": {"id": self.action_id},
            "producer": self.producer_identity.to_dict(),
            "repository_state": self.repository_state.to_dict(),
            "compatibility": self.compatibility.to_dict(),
            "policy": None if self.policy_version is None else {
                "version": self.policy_version,
                "digest": self.policy_digest,
                "execution_constraints": list(self.policy_execution_constraints),
            },
            "objective": self.objective,
            "expected_repository_evidence": list(self.expected_repository_evidence),
            "constraints": list(self.constraints),
            "validation": list(self.validation),
            "execution_metadata": {key: value for key, value in self.execution_metadata},
            "source_digest": self.source_digest,
            "rendered_text": self.rendered_text,
            "derived": True,
            "immutable": True,
            "transient": True,
        }
