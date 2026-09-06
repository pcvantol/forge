from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from forge.action_derivation_canary_closure import CanonicalActionDerivationCanaryClosureService
from forge.action_derivation_qualification import CanonicalActionDerivationQualificationService
from forge.governance_authority import CanonicalGovernanceRepository
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime import RuntimeDatabase, RuntimeDatabaseError, RuntimeIntegrityError


class ActionDerivationCanaryClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.db = RuntimeDatabase(Path(self.directory.name), forge_version="test")
        self.operators = InstallationOperatorService(
            self.db, lambda: NamedOperatorIdentity("00000000-0000-0000-0000-000000000001", 1)
        )
        self.context = self.operators.first_bind()
        self.repository = CanonicalGovernanceRepository._for_test(self.db, self.operators)
        self.digest = lambda letter: "sha256:" + letter * 64
        self._seed_validated_successor()

    def tearDown(self) -> None:
        self.db.close()
        self.directory.cleanup()

    def _seed_validated_successor(self) -> None:
        self.db.save_mission_state({"mission_id": "mission", "status": "APPROVED_PLANNABLE", "progress": {}, "resume": {}, "execution_policy": {}, "admission_contract": {"write_scope": "NONE"}})
        self.predecessor = {"derivation_id": "failed", "mission_id": "mission", "snapshot_digest": self.digest("a"), "contract_version": "1.0", "provider_configuration": self.digest("b"), "lifecycle": "FAILED", "generation_request_digest": self.digest("c"), "evidence_digest": self.digest("d"), "effective_contract_digest": self.digest("e"), "main_head": "f" * 40}
        self.db.save_action_derivation(self.predecessor)
        self.authorization = {"authorization_id": "auth", "successor_attempt_id": "successor", "mission_id": "mission", "predecessor_attempt_id": "failed", "predecessor_terminal_state": "FAILED", "attempt_sequence": 2, "planning_snapshot_digest": self.digest("a"), "effective_contract_digest": self.digest("e"), "evidence_digest": self.digest("d"), "g011_policy_digest": self.digest("b"), "provider_request_digest": self.digest("0"), "main_head": "f" * 40, "reattempt_reason": "REQUEST_SEMANTICS_CHANGED", "rationale": "bounded request changed", "authorization_identity": sha256(self.context.generated_uid.encode()).hexdigest()[:16], "installation_id": self.context.installation_id, "created_at": "2026-09-06T00:00:00Z"}
        self.authorization["digest"] = "sha256:" + sha256(json.dumps(self.authorization, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.db.create_action_derivation_reattempt_authorization(self.authorization)
        self.successor = {"derivation_id": "successor", "mission_id": "mission", "snapshot_digest": self.digest("a"), "contract_version": "1.0", "provider_configuration": self.digest("b"), "lifecycle": "VALIDATED", "generation_request_digest": self.digest("0"), "evidence_digest": self.digest("d"), "effective_contract_digest": self.digest("e"), "validation_digest": self.digest("1"), "validation_result": "PASS", "provider_output_untrusted": True, "runtime_action_executed": False, "action_materialized": False, "engineering_side_effects": 0, "predecessor_attempt_id": "failed", "authorization_id": "auth", "preflight_receipt_id": "receipt", "main_head": "f" * 40}
        self.db.save_action_derivation(self.successor)
        self.receipt = {"receipt_id": "receipt", "mission_id": "mission", "main_head": "f" * 40, "policy_digest": self.digest("b"), "request_digest": self.digest("0"), "evidence_digest": self.digest("d"), "effective_contract_digest": self.digest("e"), "provider_id": "provider", "input_tokens": 1, "input_token_bound": 2, "context_token_bound": 3, "output_token_bound": 2, "context_with_requested_output": 3, "result": "PASS", "created_at": "2026-09-06T00:00:00Z"}
        self.db.create_token_preflight_receipt(self.receipt)
        self.db.consume_token_preflight_receipt("receipt", {key: self.receipt[key] for key in ("main_head", "policy_digest", "request_digest", "evidence_digest", "effective_contract_digest")})
        self.db.consume_action_derivation_reattempt_authorization("auth", {"successor_attempt_id": "successor", "mission_id": "mission", "predecessor_attempt_id": "failed", "planning_snapshot_digest": self.digest("a"), "effective_contract_digest": self.digest("e"), "evidence_digest": self.digest("d"), "g011_policy_digest": self.digest("b"), "provider_request_digest": self.digest("0"), "main_head": "f" * 40})
        self.qualification_id = "qualification"
        CanonicalActionDerivationQualificationService(self.repository).qualify(mission_id="mission", successor_attempt_id="successor", operator_context=self.context, decision_id=self.qualification_id)

    def _service(self) -> CanonicalActionDerivationCanaryClosureService:
        return CanonicalActionDerivationCanaryClosureService(self.repository)

    def _close(self) -> dict[str, object]:
        return self._service().close(mission_id="mission", successor_attempt_id="successor", qualification_decision_id=self.qualification_id, operator_context=self.context)

    def _closure_document(self) -> dict[str, object]:
        with patch.object(self.db, "create_action_derivation_canary_closure", side_effect=lambda value: value) as writer:
            self._close()
        return writer.call_args.args[0]

    def test_closure_is_immutable_idempotent_and_survives_reopen(self) -> None:
        closure = self._close()
        self.assertEqual(closure["qualified_capability"], "ACTION_DERIVATION")
        self.assertEqual(closure["not_qualified_capabilities"], ["ACTION_MATERIALIZATION", "AUTONOMOUS_NEXT_MISSION_LOOP", "EP_DISPATCH", "EP_RESULT_OBSERVATION", "EXECUTION_ADMISSION"])
        self.assertEqual(self.db.get_document("mission_state", "mission")["status"], "APPROVED_PLANNABLE")
        self.assertEqual(self._close(), closure)
        self.assertEqual(self.db._connection.execute("SELECT COUNT(*) FROM action_derivation_canary_closures WHERE successor_attempt_id='successor'").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db._connection.execute("UPDATE action_derivation_canary_closures SET main_head='0' WHERE closure_id=?", (closure["closure_id"],))
        self.db._connection.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db._connection.execute("DELETE FROM action_derivation_canary_closures WHERE closure_id=?", (closure["closure_id"],))
        self.db._connection.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db._connection.execute(
                "INSERT INTO action_derivation_canary_closures SELECT "
                "'forged', mission_id, successor_attempt_id, predecessor_attempt_id, qualification_decision_id, "
                "qualification_decision_digest, effective_contract_digest, evidence_digest, g011_policy_digest, "
                "provider_request_digest, preflight_receipt_id, reattempt_authorization_id, main_head, "
                "qualified_capability, not_qualified_capabilities, installation_id, operator_id, runtime_id, "
                "closed_at, digest, document FROM action_derivation_canary_closures WHERE closure_id=?",
                (closure["closure_id"],),
            )
        self.db._connection.rollback()
        path = self.db.path
        self.db.close()
        self.db = RuntimeDatabase(Path(self.directory.name), path=path, forge_version="test")
        self.assertEqual(self.db.get_document("action_derivation_canary_closures", closure["closure_id"]), closure)

    def test_negative_preconditions_fail_closed(self) -> None:
        original = self.db.get_document

        def modified(table: str, identifier: str, changes: dict[str, object]):
            def get_document(name: str, key: str):
                value = original(name, key)
                return {**value, **changes} if (name, key) == (table, identifier) else value
            return get_document

        cases = (
            ("failed_successor", "action_derivations", "successor", {"lifecycle": "FAILED"}),
            ("nonterminal_successor", "action_derivations", "successor", {"lifecycle": "PROVIDER_RUNNING"}),
            ("mission_mismatch", "action_derivations", "successor", {"mission_id": "other"}),
            ("executed", "action_derivations", "successor", {"runtime_action_executed": True}),
            ("materialized", "action_derivations", "successor", {"action_materialized": True}),
            ("side_effects", "action_derivations", "successor", {"engineering_side_effects": 1}),
            ("contract_mismatch", "action_derivation_reattempt_authorizations", "auth", {"effective_contract_digest": self.digest("9")}),
            ("evidence_mismatch", "action_derivation_reattempt_authorizations", "auth", {"evidence_digest": self.digest("9")}),
            ("policy_mismatch", "action_derivation_reattempt_authorizations", "auth", {"g011_policy_digest": self.digest("9")}),
            ("request_mismatch", "action_derivation_reattempt_authorizations", "auth", {"provider_request_digest": self.digest("9")}),
        )
        for label, table, identifier, changes in cases:
            with self.subTest(label), patch.object(self.db, "get_document", side_effect=modified(table, identifier, changes)):
                with self.assertRaises(PermissionError):
                    self._close()
        with self.assertRaises(RuntimeDatabaseError):
            self._service().close(mission_id="mission", successor_attempt_id="missing", qualification_decision_id=self.qualification_id, operator_context=self.context)
        with self.assertRaises(PermissionError):
            self._service().close(mission_id="mission", successor_attempt_id="successor", qualification_decision_id="missing", operator_context=self.context)
        with patch.object(self.db, "consumed_token_preflight_receipt", side_effect=RuntimeIntegrityError("missing")):
            with self.assertRaises(RuntimeIntegrityError):
                self._close()

    def test_direct_canonical_writer_rejects_unresolved_security_and_secret_identifiers(self) -> None:
        document = self._closure_document()
        def revised(**changes):
            value = {**document, **changes}
            value["digest"] = "sha256:" + sha256(json.dumps(
                {key: item for key, item in value.items() if key != "digest"}, sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest()
            return value
        for changes in (
            {"qualification_decision_id": "missing"},
            {"reattempt_authorization_id": "missing"},
            {"reattempt_authorization_id": "sk-proj-test-marker-not-a-real-secret"},
            {"effective_contract_digest": self.digest("9")},
        ):
            with self.subTest(changes=changes), self.assertRaises(RuntimeDatabaseError):
                self.db.create_action_derivation_canary_closure(revised(**changes))
        self.assertEqual(self.db.create_action_derivation_canary_closure(document), document)
        decision = self.repository.decision(self.qualification_id)
        with patch.object(self.repository, "decision", return_value={**decision, "decision": "denied"}):
            with self.assertRaises(PermissionError):
                self._close()
        with patch.object(self.repository, "decision", return_value={**decision, "predecessor_digest": self.digest("9")}):
            with self.assertRaises(PermissionError):
                self._close()

    def test_schema30_migrates_the_bounded_closure_store_before_reopen(self) -> None:
        self.db.close()
        connection = sqlite3.connect(self.db.path)
        for trigger in (
            "action_derivation_canary_closures_authorized_insert",
            "action_derivation_canary_closures_immutable_update",
            "action_derivation_canary_closures_immutable_delete",
        ):
            connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute("DROP TABLE action_derivation_canary_closures")
        connection.execute("UPDATE runtime_metadata SET value='30' WHERE key IN ('schema_version', 'migration_version', 'last_migration')")
        connection.execute("PRAGMA user_version=30")
        connection.commit()
        connection.close()
        self.db = RuntimeDatabase(Path(self.directory.name), forge_version="test")
        self.assertEqual(self.db.metadata["schema_version"], "31")
        tables = {row["name"] for row in self.db._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        triggers = {row["name"] for row in self.db._connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertIn("action_derivation_canary_closures", tables)
        self.assertTrue({
            "action_derivation_canary_closures_authorized_insert",
            "action_derivation_canary_closures_immutable_update",
            "action_derivation_canary_closures_immutable_delete",
        } <= triggers)
