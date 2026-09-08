"""Focused unit coverage for small governed application services."""
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from forge.action_derivation_reattempt import CanonicalActionDerivationReattemptService, REQUEST_SEMANTICS_CHANGED
from forge.mission_amendment import MissionAmendmentService, _digest
from forge.models.action_derivation import PlanningSnapshot
from forge.operator_identity import OperatorContext
from forge.planner.openai_responses import CanonicalTokenPreflightAuthority, TokenPreflightBoundary, _G011PolicySnapshot


class _Cursor:
    def __init__(self, one=None, rows=()): self.one, self.rows = one, rows
    def fetchone(self): return self.one
    def fetchall(self): return self.rows


class _Connection:
    def __init__(self, cursors=()): self.cursors = list(cursors)
    def execute(self, *_args): return self.cursors.pop(0)


class GovernedServiceCoverageTests(unittest.TestCase):
    def test_successor_authorization_binds_only_a_changed_failed_request(self) -> None:
        context = OperatorContext("installation", "operator", 1)
        policy = SimpleNamespace(provider_id="openai", version=1, model="model", secret_reference=SimpleNamespace(fingerprint="secret"),
            timeout_seconds=1, input_token_bound=2, context_token_bound=3, output_token_bound=4)
        predecessor = {"lifecycle": "FAILED", "mission_id": "mission", "snapshot_digest": "snapshot",
            "effective_contract_digest": "contract", "evidence_digest": "evidence", "provider_configuration": _G011PolicySnapshot.from_policy(policy).digest,
            "generation_request_digest": "old-request", "main_head": "head"}
        database = SimpleNamespace(get_document=lambda table, key: predecessor if table == "action_derivations" else {"status": "APPROVED_PLANNABLE"},
            _connection=_Connection([_Cursor({"sequence": None})]),
            create_action_derivation_reattempt_authorization=lambda document: document)
        repository = SimpleNamespace(database=database, operators=SimpleNamespace(authorize=lambda value: value == context),
            _operator_id=lambda value: "operator-id")
        adapter = SimpleNamespace(configuration=SimpleNamespace(policy_service=SimpleNamespace(db=database), current_policy=lambda: policy,
            preflight_authority=SimpleNamespace(boundary_for=lambda _: TokenPreflightBoundary("head", "evidence", "contract"))),
            _body=lambda request, _: {"new": request.derivation_id})
        snapshot = SimpleNamespace(digest="snapshot")
        with patch("forge.action_derivation_reattempt.CanonicalActionDerivationEvidenceProducer", return_value=SimpleNamespace(planner_input=lambda _: object())), \
             patch.object(PlanningSnapshot, "from_planner_input", return_value=snapshot):
            record = CanonicalActionDerivationReattemptService(adapter, repository).authorize_successor(
                predecessor_attempt_id="failed", operator_context=context, rationale="bounded changed request")
        self.assertEqual(record["predecessor_attempt_id"], "failed")
        self.assertEqual(record["attempt_sequence"], 2)
        self.assertNotEqual(record["provider_request_digest"], "old-request")
        self.assertEqual(record["reattempt_reason"], REQUEST_SEMANTICS_CHANGED)

    def test_successor_rejects_unsupported_reason_and_untrusted_operator(self) -> None:
        database = SimpleNamespace()
        repository = SimpleNamespace(database=database, operators=SimpleNamespace(authorize=lambda _: False))
        adapter = SimpleNamespace(configuration=SimpleNamespace(policy_service=SimpleNamespace(db=database)))
        service = CanonicalActionDerivationReattemptService(adapter, repository)
        with self.assertRaises(PermissionError):
            service.authorize_successor(predecessor_attempt_id="x", operator_context=OperatorContext("i", "u", 1), rationale="ok", reason="OTHER")
        with self.assertRaises(PermissionError):
            service.authorize_successor(predecessor_attempt_id="x", operator_context=OperatorContext("i", "u", 1), rationale="ok")
        with self.assertRaises(ValueError):
            service.authorize_successor(predecessor_attempt_id="x", operator_context=OperatorContext("i", "u", 1), rationale=" ")

    def test_mission_amendment_applies_append_only_constraint_and_rejects_stale_lineage(self) -> None:
        contract = {"mission": {"engineering_constraints": ["WRITE_SCOPE=NONE"]}}
        predecessor = _digest(contract)
        amendment = {"predecessor_digest": predecessor, "changed_fields": {"engineering_constraints_add": ["NO_REPOSITORY_TARGET=TRUE"]},
            "effective_contract_digest": "sha256:" + "a" * 64}
        database = SimpleNamespace(get_document=lambda *_: {"status": "APPROVED_PLANNABLE", "admission_contract": contract},
            _connection=_Connection([_Cursor(rows=[{"document": __import__("json").dumps(amendment)}])]))
        service = MissionAmendmentService(SimpleNamespace(database=database))
        effective, digest = service.effective_contract("mission")
        self.assertIn("NO_REPOSITORY_TARGET=TRUE", effective["mission"]["engineering_constraints"])
        self.assertEqual(digest, amendment["effective_contract_digest"])
        database._connection = _Connection([_Cursor(rows=[{"document": __import__("json").dumps({**amendment, "predecessor_digest": "wrong"})}])])
        with self.assertRaisesRegex(ValueError, "stale"):
            service.effective_contract("mission")

    def test_mission_amendment_records_canonical_business_and_architecture_decisions(self) -> None:
        context = OperatorContext("installation", "operator", 1)
        contract = {"mission": {"engineering_constraints": ["WRITE_SCOPE=NONE"]}, "installation_id": "installation"}
        database = SimpleNamespace(get_document=lambda *_: {"status": "APPROVED_PLANNABLE", "admission_contract": contract},
            _connection=_Connection([_Cursor(rows=[]), _Cursor([1])]),
            create_mission_amendment=lambda document: document)
        repository = SimpleNamespace(database=database, operators=SimpleNamespace(authorize=lambda value: value == context),
            decision=lambda identifier: {"capability": "BUSINESS_APPROVAL" if identifier == "business" else "ARCHITECTURE_APPROVAL",
                "decision": "approved", "subject_id": "mission"})
        record = MissionAmendmentService(repository).amend_no_repository_target("mission", business_decision_id="business",
            architecture_decision_id="architecture", rationale="no repository delivery", context=context)
        self.assertEqual(record["revision"], 1)
        self.assertEqual(record["changed_fields"], {"engineering_constraints_add": ["NO_REPOSITORY_TARGET=TRUE"]})

    def test_canonical_authority_reads_valid_persisted_scope_and_no_write_policy(self) -> None:
        state = {"status": "APPROVED_PLANNABLE", "admission_contract": {"mission": {"scope": ["scope-b", "scope-a"]},
            "planning": {"write_scopes": ["NONE"], "human_gates": ["review"], "risk_inputs": ["risk"]}}}
        authority = CanonicalTokenPreflightAuthority(SimpleNamespace(get_document=lambda *_: state))
        self.assertEqual(authority.approved_scopes_for("mission"), ("scope-a", "scope-b"))
        self.assertEqual(authority.approved_derivation_policy_for("mission"), (("NONE",), ("review",), ("risk",)))
        with self.assertRaises(ValueError):
            TokenPreflightBoundary("", "evidence", "contract").values(policy_digest="policy", request_digest="request")


if __name__ == "__main__":
    unittest.main()
