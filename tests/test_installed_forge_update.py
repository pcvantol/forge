"""Qualification for the bounded product-owned installed Forge update."""

from __future__ import annotations

import importlib.util
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from forge.runtime import RuntimeBootstrap
from forge.runtime.operational_reset import MAINTENANCE_TABLES


SCRIPT = Path(__file__).parents[1] / "scripts" / "update_installed_forge.py"
SPEC = importlib.util.spec_from_file_location("forge_installed_update", SCRIPT)
assert SPEC and SPEC.loader
update = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = update
SPEC.loader.exec_module(update)


class InstalledForgeUpdateTests(unittest.TestCase):
    runtime_id = "forge-runtime-735b0321-c4bf-41cd-81d3-9ee00249254b"
    installation_id = "99ede979-e8b8-48ca-9174-3257778c680f"
    peer_digest = "sha256:" + "c" * 64

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data_root = self.root / "Forge Server"
        self.runtime_root = self.root / "Forge Server Runtime"
        self.runtime_root.mkdir()
        self.resolver = self.root / "bin" / "forge"
        self.resolver.parent.mkdir()
        self.resolver.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.resolver.chmod(0o755)
        self.wheel = self.root / "forge_autonomy-2.7.22-py3-none-any.whl"
        metadata = b"Metadata-Version: 2.4\nName: forge-autonomy\nVersion: 2.7.22\n\n"
        with zipfile.ZipFile(self.wheel, "w") as archive:
            archive.writestr("forge_autonomy-2.7.22.dist-info/METADATA", metadata)
        self.wheel_digest = update.file_digest(self.wheel)
        self.receipt = self.root / "release-complete.json"
        self.receipt.write_text(json.dumps({
            "state": "RELEASE_COMPLETE", "product": "forge", "component": "forge-autonomy",
            "version": "2.7.22", "source_revision": "a" * 40, "operation_id": "release-1",
            "artifacts": {"wheel": self.wheel_digest, "sdist": "sha256:" + "d" * 64},
            "qualification": {
                "exact_main_sha": "a" * 40,
                "qualification": "forge-production-distribution",
            },
        }, sort_keys=True), encoding="utf-8")
        self.request = update.UpdateRequest(
            operation_id="forge-update-2722-test-001", version="2.7.22",
            product_source="a" * 40, wheel=str(self.wheel), wheel_sha256=self.wheel_digest,
            qualification_receipt=str(self.receipt),
            qualification_receipt_sha256=update.file_digest(self.receipt),
            controller_source="b" * 40, controller_sha256=update.file_digest(SCRIPT),
            data_root=str(self.data_root), runtime_root=str(self.runtime_root),
            runtime_id=self.runtime_id, installation_id=self.installation_id,
            peer_configuration_digest=self.peer_digest,
            resolver=str(self.resolver), resolver_sha256=update.file_digest(self.resolver),
            existing_interpreter=sys.executable, existing_version="2.7.21",
            base_python=sys.executable,
        )

    def _installed_schema37(self) -> None:
        database = RuntimeBootstrap(data_root=self.data_root, forge_version="2.7.22").open()
        connection = database._connection
        self.runtime_id = database.runtime_identity.runtime_id
        self.request = update.UpdateRequest(**{
            **self.request.__dict__, "runtime_id": self.runtime_id,
        })
        connection.execute(
            "INSERT INTO runtime_metadata(key,value) VALUES ('installation_id',?)",
            (self.installation_id,),
        )
        peer_document = json.dumps({"credential_reference": "keychain://forge.ep/consumer"}, sort_keys=True)
        connection.execute(
            "INSERT INTO execution_host_peer_configuration VALUES (1,'forge-ep-primary',5,?,?)",
            (self.peer_digest, peer_document),
        )
        connection.execute(
            "INSERT INTO mission_state VALUES (?,?,?,?,?,?,?,?,?)",
            ("MISSION-0001", "COMPLETED", "COMPLETED", None, None, "{}", "{}", "{}",
             json.dumps({
                 "mission_id": "MISSION-0001", "status": "COMPLETED",
                 "budgets": {"attempts": 1, "tokens": 1000},
             })),
        )
        connection.execute(
            "INSERT INTO mission_id_allocations VALUES (?,?,?)",
            ("MISSION-0001", "2026-09-17T00:00:00Z", "test-allocation"),
        )
        connection.execute(
            "INSERT INTO architecture_reviews VALUES (?,?,?,?,?,?,?,?,?)",
            ("review-1", "MISSION-0001", "repository://forge", "[]", "low", "low", "high",
             "2026-09-17T00:00:00Z", json.dumps({"id": "review-1"})),
        )
        connection.execute(
            "INSERT INTO execution_receipts VALUES (?,?,?,?,?,?,?,?)",
            ("receipt-1", "MISSION-0001", "engineering-platform", "run-1", "report-1",
             "correlation-1", "2026-09-17T00:00:00Z", "complete"),
        )
        database._insert_governance_grant(
            "grant-1", self.installation_id, "operator-1", "MISSION_INTAKE",
            "test-provenance", "sha256:grant-1", "2026-09-17T00:00:00Z",
        )
        database._insert_governance_authority(
            self.installation_id, "operator-1", "MISSION_INTAKE", "2026-09-17T00:00:00Z",
        )
        connection.execute(
            "INSERT OR REPLACE INTO dispatcher_state VALUES (1,'IDLE',NULL,'[]',?)",
            (json.dumps({"status": "IDLE", "active_mission_id": None, "mission_sequence": []}),),
        )
        connection.commit()
        database.close()
        (self.data_root / "instance" / "runtime-instance.json").write_text(
            self.runtime_id + "\n", encoding="utf-8"
        )

        connection = sqlite3.connect(self.data_root / "forge.db")
        for (trigger,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'operational_reset_%'"
        ).fetchall():
            connection.execute(f'DROP TRIGGER "{trigger}"')
        for table in MAINTENANCE_TABLES:
            for (trigger,) in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)
            ).fetchall():
                connection.execute(f'DROP TRIGGER "{trigger}"')
        for table in reversed(MAINTENANCE_TABLES):
            connection.execute(f'DROP TABLE "{table}"')
        connection.execute(
            "UPDATE runtime_metadata SET value='37' "
            "WHERE key IN ('schema_version','migration_version','last_migration','database_version')"
        )
        connection.execute("PRAGMA user_version=37")
        connection.commit()
        connection.close()

    def _controller(self) -> object:
        return update.InstalledForgeUpdateController(
            self.request, process_reader=lambda: (),
        )

    def test_exact_release_complete_artifact_is_accepted_and_mismatch_rejected(self) -> None:
        evidence = update.validate_qualified_artifact(self.request)
        self.assertEqual(evidence["wheel_sha256"], self.wheel_digest)
        changed = update.UpdateRequest(**{**self.request.__dict__, "product_source": "f" * 40})
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "does not bind"):
            update.validate_qualified_artifact(changed)
        self.wheel.write_bytes(b"changed")
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "wheel digest"):
            update.validate_qualified_artifact(self.request)

    def test_real_schema37_to_38_migration_preserves_history_and_bindings(self) -> None:
        self._installed_schema37()
        before = update.database_snapshot(self.data_root / "forge.db")
        update.assert_selected_installation(self.request, before)
        update.assert_quiescent(before)
        backup = self.root / "backup" / "forge.sqlite3"
        backup_evidence = update._copy_sqlite_backup(self.data_root / "forge.db", backup)
        self.assertEqual(backup_evidence["integrity_check"], "ok")

        copy_root = self.root / "qualification-copy"
        (copy_root / "instance").mkdir(parents=True)
        (copy_root / "instance" / "runtime-instance.json").write_text(
            self.runtime_id + "\n", encoding="utf-8"
        )
        copied = copy_root / "forge.db"
        copied.write_bytes(backup.read_bytes())
        migrated = RuntimeBootstrap(data_root=copy_root, forge_version="2.7.22").open()
        migrated.close()
        after = update.database_snapshot(copied)
        preservation = update.verify_preservation(before, after, self.request)
        self.assertEqual(preservation["status"], "PASS")
        self.assertEqual(after["tables"]["mission_state"], before["tables"]["mission_state"])
        self.assertEqual(after["tables"]["mission_id_allocations"], before["tables"]["mission_id_allocations"])
        self.assertEqual(after["tables"]["architecture_reviews"], before["tables"]["architecture_reviews"])
        self.assertEqual(after["tables"]["execution_receipts"], before["tables"]["execution_receipts"])
        self.assertEqual(after["tables"]["governance_capability_grants"], before["tables"]["governance_capability_grants"])
        self.assertEqual(after["peer"], before["peer"])

    def test_changed_target_and_active_writer_are_blocked(self) -> None:
        self._installed_schema37()
        snapshot = update.database_snapshot(self.data_root / "forge.db")
        wrong = update.UpdateRequest(**{**self.request.__dict__, "runtime_id": "forge-runtime-wrong"})
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "different runtime"):
            update.assert_selected_installation(wrong, snapshot)
        connection = sqlite3.connect(self.data_root / "forge.db")
        connection.execute(
            "UPDATE dispatcher_state SET status='ACTIVE',active_mission_id='MISSION-0001' WHERE singleton=1"
        )
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "dispatcher"):
            update.assert_quiescent(update.database_snapshot(self.data_root / "forge.db"))

    def test_concurrent_update_lock_is_rejected(self) -> None:
        lock = self.runtime_root / "locks" / "installation-update.lock"
        with update.exclusive_lock(lock):
            with self.assertRaisesRegex(update.InstalledForgeUpdateError, "concurrent maintenance"):
                with update.exclusive_lock(lock):
                    pass

    def test_resolver_adoption_fences_without_editing_the_legacy_environment(self) -> None:
        controller = self._controller()
        state = controller._state()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.21"}):
            state = controller._adopt_resolver(state)
        self.assertTrue(self.resolver.is_symlink())
        self.assertEqual(self.resolver.resolve(), controller.legacy_entrypoint.resolve())
        legacy_bytes = controller.legacy_entrypoint.read_bytes()
        state = controller._fence(state)
        self.assertEqual(self.resolver.resolve(), controller.fenced_resolver.resolve())
        self.assertEqual(controller.legacy_entrypoint.read_bytes(), legacy_bytes)

    def test_crash_before_migration_restores_the_legacy_route(self) -> None:
        controller = self._controller()
        state = controller._state()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.21"}):
            state = controller._adopt_resolver(state)
        state = controller._fence(state)
        with patch.object(update, "database_snapshot", return_value={"user_version": 37}):
            controller._secure_failure(state, RuntimeError("interrupted"))
        self.assertEqual(self.resolver.resolve(), controller.legacy_entrypoint.resolve())
        durable = update._read_json(controller.state_path)
        self.assertEqual(durable["safety_disposition"], "LEGACY_RESTORED_BEFORE_MIGRATION")

    def test_crash_after_migration_never_reactivates_the_old_binary(self) -> None:
        controller = self._controller()
        state = controller._state()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.21"}):
            state = controller._adopt_resolver(state)
        controller._fence(state)
        with patch.object(update, "database_snapshot", return_value={"user_version": 38}):
            controller._secure_failure(state, RuntimeError("interrupted"))
        self.assertEqual(self.resolver.resolve(), controller.fenced_resolver.resolve())
        self.assertNotEqual(self.resolver.resolve(), controller.legacy_entrypoint.resolve())

    def test_crash_during_atomic_activation_leaves_the_candidate_active(self) -> None:
        controller = self._controller()
        state = controller._state()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.21"}):
            state = controller._adopt_resolver(state)
        candidate = controller.slot / "bin" / "forge"
        candidate.parent.mkdir(parents=True)
        candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        candidate.chmod(0o755)
        update._replace_symlink(
            controller.current, __import__("os").path.relpath(candidate, controller.runtime_root)
        )
        with patch.object(update, "database_snapshot", return_value={"user_version": 38}):
            controller._secure_failure(state, RuntimeError("interrupted"))
        self.assertEqual(self.resolver.resolve(), candidate.resolve())

    def test_preservation_rejects_domain_loss_and_unexpected_schema_objects(self) -> None:
        self._installed_schema37()
        before = update.database_snapshot(self.data_root / "forge.db")
        after = json.loads(json.dumps(before))
        after["user_version"] = 38
        after["tables"]["mission_state"]["count"] = 0
        for table in update.NEW_SCHEMA_38_TABLES:
            after["tables"][table] = {
                "count": 1 if table == "operational_reset_state" else 0,
                "digest": "sha256:" + "0" * 64,
            }
        after["writer_state"]["operational_reset"] = [
            {"dataset_generation": 0, "active_operation_id": None, "state": "IDLE"}
        ]
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "historical table"):
            update.verify_preservation(before, after, self.request)


if __name__ == "__main__":
    unittest.main()
