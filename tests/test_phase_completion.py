import unittest

from forge.completion import PhaseCompletionAssessor
from forge.models import (
    AssessmentStatus,
    CompletionCriterion,
    CompletionDeclaration,
    CompletionEvidence,
    CompletionEvidenceKind,
    CriterionOutcome,
    EngineeringPhase,
    ReproducibleEvidenceReference,
)


def reference(value: str) -> ReproducibleEvidenceReference:
    return ReproducibleEvidenceReference(CompletionEvidenceKind.TEST, "forge-tests", "1.0", f"tests/{value}", f"sha256:{value * 64}")


class PhaseCompletionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assessor = PhaseCompletionAssessor()
        self.criteria = (CompletionCriterion("contracts", "Contracts are versioned."), CompletionCriterion("tests", "Tests pass."))

    def test_complete_phase_requires_every_pass_and_closure_evidence(self) -> None:
        phase = EngineeringPhase("phase-b", "Phase B", "Close Phase B.", self.criteria, CompletionDeclaration(reference("c")))
        assessment = self.assessor.assess(phase, (CompletionEvidence("contracts", CriterionOutcome.PASS, reference("a")), CompletionEvidence("tests", CriterionOutcome.PASS, reference("b"))))
        self.assertEqual(assessment.status, AssessmentStatus.COMPLETE)
        self.assertEqual(assessment.findings, ())

    def test_missing_evidence_explains_incomplete_phase(self) -> None:
        phase = EngineeringPhase("phase-b", "Phase B", "Close Phase B.", self.criteria)
        assessment = self.assessor.assess(phase, ())
        self.assertEqual(assessment.status, AssessmentStatus.NOT_STARTED)
        self.assertEqual([finding.code for finding in assessment.findings], ["MISSING_EVIDENCE", "MISSING_EVIDENCE"])

    def test_failed_criterion_is_in_progress(self) -> None:
        phase = EngineeringPhase("phase-b", "Phase B", "Close Phase B.", self.criteria)
        assessment = self.assessor.assess(phase, (CompletionEvidence("contracts", CriterionOutcome.PASS, reference("a")), CompletionEvidence("tests", CriterionOutcome.FAIL, reference("b"))))
        self.assertEqual(assessment.status, AssessmentStatus.IN_PROGRESS)
        self.assertIn("FAILED_CRITERION", [finding.code for finding in assessment.findings])

    def test_partial_completion_is_in_progress(self) -> None:
        phase = EngineeringPhase("phase-b", "Phase B", "Close Phase B.", self.criteria)
        assessment = self.assessor.assess(phase, (CompletionEvidence("contracts", CriterionOutcome.PASS, reference("a")),))
        self.assertEqual(assessment.status, AssessmentStatus.IN_PROGRESS)
        self.assertEqual(assessment.findings[0].criterion_id, "tests")

    def test_all_passing_criteria_are_ready_until_closure_is_declared(self) -> None:
        phase = EngineeringPhase("phase-b", "Phase B", "Close Phase B.", self.criteria)
        assessment = self.assessor.assess(phase, (CompletionEvidence("contracts", CriterionOutcome.PASS, reference("a")), CompletionEvidence("tests", CriterionOutcome.PASS, reference("b"))))
        self.assertEqual(assessment.status, AssessmentStatus.READY)

    def test_assessment_is_deterministic_for_evidence_order(self) -> None:
        phase = EngineeringPhase("phase-b", "Phase B", "Close Phase B.", self.criteria)
        evidence = (CompletionEvidence("unknown", CriterionOutcome.PASS, reference("c")), CompletionEvidence("tests", CriterionOutcome.FAIL, reference("b")), CompletionEvidence("contracts", CriterionOutcome.PASS, reference("a")))
        self.assertEqual(self.assessor.assess(phase, evidence), self.assessor.assess(phase, tuple(reversed(evidence))))


if __name__ == "__main__":
    unittest.main()
