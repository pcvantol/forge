import sqlite3
import tempfile
import unittest
from hashlib import sha256
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
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.mission_recommendation import RequiredDiscipline
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
            self.assertFalse(hasattr(canonical, "_governance_write"))
            alternate = RuntimeDatabase(root, path=root / "alternate-runtime.db")
            with self.assertRaises(ValueError):
                CanonicalGovernanceRepository(alternate, InstallationOperatorService(alternate, lambda: NamedOperatorIdentity("operator-a", 501)))
            alternate.close()
            canonical.close()

    def test_adoption_rejects_authority_without_matching_adoption_provenance(self):
        # Fresh first-bind provenance is bootstrap, not adoption; an adoption replay
        # must not silently bless mixed provenance.
        with self.assertRaises(PermissionError):
            self.ops.adopt_governance_capabilities(self.context)

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

    def test_canonical_intake_recovers_matching_allocation_without_a_standalone_state_store(self):
        planning = self.planning()
        CanonicalBusinessWorkspace(self.repository, self.context).approve(
            decision_id="business-canonical", candidate_id="candidate-canonical", revision="1",
            scope=planning.scope, gates=("business",),
        )
        CanonicalArchitectureWorkspace(self.repository, self.context).approve(
            decision_id="architecture-canonical", candidate_id="candidate-canonical", revision="1", planning=planning,
        )
        envelope = MissionPlanningEvidenceEnvelope.compose(
            self.repository, subject_id="candidate-canonical", subject_revision="1",
            business_decision_id="business-canonical", architecture_decision_id="architecture-canonical", planning=planning,
        )
        source = "canonical-governance-envelope:" + envelope.digest
        mission_id = self.db.allocate_next_mission_id(source=source, allocated_at="now")
        mission = ArchitectureMission(
            id=mission_id, candidate_id="candidate-canonical", title="Canonical intake", summary="bounded",
            business_objective="qualify", business_value="evidence", architecture_review_reference="architecture-canonical",
            mission_recommendation_reference="business-canonical", scope=("scope",), engineering_constraints=("NONE",),
            acceptance_criteria=("no actions",), technical_assumptions=("runtime owned",), dependencies=("G001",),
            required_capabilities=("planning",), required_disciplines=(RequiredDiscipline.PLATFORM_ARCHITECTURE,),
            risks=("untrusted",), status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
        )
        intake = MissionIntake(None, lambda: "now")
        state = intake.admit_canonical_approved_mission(mission, envelope, self.repository)
        self.assertEqual(state.status.value, "APPROVED_PLANNABLE")
        self.assertEqual(state.resume["evidence_digest"], envelope.digest)
        self.assertEqual(intake.admit_canonical_approved_mission(mission, envelope, self.repository), state)
        self.assertEqual(self.db.allocate_next_mission_id(source=source, allocated_at="later"), mission_id)

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


