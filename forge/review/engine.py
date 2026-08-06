"""Pure deterministic derivation of Architecture Reviews from Repository Truth."""

from __future__ import annotations

from forge.models.architecture_review import (
    ArchitecturePressure, ArchitectureReview, ArchitectureReviewInput, MaturityArea,
    MaturityClassification, PressureLevel,
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
        inconsistent = tuple(signal.id for signal in review_input.signals if signal.kind in {ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY, ReviewSignalKind.ARCHITECTURE_EROSION})
        duplicated = tuple(signal.id for signal in review_input.signals if signal.kind in {ReviewSignalKind.DUPLICATION, ReviewSignalKind.DUPLICATE_IMPLEMENTATION})
        gaps = tuple(signal.id for signal in review_input.signals if signal.kind is ReviewSignalKind.CAPABILITY_GAP)
        maintenance = tuple(signal.id for signal in review_input.signals if signal.kind in {
            ReviewSignalKind.TECHNICAL_DEBT, ReviewSignalKind.DUPLICATE_IMPLEMENTATION,
            ReviewSignalKind.REFACTORING_OPPORTUNITY, ReviewSignalKind.DOCUMENTATION_INCONSISTENCY,
            ReviewSignalKind.DEPENDENCY_MAINTENANCE, ReviewSignalKind.REPOSITORY_HYGIENE,
            ReviewSignalKind.PERFORMANCE_OBSERVATION, ReviewSignalKind.ARCHITECTURE_EROSION,
        })
        weaknesses = tuple(sorted(set(inconsistent + duplicated + gaps + maintenance)))
        strengths = ("repository_truth_and_execution_evidence_available",) if has_truth and has_execution else ()
        architecture_observations = ("architecture_change_requires_implementation_pressure",) if inconsistent else ()
        implementation_observations = ("execution_evidence_is_incomplete",) if not has_execution else ()
        candidates = tuple(f"candidate:{signal_id}" for signal_id in gaps)
        rationale = ("Repository Truth and Execution Evidence are insufficient for an evidence-based review."
                     if confidence is ReviewConfidence.INSUFFICIENT else
                     "Review is derived deterministically from declared Repository Truth, Execution Evidence, Mission State, and Portfolio evidence.")
        return ArchitectureReview(review_id, review_input.mission_id, maturity, architecture_observations, implementation_observations,
                                  strengths, weaknesses, pressure, inconsistent, duplicated, gaps, maintenance, candidates,
                                  review_input.portfolio_item_ids,
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
        implementation = PressureLevel.HIGH if kinds & {ReviewSignalKind.IMPLEMENTATION_FAILURE, ReviewSignalKind.TECHNICAL_DEBT, ReviewSignalKind.DUPLICATE_IMPLEMENTATION, ReviewSignalKind.REFACTORING_OPPORTUNITY} else PressureLevel.NONE
        architecture = PressureLevel.HIGH if kinds & {ReviewSignalKind.ARCHITECTURAL_INCONSISTENCY, ReviewSignalKind.ARCHITECTURE_EROSION} and implementation is PressureLevel.HIGH else PressureLevel.NONE
        growth = PressureLevel.MODERATE if ReviewSignalKind.REPOSITORY_GROWTH in kinds else PressureLevel.NONE
        operational = PressureLevel.HIGH if ReviewSignalKind.OPERATIONAL_FAILURE in kinds else PressureLevel.NONE
        return ArchitecturePressure(architecture, implementation, growth, operational)
