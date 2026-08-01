"""Immutable, non-executing contracts for AI Architect reasoning sessions.

Sessions bind complete Forge-owned context, one selected provider declaration,
and advisory output into a bounded architectural reasoning record.  They do
not invoke providers, approve recommendations, or execute engineering work.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from .ai_architect_provider import AIArchitectRequest, AIArchitectResult
from .intent import IntentReference


AI_ARCHITECT_SESSION_SCHEMA_VERSION = "1.8"


class AIArchitectSessionStatus(str, Enum):
    """The bounded advisory lifecycle of an AI Architect Session."""

    CREATED = "CREATED"
    PREPARED = "PREPARED"
    REASONING = "REASONING"
    REVIEW = "REVIEW"
    COMPLETE = "COMPLETE"
    ABANDONED = "ABANDONED"


@dataclass(frozen=True)
class RepositorySnapshot:
    """An immutable declaration of the repository state supplied to a session."""

    repository_id: str
    revision: str
    evidence_references: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        if not self.repository_id or not self.revision or not self.evidence_references:
            raise ValueError("repository snapshot identity, revision, and evidence are required")
        if len(self.evidence_references) != len(set(self.evidence_references)):
            raise ValueError("repository snapshot evidence references must be unique")
        object.__setattr__(self, "evidence_references", tuple(sorted(self.evidence_references)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_id": self.repository_id,
            "revision": self.revision,
            "evidence_references": [reference.to_dict() for reference in self.evidence_references],
        }


@dataclass(frozen=True)
class AIArchitectSession:
    """One bounded, human-governed architectural reasoning interaction."""

    id: str
    workspace_id: str
    provider_id: str
    provider_version: str
    objective: str
    request: AIArchitectRequest
    repository_snapshot: RepositorySnapshot
    constitutional_context: tuple[IntentReference, ...]
    architecture_context: tuple[IntentReference, ...]
    status: AIArchitectSessionStatus = AIArchitectSessionStatus.CREATED
    output: AIArchitectResult | None = None
    schema_version: str = AI_ARCHITECT_SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != AI_ARCHITECT_SESSION_SCHEMA_VERSION:
            raise ValueError("AI Architect Session schema version is unsupported")
        if not all((self.id, self.workspace_id, self.provider_id, self.provider_version, self.objective)):
            raise ValueError("session identity, workspace, provider, and objective are required")
        if self.objective != self.request.objective:
            raise ValueError("session objective must match its complete AI Architect request")
        for references, label in (
            (self.constitutional_context, "constitutional context"),
            (self.architecture_context, "architecture context"),
        ):
            if not references:
                raise ValueError(f"{label} references are required")
            if len(references) != len(set(references)):
                raise ValueError(f"{label} references must be unique")

        if self.status in {AIArchitectSessionStatus.REVIEW, AIArchitectSessionStatus.COMPLETE} and self.output is None:
            raise ValueError("review and complete sessions require advisory output")
        if self.status not in {AIArchitectSessionStatus.REVIEW, AIArchitectSessionStatus.COMPLETE} and self.output is not None:
            raise ValueError("advisory output is recorded only for review or complete sessions")
        if self.output is not None:
            if self.output.request_id != self.request.id or self.output.provider_id != self.provider_id:
                raise ValueError("session output must match its request and selected provider")

        object.__setattr__(self, "constitutional_context", tuple(sorted(self.constitutional_context)))
        object.__setattr__(self, "architecture_context", tuple(sorted(self.architecture_context)))

    def to_dict(self) -> dict[str, Any]:
        """Serialize only declared, provider-independent session state."""

        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "workspace_id": self.workspace_id,
            "provider": {"id": self.provider_id, "version": self.provider_version},
            "objective": self.objective,
            "request": self.request.to_dict(),
            "repository_snapshot": self.repository_snapshot.to_dict(),
            "constitutional_context": [reference.to_dict() for reference in self.constitutional_context],
            "architecture_context": [reference.to_dict() for reference in self.architecture_context],
            "status": self.status.value,
            "output": None if self.output is None else self.output.to_dict(),
        }


_ALLOWED_TRANSITIONS: dict[AIArchitectSessionStatus, set[AIArchitectSessionStatus]] = {
    AIArchitectSessionStatus.CREATED: {AIArchitectSessionStatus.PREPARED, AIArchitectSessionStatus.ABANDONED},
    AIArchitectSessionStatus.PREPARED: {AIArchitectSessionStatus.REASONING, AIArchitectSessionStatus.ABANDONED},
    AIArchitectSessionStatus.REASONING: {AIArchitectSessionStatus.REVIEW, AIArchitectSessionStatus.ABANDONED},
    AIArchitectSessionStatus.REVIEW: {AIArchitectSessionStatus.COMPLETE, AIArchitectSessionStatus.ABANDONED},
    AIArchitectSessionStatus.COMPLETE: set(),
    AIArchitectSessionStatus.ABANDONED: set(),
}


def transition_ai_architect_session(
    session: AIArchitectSession,
    target: AIArchitectSessionStatus,
    *,
    output: AIArchitectResult | None = None,
) -> AIArchitectSession:
    """Create a permitted lifecycle successor without invoking a provider.

    Entering review records an already-produced advisory result.  Completion
    records no approval and does not accept any proposal or Engineering Intent.
    """

    if target not in _ALLOWED_TRANSITIONS[session.status]:
        raise ValueError(f"invalid AI Architect Session transition: {session.status.value} -> {target.value}")
    if target is AIArchitectSessionStatus.REVIEW:
        if output is None:
            raise ValueError("review requires advisory output")
        return replace(session, status=target, output=output)
    if output is not None:
        raise ValueError("advisory output may only be recorded when entering review")
    return replace(session, status=target)
