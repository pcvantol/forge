"""Regression coverage for the advisory Solution Template Framework."""

from __future__ import annotations

import unittest

from forge.business import BusinessAdvisor
from forge.models import RequiredDiscipline, SolutionTemplate
from forge.solutions import BusinessAdvisorAnswers, SolutionCatalogue, SolutionTemplateMissionCandidateGenerator


class SolutionTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogue = SolutionCatalogue()
        self.template = self.catalogue.get("crm")
        self.answers = BusinessAdvisorAnswers.from_dict({"users": "sales staff", "customers": "business customers", "deployment": "cloud", "existing_systems": "billing"})
        self.context = {"repository_id": "forge", "repository_revision": "abc123", "repository_truth_digest": "sha256:context"}

    def test_catalogue_loads_versioned_required_archetypes(self) -> None:
        identifiers = {item.identifier for item in self.catalogue.list()}
        self.assertTrue({"web-application", "mobile-application", "rest-api", "crm", "erp", "dashboard", "knowledge-base", "ai-assistant", "iot-platform", "media-platform", "e-commerce", "internal-tool", "automation-platform"}.issubset(identifiers))
        self.assertEqual(self.template.reference, "solution-template:crm@1.0")

    def test_generation_is_deterministic_editable_and_stays_in_business_review(self) -> None:
        generator = SolutionTemplateMissionCandidateGenerator()
        first = generator.generate(self.template, self.answers, self.context, available_disciplines=(RequiredDiscipline.BUSINESS,))
        second = generator.generate(self.template, self.answers, self.context, available_disciplines=(RequiredDiscipline.BUSINESS,))
        self.assertEqual(first, second)
        self.assertEqual(len(first.candidates), 6)
        self.assertTrue(all(item.solution_template_reference == self.template.reference for item in first.candidates))
        self.assertTrue(all(item.architecture_review_reference is None and item.mission_recommendation_reference is None for item in first.candidates))
        self.assertTrue(all(item.status.value == "business_review" for item in first.candidates))

    def test_advisor_guides_answers_without_approval_authority(self) -> None:
        advice = BusinessAdvisor().advise_template(self.template, self.answers)
        self.assertTrue(advice.advisory)
        self.assertIn("answer required: mobile_required", advice.missing_information)
        self.assertFalse(hasattr(BusinessAdvisor(), "approve"))

    def test_architecture_and_discipline_recommendations_remain_advisory(self) -> None:
        draft = SolutionTemplateMissionCandidateGenerator().generate(self.template, self.answers, self.context, available_disciplines=(RequiredDiscipline.BUSINESS,))
        self.assertIn("modular service boundaries", draft.architecture_recommendations)
        self.assertIn(RequiredDiscipline.ENGINEERING, draft.missing_disciplines)
        self.assertTrue(draft.advisory)

    def test_template_versioning_and_extension_are_explicit(self) -> None:
        version_two = SolutionTemplate(
            self.template.identifier, "2.0", self.template.name, self.template.purpose, self.template.typical_users,
            self.template.typical_stakeholders, self.template.business_objectives, self.template.typical_capabilities,
            self.template.recommended_mission_candidates, self.template.architecture_patterns, self.template.engineering_disciplines,
            self.template.risks, self.template.compliance_considerations, self.template.implementation_phases,
        )
        catalogue = SolutionCatalogue((self.template, version_two))
        self.assertEqual(catalogue.get("crm", "2.0").reference, "solution-template:crm@2.0")


if __name__ == "__main__":
    unittest.main()
