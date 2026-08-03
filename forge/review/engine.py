"""Pure deterministic derivation of Architecture Reviews and advisory recommendations."""

from __future__ import annotations

from forge.models.architecture_review import (
    ArchitecturePressure, ArchitectureReview, ArchitectureReviewInput, MaturityArea,
    MaturityClassification, MissionRecommendation, PressureLevel, RecommendationKind,
    RepositoryMaturity, ReviewConfidence, ReviewInputKind, ReviewSignalKind, _digest,
)


_REQUIRED_KINDS: dict[MaturityArea, frozenset[ReviewInputKind]] = {
    MaturityArea.ARCHITECTURE: frozenset((ReviewInputKind.CONSTITUTION, ReviewInputKind.ARCHITECTURE_HANDBOOK, ReviewInputKind.REPOSITORY_TRUTH)),
    MaturityArea.RUNTIME: frozenset((ReviewInputKind.REPOSITORY_TRUTH, ReviewInputKind.EXECUTION_EVIDENCE)),
    MaturityArea.PLANNING: frozenset((ReviewInputKind.MISSION_DOCUMENT, ReviewInputKind.ENGINEERING_INTENT_HISTORY)),
    MaturityArea.ENGINEERING: frozenset((ReviewInputKind.REPOSITORY_TRUTH, ReviewInputKind.EXECUTION_EVIDENCE)),
    MaturityArea.GOVERNANCE: frozenset((ReviewInputKind.CONSTITUTION, ReviewInputKind.MISSION_STATE)),
    MaturityArea.PORTFOLIO: frozenset((ReviewInputKind.PORTFOLIO,)),
    MaturityArea.EXECUTION_HOST: frozenset((ReviewInputKind.EXECUTION_EVIDENCE, ReviewInputKind.EXECUTION_REPORT)),
    MaturityArea.DOCUMENTATION: frozenset((ReviewInputKind.BOOTSTRAP_COMPLETION, ReviewInputKind.REPOSITORY_TRUTH)),
    MaturityArea.KNOWLEDGE: frozenset((ReviewInputKind.CAPABILITY_CATALOGUE, ReviewInputKind.HISTORICAL_INTENT)),
    MaturityArea.QUALIFICATION: frozenset((ReviewInputKind.MISSION_STATE, ReviewInputKind.EXECUTION_EVIDENCE)),
}


