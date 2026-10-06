"""Approved effect scope is a durable governance boundary."""

from dataclasses import replace
from types import SimpleNamespace
import unittest

from forge.lifecycle import MissionCandidate
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.mission_effect import EffectRequest, MissionEffectPolicy
from forge.models.mission_recommendation import RequiredDiscipline
from forge.governance_authority import ArchitecturePlanningEvidence
from forge.models.criterion_observation import canonical_digest
from forge.models.action import EngineeringAction
from forge.models.producer import RepositoryRevisionBinding
from forge.runtime.dynamic_mission import InstalledDynamicMissionError, InstalledDynamicMissionRuntime


class MissionEffectPolicyTests(unittest.TestCase):
    def test_supported_delivery_modes_keep_explicit_empty_writes(self) -> None:
        cases = (
            ("READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY", ()),
            ("DOCUMENTATION_ONLY", "GIT", ("docs/",)),
            ("ARCHITECTURE_DESIGN_ONLY", "EVIDENCE_ONLY", ()),
            ("ARCHITECTURE_DESIGN_ONLY", "GIT", ("docs/design.md",)),
            ("BOUNDED_REPOSITORY_CHANGE", "GIT", ("src/",)),
        )
        for mode, delivery, writes in cases:
            with self.subTest(mode=mode, delivery=delivery):
                policy = MissionEffectPolicy(mode, delivery, ("docs/",), writes)
                self.assertEqual(MissionEffectPolicy.from_dict(policy.to_dict()), policy)
                self.assertEqual(policy.to_dict()["write_paths"], list(writes))
                self.assertEqual(policy.to_dict()["read_paths"], ["docs/"])

    def test_rejects_implicit_write_and_reserved_or_aliased_paths(self) -> None:
        invalid = (
            ("READ_ONLY_ASSESSMENT", "GIT", ("docs/",)),
            ("READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY", ("docs/",)),
            ("DOCUMENTATION_ONLY", "GIT", ()),
            ("DOCUMENTATION_ONLY", "GIT", ("src/app.py",)),
            ("BOUNDED_REPOSITORY_CHANGE", "GIT", (".git/config",)),
            ("BOUNDED_REPOSITORY_CHANGE", "GIT", ("docs/../src/",)),
            ("BOUNDED_REPOSITORY_CHANGE", "GIT", ("Docs/", "docs/")),
        )
        for mode, delivery, writes in invalid:
            with self.subTest(mode=mode, writes=writes):
                with self.assertRaises(ValueError):
                    MissionEffectPolicy(mode, delivery, ("docs/",), writes)

    def test_effect_request_pins_source_and_substantive_criteria(self) -> None:
        policy = MissionEffectPolicy("READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY", ("docs/",), ())
        request = EffectRequest(policy, "a" * 40,
                                (("criterion-1", "Assess the documented architecture boundary."),))
        self.assertEqual(EffectRequest.from_dict(request.to_dict()), request)
        self.assertEqual(request.to_dict()["write_paths"], [])
        with self.assertRaisesRegex(ValueError, "full SHA"):
            EffectRequest(policy, "ambient-main", request.criteria)
        with self.assertRaisesRegex(ValueError, "criterion"):
            EffectRequest(policy, "a" * 40, (("criterion-1", "Looks good"),))

    def test_candidate_and_architecture_approval_digest_bind_same_effect(self) -> None:
        effect = MissionEffectPolicy("READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY", ("docs/",), ())
        candidate = MissionCandidate("candidate", "recommendation", "Read", "Assess docs", ("repo",),
                                     ("Report current documentation gaps",), ("No repository writes",),
                                     effect_policy=effect)
        self.assertEqual(MissionCandidate.from_dict(candidate.to_dict()), candidate)
        preview = ArchitectureMission(
            "MISSION-PREVIEW", candidate.id, candidate.title, candidate.objective,
            "Assess docs", "Useful report", "architecture-decision", candidate.recommendation_id,
            candidate.scope, candidate.architecture_constraints, candidate.acceptance_criteria,
            ("read only",), ("dependency",), ("analysis",),
            (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("stale source",),
            ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING, effect_policy=effect,
        )
        planning = ArchitecturePlanningEvidence(
            candidate.scope, (), ("No repository writes",), ("stale source",), ("owner review",),
            ("dependency",), 1000, 500, "candidate-revision",
            mission_spec_digest=canonical_digest(preview.to_dict()), effect_policy=effect,
        )
        self.assertEqual(ArchitecturePlanningEvidence.from_dict(planning.to_dict()), planning)
        self.assertEqual(ArchitectureMission.from_dict(preview.to_dict()), preview)
        self.assertNotEqual(canonical_digest(candidate.to_dict()),
                            canonical_digest(replace(candidate, effect_policy=MissionEffectPolicy(
                                "ARCHITECTURE_DESIGN_ONLY", "EVIDENCE_ONLY", ("docs/",), ())).to_dict()))
        with self.assertRaisesRegex(ValueError, "write scopes differ"):
            replace(planning, write_scopes=("docs/",))

        state = SimpleNamespace(mission=preview.to_dict(),
                                admission_contract={"planning": planning.to_dict()})
        action = EngineeringAction(1, "action-1", "intent-1", "1", "Read documentation",
                                   candidate.acceptance_criteria)
        binding = RepositoryRevisionBinding(
            "a" * 40, None, "repository-truth:approved", "sha256:" + "b" * 64,
        )
        request = InstalledDynamicMissionRuntime._effect_request(state, action, binding)
        self.assertEqual(request.policy, effect)
        self.assertEqual(request.source_revision, binding.requested_revision)
        self.assertEqual([row["description"] for row in request.to_dict()["criteria"]],
                         list(candidate.acceptance_criteria))
        with self.assertRaisesRegex(InstalledDynamicMissionError, "outside exact Mission approval"):
            InstalledDynamicMissionRuntime._effect_request(
                state, replace(action, expected_evidence=("Unapproved objective",)), binding)


if __name__ == "__main__":
    unittest.main()
