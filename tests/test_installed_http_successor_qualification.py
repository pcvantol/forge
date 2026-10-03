"""Guard the installed qualifier's observation of rejected EP HTTP traffic."""

from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from forge.ep_simulator import EpSimulatorServer, EpSimulatorState
from forge.qualification.producer_fixture_conformance import (
    ProducerFixtureError, rejection_matrix, source_receipt, validate_fixture,
)
from scripts.qualification.qualify_installed_http_successor import _count_ep_http_requests


class InstalledHttpSuccessorQualificationTests(unittest.TestCase):
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
        self.assertEqual(requests, ["GET", "POST"])
        self.assertEqual(state.audit, [])
        self.assertEqual(state.submission_ids(), ())
