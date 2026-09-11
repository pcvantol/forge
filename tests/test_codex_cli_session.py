"""Qualification of the read-only Codex ChatGPT-session provider."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from forge.models import DerivationPolicy, PlanningSnapshot, ProviderSideEffectState
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.planner import (
    AIMissionPlanner, BoundedActionDerivationProvider, CodexCliChatGPTSessionPlanningProvider,
    CodexCliChatGPTSessionPlanningProviderConfiguration, CodexCliSessionReadinessChecker,
    CodexCliInvocationRejected, CodexCliSessionReadinessState, ProviderDerivationRequest,
    ProviderSubmissionAmbiguous,
)
from forge.planner.action_derivation import ActionDerivationValidator, ProposalValidationError
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderSecurityService, ProviderAuthenticationMode,
)
from forge.runtime.database import RuntimeDatabase
from forge.secure_store import SecretState
from tests.test_action_derivation import input_model


class Store:
    def status(self, _reference):
        return SecretState.RESOLVABLE


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def document(*, scope="planner-contract", extra=False):
    result = {"result": {
        "kind": "proposals",
        "proposals": [{
            "logical_action_id": "derive-contract", "scope": scope,
            "objective": "Implement bounded derived planning.", "dependencies": [], "write_scopes": [],
            "expected_evidence": ["unit test"], "validation_strategy": ["unit test"],
            "priority": 1, "postponed": False, "human_gates": ["architecture-review"],
            "risk_inputs": ["scope-drift"], "source_evidence_refs": ["mission_state"],
            "mission_gap": None,
        }],
    }}
    if extra:
        result["result"]["proposals"][0]["untrusted_extra"] = True
    return result


def complete_document():
    result = document()
    second = dict(result["result"]["proposals"][0])
    second.update({"logical_action_id": "derive-docs", "scope": "planner-docs", "dependencies": ["derive-contract"],
                   "expected_evidence": ["documentation test"], "validation_strategy": ["documentation test"]})
    result["result"]["proposals"].append(second)
    return result


class Runner:
    def __init__(self, output=None, *, version="0.153.4", login="Logged in using ChatGPT", exec_error=None,
                 exec_result=None, events=""):
        self.output = output if output is not None else document()
        self.version, self.login, self.exec_error = version, login, exec_error
        self.exec_result, self.events = exec_result or Result(), events
        self.calls = []
        self.schemas = []

    def __call__(self, command, **kwargs):
        self.calls.append((tuple(command), kwargs))
        if "--version" in command:
            return Result(stdout=f"codex-cli {self.version}\n")
        if command[-2:] == ["login", "status"]:
            return Result(0 if "logged in" in self.login.lower() else 1, self.login)
        if self.exec_error:
            raise self.exec_error
        schema_path = Path(command[command.index("--output-schema") + 1])
        self.schemas.append(json.loads(schema_path.read_text(encoding="utf-8")))
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(self.output), encoding="utf-8")
        return Result(self.exec_result.returncode, self.events or self.exec_result.stdout, self.exec_result.stderr)


class CleanupFailureTemporaryDirectory:
    """Deterministically simulates an error after a process has run."""

    def __init__(self, **kwargs):
        self._temporary = tempfile.TemporaryDirectory(**kwargs)
        self.name = self._temporary.name

    def cleanup(self):
        self._temporary.cleanup()
        raise OSError(5, "private cleanup detail")


class CodexCliSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.db = RuntimeDatabase(self.root, path=self.root / "runtime.db")
        self.addCleanup(self.db.close)
        self.operators = InstallationOperatorService(self.db, lambda: NamedOperatorIdentity("codex-session-test", 501))
        self.service = PlanningProviderSecurityService(self.db, Store(), self.operators)
        self.context = self.operators.first_bind()
        self.input = input_model()
        self.snapshot = PlanningSnapshot.from_planner_input(self.input)
        self.policy = DerivationPolicy(("forge/planner",), ("architecture-review",), ("scope-drift",))

    def configure(self, *, model=None, profile=None):
        return self.service.configure(
            configuration_id="codex-config", provider_id="codex-session", operator_context=self.context,
            authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
            provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
            external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
            executable_path="/usr/local/bin/codex", adapter_version="1.0", model=model, profile=profile,
            timeout_seconds=30, input_token_bound=64000, context_token_bound=128000, output_token_bound=16000,
        )

    def provider(self, runner, *, checker=None, temporary_directory=tempfile.TemporaryDirectory):
        configuration = CodexCliChatGPTSessionPlanningProviderConfiguration.from_canonical_session(
            self.service, "codex-session")
        return CodexCliChatGPTSessionPlanningProvider(
            configuration, runner=runner,
            readiness_checker=checker or CodexCliSessionReadinessChecker(runner=runner, path_usable=lambda _path: True),
            temporary_directory=temporary_directory,
        )

    def request(self, *, snapshot=None, model=None):
        return ProviderDerivationRequest("derivation-1", snapshot or self.snapshot, "codex-session", model)

    def invocation_documents(self):
        return [json.loads(row["document"]) for row in self.db._connection.execute(
            "SELECT document FROM planning_provider_external_session_audit WHERE operation='invocation' ORDER BY occurred_at"
        )]

    def test_session_configuration_is_durable_and_carries_no_secret_reference(self):
        result = self.configure(profile="default")
        self.assertEqual(result["authentication_mode"], "EXTERNAL_AUTHENTICATED_SESSION")
        self.assertEqual(result["provider_type"], CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE)
        self.assertNotIn("secret_reference", result)
        policy = self.service.invocation_policy("codex-session")
        self.assertIsNone(policy.secret_reference)
        self.assertEqual(policy.profile, "default")
        persisted = " ".join(str(tuple(row)) for row in self.db._connection.execute(
            "SELECT * FROM planning_provider_external_session_config"
        ))
        self.assertNotIn("synthetic-auth-secret", persisted)
        self.db.close()
        self.db = RuntimeDatabase(self.root, path=self.root / "runtime.db")
        self.operators = InstallationOperatorService(self.db, lambda: NamedOperatorIdentity("codex-session-test", 501))
        self.service = PlanningProviderSecurityService(self.db, Store(), self.operators)
        self.assertEqual(self.service.invocation_policy("codex-session").profile, "default")

    def test_session_mode_rejects_fake_secret_reference_and_secret_mode_remains_compatible(self):
        from forge.provider_security import SecretReference
        with self.assertRaisesRegex(ValueError, "cannot carry a secret"):
            self.service.configure(
                configuration_id="codex-config", provider_id="codex-session", operator_context=self.context,
                authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
                provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
                external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
                executable_path="/usr/local/bin/codex", adapter_version="1.0",
                reference=SecretReference("keychain", "//not-a-fake/codex"),
                timeout_seconds=30, input_token_bound=64000, context_token_bound=128000, output_token_bound=16000,
            )
        configured = self.service.configure(
            configuration_id="openai-config", provider_id="openai", operator_context=self.context,
            reference=SecretReference("keychain", "//forge.openai/planning"), model="gpt-5.6",
            timeout_seconds=30, input_token_bound=64000, context_token_bound=128000, output_token_bound=16000,
        )
        self.assertEqual(configured["authentication_mode"], "SECRET_REFERENCE")

    def test_readiness_is_non_generating_and_fails_closed_for_missing_login_and_version(self):
        self.configure()
        missing = CodexCliSessionReadinessChecker(path_usable=lambda _path: False).check(
            self.service.invocation_policy("codex-session"))
        self.assertEqual(missing.state, CodexCliSessionReadinessState.NOT_INSTALLED)
        old_runner = Runner(version="0.152.9")
        old = CodexCliSessionReadinessChecker(runner=old_runner, path_usable=lambda _path: True).check(
            self.service.invocation_policy("codex-session"))
        self.assertEqual(old.state, CodexCliSessionReadinessState.UNSUPPORTED_VERSION)
        signed_out_runner = Runner(login="Not logged in")
        signed_out = CodexCliSessionReadinessChecker(runner=signed_out_runner, path_usable=lambda _path: True).check(
            self.service.invocation_policy("codex-session"))
        self.assertEqual(signed_out.state, CodexCliSessionReadinessState.NOT_SIGNED_IN)
        self.assertFalse(any("exec" in command for command, _kwargs in signed_out_runner.calls))

        stderr_status = Runner()
        original = stderr_status.__call__
        def status_on_stderr(command, **kwargs):
            result = original(command, **kwargs)
            if command[-2:] == ["login", "status"]:
                return Result(result.returncode, "", "Logged in using ChatGPT")
            return result
        ready = CodexCliSessionReadinessChecker(runner=status_on_stderr, path_usable=lambda _path: True).check(
            self.service.invocation_policy("codex-session"))
        self.assertEqual(ready.state, CodexCliSessionReadinessState.READY)

    def test_explicit_model_without_supported_status_route_is_unverified_or_unavailable(self):
        self.configure(model="selected-model")
        runner = Runner()
        unavailable = CodexCliSessionReadinessChecker(
            runner=runner, path_usable=lambda _path: True, model_availability=lambda _policy: False,
        ).check(self.service.invocation_policy("codex-session"))
        self.assertEqual(unavailable.state, CodexCliSessionReadinessState.MODEL_UNAVAILABLE)
        unverified = CodexCliSessionReadinessChecker(
            runner=runner, path_usable=lambda _path: True,
        ).check(self.service.invocation_policy("codex-session"))
        self.assertEqual(unverified.state, CodexCliSessionReadinessState.UNVERIFIED)

    def test_read_only_exec_uses_schema_and_bounded_executor_contract(self):
        self.configure()
        runner = Runner(events='{"type":"turn.completed","message":"private model output"}')
        provider = self.provider(runner)
        response = BoundedActionDerivationProvider(provider).invoke(
            self.request(), approved_scopes=("planner-contract", "planner-docs"), derivation_policy=self.policy,
        )
        self.assertEqual(len(response.proposals or ()), 1)
        command, kwargs = next((item for item in runner.calls if "exec" in item[0]))
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--output-schema", command)
        self.assertIn("--json", command)
        self.assertIn("--skip-git-repo-check", command)
        self.assertNotEqual(Path(kwargs["cwd"]), Path.cwd())
        self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
        self.assertNotIn("CODEX_ACCESS_TOKEN", kwargs["env"])
        self.assertEqual(runner.schemas[0]["type"], "object")
        self.assertNotIn("oneOf", runner.schemas[0])
        self.assertEqual(runner.schemas[0]["required"], ["result"])
        self.assertEqual(runner.schemas[0]["properties"]["result"]["anyOf"][0]["properties"]["proposals"]["items"]["properties"]["write_scopes"]["items"]["enum"],
                         ["forge/planner"])
        evidence = self.invocation_documents()
        self.assertEqual([item["state"] for item in evidence], ["STARTED", "HAPPENED_AND_CONFIRMED"])
        self.assertEqual(evidence[-1]["diagnostic"]["classification"], "COMPLETED_VALID")
        self.assertTrue(evidence[-1]["diagnostic"]["process_started"])
        self.assertEqual(evidence[-1]["diagnostic"]["returncode"], 0)
        self.assertEqual(evidence[-1]["diagnostic"]["terminal_events"], ["turn.completed"])
        self.assertNotIn("private model output", json.dumps(evidence[-1]["diagnostic"]))

    def test_malformed_or_extra_structured_output_is_never_a_proposal(self):
        self.configure()
        response = self.provider(Runner(document(extra=True))).invoke(
            self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy,
        )
        self.assertIsNone(response.proposals)
        self.assertEqual(response.evidence.status, "contract_invalid")
        self.assertEqual(self.invocation_documents()[-1]["diagnostic"]["classification"], "COMPLETED_CONTRACT_INVALID")

    def test_object_root_preserves_governance_refinement_without_permitting_mixed_variants(self):
        self.configure()
        refinement = {"result": {"kind": "governance_refinement", "reason": "needs architecture"}}
        response = self.provider(Runner(refinement)).invoke(
            self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy,
        )
        self.assertIsNone(response.proposals)
        self.assertEqual(response.governance_refinement.reason, "needs architecture")
        mixed = document(); mixed["result"]["reason"] = "not permitted"
        invalid = self.provider(Runner(mixed)).invoke(
            self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy,
        )
        self.assertIsNone(invalid.proposals)
        self.assertEqual(invalid.evidence.status, "contract_invalid")

    def test_scope_expansion_is_rejected_by_existing_deterministic_validator(self):
        self.configure()
        response = self.provider(Runner(document(scope="outside"))).invoke(
            self.request(), approved_scopes=("planner-contract", "planner-docs"), derivation_policy=self.policy,
        )
        with self.assertRaises(ProposalValidationError):
            ActionDerivationValidator().validate(response.proposals or (), self.snapshot, self.input, self.policy)

    def test_existing_pipeline_validates_then_materializes_session_proposals(self):
        self.configure()
        result = AIMissionPlanner(self.provider(Runner(complete_document()))).plan(self.input, self.policy)
        self.assertIsNone(result.governance_refinement)
        self.assertEqual([action.id for intent in result.plan.intents for action in intent.actions],
                         ["derive-contract", "derive-docs"])

    def test_process_ambiguity_has_no_blind_retry(self):
        self.configure()
        runner = Runner(exec_error=subprocess.TimeoutExpired(["codex", "exec"], 30))
        provider = self.provider(runner)
        with self.assertRaises(ProviderSubmissionAmbiguous):
            provider.invoke(self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy)
        self.assertEqual(len([call for call, _kwargs in runner.calls if "exec" in call]), 1)
        self.assertIs(provider.reconcile(self.request()), ProviderSideEffectState.MAY_HAVE_HAPPENED)
        events = self.invocation_documents()
        self.assertEqual([item["state"] for item in events], ["STARTED", "MAY_HAVE_HAPPENED"])
        diagnostic = events[-1]["diagnostic"]
        self.assertEqual(diagnostic["classification"], "MAY_HAVE_HAPPENED")
        self.assertTrue(diagnostic["process_started"])
        self.assertTrue(diagnostic["timed_out"])
        self.assertEqual(diagnostic["exception_type"], "TimeoutExpired")

    def test_subprocess_failure_after_launch_stays_ambiguous_and_is_durable_after_reopen(self):
        self.configure()
        private_error = "do not persist this subprocess message"
        runner = Runner(exec_error=subprocess.CalledProcessError(3, ["codex", "exec"], stderr=private_error))
        with self.assertRaises(ProviderSubmissionAmbiguous):
            self.provider(runner).invoke(
                self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy,
            )
        self.assertEqual(len([call for call, _kwargs in runner.calls if "exec" in call]), 1)
        self.db.close()
        self.db = RuntimeDatabase(self.root, path=self.root / "runtime.db")
        diagnostic = self.invocation_documents()[-1]["diagnostic"]
        self.assertEqual(diagnostic["classification"], "MAY_HAVE_HAPPENED")
        self.assertTrue(diagnostic["process_started"])
        self.assertEqual(diagnostic["exception_type"], "CalledProcessError")
        self.assertEqual(diagnostic["error_category"], "PROCESS_FAILURE")
        self.assertNotIn(private_error, json.dumps(diagnostic))

    def test_process_start_failure_is_proven_and_persists_only_typed_evidence(self):
        self.configure()
        runner = Runner(exec_error=FileNotFoundError(2, "private executable path"))
        with self.assertRaises(CodexCliInvocationRejected) as raised:
            self.provider(runner).invoke(
                self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy,
            )
        self.assertEqual(raised.exception.diagnostic.classification.value, "NOT_STARTED")
        diagnostic = self.invocation_documents()[-1]["diagnostic"]
        self.assertFalse(diagnostic["process_started"])
        self.assertEqual(diagnostic["errno"], 2)
        self.assertEqual(diagnostic["exception_type"], "FileNotFoundError")
        self.assertEqual(diagnostic["error_category"], "PROCESS_START_FAILURE")
        self.assertNotIn("private executable path", json.dumps(diagnostic))
        self.assertEqual(len([call for call, _kwargs in runner.calls if "exec" in call]), 1)

    def test_known_local_schema_rejection_is_not_reported_as_ambiguous(self):
        self.configure()
        private_error = "error: output schema root must be an object; request content is private"
        runner = Runner(exec_result=Result(2, stderr=private_error))
        with self.assertRaises(CodexCliInvocationRejected) as raised:
            self.provider(runner).invoke(
                self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy,
            )
        self.assertEqual(raised.exception.diagnostic.classification.value, "REJECTED_BEFORE_GENERATION")
        diagnostic = self.invocation_documents()[-1]["diagnostic"]
        self.assertTrue(diagnostic["process_started"])
        self.assertEqual(diagnostic["returncode"], 2)
        self.assertEqual(diagnostic["error_category"], "OUTPUT_SCHEMA_REJECTED")
        self.assertNotIn("request content is private", json.dumps(diagnostic))

    def test_unknown_terminal_failure_stays_ambiguous_but_retains_safe_event_names(self):
        self.configure()
        runner = Runner(exec_result=Result(1, stderr="upstream failed with private output"), events='{"type":"turn.failed","message":"private"}\n{"type":"error","message":"private"}')
        with self.assertRaises(ProviderSubmissionAmbiguous):
            self.provider(runner).invoke(
                self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy,
            )
        diagnostic = self.invocation_documents()[-1]["diagnostic"]
        self.assertEqual(diagnostic["classification"], "MAY_HAVE_HAPPENED")
        self.assertEqual(diagnostic["error_category"], "TERMINAL_FAILURE")
        self.assertEqual(diagnostic["terminal_events"], ["error", "turn.failed"])
        self.assertNotIn("private output", json.dumps(diagnostic))

    def test_cleanup_failure_after_a_started_process_is_never_proven_not_started(self):
        self.configure()
        runner = Runner()
        with self.assertRaises(ProviderSubmissionAmbiguous):
            self.provider(runner, temporary_directory=CleanupFailureTemporaryDirectory).invoke(
                self.request(), approved_scopes=("planner-contract",), derivation_policy=self.policy,
            )
        diagnostic = self.invocation_documents()[-1]["diagnostic"]
        self.assertEqual(diagnostic["classification"], "MAY_HAVE_HAPPENED")
        self.assertTrue(diagnostic["process_started"])
        self.assertEqual(diagnostic["error_category"], "LOCAL_CLEANUP_FAILURE")
        self.assertNotIn("private cleanup detail", json.dumps(diagnostic))


if __name__ == "__main__":
    unittest.main()