class GovernanceSchema19MigrationTests(unittest.TestCase):
    """Regression coverage for G001-bound schema-19 runtime recovery."""

    identity = NamedOperatorIdentity("operator-a", 501)

    @staticmethod
    def _drop_governance_objects(database):
        rows = database._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'governance_%'"
        ).fetchall()
        for row in rows:
            database._connection.execute(f"DROP TRIGGER {row['name']}")
        for table in ("governance_decisions", "governance_capability_grants", "governance_authority"):
            database._connection.execute(f"DROP TABLE {table}")

    def _schema19_fixture(self, *, partial=False, bind=True):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        path = root / "runtime.db"
        database = RuntimeDatabase(root, path=path)
        if bind:
            InstallationOperatorService(database, lambda: self.identity).first_bind()
        self._drop_governance_objects(database)
        if partial:
            database._connection.execute("""
                CREATE TABLE governance_capability_grants (
                    grant_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL,
                    operator_id TEXT NOT NULL, capability TEXT NOT NULL,
                    bootstrap_provenance TEXT NOT NULL, digest TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    UNIQUE(installation_id, operator_id, capability)
                )
            """)
        database._set_metadata({"schema_version": "19", "migration_version": "19", "last_migration": "19"})
        database._connection.execute("PRAGMA user_version=19")
        database._connection.commit()
        database.close()
        self.addCleanup(temporary.cleanup)
        return root, path

    @staticmethod
    def _schema_version(path):
        connection = sqlite3.connect(path)
        try:
            return (connection.execute("PRAGMA user_version").fetchone()[0],
                    dict(connection.execute("SELECT key, value FROM runtime_metadata")))
        finally:
            connection.close()

    def test_schema19_pre_governance_fixture_migrates_and_adopts_existing_g001(self):
        root, path = self._schema19_fixture()
        version, metadata = self._schema_version(path)
        self.assertEqual(version, 19)
        self.assertEqual(metadata["schema_version"], "19")
        connection = sqlite3.connect(path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('governance_authority', 'governance_decisions')").fetchone()[0], 0)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM installation_operator_binding").fetchone()[0], 1)
        connection.close()

        database = RuntimeDatabase(root, path=path)
        operators = InstallationOperatorService(database, lambda: self.identity)
        context = operators.context()
        operators.adopt_governance_capabilities(context)
        capabilities = tuple(row["capability"] for row in database._connection.execute(
            "SELECT capability FROM governance_authority ORDER BY capability"
        ))
        self.assertEqual(capabilities, ("ARCHITECTURE_APPROVAL", "BUSINESS_APPROVAL", "SECURITY_APPROVAL"))
        repository = CanonicalGovernanceRepository._for_test(database, operators)
        planning = GovernanceAuthorityTests.planning("legacy-19")
        CanonicalBusinessWorkspace(repository, context).approve(
            decision_id="legacy-business", candidate_id="legacy-candidate", revision="legacy-19",
            scope=planning.scope, gates=("business",),
        )
        CanonicalArchitectureWorkspace(repository, context).approve(
            decision_id="legacy-architecture", candidate_id="legacy-candidate", revision="legacy-19",
            planning=planning,
        )
        envelope = MissionPlanningEvidenceEnvelope.compose(
            repository, subject_id="legacy-candidate", subject_revision="legacy-19",
            business_decision_id="legacy-business", architecture_decision_id="legacy-architecture", planning=planning,
        )
        self.assertEqual(MissionIntake(None, lambda: "now").validate_approved_evidence(envelope, repository), envelope)
        self.assertEqual(self._schema_version(path)[0], 21)
        database.close()

    def test_schema19_partial_governance_fixture_recovers_without_manual_repair(self):
        root, path = self._schema19_fixture(partial=True)
        version, metadata = self._schema_version(path)
        self.assertEqual((version, metadata["schema_version"]), (19, "19"))
        connection = sqlite3.connect(path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='governance_capability_grants'").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('governance_authority', 'governance_decisions')").fetchone()[0], 0)
        connection.close()

        database = RuntimeDatabase(root, path=path)
        database.validate_integrity()
        self.assertEqual(self._schema_version(path)[0], 21)
        database.close()

        reopened = RuntimeDatabase(root, path=path)
        self.assertEqual(reopened.metadata["schema_version"], "21")
        reopened.close()

    def test_schema19_migration_rejects_incompatible_partial_table_without_advancing_metadata(self):
        root, path = self._schema19_fixture(partial=True)
        connection = sqlite3.connect(path)
        connection.execute("DROP TABLE governance_capability_grants")
        connection.execute("CREATE TABLE governance_capability_grants (grant_id TEXT PRIMARY KEY, malformed TEXT NOT NULL)")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(Exception, "incompatible governance_capability_grants table"):
            RuntimeDatabase(root, path=path)
        version, metadata = self._schema_version(path)
        self.assertEqual((version, metadata["schema_version"], metadata["migration_version"]), (19, "19", "19"))
        connection = sqlite3.connect(path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name IN ('governance_authority', 'governance_decisions')").fetchone()[0], 0)
        connection.close()

    def test_schema19_migration_rejects_conflicting_preexisting_authority_during_adoption(self):
        root, path = self._schema19_fixture()
        connection = sqlite3.connect(path)
        installation_id = connection.execute("SELECT installation_id FROM installation_operator_binding").fetchone()[0]
        operator_id = sha256(self.identity.generated_uid.encode()).hexdigest()[:16]
        connection.execute("CREATE TABLE governance_authority (installation_id TEXT NOT NULL, operator_id TEXT NOT NULL, capability TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (installation_id, operator_id, capability))")
        connection.execute("INSERT INTO governance_authority VALUES (?, ?, 'BUSINESS_APPROVAL', 1, 'now')", (installation_id, operator_id))
        connection.commit()
        connection.close()
        database = RuntimeDatabase(root, path=path)
        operators = InstallationOperatorService(database, lambda: self.identity)
        with self.assertRaises(PermissionError):
            operators.adopt_governance_capabilities(operators.context())
        database.close()

    def test_schema19_migration_accepts_correct_preexisting_guard_trigger(self):
        root, path = self._schema19_fixture(partial=True)
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE governance_authority (installation_id TEXT NOT NULL, operator_id TEXT NOT NULL, capability TEXT NOT NULL, version INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY (installation_id, operator_id, capability))")
        connection.execute("CREATE TABLE governance_decisions (decision_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL, subject_id TEXT NOT NULL, subject_revision TEXT NOT NULL, capability TEXT NOT NULL, predecessor_digest TEXT, document TEXT NOT NULL, digest TEXT NOT NULL UNIQUE, occurred_at TEXT NOT NULL, UNIQUE(installation_id, subject_id, subject_revision, capability))")
        connection.execute("CREATE TRIGGER governance_authority_authorized_insert BEFORE INSERT ON governance_authority WHEN forge_governance_write_permitted() != 1 BEGIN SELECT RAISE(ABORT, 'canonical governance repository required'); END")
        connection.commit()
        connection.close()
        database = RuntimeDatabase(root, path=path)
        self.assertEqual(database.metadata["schema_version"], "21")
        database.close()

    def test_schema19_migration_requires_existing_g001_binding_for_adoption(self):
        root, path = self._schema19_fixture(bind=False)
        database = RuntimeDatabase(root, path=path)
        operators = InstallationOperatorService(database, lambda: self.identity)
        with self.assertRaises(PermissionError):
            operators.context()
        database.close()


if __name__ == "__main__":
    unittest.main()
