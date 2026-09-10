"""Versioned evidence contracts for Architecture Mission completion.

The provider and Execution Host may supply evidence, but neither can declare a
Mission complete.  These contracts bind an approved acceptance criterion to
canonical terminal execution evidence and one exact Repository Truth snapshot;
the Forge-owned evaluator derives the result.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any


MISSION_COMPLETION_EVIDENCE_SCHEMA_VERSION = "1.0"


def _digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _require_digest(value: str, label: str) -> None:
    digest = value.removeprefix("sha256:")
    if not value.startswith("sha256:") or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{label} must be a sha256 digest")


def mission_criterion_id(mission_id: str, criterion: str) -> str:
    """Return the stable identity of one criterion in one approved Mission."""
    if not mission_id or not criterion:
        raise ValueError("mission criterion identity requires mission and criterion")
    return f"mission-criterion-{_digest({'mission_id': mission_id, 'criterion': criterion})[7:23]}"


@dataclass(frozen=True, order=True)
class CanonicalExecutionEvidenceReference:
    """Exact terminal Host/repository evidence used by one criterion binding."""

    receipt_id: str
    action_id: str
    report_id: str
    repository_revision: str
    repository_evidence_digest: str

    def __post_init__(self) -> None:
        if not all((self.receipt_id, self.action_id, self.report_id, self.repository_revision)):
            raise ValueError("canonical execution evidence reference requires complete lineage")
        _require_digest(self.repository_evidence_digest, "repository evidence digest")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class RepositoryTruthReference:
    """Exact Forge-observed Repository Truth snapshot used for evaluation."""

    source_id: str
    revision: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.source_id, self.revision, self.locator)):
            raise ValueError("repository truth reference requires complete provenance")
        _require_digest(self.content_digest, "repository truth digest")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class MissionCriterionEvidenceBinding:
    """Evidence association only; it contains no provider-authored PASS flag."""

    criterion_id: str
    execution_evidence: tuple[CanonicalExecutionEvidenceReference, ...]
    repository_truth: RepositoryTruthReference

    def __post_init__(self) -> None:
        if not self.criterion_id or not self.execution_evidence:
            raise ValueError("criterion evidence binding requires criterion identity and terminal evidence")
        if len(self.execution_evidence) != len(set(self.execution_evidence)):
            raise ValueError("criterion execution evidence references must be unique")
        object.__setattr__(self, "execution_evidence", tuple(sorted(self.execution_evidence)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "execution_evidence": [item.to_dict() for item in self.execution_evidence],
            "repository_truth": self.repository_truth.to_dict(),
        }


@dataclass(frozen=True)
class MissionCompletionEvidence:
    """Immutable proposed bindings consumed by deterministic Forge evaluation."""

    mission_id: str
    mission_digest: str
    bindings: tuple[MissionCriterionEvidenceBinding, ...]
    schema_version: str = MISSION_COMPLETION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MISSION_COMPLETION_EVIDENCE_SCHEMA_VERSION or not self.mission_id:
            raise ValueError("mission completion evidence identity or schema is invalid")
        _require_digest(self.mission_digest, "mission digest")
        criterion_ids = tuple(item.criterion_id for item in self.bindings)
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("mission completion evidence must bind each criterion at most once")
        object.__setattr__(self, "bindings", tuple(sorted(self.bindings)))

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mission_id": self.mission_id,
            "mission_digest": self.mission_digest,
            "bindings": [item.to_dict() for item in self.bindings],
        }


class MissionCriterionEvaluationStatus(str, Enum):
    PROVEN = "PROVEN"
    UNSATISFIED = "UNSATISFIED"


@dataclass(frozen=True, order=True)
class MissionCriterionEvaluation:
    criterion_id: str
    criterion: str
    status: MissionCriterionEvaluationStatus
    reason: str
    execution_evidence: tuple[CanonicalExecutionEvidenceReference, ...] = ()
    repository_truth: RepositoryTruthReference | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "criterion": self.criterion,
            "status": self.status.value,
            "reason": self.reason,
            "execution_evidence": [item.to_dict() for item in self.execution_evidence],
            "repository_truth": None if self.repository_truth is None else self.repository_truth.to_dict(),
        }


@dataclass(frozen=True)
class MissionCompletionEvaluation:
    """Forge-owned result; completion is derived from every criterion result."""

    mission_id: str
    mission_digest: str
    criteria: tuple[MissionCriterionEvaluation, ...]
    evidence_digest: str | None
    schema_version: str = MISSION_COMPLETION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MISSION_COMPLETION_EVIDENCE_SCHEMA_VERSION or not self.mission_id or not self.criteria:
            raise ValueError("mission completion evaluation requires mission identity and criteria")
        _require_digest(self.mission_digest, "mission digest")
        if self.evidence_digest is not None:
            _require_digest(self.evidence_digest, "completion evidence digest")
        criterion_ids = tuple(item.criterion_id for item in self.criteria)
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("mission completion evaluation criterion identities must be unique")
        object.__setattr__(self, "criteria", tuple(sorted(self.criteria)))
        if self.all_required_criteria_proven and self.evidence_digest is None:
            raise ValueError("proven Mission completion requires immutable evidence bindings")

    @property
    def all_required_criteria_proven(self) -> bool:
        return all(item.status is MissionCriterionEvaluationStatus.PROVEN for item in self.criteria)

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mission_id": self.mission_id,
            "mission_digest": self.mission_digest,
            "criteria": [item.to_dict() for item in self.criteria],
            "evidence_digest": self.evidence_digest,
            "all_required_criteria_proven": self.all_required_criteria_proven,
        }
