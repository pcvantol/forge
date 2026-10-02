"""Durable PA-F1 intent registration without execution or host effects."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

from forge.runtime import RuntimeBootstrap, RuntimeDatabaseError, RUNTIME_SCHEMA_VERSION
from forge.runtime.action_intents import ActionIntentError, ActionIntentLedger


MISSION_ID = "MISSION-FIXTURE-1"
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


class ActionIntentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "installed"
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.addCleanup(self.database.close)
        self.graph = json.loads(Path("forge/api/parallel-action-peer-graph-v1.json").read_text())
        self.state = {
            "mission_id": MISSION_ID,
            "mission": {"id": MISSION_ID, "status": "approved_for_engineering",
                        "scope": ["repository-a", "repository-b"]},
            "revision": 1,
            "actions": [{"id": action["action_id"], "dependencies": [
                edge["predecessor_action_id"] for edge in action["dependencies"]
            ]} for action in self.graph["actions"]],
            "status": "READY", "lifecycle": "READY", "progress": {}, "resume": {},
            "execution_policy": {"mode": "serial"},
        }
        self.database.create_mission_state(self.state)
        self.database.record_mission_action_slots(self.graph)

    def _rows(self) -> list[sqlite3.Row]:
        return self.database._connection.execute(  # noqa: SLF001 - controlled storage evidence
            "SELECT * FROM mission_action_intent_revisions ORDER BY action_id,slot_revision"
        ).fetchall()

    def test_materialize_bind_independently_replay_and_restart(self) -> None:
        initial = self.database.materialize_action_intents(MISSION_ID)
        self.assertEqual(RUNTIME_SCHEMA_VERSION, 43)
        self.assertEqual([item["action_id"] for item in initial["actions"]],
                         ["ACTION-A", "ACTION-B", "ACTION-Q"])
        self.assertEqual([item["target"]["repository_id"] for item in initial["actions"]],
                         ["repository-a", "repository-b", "repository-a"])
        self.assertTrue(all(item["correlation_status"] == "UNBOUND" for item in initial["actions"]))
        self.assertTrue(all(item["target_verification"] == "UNVERIFIED" for item in initial["actions"]))
        self.assertFalse(initial["dispatch_authorized"])
        self.assertEqual(self.database.materialize_action_intents(MISSION_ID), initial)

        a = self.database.bind_action_intent(
            MISSION_ID, "ACTION-A", expected_slot_revision=1,
            correlation_id="correlation-A", request_digest=DIGEST_A,
        )
        b = self.database.bind_action_intent(
            MISSION_ID, "ACTION-B", expected_slot_revision=1,
            correlation_id="correlation-B", request_digest=DIGEST_B,
        )
        self.assertEqual((a["slot_revision"], b["slot_revision"]), (2, 2))
        self.assertEqual(self.database.bind_action_intent(
            MISSION_ID, "ACTION-A", expected_slot_revision=1,
            correlation_id="correlation-A", request_digest=DIGEST_A,
        ), a)
        self.assertEqual(len(self._rows()), 5)
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        after = self.database.read_action_intents(MISSION_ID)
        self.assertEqual({item["action_id"]: item["correlation_status"] for item in after["actions"]},
                         {"ACTION-A": "BOUND", "ACTION-B": "BOUND", "ACTION-Q": "UNBOUND"})
        self.assertEqual(after["actions"][0]["request_digest"], DIGEST_A)
        self.assertEqual(after["source_freshness"], "CURRENT")
        self.assertFalse(after["dispatch_authorized"])

    def test_cas_and_correlation_conflicts_leave_other_slots_untouched(self) -> None:
        self.database.materialize_action_intents(MISSION_ID)
        self.database.bind_action_intent(
            MISSION_ID, "ACTION-A", expected_slot_revision=1,
            correlation_id="same-correlation", request_digest=DIGEST_A,
        )
        before = [tuple(row) for row in self._rows()]
        for kwargs in (
            {"expected_slot_revision": 2, "correlation_id": "other", "request_digest": DIGEST_A},
            {"expected_slot_revision": 1, "correlation_id": "same-correlation", "request_digest": DIGEST_B},
        ):
            with self.assertRaises(RuntimeDatabaseError):
                self.database.bind_action_intent(MISSION_ID, "ACTION-A", **kwargs)
        with self.assertRaises(RuntimeDatabaseError):
            self.database.bind_action_intent(
                MISSION_ID, "ACTION-B", expected_slot_revision=1,
                correlation_id="same-correlation", request_digest=DIGEST_B,
            )
        self.assertEqual([tuple(row) for row in self._rows()], before)

    def test_stale_mission_and_changed_source_fail_without_new_rows(self) -> None:
        self.database.materialize_action_intents(MISSION_ID)
        changed = {**self.state, "revision": 2}
        self.database.save_mission_state(changed)
        with self.assertRaises(RuntimeDatabaseError):
            self.database.bind_action_intent(
                MISSION_ID, "ACTION-A", expected_slot_revision=1,
                correlation_id="stale", request_digest=DIGEST_A,
            )
        with self.assertRaises(RuntimeDatabaseError):
            self.database.materialize_action_intents(MISSION_ID)
        self.assertEqual(self.database.read_action_intents(MISSION_ID)["source_freshness"], "STALE")
        self.assertEqual(len(self._rows()), 3)

    def test_same_revision_graph_drift_fails_closed(self) -> None:
        changed = json.loads(json.dumps(self.state))
        changed["actions"][2]["dependencies"] = ["ACTION-A"]
        self.database.save_mission_state(changed)
        with self.assertRaises(RuntimeDatabaseError):
            self.database.materialize_action_intents(MISSION_ID)
        self.assertEqual(self._rows(), [])

    def test_partial_insert_rolls_back_all_actions(self) -> None:
        with self.database._connection:  # noqa: SLF001 - controlled fault injection
            self.database._connection.execute(  # noqa: SLF001
                "CREATE TRIGGER block_action_b BEFORE INSERT ON mission_action_intent_revisions "
                "WHEN NEW.action_id='ACTION-B' BEGIN SELECT RAISE(ABORT, 'blocked'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.materialize_action_intents(MISSION_ID)
        self.assertEqual(self._rows(), [])

    def test_two_connections_cannot_bind_the_same_slot_twice(self) -> None:
        self.database.materialize_action_intents(MISSION_ID)
        barrier = Barrier(2)
        connections = [sqlite3.connect(self.database.path, timeout=10, check_same_thread=False)
                       for _ in range(2)]
        for connection in connections:
            connection.row_factory = sqlite3.Row
        self.addCleanup(lambda: [connection.close() for connection in connections])

        def compete(index: int) -> str:
            try:
                barrier.wait(timeout=10)
                ActionIntentLedger(connections[index]).bind(
                    MISSION_ID, "ACTION-A", expected_slot_revision=1,
                    correlation_id=("first", "second")[index], request_digest=DIGEST_A,
                )
                return "BOUND"
            except ActionIntentError:
                return "CONFLICT"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = sorted(pool.map(compete, (0, 1)))
        self.assertEqual(outcomes, ["BOUND", "CONFLICT"])
        self.assertEqual(len(self._rows()), 4)

    def test_schema42_migrates_without_replaying_or_changing_mission(self) -> None:
        before = self.database.get_document("mission_state", MISSION_ID)
        self.database.close()
        with sqlite3.connect(self.root / "forge.db") as connection:
            for operation in ("insert", "update", "delete"):
                connection.execute(
                    f"DROP TRIGGER operational_reset_block_mission_action_intent_revisions_{operation}"
                )
            for operation in ("update", "delete"):
                connection.execute(f"DROP TRIGGER mission_action_intent_revisions_immutable_{operation}")
            connection.execute("DROP TABLE mission_action_intent_revisions")
            connection.execute("UPDATE runtime_metadata SET value='42' "
                               "WHERE key IN ('schema_version','migration_version','last_migration')")
            connection.execute("PRAGMA user_version=42")
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.assertEqual(self.database.get_document("mission_state", MISSION_ID), before)
        self.assertEqual(self.database.metadata["schema_version"], "43")
        self.assertEqual(self.database.read_action_intents(MISSION_ID)["actions"], [])
        self.assertEqual(len(self.database.materialize_action_intents(MISSION_ID)["actions"]), 3)

    def test_existing_serial_migration_is_preserved_and_never_replayed(self) -> None:
        state = json.loads(json.dumps(self.state))
        for action in state["actions"]:
            action["status"] = "READY"
        state["actions"][0]["status"] = "WAITING_FOR_RESULT"
        state["execution_correlation"] = {
            "request": {"mission_id": MISSION_ID, "action_id": "ACTION-A",
                        "correlation_id": "legacy-A", "runtime_prompt": "synthetic-private-bytes"},
            "host_run_id": "legacy-run-A",
        }
        self.database.save_mission_state(state)
        self.database.migrate_legacy_serial_execution_slot(MISSION_ID)
        connection = self.database._connection  # noqa: SLF001 - exact historical bytes
        before = connection.execute(
            "SELECT document FROM mission_action_execution_slots WHERE mission_id=?", (MISSION_ID,)
        ).fetchone()[0]
        with self.assertRaises(RuntimeDatabaseError):
            self.database.materialize_action_intents(MISSION_ID)
        self.assertEqual(self._rows(), [])
        self.assertEqual(connection.execute(
            "SELECT document FROM mission_action_execution_slots WHERE mission_id=?", (MISSION_ID,)
        ).fetchone()[0], before)
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.assertEqual(self.database._connection.execute(  # noqa: SLF001
            "SELECT document FROM mission_action_execution_slots WHERE mission_id=?", (MISSION_ID,)
        ).fetchone()[0], before)

    def test_corrupt_digest_is_not_read_as_valid_intent(self) -> None:
        self.database.materialize_action_intents(MISSION_ID)
        with self.database._connection:  # noqa: SLF001 - controlled corruption fixture
            self.database._connection.execute(  # noqa: SLF001
                "DROP TRIGGER mission_action_intent_revisions_immutable_update"
            )
            self.database._connection.execute(  # noqa: SLF001
                "UPDATE mission_action_intent_revisions SET document_digest=? "
                "WHERE action_id='ACTION-A'", ("sha256:" + "0" * 64,)
            )
        with self.assertRaises(RuntimeDatabaseError):
            self.database.read_action_intents(MISSION_ID)

    def test_unapproved_or_out_of_scope_mission_cannot_create_intents(self) -> None:
        cases = (
            {"mission": {**self.state["mission"], "status": "draft"}},
            {"mission": {**self.state["mission"], "scope": ["repository-a"]}},
            {"mission": {**self.state["mission"], "scope": ["repository-a", "repository-a"]}},
            {"actions": self.state["actions"][:-1]},
        )
        for change in cases:
            with self.subTest(change=change):
                self.database.save_mission_state({**self.state, **change})
                with self.assertRaises(RuntimeDatabaseError):
                    self.database.materialize_action_intents(MISSION_ID)
                self.assertEqual(self._rows(), [])

    def test_binding_requires_existing_action_and_valid_correlation(self) -> None:
        self.database.materialize_action_intents(MISSION_ID)
        for action_id, correlation, digest in (
            ("MISSING", "request-1", DIGEST_A),
            ("ACTION-A", "Bearer secret", DIGEST_A),
            ("ACTION-A", "request-1", "raw-payload"),
        ):
            with self.subTest(action_id=action_id, correlation=correlation):
                with self.assertRaises(RuntimeDatabaseError):
                    self.database.bind_action_intent(
                        MISSION_ID, action_id, expected_slot_revision=1,
                        correlation_id=correlation, request_digest=digest,
                    )
        self.assertEqual(len(self._rows()), 3)

    def test_corrupt_target_and_history_fail_closed_on_read_and_replay(self) -> None:
        self.database.materialize_action_intents(MISSION_ID)
        connection = self.database._connection  # noqa: SLF001 - isolated corruption fixture
        with connection:
            connection.execute("DROP TRIGGER mission_action_intent_revisions_immutable_update")
            row = connection.execute(
                "SELECT * FROM mission_action_intent_revisions WHERE action_id='ACTION-A'"
            ).fetchone()
            document = json.loads(row["document"])
            document["target"]["repository_id"] = "repository-b"
            encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            from hashlib import sha256
            connection.execute(
                "UPDATE mission_action_intent_revisions SET document=?,document_digest=? "
                "WHERE action_id='ACTION-A'",
                (encoded, "sha256:" + sha256(encoded.encode()).hexdigest()),
            )
        with self.assertRaises(RuntimeDatabaseError):
            self.database.read_action_intents(MISSION_ID)
        with self.assertRaises(RuntimeDatabaseError):
            self.database.materialize_action_intents(MISSION_ID)


if __name__ == "__main__":
    unittest.main()
