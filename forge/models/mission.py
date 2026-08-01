"""Immutable, local, non-executing Engineering Mission contracts.

An Engineering Mission is Forge's highest operational grouping artifact.  It
groups ordered, independently executable Engineering Intents; it neither
redefines their canonical meaning nor executes, persists, plans, or schedules
them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any, Mapping

from .intent import IntentStatus


ENGINEERING_MISSION_SCHEMA_VERSION = "1.10"


class MissionStatus(str, Enum):
    """The closed, human-governed Mission lifecycle."""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class MissionEvidenceKind(str, Enum):
    """The aggregate evidence required to complete a Mission."""

    REPOSITORY = "repository"
    VALIDATION = "validation"
    CONSTITUTIONAL_COMPLIANCE = "constitutional_compliance"


@dataclass(frozen=True, order=True)
class MissionIntentMembership:
    """One ordered, revision-pinned Engineering Intent in a Mission."""

    order: int
    intent_id: str
    intent_revision: str

    def __post_init__(self) -> None:
        if self.order < 1 or not self.intent_id or not self.intent_revision:
            raise ValueError("mission intent membership order, id, and revision are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class MissionDependency:
    """A version-pinned external prerequisite; it is not a scheduler input."""

    id: str
    revision: str
    description: str

    def __post_init__(self) -> None:
        if not all((self.id, self.revision, self.description)):
            raise ValueError("mission dependency identity, revision, and description are required")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MissionDependencies:
    """Declared dependencies, preserved as local, immutable provenance."""

    items: tuple[MissionDependency, ...] = ()

    def __post_init__(self) -> None:
        if len(self.items) != len(set(self.items)):
            raise ValueError("mission dependencies must be unique")
        object.__setattr__(self, "items", tuple(sorted(self.items)))

    def to_dict(self) -> list[dict[str, str]]:
        return [item.to_dict() for item in self.items]


@dataclass(frozen=True)
class MissionScope:
    """Explicit Mission boundaries, not a mechanism for changing Intents."""

    in_scope: tuple[str, ...]
    out_of_scope: tuple[str, ...]

    def __post_init__(self) -> None:
        for values, label in ((self.in_scope, "in-scope"), (self.out_of_scope, "out-of-scope")):
            if not values or any(not value for value in values):
                raise ValueError(f"mission {label} boundaries are required")
            if len(values) != len(set(values)):
                raise ValueError(f"mission {label} boundaries must be unique")
        object.__setattr__(self, "in_scope", tuple(sorted(self.in_scope)))
        object.__setattr__(self, "out_of_scope", tuple(sorted(self.out_of_scope)))

    def to_dict(self) -> dict[str, list[str]]:
        return {"in_scope": list(self.in_scope), "out_of_scope": list(self.out_of_scope)}


@dataclass(frozen=True, order=True)
class MissionEvidence:
    """A reproducible evidence pointer; Mission contracts never fetch it."""

    kind: MissionEvidenceKind
    source_id: str
    source_version: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.source_id, self.source_version, self.locator, self.content_digest)):
            raise ValueError("mission evidence source identity, version, locator, and digest are required")
        digest = self.content_digest.removeprefix("sha256:")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("mission evidence content digest must be a sha256 digest")

    def to_dict(self) -> dict[str, str]:
        document = asdict(self)
        document["kind"] = self.kind.value
        return document


@dataclass(frozen=True, order=True)
class MissionIntentCompletion:
    """The terminal verified state declared for one pinned Intent membership."""

    intent_id: str
    intent_revision: str
    status: IntentStatus

    def __post_init__(self) -> None:
        if not self.intent_id or not self.intent_revision:
            raise ValueError("mission intent completion identity and revision are required")
        if self.status not in {IntentStatus.VERIFIED, IntentStatus.ARCHIVED}:
            raise ValueError("mission intent completion requires VERIFIED or ARCHIVED status")

    def to_dict(self) -> dict[str, str]:
        return {"intent_id": self.intent_id, "intent_revision": self.intent_revision, "status": self.status.value}


@dataclass(frozen=True)
class MissionCompletion:
    """Declared aggregate completion evidence; it confers no execution authority."""

    intent_completions: tuple[MissionIntentCompletion, ...]
    evidence: tuple[MissionEvidence, ...]

    def __post_init__(self) -> None:
        if not self.intent_completions:
            raise ValueError("mission completion requires completed Engineering Intents")
        completion_keys = [(item.intent_id, item.intent_revision) for item in self.intent_completions]
        if len(completion_keys) != len(set(completion_keys)):
            raise ValueError("mission completion Intent references must be unique")
        evidence_keys = [(item.kind, item.source_id, item.source_version, item.locator, item.content_digest) for item in self.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("mission completion evidence references must be unique")
        kinds = {item.kind for item in self.evidence}
        required = {MissionEvidenceKind.REPOSITORY, MissionEvidenceKind.VALIDATION, MissionEvidenceKind.CONSTITUTIONAL_COMPLIANCE}
        if not required.issubset(kinds):
            raise ValueError("mission completion requires repository, validation, and constitutional compliance evidence")
        object.__setattr__(self, "intent_completions", tuple(sorted(self.intent_completions, key=lambda item: (item.intent_id, item.intent_revision))))
        object.__setattr__(self, "evidence", tuple(sorted(self.evidence, key=lambda item: (item.kind.value, item.source_id, item.source_version, item.locator, item.content_digest))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_completions": [item.to_dict() for item in self.intent_completions],
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class MissionProgress:
    """A declarative progress snapshot derived from supplied Intent states."""

    total_intents: int
    completed_intents: int
    remaining_intent_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.total_intents < 1 or not 0 <= self.completed_intents <= self.total_intents:
            raise ValueError("mission progress counts are invalid")
        if self.total_intents - self.completed_intents != len(self.remaining_intent_ids):
            raise ValueError("mission progress remaining intents do not match counts")
        if len(self.remaining_intent_ids) != len(set(self.remaining_intent_ids)):
            raise ValueError("mission progress remaining intent ids must be unique")

    @property
    def percent_complete(self) -> int:
        return (self.completed_intents * 100) // self.total_intents

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_intents": self.total_intents,
            "completed_intents": self.completed_intents,
            "remaining_intent_ids": list(self.remaining_intent_ids),
            "percent_complete": self.percent_complete,
        }


@dataclass(frozen=True)
class EngineeringMission:
    """The highest operational grouping artifact, subordinate to Workspace ownership."""

    id: str
    revision: str
    title: str
    objective: str
    scope: MissionScope
    intents: tuple[MissionIntentMembership, ...]
    dependencies: MissionDependencies = MissionDependencies()
    evidence: tuple[MissionEvidence, ...] = ()
    completion: MissionCompletion | None = None
    status: MissionStatus = MissionStatus.CREATED
    schema_version: str = ENGINEERING_MISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not all((self.id, self.revision, self.title, self.objective)):
            raise ValueError("mission identity, revision, title, and objective are required")
        if self.schema_version != ENGINEERING_MISSION_SCHEMA_VERSION:
            raise ValueError("engineering mission schema version is unsupported")
        if not self.intents:
            raise ValueError("mission must contain Engineering Intents")
        if tuple(item.order for item in self.intents) != tuple(range(1, len(self.intents) + 1)):
            raise ValueError("mission Intent memberships must be ordered consecutively")
        membership_keys = [(item.intent_id, item.intent_revision) for item in self.intents]
        if len(membership_keys) != len(set(membership_keys)):
            raise ValueError("mission Intent memberships must be unique")
        evidence_keys = [(item.kind, item.source_id, item.source_version, item.locator, item.content_digest) for item in self.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("mission evidence references must be unique")
        if self.status in {MissionStatus.COMPLETED, MissionStatus.ARCHIVED}:
            if self.completion is None:
                raise ValueError("completed and archived missions require completion evidence")
            self._validate_completion()
        if self.status in {MissionStatus.CREATED, MissionStatus.PLANNING, MissionStatus.BLOCKED} and self.completion is not None:
            raise ValueError("mission completion may be declared only while active or after completion")

    def _validate_completion(self) -> None:
        assert self.completion is not None
        expected = {(item.intent_id, item.intent_revision) for item in self.intents}
        actual = {(item.intent_id, item.intent_revision) for item in self.completion.intent_completions}
        if actual != expected:
            raise ValueError("mission completion must cover every Mission Intent membership")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "revision": self.revision,
            "title": self.title,
            "objective": self.objective,
            "scope": self.scope.to_dict(),
            "intents": [item.to_dict() for item in self.intents],
            "dependencies": self.dependencies.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
            "completion": None if self.completion is None else self.completion.to_dict(),
            "status": self.status.value,
        }


_NEXT_STATUS: dict[MissionStatus, frozenset[MissionStatus]] = {
    MissionStatus.CREATED: frozenset((MissionStatus.PLANNING,)),
    MissionStatus.PLANNING: frozenset((MissionStatus.ACTIVE,)),
    MissionStatus.ACTIVE: frozenset((MissionStatus.BLOCKED, MissionStatus.COMPLETED)),
    MissionStatus.BLOCKED: frozenset((MissionStatus.ACTIVE,)),
    MissionStatus.COMPLETED: frozenset((MissionStatus.ARCHIVED,)),
    MissionStatus.ARCHIVED: frozenset(),
}


def transition_mission(mission: EngineeringMission, status: MissionStatus) -> EngineeringMission:
    """Return a status-only permitted Mission lifecycle transition."""

    if status not in _NEXT_STATUS[mission.status]:
        raise ValueError("mission status transition is not permitted")
    return replace(mission, status=status)


def derive_mission_progress(
    mission: EngineeringMission,
    intent_statuses: Mapping[tuple[str, str], IntentStatus],
) -> MissionProgress:
    """Derive progress from Mission memberships and supplied Intent lifecycle states."""

    completed = 0
    remaining: list[str] = []
    for membership in mission.intents:
        status = intent_statuses.get((membership.intent_id, membership.intent_revision))
        if status in {IntentStatus.VERIFIED, IntentStatus.ARCHIVED}:
            completed += 1
        else:
            remaining.append(membership.intent_id)
    return MissionProgress(len(mission.intents), completed, tuple(remaining))
