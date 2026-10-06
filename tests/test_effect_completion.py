"""Per-criterion effect reports preserve unchanged Repository Truth."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest

from forge.completion.effect_report_observer import EffectReportCriterionObserver
from forge.completion.mission import MissionCompletionEvaluator
from forge.models.criterion_assessment import CriterionAssessmentContract, CriterionEvidenceRequirement
from forge.models.criterion_observation import canonical_digest
from forge.models.mission_completion import (
    MissionCompletionEvidence, MissionCriterionEvidenceBinding,
    MissionCriterionEvaluationStatus, mission_criterion_id,
)
from forge.models.mission_effect import MissionEffectPolicy
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from tests.test_substantive_mission_completion import host, mission, reference, truth


class EffectCompletionTests(unittest.TestCase):
    def _case(self):
        criterion = "A useful report identifies current documentation gaps."
        contract = CriterionAssessmentContract(criterion, (
            CriterionEvidenceRequirement("approved-effect-report", kind="effect_report"),
        ))
        approved = replace(mission(contracts=(contract,)), effect_policy=MissionEffectPolicy(
            "READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY", ("docs/",), (),
        ))
        ref = reference(revision="a" * 40)
        criterion_id = mission_criterion_id(approved.id, criterion)
        effect = {
            "contract_version": "1.0", "mode": "READ_ONLY_ASSESSMENT",
            "delivery": "EVIDENCE_ONLY", "source_revision": ref.repository_revision,
            "delivery_revision": None, "report_id": ref.report_id,
            "report_digest": canonical_digest("verified EP report"),
            "source_manifest_digest": canonical_digest("pinned snapshot"),
            "subject_digest": canonical_digest("exact review subject"),
            "criteria": [{"id": criterion_id,
                          "analysis_digest": canonical_digest("source-backed analysis"),
                          "source_paths": ["docs/architecture.md"]}],
            "controls": ["effect_source_binding", "effect_output_integrity",
                         "effect_scope_containment", "report_criteria_contract"],
            "reviews": ["quality", "security"],
        }
        observation, = EffectReportCriterionObserver().observe(
            approved, ref, SimpleNamespace(effect_result=effect),
        )
        binding = MissionCriterionEvidenceBinding(criterion_id, (ref,), truth(ref),
                                                  (observation,), contract.digest)
        evidence = MissionCompletionEvidence(approved.id, canonical_digest(approved.to_dict()), (binding,))
        canonical = {**host(ref, approved.id), "effect_result": effect}
        return approved, ref, effect, observation, evidence, canonical

    def test_read_only_criterion_requires_verified_report_bound_to_source(self):
        approved, ref, effect, observation, evidence, canonical = self._case()
        evaluation = MissionCompletionEvaluator().evaluate(
            approved, truth(ref).to_dict(), (canonical,), evidence,
        )
        self.assertTrue(evaluation.all_required_criteria_proven)
        self.assertEqual(evaluation.criteria[0].status, MissionCriterionEvaluationStatus.PROVEN)
        self.assertEqual(evaluation.criteria[0].requirement_results[0]["reason"],
                         "VERIFIED_EP_EFFECT_CRITERION_SATISFIED")

        for changed in (
            {**canonical, "effect_result": None},
            {**canonical, "effect_result": {**effect, "source_revision": "b" * 40}},
            {**canonical, "effect_result": {**effect, "report_digest": canonical_digest("other report")}},
        ):
            with self.subTest(changed=changed["effect_result"]):
                result = MissionCompletionEvaluator().evaluate(
                    approved, truth(ref).to_dict(), (changed,), evidence,
                )
                self.assertFalse(result.all_required_criteria_proven)

    def test_missing_approved_report_requirement_cannot_complete_effect_mission(self):
        approved, ref, effect, observation, evidence, canonical = self._case()
        from forge.models.criterion_assessment import CriterionEvidenceRequirement
        old = approved.criterion_assessment_contracts[0]
        unsupported = replace(old, requirements=(CriterionEvidenceRequirement(
            "legacy-control", "legacy", "check"),))
        approved = replace(approved, criterion_assessment_contracts=(unsupported,))
        result = MissionCompletionEvaluator().evaluate(
            approved, truth(ref).to_dict(), (canonical,), None,
        )
        self.assertEqual(result.criteria[0].reason, "APPROVED_EFFECT_REPORT_REQUIREMENT_MISSING")

    def test_evidence_only_retains_original_repository_truth(self):
        approved, ref, effect, observation, evidence, canonical = self._case()
        current = truth(ref).to_dict()
        terminal = SimpleNamespace(
            repository_evidence=SimpleNamespace(repository_revision=ref.repository_revision,
                                                candidate_revision=None,
                                                content_digest=ref.repository_evidence_digest),
            receipt_id=ref.receipt_id, report_id=ref.report_id, host_id="sim-ep",
            effect_result=effect,
        )
        observed = InstalledDynamicMissionRuntime._repository_truth(
            SimpleNamespace(repository_truth=current), terminal,
        )
        self.assertEqual(observed, current)


if __name__ == "__main__":
    unittest.main()
