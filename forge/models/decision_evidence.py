"""Immutable, repository-grounded Decision Evidence contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any


DECISION_EVIDENCE_SCHEMA_VERSION = "1.0"


class DecisionType(str, Enum):
    MISSION_RECOMMENDATION = "mission_recommendation"
    ARCHITECTURE_REVIEW = "architecture_review"
    BUSINESS_ADVISOR_RECOMMENDATION = "business_advisor_recommendation"
    ARCHITECTURE_ADVISOR_RECOMMENDATION = "architecture_advisor_recommendation"
    MISSION_PLANNING = "mission_planning"
    ENGINEERING_INTENT = "engineering_intent"
    ENGINEERING_ACTION_SELECTION = "engineering_action_selection"
    EXECUTION_POLICY = "execution_policy"
    SOLUTION_TEMPLATE_SELECTION = "solution_template_selection"
    PORTFOLIO_RECOMMENDATION = "portfolio_recommendation"


class DecisionReferenceKind(str, Enum):
    REPOSITORY_TRUTH = "repository_truth"
    MISSION = "mission"
    MISSION_RECOMMENDATION = "mission_recommendation"
    ARCHITECTURE_REVIEW = "architecture_review"
    EXECUTION_EVIDENCE = "execution_evidence"
    REPOSITORY_EVIDENCE = "repository_evidence"
    SOLUTION_TEMPLATE = "solution_template"
    ENGINEERING_INTENT = "engineering_intent"
    ENGINEERING_ACTION = "engineering_action"
    MISSION_STATE = "mission_state"


class ApprovalState(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING_HUMAN_APPROVAL = "pending_human_approval"
    HUMAN_APPROVED = "human_approved"
    HUMAN_REJECTED = "human_rejected"


class DecisionOutcome(str, Enum):
    PROPOSED = "proposed"
    SELECTED = "selected"
    DEFERRED = "deferred"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, order=True)
class DecisionReference:
    """A pointer to a canonical artefact; its content is never copied here."""

    kind: DecisionReferenceKind
    artifact_id: str
    locator: str
    revision: str
    content_digest: str

    def __post_init__(self) -> None:
        digest = self.content_digest.removeprefix("sha256:")
        if not all((self.artifact_id, self.locator, self.revision)):
            raise ValueError("decision references require identity, locator, and revision")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("decision references require a sha256 content digest")

    def to_dict(self) -> dict[str, str]:
        document = asdict(self)
        document["kind"] = self.kind.value
        return document

    @classmethod
    def from_dict(cls, document: dict[str, str]) -> "DecisionReference":
        return cls(DecisionReferenceKind(document["kind"]), document["artifact_id"], document["locator"], document["revision"], document["content_digest"])


@dataclass(frozen=True, order=True)
class DecisionAlternative:
    id: str
    summary: str
    rejection_reason: str

    def __post_init__(self) -> None:
        if not all((self.id, self.summary, self.rejection_reason)):
            raise ValueError("decision alternatives require identity, summary, and rejection reason")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, document: dict[str, str]) -> "DecisionAlternative":
        return cls(document["id"], document["summary"], document["rejection_reason"])


@dataclass(frozen=True)
class DecisionConfidence:
    """Explicit confidence provenance; opaque model output is deliberately excluded."""

    score: int
    repository_truth: DecisionReference
    architecture_review: DecisionReference
    execution_evidence: DecisionReference
    mission_state: DecisionReference

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("decision confidence score must be between 0 and 100")
        expected = (DecisionReferenceKind.REPOSITORY_TRUTH, DecisionReferenceKind.ARCHITECTURE_REVIEW,
                    DecisionReferenceKind.EXECUTION_EVIDENCE, DecisionReferenceKind.MISSION_STATE)
        actual = tuple(item.kind for item in (self.repository_truth, self.architecture_review, self.execution_evidence, self.mission_state))
        if actual != expected:
            raise ValueError("decision confidence must reference Repository Truth, Architecture Review, Execution Evidence, and Mission State")

    @property
    def level(self) -> str:
        return "high" if self.score >= 75 else "medium" if self.score >= 45 else "low"

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "level": self.level, "repository_truth": self.repository_truth.to_dict(),
                "architecture_review": self.architecture_review.to_dict(), "execution_evidence": self.execution_evidence.to_dict(),
                "mission_state": self.mission_state.to_dict()}

    @classmethod
    def from_dict(cls, document: dict[str, Any]) -> "DecisionConfidence":
        return cls(document["score"], *(DecisionReference.from_dict(document[name]) for name in ("repository_truth", "architecture_review", "execution_evidence", "mission_state")))


@dataclass(frozen=True)
class DecisionEvidence:
    """One immutable explanation of a significant Forge decision; never an approval."""

    id: str
    decision_type: DecisionType
    timestamp: str
    repository_context: DecisionReference
    mission_context: DecisionReference
    decision: str
    reasoning_summary: str
    evidence_references: tuple[DecisionReference, ...]
    confidence: DecisionConfidence
    alternatives_considered: tuple[DecisionAlternative, ...]
    chosen_alternative: str
    required_disciplines: tuple[str, ...]
    architecture_constraints: tuple[str, ...]
    business_constraints: tuple[str, ...]
    repository_maturity_reference: DecisionReference
    execution_evidence_references: tuple[DecisionReference, ...]
    approval_state: ApprovalState
    decision_outcome: DecisionOutcome
    schema_version: str = DECISION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_EVIDENCE_SCHEMA_VERSION or not all((self.id, self.timestamp, self.decision, self.reasoning_summary, self.chosen_alternative)):
            raise ValueError("decision evidence requires identity, timestamp, decision, concise reasoning, and chosen alternative")
        if self.repository_context.kind is not DecisionReferenceKind.REPOSITORY_TRUTH or self.mission_context.kind is not DecisionReferenceKind.MISSION:
            raise ValueError("decision evidence requires Repository Truth and Mission context references")
        if self.repository_maturity_reference.kind is not DecisionReferenceKind.REPOSITORY_EVIDENCE:
            raise ValueError("decision evidence requires a Repository Evidence maturity reference")
        if not self.execution_evidence_references or any(item.kind is not DecisionReferenceKind.EXECUTION_EVIDENCE for item in self.execution_evidence_references):
            raise ValueError("decision evidence requires Execution Evidence references")
        if not self.evidence_references:
            raise ValueError("decision evidence requires canonical evidence references")
        if self.chosen_alternative not in {item.id for item in self.alternatives_considered}:
            raise ValueError("chosen alternative must be one of the considered alternatives")
        for field_name in ("evidence_references", "alternatives_considered", "required_disciplines", "architecture_constraints", "business_constraints", "execution_evidence_references"):
            values = getattr(self, field_name)
            if not values or len(values) != len(set(values)):
                raise ValueError(f"decision evidence {field_name} must be non-empty and unique")
            key = (lambda item: item.id) if field_name == "alternatives_considered" else (lambda item: item.artifact_id) if "references" in field_name else (lambda item: item)
            object.__setattr__(self, field_name, tuple(sorted(values, key=key)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id, "decision_type": self.decision_type.value, "timestamp": self.timestamp,
                "repository_context": self.repository_context.to_dict(), "mission_context": self.mission_context.to_dict(), "decision": self.decision,
                "reasoning_summary": self.reasoning_summary, "evidence_references": [item.to_dict() for item in self.evidence_references],
                "confidence": self.confidence.to_dict(), "alternatives_considered": [item.to_dict() for item in self.alternatives_considered],
                "chosen_alternative": self.chosen_alternative, "required_disciplines": list(self.required_disciplines),
                "architecture_constraints": list(self.architecture_constraints), "business_constraints": list(self.business_constraints),
                "repository_maturity_reference": self.repository_maturity_reference.to_dict(),
                "execution_evidence_references": [item.to_dict() for item in self.execution_evidence_references],
                "approval_state": self.approval_state.value, "decision_outcome": self.decision_outcome.value}

    @classmethod
    def from_dict(cls, document: dict[str, Any]) -> "DecisionEvidence":
        return cls(document["id"], DecisionType(document["decision_type"]), document["timestamp"],
                   DecisionReference.from_dict(document["repository_context"]), DecisionReference.from_dict(document["mission_context"]),
                   document["decision"], document["reasoning_summary"], tuple(DecisionReference.from_dict(item) for item in document["evidence_references"]),
                   DecisionConfidence.from_dict(document["confidence"]), tuple(DecisionAlternative.from_dict(item) for item in document["alternatives_considered"]),
                   document["chosen_alternative"], tuple(document["required_disciplines"]), tuple(document["architecture_constraints"]),
                   tuple(document["business_constraints"]), DecisionReference.from_dict(document["repository_maturity_reference"]),
                   tuple(DecisionReference.from_dict(item) for item in document["execution_evidence_references"]),
                   ApprovalState(document["approval_state"]), DecisionOutcome(document["decision_outcome"]), document.get("schema_version", DECISION_EVIDENCE_SCHEMA_VERSION))

    @property
    def content_digest(self) -> str:
        return "sha256:" + sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