class ArchitectureReviewEngine:
    """Evaluate declared repository evidence only; never retrieve, approve, or execute."""

    def review(self, review_input: ArchitectureReviewInput) -> ArchitectureReview:
        kinds = {item.kind for item in review_input.evidence}
        digest = _digest(review_input.to_dict())
        review_id = f"architecture-review-{digest[:16]}"
        maturity = tuple(self._maturity(area, kinds) for area in MaturityArea)
        pressure = self._pressure(review_input)
        has_truth = ReviewInputKind.REPOSITORY_TRUTH in kinds
        has_execution = ReviewInputKind.EXECUTION_EVIDENCE in kinds
        confidence = (ReviewConfidence.HIGH if has_truth and has_execution and ReviewInputKind.MISSION_STATE in kinds and ReviewInputKind.PORTFOLIO in kinds
                      else ReviewConfidence.MEDIUM if has_truth and has_execution else ReviewConfidence.INSUFFICIENT)
        inconsistent = tuple(signal.id for signal in review_input.signals if signal.kind is ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY)
        duplicated = tuple(signal.id for signal in review_input.signals if signal.kind is ReviewSignalKind.DUPLICATION)
        gaps = tuple(signal.id for signal in review_input.signals if signal.kind is ReviewSignalKind.CAPABILITY_GAP)
        weaknesses = tuple(sorted(set(inconsistent + duplicated + gaps)))
        strengths = ("repository_truth_and_execution_evidence_available",) if has_truth and has_execution else ()
        architecture_observations = ("architecture_change_requires_implementation_pressure",) if inconsistent else ()
        implementation_observations = ("execution_evidence_is_incomplete",) if not has_execution else ()
        recommendations = self._recommend(review_id, review_input, pressure, confidence, has_truth and has_execution)
        candidates = tuple(f"candidate:{signal_id}" for signal_id in gaps)
        rationale = ("Repository Truth and Execution Evidence are insufficient for an evidence-based review."
                     if confidence is ReviewConfidence.INSUFFICIENT else
                     "Review is derived deterministically from declared Repository Truth, Execution Evidence, Mission State, and Portfolio evidence.")
        return ArchitectureReview(review_id, review_input.mission_id, maturity, architecture_observations, implementation_observations,
                                  strengths, weaknesses, pressure, inconsistent, duplicated, gaps, candidates, recommendations,
                                  rationale, confidence, f"sha256:{digest}")

    def generate(self, review_input: ArchitectureReviewInput) -> ArchitectureReview:
        """Compatibility-oriented name for producing one Architecture Review."""
        return self.review(review_input)

    def _maturity(self, area: MaturityArea, kinds: set[ReviewInputKind]) -> RepositoryMaturity:
        required = _REQUIRED_KINDS[area]
        present = tuple(sorted(required & kinds, key=lambda item: item.value))
        classification = (MaturityClassification.QUALIFIED if set(present) == required and len(required) > 1 else
                          MaturityClassification.ESTABLISHED if set(present) == required else
                          MaturityClassification.FOUNDATION if present else MaturityClassification.NOT_EVIDENCED)
        return RepositoryMaturity(area, classification, present)

    @staticmethod
    def _pressure(review_input: ArchitectureReviewInput) -> ArchitecturePressure:
        kinds = {signal.kind for signal in review_input.signals}
        implementation = PressureLevel.HIGH if ReviewSignalKind.IMPLEMENTATION_FAILURE in kinds else PressureLevel.NONE
        architecture = PressureLevel.HIGH if ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY in kinds and implementation is PressureLevel.HIGH else PressureLevel.NONE
        growth = PressureLevel.MODERATE if ReviewSignalKind.REPOSITORY_GROWTH in kinds else PressureLevel.NONE
        operational = PressureLevel.HIGH if ReviewSignalKind.OPERATIONAL_FAILURE in kinds else PressureLevel.NONE
        return ArchitecturePressure(architecture, implementation, growth, operational)

    @staticmethod
    def _recommend(review_id: str, review_input: ArchitectureReviewInput, pressure: ArchitecturePressure,
                   confidence: ReviewConfidence, sufficient: bool) -> tuple[MissionRecommendation, ...]:
        signals = {kind: tuple(signal.id for signal in review_input.signals if signal.kind is kind) for kind in ReviewSignalKind}
        candidates: list[tuple[RecommendationKind, str, str, tuple[str, ...]]] = []
        if not sufficient:
            candidates.append((RecommendationKind.QUALIFICATION, "Qualify repository evidence", "Complete Repository Truth and Execution Evidence before Portfolio action.", ()))
        if signals[ReviewSignalKind.CAPABILITY_GAP]:
            candidates.append((RecommendationKind.NEW_CAPABILITY, "Consider a capability candidate", "A repository-evidence capability gap is available for Business Workspace review.", signals[ReviewSignalKind.CAPABILITY_GAP]))
        if signals[ReviewSignalKind.DUPLICATION]:
            candidates.append((RecommendationKind.RECONCILIATION, "Consider reconciliation", "Repository evidence records duplicated responsibility for human review.", signals[ReviewSignalKind.DUPLICATION]))
        if signals[ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY] and pressure.implementation is PressureLevel.HIGH:
            candidates.append((RecommendationKind.RECONCILIATION, "Consider architectural reconciliation", "Implementation pressure demonstrates the necessity of reviewing the recorded inconsistency.", signals[ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY]))
        if signals[ReviewSignalKind.OPERATIONAL_FAILURE]:
            candidates.append((RecommendationKind.RUNTIME_IMPROVEMENT, "Consider runtime improvement", "Operational evidence is available for human Portfolio review.", signals[ReviewSignalKind.OPERATIONAL_FAILURE]))
        return tuple(MissionRecommendation(f"mission-recommendation-{_digest((review_id, kind.value, source_ids))[:16]}", review_id, kind, title, rationale, confidence, source_ids)
                     for kind, title, rationale, source_ids in sorted(candidates, key=lambda item: (item[0].value, item[1], item[3])))
