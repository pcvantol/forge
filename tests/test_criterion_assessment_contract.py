"""Approved criterion semantics, compatibility and canonical intake binding."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from forge.governance_authority import (
    ArchitecturePlanningEvidence, CanonicalArchitectureWorkspace,
    CanonicalBusinessWorkspace, CanonicalGovernanceRepository,
    GovernanceCapability, GovernanceDecision, MissionPlanningEvidenceEnvelope,
)
from forge.intake import MissionIntake, MissionIntakeError
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from forge.models.mission_planner import planning_digest
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime.database import RuntimeDatabase


def requirement(identifier="requirement-synthetic", expected='true'):
    return CriterionEvidenceRequirement(identifier, kind="repository_json", artifact_path="evidence/result.json",
                                        json_pointer="/delivered", expected_json=expected)


def contract(criterion="K1", expected='true'):
    return CriterionAssessmentContract(criterion, (requirement(expected=expected),))


def legacy_mission():
    return ArchitectureMission("mission-synthetic", "candidate-synthetic", "Synthetic", "Summary", "Objective", "Value",
                               "architecture-synthetic", "recommendation-synthetic", acceptance_criteria=("K1",))


def legacy_planning():
    return ArchitecturePlanningEvidence(("scope",), ("evidence/result.json",), ("no unrelated changes",),
                                        ("untrusted evidence",), ("protected delivery",), ("dependency",), 64, 16, "1")


def planning():
    return replace(legacy_planning(), criterion_assessment_contracts=(contract(),), maximum_actions=4,
                   maximum_consecutive_no_progress_actions=2,
                   repository_evidence_source=ApprovedRepositoryEvidenceSource("repository-synthetic", "example/fixture"))


class CriterionAssessmentContractTests(unittest.TestCase):
    def test_exact_expected_json_is_canonical_and_stable(self):
        left = replace(requirement(), expected_json=' {"b": 2, "a": [true, null]} ')
        right = replace(requirement(), expected_json='{"a":[true,null],"b":2}')
        self.assertEqual(left, right)
        self.assertEqual(left.digest, right.digest)
        self.assertEqual(CriterionEvidenceRequirement.from_dict(left.to_dict()), left)
        self.assertNotEqual(left.digest, replace(left, json_pointer="/different").digest)
        self.assertNotEqual(left.digest, replace(left, expected_json='false').digest)

    def test_requirement_sources_cannot_be_conflated(self):
        control = CriterionEvidenceRequirement("check", "control-a", "python3 -m unittest test_a")
        self.assertEqual(CriterionEvidenceRequirement.from_dict(control.to_dict()), control)
        for changes in ({"control_identity": ""}, {"command": ""}, {"artifact_path": "evidence/result.json"},
                        {"kind": "unknown"}, {"expected_json": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(control, **changes)
        with self.assertRaises(ValueError):
            replace(requirement(), command="echo PASS")

    def test_unsafe_or_ambiguous_repository_assertions_are_rejected(self):
        for path in ("/absolute.json", "../escape.json", "a/../b.json", "a//b.json", "a\\b.json", "a?query", "a#fragment", "a%2fb"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                replace(requirement(), artifact_path=path)
        for pointer in ("missing-slash", "/bad~escape", "/bad~", None):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                replace(requirement(), json_pointer=pointer)
        for expected in ("", "NaN", "Infinity", "1e999", '{"a":1,"a":2}', "broken"):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                replace(requirement(), expected_json=expected)
        self.assertEqual(replace(requirement(), json_pointer="/a~1b/~0").json_pointer, "/a~1b/~0")
        self.assertEqual(replace(requirement(), json_pointer="").json_pointer, "")

    def test_repository_source_cannot_be_an_arbitrary_url_or_path(self):
        for repository in ("https://example.invalid/repository", "example/../fixture", "example/fixture?query", "example/..", "example/fixture#part"):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                ApprovedRepositoryEvidenceSource("synthetic", repository)
        source = ApprovedRepositoryEvidenceSource("synthetic", "example/fixture")
        self.assertEqual(ApprovedRepositoryEvidenceSource.from_dict(source.to_dict()), source)

    def test_contract_is_exact_conjunctive_and_order_independent(self):
        a = CriterionEvidenceRequirement("a", "control-a", "check a")
        b = CriterionEvidenceRequirement("b", "control-b", "check b")
        first = CriterionAssessmentContract("K1", (b, a))
        second = CriterionAssessmentContract("K1", (a, b))
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(CriterionAssessmentContract.from_dict(first.to_dict()), first)
        self.assertNotEqual(first.digest, replace(first, criterion="K1 ").digest)
        self.assertNotEqual(first.digest, replace(first, validity_policy="historical_delivery").digest)
        for changes in ({"requirements": ()}, {"requirements": (a, a)},
                        {"requirements": (a, replace(a, requirement_id="alias"))},
                        {"requirements": (a, replace(b, requirement_id="a"))},
                        {"validity_policy": "always"}, {"schema_version": "future"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(first, **changes)

    def test_contracts_require_explicit_finite_continuation_and_repository_source(self):
        for changes in ({"maximum_actions": None}, {"maximum_actions": True}, {"maximum_actions": 0},
                        {"maximum_actions": 1.5}, {"maximum_consecutive_no_progress_actions": None},
                        {"maximum_consecutive_no_progress_actions": 0},
                        {"maximum_consecutive_no_progress_actions": 5}, {"repository_evidence_source": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(planning(), **changes)

    def test_mission_contracts_cover_exact_acceptance_and_reject_conflicting_requirement_ids(self):
        evidence = planning()
        mission = replace(legacy_mission(), criterion_assessment_contracts=evidence.criterion_assessment_contracts,
                          maximum_actions=4, maximum_consecutive_no_progress_actions=2,
                          repository_evidence_source=evidence.repository_evidence_source)
        self.assertEqual(ArchitectureMission.from_dict(mission.to_dict()), mission)
        with self.assertRaises(ValueError):
            replace(mission, acceptance_criteria=("K1", "K2"))
        with self.assertRaises(ValueError):
            replace(evidence, criterion_assessment_contracts=(contract(), contract("K2", "false")))
        with self.assertRaises(ValueError):
            replace(evidence, criterion_assessment_contracts=(contract(), contract()))

    def test_legacy_serialization_omits_new_fields_and_retains_original_digests(self):
        mission, evidence = legacy_mission(), legacy_planning()
        additions = {"criterion_assessment_contracts", "maximum_actions", "maximum_consecutive_no_progress_actions", "repository_evidence_source"}
        self.assertTrue(additions.isdisjoint(mission.to_dict()))
        self.assertTrue(additions.isdisjoint(evidence.to_dict()))
        self.assertEqual(ArchitectureMission.from_dict(mission.to_dict()), mission)
        self.assertEqual(ArchitecturePlanningEvidence.from_dict(evidence.to_dict()), evidence)
        self.assertEqual(planning_digest(mission), "sha256:7a256ae0a560807238ffaaef671f52248300c2c911d97340ba2f62abb3ae0b98")
        self.assertEqual(planning_digest(evidence), "sha256:ac50e930d6c0db39ae1dea188af8833d5f1f3aafa00b8c6f876caca761624765")

    def test_planning_roundtrip_binds_source_and_contract_ceiling(self):
        original = planning()
        self.assertEqual(ArchitecturePlanningEvidence.from_dict(original.to_dict()), original)
        for changed in (replace(original, maximum_actions=5),
                        replace(original, criterion_assessment_contracts=(contract(expected="false"),)),
                        replace(original, repository_evidence_source=ApprovedRepositoryEvidenceSource("synthetic", "example/other"))):
            self.assertNotEqual(changed.digest, original.digest)


class CriterionApprovalBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.db = RuntimeDatabase(self.root, path=self.root / "synthetic-runtime.db")
        self.operators = InstallationOperatorService(self.db, lambda: NamedOperatorIdentity("synthetic-operator", 501))
        self.context = self.operators.first_bind()
        self.repository = CanonicalGovernanceRepository._for_test(self.db, self.operators)

    def tearDown(self):
        self.db.close()
        self.temporary.cleanup()

    def approve(self, evidence):
        CanonicalBusinessWorkspace(self.repository, self.context).approve(
            decision_id="business-synthetic", candidate_id="candidate-synthetic", revision="1",
            scope=evidence.scope, gates=("business",))
        CanonicalArchitectureWorkspace(self.repository, self.context).approve(
            decision_id="architecture-synthetic", candidate_id="candidate-synthetic", revision="1", planning=evidence)

    def envelope(self, evidence):
        return MissionPlanningEvidenceEnvelope.compose(
            self.repository, subject_id="candidate-synthetic", subject_revision="1",
            business_decision_id="business-synthetic", architecture_decision_id="architecture-synthetic", planning=evidence)

    def mission(self, evidence, envelope):
        identifier = self.db.allocate_next_mission_id(source="canonical-governance-envelope:" + envelope.digest, allocated_at="synthetic-time")
        return replace(legacy_mission(), id=identifier, scope=evidence.scope,
                       status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
                       criterion_assessment_contracts=evidence.criterion_assessment_contracts,
                       maximum_actions=evidence.maximum_actions,
                       maximum_consecutive_no_progress_actions=evidence.maximum_consecutive_no_progress_actions,
                       repository_evidence_source=evidence.repository_evidence_source)

    def test_approval_binds_exact_planning_and_rejects_post_approval_expansion(self):
        evidence = planning()
        self.approve(evidence)
        self.assertEqual(self.repository.decision("architecture-synthetic")["evidence"]["planning_digest"], evidence.digest)
        self.assertEqual(self.envelope(evidence).validate(self.repository).planning, evidence)
        for changed in (replace(evidence, maximum_actions=5), replace(evidence, write_scopes=("expanded",)),
                        replace(evidence, criterion_assessment_contracts=(contract(expected="false"),)),
                        replace(evidence, repository_evidence_source=ApprovedRepositoryEvidenceSource("repository-synthetic", "example/other")),
                        legacy_planning()):
            with self.subTest(changed=changed), self.assertRaisesRegex(ValueError, "exact Architecture approval"):
                self.envelope(changed)
        self.assertEqual(self.db._connection.execute("SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 0)

    def test_legacy_approval_cannot_be_reinterpreted_as_approved_criterion_semantics(self):
        self.approve(legacy_planning())
        self.assertNotIn("planning_digest", self.repository.decision("architecture-synthetic")["evidence"])
        with self.assertRaisesRegex(ValueError, "exact Architecture approval"):
            self.envelope(planning())
        self.assertEqual(self.envelope(legacy_planning()).validate(self.repository).planning, legacy_planning())

    def test_intake_preserves_contract_across_replay_and_rejects_changed_mission_claims(self):
        evidence = planning()
        self.approve(evidence)
        envelope = self.envelope(evidence)
        mission = self.mission(evidence, envelope)
        intake = MissionIntake(None, lambda: "synthetic-time")
        accepted = intake.admit_canonical_approved_mission(mission, envelope, self.repository)
        self.assertEqual(accepted.actions, ())
        self.assertEqual(intake.admit_canonical_approved_mission(mission, envelope, self.repository), accepted)
        for changed in (replace(mission, maximum_actions=5), replace(mission, candidate_id="different-candidate"),
                        replace(mission, architecture_review_reference="different-approval"),
                        replace(mission, scope=("different-scope",)),
                        replace(mission, criterion_assessment_contracts=(contract(expected="false"),)),
                        replace(mission, repository_evidence_source=ApprovedRepositoryEvidenceSource("repository-synthetic", "example/other"))):
            with self.subTest(changed=changed), self.assertRaisesRegex(MissionIntakeError, "differs from canonical"):
                intake.admit_canonical_approved_mission(changed, envelope, self.repository)
        self.assertEqual(self.db._connection.execute("SELECT COUNT(*) FROM mission_state").fetchone()[0], 1)

    def test_store_reopening_preserves_approval_and_contract(self):
        evidence = planning()
        self.approve(evidence)
        envelope = self.envelope(evidence)
        mission = self.mission(evidence, envelope)
        accepted = MissionIntake(None, lambda: "synthetic-time").admit_canonical_approved_mission(mission, envelope, self.repository)
        self.db.close()
        self.db = RuntimeDatabase(self.root, path=self.root / "synthetic-runtime.db")
        self.operators = InstallationOperatorService(self.db, lambda: NamedOperatorIdentity("synthetic-operator", 501))
        self.context = self.operators.context()
        self.repository = CanonicalGovernanceRepository._for_test(self.db, self.operators)
        restored = MissionPlanningEvidenceEnvelope.compose(
            self.repository, subject_id="candidate-synthetic", subject_revision="1",
            business_decision_id="business-synthetic", architecture_decision_id="architecture-synthetic",
            planning=ArchitecturePlanningEvidence.from_dict(evidence.to_dict()))
        self.assertEqual(restored, envelope)
        self.assertEqual(MissionIntake(None, lambda: "later-synthetic-time").admit_canonical_approved_mission(
            ArchitectureMission.from_dict(mission.to_dict()), restored, self.repository), accepted)
        self.assertEqual(self.db._connection.execute("SELECT COUNT(*) FROM mission_state").fetchone()[0], 1)
        self.assertEqual(self.db._connection.execute("SELECT COUNT(*) FROM governance_decisions").fetchone()[0], 2)

    def test_contract_bearing_mission_cannot_use_legacy_admission(self):
        evidence = planning()
        self.approve(evidence)
        envelope = self.envelope(evidence)
        mission = self.mission(evidence, envelope)
        with self.assertRaisesRegex(MissionIntakeError, "canonical approval evidence"):
            MissionIntake(None, lambda: "synthetic-time").admit_approved_mission(mission)


if __name__ == "__main__":
    unittest.main()
