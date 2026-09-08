import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from forge.governance_authority import CanonicalGovernanceRepository
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.programme_authorization import CandidateQualification, ProgrammeAuthorization, ProgrammeAuthorizationGate
from forge.runtime.database import RuntimeDatabase


class ProgrammeAuthorizationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name)
        self.db = RuntimeDatabase(root, path=root / "runtime.db")
        self.ops = InstallationOperatorService(self.db, lambda: NamedOperatorIdentity("operator-a", 501))
        self.context = self.ops.first_bind()
        self.repository = CanonicalGovernanceRepository._for_test(self.db, self.ops)
        self.gate = ProgrammeAuthorizationGate(self.repository, self.context,
                                               now=lambda: datetime(2026, 9, 7, tzinfo=timezone.utc))
        self.authorization = ProgrammeAuthorization(
            "owner-programme-1", "AUTONOMY_BOOTSTRAP_CLEAN_EP_AND_FIRST_DELIVERY_LOOP",
            "pcvantol", "github:pcvantol:19624891", "owner-task:verified-2026-09-07",
            ("pcvantol/engineering-platform",), ("ep-installation", "governance"),
            "2026-10-01T00:00:00Z")

    def tearDown(self): self.db.close(); self.temp.cleanup()

    def candidate(self, **changes):
        value = dict(repository="pcvantol/engineering-platform", pull_request=77,
                     head_sha="a" * 40, base_branch="main", changed_scopes=("governance",),
                     technical_qualification_passed=True, ci_passed=True, reviews_passed=True,
                     security_passed=True, owner_workflow_evidence="github-run:123",
                     owner_workflow_head_sha="a" * 40, mission_id="mission-1", action_id="action-1")
        value.update(changes)
        if "head_sha" in changes and "owner_workflow_head_sha" not in changes:
            value["owner_workflow_head_sha"] = changes["head_sha"]
        return CandidateQualification(**value)

    def test_persists_owner_grant_and_exact_head_qualification_through_canonical_writer(self):
        digest = self.gate.record_authorization(self.authorization)
        qualified = self.gate.qualify(self.authorization.authorization_id, self.candidate())
        self.assertTrue(digest.startswith("sha256:")); self.assertTrue(qualified.startswith("sha256:"))
        stored = self.repository.decision(self.authorization.authorization_id)
        self.assertEqual(stored["evidence"]["source_reference"], "owner-task:verified-2026-09-07")

    def test_fails_closed_for_scope_expansion_or_missing_real_gates(self):
        self.gate.record_authorization(self.authorization)
        with self.assertRaises(PermissionError): self.gate.qualify(self.authorization.authorization_id, self.candidate(changed_scopes=("outside",)))
        with self.assertRaises(PermissionError): self.gate.qualify(self.authorization.authorization_id, self.candidate(security_passed=False))

    def test_repair_is_limited_across_the_action_lineage_even_when_the_head_changes(self):
        self.gate.record_authorization(self.authorization)
        candidate = self.candidate(technical_qualification_passed=False, ci_passed=False)
        for _ in range(3): self.gate.record_repair_attempt(self.authorization.authorization_id, candidate)
        with self.assertRaises(PermissionError): self.gate.record_repair_attempt(self.authorization.authorization_id, candidate)
        with self.assertRaises(PermissionError):
            self.gate.record_repair_attempt(self.authorization.authorization_id, self.candidate(head_sha="b" * 40, technical_qualification_passed=False, ci_passed=False))

    def test_repair_permission_requires_action_lineage_and_is_not_merge_qualification(self):
        self.gate.record_authorization(self.authorization)
        candidate = self.candidate(technical_qualification_passed=False, ci_passed=False)
        self.assertTrue(self.gate.record_repair_attempt(self.authorization.authorization_id, candidate).startswith("sha256:"))
        with self.assertRaises(PermissionError):
            self.gate.qualify(self.authorization.authorization_id, candidate)
        with self.assertRaises(PermissionError):
            self.gate.record_repair_attempt(self.authorization.authorization_id, self.candidate(mission_id=None))
