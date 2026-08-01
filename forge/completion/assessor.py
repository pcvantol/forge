"""Pure deterministic assessment of declared Phase Completion 1.0 evidence."""

from __future__ import annotations

from collections.abc import Iterable

from forge.models import (
    AssessmentFinding,
    AssessmentStatus,
    CompletionEvidence,
    CriterionOutcome,
    EngineeringPhase,
    PhaseAssessment,
)


class PhaseCompletionAssessor:
    """Assess declared evidence only; never fetch, invent, or mutate evidence."""

    def assess(self, phase: EngineeringPhase, evidence: Iterable[CompletionEvidence]) -> PhaseAssessment:
        declared = tuple(evidence)
        criterion_ids = {criterion.id for criterion in phase.criteria}
        evidence_by_criterion: dict[str, list[CompletionEvidence]] = {}
        findings: list[AssessmentFinding] = []
        for item in declared:
            if item.criterion_id not in criterion_ids:
                findings.append(AssessmentFinding(item.criterion_id, "UNKNOWN_CRITERION", "Evidence references no declared phase criterion."))
                continue
            evidence_by_criterion.setdefault(item.criterion_id, []).append(item)

        has_criterion_evidence = bool(evidence_by_criterion)
        for criterion in phase.criteria:
            if not criterion.required:
                continue
            criterion_evidence = evidence_by_criterion.get(criterion.id, [])
            if not criterion_evidence:
                findings.append(AssessmentFinding(criterion.id, "MISSING_EVIDENCE", "Required criterion has no declared evidence."))
            elif any(item.outcome is CriterionOutcome.FAIL for item in criterion_evidence):
                findings.append(AssessmentFinding(criterion.id, "FAILED_CRITERION", "Required criterion has declared failing evidence."))
            elif not any(item.outcome is CriterionOutcome.PASS for item in criterion_evidence):
                findings.append(AssessmentFinding(criterion.id, "UNRESOLVED_CRITERION", "Required criterion has no passing evidence."))

        ordered_findings = tuple(sorted(findings))
        required_unresolved = any(finding.code != "UNKNOWN_CRITERION" for finding in ordered_findings)
        if not has_criterion_evidence:
            status = AssessmentStatus.NOT_STARTED
        elif required_unresolved or any(finding.code == "UNKNOWN_CRITERION" for finding in ordered_findings):
            status = AssessmentStatus.IN_PROGRESS
        elif phase.completion_declaration is None:
            status = AssessmentStatus.READY
        else:
            status = AssessmentStatus.COMPLETE
        return PhaseAssessment(phase.id, status, ordered_findings)
