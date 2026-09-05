import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from forge.governance_authority import (
    ArchitecturePlanningEvidence,
    CanonicalArchitectureWorkspace,
    CanonicalBusinessWorkspace,
    CanonicalGovernanceRepository,
    GovernanceCapability,
    GovernanceDecision,
    MissionPlanningEvidenceEnvelope,
)
from forge.business import BusinessWorkspace
from forge.architecture import ArchitectureWorkspace
from forge.intake import MissionIntake, MissionIntakeError
from forge.models.architecture_mission import ArchitectureMissionStatus
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime.database import RuntimeDatabase


class GovernanceAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "runtime.db"
        self.db = RuntimeDatabase(self.root, path=self.path)
        self.ops = InstallationOperatorService(self.db, lambda: NamedOperatorIdentity("operator-a", 501))
        self.context = self.ops.first_bind()
        self.repository = CanonicalGovernanceRepository._for_test(self.db, self.ops)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    @staticmethod
    def planning(revision="1"):
        return ArchitecturePlanningEvidence(
            scope=("bounded planning qualification",), write_scopes=("NONE",),
            non_goals=("action execution",), risk_inputs=("untrusted provider output",),
            human_gates=("security review",), dependencies=("G001",),
            context_input_bound=64, context_output_bound=16, provenance_revision=revision,
        )

    def test_runtime_bound_workspaces_persist_business_architecture_and_envelope(self):
        business = BusinessWorkspace.for_runtime(self.db, self.repository, self.context)
        architecture = ArchitectureWorkspace.for_runtime(self.db, self.repository, self.context)
        business.approve(decision_id="business-1", candidate_id="candidate-1", revision="1", scope=("bounded planning qualification",), gates=("business",))
        architecture.approve(decision_id="architecture-1", candidate_id="candidate-1", revision="1", planning=self.planning())
        envelope = MissionPlanningEvidenceEnvelope.compose(
            self.repository, subject_id="candidate-1", subject_revision="1",
            business_decision_id="business-1", architecture_decision_id="architecture-1", planning=self.planning(),
        )
        self.assertEqual(envelope.validate(self.repository), envelope)
        # Intake validates only; no Mission identifier or runtime state is created here.
        intake = MissionIntake(None, lambda: "2026-01-01T00:00:00Z")
        self.assertEqual(intake.validate_approved_evidence(envelope, self.repository), envelope)
        self.assertEqual(self.db._connection.execute("SELECT COUNT(*) FROM mission_state").fetchone()[0], 0)

    def test_workspace_cannot_bind_an_arbitrary_database_as_canonical_authority(self):
        with tempfile.TemporaryDirectory() as other:
            other_db = RuntimeDatabase(Path(other), path=Path(other) / "runtime.db")
            with self.assertRaises(Exception):
                BusinessWorkspace.for_runtime(other_db, self.repository, self.context)
            with self.assertRaises(Exception):
                ArchitectureWorkspace.for_runtime(other_db, self.repository, self.context)
            other_db.close()

    def test_production_repository_requires_the_resolved_runtime_and_has_no_operator_grant_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = RuntimeDatabase(root)
            operators = InstallationOperatorService(canonical, lambda: NamedOperatorIdentity("operator-a", 501))
            operators.first_bind()
            repository = CanonicalGovernanceRepository(canonical, operators)
            self.assertFalse(hasattr(repository, "grant_current_operator"))
            self.assertFalse(hasattr(repository, "bootstrap_grant"))
            self.assertFalse(hasattr(repository, "_bootstrap_authority"))
            alternate = RuntimeDatabase(root, path=root / "alternate-runtime.db")
            with self.assertRaises(ValueError):
                CanonicalGovernanceRepository(alternate, InstallationOperatorService(alternate, lambda: NamedOperatorIdentity("operator-a", 501)))
            alternate.close()
            canonical.close()

    def test_canonical_intake_cannot_allocate_before_envelope_validation(self):
        class Store:
            def __init__(self): self.calls = 0
            def create_pending(self, *_args, **_kwargs): self.calls += 1; return "pending"
        store = Store()
        intake = MissionIntake(store, lambda: "now")
        invalid = MissionPlanningEvidenceEnvelope("wrong", "candidate", "1", "business", "architecture", self.planning(), "sha256:bad")
        mission = SimpleNamespace(status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING)
        with self.assertRaises(MissionIntakeError):
            intake.admit_canonical_approved_mission(mission, invalid, self.repository)
        self.assertEqual(store.calls, 0)

    def test_capability_identity_and_immutability_fail_closed(self):
        decision = GovernanceDecision("decision-1", "candidate-1", "1", GovernanceCapability.BUSINESS_APPROVAL, "approved", ("scope",), ("gate",))
        self.repository.record(decision, self.context)
        with self.assertRaises(sqlite3.DatabaseError):
            self.db._connection.execute("UPDATE governance_decisions SET subject_id='x'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db._connection.execute("DELETE FROM governance_decisions")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db._connection.execute("INSERT INTO governance_decisions VALUES ('raw', 'x', 'x', '1', 'BUSINESS_APPROVAL', NULL, '{}', 'sha256:raw', 'now')")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db._connection.execute("INSERT INTO governance_authority VALUES ('x', 'x', 'BUSINESS_APPROVAL', 1, 'now')")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db._connection.execute("UPDATE governance_authority SET capability='SECURITY_APPROVAL'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db._connection.execute("DELETE FROM governance_authority")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db._connection.execute("UPDATE governance_capability_grants SET capability='SECURITY_APPROVAL'")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db._connection.execute("DELETE FROM governance_capability_grants")
        forged = type(self.context)(self.context.installation_id, "other", self.context.binding_version)
        with self.assertRaises(PermissionError):
            self.repository.record(replace(decision, decision_id="decision-2"), forged)

    def test_wrong_capability_conflict_stale_and_tampered_envelope_fail_closed(self):
        self.repository.record(GovernanceDecision("architecture", "candidate-1", "1", GovernanceCapability.ARCHITECTURE_APPROVAL, "approved", ("scope",), ("gate",)), self.context)
        self.repository.record(GovernanceDecision("business", "candidate-1", "1", GovernanceCapability.BUSINESS_APPROVAL, "approved", ("scope",), ("gate",)), self.context)
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.record(GovernanceDecision("conflict", "candidate-1", "1", GovernanceCapability.BUSINESS_APPROVAL, "rejected", ("scope",), ("gate",)), self.context)
        with self.assertRaises(ValueError):
            MissionPlanningEvidenceEnvelope.compose(self.repository, subject_id="candidate-1", subject_revision="1", business_decision_id="business", architecture_decision_id="architecture", planning=self.planning("2"))
        envelope = MissionPlanningEvidenceEnvelope.compose(self.repository, subject_id="candidate-1", subject_revision="1", business_decision_id="business", architecture_decision_id="architecture", planning=self.planning())
        with self.assertRaises(MissionIntakeError):
            MissionIntake(None, lambda: "now").validate_approved_evidence(replace(envelope, digest="sha256:tampered"), self.repository)

    def test_cross_installation_replay_and_restart_fail_closed(self):
        CanonicalBusinessWorkspace(self.repository, self.context).approve(decision_id="business", candidate_id="candidate", revision="1", scope=("scope",), gates=("gate",))
        CanonicalArchitectureWorkspace(self.repository, self.context).approve(decision_id="architecture", candidate_id="candidate", revision="1", planning=self.planning())
        envelope = MissionPlanningEvidenceEnvelope.compose(self.repository, subject_id="candidate", subject_revision="1", business_decision_id="business", architecture_decision_id="architecture", planning=self.planning())
        self.db.close()
        self.db = RuntimeDatabase(self.root, path=self.path)
        self.ops = InstallationOperatorService(self.db, lambda: NamedOperatorIdentity("operator-a", 501))
        self.context = self.ops.context()
        self.repository = CanonicalGovernanceRepository._for_test(self.db, self.ops)
        self.assertEqual(envelope.validate(self.repository).digest, envelope.digest)
        with tempfile.TemporaryDirectory() as other:
            other_db = RuntimeDatabase(Path(other), path=Path(other) / "runtime.db")
            other_ops = InstallationOperatorService(other_db, lambda: NamedOperatorIdentity("operator-a", 501))
            other_ops.first_bind()
            with self.assertRaises(ValueError):
                envelope.validate(CanonicalGovernanceRepository._for_test(other_db, other_ops))
            other_db.close()


if __name__ == "__main__":
    unittest.main()
