"""Versioned, immutable, non-executing Engineering Intent lifecycle contracts.

The lifecycle records governed engineering meaning and its evidence.  It does
not persist an intent, obtain evidence, approve work, invoke a provider, or
execute against a repository.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any, Iterable


ENGINEERING_INTENT_SCHEMA_VERSION = "1.2"


class IntentStatus(str, Enum):
    """The complete governed lifecycle of an Engineering Intent."""

    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    IMPLEMENTED = "IMPLEMENTED"
    VERIFIED = "VERIFIED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class IntentCategory(str, Enum):
    """The established categories of bounded engineering work."""

    ASSESSMENT = "Assessment"
    IMPLEMENTATION = "Implementation"
    REPAIR = "Repair"
    MIGRATION = "Migration"
    KNOWLEDGE_CAPTURE = "Knowledge Capture"
    ARCHITECTURE_AUTHORING = "Architecture Authoring"
    RECONCILIATION = "Reconciliation"


class IntentRelationshipKind(str, Enum):
    """Explicit links between durable Intent records."""

    REPLACES = "replaces"
    DEPENDS_ON = "depends_on"
    SUPERSEDES = "supersedes"
    IMPLEMENTS = "implements"
    DERIVED_FROM = "derived_from"


class IntentEvidenceKind(str, Enum):
    """Evidence classifications accepted by the Intent lifecycle."""

    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    REPOSITORY = "repository"
    ARCHITECTURAL = "architectural"


@dataclass(frozen=True, order=True)
class IntentReference:
    """A versioned, immutable pointer to one traceability source."""

    id: str
    version: str
    locator: str

    def __post_init__(self) -> None:
        if not all((self.id, self.version, self.locator)):
            raise ValueError("intent reference id, version, and locator are required")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class IntentTraceability:
    """The mandatory Vision-to-Evidence lineage declared by every Intent."""

    vision: tuple[IntentReference, ...]
    architecture: tuple[IntentReference, ...]
    roadmap: tuple[IntentReference, ...]
    proposal: tuple[IntentReference, ...]
    repository: tuple[IntentReference, ...]

    def __post_init__(self) -> None:
        stages = (self.vision, self.architecture, self.roadmap, self.proposal, self.repository)
        if any(not stage for stage in stages):
            raise ValueError("intent traceability requires vision, architecture, roadmap, proposal, and repository references")
        if any(len(stage) != len(set(stage)) for stage in stages):
            raise ValueError("intent traceability references must be unique within each stage")

    def to_dict(self) -> dict[str, list[dict[str, str]]]:
        return {
            "vision": [reference.to_dict() for reference in self.vision],
            "architecture": [reference.to_dict() for reference in self.architecture],
            "roadmap": [reference.to_dict() for reference in self.roadmap],
            "proposal": [reference.to_dict() for reference in self.proposal],
            "repository": [reference.to_dict() for reference in self.repository],
        }


@dataclass(frozen=True, order=True)
class IntentRelationship:
    """One typed Intent-to-Intent relationship; references remain local pointers."""

    kind: IntentRelationshipKind
    target_intent_id: str

    def __post_init__(self) -> None:
        if not self.target_intent_id:
            raise ValueError("intent relationship target is required")

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "target_intent_id": self.target_intent_id}


@dataclass(frozen=True)
class IntentEvidence:
    """An immutable reproducible reference; the lifecycle never fetches it."""

    kind: IntentEvidenceKind
    source_id: str
    source_version: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.source_id, self.source_version, self.locator, self.content_digest)):
            raise ValueError("intent evidence source identity, version, locator, and digest are required")
        digest = self.content_digest.removeprefix("sha256:")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("intent evidence content digest must be a sha256 digest")

    def to_dict(self) -> dict[str, str]:
        document = asdict(self)
        document["kind"] = self.kind.value
        return document


@dataclass(frozen=True)
class IntentApproval:
    """Human approval provenance; it is metadata, never an automatic decision."""

    approved_by: str
    approved_at: str
    decision_reference: IntentReference

    def __post_init__(self) -> None:
        if not self.approved_by or not self.approved_at:
            raise ValueError("intent approval actor and timestamp are required")

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "decision_reference": self.decision_reference.to_dict(),
        }


@dataclass(frozen=True)
class EngineeringIntent:
    """A versioned, immutable canonical record of one bounded increment."""

    id: str
    revision: str
    title: str
    objective: str
    category: IntentCategory
    traceability: IntentTraceability
    relationships: tuple[IntentRelationship, ...] = ()
    evidence: tuple[IntentEvidence, ...] = ()
    approval: IntentApproval | None = None
    status: IntentStatus = IntentStatus.DRAFT
    schema_version: str = ENGINEERING_INTENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not all((self.id, self.revision, self.title, self.objective)):
            raise ValueError("intent identity, revision, title, and objective are required")
        if self.schema_version != ENGINEERING_INTENT_SCHEMA_VERSION:
            raise ValueError("engineering intent schema version is unsupported")
        if any(relationship.target_intent_id == self.id for relationship in self.relationships):
            raise ValueError("an intent must not relate to itself")
        relationship_keys = [(relationship.kind, relationship.target_intent_id) for relationship in self.relationships]
        if len(relationship_keys) != len(set(relationship_keys)):
            raise ValueError("intent relationships must be unique")
        evidence_keys = [(item.kind, item.source_id, item.source_version, item.locator, item.content_digest) for item in self.evidence]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("intent evidence references must be unique")
        if self.status in {IntentStatus.APPROVED, IntentStatus.IMPLEMENTED, IntentStatus.VERIFIED, IntentStatus.ARCHIVED} and self.approval is None:
            raise ValueError("approved and later intent states require human approval metadata")
        if self.status in {IntentStatus.IMPLEMENTED, IntentStatus.VERIFIED, IntentStatus.ARCHIVED} and not self._has_evidence(IntentEvidenceKind.IMPLEMENTATION):
            raise ValueError("implemented and later intent states require implementation evidence")
        if self.status in {IntentStatus.VERIFIED, IntentStatus.ARCHIVED} and not self._has_evidence(IntentEvidenceKind.VALIDATION):
            raise ValueError("verified and archived intent states require validation evidence")
        if self.status in {IntentStatus.VERIFIED, IntentStatus.ARCHIVED} and not self._has_evidence(IntentEvidenceKind.REPOSITORY):
            raise ValueError("verified and archived intent states require repository evidence")
        if self.status is IntentStatus.SUPERSEDED and not any(
            relationship.kind is IntentRelationshipKind.REPLACES for relationship in self.relationships
        ):
            raise ValueError("a superseded intent requires an explicit replaces relationship")

    def _has_evidence(self, kind: IntentEvidenceKind) -> bool:
        return any(item.kind is kind for item in self.evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "revision": self.revision,
            "title": self.title,
            "objective": self.objective,
            "category": self.category.value,
            "traceability": self.traceability.to_dict(),
            "relationships": [relationship.to_dict() for relationship in self.relationships],
            "evidence": [item.to_dict() for item in self.evidence],
            "approval": None if self.approval is None else self.approval.to_dict(),
            "status": self.status.value,
        }


_NEXT_STATUS: dict[IntentStatus, frozenset[IntentStatus]] = {
    IntentStatus.DRAFT: frozenset((IntentStatus.PROPOSED, IntentStatus.SUPERSEDED)),
    IntentStatus.PROPOSED: frozenset((IntentStatus.APPROVED, IntentStatus.SUPERSEDED)),
    IntentStatus.APPROVED: frozenset((IntentStatus.IMPLEMENTED, IntentStatus.SUPERSEDED)),
    IntentStatus.IMPLEMENTED: frozenset((IntentStatus.VERIFIED, IntentStatus.SUPERSEDED)),
    IntentStatus.VERIFIED: frozenset((IntentStatus.ARCHIVED, IntentStatus.SUPERSEDED)),
    IntentStatus.SUPERSEDED: frozenset(),
    IntentStatus.ARCHIVED: frozenset(),
}


def transition_intent(intent: EngineeringIntent, status: IntentStatus) -> EngineeringIntent:
    """Return a status-only lifecycle transition; content remains immutable."""

    if status not in _NEXT_STATUS[intent.status]:
        raise ValueError("intent status transition is not permitted")
    if status is IntentStatus.APPROVED and intent.approval is None:
        raise ValueError("approval transition requires human approval metadata")
    return replace(intent, status=status)


def validate_intent_relationships(intents: Iterable[EngineeringIntent]) -> None:
    """Validate cross-Intent identity and explicit reciprocal supersession links."""

    records = tuple(intents)
    by_id = {intent.id: intent for intent in records}
    if len(by_id) != len(records):
        raise ValueError("intent ids must be unique")
    for intent in records:
        for relationship in intent.relationships:
            target = by_id.get(relationship.target_intent_id)
            if target is None:
                raise ValueError("intent relationship target must be present")
            if relationship.kind is IntentRelationshipKind.SUPERSEDES:
                if target.status is not IntentStatus.SUPERSEDED:
                    raise ValueError("a superseded target must have SUPERSEDED status")
                if IntentRelationship(IntentRelationshipKind.REPLACES, intent.id) not in target.relationships:
                    raise ValueError("supersession requires a reciprocal replaces relationship")
            if relationship.kind is IntentRelationshipKind.REPLACES:
                if intent.status is not IntentStatus.SUPERSEDED:
                    raise ValueError("a replaced intent must have SUPERSEDED status")
                if IntentRelationship(IntentRelationshipKind.SUPERSEDES, intent.id) not in target.relationships:
                    raise ValueError("replacement requires a reciprocal supersedes relationship")
