"""Immutable, non-executing Runtime Prompt Generation contracts.

Runtime Prompts are provider-specific, transient derivations of an approved
Engineering Intent.  These contracts deliberately model no provider template,
provider invocation, persistence, queue, or execution host.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .action import EngineeringAction, EngineeringActionStatus
from .intent import EngineeringIntent, IntentReference, IntentStatus
from .producer import DEFAULT_FORGE_PRODUCER, ProducerIdentity


RUNTIME_PROMPT_SCHEMA_VERSION = "1.9"


class RuntimePromptSectionKind(str, Enum):
    """The provider-neutral structure every generated prompt must retain."""

    CONTEXT = "Context"
    OBJECTIVE = "Objective"
    REPOSITORY = "Repository"
    CONSTRAINTS = "Constraints"
    VALIDATION = "Validation"
    DELIVERABLES = "Deliverables"


@dataclass(frozen=True, order=True)
class ProviderPromptDefinition:
    """Identity and version of a future provider-specific prompt definition.

    It is provenance only in Increment 1.9.  It does not carry a template or
    provider implementation.
    """

    id: str
    version: str

    def __post_init__(self) -> None:
        if not self.id or not self.version:
            raise ValueError("provider prompt definition identity and version are required")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "version": self.version}


@dataclass(frozen=True)
class RuntimePromptGenerationContext:
    """Versioned Forge-owned context required to derive a Runtime Prompt."""

    repository: tuple[IntentReference, ...]
    architecture_handbook: tuple[IntentReference, ...]
    constitution: tuple[IntentReference, ...]
    workspace: tuple[IntentReference, ...]
    capabilities: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        for references, label in (
            (self.repository, "repository"),
            (self.architecture_handbook, "architecture handbook"),
            (self.constitution, "constitution"),
            (self.workspace, "workspace"),
            (self.capabilities, "capability"),
        ):
            if not references:
                raise ValueError(f"runtime prompt {label} context is required")
            if len(references) != len(set(references)):
                raise ValueError(f"runtime prompt {label} references must be unique")
        object.__setattr__(self, "repository", tuple(sorted(self.repository)))
        object.__setattr__(self, "architecture_handbook", tuple(sorted(self.architecture_handbook)))
        object.__setattr__(self, "constitution", tuple(sorted(self.constitution)))
        object.__setattr__(self, "workspace", tuple(sorted(self.workspace)))
        object.__setattr__(self, "capabilities", tuple(sorted(self.capabilities)))

    def to_dict(self) -> dict[str, list[dict[str, str]]]:
        return {
            "repository": [reference.to_dict() for reference in self.repository],
            "architecture_handbook": [reference.to_dict() for reference in self.architecture_handbook],
            "constitution": [reference.to_dict() for reference in self.constitution],
            "workspace": [reference.to_dict() for reference in self.workspace],
            "capabilities": [reference.to_dict() for reference in self.capabilities],
        }


@dataclass(frozen=True)
class RuntimePromptGenerationRequest:
    """An immutable released Action, its Intent provenance, and generation inputs."""

    intent: EngineeringIntent
    action: EngineeringAction
    provider_definition: ProviderPromptDefinition
    context: RuntimePromptGenerationContext
    constraints: tuple[str, ...]
    validation: tuple[str, ...]
    deliverables: tuple[str, ...]
    schema_version: str = RUNTIME_PROMPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_PROMPT_SCHEMA_VERSION:
            raise ValueError("runtime prompt generation schema version is unsupported")
        if self.intent.status is not IntentStatus.APPROVED:
            raise ValueError("runtime prompt source intent must be approved")
        if (self.action.intent_id, self.action.intent_revision) != (self.intent.id, self.intent.revision):
            raise ValueError("runtime prompt action must belong to the source intent revision")
        if self.action.status is not EngineeringActionStatus.ACTIVE:
            raise ValueError("runtime prompt source action must be active")
        for values, label in (
            (self.constraints, "constraint"),
            (self.validation, "validation"),
            (self.deliverables, "deliverable"),
        ):
            if not values or any(not value for value in values):
                raise ValueError(f"runtime prompt {label} values are required")
            if len(values) != len(set(values)):
                raise ValueError(f"runtime prompt {label} values must be unique")
            object.__setattr__(self, label + "s" if label != "validation" else label, tuple(sorted(values)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "intent": self.intent.to_dict(),
            "action": self.action.to_dict(),
            "provider_definition": self.provider_definition.to_dict(),
            "context": self.context.to_dict(),
            "constraints": list(self.constraints),
            "validation": list(self.validation),
            "deliverables": list(self.deliverables),
        }

    def digest(self) -> str:
        """Return the stable provenance digest of the complete request."""

        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class RuntimePromptSection:
    """One required abstract prompt section, with declared source references."""

    kind: RuntimePromptSectionKind
    content: tuple[str, ...]
    references: tuple[IntentReference, ...] = ()

    def __post_init__(self) -> None:
        if not self.content or any(not item for item in self.content):
            raise ValueError("runtime prompt section content is required")
        if len(self.content) != len(set(self.content)):
            raise ValueError("runtime prompt section content must be unique")
        if len(self.references) != len(set(self.references)):
            raise ValueError("runtime prompt section references must be unique")
        object.__setattr__(self, "content", tuple(sorted(self.content)))
        object.__setattr__(self, "references", tuple(sorted(self.references)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "content": list(self.content),
            "references": [reference.to_dict() for reference in self.references],
        }


@dataclass(frozen=True)
class RuntimePrompt:
    """A provider-specific, transient, derived prompt representation."""

    id: str
    source_intent_id: str
    source_intent_revision: str
    source_action_id: str
    provider_definition: ProviderPromptDefinition
    generation_request_digest: str
    sections: tuple[RuntimePromptSection, ...]
    schema_version: str = RUNTIME_PROMPT_SCHEMA_VERSION
    producer_identity: ProducerIdentity = DEFAULT_FORGE_PRODUCER.identity
    correlation_id: str = ""
    mission_id: str | None = None
    execution_metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_PROMPT_SCHEMA_VERSION:
            raise ValueError("runtime prompt schema version is unsupported")
        if not all((self.id, self.source_intent_id, self.source_intent_revision, self.source_action_id, self.generation_request_digest)):
            raise ValueError("runtime prompt identity and provenance are required")
        if not self.generation_request_digest.startswith("sha256:"):
            raise ValueError("runtime prompt provenance digest must be a sha256 digest")
        kinds = tuple(section.kind for section in self.sections)
        if len(kinds) != len(set(kinds)):
            raise ValueError("runtime prompt sections must be unique")
        missing = set(RuntimePromptSectionKind).difference(kinds)
        if missing:
            labels = ", ".join(sorted(kind.value for kind in missing))
            raise ValueError(f"runtime prompt is missing required sections: {labels}")
        object.__setattr__(self, "sections", tuple(sorted(self.sections, key=lambda section: section.kind.value)))
        if not self.correlation_id:
            seed = f"{self.id}:{self.source_intent_id}:{self.source_intent_revision}:{self.source_action_id}"
            object.__setattr__(self, "correlation_id", "runtime-" + hashlib.sha256(seed.encode()).hexdigest()[:16])
        metadata = tuple(sorted(self.execution_metadata)) or (
            ("provider_definition", self.provider_definition.id),
            ("provider_version", self.provider_definition.version),
        )
        if any(not key or not value for key, value in metadata) or len({key for key, _ in metadata}) != len(metadata):
            raise ValueError("runtime prompt execution metadata keys and values must be unique and non-empty")
        object.__setattr__(self, "execution_metadata", metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "source_intent": {"id": self.source_intent_id, "revision": self.source_intent_revision},
            "source_action": {"id": self.source_action_id},
            "producer": self.producer_identity.to_dict(),
            "correlation_id": self.correlation_id,
            "mission_id": self.mission_id,
            "execution_metadata": {key: value for key, value in self.execution_metadata},
            "execution_constraints": list(next(
                section.content for section in self.sections
                if section.kind is RuntimePromptSectionKind.CONSTRAINTS
            )),
            "provider_definition": self.provider_definition.to_dict(),
            "generation_request_digest": self.generation_request_digest,
            "derived": True,
            "transient": True,
            "sections": [section.to_dict() for section in self.sections],
        }

    def to_markdown(self) -> str:
        """Render only the abstract canonical section structure."""

        lines = [f"# Runtime Prompt: {self.id}", ""]
        for section in self.sections:
            lines.extend((f"## {section.kind.value}", ""))
            lines.extend(f"- {item}" for item in section.content)
            if section.references:
                lines.extend(("", "References:"))
                lines.extend(f"- {reference.id} ({reference.version})" for reference in section.references)
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"
