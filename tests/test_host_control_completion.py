"""Only exact executed EP controls can prove a functional criterion."""
from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path

from forge.completion.host_control_observer import HostControlCriterionObserver
from forge.completion.mission import MissionCompletionEvaluator
from forge.governance_authority import ArchitecturePlanningEvidence
from forge.mission_cli import inspect, _require_ep_mission_capabilities, _verified_initial_truth
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from forge.models.criterion_observation import canonical_digest
from forge.models.mission_completion import (
    CanonicalExecutionEvidenceReference, MissionCompletionEvidence,
    MissionCriterionEvidenceBinding, RepositoryTruthReference, mission_criterion_id,
)
from forge.models.mission_recommendation import RequiredDiscipline
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot


def digest(value):
    return "sha256:" + sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class HostControlCompletionTests(unittest.TestCase):
    def setUp(self):
        self.binding = {
            "validation_id": "repository_suite", "required": True, "category": "repository",
            "control_identity": "python3 -m unittest discover -s tests",
            "command": ["/test/python", "-m", "unittest", "discover", "-s", "tests"],
        }
        self.command_identity = ["{python}", "-m", "unittest", "discover", "-s", "tests"]
        definition = digest({"validation_profile_version": "1.0",
                             "profile_reference": "validation-profile-registry:FULL@1.0",
                             "validation_id": "repository_suite", "category": "repository",
                             "control_identity": self.binding["control_identity"],
                             "command_identity": self.command_identity})
        requirement = CriterionEvidenceRequirement(
            "behavior", self.binding["control_identity"], json.dumps(self.command_identity),
            validation_id="repository_suite", validation_profile_version="1.0",
            profile_reference="validation-profile-registry:FULL@1.0", control_category="repository",
            control_definition_digest=definition, minimum_test_count=1)
        contract = CriterionAssessmentContract("Installed parser rejects invalid input", (requirement,))
        self.mission = ArchitectureMission(
            "MISSION-0042", "candidate", "Parser", "Verify parser", "Bounded parser work",
            "Correct input handling", "architecture", "recommendation", ("target",),
            ("bounded", "ep-merge-delegation:" + "a" * 32,
             "ep-delivery-control-validation:1"),
            (contract.criterion,), ("test consumer",), ("ep",), ("parser",),
            (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("scope drift",),
            ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
            criterion_assessment_contracts=(contract,), maximum_actions=3,
            maximum_consecutive_no_progress_actions=1,
            repository_evidence_source=ApprovedRepositoryEvidenceSource("target", "example/qualification"))
        self.reference = CanonicalExecutionEvidenceReference(
            "receipt", "action", "report", "a" * 40, canonical_digest("artifact"), "a" * 40)
        self.context = {
            "contract_version": "1.0", "status": "AVAILABLE",
            "validation_profile_version": "1.0", "profile_digest": canonical_digest("profile"),
            "profile_reference": "validation-profile-registry:FULL@1.0",
            "candidate_sha": "a" * 40, "currentness": 0, "profile_currentness_conflict": False,
            "required_validation_controls": ["repository_suite"],
            "controls": {"repository_suite": {
                "validation_id": "repository_suite", "category": "repository",
                "control_identity": self.binding["control_identity"],
                "control_definition_digest": definition, "required_for_profile": True,
                "currentness": 0,
                "execution_status": "EXECUTED", "result": "PASS",
                "evidence_ref": "command_terminal", "evidence_authority": "command_terminal",
                "command_id": "command-1", "exit_code": 0,
                "result_detail": {"status": "AVAILABLE", "capture_status": "AVAILABLE",
                    "schema": "deterministic-validation-result-detail-v1",
                    "run_id": "run", "command_id": "command-1",
                    "validation_id": "repository_suite", "exit_code": 0,
                    "artifact_id": "detail-1", "digest": canonical_digest("detail"),
                    "output_digest": canonical_digest("output"), "test_count": 2,
                    "test_count_source": "unittest_terminal_summary"},
            }},
        }

    def observe(self, context):
        return HostControlCriterionObserver().observe(
            self.mission, self.reference,
            SimpleNamespace(validation_controls=context, host_run_id="run"))[0]

    def assess(self, context):
        observation = self.observe(context)
        contract = self.mission.criterion_assessment_contracts[0]
        truth = RepositoryTruthReference("truth", self.reference.repository_revision,
                                         "repository://target/revision", canonical_digest("truth"))
        binding = MissionCriterionEvidenceBinding(
            mission_criterion_id(self.mission.id, contract.criterion), (self.reference,), truth,
            (observation,), contract.digest)
        completion = MissionCompletionEvidence(
            self.mission.id, canonical_digest(self.mission.to_dict()), (binding,))
        host = {"receipt_id": "receipt", "report_id": "report", "outcome": "complete",
                "correlation_id": "correlation", "host_run_id": "run",
                "repository_evidence": {"mission_id": self.mission.id, "action_id": "action",
                    "report_id": "report", "correlation_id": "correlation", "host_run_id": "run",
                    "repository_revision": self.reference.repository_revision,
                    "content_digest": self.reference.repository_evidence_digest,
                    "candidate_revision": "a" * 40}}
        return MissionCompletionEvaluator().evaluate(
            self.mission, truth.to_dict(), (host,), completion)

    def test_passing_record_is_observed(self):
        observation = self.observe(self.context)
        self.assertEqual((observation.result, observation.reason),
                         ("PASS", "APPROVED_HOST_CONTROL_EXECUTED_AND_PASSED"))
        self.assertTrue(self.assess(self.context).all_required_criteria_proven)

    def test_inspect_checks_evidence_fit_without_allocation(self):
        planning = ArchitecturePlanningEvidence(
            ("target",), ("parser.py",), ("no unrelated work",), ("scope drift",),
            ("protected delivery",), ("ep",), 1000, 1000, "1",
            criterion_assessment_contracts=self.mission.criterion_assessment_contracts,
            maximum_actions=3, maximum_consecutive_no_progress_actions=1,
            repository_evidence_source=self.mission.repository_evidence_source)
        document = {"candidate_id": "candidate", "subject_revision": "1",
                    "business_decision_id": "business", "architecture_decision_id": "architecture",
                    "planning": planning.to_dict(), "mission": self.mission.to_dict()}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "mission.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            result = inspect(str(path))
            incomplete = deepcopy(document)
            incomplete["planning"]["criterion_assessment_contracts"][0]["requirements"][0]["minimum_test_count"] = 0
            incomplete["mission"]["criterion_assessment_contracts"][0]["requirements"][0]["minimum_test_count"] = 0
            path.write_text(json.dumps(incomplete), encoding="utf-8")
            unsupported = inspect(str(path))
        self.assertEqual(result["status"], "VALID")
        self.assertFalse(result["allocated"])
        self.assertEqual(unsupported["status"], "UNSUPPORTED_EVIDENCE")
        self.assertEqual(len(unsupported["incomplete_host_controls"]), 1)

    def test_inspect_rejects_missing_or_malformed_merge_delegation(self):
        planning = ArchitecturePlanningEvidence(
            ("target",), ("parser.py",), ("no unrelated work",), ("scope drift",),
            ("protected delivery",), ("ep",), 1000, 1000, "1",
            criterion_assessment_contracts=self.mission.criterion_assessment_contracts,
            maximum_actions=3, maximum_consecutive_no_progress_actions=1,
            repository_evidence_source=self.mission.repository_evidence_source)
        for constraints in (("bounded",), ("bounded", "ep-merge-delegation:bad"),
                            ("ep-merge-delegation:" + "a" * 32,
                             "ep-merge-delegation:" + "b" * 32)):
            with self.subTest(constraints=constraints), TemporaryDirectory() as directory:
                document = {"candidate_id": "candidate", "subject_revision": "1",
                            "business_decision_id": "business", "architecture_decision_id": "architecture",
                            "planning": planning.to_dict(), "mission": {
                                **self.mission.to_dict(), "engineering_constraints": list(constraints)}}
                path = Path(directory) / "mission.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "merge delegation"):
                    inspect(str(path))

    def test_inspect_requires_delivery_validation_for_host_control(self):
        planning = ArchitecturePlanningEvidence(
            ("target",), ("parser.py",), ("no unrelated work",), ("scope drift",),
            ("protected delivery",), ("ep",), 1000, 1000, "1",
            criterion_assessment_contracts=self.mission.criterion_assessment_contracts,
            maximum_actions=3, maximum_consecutive_no_progress_actions=1,
            repository_evidence_source=self.mission.repository_evidence_source)
        with TemporaryDirectory() as directory:
            document = {"candidate_id": "candidate", "subject_revision": "1",
                        "business_decision_id": "business", "architecture_decision_id": "architecture",
                        "planning": planning.to_dict(), "mission": {
                            **self.mission.to_dict(), "engineering_constraints": [
                                "bounded", "ep-merge-delegation:" + "a" * 32]}}
            path = Path(directory) / "mission.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "delivery-revision validation"):
                inspect(str(path))

    def test_start_truth_uses_fresh_approved_head_instead_of_supplied_evidence(self):
        revision = "a" * 40
        requested = RepositoryTruthSnapshot(
            "supplied", "target", revision, "supplied time",
            (RepositoryTruthEvidence("invented", "invented", revision, "invented locator",
                                     digest("invented evidence")),))
        runtime = SimpleNamespace(
            states=SimpleNamespace(get=lambda _: SimpleNamespace(mission=self.mission.to_dict())),
            host=SimpleNamespace(config=SimpleNamespace(repository_id="target")))
        with patch("forge.mission_cli._github_default_head", return_value=("main", revision)):
            observed = _verified_initial_truth(runtime, self.mission.id, requested)
            self.assertEqual(observed.repository_revision, revision)
            self.assertEqual(observed.evidence[0].kind, "git_ref")
            self.assertNotEqual(observed.evidence[0].locator, "invented locator")
        with patch("forge.mission_cli._github_default_head", return_value=("main", "b" * 40)):
            with self.assertRaisesRegex(ValueError, "stale"):
                _verified_initial_truth(runtime, self.mission.id, requested)

    def test_mission_run_requires_all_declared_ep_capabilities(self):
        capabilities = {"validation_controls": ["1.0"], "delivery_revision_validation": ["1.0"],
                        "bounded_merge_delegation": ["1.0"]}
        runtime = SimpleNamespace(host=SimpleNamespace(preflight=lambda: {"contracts": capabilities}))
        _require_ep_mission_capabilities(runtime)
        for missing in capabilities:
            with self.subTest(missing=missing):
                reduced = {key: value for key, value in capabilities.items() if key != missing}
                runtime = SimpleNamespace(host=SimpleNamespace(preflight=lambda: {"contracts": reduced}))
                with self.assertRaisesRegex(ValueError, "lacks"):
                    _require_ep_mission_capabilities(runtime)

    def test_skipped_empty_wrong_candidate_and_changed_definition_are_unproven(self):
        changes = (
            lambda c: c["controls"]["repository_suite"].update(execution_status="SKIPPED"),
            lambda c: c["controls"]["repository_suite"]["result_detail"].update(test_count=0),
            lambda c: c.update(candidate_sha="c" * 40),
            lambda c: c["controls"]["repository_suite"].update(control_definition_digest=canonical_digest("changed-command")),
            lambda c: c["controls"]["repository_suite"].update(evidence_authority="agent_summary"),
        )
        for change in changes:
            context = deepcopy(self.context)
            change(context)
            with self.subTest(context=context):
                self.assertEqual(self.observe(context).result, "UNAVAILABLE")
                self.assertFalse(self.assess(context).all_required_criteria_proven)

    def test_candidate_control_does_not_prove_different_current_delivery(self):
        self.reference = CanonicalExecutionEvidenceReference(
            "receipt", "action", "report", "b" * 40, canonical_digest("artifact"), "a" * 40)
        observation = self.observe(self.context)
        self.assertEqual(observation.reason, "HOST_CONTROL_DELIVERY_REVISION_NOT_VALIDATED")
        self.assertFalse(self.assess(self.context).all_required_criteria_proven)

    def test_executed_control_on_final_delivery_proves_current_revision(self):
        self.reference = CanonicalExecutionEvidenceReference(
            "receipt", "action", "report", "b" * 40, canonical_digest("artifact"), "a" * 40)
        context = deepcopy(self.context)
        context["candidate_sha"] = "b" * 40
        self.assertEqual(self.observe(context).result, "PASS")
        self.assertTrue(self.assess(context).all_required_criteria_proven)


if __name__ == "__main__":
    unittest.main()
