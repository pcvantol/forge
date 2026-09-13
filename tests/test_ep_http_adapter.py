"""HTTP consumer tests for the strict EP producer-readback v1.2 boundary."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from forge.models import ForgeActionContextEnvelope, ForgePlanningContextEnvelope, Producer, ProducerContract, ProducerIdentity, RuntimePrompt, RuntimePromptEnvelope, RuntimePromptSection, RuntimePromptSectionKind, ProviderPromptDefinition
from forge.models.execution_host import ExecutionRequest
from forge.models import ExecutionDispatch, ExecutionEvidenceOutcome
from forge.runtime.database import RuntimeDatabase
from forge.scheduler.ep_http_adapter import (
    EngineeringPlatformHttpConfiguration,
    EngineeringPlatformHttpExecutionHost,
    _NoRedirectHandler,
)


FIXTURES = Path(__file__).with_name("fixtures")


class _Response:
    def __init__(self, value: bytes) -> None: self.value = value
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, _limit: int | None = None) -> bytes: return self.value if _limit is None else self.value[:_limit]


def _prompt() -> RuntimePrompt:
    return RuntimePrompt("runtime-prompt-fixture", "intent-fixture", "7", "action-fixture",
        ProviderPromptDefinition("provider", "1"), "sha256:" + "a" * 64,
        tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind))


def _request() -> ExecutionRequest:
    prompt = _prompt()
    context = ForgeActionContextEnvelope.create(
        action_id="action-fixture", summary="Execute the safe fixture action.",
        source_digest=prompt.generation_request_digest,
    )
    planning = ForgePlanningContextEnvelope.create(
        mission_id="mission-fixture", mission_revision="3", intent_id="intent-fixture", intent_revision="7",
        action_id="action-fixture", mission_title="Fixture Mission",
        business_summary="Deliver the fixture outcome.", engineering_summary="Exercise the Forge to EP contract.",
        mission_lifecycle="ACTIVE", decision_evidence_reference="architecture-review:fixture",
    )
    contract = ProducerContract(Producer(ProducerIdentity("forge", "FORGE", "2.7.2")), "forge-correlation-fixture",
        "action-fixture", RuntimePromptEnvelope(prompt.id, "1.0", "text/markdown", "exact persisted prompt", "sha256:" + "a" * 64),
        ("Execute only the supplied Runtime Prompt.",),
        (("intent_id", "intent-fixture"), ("intent_revision", "7"), ("mission_revision", "3"),
         ("repository_id", "forge"), ("workspace_id", "workspace-1")), action_context=context,
        planning_context=planning, mission_id="mission-fixture")
    return ExecutionRequest("engineering-platform", "mission-fixture", "intent-fixture", "7", "action-fixture", prompt,
        "workspace-1", "forge", "forge-correlation-fixture", "2026-09-07T00:00:00Z", producer_contract=contract)


class EngineeringPlatformHttpExecutionHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.database = RuntimeDatabase(".", path=Path(self.temporary.name) / "runtime.db", forge_version="test")
        self.config = EngineeringPlatformHttpConfiguration(
            "https://ep.test", "forge", "credential",
            expected_instance_id="instance-fixture", repository_id="forge", repository_identity="forge",
            peer_binding_id="ep-primary", peer_configuration_revision=1,
            peer_configuration_digest="sha256:" + "d" * 64,
        )
        self.request = _request()
        self.compatible = {"contract_version": "1.0", "producer": {"id": "engineering-platform", "version": "2.3.0"},
            "instance": {"id": "instance-fixture"}, "contracts": {"producer_readback": ["1.2"], "terminal_evidence": ["1.3"]}}
        self.readback = json.loads((FIXTURES / "forge-producer-readback-v1.1.json").read_text())
        self.readback["contract_version"] = "1.2"
        self.readback["producer"]["version"] = "2.7.2"
        self.readback["provenance"]["forge_execution"].update({
            "contract_version": "1.3", "producer_contract_version": "1.0",
            "forge_application_version": "2.7.2",
            "action_context_envelope": self.request.producer_contract.action_context.to_dict(),
            "planning_context_envelope": self.request.producer_contract.planning_context.to_dict(),
        })
        self.readback["disposition"] = {"state": "QUEUED", "terminal": False, "execution_eligible": True,
            "revision": 0, "operation_id": None, "event_reference": None, "reason": "NOT_RECORDED",
            "actor_reference": "NOT_RECORDED", "recorded_at": None}
        self.readback["run"].update({
            "execution_started_at": "2026-09-12T00:00:00+00:00",
            "execution_completed_at": "2026-09-12T00:01:00+00:00",
            "execution_duration_ms": 60_000,
        })
        artifact = json.loads((FIXTURES / "forge-terminal-evidence-v1.1.json").read_text())
        artifact["contract_version"] = "1.3"
        artifact["producer"]["version"] = "2.7.2"
        artifact["provenance"].update({
            "contract_version": "1.3", "producer_contract_version": "1.0",
            "forge_application_version": "2.7.2",
            "action_context_envelope": self.request.producer_contract.action_context.to_dict(),
            "planning_context_envelope": self.request.producer_contract.planning_context.to_dict(),
        })
        artifact["assurance"] = {"status": "PASS", "profile": {"version": "validation-profile@1",
            "digest": "sha256:" + "b" * 64, "candidate_sha": "c" * 40}, "quality_review": "PASS",
            "security_review": "PASS", "repair_rounds": {"used": 0, "maximum": 3},
            "findings": {"open_blocking": 0, "open_non_blocking": 0, "artifact": None}}
        artifact["run"].update({
            "execution_started_at": "2026-09-12T00:00:00+00:00",
            "execution_completed_at": "2026-09-12T00:01:00+00:00",
            "execution_duration_ms": 60_000,
        })
        artifact["host_execution"] = {
            "contract_version": "1.0",
            "start": {
                "status": "AVAILABLE", "target_branch": "main", "target_commit": "a" * 40,
                "checkout_identity_digest": "sha256:" + "d" * 64,
                "tracked_file_count": 2, "inventory_digest": "sha256:" + "e" * 64,
            },
            "terminal": {
                "status": "AVAILABLE", "tracked_file_count": 2,
                "inventory_digest": "sha256:" + "f" * 64, "worktree_state": "clean",
                "diff": {"modified": 0, "created": 0, "deleted": 0, "renamed": 0},
                "activity": {"provider_invocations": 1, "host_validation_actions": 2},
            },
        }
        self.artifact = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n"

    def _accepted_submission(self) -> dict[str, object]:
        return {
            "submission_id": "submission-fixture",
            "receipt": {
                "contract_version": "1.0",
                "id": "ep-submission-receipt:submission-fixture",
                "event": "FORGE_SUBMISSION_ACCEPTED",
                "issued_at": "2026-09-12T00:00:00Z",
                "submission_id": "submission-fixture",
                "ep_instance_id": "instance-fixture",
                "ep_application_version": "2.3.8",
                "producer_contract_version": "1.0",
                "forge_provenance_contract_version": "1.3",
                "forge_application_version": "2.7.2",
                "producer_readback_contract_version": "1.2",
                "accepted_request_digest": "sha256:" + "c" * 64,
            },
        }

    def tearDown(self) -> None:
        self.database.close(); self.temporary.cleanup()

    def _seed_binding(self) -> None:
        host = EngineeringPlatformHttpExecutionHost(self.config, self.database)
        host._binding(self.request)
        self.database.save_execution_host_binding(self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_id": "submission-fixture", "host_run_id": "run-fixture",
             "submission_receipt": self._accepted_submission()["receipt"]})

    @staticmethod
    def _urlopen(responses: list[bytes], observed: list[object]):
        def call(request, *, timeout):
            observed.append(request)
            return _Response(responses.pop(0))
        return call

    def test_accepted_submission_recovers_after_reopen_without_process_memory(self) -> None:
        waiting = {**self.readback, "run": None}
        observed: list[object] = []
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
            json.dumps(self.compatible).encode(), json.dumps(self._accepted_submission()).encode(), json.dumps(waiting).encode()], observed)):
            host = EngineeringPlatformHttpExecutionHost(self.config, self.database)
            self.assertIsNone(host.dispatch(self.request))
        self.assertEqual(self.database.execution_host_binding(self.request.correlation_id)["submission_id"], "submission-fixture")
        self.assertEqual(
            self.database.execution_host_binding(self.request.correlation_id)["submission_receipt"]["id"],
            "ep-submission-receipt:submission-fixture",
        )
        sent, received = self.database.execution_host_exchange_audit(self.request.correlation_id)
        self.assertEqual((sent["direction"], sent["event_kind"]), ("FORGE_TO_EP", "FORGE_SUBMISSION_SENT"))
        self.assertEqual((received["direction"], received["event_kind"]), ("EP_TO_FORGE", "EP_SUBMISSION_RECEIPT_RECEIVED"))
        self.assertEqual(received["document"]["ep_application_version"], "2.3.8")
        self.assertEqual(received["document"]["receipt_id"], "ep-submission-receipt:submission-fixture")
        journal = self.database.operational_log_page(correlation_id=self.request.correlation_id)
        self.assertEqual(
            {item["event"] for item in journal["items"]},
            {"execution_host_binding_persisted", "forge_submission_sent", "ep_submission_receipt_received"},
        )
        receipt_event = next(item for item in journal["items"] if item["event"] == "ep_submission_receipt_received")
        self.assertEqual(receipt_event["details"]["ep_application_version"], "2.3.8")
        self.assertEqual(receipt_event["details"]["exchange_direction"], "EP_TO_FORGE")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database._connection.execute(
                "UPDATE execution_host_exchange_audit SET event_kind='FORGE_SUBMISSION_SENT' "
                "WHERE audit_id=?", (received["audit_id"],),
            )
        submitted = json.loads(observed[1].data.decode())
        self.assertEqual(submitted["producer"]["version"], "2.7.2")
        self.assertEqual(submitted["constraints"]["forge_execution"], {
            "contract_version": "1.3", "host_id": "engineering-platform", "repository_id": "forge",
            "correlation_id": "forge-correlation-fixture", "mission_id": "mission-fixture",
            "mission_revision": "3", "intent_id": "intent-fixture", "intent_revision": "7",
            "action_id": "action-fixture", "runtime_prompt": {"id": "runtime-prompt-fixture", "content_digest": "sha256:" + "a" * 64},
            "retry_of_correlation_id": None, "producer_contract_version": "1.0",
            "forge_application_version": "2.7.2",
            "action_context_envelope": self.request.producer_contract.action_context.to_dict(),
            "planning_context_envelope": self.request.producer_contract.planning_context.to_dict(),
        })
        self.database.close()
        self.database = RuntimeDatabase(".", path=Path(self.temporary.name) / "runtime.db", forge_version="test")
        observed = []
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(self.readback).encode()], observed)):
            dispatch = EngineeringPlatformHttpExecutionHost(self.config, self.database).recover_dispatch(self.request)
        self.assertEqual(dispatch.host_run_id, "run-fixture")
        self.assertEqual(observed[0].get_header("Authorization"), "Bearer credential")

    def test_submission_without_the_versioned_ep_receipt_fails_closed_and_is_audited(self) -> None:
        observed: list[object] = []
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), b'{"submission_id":"submission-fixture"}'], observed)):
            with self.assertRaisesRegex(ValueError, "omits a versioned receipt"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).dispatch(self.request)
        (sent,) = self.database.execution_host_exchange_audit(self.request.correlation_id)
        self.assertEqual((sent["direction"], sent["event_kind"]), ("FORGE_TO_EP", "FORGE_SUBMISSION_SENT"))
        self.assertEqual([request.get_method() for request in observed], ["GET", "POST"])

    def test_submission_receipt_requires_a_canonical_accepted_request_digest(self) -> None:
        accepted = self._accepted_submission()
        accepted["receipt"]["accepted_request_digest"] = "sha256:not-a-digest"  # type: ignore[index]
        observed: list[object] = []
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(accepted).encode()], observed)):
            with self.assertRaisesRegex(ValueError, "accepted-request digest is invalid"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).dispatch(self.request)

    def test_capability_preflight_rejects_legacy_and_never_posts(self) -> None:
        legacy = {"contract_version": "1.0", "producer": {"id": "engineering-platform", "version": "2.3.0"},
            "instance": {"id": "instance-fixture"}, "contracts": {"producer_readback": ["1.1"], "terminal_evidence": ["1.1"]}}
        observed: list[object] = []
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([json.dumps(legacy).encode()], observed)):
            with self.assertRaisesRegex(ValueError, "INCOMPATIBLE"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).dispatch(self.request)
        self.assertEqual(observed[0].get_method(), "GET")

    def test_preflight_enforces_exact_product_instance_and_declaration_schema(self) -> None:
        cases = (
            ("EP_INSTANCE_IDENTITY_MISMATCH", {**self.compatible, "instance": {"id": "other-instance"}}),
            ("MALFORMED", {**self.compatible, "producer": {"id": "other-product", "version": "1"}}),
            ("MALFORMED", {**self.compatible, "unexpected": True}),
        )
        for error, declaration in cases:
            with self.subTest(error=error):
                observed: list[object] = []
                with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([json.dumps(declaration).encode()], observed)):
                    with self.assertRaisesRegex(ValueError, error):
                        EngineeringPlatformHttpExecutionHost(self.config, self.database).preflight()
                self.assertEqual([request.get_method() for request in observed], ["GET"])

    def test_preflight_authentication_rejection_is_safe_and_never_posts(self) -> None:
        rejected = HTTPError("https://ep.test/v1/producer-compatibility", 401, "denied", {}, None)
        with patch("forge.scheduler.ep_http_adapter._open", side_effect=rejected) as transport:
            with self.assertRaisesRegex(ValueError, "401") as error:
                EngineeringPlatformHttpExecutionHost(self.config, self.database).preflight()
        self.assertNotIn("credential", str(error.exception))
        self.assertEqual(transport.call_args.args[0].get_method(), "GET")

    def test_redirects_and_header_injection_are_rejected(self) -> None:
        self.assertIsNone(_NoRedirectHandler().redirect_request(None, None, 302, "redirect", {}, "https://other.test"))
        with self.assertRaisesRegex(ValueError, "configuration"):
            EngineeringPlatformHttpExecutionHost(
                replace(self.config, bearer_token="credential\r\nInjected: value"), self.database,
            )

    def test_request_scope_mismatch_blocks_before_network_or_submission(self) -> None:
        host = EngineeringPlatformHttpExecutionHost(self.config, self.database)
        for request in (
            replace(self.request, host_id="other-host"),
            replace(self.request, repository_id="other-repository"),
            replace(self.request, repository_identity="other-source"),
        ):
            with self.subTest(request=request):
                with patch("forge.scheduler.ep_http_adapter._open") as transport:
                    with self.assertRaisesRegex(ValueError, "SCOPE_MISMATCH"):
                        host.dispatch(request)
                transport.assert_not_called()

    def test_correlation_cannot_be_retargeted_and_historical_binding_fails_closed(self) -> None:
        host = EngineeringPlatformHttpExecutionHost(self.config, self.database)
        host._binding(self.request)
        changed = replace(self.config, peer_configuration_revision=2,
                          peer_configuration_digest="sha256:" + "e" * 64)
        with patch("forge.scheduler.ep_http_adapter._open") as transport:
            with self.assertRaisesRegex(ValueError, "RETARGETING_BLOCKED"):
                EngineeringPlatformHttpExecutionHost(changed, self.database).dispatch(self.request)
        transport.assert_not_called()

        self.database._connection.execute("DELETE FROM execution_host_bindings")
        self.database.save_execution_host_binding(
            self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_id": "historic-submission"},
        )
        with self.assertRaisesRegex(ValueError, "HISTORICAL_BINDING"):
            host.recover_dispatch(self.request)

    def test_valid_hash_from_another_run_is_rejected_after_raw_artifact_fetch(self) -> None:
        self._seed_binding()
        substituted = json.loads(self.artifact)
        substituted["run"]["id"] = "other-run"
        raw = json.dumps(substituted, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        readback = json.loads(json.dumps(self.readback))
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        observed: list[object] = []
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(readback).encode(), raw], observed)):
            with self.assertRaisesRegex(ValueError, "artifact"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(ExecutionDispatch(self.request, "run-fixture"))
        self.assertEqual(len(observed), 3, "the adapter must preflight, fetch and hash real artifact bytes before rejecting it")

    def test_existing_dispatch_with_a_different_run_is_an_identity_error(self) -> None:
        self._seed_binding()
        changed = json.loads(json.dumps(self.readback)); changed["run"]["id"] = "other-run"
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(changed).encode()], [])):
            with self.assertRaisesRegex(ValueError, "conflicts"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).recover_dispatch(self.request)

    def test_terminal_evidence_carries_the_exact_persisted_submission_receipt(self) -> None:
        self._seed_binding()
        receipt = self._accepted_submission()["receipt"]
        self.database.save_execution_host_binding(
            self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_receipt": receipt},
        )
        readback = json.loads(json.dumps(self.readback))
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(self.artifact).hexdigest()
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(readback).encode(), self.artifact], [])):
            evidence = EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(
                ExecutionDispatch(self.request, "run-fixture")
            )
        self.assertEqual(evidence.receipt_id, "ep-submission-receipt:submission-fixture")
        self.assertEqual(evidence.execution_started_at, "2026-09-12T00:00:00+00:00")
        self.assertEqual(evidence.execution_completed_at, "2026-09-12T00:01:00+00:00")
        self.assertEqual(evidence.execution_duration_ms, 60_000)

    def test_v13_host_evidence_rejects_a_raw_checkout_path(self) -> None:
        """A local EP path is operator evidence, never Forge receipt data."""
        artifact = json.loads(self.artifact)
        artifact["host_execution"]["start"]["checkout_path"] = "/private/ep-checkout"
        with self.assertRaisesRegex(ValueError, "host start evidence"):
            self._terminal_retrieval(json.loads(json.dumps(self.readback)), artifact)

    def test_historical_artifact_without_timing_uses_complete_authenticated_readback(self) -> None:
        readback, artifact = json.loads(json.dumps(self.readback)), json.loads(self.artifact)
        artifact["run"].pop("execution_started_at")
        artifact["run"].pop("execution_completed_at")
        artifact["run"].pop("execution_duration_ms")

        evidence = self._terminal_retrieval(readback, artifact)

        self.assertEqual(evidence.execution_duration_ms, 60_000)

    def test_terminal_evidence_carries_the_exact_persisted_retry_lineage(self) -> None:
        self._seed_binding()
        request = replace(self.request, retry_of_correlation_id="prior-correlation")
        readback = json.loads(json.dumps(self.readback))
        artifact = json.loads(self.artifact)
        readback["provenance"]["forge_execution"]["retry_of_correlation_id"] = "prior-correlation"
        artifact["provenance"]["retry_of_correlation_id"] = "prior-correlation"
        raw = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(readback).encode(), raw], [])):
            evidence = EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(
                ExecutionDispatch(request, "run-fixture")
            )
        self.assertEqual(evidence.retry_of_correlation_id, "prior-correlation")
        self.assertEqual(evidence.original_correlation_id, "prior-correlation")

    def test_historical_terminal_evidence_uses_only_the_exact_immutable_receipt_audit(self) -> None:
        host = EngineeringPlatformHttpExecutionHost(self.config, self.database)
        host._binding(self.request)
        self.database.save_execution_host_binding(
            self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_id": "submission-fixture", "host_run_id": "run-fixture"},
        )
        binding = self.database.execution_host_binding(self.request.correlation_id)
        self.assertIsNotNone(binding)
        host._bindings.record_execution_host_exchange_audit(
            self.request.correlation_id, direction="EP_TO_FORGE", event_kind="EP_SUBMISSION_RECEIPT_RECEIVED",
            document=host._audit_document(self.request, binding, receipt=self._accepted_submission()["receipt"]),
        )
        readback = json.loads(json.dumps(self.readback))
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(self.artifact).hexdigest()
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(readback).encode(), self.artifact], [])):
            evidence = host.retrieve_evidence(ExecutionDispatch(self.request, "run-fixture"))
        self.assertEqual(evidence.receipt_id, "ep-submission-receipt:submission-fixture")

    def test_historical_receipt_audit_mismatch_fails_closed(self) -> None:
        host = EngineeringPlatformHttpExecutionHost(self.config, self.database)
        host._binding(self.request)
        self.database.save_execution_host_binding(
            self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_id": "submission-fixture", "host_run_id": "run-fixture"},
        )
        binding = self.database.execution_host_binding(self.request.correlation_id)
        self.assertIsNotNone(binding)
        document = host._audit_document(self.request, binding, receipt=self._accepted_submission()["receipt"])
        document["submission_id"] = "other-submission"
        host._bindings.record_execution_host_exchange_audit(
            self.request.correlation_id, direction="EP_TO_FORGE", event_kind="EP_SUBMISSION_RECEIPT_RECEIVED",
            document=document,
        )
        readback = json.loads(json.dumps(self.readback))
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(self.artifact).hexdigest()
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(readback).encode(), self.artifact], [])):
            with self.assertRaisesRegex(ValueError, "does not bind"):
                host.retrieve_evidence(ExecutionDispatch(self.request, "run-fixture"))

    def test_host_proven_operator_retry_resolution_returns_the_successor_evidence(self) -> None:
        self._seed_binding()
        parent = json.loads(json.dumps(self.readback))
        parent["run"].update({"state": "BLOCKED", "terminal": False, "operator_resolution": "RETRIED"})
        parent["result"].update({"outcome": "BLOCKED", "terminal": False, "delivery_qualified": False})
        parent["evidence"]["terminal_artifact"] = None
        parent["disposition"].update({"resolution_submission_id": "retry-submission", "retry_parent_run_id": None})
        successor = json.loads(json.dumps(self.readback))
        successor["submission"]["id"] = "retry-submission"
        successor["run"].update({"id": "retry-run", "state": "COMPLETE", "terminal": True, "operator_resolution": "NONE"})
        successor["disposition"].update({"resolution_submission_id": None, "retry_parent_run_id": "run-fixture"})
        artifact = json.loads(self.artifact)
        artifact["submission"]["id"] = "retry-submission"
        artifact["run"]["id"] = "retry-run"
        raw = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        successor["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(parent).encode(), json.dumps(successor).encode(), raw], [])):
            evidence = EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(
                ExecutionDispatch(self.request, "run-fixture")
            )
        self.assertEqual(evidence.host_run_id, "retry-run")
        self.assertEqual(evidence.resolved_from_host_run_id, "run-fixture")
        self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.COMPLETE)
        binding = self.database.execution_host_binding(self.request.correlation_id)
        self.assertEqual(binding["operator_retry_resolution"], {
            "submission_id": "retry-submission", "retry_parent_run_id": "run-fixture", "run_id": "retry-run",
        })
        page = self.database.operational_log_page(correlation_id=self.request.correlation_id)
        event = next(item for item in page["items"] if item["event"] == "ep_operator_retry_resolution_evidence_accepted")
        self.assertEqual(event["run_id"], "retry-run")
        self.assertEqual(event["details"]["resolution_submission_id"], "retry-submission")

    def test_operator_retry_resolution_requires_its_exact_parent_run(self) -> None:
        self._seed_binding()
        parent = json.loads(json.dumps(self.readback))
        parent["run"].update({"state": "BLOCKED", "terminal": False, "operator_resolution": "RETRIED"})
        parent["result"].update({"outcome": "BLOCKED", "terminal": False, "delivery_qualified": False})
        parent["evidence"]["terminal_artifact"] = None
        parent["disposition"].update({"resolution_submission_id": "retry-submission", "retry_parent_run_id": None})
        successor = json.loads(json.dumps(self.readback))
        successor["submission"]["id"] = "retry-submission"
        successor["run"].update({"id": "retry-run", "state": "COMPLETE", "terminal": True, "operator_resolution": "NONE"})
        successor["disposition"].update({"resolution_submission_id": None, "retry_parent_run_id": "other-run"})
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(parent).encode(), json.dumps(successor).encode()], [])):
            with self.assertRaisesRegex(ValueError, "lineage"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(
                    ExecutionDispatch(self.request, "run-fixture")
                )

    def test_configuration_and_transport_fail_closed_without_persisted_authority(self) -> None:
        with self.assertRaisesRegex(ValueError, "configuration"):
            EngineeringPlatformHttpExecutionHost(EngineeringPlatformHttpConfiguration("", "forge", "credential"), self.database)
        with patch("forge.scheduler.ep_http_adapter._open", side_effect=URLError("offline")):
            with self.assertRaisesRegex(Exception, "transport unavailable"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database)._json("/v1/projects/forge/submissions")

    def test_failed_terminal_evidence_without_delivery_revision_is_preserved(self) -> None:
        self._seed_binding()
        artifact = json.loads(self.artifact)
        artifact["run"].update({"outcome": "FAILED", "delivery_qualified": False})
        artifact["report"]["terminal_state"] = "FAILED"
        artifact["repository"].update({"revision": None, "revision_required": False})
        raw = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        readback = json.loads(json.dumps(self.readback))
        readback["result"].update({"outcome": "FAILED", "delivery_qualified": False})
        readback["run"].update({"state": "FAILED"})
        readback["evidence"]["repository"]["revision"] = None
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(readback).encode(), raw], [])):
            evidence = EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(ExecutionDispatch(self.request, "run-fixture"))
        self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.FAILED)
        self.assertIsNone(evidence.repository_evidence.repository_revision)

    def test_blocked_retried_run_without_an_immutable_artifact_fails_closed(self) -> None:
        self._seed_binding()
        terminal = json.loads(json.dumps(self.readback))
        terminal["run"].update({"state": "BLOCKED", "terminal": False, "operator_resolution": "RETRIED"})
        terminal["result"].update({"outcome": "BLOCKED", "terminal": False, "delivery_qualified": False})
        terminal["evidence"]["terminal_artifact"] = None
        observed: list[object] = []
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(terminal).encode()], observed)):
            with self.assertRaisesRegex(ValueError, "EP retry resolution successor identity is invalid"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(
                    ExecutionDispatch(self.request, "run-fixture")
                )
        self.assertEqual(len(observed), 2, "a missing terminal artifact must never be fetched or fabricated")

    def _terminal_retrieval(self, readback: dict, artifact: dict):
        self._seed_binding()
        raw = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        with patch("forge.scheduler.ep_http_adapter._open", self._urlopen([
                json.dumps(self.compatible).encode(), json.dumps(readback).encode(), raw], [])):
            return EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(ExecutionDispatch(self.request, "run-fixture"))

    def test_terminal_outcome_qualification_digest_and_flags_must_have_parity(self) -> None:
        cases = (
            ("artifact outcome", lambda r, a: a["run"].update({"outcome": "FAILED"})),
            ("report state", lambda r, a: a["report"].update({"terminal_state": "FAILED"})),
            ("qualification", lambda r, a: r["result"].update({"delivery_qualified": False})),
            ("missing accepted digest", lambda r, a: (r["submission"].pop("accepted_request_digest"), a["submission"].pop("accepted_request_digest"))),
            ("invalid accepted digest type", lambda r, a: (r["submission"].update({"accepted_request_digest": []}), a["submission"].update({"accepted_request_digest": []}))),
            ("terminal flag", lambda r, a: r["run"].update({"terminal": False})),
            ("missing timing", lambda r, a: r["run"].pop("execution_duration_ms")),
            ("timing mismatch", lambda r, a: a["run"].update({"execution_duration_ms": 59_000})),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                readback, artifact = json.loads(json.dumps(self.readback)), json.loads(self.artifact)
                mutate(readback, artifact)
                with self.assertRaises(ValueError):
                    self._terminal_retrieval(readback, artifact)
                self.database._connection.execute("DELETE FROM execution_host_bindings")

    def test_complete_requires_qualified_delivery_revision(self) -> None:
        readback, artifact = json.loads(json.dumps(self.readback)), json.loads(self.artifact)
        readback["evidence"]["repository"]["revision"] = None
        artifact["repository"].update({"revision": None, "revision_required": False})
        with self.assertRaisesRegex(ValueError, "qualified delivery revision"):
            self._terminal_retrieval(readback, artifact)

    def test_exact_host_verified_noop_assurance_without_a_profile_is_accepted(self) -> None:
        readback, artifact = json.loads(json.dumps(self.readback)), json.loads(self.artifact)
        artifact["assurance"] = {
            "status": "NOT_RECORDED", "profile": None,
            "quality_review": "NOT_RECORDED", "security_review": "NOT_RECORDED",
            "repair_rounds": {"used": 0, "maximum": 3},
            "findings": {"open_blocking": 0, "open_non_blocking": 0, "artifact": None},
        }

        evidence = self._terminal_retrieval(readback, artifact)

        self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.COMPLETE)

    def test_partial_not_recorded_assurance_fails_closed(self) -> None:
        cases = (
            ("review", lambda assurance: assurance.update({"quality_review": "PASS"})),
            ("repair", lambda assurance: assurance["repair_rounds"].update({"used": 1})),
            ("finding", lambda assurance: assurance["findings"].update({"open_blocking": 1})),
            ("status", lambda assurance: assurance.update({"status": "PASS"})),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                readback, artifact = json.loads(json.dumps(self.readback)), json.loads(self.artifact)
                artifact["assurance"] = {
                    "status": "NOT_RECORDED", "profile": None,
                    "quality_review": "NOT_RECORDED", "security_review": "NOT_RECORDED",
                    "repair_rounds": {"used": 0, "maximum": 3},
                    "findings": {"open_blocking": 0, "open_non_blocking": 0, "artifact": None},
                }
                mutate(artifact["assurance"])
                with self.assertRaises(ValueError):
                    self._terminal_retrieval(readback, artifact)
                self.database._connection.execute("DELETE FROM execution_host_bindings")


if __name__ == "__main__":
    unittest.main()
