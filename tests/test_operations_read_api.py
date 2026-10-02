"""Qualification of authenticated installed Forge read-only operations routes."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from http.client import HTTPConnection
import json
from pathlib import Path
import socket
import sqlite3
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_assessment import ApprovedRepositoryEvidenceSource
from forge.models.intent import EngineeringIntent, IntentCategory, IntentReference, IntentTraceability
from forge.models.mission import EngineeringMission, MissionIntentMembership, MissionScope
from forge.execution_host_configuration import EngineeringPlatformPeerConfigurationService
from forge.operations_read_api import InstalledOperationsReadService, OperationsReadAPI, make_server
from forge.runtime import RuntimeBootstrap
from forge.runtime.database import RuntimeDatabaseError
from forge.secure_store import SecretReference
from forge.server_runtime import ForgeServerAPI, make_server as make_forge_server
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
    def test_running_read_listener_rejects_replaced_instance_root(self) -> None:
        for replacement in ("symlink", "directory"):
            with self.subTest(replacement=replacement), TemporaryDirectory() as temporary:
                base = Path(temporary)
                root_a, root_b = base / "a", base / "b"
                for root in (root_a, root_b):
                    RuntimeBootstrap(data_root=root, forge_version="test").open().close()
                other_id = (root_b / "instance" / "runtime-instance.json").read_text().strip()
                api = OperationsReadAPI(InstalledOperationsReadService(root_a), CREDENTIAL)
                server = make_server("127.0.0.1", 0, api)
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    endpoint = f"http://127.0.0.1:{server.server_port}/v1/status"
                    authorized = Request(endpoint, headers={"Authorization": "Bearer " + CREDENTIAL})
                    with urlopen(authorized, timeout=2) as response:
                        self.assertEqual(response.status, 200)
                    root_a.rename(base / "a-parked")
                    if replacement == "symlink":
                        root_a.symlink_to(root_b, target_is_directory=True)
                    else:
                        root_b.rename(root_a)
                    with self.assertRaises(HTTPError) as unavailable:
                        urlopen(authorized, timeout=2)
                    self.assertEqual(unavailable.exception.code, 503)
                    payload = unavailable.exception.read()
                    self.assertEqual(json.loads(payload)["error"]["code"], "INSTANCE_UNAVAILABLE")
                    self.assertNotIn(other_id.encode(), payload)
                    unavailable.exception.close()
                    with self.assertRaises(HTTPError) as denied:
                        urlopen(Request(endpoint), timeout=2)
                    self.assertEqual(denied.exception.code, 401)
                    denied.exception.close()
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)

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

    def test_future_runtime_timestamp_is_fail_closed(self) -> None:
        with self.database._connection:  # noqa: SLF001 - controlled clock-skew fixture
            self.database._connection.execute(  # noqa: SLF001
                "UPDATE runtime_metadata SET value = '2099-01-01T00:00:00Z' WHERE key = 'last_access_at'"
            )

        response = self.api.handle("GET", "/v1/status", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["freshness"], "STALE")

    def test_failed_installed_runtime_validation_is_unavailable(self) -> None:
        marker = self.root / "instance" / "runtime-instance.json"
        marker.write_text("different-runtime\n", encoding="utf-8")
        before = self.snapshot()

        response = self.api.handle("GET", "/v1/status", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 503)
        self.assertEqual(response.body["availability"], "UNAVAILABLE")
        self.assertEqual(response.body["freshness"], "UNAVAILABLE")
        self.assertEqual(response.body["runtime"]["execution_host_peer"]["status"], "ERROR")
        self.assertEqual(self.snapshot(), before)

    def test_absent_runtime_is_unavailable_without_initialization(self) -> None:
        with TemporaryDirectory() as temporary:
            path_credential = "ghp_" + "syntheticvalue"
            absent_root = Path(temporary) / path_credential
            api = OperationsReadAPI(InstalledOperationsReadService(absent_root), CREDENTIAL)

            response = api.handle("GET", "/v1/status", "Bearer " + CREDENTIAL)

            self.assertEqual(response.status, 503)
            self.assertEqual(response.body["availability"], "UNAVAILABLE")
            self.assertEqual(response.body["freshness"], "UNAVAILABLE")
            self.assertFalse(response.body["runtime"]["initialized"])
            self.assertEqual(response.body["runtime"]["runtime_status"], "uninitialized")
            self.assertNotIn(path_credential, json.dumps(response.body, sort_keys=True))
            self.assertFalse(absent_root.exists())


class TestProjectRoadmapEndpoint(_InstalledFixture):
    def configure_project(self, project_id: str = "forge-project", *, replace: bool = False,
                          expected_revision: int | None = None,
                          expected_digest: str | None = None):
        return EngineeringPlatformPeerConfigurationService(self.root).configure(
            binding_id="ep-primary", endpoint="https://ep.test",
            expected_ep_instance_id="ep-instance-1", ep_consumer_id="forge-consumer-1",
            execution_host_id="engineering-platform", ep_project_id=project_id,
            ep_repository_id="forge-repository", repository_identity="forge-source",
            credential_reference=SecretReference.parse("keychain://forge.ep/consumer"),
            operator_id="local-admin", occurred_at="2026-09-10T18:00:00Z",
            replace=replace, expected_revision=expected_revision, expected_digest=expected_digest,
        )

    def create_mission(self, number: str = "0042") -> None:
        mission = ArchitectureMission(
            id=f"MISSION-{number}", candidate_id=f"CANDIDATE-{number}", title="Read project",
            summary="Project existing work", business_objective="Show actual project work",
            business_value="Read-only overview", architecture_review_reference=f"review-{number}",
            mission_recommendation_reference=f"recommendation-{number}", scope=("forge-repository",),
            status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
            repository_evidence_source=ApprovedRepositoryEvidenceSource("forge-repository", "pcvantol/forge"),
        )
        reference = IntentReference("source", "1", "docs/source.md")
        intent = EngineeringIntent(
            f"INTENT-{number}", "1", "Projection", "Read the existing DAG",
            IntentCategory.IMPLEMENTATION,
            IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)),
        )
        first = EngineeringAction(1, f"ACTION-{number}-A", intent.id, "1", "Read", ("proof",))
        second = EngineeringAction(2, f"ACTION-{number}-B", intent.id, "1", "Project", ("proof",),
                                   dependencies=(first.id,))
        MissionStateStore(self.database, data_root=str(self.root)).create(
            mission, (intent,), (first, second), occurred_at="2026-09-21T05:00:00Z",
        )

    def test_durable_action_slots_replay_restart_readback_and_stale_revision(self) -> None:
        self.create_mission()
        graph = self._slot_graph()
        receipt = self.database.record_mission_action_slots(graph)
        self.assertEqual(self.database.record_mission_action_slots(graph), receipt)
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        slots = response.body["mission"]["planning_slots"]
        self.assertEqual(slots["freshness"], "CURRENT")
        self.assertEqual(slots["document_digest"], receipt["document_digest"])
        self.assertFalse(slots["dispatch_authorized"])
        self.assertEqual([item["action_id"] for item in slots["actions"]],
                         ["ACTION-0042-A", "ACTION-0042-B"])
        self.assertEqual(slots["selected_binding_resolution"], "UNCONFIGURED")
        self.assertTrue(all(item["selected_binding_resolution"] == "UNCONFIGURED"
                            for item in slots["actions"]))
        frontier = response.body["mission"]["action_frontier"]
        self.assertEqual(frontier["source_slot_digest"], receipt["document_digest"])
        self.assertEqual([item["target_resolution"] for item in frontier["actions"]],
                         ["PINNED_UNVERIFIED"] * 2)
        self.assertEqual([item["selected_binding_resolution"] for item in frontier["actions"]],
                         ["UNCONFIGURED"] * 2)
        with self.database._connection:  # noqa: SLF001 - simulated later Mission revision
            row = self.database._connection.execute(  # noqa: SLF001
                "SELECT document FROM mission_state WHERE mission_id='MISSION-0042'"
            ).fetchone()
            state = json.loads(row[0])
            state["revision"] = 2
            self.database._connection.execute(  # noqa: SLF001
                "UPDATE mission_state SET document=? WHERE mission_id='MISSION-0042'",
                (json.dumps(state),),
            )
        stale = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(stale.body["mission"]["planning_slots"]["freshness"], "STALE")
        self.assertEqual(stale.body["mission"]["planning_slots"]["selected_binding_resolution"], "STALE")
        self.assertIsNone(stale.body["mission"]["action_frontier"]["source_slot_digest"])
        self.assertTrue(all(item["target_resolution"] == "UNAVAILABLE"
                            for item in stale.body["mission"]["action_frontier"]["actions"]))
        self.configure_project()
        stale_with_binding = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(stale_with_binding.body["mission"]["planning_slots"]["selected_binding_resolution"], "STALE")
        with self.assertRaisesRegex(RuntimeDatabaseError, "current approved Mission revision"):
            self.database.record_mission_action_slots(graph)

    def test_action_slots_resolve_only_exact_selected_binding_without_dispatch(self) -> None:
        self.create_mission()
        self.database.record_mission_action_slots(self._slot_graph())
        self.configure_project()
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        before = self.snapshot()

        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 200)
        slots = response.body["mission"]["planning_slots"]
        self.assertEqual(slots["selected_binding_resolution"], "MATCHED_SELECTED_BINDING")
        self.assertEqual([item["selected_binding_resolution"] for item in slots["actions"]],
                         ["MATCHED_SELECTED_BINDING"] * 2)
        self.assertTrue(all(item["baseline_verification"] == "UNVERIFIED" for item in slots["actions"]))
        self.assertEqual(slots["target_verification"], "UNVERIFIED")
        self.assertFalse(slots["dispatch_authorized"])
        frontier = response.body["mission"]["action_frontier"]
        self.assertEqual(frontier["source_slot_digest"], slots["document_digest"])
        self.assertEqual([item["target_repository_id"] for item in frontier["actions"]],
                         ["forge-repository"] * 2)
        self.assertEqual([item["selected_binding_resolution"] for item in frontier["actions"]],
                         ["MATCHED_SELECTED_BINDING"] * 2)
        self.assertTrue(all(item["target_resolution"] == "PINNED_UNVERIFIED"
                            and item["baseline_verification"] == "UNVERIFIED"
                            and not item["dispatchable"] for item in frontier["actions"]))
        self.assertNotIn("keychain://", json.dumps(response.body))
        self.assertNotIn("https://ep.test", json.dumps(response.body))
        self.assertEqual(self.snapshot(), before)

        wrong = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer wrong")
        self.assertEqual(wrong.status, 401)

        with self.database._connection:  # noqa: SLF001 - synthetic config corruption
            self.database._connection.execute(  # noqa: SLF001
                "UPDATE execution_host_peer_configuration SET configuration_digest=? WHERE singleton=1",
                ("sha256:" + "0" * 64,),
            )
        corrupt = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(corrupt.status, 503)
        self.assertNotIn("planning_slots", json.dumps(corrupt.body))
        self.assertNotIn("keychain://", json.dumps(corrupt.body))

    def test_action_slots_distinguish_mismatch_and_mixed_binding(self) -> None:
        self.create_mission()
        graph = self._slot_graph()
        graph["actions"][1]["target"]["project_id"] = "other-project"
        self.database.record_mission_action_slots(graph)
        old = self.configure_project()
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        slots = response.body["mission"]["planning_slots"]
        self.assertEqual(slots["selected_binding_resolution"], "MIXED")
        self.assertEqual([item["selected_binding_resolution"] for item in slots["actions"]],
                         ["MATCHED_SELECTED_BINDING", "MISMATCH"])
        self.assertEqual([item["selected_binding_resolution"] for item in
                          response.body["mission"]["action_frontier"]["actions"]],
                         ["MATCHED_SELECTED_BINDING", "MISMATCH"])
        self.assertFalse(slots["dispatch_authorized"])

        self.configure_project("different-project", replace=True,
                               expected_revision=old.configuration_revision,
                               expected_digest=old.configuration_digest)
        rebound = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(rebound.status, 200)
        self.assertEqual(rebound.body["mission"]["planning_slots"]["selected_binding_resolution"], "MISMATCH")

    def test_action_slots_reject_conflict_scope_and_unstored_action(self) -> None:
        self.create_mission()
        graph = self._slot_graph()
        self.database.record_mission_action_slots(graph)
        changed = json.loads(json.dumps(graph))
        changed["actions"][0]["target"]["baseline_revision"] = "different"
        with self.assertRaisesRegex(RuntimeDatabaseError, "conflict"):
            self.database.record_mission_action_slots(changed)
        outside = json.loads(json.dumps(graph))
        outside["actions"][0]["target"]["repository_id"] = "other-repository"
        outside["actions"][1]["dependencies"][0]["required_evidence"]["repository_id"] = "other-repository"
        with self.assertRaisesRegex(RuntimeDatabaseError, "scope"):
            self.database.record_mission_action_slots(outside)
        missing = json.loads(json.dumps(graph))
        missing["actions"][1]["action_id"] = "ACTION-UNKNOWN"
        with self.assertRaisesRegex(RuntimeDatabaseError, "Action set"):
            self.database.record_mission_action_slots(missing)
        altered_edges = json.loads(json.dumps(graph))
        altered_edges["actions"][1]["dependencies"] = []
        with self.assertRaisesRegex(RuntimeDatabaseError, "predecessors"):
            self.database.record_mission_action_slots(altered_edges)
        count = self.database._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM mission_action_slot_snapshots"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_action_slot_writer_rejects_corrupt_current_graph_without_snapshot(self) -> None:
        self.create_mission()
        original = self.database.get_document("mission_state", "MISSION-0042")
        for change in ("duplicate_edge", "self_edge", "unknown_edge", "missing_edge",
                       "malformed_edge", "duplicate_action", "malformed_action",
                       "duplicate_scope", "empty_scope", "malformed_scope"):
            with self.subTest(change=change):
                state = json.loads(json.dumps(original))
                if change == "duplicate_edge":
                    state["actions"][1]["dependencies"] *= 2
                elif change == "self_edge":
                    state["actions"][1]["dependencies"] = ["ACTION-0042-B"]
                elif change == "unknown_edge":
                    state["actions"][1]["dependencies"] = ["ACTION-UNKNOWN"]
                elif change == "missing_edge":
                    state["actions"][1]["dependencies"] = []
                elif change == "malformed_edge":
                    state["actions"][1]["dependencies"] = [{"id": "ACTION-0042-A"}]
                elif change == "duplicate_action":
                    state["actions"][1]["id"] = "ACTION-0042-A"
                elif change == "malformed_action":
                    state["actions"][1]["id"] = {"id": "ACTION-0042-B"}
                elif change == "duplicate_scope":
                    state["mission"]["scope"].append("forge-repository")
                elif change == "empty_scope":
                    state["mission"]["scope"] = []
                else:
                    state["mission"]["scope"] = [{"repository_id": "forge-repository"}]
                with self.database._connection:  # noqa: SLF001 - corrupt current-state fixture
                    self.database._connection.execute(  # noqa: SLF001
                        "UPDATE mission_state SET document=? WHERE mission_id='MISSION-0042'",
                        (json.dumps(state),),
                    )
                changes = self.database._connection.total_changes  # noqa: SLF001
                with self.assertRaisesRegex(RuntimeDatabaseError, "Action slot"):
                    self.database.record_mission_action_slots(self._slot_graph())
                self.assertEqual(self.database._connection.total_changes, changes)  # noqa: SLF001
                count = self.database._connection.execute(  # noqa: SLF001
                    "SELECT COUNT(*) FROM mission_action_slot_snapshots"
                ).fetchone()[0]
                self.assertEqual(count, 0)

    def test_action_slots_reject_missing_mission_and_corrupt_readback(self) -> None:
        graph = self._slot_graph()
        with self.assertRaisesRegex(RuntimeDatabaseError, "existing Mission"):
            self.database.record_mission_action_slots(graph)
        self.create_mission()
        self.database.record_mission_action_slots(graph)
        with self.database._connection:  # noqa: SLF001 - controlled corrupt-storage fixture
            self.database._connection.execute(  # noqa: SLF001
                "UPDATE mission_action_slot_snapshots SET document_digest=? WHERE mission_id=?",
                ("sha256:" + "0" * 64, "MISSION-0042"),
            )
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 409)
        self.assertEqual(response.body["error"]["code"], "MISSION_ACTION_SLOTS_INVALID")

    def test_schema40_migration_keeps_serial_mission_without_invented_slots(self) -> None:
        self.create_mission()
        prior = self.database.get_document("mission_state", "MISSION-0042")
        self.database.close()
        with sqlite3.connect(self.root / "forge.db") as connection:
            connection.execute("DROP TABLE mission_action_slot_snapshots")
            connection.execute(
                "UPDATE runtime_metadata SET value='40' WHERE key IN "
                "('schema_version','migration_version','last_migration','database_version')"
            )
            connection.execute("PRAGMA user_version=40")
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.assertEqual(self.database.get_document("mission_state", "MISSION-0042"), prior)
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        self.assertIsNone(response.body["mission"]["planning_slots"])

    def test_schema41_migration_preserves_serial_state_without_invented_execution_slot(self) -> None:
        self.create_mission()
        state = self.database.get_document("mission_state", "MISSION-0042")
        state["actions"][0]["status"] = "WAITING_FOR_RESULT"
        state["execution_correlation"] = {
            "mission_id": "MISSION-0042", "action_id": "ACTION-0042-A",
            "correlation_id": "corr-0042", "runtime_prompt": "synthetic-private-prompt",
        }
        self.database.save_mission_state(state)
        prior = self.database.get_document("mission_state", "MISSION-0042")
        path = self.database.path
        self.database.close()
        with sqlite3.connect(path) as connection:
            connection.execute("DROP TABLE mission_action_execution_slots")
            connection.execute(
                "UPDATE runtime_metadata SET value='41' WHERE key IN "
                "('schema_version','migration_version','last_migration','database_version')"
            )
            connection.execute("PRAGMA user_version=41")
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.assertEqual(self.database.get_document("mission_state", "MISSION-0042"), prior)
        self.assertEqual(self.database._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM mission_action_execution_slots"
        ).fetchone()[0], 0)
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["mission"]["execution_slots"]["status"], "UNAVAILABLE")
        self.assertNotIn("synthetic-private-prompt", json.dumps(response.body))

    def test_installed_mission_readback_binds_only_one_legacy_correlation(self) -> None:
        self.create_mission()
        document = self.database.get_document("mission_state", "MISSION-0042")
        document["actions"][0]["status"] = "WAITING_FOR_RESULT"
        document["execution_correlation"] = {
            "request": {"mission_id": "MISSION-0042", "action_id": "ACTION-0042-A",
                        "correlation_id": "corr-0042", "runtime_prompt": "synthetic-private-prompt"},
            "host_run_id": "run-0042",
        }
        self.database.save_mission_state(document)
        before = self.snapshot()
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        serial = response.body["mission"]["serial_correlation"]
        self.assertEqual((serial["binding_status"], serial["action_id"], serial["correlation_id"]),
                         ("BOUND", "ACTION-0042-A", "corr-0042"))
        self.assertNotIn("synthetic-private-prompt", json.dumps(response.body))
        self.assertEqual(self.snapshot(), before)
        document["actions"][1]["status"] = "ACTIVE"
        self.database.save_mission_state(document)
        ambiguous = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(ambiguous.status, 200)
        self.assertEqual(ambiguous.body["mission"]["serial_correlation"]["reason"],
                         "MULTIPLE_IN_FLIGHT_ACTIONS")
        self.assertNotIn("action_id", ambiguous.body["mission"]["serial_correlation"])

    def test_serial_execution_slot_migration_replay_restart_and_private_readback(self) -> None:
        self.create_mission()
        state = self.database.get_document("mission_state", "MISSION-0042")
        state["actions"][0]["status"] = "WAITING_FOR_RESULT"
        correlation = {
            "request": {"mission_id": "MISSION-0042", "action_id": "ACTION-0042-A",
                        "correlation_id": "corr-0042", "runtime_prompt": "synthetic-private-prompt",
                        "credential_reference": "synthetic-private-credential"},
            "host_run_id": "run-0042", "receipt_id": "receipt-0042",
        }
        state["execution_correlation"] = correlation
        self.database.save_mission_state(state)
        receipt = self.database.migrate_legacy_serial_execution_slot("MISSION-0042")
        self.assertEqual(self.database.migrate_legacy_serial_execution_slot("MISSION-0042"), receipt)
        self.assertNotIn("source_digest", receipt)
        self.assertNotIn("document_digest", receipt)
        row = self.database._connection.execute(  # noqa: SLF001
            "SELECT document FROM mission_action_execution_slots WHERE mission_id='MISSION-0042'"
        ).fetchone()
        self.assertEqual(json.loads(row[0])["correlation"], correlation)
        self.assertEqual(self.database.get_document("mission_state", "MISSION-0042"), state)
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        before = self.snapshot()
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        slots = response.body["mission"]["execution_slots"]
        self.assertEqual(slots["status"], "MIGRATED")
        self.assertEqual(slots["actions"][0]["action_id"], "ACTION-0042-A")
        self.assertEqual(slots["actions"][0]["correlation_id"], "corr-0042")
        self.assertEqual(slots["actions"][0]["host_run_id"], "run-0042")
        self.assertFalse(slots["dispatch_authorized"])
        self.assertNotIn("source_digest", json.dumps(slots))
        self.assertNotIn("document_digest", json.dumps(slots))
        self.assertNotIn("synthetic-private-prompt", json.dumps(response.body))
        self.assertNotIn("synthetic-private-credential", json.dumps(response.body))
        self.assertEqual(self.snapshot(), before)
        denied = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer wrong")
        self.assertEqual(denied.status, 401)
        changed = json.loads(json.dumps(state))
        changed["execution_correlation"]["host_run_id"] = "different-run"
        self.database.save_mission_state(changed)
        with self.assertRaisesRegex(RuntimeDatabaseError, "conflicts"):
            self.database.migrate_legacy_serial_execution_slot("MISSION-0042")
        self.assertEqual(self.database._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM mission_action_execution_slots"
        ).fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database._connection.execute(  # noqa: SLF001
                "DELETE FROM mission_action_execution_slots WHERE mission_id='MISSION-0042'"
            )
        later = json.loads(json.dumps(state))
        later["revision"] = 2
        self.database.save_mission_state(later)
        with self.assertRaisesRegex(RuntimeDatabaseError, "conflicts"):
            self.database.migrate_legacy_serial_execution_slot("MISSION-0042")
        historical = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(historical.status, 200)
        self.assertEqual(historical.body["mission"]["execution_slots"]["actions"][0]["source_revision"], 1)

    def test_serial_execution_slot_migration_rejects_ambiguous_identity(self) -> None:
        self.create_mission()
        original = self.database.get_document("mission_state", "MISSION-0042")
        for change in ("absent", "ambiguous", "wrong_mission", "wrong_action",
                       "missing_correlation", "malformed_status"):
            with self.subTest(change=change):
                state = json.loads(json.dumps(original))
                state["actions"][0]["status"] = "WAITING_FOR_RESULT"
                state["execution_correlation"] = {
                    "mission_id": "MISSION-0042", "action_id": "ACTION-0042-A",
                    "correlation_id": "corr-0042",
                }
                if change == "absent":
                    state["execution_correlation"] = None
                elif change == "ambiguous":
                    state["actions"][1]["status"] = "WAITING_FOR_RESULT"
                elif change == "wrong_mission":
                    state["execution_correlation"]["mission_id"] = "MISSION-OTHER"
                elif change == "wrong_action":
                    state["execution_correlation"]["action_id"] = "ACTION-0042-B"
                elif change == "missing_correlation":
                    state["execution_correlation"].pop("correlation_id")
                elif change == "malformed_status":
                    state["actions"].pop()
                    state["actions"][0]["status"] = {"state": "WAITING_FOR_RESULT"}
                self.database.save_mission_state(state)
                changes = self.database._connection.total_changes  # noqa: SLF001
                with self.assertRaisesRegex(RuntimeDatabaseError, "unavailable or ambiguous"):
                    self.database.migrate_legacy_serial_execution_slot("MISSION-0042")
                self.assertEqual(self.database._connection.total_changes, changes)  # noqa: SLF001
                self.assertEqual(self.database._connection.execute(  # noqa: SLF001
                    "SELECT COUNT(*) FROM mission_action_execution_slots"
                ).fetchone()[0], 0)
        ambiguous = json.loads(json.dumps(original))
        ambiguous["actions"][0]["status"] = "WAITING_FOR_RESULT"
        ambiguous["actions"][1]["status"] = "WAITING_FOR_RESULT"
        ambiguous["execution_correlation"] = {
            "mission_id": "MISSION-0042", "action_id": "ACTION-0042-A",
            "correlation_id": "corr-0042",
        }
        self.database.save_mission_state(ambiguous)
        unsupported = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(unsupported.body["mission"]["execution_slots"]["status"], "UNSUPPORTED")

    def test_serial_execution_slot_corrupt_digest_fails_closed(self) -> None:
        self.create_mission()
        state = self.database.get_document("mission_state", "MISSION-0042")
        state["actions"][0]["status"] = "WAITING_FOR_RESULT"
        state["execution_correlation"] = {
            "mission_id": "MISSION-0042", "action_id": "ACTION-0042-A",
            "correlation_id": "corr-0042", "runtime_prompt": "synthetic-private-prompt",
        }
        self.database.save_mission_state(state)
        self.database.migrate_legacy_serial_execution_slot("MISSION-0042")
        with self.database._connection:  # noqa: SLF001 - corrupt-storage fixture
            self.database._connection.execute(  # noqa: SLF001
                "DROP TRIGGER mission_action_execution_slots_immutable_update"
            )
            self.database._connection.execute(  # noqa: SLF001
                "UPDATE mission_action_execution_slots SET document_digest=? WHERE mission_id=?",
                ("sha256:" + "0" * 64, "MISSION-0042"),
            )
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 409)
        self.assertEqual(response.body["error"]["code"], "MISSION_EXECUTION_SLOTS_INVALID")
        self.assertNotIn("synthetic-private-prompt", json.dumps(response.body))

    def test_same_revision_action_slot_graph_drift_fails_closed(self) -> None:
        self.create_mission()
        self.database.record_mission_action_slots(self._slot_graph())
        original = self.database.get_document("mission_state", "MISSION-0042")
        current = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(current.body["mission"]["planning_slots"]["freshness"], "CURRENT")
        for change in ("edge", "duplicate_edge", "action", "scope", "scope_expansion",
                       "duplicate_scope", "malformed_scope", "malformed_edge", "approval"):
            with self.subTest(change=change):
                state = json.loads(json.dumps(original))
                if change == "edge":
                    state["actions"][1]["dependencies"] = []
                elif change == "duplicate_edge":
                    state["actions"][1]["dependencies"] *= 2
                elif change == "action":
                    state["actions"].pop()
                elif change == "scope":
                    state["mission"]["scope"] = ["other-repository"]
                elif change == "scope_expansion":
                    state["mission"]["scope"].append("other-repository")
                elif change == "duplicate_scope":
                    state["mission"]["scope"].append("forge-repository")
                elif change == "malformed_scope":
                    state["mission"]["scope"] = [{"repository_id": "forge-repository"}]
                elif change == "malformed_edge":
                    state["actions"][1]["dependencies"] = [{"action_id": "ACTION-0042-A"}]
                else:
                    state["mission"]["status"] = "architecture_review"
                self.database.save_mission_state(state)
                before = self.snapshot()
                response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
                self.assertEqual(response.status, 409)
                self.assertEqual(response.body["error"]["code"], "MISSION_ACTION_SLOTS_DRIFT")
                self.assertNotIn("planning_slots", json.dumps(response.body))
                self.assertEqual(self.snapshot(), before)
        later = json.loads(json.dumps(original))
        later["revision"] = 2
        self.database.save_mission_state(later)
        stale = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(stale.status, 200)
        self.assertEqual(stale.body["mission"]["planning_slots"]["freshness"], "STALE")

    @staticmethod
    def _slot_graph() -> dict:
        return {
            "contract_version": "parallel-action-graph/v1", "mission_id": "MISSION-0042",
            "mission_revision": 1, "actions": [
                {"action_id": action, "target": {
                    "ep_instance_id": "ep-instance-1", "project_id": "forge-project",
                    "repository_id": "forge-repository", "baseline_revision": "baseline-1",
                }, "dependencies": [] if action.endswith("-A") else [{
                    "predecessor_action_id": "ACTION-0042-A",
                    "required_evidence": {"kind": "REPOSITORY_REVISION",
                                          "repository_id": "forge-repository",
                                          "content_digest": "sha256:" + "a" * 64},
                }]}
                for action in ("ACTION-0042-A", "ACTION-0042-B")
            ],
        }

    def test_unconfigured_project_is_empty_and_read_only(self) -> None:
        before = self.snapshot()
        denied = self.api.handle("GET", "/v1/projects", None)
        listed = self.api.handle("GET", "/v1/projects", "Bearer " + CREDENTIAL)
        detail = self.api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual((denied.status, listed.status, detail.status), (401, 200, 503))
        self.assertEqual(listed.body["availability"], "UNCONFIGURED")
        self.assertEqual(listed.body["projects"], [])
        self.assertEqual(detail.body["error"]["code"], "PROJECT_UNCONFIGURED")
        self.assertEqual(self.snapshot(), before)

    def test_configured_project_returns_actual_mission_action_graph(self) -> None:
        self.configure_project()
        empty = self.api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual(empty.body["repository_scope"]["missions"], [])
        self.assertEqual(empty.body["freshness"], "UNKNOWN")
        self.assertIsNone(empty.body["source_observed_at"])
        self.assertEqual(empty.body["repository_scope"]["active_mission_ids"], [])
        self.assertEqual(empty.body["repository_scope"]["active_mission_count"], 0)
        self.assertEqual(empty.body["repository_scope"]["active_mission_multiplicity"], "NONE")
        self.create_mission()
        before = self.snapshot()
        listed = self.api.handle("GET", "/v1/projects", "Bearer " + CREDENTIAL)
        response = self.api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual((listed.status, response.status), (200, 200))
        self.assertEqual(listed.body["projects"][0]["project_id"], "forge-project")
        self.assertEqual(response.body["project_capability_graph"], "UNAVAILABLE")
        self.assertEqual(response.body["candidate_and_expected_views"], "UNAVAILABLE")
        self.assertEqual(response.body["graph_kind"], "REPOSITORY_MISSION_ACTION_SUBSET")
        self.assertEqual(response.body["project_mission_attribution"], "UNAVAILABLE")
        self.assertEqual(response.body["repository_scope"]["missions"][0]["group"], "ACTIVE")
        self.assertEqual(response.body["repository_scope"]["active_mission_ids"], ["MISSION-0042"])
        self.assertEqual(response.body["repository_scope"]["active_mission_count"], 1)
        self.assertEqual(response.body["repository_scope"]["active_mission_multiplicity"], "SINGLE")
        self.assertEqual(response.body["repository_scope"]["missions"][0]["actions"][1]["dependencies"], ["ACTION-0042-A"])
        self.assertNotIn("keychain://", json.dumps(response.body))
        self.assertEqual(self.snapshot(), before)

    def test_project_freshness_uses_mission_transitions_not_runtime_reopen(self) -> None:
        self.configure_project()
        self.create_mission("0042")
        self.create_mission("0043")
        current = self.database.get_document("mission_state", "MISSION-0043")
        current["state_history"][-1]["occurred_at"] = "2026-10-01T19:00:00Z"
        self.database.save_mission_state(current)
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        clock = lambda: datetime(2026, 10, 1, 19, 1, tzinfo=UTC)
        api = OperationsReadAPI(InstalledOperationsReadService(self.root, clock=clock), CREDENTIAL)
        before = self.snapshot()

        response = api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 200)
        missions = response.body["repository_scope"]["missions"]
        self.assertEqual([item["freshness"] for item in missions], ["STALE", "CURRENT"])
        self.assertEqual(response.body["freshness"], "STALE")
        self.assertEqual(response.body["source_observed_at"], "2026-09-21T05:00:00Z")
        self.assertEqual(self.snapshot(), before)
        denied = api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer wrong")
        self.assertEqual(denied.status, 401)

    def test_project_freshness_missing_and_future_transition_fail_closed(self) -> None:
        self.configure_project()
        self.create_mission("0042")
        self.create_mission("0043")
        missing = self.database.get_document("mission_state", "MISSION-0042")
        missing["state_history"] = []
        self.database.save_mission_state(missing)
        future = self.database.get_document("mission_state", "MISSION-0043")
        future["state_history"][-1]["occurred_at"] = "2099-01-01T00:00:00Z"
        self.database.save_mission_state(future)
        clock = lambda: datetime(2026, 10, 1, 19, 1, tzinfo=UTC)
        api = OperationsReadAPI(InstalledOperationsReadService(self.root, clock=clock), CREDENTIAL)

        response = api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 200)
        self.assertEqual([item["freshness"] for item in response.body["repository_scope"]["missions"]],
                         ["UNKNOWN", "STALE"])
        self.assertEqual(response.body["freshness"], "UNKNOWN")
        self.assertIsNone(response.body["source_observed_at"])

        malformed = self.database.get_document("mission_state", "MISSION-0042")
        malformed["state_history"] = [{"occurred_at": "not-a-timestamp"}]
        self.database.save_mission_state(malformed)
        malformed_response = api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual(malformed_response.body["freshness"], "UNKNOWN")

        repaired = self.database.get_document("mission_state", "MISSION-0042")
        repaired["state_history"] = [{"occurred_at": "2026-10-01T19:00:00Z"}]
        self.database.save_mission_state(repaired)
        future_only = api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual(future_only.body["freshness"], "STALE")
        self.assertEqual(future_only.body["source_observed_at"], "2026-10-01T19:00:00Z")

    def test_multiple_missions_have_stable_order_without_claiming_runtime_parallelism(self) -> None:
        self.configure_project()
        self.create_mission("0043")
        self.create_mission("0042")
        response = self.api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["mission_id"] for item in response.body["repository_scope"]["missions"]],
                         ["MISSION-0042", "MISSION-0043"])
        self.assertEqual([item["group"] for item in response.body["repository_scope"]["missions"]], ["ACTIVE", "ACTIVE"])
        self.assertEqual(response.body["repository_scope"]["active_mission_ids"],
                         ["MISSION-0042", "MISSION-0043"])
        self.assertEqual(response.body["repository_scope"]["active_mission_count"], 2)
        self.assertEqual(response.body["repository_scope"]["active_mission_multiplicity"], "UNSUPPORTED_MULTIPLE")
        self.assertEqual(response.body["project_mission_attribution"], "UNAVAILABLE")

    def test_pending_and_history_do_not_inflate_repository_active_count(self) -> None:
        self.configure_project()
        self.create_mission("0042")
        self.create_mission("0043")
        self.create_mission("0044")
        pending = self.database.get_document("mission_state", "MISSION-0043")
        pending["status"] = "APPROVED_PLANNABLE"
        self.database.save_mission_state(pending)
        history = self.database.get_document("mission_state", "MISSION-0044")
        history["status"] = "COMPLETED"
        self.database.save_mission_state(history)
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        before = self.snapshot()

        response = self.api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 200)
        scope = response.body["repository_scope"]
        self.assertEqual([item["group"] for item in scope["missions"]],
                         ["ACTIVE", "APPROVED_PENDING", "HISTORY"])
        self.assertEqual(scope["active_mission_ids"], ["MISSION-0042"])
        self.assertEqual(scope["active_mission_count"], 1)
        self.assertEqual(scope["active_mission_multiplicity"], "SINGLE")
        self.assertEqual(self.snapshot(), before)

    def test_existing_mission_with_two_independent_actions_has_only_a_logical_frontier(self) -> None:
        self.create_mission()
        row = self.database._connection.execute(  # noqa: SLF001 - controlled graph fixture
            "SELECT document FROM mission_state WHERE mission_id='MISSION-0042'"
        ).fetchone()
        document = json.loads(row[0])
        document["actions"][1]["dependencies"] = []
        self.database._connection.execute(  # noqa: SLF001
            "UPDATE mission_state SET document=? WHERE mission_id='MISSION-0042'", (json.dumps(document),)
        )
        self.database._connection.commit()  # noqa: SLF001
        before = self.snapshot()
        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        frontier = response.body["mission"]["action_frontier"]
        self.assertEqual(frontier["logical_frontier_action_ids"], ["ACTION-0042-A", "ACTION-0042-B"])
        self.assertTrue(all(not item["dispatchable"] for item in frontier["actions"]))
        self.assertEqual(frontier["parallel_execution"], "NOT_QUALIFIED")
        self.assertEqual(self.snapshot(), before)

    def test_same_repository_project_rebind_does_not_claim_mission_membership(self) -> None:
        old = self.configure_project()
        self.create_mission()
        self.configure_project("new-project", replace=True,
                               expected_revision=old.configuration_revision,
                               expected_digest=old.configuration_digest)
        response = self.api.handle("GET", "/v1/projects/new-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body["project_id"], "new-project")
        self.assertNotIn("missions", response.body)
        self.assertEqual(response.body["project_mission_attribution"], "UNAVAILABLE")
        self.assertEqual(response.body["repository_scope"]["missions"][0]["mission_id"], "MISSION-0042")

    def test_wrong_project_malformed_reference_and_method_fail_closed(self) -> None:
        self.configure_project()
        auth = "Bearer " + CREDENTIAL
        wrong = self.api.handle("GET", "/v1/projects/other/roadmap", auth)
        malformed = self.api.handle("GET", "/v1/projects/%2Fetc/roadmap", auth)
        mutation = self.api.handle("POST", "/v1/projects/forge-project/roadmap", auth)
        self.assertEqual((wrong.status, malformed.status, mutation.status), (404, 400, 405))
        self.assertEqual(wrong.body["error"]["code"], "PROJECT_MISSING")

    def test_corrupt_mission_graph_does_not_claim_a_valid_roadmap(self) -> None:
        self.configure_project()
        self.create_mission()
        row = self.database._connection.execute(  # noqa: SLF001 - controlled corruption fixture
            "SELECT document FROM mission_state WHERE mission_id='MISSION-0042'"
        ).fetchone()
        document = json.loads(row[0])
        document["actions"][1]["dependencies"] = ["ACTION-MISSING"]
        self.database._connection.execute(  # noqa: SLF001
            "UPDATE mission_state SET document=? WHERE mission_id='MISSION-0042'", (json.dumps(document),)
        )
        self.database._connection.commit()  # noqa: SLF001
        response = self.api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 409)
        self.assertEqual(response.body["error"]["code"], "PROJECT_DAG_INVALID")
        mission_response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)
        self.assertEqual(mission_response.status, 409)
        self.assertEqual(mission_response.body["error"]["code"], "MISSION_ACTION_GRAPH_INVALID")

    def test_mission_from_other_repository_is_not_attributed_to_project(self) -> None:
        self.configure_project()
        self.create_mission()
        row = self.database._connection.execute(  # noqa: SLF001 - controlled foreign-source fixture
            "SELECT document FROM mission_state WHERE mission_id='MISSION-0042'"
        ).fetchone()
        document = json.loads(row[0])
        document["mission"]["repository_evidence_source"]["repository_id"] = "other-repository"
        self.database._connection.execute(  # noqa: SLF001
            "UPDATE mission_state SET document=? WHERE mission_id='MISSION-0042'", (json.dumps(document),)
        )
        self.database._connection.commit()  # noqa: SLF001
        response = self.api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 409)
        self.assertEqual(response.body["error"]["code"], "PROJECT_AMBIGUOUS")

    def test_cyclic_action_dependencies_are_not_exposed_as_a_dag(self) -> None:
        self.configure_project()
        self.create_mission()
        row = self.database._connection.execute(  # noqa: SLF001 - controlled cycle fixture
            "SELECT document FROM mission_state WHERE mission_id='MISSION-0042'"
        ).fetchone()
        document = json.loads(row[0])
        document["actions"][0]["dependencies"] = ["ACTION-0042-B"]
        self.database._connection.execute(  # noqa: SLF001
            "UPDATE mission_state SET document=? WHERE mission_id='MISSION-0042'", (json.dumps(document),)
        )
        self.database._connection.commit()  # noqa: SLF001
        response = self.api.handle("GET", "/v1/projects/forge-project/roadmap", "Bearer " + CREDENTIAL)
        self.assertEqual(response.status, 409)
        self.assertEqual(response.body["error"]["code"], "PROJECT_DAG_INVALID")

    def test_real_forge_server_route_uses_bearer_and_read_service(self) -> None:
        self.configure_project()
        api = ForgeServerAPI(SimpleNamespace(root=self.root), CREDENTIAL)
        server = make_forge_server("127.0.0.1", 0, api)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_address[1]}/v1/projects"
            with self.assertRaises(HTTPError) as denied:
                urlopen(Request(endpoint), timeout=3)
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
            with urlopen(Request(endpoint, headers={"Authorization": "Bearer " + CREDENTIAL}), timeout=3) as response:
                document = json.load(response)
            self.assertEqual(document["projects"][0]["project_id"], "forge-project")
            self.assertTrue(document["read_only"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_real_forge_server_reads_pinned_frontier_target_without_mutation(self) -> None:
        self.create_mission()
        receipt = self.database.record_mission_action_slots(self._slot_graph())
        self.configure_project()
        before = self.snapshot()
        api = ForgeServerAPI(SimpleNamespace(root=self.root), CREDENTIAL)
        server = make_forge_server("127.0.0.1", 0, api)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_address[1]}/v1/missions/MISSION-0042"
            with self.assertRaises(HTTPError) as denied:
                urlopen(Request(endpoint), timeout=3)
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
            with urlopen(Request(endpoint, headers={"Authorization": "Bearer " + CREDENTIAL}),
                         timeout=3) as response:
                self.assertEqual(response.status, 200)
                document = json.load(response)
            frontier = document["mission"]["action_frontier"]
            self.assertEqual(frontier["source_slot_digest"], receipt["document_digest"])
            self.assertEqual([item["target_repository_id"] for item in frontier["actions"]],
                             ["forge-repository"] * 2)
            self.assertTrue(all(item["target_resolution"] == "PINNED_UNVERIFIED"
                                and not item["dispatchable"] for item in frontier["actions"]))
            self.assertEqual(frontier["parallel_execution"], "NOT_QUALIFIED")
            self.assertNotIn("keychain://", json.dumps(document))
            self.assertEqual(self.snapshot(), before)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_real_server_rejects_mutation_and_malformed_requests(self) -> None:
        api = ForgeServerAPI(SimpleNamespace(root=self.root), CREDENTIAL)
        with self.assertRaises(ValueError):
            make_forge_server("0.0.0.0", 0, api)
        with self.assertRaises(ValueError):
            make_forge_server("127.0.0.1", 65536, api)
        server = make_forge_server("127.0.0.1", 0, api)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            for body, expected in ((b"", 405), (b"{}", 405), (b"[]", 400), (b"{bad", 400)):
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request("POST", "/v1/projects", body=body,
                                   headers={"Authorization": "Bearer " + CREDENTIAL,
                                            "Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
                connection.close()
            connection = HTTPConnection("127.0.0.1", port, timeout=3)
            connection.request("HEAD", "/v1/projects", headers={"Authorization": "Bearer " + CREDENTIAL})
            response = connection.getresponse()
            self.assertEqual(response.status, 405)
            self.assertEqual(response.read(), b"")
            connection.close()
            connection = HTTPConnection("127.0.0.1", port, timeout=3)
            connection.request("GET", "/v1/status", headers={"Authorization": "Bearer " + CREDENTIAL})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertTrue(json.load(response)["read_only"])
            connection.close()
            connection = HTTPConnection("127.0.0.1", port, timeout=3)
            connection.putrequest("POST", "/v1/projects")
            connection.putheader("Authorization", "Bearer " + CREDENTIAL)
            connection.putheader("Content-Length", "invalid")
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.close()
            connection = HTTPConnection("127.0.0.1", port, timeout=3)
            connection.putrequest("POST", "/v1/projects")
            connection.putheader("Authorization", "Bearer " + CREDENTIAL)
            connection.putheader("Content-Length", "1048577")
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_real_listeners_reject_ambiguous_authorization(self) -> None:
        for server in (
            make_server("127.0.0.1", 0, self.api),
            make_forge_server("127.0.0.1", 0, ForgeServerAPI(SimpleNamespace(root=self.root), CREDENTIAL)),
        ):
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                for second in ("Bearer " + CREDENTIAL, "Bearer other-credential"):
                    connection = HTTPConnection("127.0.0.1", port, timeout=3)
                    connection.putrequest("GET", "/v1/status")
                    connection.putheader("Authorization", "Bearer " + CREDENTIAL)
                    connection.putheader("Authorization", second)
                    connection.endheaders()
                    response = connection.getresponse()
                    self.assertEqual(response.status, 400)
                    self.assertEqual(json.load(response)["error"]["code"], "REQUEST_INVALID")
                    connection.close()
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request("GET", "/v1/status", headers={"Authorization": "Bearer " + CREDENTIAL})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_real_listeners_do_not_echo_parser_request_text(self) -> None:
        forge_api = ForgeServerAPI(SimpleNamespace(root=self.root), CREDENTIAL)
        for api, server in (
            (self.api, make_server("127.0.0.1", 0, self.api)),
            (forge_api, make_forge_server("127.0.0.1", 0, forge_api)),
        ):
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.object(api, "handle", side_effect=AssertionError("parser reached application")):
                    for request_line, status in (
                        (b"GET /?token=FORGE_PARSER_LEAK EXTRA HTTP/1.1", b" 400 "),
                        (b"FORGE_PARSER_LEAK /v1/status HTTP/1.1", b" 501 "),
                    ):
                        with socket.create_connection(server.server_address, timeout=3) as raw:
                            raw.sendall(request_line + b"\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                            with raw.makefile("rb") as reply:
                                response = reply.read()
                        self.assertIn(status, response.split(b"\r\n", 1)[0])
                        self.assertNotIn(b"FORGE_PARSER_LEAK", response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_real_listeners_reject_authority_bearing_targets(self) -> None:
        forge_api = ForgeServerAPI(SimpleNamespace(root=self.root), CREDENTIAL)
        for api, server in (
            (self.api, make_server("127.0.0.1", 0, self.api)),
            (forge_api, make_forge_server("127.0.0.1", 0, forge_api)),
        ):
            service = api.service if isinstance(api, OperationsReadAPI) else api._read_api.service
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                with patch.object(service, "installed_status", wraps=service.installed_status) as status_read:
                    for target in (
                        "http://evil.example/v1/status",
                        "//evil.example/v1/status",
                        "v1/status",
                        "/v1/status#fragment",
                    ):
                        connection = HTTPConnection("127.0.0.1", port, timeout=3)
                        connection.putrequest("GET", target)
                        connection.putheader("Authorization", "Bearer " + CREDENTIAL)
                        connection.endheaders()
                        response = connection.getresponse()
                        self.assertEqual(response.status, 400, target)
                        self.assertEqual(json.load(response)["error"]["code"], "REQUEST_INVALID")
                        connection.close()
                    with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
                        raw.sendall(
                            b"GET /v1/status\xa0 HTTP/1.1\r\n"
                            b"Host: 127.0.0.1\r\n"
                            + b"Authorization: Bearer " + CREDENTIAL.encode("ascii")
                            + b"\r\nConnection: close\r\n\r\n"
                        )
                        with raw.makefile("rb") as reply:
                            self.assertIn(b" 400 ", reply.readline())
                    status_read.assert_not_called()
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request("GET", "/v1/status?view=1",
                                   headers={"Authorization": "Bearer " + CREDENTIAL})
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                response.read()
                connection.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_direct_apis_reject_control_and_backslash_targets(self) -> None:
        forge_api = ForgeServerAPI(SimpleNamespace(root=self.root), CREDENTIAL)
        for target in ("/v1/status\\evil", "/v1/status\t", "/v1/status\xa0"):
            for response in (
                self.api.handle("GET", target, "Bearer " + CREDENTIAL),
                forge_api.handle("GET", target, "Bearer " + CREDENTIAL),
            ):
                self.assertEqual(response.status, 400)
                self.assertEqual(response.body["error"]["code"], "REQUEST_INVALID")

    def test_real_forge_server_rejects_ambiguous_body_framing(self) -> None:
        api = ForgeServerAPI(SimpleNamespace(root=self.root), CREDENTIAL)
        server = make_forge_server("127.0.0.1", 0, api)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for framing in (
                (("Content-Length", "2"), ("Content-Length", "2")),
                (("Content-Length", "2"), ("Content-Length", "3")),
                (("Content-Length", "2"), ("Transfer-Encoding", "chunked")),
                (("Transfer-Encoding", "chunked"),),
                (("Content-Length", "+2"),),
                (("Content-Length", "2_0"),),
                (("Content-Length", "2x"),),
            ):
                connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
                connection.putrequest("POST", "/v1/execution-host/detach")
                connection.putheader("Authorization", "Bearer " + CREDENTIAL)
                for name, value in framing:
                    connection.putheader(name, value)
                connection.endheaders()
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                self.assertEqual(json.load(response)["error"]["code"], "REQUEST_INVALID")
                connection.close()
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
            connection.putrequest("GET", "/v1/status")
            connection.putheader("Authorization", "Bearer " + CREDENTIAL)
            connection.putheader("Transfer-Encoding", "chunked")
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
            connection.close()
            with patch.object(api, "handle", wraps=api.handle) as dispatch:
                connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
                connection.putrequest("POST", "/v1/missions/inspect")
                connection.putheader("Authorization", "Bearer " + CREDENTIAL)
                connection.putheader("Authorization", "Bearer " + CREDENTIAL)
                connection.putheader("Content-Length", "2")
                connection.endheaders(b"{}")
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
                connection.close()
                dispatch.assert_not_called()
            with patch.object(api, "handle", wraps=api.handle) as dispatch:
                connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=8)
                connection.putrequest("POST", "/v1/missions/inspect")
                connection.putheader("Authorization", "Bearer " + CREDENTIAL)
                connection.putheader("Content-Length", "3")
                connection.endheaders(b"{}")
                connection.sock.shutdown(socket.SHUT_WR)
                response = connection.getresponse()
                self.assertEqual(response.status, 400)
                response.read()
                connection.close()
                dispatch.assert_not_called()
            connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
            connection.request("GET", "/v1/status", headers={"Authorization": "Bearer " + CREDENTIAL})
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


class TestMissionEndpoint(_InstalledFixture):
    def test_mission_lineage_read_only(self) -> None:
        criterion = "Report approved criteria, Actions, and evidence lineage"
        projected_credentials = (
            "github_pat_" + "syntheticvalue",
            "ghp_" + "syntheticvalue",
            "sk-" + "synthetic-value",
            "https://operator:synthetic-password@example.test/resource",
        )
        mission = ArchitectureMission(
            id="MISSION-0042", candidate_id="CANDIDATE-0042", title="Read-only projection",
            summary="Expose lineage", business_objective="Make Mission state observable",
            business_value="Support local operations", architecture_review_reference="review-0042",
            mission_recommendation_reference="recommendation-0042",
            acceptance_criteria=(criterion, "Keep projected values safe: " + " ".join(projected_credentials)),
            status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
        )
        reference = IntentReference("source", "1", "docs/source.md")
        intent = EngineeringIntent(
            "INTENT-0042", "1", "Projection", "Project existing state",
            IntentCategory.IMPLEMENTATION,
            IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)),
        )
        action = EngineeringAction(
            1, "ACTION-0042", intent.id, "1", "Observe " + " ".join(projected_credentials), ("projection",),
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
        frontier = response.body["mission"]["action_frontier"]
        self.assertEqual(frontier["contract_version"], "parallel-action-frontier/v2")
        self.assertEqual(frontier["logical_frontier_action_ids"], ["ACTION-0042"])
        self.assertEqual(frontier["actions"][0]["target_resolution"], "UNAVAILABLE")
        self.assertFalse(frontier["actions"][0]["dispatchable"])
        self.assertEqual(frontier["parallel_execution"], "NOT_QUALIFIED")
        self.assertEqual(response.body["mission"]["repository_revision"], "a" * 40)
        self.assertEqual(response.body["mission"]["execution_attempts"][0]["receipt_id"], "receipt-0042")
        redacted_values = "[REDACTED] [REDACTED] [REDACTED] https://[REDACTED]@example.test/resource"
        self.assertCountEqual(
            response.body["mission"]["criteria"],
            [criterion, "Keep projected values safe: " + redacted_values],
        )
        expected_action = action.to_dict()
        expected_action["objective"] = "Observe " + redacted_values
        self.assertEqual(response.body["mission"]["actions"], [expected_action])
        lineage = response.body["mission"]["evidence_lineage"]
        self.assertEqual(lineage["repository_truth"]["content_digest"], "sha256:" + "b" * 64)
        self.assertEqual(lineage["execution_attempts"][0]["report_id"], "report-0042")
        self.assertEqual(
            lineage["execution_attempts"][0]["repository_evidence"]["action_id"], "ACTION-0042",
        )
        rendered = json.dumps(response.body, sort_keys=True)
        for credential in projected_credentials:
            self.assertNotIn(credential, rendered)
        self.assertIn("https://[REDACTED]@example.test/resource", rendered)
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

    def test_mission_requires_the_validated_installed_runtime(self) -> None:
        marker = self.root / "instance" / "runtime-instance.json"
        marker.write_text("different-runtime\n", encoding="utf-8")

        response = self.api.handle("GET", "/v1/missions/MISSION-0042", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 503)
        self.assertEqual(response.body["error"]["code"], "MISSION_UNAVAILABLE")

    def test_free_text_and_unknown_evidence_fields_cannot_expose_credentials(self) -> None:
        assignments = "api_key=alpha password:bravo client_secret=charlie token=delta"
        mission = ArchitectureMission(
            id="MISSION-0043", candidate_id="CANDIDATE-0043", title="Safe projection",
            summary="Expose bounded lineage", business_objective="Keep Mission state observable",
            business_value="Support local operations", architecture_review_reference="review-0043",
            mission_recommendation_reference="recommendation-0043",
            acceptance_criteria=("Never expose " + assignments,),
            status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
        )
        reference = IntentReference("source", "1", "docs/source.md")
        intent = EngineeringIntent(
            "INTENT-0043", "1", "Projection", "Project bounded state",
            IntentCategory.IMPLEMENTATION,
            IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)),
        )
        action = EngineeringAction(
            1, "ACTION-0043", intent.id, "1", "Observe " + assignments, ("evidence " + assignments,),
        )
        store = MissionStateStore(self.database, data_root=str(self.root))
        state = store.create(mission, (intent,), (action,), occurred_at="2026-09-21T05:00:00Z")
        state = replace(
            state,
            execution_history=({
                "correlation_id": "correlation-0043", "host_run_id": "run-0043",
                "report_id": "report-0043", "receipt_id": "receipt-0043", "outcome": "WAITING",
                "provider_payload": {"unmodelled": assignments},
            },),
        )
        self.database.save_mission_state(state)

        response = self.api.handle("GET", "/v1/missions/MISSION-0043", "Bearer " + CREDENTIAL)

        self.assertEqual(response.status, 200)
        rendered = json.dumps(response.body, sort_keys=True)
        for secret in ("alpha", "bravo", "charlie", "delta", "provider_payload", "unmodelled"):
            self.assertNotIn(secret, rendered)
        self.assertIn("api_key=[REDACTED]", rendered)
        self.assertIn("password:[REDACTED]", rendered)
        self.assertIn("client_secret=[REDACTED]", rendered)
        self.assertIn("token=[REDACTED]", rendered)

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

        self.assertEqual(
            set(openapi["paths"]),
            {"/v1/status", "/v1/health", "/v1/missions/{mission_id}"},
        )
        self.assertTrue(all(set(value) == {"get"} for value in openapi["paths"].values()))
        self.assertEqual(set(openapi["paths"]["/v1/status"]["get"]["responses"]), {"200", "401", "503"})
        self.assertEqual(set(openapi["paths"]["/v1/health"]["get"]["responses"]), {"200", "401", "503"})
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
        self.assertTrue(any(item["request"]["url"].endswith("/v1/health") for item in requests))
        self.assertTrue(any("/v1/missions/" in item["request"]["url"] for item in requests))
        schemas = openapi["components"]["schemas"]
        self.assertEqual(
            set(schemas),
            {"ErrorResponse", "HealthResponse", "MissionResponse", "StatusResponse"},
        )
        for path in openapi["paths"].values():
            for response in path["get"]["responses"].values():
                media = response["content"]["application/json"]
                if "oneOf" in media["schema"]:
                    self.assertTrue(all(
                        item["$ref"].startswith("#/components/schemas/")
                        for item in media["schema"]["oneOf"]
                    ))
                else:
                    self.assertRegex(media["schema"]["$ref"], r"^#/components/schemas/")
        self.assertEqual(
            openapi["components"]["schemas"]["MissionResponse"]["required"],
            ["api_version", "availability", "freshness", "source_observed_at", "read_only", "mission"],
        )
        health = openapi["components"]["schemas"]["HealthResponse"]
        self.assertFalse(health["additionalProperties"])
        self.assertEqual(set(health["required"]), set(health["properties"]))
        for name in ("liveness", "registry", "observation_provenance"):
            self.assertFalse(health["properties"][name]["additionalProperties"])
        for name in ("capabilities", "checks"):
            self.assertFalse(health["properties"][name]["items"]["additionalProperties"])
