"""Qualification of authenticated installed Forge read-only operations routes."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.intent import EngineeringIntent, IntentCategory, IntentReference, IntentTraceability
from forge.models.mission import EngineeringMission, MissionIntentMembership, MissionScope
from forge.operations_read_api import InstalledOperationsReadService, OperationsReadAPI, make_server
from forge.runtime import RuntimeBootstrap
from forge.state import MissionStateStore


CREDENTIAL = "synthetic-operations-credential"


class _InstalledFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "forge-server"
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.api = OperationsReadAPI(InstalledOperationsReadService(self.root), CREDENTIAL)

    def tearDown(self) -> None:
        if self.database is not None:
            self.database.close()
        self.temporary.cleanup()

    def snapshot(self) -> dict[Path, bytes]:
        return {
            path.relative_to(self.root): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file() and not path.name.endswith(("-shm", "-wal"))
        }


class TestStatusEndpoint(_InstalledFixture):
    def test_installed_status_auth_and_redaction(self) -> None:
        denied = self.api.handle("GET", "/v1/status", None)
        wrong = self.api.handle("GET", "/v1/status", "Bearer " + CREDENTIAL + "-wrong")
        before = self.snapshot()
        accepted = self.api.handle("GET", "/v1/status", "Bearer " + CREDENTIAL)

        self.assertEqual((denied.status, wrong.status, accepted.status), (401, 401, 200))
        self.assertEqual(accepted.body["availability"], "AVAILABLE")
        self.assertTrue(accepted.body["read_only"])
        rendered = json.dumps((denied.body, wrong.body, accepted.body), sort_keys=True)
        self.assertNotIn(CREDENTIAL, rendered)
        self.assertNotIn("credential_reference", rendered.lower())
        self.assertEqual(self.snapshot(), before)

    def test_stale_and_unavailable_statuses_are_explicit(self) -> None:
        with self.database._connection:  # noqa: SLF001 - controlled stale fixture
            self.database._connection.execute(  # noqa: SLF001
                "UPDATE runtime_metadata SET value = '2020-01-01T00:00:00Z' WHERE key = 'last_access_at'"
            )
        stale = self.api.handle("GET", "/v1/status", "Bearer " + CREDENTIAL)
        self.assertEqual(stale.status, 200)
        self.assertEqual(stale.body["freshness"], "STALE")

        self.database.close()
        self.database = None
        (self.root / "forge.db").write_bytes(b"unavailable")
        unavailable = self.api.handle("GET", "/v1/status", "Bearer " + CREDENTIAL)
        self.assertEqual(unavailable.status, 503)
        self.assertEqual(unavailable.body["availability"], "UNAVAILABLE")
        self.assertEqual(unavailable.body["freshness"], "UNAVAILABLE")


class TestMissionEndpoint(_InstalledFixture):
    def test_mission_lineage_read_only(self) -> None:
        criterion = "Report approved criteria, Actions, and evidence lineage"
        mission = ArchitectureMission(
            id="MISSION-0042", candidate_id="CANDIDATE-0042", title="Read-only projection",
            summary="Expose lineage", business_objective="Make Mission state observable",
            business_value="Support local operations", architecture_review_reference="review-0042",
            mission_recommendation_reference="recommendation-0042",
            acceptance_criteria=(criterion,),
            status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
        )
        reference = IntentReference("source", "1", "docs/source.md")
        intent = EngineeringIntent(
            "INTENT-0042", "1", "Projection", "Project existing state",
            IntentCategory.IMPLEMENTATION,
            IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)),
        )
        action = EngineeringAction(
            1, "ACTION-0042", intent.id, "1", "Observe read-only state", ("projection",),
            status=EngineeringActionStatus.READY,
        )
        states = MissionStateStore(self.database, data_root=str(self.root))
        state = states.create(mission, (intent,), (action,), occurred_at="2026-09-21T05:00:00Z")
        state = replace(
            state,
            repository_truth={
                "source_id": "repository-truth-0042", "revision": "a" * 40,
                "locator": "repository://pcvantol/forge", "content_digest": "sha256:" + "b" * 64,
            },
            execution_history=({
                "correlation_id": "correlation-0042", "host_run_id": "run-0042",
                "report_id": "report-0042", "receipt_id": "receipt-0042", "outcome": "WAITING",
                "retry_of_correlation_id": None,
                "repository_evidence": {
                    "mission_id": "MISSION-0042", "intent_id": "INTENT-0042", "intent_revision": "1",
                    "action_id": "ACTION-0042", "runtime_prompt_id": "prompt-0042",
                    "correlation_id": "correlation-0042", "host_run_id": "run-0042",
                    "repository_id": "pcvantol/forge", "repository_revision": "a" * 40,
                    "report_id": "report-0042", "content_digest": "sha256:" + "c" * 64,
                },
            },),
        )
        self.database.save_mission_state(state)
        self.database.close()
        self.database = None
        before = self.snapshot()

        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 200)
        self.assertTrue(response.body["read_only"])
        self.assertEqual(response.body["mission"]["mission_id"], "MISSION-0042")
        self.assertEqual(response.body["mission"]["action_ids"], ["ACTION-0042"])
        self.assertEqual(response.body["mission"]["repository_revision"], "a" * 40)
        self.assertEqual(response.body["mission"]["execution_attempts"][0]["receipt_id"], "receipt-0042")
        self.assertEqual(response.body["mission"]["criteria"], [criterion])
        self.assertEqual(response.body["mission"]["actions"], [action.to_dict()])
        lineage = response.body["mission"]["evidence_lineage"]
        self.assertEqual(lineage["repository_truth"]["content_digest"], "sha256:" + "b" * 64)
        self.assertEqual(lineage["execution_attempts"][0]["report_id"], "report-0042")
        self.assertEqual(
            lineage["execution_attempts"][0]["repository_evidence"]["action_id"], "ACTION-0042",
        )
        self.assertEqual(self.snapshot(), before)

    def test_missing_and_inconsistent_mission_states_are_explicit(self) -> None:
        missing = self.api.handle("GET", "/v1/missions/MISSION-404", "Bearer " + CREDENTIAL)
        self.assertEqual(missing.status, 404)
        self.assertEqual(missing.body["error"]["code"], "MISSION_MISSING")

        mission = EngineeringMission(
            "MISSION-0042", "1", "Read-only projection", "Expose lineage",
            MissionScope(("projection",), ("mutation",)),
            (MissionIntentMembership(1, "INTENT-0042", "1"),),
        )
        reference = IntentReference("source", "1", "docs/source.md")
        intent = EngineeringIntent(
            "INTENT-0042", "1", "Projection", "Project existing state",
            IntentCategory.IMPLEMENTATION,
            IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)),
        )
        action = EngineeringAction(1, "ACTION-0042", intent.id, "1", "Observe", ("projection",))
        MissionStateStore(self.database, data_root=str(self.root)).create(
            mission, (intent,), (action,), occurred_at="2026-09-21T05:00:00Z",
        )
        row = self.database._connection.execute(  # noqa: SLF001 - deliberate corruption boundary
            "SELECT document FROM mission_state WHERE mission_id = 'MISSION-0042'"
        ).fetchone()
        document = json.loads(row[0])
        document["mission"]["id"] = "MISSION-CONFLICT"
        with self.database._connection:  # noqa: SLF001 - deliberate corruption boundary
            self.database._connection.execute(  # noqa: SLF001
                "UPDATE mission_state SET document = ? WHERE mission_id = 'MISSION-0042'",
                (json.dumps(document, sort_keys=True),),
            )
        ambiguous = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(ambiguous.status, 409)
        self.assertEqual(ambiguous.body["error"]["code"], "MISSION_AMBIGUOUS")

    def test_mutating_methods_are_rejected_without_runtime_changes(self) -> None:
        before = self.snapshot()
        response = self.api.handle("POST", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 405)
        self.assertEqual(self.snapshot(), before)


class TestHTTPTransport(_InstalledFixture):
    def test_loopback_server_applies_the_same_authentication_boundary(self) -> None:
        server = make_server("127.0.0.1", 0, self.api)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/v1/status"
        try:
            with self.assertRaises(HTTPError) as denied:
                urlopen(url, timeout=2)
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
            request = Request(url, headers={"Authorization": "Bearer " + CREDENTIAL})
            with urlopen(request, timeout=2) as response:
                body = json.load(response)
            self.assertEqual(body["availability"], "AVAILABLE")
            self.assertTrue(body["read_only"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


class TestTransportContract(unittest.TestCase):
    def test_openapi_and_postman_cover_the_implemented_read_routes(self) -> None:
        contract_root = Path(__file__).parents[1] / "forge" / "api"
        openapi = json.loads((contract_root / "operations-read-openapi-v1.json").read_text(encoding="utf-8"))
        postman = json.loads((contract_root / "operations-read-postman-v1.json").read_text(encoding="utf-8"))

        self.assertEqual(set(openapi["paths"]), {"/v1/status", "/v1/missions/{mission_id}"})
        self.assertTrue(all(set(value) == {"get"} for value in openapi["paths"].values()))
        self.assertEqual(set(openapi["paths"]["/v1/status"]["get"]["responses"]), {"200", "401", "503"})
        self.assertEqual(
            set(openapi["paths"]["/v1/missions/{mission_id}"]["get"]["responses"]),
            {"200", "400", "401", "404", "409", "503"},
        )
        requests = postman["item"]
        self.assertTrue(all(item["request"]["method"] == "GET" for item in requests))
        self.assertEqual(
            {response["code"] for item in requests for response in item["response"]},
            {200, 400, 401, 404, 409, 503},
        )
        self.assertTrue(any(item["request"]["url"].endswith("/v1/status") for item in requests))
        self.assertTrue(any("/v1/missions/" in item["request"]["url"] for item in requests))
