import json
from hashlib import sha256
import tempfile
import unittest
from pathlib import Path

from forge.action_derivation_evidence import ActionDerivationEvidenceError, CanonicalActionDerivationEvidenceProducer
from forge.governance_authority import (ArchitecturePlanningEvidence, CanonicalArchitectureWorkspace,
    CanonicalBusinessWorkspace, CanonicalGovernanceRepository)
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.mission_recommendation import RequiredDiscipline
from forge.models.action_derivation import PlanningSnapshot
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.planner import (CanonicalTokenPreflightAuthority, OpenAIPlanningProviderConfiguration,
                           OpenAIResponsesPlanningProvider, ProviderDerivationRequest, TokenPreflightBoundary)
from forge.provider_security import (PlanningProviderSecurityService, SecretReference, SecretState)
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

    def test_canonical_validation_records_only_a_bound_immutable_failure(self):
        self._state()
        producer = CanonicalActionDerivationEvidenceProducer(self.db, self.repository)
        evidence = producer.produce("mission")
        snapshot = PlanningSnapshot.from_planner_input(producer.planner_input("mission"))
        contract = self.db.get_document("mission_state", "mission")["admission_contract"]
        effective_digest = "sha256:" + sha256(json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

        class Resolver:
            def status(self, reference): return SecretState.RESOLVABLE
            def resolve(self, reference): return SecretState.RESOLVABLE, "fixture-secret"
        class Response:
            def __init__(self, body): self.body = body
            def read(self): return json.dumps(self.body).encode()
            def __enter__(self): return self
            def __exit__(self, *_): return None
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            if request.full_url.endswith("/input_tokens"):
                return Response({"input_tokens": 1})
            return Response({"id": "resp_fixture", "status": "completed", "output": [{"content": [{"text": json.dumps({
                "kind": "proposals", "proposals": [{
                    "logical_action_id": "outside", "scope": "outside-approved-mission", "objective": "untrusted",
                    "dependencies": [], "write_scopes": [], "expected_evidence": ["e"],
                    "validation_strategy": ["v"], "priority": 1, "postponed": False,
                    "human_gates": ["human gate"], "risk_inputs": ["untrusted provider"],
                    "source_evidence_refs": ["mission_state"],
                }],
            })}]}]})
        resolver = Resolver()
        service = PlanningProviderSecurityService(self.db, resolver, self.operators)
        service.configure(configuration_id="config", provider_id="openai-planning",
                          reference=SecretReference("keychain", "//forge.openai/planning"),
                          operator_context=self.operators.context(), model="gpt-5.6", timeout_seconds=120,
                          input_token_bound=64000, context_token_bound=128000, output_token_bound=16000)
        adapter = OpenAIResponsesPlanningProvider(
            OpenAIPlanningProviderConfiguration._for_test(
                service, "openai-planning", CanonicalTokenPreflightAuthority._for_test(
                    self.db, lambda _: TokenPreflightBoundary("a" * 40, evidence["digest"], effective_digest),
                    lambda _: ("planning-only",),
                    lambda _: (("NONE",), ("human gate",), ("untrusted provider",)),
                ),
            ),
            resolver, opener=opener,
        )
        request = ProviderDerivationRequest("derivation-failure", snapshot, "openai-planning", "gpt-5.6")
        receipt = adapter.preflight(request, operator_context=self.operators.context())
        recorded = adapter.invoke_and_validate(request, receipt_id=receipt["receipt_id"],
                                               governance_repository=self.repository)
        self.assertEqual(recorded["lifecycle"], "FAILED")
        self.assertEqual(recorded["validation_failure_code"], "SCOPE_OUTSIDE_MISSION")
        self.assertEqual(recorded["generation_request_digest"], receipt["request_digest"])
        self.assertEqual(recorded["preflight_receipt_id"], receipt["receipt_id"])
        self.assertEqual(recorded["main_head"], "a" * 40)
        self.assertNotIn("outside-approved-mission", json.dumps(recorded))
        self.assertEqual(calls, ["https://api.openai.com/v1/responses/input_tokens", "https://api.openai.com/v1/responses"])
        with self.assertRaises(Exception):
            self.db._connection.execute("UPDATE action_derivations SET lifecycle='MATERIALIZED' WHERE derivation_id='derivation-failure'")

    def test_canonical_validation_records_a_bound_non_materializing_success(self):
        self._state()
        producer = CanonicalActionDerivationEvidenceProducer(self.db, self.repository)
        evidence = producer.produce("mission")
        snapshot = PlanningSnapshot.from_planner_input(producer.planner_input("mission"))
        contract = self.db.get_document("mission_state", "mission")["admission_contract"]
        effective_digest = "sha256:" + sha256(json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

        class Resolver:
            def status(self, reference): return SecretState.RESOLVABLE
            def resolve(self, reference): return SecretState.RESOLVABLE, "fixture-secret"
        class Response:
            def __init__(self, body): self.body = body
            def read(self): return json.dumps(self.body).encode()
            def __enter__(self): return self
            def __exit__(self, *_): return None
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            if request.full_url.endswith("/input_tokens"):
                return Response({"input_tokens": 1})
            return Response({"id": "resp_fixture", "status": "completed", "output": [{"content": [{"text": json.dumps({
                "kind": "proposals", "proposals": [{
                    "logical_action_id": "planning", "scope": "planning-only", "objective": "untrusted",
                    "dependencies": [], "write_scopes": [], "expected_evidence": ["e"],
                    "validation_strategy": ["v"], "priority": 1, "postponed": False,
                    "human_gates": ["human gate"], "risk_inputs": ["untrusted provider"],
                    "source_evidence_refs": ["mission_state"],
                }],
            })}]}]})
        resolver = Resolver()
        service = PlanningProviderSecurityService(self.db, resolver, self.operators)
        service.configure(configuration_id="config", provider_id="openai-planning",
                          reference=SecretReference("keychain", "//forge.openai/planning"),
                          operator_context=self.operators.context(), model="gpt-5.6", timeout_seconds=120,
                          input_token_bound=64000, context_token_bound=128000, output_token_bound=16000)
        adapter = OpenAIResponsesPlanningProvider(
            OpenAIPlanningProviderConfiguration._for_test(
                service, "openai-planning", CanonicalTokenPreflightAuthority._for_test(
                    self.db, lambda _: TokenPreflightBoundary("a" * 40, evidence["digest"], effective_digest),
                    lambda _: ("planning-only",),
                    lambda _: (("NONE",), ("human gate",), ("untrusted provider",)),
                ),
            ), resolver, opener=opener,
        )
        request = ProviderDerivationRequest("derivation-success", snapshot, "openai-planning", "gpt-5.6")
        receipt = adapter.preflight(request, operator_context=self.operators.context())
        validated = adapter.invoke_and_validate(request, receipt_id=receipt["receipt_id"],
                                                governance_repository=self.repository)
        record = self.db.get_document("action_derivations", "derivation-success")
        self.assertEqual(validated.status.value, "PASS")
        self.assertEqual(record["lifecycle"], "VALIDATED")
        self.assertEqual(record["validation_result"], "PASS")
        self.assertEqual(record["generation_request_digest"], receipt["request_digest"])
        self.assertEqual(record["preflight_receipt_id"], receipt["receipt_id"])
        self.assertEqual(record["main_head"], "a" * 40)
        self.assertTrue(record["provider_output_untrusted"])
        self.assertFalse(record["runtime_action_executed"])
        self.assertFalse(record["action_materialized"])
        self.assertNotIn("planning-only", json.dumps(record))
        with self.assertRaisesRegex(Exception, "validation bindings"):
            self.db.save_action_derivation({**record, "lifecycle": "MATERIALIZED",
                                             "generation_request_digest": "sha256:" + "b" * 64})
        retry_request = ProviderDerivationRequest("derivation-success-retry", snapshot, "openai-planning", "gpt-5.6")
        retry_receipt = adapter.preflight(retry_request, operator_context=self.operators.context())
        with self.assertRaisesRegex(PermissionError, "already resolved"):
            adapter.invoke_and_validate(retry_request, receipt_id=retry_receipt["receipt_id"],
                                        governance_repository=self.repository)
        self.assertEqual(calls, ["https://api.openai.com/v1/responses/input_tokens",
                                 "https://api.openai.com/v1/responses",
                                 "https://api.openai.com/v1/responses/input_tokens"])
