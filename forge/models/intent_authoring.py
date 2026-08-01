"""Pure, local contracts for authoring an Engineering Intent from repository knowledge.

This module validates declared authoring context only.  It does not read a
repository, create an Engineering Intent, generate a prompt, invoke a Runtime
Provider, or execute work.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .intent import IntentReference


ENGINEERING_INTENT_AUTHORING_SCHEMA_VERSION = "1.4"


class AuthoringSourceKind(str, Enum):
    """Repository-held source classes required to author a future Intent."""

    CONSTITUTION = "constitution"
    ARCHITECTURE_HANDBOOK = "architecture_handbook"
    ROADMAP = "roadmap"
    EXISTING_ENGINEERING_INTENTS = "existing_engineering_intents"
    REPOSITORY_EVIDENCE = "repository_evidence"
    CAPABILITY_CATALOGUE = "capability_catalogue"
    KNOWLEDGE_MODEL = "knowledge_model"


@dataclass(frozen=True)
class AuthoringSource:
    """Versioned references for one required authoring source class."""

    kind: AuthoringSourceKind
    references: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.references:
            raise ValueError("authoring source references are required")
        if len(self.references) != len(set(self.references)):
            raise ValueError("authoring source references must be unique")
        object.__setattr__(self, "references", tuple(sorted(self.references)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "references": [reference.to_dict() for reference in self.references],
        }


@dataclass(frozen=True)
class EngineeringIntentAuthoringContext:
    """Immutable declared context from which a human may author one Intent."""

    objective: str
    rationale: str
    sources: tuple[AuthoringSource, ...]
    affected_capabilities: tuple[IntentReference, ...]
    architecture_references: tuple[IntentReference, ...]
    constitutional_articles: tuple[IntentReference, ...]
    expected_evidence: tuple[IntentReference, ...]
    validation: tuple[IntentReference, ...]
    schema_version: str = ENGINEERING_INTENT_AUTHORING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENGINEERING_INTENT_AUTHORING_SCHEMA_VERSION:
            raise ValueError("engineering intent authoring schema version is unsupported")
        if not self.objective or not self.rationale:
            raise ValueError("authoring objective and rationale are required")
        if not self.affected_capabilities:
            raise ValueError("affected capability references are required")
        if not self.architecture_references:
            raise ValueError("architecture references are required")
        if not self.expected_evidence:
            raise ValueError("expected evidence references are required")
        if not self.validation:
            raise ValueError("validation references are required")

        source_kinds = tuple(source.kind for source in self.sources)
        if len(source_kinds) != len(set(source_kinds)):
            raise ValueError("authoring source classes must be unique")
        missing = set(AuthoringSourceKind).difference(source_kinds)
        if missing:
            labels = ", ".join(sorted(kind.value for kind in missing))
            raise ValueError(f"authoring context is missing required source classes: {labels}")

        for references, label in (
            (self.affected_capabilities, "affected capability"),
            (self.architecture_references, "architecture"),
            (self.constitutional_articles, "constitutional article"),
            (self.expected_evidence, "expected evidence"),
            (self.validation, "validation"),
        ):
            if len(references) != len(set(references)):
                raise ValueError(f"{label} references must be unique")

        object.__setattr__(self, "sources", tuple(sorted(self.sources, key=lambda source: source.kind.value)))
        object.__setattr__(self, "affected_capabilities", tuple(sorted(self.affected_capabilities)))
        object.__setattr__(self, "architecture_references", tuple(sorted(self.architecture_references)))
        object.__setattr__(self, "constitutional_articles", tuple(sorted(self.constitutional_articles)))
        object.__setattr__(self, "expected_evidence", tuple(sorted(self.expected_evidence)))
        object.__setattr__(self, "validation", tuple(sorted(self.validation)))

    def to_dict(self) -> dict[str, Any]:
        """Serialize a stable, provider-independent authoring declaration."""

        return {
            "schema_version": self.schema_version,
            "objective": self.objective,
            "rationale": self.rationale,
            "sources": [source.to_dict() for source in self.sources],
            "affected_capabilities": [reference.to_dict() for reference in self.affected_capabilities],
            "architecture_references": [reference.to_dict() for reference in self.architecture_references],
            "constitutional_articles": [reference.to_dict() for reference in self.constitutional_articles],
            "expected_evidence": [reference.to_dict() for reference in self.expected_evidence],
            "validation": [reference.to_dict() for reference in self.validation],
        }
