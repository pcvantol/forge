"""HTTP consumer tests against EP's pinned v1.1 shared fixtures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import URLError

from forge.models import Producer, ProducerContract, ProducerIdentity, RuntimePrompt, RuntimePromptEnvelope, RuntimePromptSection, RuntimePromptSectionKind, ProviderPromptDefinition
from forge.models.execution_host import ExecutionRequest
from forge.models import ExecutionDispatch, ExecutionEvidenceOutcome
from forge.runtime.database import RuntimeDatabase
from forge.scheduler.ep_http_adapter import EngineeringPlatformHttpConfiguration, EngineeringPlatformHttpExecutionHost


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
    contract = ProducerContract(Producer(ProducerIdentity("forge", "FORGE", "1.0")), "forge-correlation-fixture",
        "action-fixture", RuntimePromptEnvelope(prompt.id, "1.0", "text/markdown", "exact persisted prompt", "sha256:" + "a" * 64),
        ("Execute only the supplied Runtime Prompt.",),
        (("intent_id", "intent-fixture"), ("intent_revision", "7"), ("mission_revision", "3"),
         ("repository_id", "forge"), ("workspace_id", "workspace-1")), mission_id="mission-fixture")
    return ExecutionRequest("engineering-platform", "mission-fixture", "intent-fixture", "7", "action-fixture", prompt,
        "workspace-1", "forge", "forge-correlation-fixture", "2026-09-07T00:00:00Z", producer_contract=contract)


class EngineeringPlatformHttpExecutionHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.database = RuntimeDatabase(".", path=Path(self.temporary.name) / "runtime.db", forge_version="test")
        self.config = EngineeringPlatformHttpConfiguration("https://ep.test", "forge", "credential")
        self.request = _request()
        self.readback = json.loads((FIXTURES / "forge-producer-readback-v1.1.json").read_text())
        self.artifact = (FIXTURES / "forge-terminal-evidence-v1.1.json").read_bytes()

    def tearDown(self) -> None:
        self.database.close(); self.temporary.cleanup()

    @staticmethod
    def _urlopen(responses: list[bytes], observed: list[object]):
        def call(request, *, timeout):
            observed.append(request)
            return _Response(responses.pop(0))
        return call

    def test_accepted_submission_recovers_after_reopen_without_process_memory(self) -> None:
        waiting = {**self.readback, "run": None}
        observed: list[object] = []
        with patch("forge.scheduler.ep_http_adapter.urlopen", self._urlopen([
            json.dumps({"submission_id": "submission-fixture"}).encode(), json.dumps(waiting).encode()], observed)):
            host = EngineeringPlatformHttpExecutionHost(self.config, self.database)
            self.assertIsNone(host.dispatch(self.request))
        self.assertEqual(self.database.execution_host_binding(self.request.correlation_id)["submission_id"], "submission-fixture")
        self.database.close()
        self.database = RuntimeDatabase(".", path=Path(self.temporary.name) / "runtime.db", forge_version="test")
        observed = []
        with patch("forge.scheduler.ep_http_adapter.urlopen", self._urlopen([json.dumps(self.readback).encode()], observed)):
            dispatch = EngineeringPlatformHttpExecutionHost(self.config, self.database).recover_dispatch(self.request)
        self.assertEqual(dispatch.host_run_id, "run-fixture")
        self.assertEqual(observed[0].get_header("Authorization"), "Bearer credential")

    def test_valid_hash_from_another_run_is_rejected_after_raw_artifact_fetch(self) -> None:
        self.database.save_execution_host_binding(self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_id": "submission-fixture", "host_run_id": "run-fixture"})
        substituted = json.loads(self.artifact)
        substituted["run"]["id"] = "other-run"
        raw = json.dumps(substituted, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        readback = json.loads(json.dumps(self.readback))
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        observed: list[object] = []
        with patch("forge.scheduler.ep_http_adapter.urlopen", self._urlopen([json.dumps(readback).encode(), raw], observed)):
            with self.assertRaisesRegex(ValueError, "artifact"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(ExecutionDispatch(self.request, "run-fixture"))
        self.assertEqual(len(observed), 2, "the adapter must fetch and hash real artifact bytes before rejecting it")

    def test_existing_dispatch_with_a_different_run_is_an_identity_error(self) -> None:
        self.database.save_execution_host_binding(self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_id": "submission-fixture", "host_run_id": "run-fixture"})
        changed = json.loads(json.dumps(self.readback)); changed["run"]["id"] = "other-run"
        with patch("forge.scheduler.ep_http_adapter.urlopen", self._urlopen([json.dumps(changed).encode()], [])):
            with self.assertRaisesRegex(ValueError, "conflicts"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database).recover_dispatch(self.request)

    def test_configuration_and_transport_fail_closed_without_persisted_authority(self) -> None:
        with self.assertRaisesRegex(ValueError, "configuration"):
            EngineeringPlatformHttpExecutionHost(EngineeringPlatformHttpConfiguration("", "forge", "credential"), self.database)
        with patch("forge.scheduler.ep_http_adapter.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(Exception, "transport unavailable"):
                EngineeringPlatformHttpExecutionHost(self.config, self.database)._json("/v1/projects/forge/submissions")

    def test_failed_terminal_evidence_without_delivery_revision_is_preserved(self) -> None:
        self.database.save_execution_host_binding(self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_id": "submission-fixture", "host_run_id": "run-fixture"})
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
        with patch("forge.scheduler.ep_http_adapter.urlopen", self._urlopen([json.dumps(readback).encode(), raw], [])):
            evidence = EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(ExecutionDispatch(self.request, "run-fixture"))
        self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.FAILED)
        self.assertIsNone(evidence.repository_evidence.repository_revision)

    def _terminal_retrieval(self, readback: dict, artifact: dict):
        self.database.save_execution_host_binding(self.request.correlation_id,
            {"correlation_id": self.request.correlation_id, "submission_id": "submission-fixture", "host_run_id": "run-fixture"})
        raw = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        with patch("forge.scheduler.ep_http_adapter.urlopen", self._urlopen([json.dumps(readback).encode(), raw], [])):
            return EngineeringPlatformHttpExecutionHost(self.config, self.database).retrieve_evidence(ExecutionDispatch(self.request, "run-fixture"))

    def test_terminal_outcome_qualification_digest_and_flags_must_have_parity(self) -> None:
        cases = (
            ("artifact outcome", lambda r, a: a["run"].update({"outcome": "FAILED"})),
            ("report state", lambda r, a: a["report"].update({"terminal_state": "FAILED"})),
            ("qualification", lambda r, a: r["result"].update({"delivery_qualified": False})),
            ("missing accepted digest", lambda r, a: (r["submission"].pop("accepted_request_digest"), a["submission"].pop("accepted_request_digest"))),
            ("invalid accepted digest type", lambda r, a: (r["submission"].update({"accepted_request_digest": []}), a["submission"].update({"accepted_request_digest": []}))),
            ("terminal flag", lambda r, a: r["run"].update({"terminal": False})),
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


if __name__ == "__main__":
    unittest.main()
