"""Public Candidate-to-installed-Mission governance and restart boundaries."""

from dataclasses import replace
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread, current_thread
import unittest
from unittest.mock import patch

from forge.governance import resolve_governance_profile
from forge.governance_authority import ArchitecturePlanningEvidence, CanonicalGovernanceRepository
from forge.governed_candidate_intake import GovernedCandidateIntake, GovernedCandidateIntakeError
from forge.lifecycle import LifecycleError, MissionCandidate, MissionRecommendation, RecommendationLifecycleStore, RecommendationStatus
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_assessment import ApprovedRepositoryEvidenceSource
from forge.models.criterion_observation import canonical_digest
from forge.models.mission_recommendation import RequiredDiscipline
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime import RuntimeBootstrap
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime


class GovernedCandidateIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        data_root = self.root / "runtime"
        self.database = RuntimeBootstrap(data_root=data_root, forge_version="test").open()
        operators = InstallationOperatorService(
            self.database, lambda: NamedOperatorIdentity("candidate-operator", 501),
        )
        operators.first_bind()
        repository = CanonicalGovernanceRepository.for_runtime(
            self.database, lambda: NamedOperatorIdentity("candidate-operator", 501), data_root=data_root,
        )
        self.runtime = InstalledDynamicMissionRuntime(
            self.database, repository, data_root=str(data_root), provider=object(), host=object(),
        )
        self.lifecycle = RecommendationLifecycleStore(self.root / "governance" / "lifecycle.sqlite")
        recommendation = MissionRecommendation(
            "recommendation", "Bounded proof", "qualification", "Prove the approved result.",
            "Deliver one property.", "Inspectable value.", "Verified output.", "Preserve boundaries.",
            ("repository:fixture",), "review:fixture", ("fixture-dependency",),
            ("Defer proof.",), 90, "2026-10-03T00:00:00Z",
        )
        self.lifecycle.create_recommendation(recommendation, actor="portfolio", rationale="Fixture input.")
        self.lifecycle.transition(recommendation.id, RecommendationStatus.RECOMMENDED, actor="portfolio",
                                  occurred_at="2026-10-03T00:00:01Z", rationale="Ready for review.")
        self.candidate = self.lifecycle.create_candidate(MissionCandidate(
            "candidate", recommendation.id, recommendation.title, recommendation.engineering_summary,
            ("fixture-scope",), ("property exists",), ("no extra effects",), recommendation.dependencies,
        ))
        self.bridge = GovernedCandidateIntake(self.lifecycle, self.runtime, resolve_governance_profile("duo"))
        self.addCleanup(self.lifecycle.close)
        self.addCleanup(self.database.close)
        self.addCleanup(self.directory.cleanup)

    def approved_input(self) -> tuple[ArchitectureMission, ArchitecturePlanningEvidence]:
        revision, _, architecture_id = self.bridge.decision_ids(self.candidate.id)
        preview = ArchitectureMission(
            "MISSION-PREVIEW", self.candidate.id, self.candidate.title, self.candidate.objective,
            "Prove the approved result.", "Inspectable value.", architecture_id,
            self.candidate.recommendation_id, self.candidate.scope,
            self.candidate.architecture_constraints, self.candidate.acceptance_criteria,
            ("fixture assumption",), self.candidate.dependencies, ("fixture host",),
            (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("scope drift",),
            ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
        )
        planning = ArchitecturePlanningEvidence(
            self.candidate.scope, ("fixture-write",), ("no extra effects",),
            ("scope drift",), ("owner review",), self.candidate.dependencies,
            1000, 500, revision, mission_spec_digest=canonical_digest(preview.to_dict()),
        )
        return preview, planning

    def approve(self, preview: ArchitectureMission, planning: ArchitecturePlanningEvidence) -> None:
        self.bridge.approve_business(self.candidate.id, actor="business_owner",
                                     occurred_at="2026-10-03T00:00:02Z", rationale="Value approved.",
                                     human_gates=planning.human_gates)
        self.bridge.approve_architecture(self.candidate.id, preview, planning,
                                         actor="platform_architect", occurred_at="2026-10-03T00:00:03Z",
                                         rationale="Exact planning approved.")

    @contextmanager
    def reopened_bridge(self):
        data_root = self.root / "runtime"
        with RuntimeBootstrap(data_root=data_root, forge_version="test").open() as database:
            repository = CanonicalGovernanceRepository.for_runtime(
                database, lambda: NamedOperatorIdentity("candidate-operator", 501), data_root=data_root,
            )
            runtime = InstalledDynamicMissionRuntime(
                database, repository, data_root=str(data_root), provider=object(), host=object(),
            )
            with RecommendationLifecycleStore(self.root / "governance" / "lifecycle.sqlite") as lifecycle:
                yield GovernedCandidateIntake(lifecycle, runtime, resolve_governance_profile("duo"))

    @contextmanager
    def foreign_installation_bridge(self):
        data_root = self.root / "second-runtime"
        with RuntimeBootstrap(data_root=data_root, forge_version="test").open() as database:
            identity = lambda: NamedOperatorIdentity("second-operator", 502)
            InstallationOperatorService(database, identity).first_bind()
            repository = CanonicalGovernanceRepository.for_runtime(
                database, identity, data_root=data_root,
            )
            runtime = InstalledDynamicMissionRuntime(
                database, repository, data_root=str(data_root), provider=object(), host=object(),
            )
            yield GovernedCandidateIntake(self.lifecycle, runtime, resolve_governance_profile("duo")), database

    def test_exact_candidate_enters_zero_action_runtime_once_and_replays_after_restart(self) -> None:
        preview, planning = self.approved_input()
        self.approve(preview, planning)
        first = self.bridge.admit(self.candidate.id, preview, planning, occurred_at="2026-10-03T00:00:04Z")
        self.assertEqual(first.status.value, "APPROVED_PLANNABLE")
        self.assertEqual(first.actions, ())
        self.assertEqual(first.admission_contract["subject_revision"], canonical_digest(self.candidate.to_dict()))
        with self.reopened_bridge() as reopened:
            self.assertEqual(reopened.admit(self.candidate.id, preview, planning,
                                            occurred_at="2026-10-03T00:00:05Z"), first)
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 1)
        self.assertEqual(self.lifecycle.get_recommendation("recommendation").status,
                         RecommendationStatus.MISSION_ALLOCATED)

    def test_two_approved_repository_sources_admit_without_serial_execution(self) -> None:
        self.candidate = self.lifecycle.update_candidate(
            self.candidate.id, scope=("repository-a", "repository-b"))
        preview, planning = self.approved_input()
        sources = (
            ApprovedRepositoryEvidenceSource("repository-a", "example/repository-a"),
            ApprovedRepositoryEvidenceSource("repository-b", "example/repository-b"),
        )
        preview = replace(preview, repository_evidence_sources=sources)
        planning = replace(planning, repository_evidence_sources=sources,
                           mission_spec_digest=canonical_digest(preview.to_dict()))
        self.approve(preview, planning)
        state = self.bridge.admit(self.candidate.id, preview, planning,
                                  occurred_at="2026-10-03T00:00:04Z")
        self.assertEqual(state.status.value, "APPROVED_PLANNABLE")
        self.assertEqual(state.actions, ())
        with self.assertRaisesRegex(ValueError, "serial execution cannot consume"):
            self.runtime._approved_origin(state)  # noqa: SLF001 - assert serial boundary

    def test_missing_or_wrong_actor_approval_creates_no_mission(self) -> None:
        preview, planning = self.approved_input()
        with self.assertRaises(GovernedCandidateIntakeError):
            self.bridge.admit(self.candidate.id, preview, planning, occurred_at="now")
        with self.assertRaises(PermissionError):
            self.bridge.approve_business(self.candidate.id, actor="stranger", occurred_at="now",
                                         rationale="No authority.", human_gates=planning.human_gates)
        with self.assertRaises(PermissionError):
            self.bridge.approve_business(self.candidate.id, actor="platform_architect", occurred_at="now",
                                         rationale="Wrong role.", human_gates=planning.human_gates)
        with self.assertRaises(GovernedCandidateIntakeError):
            self.bridge.approve_architecture(self.candidate.id, preview, planning,
                                             actor="platform_architect", occurred_at="now", rationale="Too early.")
        with self.assertRaises(PermissionError):
            self.bridge.approve_architecture(self.candidate.id, preview, planning,
                                             actor="business_owner", occurred_at="now", rationale="Wrong role.")
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 0)

    def test_candidate_change_after_business_approval_invalidates_architecture(self) -> None:
        preview, planning = self.approved_input()
        self.bridge.approve_business(self.candidate.id, actor="business_owner",
                                     occurred_at="now", rationale="Value approved.",
                                     human_gates=planning.human_gates)
        self.lifecycle.update_candidate(self.candidate.id, objective="Changed after approval.")
        with self.assertRaises(GovernedCandidateIntakeError):
            self.bridge.approve_business(self.candidate.id, actor="business_owner",
                                         occurred_at="later", rationale="Must not approve changed content.",
                                         human_gates=planning.human_gates)
        with self.assertRaises(GovernedCandidateIntakeError):
            self.bridge.approve_architecture(self.candidate.id, preview, planning,
                                             actor="platform_architect", occurred_at="later",
                                             rationale="Must not reuse approval.")
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM governance_decisions").fetchone()[0], 1)
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 0)

    def test_changed_mission_contract_cannot_allocate_or_reuse_approval(self) -> None:
        preview, planning = self.approved_input()
        self.approve(preview, planning)
        changed = replace(preview, acceptance_criteria=("different criterion",))
        with self.assertRaises(GovernedCandidateIntakeError):
            self.bridge.admit(self.candidate.id, changed, planning, occurred_at="now")
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 0)

    def test_stale_candidate_after_both_approvals_cannot_allocate(self) -> None:
        preview, planning = self.approved_input()
        self.approve(preview, planning)
        self.lifecycle.update_candidate(self.candidate.id, objective="Changed after both approvals.")
        with self.assertRaises(GovernedCandidateIntakeError):
            self.bridge.admit(self.candidate.id, preview, planning, occurred_at="now")
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 0)

    def test_candidate_change_between_bridge_read_and_allocation_rejects_before_id(self) -> None:
        preview, planning = self.approved_input()
        self.approve(preview, planning)
        original_allocate = self.lifecycle.allocate
        with RecommendationLifecycleStore(self.root / "governance" / "lifecycle.sqlite") as competing:
            def update_before_allocate(*args, **kwargs):
                competing.update_candidate(self.candidate.id, objective="Changed between read and allocation.")
                return original_allocate(*args, **kwargs)

            with patch.object(self.lifecycle, "allocate", side_effect=update_before_allocate):
                with self.assertRaisesRegex(LifecycleError, "Candidate content changed"):
                    self.bridge.admit(self.candidate.id, preview, planning, occurred_at="now")
        self.assertIsNone(self.lifecycle.allocation_for_recommendation(self.candidate.recommendation_id))
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 0)

    def test_candidate_update_waiting_on_allocation_cannot_overwrite_frozen_row(self) -> None:
        preview, planning = self.approved_input()
        self.approve(preview, planning)
        revision = canonical_digest(self.candidate.to_dict())
        ready, start, read_unfrozen = Event(), Event(), Event()
        outcomes: list[object] = []
        original_from_dict = MissionCandidate.from_dict

        def mark_candidate_read(document):
            if current_thread().name == "candidate-updater":
                read_unfrozen.set()
            return original_from_dict(document)

        def competing_update() -> None:
            with RecommendationLifecycleStore(self.root / "governance" / "lifecycle.sqlite") as competing:
                ready.set()
                if not start.wait(5):
                    outcomes.append(TimeoutError("allocation did not start"))
                    return
                try:
                    competing.update_candidate(self.candidate.id, objective="Late competing update.")
                    outcomes.append("updated")
                except LifecycleError as error:
                    outcomes.append(error)

        worker = Thread(target=competing_update, name="candidate-updater")
        with patch.object(MissionCandidate, "from_dict", side_effect=mark_candidate_read):
            worker.start()
            self.assertTrue(ready.wait(5))

            def allocate_id(_source: str, _timestamp: str) -> str:
                start.set()
                read_unfrozen.wait(1)
                return "MISSION-0001"

            allocation = self.lifecycle.allocate(
                self.candidate.id, actor="forge", occurred_at="now", rationale="Approved Candidate.",
                allocate_mission_id=allocate_id, expected_candidate_digest=revision,
            )
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(allocation.mission_id, "MISSION-0001")
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], LifecycleError)
        self.assertEqual(self.lifecycle.get_candidate(self.candidate.id), self.candidate)

    def test_foreign_installation_decision_cannot_allocate(self) -> None:
        preview, planning = self.approved_input()
        self.approve(preview, planning)
        original = self.runtime.repository.decision

        def foreign_decision(decision_id: str) -> dict:
            document = original(decision_id)
            if decision_id == self.bridge.decision_ids(self.candidate.id)[2]:
                document["installation_id"] = "foreign-installation"
            return document

        with patch.object(self.runtime.repository, "decision", side_effect=foreign_decision):
            with self.assertRaisesRegex(ValueError, "cross-installation"):
                self.bridge.admit(self.candidate.id, preview, planning, occurred_at="now")
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 0)

    def test_allocated_candidate_cannot_replay_into_a_second_installation(self) -> None:
        preview, planning = self.approved_input()
        self.approve(preview, planning)
        with self.foreign_installation_bridge() as (foreign, database):
            foreign.approve_business(self.candidate.id, actor="business_owner",
                                     occurred_at="before-allocation", rationale="Separate synthetic decision.",
                                     human_gates=planning.human_gates)
            foreign.approve_architecture(self.candidate.id, preview, planning,
                                         actor="platform_architect", occurred_at="before-allocation",
                                         rationale="Separate synthetic planning decision.")
            original = self.bridge.admit(self.candidate.id, preview, planning, occurred_at="allocate-in-first")
            self.assertTrue(original.mission_id.startswith("MISSION-"))
            with self.assertRaisesRegex(GovernedCandidateIntakeError, "allocation differs"):
                foreign.admit(self.candidate.id, preview, planning, occurred_at="replay-in-second")
            with self.assertRaisesRegex(GovernedCandidateIntakeError, "another installation"):
                foreign.approve_business(self.candidate.id, actor="business_owner",
                                         occurred_at="after-allocation", rationale="Must not replay.",
                                         human_gates=planning.human_gates)
            self.assertEqual(database._connection.execute(
                "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 0)
            self.assertEqual(database._connection.execute(
                "SELECT COUNT(*) FROM mission_state").fetchone()[0], 0)

    def test_restart_after_allocation_before_intake_reuses_mission_id(self) -> None:
        preview, planning = self.approved_input()
        self.approve(preview, planning)
        with patch.object(self.runtime, "admit", side_effect=RuntimeError("interrupted before intake")):
            with self.assertRaisesRegex(RuntimeError, "interrupted before intake"):
                self.bridge.admit(self.candidate.id, preview, planning, occurred_at="now")
        allocation = self.lifecycle.allocation_for_recommendation(self.candidate.recommendation_id)
        self.assertIsNotNone(allocation)
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_state").fetchone()[0], 0)
        with self.reopened_bridge() as reopened:
            resumed = reopened.admit(self.candidate.id, preview, planning, occurred_at="later")
        self.assertEqual(resumed.mission_id, allocation.mission_id)
        self.assertEqual(self.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
