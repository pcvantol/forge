"""Append-only governance records from advisory recommendation to allocation.

This store deliberately sits outside :mod:`forge.runtime`: recommendations and
unallocated candidates are governance artefacts, not operational Runtime state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Callable


class LifecycleError(ValueError):
    """Raised when a lifecycle transition or immutable record is invalid."""


class RecommendationStatus(str, Enum):
    PROPOSED = "PROPOSED"
    RECOMMENDED = "RECOMMENDED"
    BUSINESS_REJECTED = "BUSINESS_REJECTED"
    BUSINESS_APPROVED = "BUSINESS_APPROVED"
    ARCHITECTURE_REJECTED = "ARCHITECTURE_REJECTED"
    ARCHITECTURE_APPROVED = "ARCHITECTURE_APPROVED"
    MISSION_ALLOCATED = "MISSION_ALLOCATED"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


_TRANSITIONS: dict[RecommendationStatus, frozenset[RecommendationStatus]] = {
    RecommendationStatus.PROPOSED: frozenset((RecommendationStatus.RECOMMENDED, RecommendationStatus.ARCHIVED)),
    RecommendationStatus.RECOMMENDED: frozenset((RecommendationStatus.BUSINESS_APPROVED, RecommendationStatus.BUSINESS_REJECTED, RecommendationStatus.SUPERSEDED, RecommendationStatus.ARCHIVED)),
    RecommendationStatus.BUSINESS_APPROVED: frozenset((RecommendationStatus.ARCHITECTURE_APPROVED, RecommendationStatus.ARCHITECTURE_REJECTED, RecommendationStatus.SUPERSEDED, RecommendationStatus.ARCHIVED)),
    RecommendationStatus.ARCHITECTURE_APPROVED: frozenset((RecommendationStatus.MISSION_ALLOCATED, RecommendationStatus.SUPERSEDED, RecommendationStatus.ARCHIVED)),
    RecommendationStatus.BUSINESS_REJECTED: frozenset((RecommendationStatus.ARCHIVED,)),
    RecommendationStatus.ARCHITECTURE_REJECTED: frozenset((RecommendationStatus.ARCHIVED,)),
    RecommendationStatus.MISSION_ALLOCATED: frozenset((RecommendationStatus.ARCHIVED,)),
    RecommendationStatus.SUPERSEDED: frozenset((RecommendationStatus.ARCHIVED,)),
    RecommendationStatus.ARCHIVED: frozenset(),
}


@dataclass(frozen=True)
class MissionRecommendation:
    """Immutable advisory input for Business governance."""

    id: str
    title: str
    mission_origin: str
    business_summary: str
    engineering_summary: str
    business_value: str
    engineering_value: str
    architectural_value: str
    repository_evidence: tuple[str, ...]
    decision_evidence_reference: str
    dependencies: tuple[str, ...]
    alternatives: tuple[str, ...]
    confidence: int
    recommendation_timestamp: str
    status: RecommendationStatus = RecommendationStatus.PROPOSED
    recommendation_set_id: str | None = None
    rank: int | None = None
    recommendation_type: str | None = None
    expected_outcome: str | None = None
    expected_repository_impact: str | None = None
    risk_if_deferred: str | None = None
    required_disciplines: tuple[str, ...] = ()
    known_constraints: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    supersedes_recommendation_id: str | None = None

    def __post_init__(self) -> None:
        if not all((self.id, self.title, self.mission_origin, self.business_summary, self.engineering_summary,
                    self.business_value, self.engineering_value, self.architectural_value,
                    self.decision_evidence_reference, self.recommendation_timestamp)):
            raise LifecycleError("recommendation requires complete governance context")
        if not 0 <= self.confidence <= 100:
            raise LifecycleError("recommendation confidence must be between 0 and 100")
        if self.rank is not None and self.rank < 1:
            raise LifecycleError("recommendation rank must be positive when supplied")
        for name in ("repository_evidence", "dependencies", "alternatives", "required_disciplines", "known_constraints", "evidence_references"):
            values = getattr(self, name)
            if any(not item for item in values) or len(values) != len(set(values)):
                raise LifecycleError(f"recommendation {name} must be unique and non-empty when supplied")
            object.__setattr__(self, name, tuple(sorted(values)))

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["status"] = self.status.value
        return result

    @classmethod
    def from_dict(cls, document: dict[str, object]) -> "MissionRecommendation":
        return cls(**{**document, "repository_evidence": tuple(document["repository_evidence"]),
                      "dependencies": tuple(document["dependencies"]), "alternatives": tuple(document["alternatives"]),
                      "required_disciplines": tuple(document.get("required_disciplines", ())),
                      "known_constraints": tuple(document.get("known_constraints", ())),
                      "evidence_references": tuple(document.get("evidence_references", ())),
                      "status": RecommendationStatus(str(document["status"]))})  # type: ignore[arg-type]


@dataclass(frozen=True)
class MissionCandidate:
    """Mutable governance-to-execution object, frozen by allocation."""

    id: str
    recommendation_id: str
    title: str
    objective: str
    scope: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    architecture_constraints: tuple[str, ...]
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.id, self.recommendation_id, self.title, self.objective)):
            raise LifecycleError("mission candidate requires identity, provenance, title, and objective")
        for name in ("scope", "acceptance_criteria", "architecture_constraints", "dependencies"):
            values = getattr(self, name)
            if any(not item for item in values) or len(values) != len(set(values)):
                raise LifecycleError(f"candidate {name} must be unique and non-empty when supplied")
            object.__setattr__(self, name, tuple(sorted(values)))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, document: dict[str, object]) -> "MissionCandidate":
        return cls(**{**document, **{key: tuple(document[key]) for key in ("scope", "acceptance_criteria", "architecture_constraints", "dependencies")}})  # type: ignore[arg-type]


@dataclass(frozen=True)
class LifecycleDecisionEvidence:
    """Immutable evidence emitted for every lifecycle decision."""

    id: str
    kind: str
    recommendation_id: str
    occurred_at: str
    actor: str
    rationale: str
    references: tuple[str, ...]
    decision_type: str = "LIFECYCLE"
    selected_recommendation_id: str | None = None
    ranked_alternatives: tuple[str, ...] = ()
    confidence: int | None = None

    def __post_init__(self) -> None:
        if not all((self.id, self.kind, self.recommendation_id, self.occurred_at, self.actor, self.rationale)):
            raise LifecycleError("decision evidence requires identity, actor, time, and rationale")
        if any(not value for value in self.references) or len(self.references) != len(set(self.references)):
            raise LifecycleError("decision evidence references must be unique and non-empty")
        if self.confidence is not None and not 0 <= self.confidence <= 100:
            raise LifecycleError("decision evidence confidence must be between 0 and 100")
        if any(not value for value in self.ranked_alternatives) or len(self.ranked_alternatives) != len(set(self.ranked_alternatives)):
            raise LifecycleError("decision evidence ranked alternatives must be unique and non-empty when supplied")
        object.__setattr__(self, "references", tuple(sorted(self.references)))
        object.__setattr__(self, "ranked_alternatives", tuple(self.ranked_alternatives))

    @property
    def content_digest(self) -> str:
        return "sha256:" + sha256(_dump(self.to_dict()).encode()).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class MissionAllocation:
    recommendation_id: str
    candidate_id: str
    mission_id: str
    business_decision_evidence_id: str
    architecture_decision_evidence_id: str
    allocation_decision_evidence_id: str
    allocated_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class RecommendationLifecycleStore:
    """The canonical local governance aggregate; it has no Runtime dependency."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS recommendations (recommendation_id TEXT PRIMARY KEY, document TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS candidates (candidate_id TEXT PRIMARY KEY, recommendation_id TEXT UNIQUE NOT NULL, frozen INTEGER NOT NULL DEFAULT 0, document TEXT NOT NULL, FOREIGN KEY(recommendation_id) REFERENCES recommendations(recommendation_id));
            CREATE TABLE IF NOT EXISTS decision_evidence (evidence_id TEXT PRIMARY KEY, recommendation_id TEXT NOT NULL, kind TEXT NOT NULL, content_digest TEXT NOT NULL UNIQUE, document TEXT NOT NULL, FOREIGN KEY(recommendation_id) REFERENCES recommendations(recommendation_id));
            CREATE TABLE IF NOT EXISTS transitions (sequence INTEGER PRIMARY KEY AUTOINCREMENT, recommendation_id TEXT NOT NULL, from_status TEXT, to_status TEXT NOT NULL, evidence_id TEXT NOT NULL UNIQUE, FOREIGN KEY(recommendation_id) REFERENCES recommendations(recommendation_id), FOREIGN KEY(evidence_id) REFERENCES decision_evidence(evidence_id));
            CREATE TABLE IF NOT EXISTS allocations (recommendation_id TEXT PRIMARY KEY, candidate_id TEXT UNIQUE NOT NULL, mission_id TEXT UNIQUE NOT NULL, document TEXT NOT NULL, FOREIGN KEY(recommendation_id) REFERENCES recommendations(recommendation_id), FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id));
            CREATE TRIGGER IF NOT EXISTS recommendations_immutable_update BEFORE UPDATE ON recommendations BEGIN SELECT RAISE(ABORT, 'recommendations are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS recommendations_immutable_delete BEFORE DELETE ON recommendations BEGIN SELECT RAISE(ABORT, 'recommendations are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS lifecycle_evidence_immutable_update BEFORE UPDATE ON decision_evidence BEGIN SELECT RAISE(ABORT, 'decision evidence is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS lifecycle_evidence_immutable_delete BEFORE DELETE ON decision_evidence BEGIN SELECT RAISE(ABORT, 'decision evidence is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS lifecycle_transitions_immutable_update BEFORE UPDATE ON transitions BEGIN SELECT RAISE(ABORT, 'transitions are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS lifecycle_transitions_immutable_delete BEFORE DELETE ON transitions BEGIN SELECT RAISE(ABORT, 'transitions are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS lifecycle_allocations_immutable_update BEFORE UPDATE ON allocations BEGIN SELECT RAISE(ABORT, 'allocations are immutable'); END;
            CREATE TRIGGER IF NOT EXISTS lifecycle_allocations_immutable_delete BEFORE DELETE ON allocations BEGIN SELECT RAISE(ABORT, 'allocations are immutable'); END;
        """)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "RecommendationLifecycleStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def create_recommendation(self, recommendation: MissionRecommendation, *, actor: str, rationale: str) -> MissionRecommendation:
        if recommendation.status is not RecommendationStatus.PROPOSED:
            raise LifecycleError("new recommendations must be proposed")
        evidence = self._evidence("recommendation", recommendation.id, recommendation.recommendation_timestamp, actor, rationale, recommendation.repository_evidence + (recommendation.decision_evidence_reference,))
        with self._connection:
            self._connection.execute("INSERT INTO recommendations VALUES (?, ?)", (recommendation.id, _dump(recommendation.to_dict())))
            self._append_evidence(evidence)
            self._connection.execute("INSERT INTO transitions(recommendation_id, from_status, to_status, evidence_id) VALUES (?, ?, ?, ?)", (recommendation.id, None, recommendation.status.value, evidence.id))
        return recommendation

    def get_recommendation(self, recommendation_id: str) -> MissionRecommendation:
        row = self._connection.execute("SELECT document FROM recommendations WHERE recommendation_id = ?", (recommendation_id,)).fetchone()
        if row is None:
            raise LifecycleError(f"unknown recommendation: {recommendation_id}")
        # The current status is derived from the immutable transition log, never mutating the recommendation.
        status = self._connection.execute("SELECT to_status FROM transitions WHERE recommendation_id = ? ORDER BY sequence DESC LIMIT 1", (recommendation_id,)).fetchone()["to_status"]
        document = json.loads(row["document"]); document["status"] = status
        return MissionRecommendation.from_dict(document)

    def resolve_recommendation(self, reference: str) -> MissionRecommendation:
        """Resolve an exact canonical ID or title, failing closed on ambiguity."""
        try:
            return self.get_recommendation(reference)
        except LifecycleError:
            rows = self._connection.execute("SELECT recommendation_id, document FROM recommendations").fetchall()
            matches = [row["recommendation_id"] for row in rows if json.loads(row["document"])["title"] == reference]
            if not matches:
                raise LifecycleError(f"unknown recommendation reference: {reference}")
            if len(matches) != 1:
                raise LifecycleError(f"ambiguous recommendation reference: {reference}")
            return self.get_recommendation(str(matches[0]))

    def transition(self, recommendation_id: str, target: RecommendationStatus, *, actor: str, occurred_at: str, rationale: str, references: tuple[str, ...] = ()) -> MissionRecommendation:
        current = self.get_recommendation(recommendation_id)
        if target not in _TRANSITIONS[current.status]:
            raise LifecycleError(f"recommendation transition {current.status.value} -> {target.value} is not permitted")
        if target is RecommendationStatus.MISSION_ALLOCATED:
            raise LifecycleError("mission allocation must use allocate")
        evidence = self._evidence(self._decision_kind(target), recommendation_id, occurred_at, actor, rationale, references or (recommendation_id,))
        with self._connection:
            self._append_evidence(evidence)
            self._connection.execute("INSERT INTO transitions(recommendation_id, from_status, to_status, evidence_id) VALUES (?, ?, ?, ?)", (recommendation_id, current.status.value, target.value, evidence.id))
        return self.get_recommendation(recommendation_id)

    def create_candidate(self, candidate: MissionCandidate) -> MissionCandidate:
        recommendation = self.get_recommendation(candidate.recommendation_id)
        if recommendation.status is not RecommendationStatus.ARCHITECTURE_APPROVED:
            raise LifecycleError("a candidate may enter allocation only after architecture approval")
        with self._connection:
            self._connection.execute("INSERT INTO candidates VALUES (?, ?, 0, ?)", (candidate.id, candidate.recommendation_id, _dump(candidate.to_dict())))
        return candidate

    def update_candidate(self, candidate_id: str, **changes: object) -> MissionCandidate:
        row = self._connection.execute("SELECT frozen, document FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None:
            raise LifecycleError(f"unknown mission candidate: {candidate_id}")
        if row["frozen"]:
            raise LifecycleError("allocated mission candidates are immutable")
        candidate = MissionCandidate.from_dict(json.loads(row["document"]))
        allowed = {"title", "objective", "scope", "acceptance_criteria", "architecture_constraints", "dependencies"}
        if not changes or set(changes) - allowed:
            raise LifecycleError("candidate update contains an unsupported field")
        updated = replace(candidate, **changes)
        with self._connection:
            self._connection.execute("UPDATE candidates SET document = ? WHERE candidate_id = ?", (_dump(updated.to_dict()), candidate_id))
        return updated

    def allocate(self, candidate_id: str, *, actor: str, occurred_at: str, rationale: str, allocate_mission_id: Callable[[str, str], str]) -> MissionAllocation:
        row = self._connection.execute("SELECT recommendation_id, frozen FROM candidates WHERE candidate_id = ?", (candidate_id,)).fetchone()
        if row is None or row["frozen"]:
            raise LifecycleError("candidate is unknown or already allocated")
        recommendation = self.get_recommendation(row["recommendation_id"])
        if recommendation.status is not RecommendationStatus.ARCHITECTURE_APPROVED:
            raise LifecycleError("mission allocation requires recorded Business and Architecture approvals")
        decisions = self._approval_evidence(recommendation.id)
        if "business_decision" not in decisions or "architecture_decision" not in decisions:
            raise LifecycleError("mission allocation requires immutable Business and Architecture Decision Evidence")
        mission_id = allocate_mission_id(recommendation.id, occurred_at)
        if not re.fullmatch(r"MISSION-\d{4,}", mission_id):
            raise LifecycleError("allocator returned an invalid mission id")
        evidence = self._evidence("mission_allocation", recommendation.id, occurred_at, actor, rationale, (candidate_id, mission_id, decisions["business_decision"], decisions["architecture_decision"]))
        allocation = MissionAllocation(recommendation.id, candidate_id, mission_id, decisions["business_decision"], decisions["architecture_decision"], evidence.id, occurred_at)
        with self._connection:
            self._append_evidence(evidence)
            self._connection.execute("INSERT INTO transitions(recommendation_id, from_status, to_status, evidence_id) VALUES (?, ?, ?, ?)", (recommendation.id, recommendation.status.value, RecommendationStatus.MISSION_ALLOCATED.value, evidence.id))
            self._connection.execute("INSERT INTO allocations VALUES (?, ?, ?, ?)", (recommendation.id, candidate_id, mission_id, _dump(allocation.to_dict())))
            self._connection.execute("UPDATE candidates SET frozen = 1 WHERE candidate_id = ?", (candidate_id,))
        return allocation

    def record_completion(self, mission_id: str, *, actor: str, occurred_at: str, rationale: str, references: tuple[str, ...]) -> LifecycleDecisionEvidence:
        """Append immutable completion evidence without turning history into Runtime state."""
        row = self._connection.execute("SELECT recommendation_id FROM allocations WHERE mission_id = ?", (mission_id,)).fetchone()
        if row is None:
            raise LifecycleError("mission completion requires an allocated Mission")
        evidence = self._evidence("mission_completion", row["recommendation_id"], occurred_at, actor, rationale, (mission_id, *references))
        with self._connection:
            self._append_evidence(evidence)
        return evidence

    def history(self, recommendation_id: str) -> tuple[LifecycleDecisionEvidence, ...]:
        self.get_recommendation(recommendation_id)
        rows = self._connection.execute("SELECT document FROM decision_evidence WHERE recommendation_id = ? ORDER BY evidence_id", (recommendation_id,)).fetchall()
        return tuple(LifecycleDecisionEvidence(**{**json.loads(row["document"]), "references": tuple(json.loads(row["document"])["references"]),
                                                 "ranked_alternatives": tuple(json.loads(row["document"]).get("ranked_alternatives", ()))}) for row in rows)

    def list_recommendations(self) -> tuple[MissionRecommendation, ...]:
        """Return the current immutable governance projection in deterministic rank order."""
        rows = self._connection.execute("SELECT recommendation_id FROM recommendations").fetchall()
        recommendations = tuple(self.get_recommendation(str(row["recommendation_id"])) for row in rows)
        return tuple(sorted(recommendations, key=lambda item: (item.rank is None, item.rank or 0, item.id)))

    def recommendation_set(self, recommendation_set_id: str) -> tuple[MissionRecommendation, ...]:
        """Return one canonical, deterministically ranked recommendation set."""
        if not recommendation_set_id:
            raise LifecycleError("recommendation set id is required")
        recommendations = tuple(item for item in self.list_recommendations() if item.recommendation_set_id == recommendation_set_id)
        if not recommendations:
            raise LifecycleError(f"unknown recommendation set: {recommendation_set_id}")
        ranks = tuple(item.rank for item in recommendations)
        if any(rank is None for rank in ranks) or ranks != tuple(range(1, len(recommendations) + 1)):
            raise LifecycleError("recommendation set ranks must be complete, unique, and contiguous")
        return recommendations

    def reconcile_recommendation_set_selection(self, recommendation_set_id: str, *, selected_recommendation_id: str,
                                               decision_evidence_id: str, actor: str, occurred_at: str,
                                               rationale: str) -> tuple[MissionRecommendation, ...]:
        """Append a bounded correction so exactly rank one is current and recommended.

        This preserves immutable recommendation generation and Decision Evidence.
        It cannot approve, allocate, supersede, or archive work.
        """
        recommendations = self.recommendation_set(recommendation_set_id)
        selected = recommendations[0]
        if selected.id != selected_recommendation_id:
            raise LifecycleError("only the rank-one recommendation may be selected")
        decision = self._decision_evidence(decision_evidence_id)
        if (decision.decision_type != "MISSION_RECOMMENDATION"
                or decision.selected_recommendation_id != selected.id
                or decision.ranked_alternatives != tuple(item.id for item in recommendations)):
            raise LifecycleError("selection Decision Evidence does not match the recommendation set")
        if selected.status is RecommendationStatus.PROPOSED:
            self.transition(selected.id, RecommendationStatus.RECOMMENDED, actor=actor, occurred_at=occurred_at,
                            rationale=rationale, references=(decision_evidence_id,))
        elif selected.status is not RecommendationStatus.RECOMMENDED:
            raise LifecycleError("selected recommendation is not eligible for reconciliation")
        for recommendation in recommendations[1:]:
            if recommendation.status is RecommendationStatus.PROPOSED:
                continue
            if recommendation.status is not RecommendationStatus.RECOMMENDED:
                raise LifecycleError("non-selected recommendation is not eligible for reconciliation")
            evidence = self._evidence("recommendation_selection_correction", recommendation.id, occurred_at, actor,
                                      rationale, (decision_evidence_id, recommendation_set_id, selected.id))
            with self._connection:
                self._append_evidence(evidence)
                self._connection.execute(
                    "INSERT INTO transitions(recommendation_id, from_status, to_status, evidence_id) VALUES (?, ?, ?, ?)",
                    (recommendation.id, RecommendationStatus.RECOMMENDED.value,
                     RecommendationStatus.PROPOSED.value, evidence.id),
                )
        reconciled = self.recommendation_set(recommendation_set_id)
        if (sum(item.status is RecommendationStatus.RECOMMENDED for item in reconciled) != 1
                or reconciled[0].status is not RecommendationStatus.RECOMMENDED):
            raise LifecycleError("recommendation set selection reconciliation failed")
        return reconciled

    def append_recommendation_decision(self, recommendation_id: str, *, evidence_id: str,
                                       occurred_at: str, actor: str, rationale: str,
                                       ranked_alternatives: tuple[str, ...], confidence: int,
                                       references: tuple[str, ...]) -> LifecycleDecisionEvidence:
        """Persist the bounded Portfolio recommendation decision without an approval transition."""
        self.get_recommendation(recommendation_id)
        evidence = LifecycleDecisionEvidence(
            evidence_id, "mission_recommendation", recommendation_id, occurred_at, actor, rationale,
            references, "MISSION_RECOMMENDATION", recommendation_id, ranked_alternatives, confidence,
        )
        with self._connection:
            self._append_evidence(evidence)
        return evidence

    def decision_evidence(self, evidence_id: str) -> LifecycleDecisionEvidence:
        """Resolve immutable lifecycle Decision Evidence by canonical identifier."""
        return self._decision_evidence(evidence_id)

    def candidate_for_recommendation(self, recommendation_id: str) -> MissionCandidate | None:
        """Return the one canonical candidate, without creating one implicitly."""
        row = self._connection.execute(
            "SELECT document FROM candidates WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone()
        return None if row is None else MissionCandidate.from_dict(json.loads(row["document"]))

    def allocation_for_recommendation(self, recommendation_id: str) -> MissionAllocation | None:
        """Return the immutable allocation when the recommendation already has one."""
        row = self._connection.execute(
            "SELECT document FROM allocations WHERE recommendation_id = ?", (recommendation_id,)
        ).fetchone()
        return None if row is None else MissionAllocation(**json.loads(row["document"]))

    def _approval_evidence(self, recommendation_id: str) -> dict[str, str]:
        rows = self._connection.execute("SELECT kind, evidence_id FROM decision_evidence WHERE recommendation_id = ?", (recommendation_id,)).fetchall()
        return {row["kind"]: row["evidence_id"] for row in rows}

    def _decision_evidence(self, evidence_id: str) -> LifecycleDecisionEvidence:
        row = self._connection.execute("SELECT document FROM decision_evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
        if row is None:
            raise LifecycleError(f"unknown decision evidence: {evidence_id}")
        document = json.loads(row["document"])
        return LifecycleDecisionEvidence(**{**document, "references": tuple(document["references"]),
                                             "ranked_alternatives": tuple(document.get("ranked_alternatives", ()))})

    @staticmethod
    def _decision_kind(target: RecommendationStatus) -> str:
        return {RecommendationStatus.BUSINESS_APPROVED: "business_decision", RecommendationStatus.BUSINESS_REJECTED: "business_decision", RecommendationStatus.ARCHITECTURE_APPROVED: "architecture_decision", RecommendationStatus.ARCHITECTURE_REJECTED: "architecture_decision"}.get(target, "recommendation_transition")

    @staticmethod
    def _evidence(kind: str, recommendation_id: str, occurred_at: str, actor: str, rationale: str, references: tuple[str, ...]) -> LifecycleDecisionEvidence:
        digest = sha256(_dump((kind, recommendation_id, occurred_at, actor, rationale, tuple(sorted(references)))).encode()).hexdigest()[:16]
        return LifecycleDecisionEvidence(f"decision-{kind}-{digest}", kind, recommendation_id, occurred_at, actor, rationale, references)

    def _append_evidence(self, evidence: LifecycleDecisionEvidence) -> None:
        self._connection.execute("INSERT INTO decision_evidence VALUES (?, ?, ?, ?, ?)", (evidence.id, evidence.recommendation_id, evidence.kind, evidence.content_digest, _dump(evidence.to_dict())))
