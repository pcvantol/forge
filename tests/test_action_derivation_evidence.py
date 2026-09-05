import tempfile
import unittest
from pathlib import Path

from forge.action_derivation_evidence import ActionDerivationEvidenceError, CanonicalActionDerivationEvidenceProducer
from forge.governance_authority import (ArchitecturePlanningEvidence, CanonicalArchitectureWorkspace,
    CanonicalBusinessWorkspace, CanonicalGovernanceRepository)
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.mission_recommendation import RequiredDiscipline
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime.database import RuntimeDatabase


class ActionDerivationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.db = RuntimeDatabase(root, path=root / "runtime.db")
        self.operators = InstallationOperatorService(self.db, lambda: NamedOperatorIdentity("operator", 501))
        self.context = self.operators.first_bind(); self.repository = CanonicalGovernanceRepository._for_test(self.db, self.operators)

    def tearDown(self): self.db.close(); self.temp.cleanup()

    def _state(self, *, no_target=True):
        planning = ArchitecturePlanningEvidence(("planning-only",), ("NONE",), ("no execution",),
            ("untrusted provider",), ("human gate",), ("G001",), 64000, 16000, "r1")
        CanonicalBusinessWorkspace(self.repository, self.context).approve(decision_id="business", candidate_id="candidate", revision="r1", scope=planning.scope, gates=("human gate",))
        CanonicalArchitectureWorkspace(self.repository, self.context).approve(decision_id="architecture", candidate_id="candidate", revision="r1", planning=planning)
        constraints = ("NO_REPOSITORY_TARGET=TRUE", "WRITE_SCOPE=NONE") if no_target else ("WRITE_SCOPE=NONE",)
        mission = ArchitectureMission("mission", "candidate", "planning", "bounded", "objective", "value", "architecture", "business", planning.scope, constraints, ("no execution",), ("no target",), planning.dependencies, ("action-derivation-planning",), (RequiredDiscipline.PLATFORM_ARCHITECTURE,), planning.risk_inputs, ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING)
        contract = {"installation_id": self.context.installation_id, "candidate_id":"candidate", "subject_revision":"r1", "business_decision_id":"business", "architecture_decision_id":"architecture", "planning":planning.to_dict(), "envelope_digest":"sha256:" + "a" * 64, "write_scope":"NONE", "mission":mission.to_dict()}
        self.db.create_mission_state({"mission_id":"mission", "status":"APPROVED_PLANNABLE", "lifecycle":"APPROVED_PLANNABLE", "progress":{}, "resume":{}, "execution_policy":{"write_scope":"NONE"}, "revision":1, "admission_contract":contract})

    def test_produces_one_complete_no_repository_target_evidence_set(self):
        self._state(); producer = CanonicalActionDerivationEvidenceProducer(self.db, self.repository)
        evidence = producer.produce("mission")
        self.assertEqual(evidence["repository_context"]["kind"], "NO_REPOSITORY_TARGET")
        self.assertFalse(evidence["capability_catalogue"]["grants_authority"])
        self.assertEqual(producer.produce("mission"), evidence)
        planner_input = producer.planner_input("mission")
        self.assertTrue(all(scope.allow_provider_derivation for scope in planner_input.approved_scopes))

    def test_missing_explicit_no_repository_target_fails_closed(self):
        self._state(no_target=False)
        with self.assertRaisesRegex(ActionDerivationEvidenceError, "NO_REPOSITORY_TARGET"):
            CanonicalActionDerivationEvidenceProducer(self.db, self.repository).produce("mission")

