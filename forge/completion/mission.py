"""Deterministic Architecture Mission completion evaluation."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from forge.models.architecture_mission import ArchitectureMission
from forge.models.mission_completion import (
    CanonicalExecutionEvidenceReference,
    MissionCompletionEvaluation,
    MissionCompletionEvidence,
    MissionCriterionEvaluation,
    MissionCriterionEvaluationStatus,
    RepositoryTruthReference,
    mission_criterion_id,
)


class MissionCompletionEvaluationError(ValueError):
    """Completion input is stale, malformed, or outside the approved Mission."""


def _digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _truth_reference(document: Mapping[str, Any]) -> RepositoryTruthReference:
    try:
        values = tuple(document[item] for item in ("source_id", "revision", "locator", "content_digest"))
        if any(not isinstance(item, str) or not item for item in values):
            raise TypeError
        return RepositoryTruthReference(*values)
    except (KeyError, TypeError, ValueError) as error:
        raise MissionCompletionEvaluationError("current Repository Truth provenance is incomplete") from error


def _canonical_execution_references(
    mission_id: str, evidence: Sequence[Mapping[str, Any]],
) -> dict[str, CanonicalExecutionEvidenceReference]:
    references: dict[str, CanonicalExecutionEvidenceReference] = {}
    for document in evidence:
        if document.get("outcome") != "complete":
            continue
        repository = document.get("repository_evidence")
        if not isinstance(repository, Mapping) or repository.get("mission_id") != mission_id:
            continue
        try:
            values = (
                document["receipt_id"], repository["action_id"], document["report_id"],
                repository["repository_revision"], repository["content_digest"],
            )
            if any(not isinstance(item, str) or not item for item in values):
                raise TypeError
            reference = CanonicalExecutionEvidenceReference(*values)
        except (KeyError, TypeError, ValueError):
            continue
        if any(document.get(key) != repository.get(key) for key in ("correlation_id", "host_run_id", "report_id")):
            continue
        previous = references.get(reference.receipt_id)
        if previous is not None and previous != reference:
            raise MissionCompletionEvaluationError("execution receipt identity binds conflicting terminal evidence")
        references[reference.receipt_id] = reference
    return references


class MissionCompletionEvaluator:
    """Evaluate explicit evidence associations without accepting prose authority."""

    def evaluate(
        self,
        mission: ArchitectureMission,
        repository_truth: Mapping[str, Any],
        execution_evidence: Sequence[Mapping[str, Any]],
        evidence: MissionCompletionEvidence | None,
    ) -> MissionCompletionEvaluation:
        if not mission.acceptance_criteria:
            raise MissionCompletionEvaluationError("approved Mission has no acceptance criteria")
        mission_digest = _digest(mission.to_dict())
        truth = _truth_reference(repository_truth)
        identifiers = {mission_criterion_id(mission.id, criterion): criterion for criterion in mission.acceptance_criteria}
        canonical = _canonical_execution_references(mission.id, execution_evidence)
        bindings = {} if evidence is None else {item.criterion_id: item for item in evidence.bindings}
        if evidence is not None:
            if evidence.mission_id != mission.id or evidence.mission_digest != mission_digest:
                raise MissionCompletionEvaluationError("completion evidence does not bind the approved Mission")
            unknown = set(bindings) - set(identifiers)
            if unknown:
                raise MissionCompletionEvaluationError("completion evidence references an unknown Mission criterion")

        evaluations: list[MissionCriterionEvaluation] = []
        for criterion_id, criterion in identifiers.items():
            binding = bindings.get(criterion_id)
            if binding is None:
                evaluations.append(MissionCriterionEvaluation(
                    criterion_id, criterion, MissionCriterionEvaluationStatus.UNSATISFIED, "MISSING_EVIDENCE"
                ))
                continue
            if binding.repository_truth != truth:
                evaluations.append(MissionCriterionEvaluation(
                    criterion_id, criterion, MissionCriterionEvaluationStatus.UNSATISFIED,
                    "STALE_REPOSITORY_TRUTH", binding.execution_evidence, binding.repository_truth,
                ))
                continue
            if any(canonical.get(reference.receipt_id) != reference for reference in binding.execution_evidence):
                evaluations.append(MissionCriterionEvaluation(
                    criterion_id, criterion, MissionCriterionEvaluationStatus.UNSATISFIED,
                    "NON_CANONICAL_EXECUTION_EVIDENCE", binding.execution_evidence, truth,
                ))
                continue
            evaluations.append(MissionCriterionEvaluation(
                criterion_id, criterion, MissionCriterionEvaluationStatus.PROVEN,
                "CANONICAL_EXECUTION_AND_REPOSITORY_TRUTH", binding.execution_evidence, truth,
            ))
        return MissionCompletionEvaluation(
            mission.id, mission_digest, tuple(evaluations), None if evidence is None else evidence.digest
        )
