import unittest

from forge.constitutional import ConstitutionalAssessor
from forge.models import (
    ConstitutionalAssessment,
    ConstitutionalAssessmentStatus,
    ConstitutionalFinding,
    ConstitutionalFindingSeverity,
    ConstitutionalRule,
)


def rule(article: str = "article-1") -> ConstitutionalRule:
    return ConstitutionalRule(article, "Repository-first Engineering", "Repository evidence is authoritative.", "Observable evidence prevents stale claims from controlling assessment.", "Assess architectural claims against repository-held knowledge.")


def finding(article: str, severity: ConstitutionalFindingSeverity, concept: str) -> ConstitutionalFinding:
    return ConstitutionalFinding(article, severity, f"{concept} does not satisfy the article.", concept, f"Reconcile {concept} with {article} before progressing.")


class ConstitutionalValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assessor = ConstitutionalAssessor()

    def test_valid_constitutional_rule_is_immutable_and_serializable(self) -> None:
        constitutional_rule = rule()
        self.assertEqual(constitutional_rule.id, "article-1")
        self.assertEqual(constitutional_rule.to_dict()["validation_intent"], "Assess architectural claims against repository-held knowledge.")
        with self.assertRaises(ValueError):
            ConstitutionalRule("", "Title", "Description", "Rationale", "Intent")

    def test_assessment_states_follow_declared_applicability_and_findings(self) -> None:
        applicable = (rule(),)
        self.assertEqual(self.assessor.assess("handbook", (), ()).status, ConstitutionalAssessmentStatus.NOT_APPLICABLE)
        self.assertEqual(self.assessor.assess("handbook", applicable, ()).status, ConstitutionalAssessmentStatus.PASS)
        self.assertEqual(self.assessor.assess("handbook", applicable, (finding("article-1", ConstitutionalFindingSeverity.WARNING, "handbook"),)).status, ConstitutionalAssessmentStatus.WARNING)
        self.assertEqual(self.assessor.assess("handbook", applicable, (finding("article-1", ConstitutionalFindingSeverity.VIOLATION, "intent"),)).status, ConstitutionalAssessmentStatus.VIOLATION)

    def test_finding_requires_article_and_architectural_guidance(self) -> None:
        constitutional_finding = finding("article-1", ConstitutionalFindingSeverity.VIOLATION, "repository model")
        self.assertEqual(constitutional_finding.article_id, "article-1")
        self.assertEqual(constitutional_finding.affected_concept, "repository model")
        with self.assertRaises(ValueError):
            ConstitutionalFinding("", ConstitutionalFindingSeverity.WARNING, "Explanation", "Concept", "Recommendation")

    def test_assessment_is_deterministic_for_rule_and_finding_order(self) -> None:
        first_rule = rule("article-1")
        second_rule = rule("article-3")
        warning = finding("article-3", ConstitutionalFindingSeverity.WARNING, "engineering intent")
        violation = finding("article-1", ConstitutionalFindingSeverity.VIOLATION, "repository knowledge")
        forward = self.assessor.assess("architecture-handbook", (second_rule, first_rule), (warning, violation))
        reverse = self.assessor.assess("architecture-handbook", (first_rule, second_rule), (violation, warning))
        self.assertEqual(forward, reverse)
        self.assertEqual(forward.status, ConstitutionalAssessmentStatus.VIOLATION)
        self.assertEqual([item.article_id for item in forward.findings], ["article-1", "article-3"])

    def test_findings_must_reference_an_applicable_rule(self) -> None:
        with self.assertRaises(ValueError):
            self.assessor.assess("handbook", (rule(),), (finding("article-2", ConstitutionalFindingSeverity.WARNING, "workspace"),))

    def test_assessment_status_cannot_conflict_with_declared_findings(self) -> None:
        with self.assertRaises(ValueError):
            ConstitutionalAssessment("handbook", (rule(),), ConstitutionalAssessmentStatus.PASS, (finding("article-1", ConstitutionalFindingSeverity.WARNING, "handbook"),))


if __name__ == "__main__":
    unittest.main()
