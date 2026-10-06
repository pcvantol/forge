"""Guard the installed qualifier's observation of rejected EP HTTP traffic."""

from __future__ import annotations

import unittest
from copy import deepcopy
import os
from pathlib import Path
import socket
import subprocess
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from forge.ep_simulator import EpSimulatorScenario, EpSimulatorServer, EpSimulatorState
from forge.qualification.producer_fixture_conformance import (
    ProducerFixtureError, rejection_matrix, source_receipt, validate_fixture,
    validate_identity_fixture,
)
from scripts.qualification.qualify_installed_http_successor import (
    _child_env, _count_ep_http_requests, _installed_runtime_storage_negatives, _loopback_only,
)


class InstalledHttpSuccessorQualificationTests(unittest.TestCase):
    def test_installed_runtime_marker_storage_and_schema_fail_without_new_identity(self) -> None:
        with TemporaryDirectory() as directory:
            cases = _installed_runtime_storage_negatives(Path(directory) / "runtime")
        self.assertEqual(cases, [
            {"case": "wrong-runtime-marker", "result": "REJECTED"},
            {"case": "missing-runtime-storage", "result": "REJECTED"},
            {"case": "unsupported-runtime-schema", "result": "REJECTED"},
        ])

    def test_scenario_process_receives_no_host_credentials_or_external_network(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
            "GH_TOKEN": "private", "OPENAI_API_KEY": "private", "AWS_SECRET_ACCESS_KEY": "private",
        }):
            root = Path(directory)
            env = _child_env(root)
            self.assertEqual(env["HOME"], str(root / "home"))
            self.assertEqual(env["CODEX_HOME"], str(root / "config" / "codex"))
            self.assertEqual(env["PATH"], "/usr/bin:/bin")
            for name in ("GH_TOKEN", "OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY"):
                self.assertNotIn(name, env)
            endpoint = "http://127.0.0.1:34567"
            with _loopback_only(endpoint), self.assertRaisesRegex(PermissionError, "non-simulator"):
                socket.getaddrinfo("github.com", 443)
            with _loopback_only(endpoint), socket.socket() as connection, \
                 self.assertRaisesRegex(PermissionError, "non-simulator"):
                connection.connect(("8.8.8.8", 443))
            with _loopback_only(endpoint), socket.socket() as connection, \
                 self.assertRaisesRegex(PermissionError, "non-simulator"):
                connection.connect(("127.0.0.1", 34568))
            with _loopback_only(endpoint), self.assertRaisesRegex(PermissionError, "real provider"):
                subprocess.run(["/usr/bin/true"], check=True)

    def _producer_fixture(self):
        state = EpSimulatorState(project_id="test-project", repository_id="test-repository")
        payload = {
            "repository_id": "test-repository",
            "producer": {"id": "forge", "type": "FORGE", "version": "fixture-version"},
            "prompt": "Canonical café prompt", "idempotency_key": "correlation-fixture",
            "correlation_id": "correlation-fixture", "mission_id": "mission-fixture",
            "engineering_action_id": "action-fixture",
            "constraints": {
                "forge_execution": {"contract_version": "1.3", "producer_contract_version": "1.4",
                                    "forge_application_version": "fixture-version"},
                "repository_revision_binding": {"requested_revision": "0" * 40,
                                                "allowed_baseline_revision": None},
            },
        }
        submission_id = state.accept(payload)["submission_id"]
        return state, payload, submission_id

    def test_pinned_producer_fixture_accepts_pending_and_terminal_then_rejects_drift(self) -> None:
        receipt = source_receipt()
        self.assertEqual(receipt["readback_contract"], "1.2")
        self.assertEqual(receipt["terminal_contract"], "1.4")
        state, payload, submission_id = self._producer_fixture()
        self.assertEqual(state.submitted_payload(submission_id), payload)
        pending = state.readback(submission_id)
        pending_result = validate_fixture(
            payload, pending, None, project_id="test-project",
            repository_id="test-repository", submission_id=submission_id,
        )
        self.assertIsNone(pending_result["run_id"])
        state.complete(submission_id, delivery_revision="a" * 40)
        readback, raw = state.terminal_documents(submission_id)
        result = validate_fixture(
            payload, readback, raw, project_id="test-project",
            repository_id="test-repository", submission_id=submission_id,
        )
        self.assertEqual(result["run_id"], "sim-run-0001")
        negatives = rejection_matrix(
            payload, readback, raw, project_id="test-project",
            repository_id="test-repository", submission_id=submission_id,
        )
        self.assertEqual(len(negatives), 28)
        self.assertEqual({item["result"] for item in negatives}, {"REJECTED"})
        self.assertTrue({"artifact-host-null", "queued-operation",
                         "artifact-requested-revision", "artifact-delivery-revision"}
                        <= {item["case"] for item in negatives})
        changed = deepcopy(readback)
        changed["provenance"]["forge_execution"]["contract_version"] = "wrong"
        with self.assertRaises(ProducerFixtureError):
            validate_fixture(payload, changed, raw, project_id="test-project",
                             repository_id="test-repository", submission_id=submission_id)
        with self.assertRaises(ProducerFixtureError):
            validate_fixture(payload, readback, raw[:-1], project_id="test-project",
                             repository_id="test-repository", submission_id=submission_id)

    def test_pinned_schema_rejects_changed_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            altered = Path(directory) / "schema.json"
            altered.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ProducerFixtureError, "schema bytes"):
                source_receipt(altered)
            with self.assertRaisesRegex(ProducerFixtureError, "identity readback schema bytes"):
                source_receipt(identity_schema_path=altered)

    def test_protected_main_identity_fixture_binds_terminal_v13_to_v12_source(self) -> None:
        state, payload, submission_id = self._producer_fixture()
        state.set_scenario(EpSimulatorScenario(identity_readback_supported=True))
        state.complete(submission_id, delivery_revision="a" * 40)
        source_readback, raw = state.terminal_documents(submission_id)
        recovered = state.identity_readback(
            repository_id="test-repository", correlation_id=payload["correlation_id"],
            idempotency_key=payload["idempotency_key"],
            accepted_request_digest=source_readback["submission"]["accepted_request_digest"],
            identity_contract="1.0", readback_contract="1.3",
        )
        qualified = validate_identity_fixture(
            payload, recovered, source_readback, raw,
            project_id="test-project", repository_id="test-repository",
            consumer_id=state.consumer_id, instance_id=state.instance_id,
            submission_id=submission_id,
        )
        self.assertEqual(qualified["readback_contract_version"], "1.3")
        self.assertEqual(qualified["run_id"], "sim-run-0001")
        changed = deepcopy(recovered)
        changed["identity"]["consumer_id"] = "foreign"
        with self.assertRaisesRegex(ProducerFixtureError, "identity request binding"):
            validate_identity_fixture(
                payload, changed, source_readback, raw,
                project_id="test-project", repository_id="test-repository",
                consumer_id=state.consumer_id, instance_id=state.instance_id,
                submission_id=submission_id,
            )
        changed = deepcopy(recovered)
        changed["readback"]["disposition"]["execution_eligible"] = True
        with self.assertRaisesRegex(ProducerFixtureError, "identity terminal disposition"):
            validate_identity_fixture(
                payload, changed, source_readback, raw,
                project_id="test-project", repository_id="test-repository",
                consumer_id=state.consumer_id, instance_id=state.instance_id,
                submission_id=submission_id,
            )

    def test_listener_counts_unauthorized_get_and_post_without_simulator_audit(self) -> None:
        state = EpSimulatorState(
            project_id="test-project", repository_id="test-repository",
            repository_identity="pcvantol/forge", consumer_id="test-consumer",
            instance_id="test-instance", bearer_token="synthetic-token",
        )
        server = EpSimulatorServer(state)
        requests = _count_ep_http_requests(server)
        with server:
            for method in ("GET", "POST"):
                with self.subTest(method=method):
                    request = Request(server.base_url + "/v1/producer-compatibility", method=method)
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request, timeout=5)
                    self.assertEqual(error.exception.code, 401)
                    error.exception.close()
        self.assertEqual(requests, [
            "GET /v1/producer-compatibility", "POST /v1/producer-compatibility",
        ])
        self.assertEqual(state.audit, [])
        self.assertEqual(state.submission_ids(), ())
