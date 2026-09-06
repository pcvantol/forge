from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from forge.action_derivation_qualification import CanonicalActionDerivationQualificationService
from forge.governance_authority import CanonicalGovernanceRepository
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime import RuntimeDatabase


class ActionDerivationQualificationTests(unittest.TestCase):
    def test_validated_successor_requires_and_records_security_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            db = RuntimeDatabase(Path(directory), forge_version="test")
            try:
                operators = InstallationOperatorService(db, lambda: NamedOperatorIdentity("00000000-0000-0000-0000-000000000001", 1))
                context = operators.first_bind(); repository = CanonicalGovernanceRepository._for_test(db, operators)
                digest = lambda char: "sha256:" + char * 64
                db.save_mission_state({"mission_id":"mission","status":"APPROVED_PLANNABLE","progress":{},"resume":{},"execution_policy":{}})
                predecessor={"derivation_id":"failed","mission_id":"mission","snapshot_digest":digest("a"),"contract_version":"1.0","provider_configuration":digest("b"),"lifecycle":"FAILED","generation_request_digest":digest("c"),"evidence_digest":digest("d"),"effective_contract_digest":digest("e"),"main_head":"f"*40}
                db.save_action_derivation(predecessor)
                auth={"authorization_id":"auth","successor_attempt_id":"successor","mission_id":"mission","predecessor_attempt_id":"failed","predecessor_terminal_state":"FAILED","attempt_sequence":2,"planning_snapshot_digest":digest("a"),"effective_contract_digest":digest("e"),"evidence_digest":digest("d"),"g011_policy_digest":digest("b"),"provider_request_digest":digest("0"),"main_head":"f"*40,"reattempt_reason":"REQUEST_SEMANTICS_CHANGED","rationale":"changed request","authorization_identity":sha256(context.generated_uid.encode()).hexdigest()[:16],"installation_id":context.installation_id,"created_at":"2026-09-06T00:00:00Z"}
                auth["digest"]="sha256:"+sha256(json.dumps(auth,sort_keys=True,separators=(",",":")).encode()).hexdigest(); db.create_action_derivation_reattempt_authorization(auth)
                successor={"derivation_id":"successor","mission_id":"mission","snapshot_digest":digest("a"),"contract_version":"1.0","provider_configuration":digest("b"),"lifecycle":"VALIDATED","generation_request_digest":digest("0"),"evidence_digest":digest("d"),"effective_contract_digest":digest("e"),"validation_digest":digest("1"),"validation_result":"PASS","provider_output_untrusted":True,"runtime_action_executed":False,"action_materialized":False,"predecessor_attempt_id":"failed","authorization_id":"auth","preflight_receipt_id":"receipt"}
                db.save_action_derivation(successor)
                receipt={"receipt_id":"receipt","mission_id":"mission","main_head":"f"*40,"policy_digest":digest("b"),"request_digest":digest("0"),"evidence_digest":digest("d"),"effective_contract_digest":digest("e"),"provider_id":"provider","input_tokens":1,"input_token_bound":2,"context_token_bound":3,"output_token_bound":2,"context_with_requested_output":3,"result":"PASS","created_at":"2026-09-06T00:00:00Z"}
                db.create_token_preflight_receipt(receipt); db.consume_token_preflight_receipt("receipt",{key:receipt[key] for key in ("main_head","policy_digest","request_digest","evidence_digest","effective_contract_digest")})
                db.consume_action_derivation_reattempt_authorization("auth", {"successor_attempt_id":"successor", "mission_id":"mission", "predecessor_attempt_id":"failed", "planning_snapshot_digest":digest("a"), "effective_contract_digest":digest("e"), "evidence_digest":digest("d"), "g011_policy_digest":digest("b"), "provider_request_digest":digest("0"), "main_head":"f"*40})
                result=CanonicalActionDerivationQualificationService(repository).qualify(mission_id="mission",successor_attempt_id="successor",operator_context=context,decision_id="decision")
                self.assertTrue(result.startswith("sha256:")); self.assertEqual(repository.decision("decision")["capability"],"SECURITY_APPROVAL")
            finally: db.close()
