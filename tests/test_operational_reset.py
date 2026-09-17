from __future__ import annotations

from collections import namedtuple
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime import RuntimeBootstrap, RuntimeMaintenanceActive
from forge.runtime.operational_reset import (
    MAINTENANCE_TABLES,
    PURGE_TABLES,
    RESET_PROFILE,
    TABLE_CLASSIFICATION,
    ForgeOperationalResetService,
    OperationalResetError,
)


IDENTITY = NamedOperatorIdentity("123e4567-e89b-42d3-a456-426614174000", 501)
Disk = namedtuple("Disk", "total used free")


class OneShotFault:
    def __init__(self, event: str) -> None:
        self.event = event
        self.fired = False

    def __call__(self, event: str, _path: str | None) -> None:
        if event == self.event and not self.fired:
            self.fired = True
            raise RuntimeError("synthetic crash: " + event)


class OperationalResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="2.7.21").open()
        InstallationOperatorService(self.database, lambda: IDENTITY).first_bind()

    def tearDown(self) -> None:
        if getattr(self, "database", None) is not None:
            self.database.close()
        self.temporary.cleanup()

    def service(self, **values: object) -> ForgeOperationalResetService:
        return ForgeOperationalResetService(self.root, identity_resolver=lambda: IDENTITY, **values)

    def seed_operational_state(self, *, external: bool = True) -> None:
        document = {
            "id": "MISSION-0042", "mission_id": "MISSION-0042", "lifecycle": "ACTIVE",
            "status": "ACTIVE", "progress": {}, "resume_point": {}, "execution_policy": {},
        }
        self.database._connection.execute(
            "INSERT INTO mission_state VALUES (?,?,?,?,?,?,?,?,?)",
            ("MISSION-0042", "ACTIVE", "ACTIVE", None, None, "{}", "{}", "{}", json.dumps(document)),
        )
        self.database._connection.execute(
            "INSERT INTO mission_id_allocations VALUES (?,?,?)", ("MISSION-0042", "now", "source-42")
        )
        submission = {
            "submission_id": "submission-old", "mission_id": "MISSION-0042", "intent_id": "intent-old",
            "action_id": "action-old", "iteration": 1, "state": "CREATED", "envelope": {"old": True},
        }
        self.database._connection.execute(
            "INSERT INTO scheduler_submissions VALUES (?,?,?,?,?,?,?,?,?)",
            ("submission-old", "MISSION-0042", "intent-old", "action-old", 1, "CREATED", None, None, json.dumps(submission)),
        )
        self.database._connection.execute(
            "INSERT INTO execution_host_bindings VALUES (?,?)",
            ("correlation-old", json.dumps({"correlation_id": "correlation-old"})),
        )
        self.database._connection.execute(
            "INSERT INTO planning_provider_security_config VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("config", "provider", "keychain://forge/account", 1, "operator", 1, "now", "now", "model", 5, 10, 20, 5),
        )
        self.database._connection.execute(
            "INSERT INTO planning_provider_generation_permits VALUES (?,?,?,?,?,?,?,?)",
            ("permit-old", "provider", 1, "sha256:" + "1" * 64, "sha256:" + "2" * 64, "PENDING", "now", "now"),
        )
        self.database._connection.execute(
            "INSERT INTO execution_host_peer_configuration VALUES (?,?,?,?,?)",
            (1, "binding", 1, "sha256:" + "3" * 64, json.dumps({
                "binding_id": "binding", "credential_reference": "keychain://forge/ep-token",
            })),
        )
        self.database._connection.commit()
        self.database.save_action_derivation(self.old_action_derivation())
        if external:
            operational = self.root / "artifacts" / "operational"
            operational.mkdir()
            (operational / "evidence.json").write_text('{"evidence":true}\n', encoding="utf-8")
            (self.root / "artifacts" / "controlled-installation-e2e-starter-exit-2026-09-14.md").write_text(
                "installation qualification\n", encoding="utf-8",
            )

    @staticmethod
    def old_action_derivation() -> dict[str, object]:
        return {
            "derivation_id": "derivation-old", "mission_id": "MISSION-0042",
            "snapshot_digest": "sha256:" + "4" * 64, "contract_version": "1",
            "provider_configuration": "sha256:" + "5" * 64,
            "lifecycle": "DERIVATION_REQUESTED",
            "generation_request_digest": "sha256:" + "6" * 64,
        }

    def prepare(self, service: ForgeOperationalResetService, operation: str = "forge-reset-test-0001") -> dict[str, object]:
        plan = service.preview()
        self.assertEqual(plan["status"], "READY", plan["blockers"])
        return service.prepare(operation_id=operation, expected_plan_digest=str(plan["plan_digest"]))

    def complete(self, service: ForgeOperationalResetService, operation: str = "forge-reset-test-0001") -> dict[str, object]:
        receipt = self.prepare(service, operation)
        receipt = service.apply(
            operation_id=operation, plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        receipt = service.verify(
            operation_id=operation, plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        return service.finish(operation_id=operation, verification_digest=str(receipt["verification_digest"]))

    def test_mapping_covers_every_application_table_and_preview_is_read_only(self) -> None:
        runtime_lock = self.root / "forge-runtime-mutation.lock"
        runtime_lock.touch()
        before = {
            table: self.database._connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in TABLE_CLASSIFICATION
        }
        plan = self.service().preview()
        after = {
            table: self.database._connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in TABLE_CLASSIFICATION
        }
        actual = {
            row[0] for row in self.database._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        self.assertEqual(set(TABLE_CLASSIFICATION), actual)
        self.assertEqual(before, after)
        self.assertEqual(plan["profile"], RESET_PROFILE)
        self.assertIn(
            {"path": "forge-runtime-mutation.lock", "category": "SYSTEM_RUNTIME_CONTROL", "effect": "PRESERVE", "size_bytes": 0},
            plan["external_control_entries"],
        )
        self.assertIsNone(self.database._connection.execute(
            "SELECT active_operation_id FROM operational_reset_state"
        ).fetchone()[0])

    def test_unknown_table_root_file_and_symlink_fail_closed_without_deleting_user_data(self) -> None:
        self.database._connection.execute("CREATE TABLE future_product_data(id TEXT)")
        self.database._connection.commit()
        user_file = self.root / "notes.txt"
        user_file.write_text("keep me", encoding="utf-8")
        (self.root / "artifacts" / "escape").symlink_to(user_file)
        plan = self.service().preview()
        codes = {item["code"] for item in plan["blockers"]}
        self.assertIn("UNKNOWN_OR_INCOMPLETE_SCHEMA", codes)
        self.assertIn("UNKNOWN_OR_UNSAFE_EXTERNAL_DATA", codes)
        self.assertEqual(user_file.read_text(encoding="utf-8"), "keep me")

    def test_missing_durable_writer_fence_blocks_prepare(self) -> None:
        self.database._connection.execute("DROP TRIGGER operational_reset_block_mission_state_insert")
        self.database._connection.commit()
        plan = self.service().preview()
        self.assertIn("MAINTENANCE_FENCE_INCOMPLETE", {item["code"] for item in plan["blockers"]})
        with self.assertRaisesRegex(OperationalResetError, "blocking findings"):
            self.service().prepare(
                operation_id="forge-reset-test-0001", expected_plan_digest=str(plan["plan_digest"]),
            )

    def test_explicit_data_root_symlink_is_rejected_before_canonicalization(self) -> None:
        alias = self.root.parent / (self.root.name + "-alias")
        alias.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(alias.unlink)
        service = ForgeOperationalResetService(alias, identity_resolver=lambda: IDENTITY)
        with self.assertRaisesRegex(OperationalResetError, "data root.*symlink"):
            service.preview()

    def test_explicit_data_root_with_symlink_parent_is_rejected_before_canonicalization(self) -> None:
        alias = self.root.parent / (self.root.name + "-parent-alias")
        alias.symlink_to(self.root.parent, target_is_directory=True)
        self.addCleanup(alias.unlink)
        service = ForgeOperationalResetService(
            alias / self.root.name, identity_resolver=lambda: IDENTITY,
        )
        with self.assertRaisesRegex(OperationalResetError, "data root.*symlink"):
            service.preview()

    def test_schema37_preview_inventory_is_read_only_and_prepare_requires_installed_migration(self) -> None:
        self.database.close()
        self.database = None
        connection = sqlite3.connect(self.root / "forge.db")
        for (trigger,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'operational_reset_%'"
        ).fetchall():
            connection.execute(f'DROP TRIGGER "{trigger}"')
        for table in MAINTENANCE_TABLES:
            triggers = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)
            ).fetchall()
            for (trigger,) in triggers:
                connection.execute(f'DROP TRIGGER "{trigger}"')
        for table in reversed(MAINTENANCE_TABLES):
            connection.execute(f'DROP TABLE "{table}"')
        connection.execute("UPDATE runtime_metadata SET value='37' WHERE key IN ('schema_version','migration_version','last_migration')")
        connection.execute("PRAGMA user_version=37")
        connection.commit()
        before = (self.root / "forge.db").stat().st_size
        connection.close()
        plan = self.service().preview()
        self.assertEqual(plan["target"]["schema_version"], 37)
        self.assertIn("SCHEMA_MIGRATION_REQUIRED", {item["code"] for item in plan["blockers"]})
        self.assertEqual((self.root / "forge.db").stat().st_size, before)

    def test_reset_preserves_identity_binding_credentials_security_allocator_and_qualification_artifact(self) -> None:
        self.seed_operational_state()
        runtime_id = self.database.runtime_identity.runtime_id
        original_binding = self.database._connection.execute(
            "SELECT document FROM execution_host_peer_configuration"
        ).fetchone()[0]
        original_config = self.database._connection.execute(
            "SELECT secret_reference FROM planning_provider_security_config"
        ).fetchone()[0]
        self.database.close()
        self.database = None
        service = self.service()
        receipt = self.complete(service)
        self.assertEqual(receipt["state"], "COMPLETED")
        reopened = RuntimeBootstrap(data_root=self.root, forge_version="2.7.21").open()
        try:
            self.assertEqual(reopened.runtime_identity.runtime_id, runtime_id)
            for table in PURGE_TABLES:
                self.assertEqual(reopened._connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0], 0, table)
            self.assertEqual(reopened._connection.execute("SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0], 1)
            self.assertEqual(reopened._connection.execute(
                "SELECT document FROM execution_host_peer_configuration"
            ).fetchone()[0], original_binding)
            self.assertEqual(reopened._connection.execute(
                "SELECT secret_reference FROM planning_provider_security_config"
            ).fetchone()[0], original_config)
            self.assertEqual(reopened._connection.execute(
                "SELECT state FROM planning_provider_generation_permits"
            ).fetchone()[0], "INVALIDATED_BY_OPERATIONAL_RESET")
            self.assertGreater(reopened._connection.execute(
                "SELECT COUNT(*) FROM operational_reset_tombstones"
            ).fetchone()[0], 0)
        finally:
            reopened.close()
        self.assertTrue((self.root / "artifacts" / "controlled-installation-e2e-starter-exit-2026-09-14.md").is_file())
        self.assertFalse((self.root / "artifacts" / "operational" / "evidence.json").exists())
        encoded = json.dumps(receipt)
        self.assertNotIn("keychain://", encoded)

    def test_raw_idle_connection_needs_no_udf_and_existing_owning_writer_is_fenced(self) -> None:
        raw = sqlite3.connect(self.root / "forge.db")
        raw.execute("UPDATE runtime_metadata SET value=value WHERE key='status'")
        raw.commit()
        existing = self.database
        receipt = self.prepare(self.service())
        with self.assertRaises(sqlite3.DatabaseError):
            raw.execute("UPDATE runtime_metadata SET value=value WHERE key='status'")
        raw.rollback()
        raw.close()
        with self.assertRaises(sqlite3.DatabaseError):
            existing.save_planning_state({
                "planner_version": "blocked", "current_queue": [], "pending_engineering_actions": [],
                "blocked_engineering_actions": [], "execution_policy": {}, "planner_runtime_metadata": {},
            })
        with self.assertRaises(RuntimeMaintenanceActive):
            RuntimeBootstrap(data_root=self.root, forge_version="2.7.21").open()
        self.service().finish(operation_id=str(receipt["operation_id"]), cancel_before_apply=True)

    def test_stale_plan_wrong_request_and_operation_id_reuse_are_rejected(self) -> None:
        plan = self.service().preview()
        self.database._connection.execute("INSERT INTO mission_id_allocations VALUES (?,?,?)", ("MISSION-0009", "now", "new"))
        self.database._connection.commit()
        with self.assertRaisesRegex(OperationalResetError, "plan changed"):
            self.service().prepare(operation_id="forge-reset-test-0001", expected_plan_digest=str(plan["plan_digest"]))
        current = self.prepare(self.service())
        with self.assertRaisesRegex(OperationalResetError, "different request"):
            self.service().prepare(
                operation_id="forge-reset-test-0001", expected_plan_digest="sha256:" + "0" * 64,
            )
        with self.assertRaisesRegex(OperationalResetError, "differs"):
            self.service().apply(
                operation_id="forge-reset-test-0001", plan_digest=str(current["plan_digest"]),
                request_digest="sha256:" + "0" * 64, backup_digest=str(current["backup_digest"]),
            )
        self.service().finish(operation_id="forge-reset-test-0001", cancel_before_apply=True)

    def test_insufficient_disk_leaves_durable_safe_maintenance_and_can_cancel(self) -> None:
        service = self.service(disk_usage=lambda _path: Disk(1, 1, 0))
        plan = service.preview()
        with self.assertRaisesRegex(OperationalResetError, "insufficient"):
            service.prepare(operation_id="forge-reset-test-0001", expected_plan_digest=str(plan["plan_digest"]))
        self.assertEqual(service.status()["active_operation_id"], "forge-reset-test-0001")
        result = service.finish(operation_id="forge-reset-test-0001", cancel_before_apply=True)
        self.assertEqual(result["state"], "CANCELLED")

    def test_backup_nested_symlink_is_rejected_without_writing_outside_root(self) -> None:
        self.seed_operational_state()
        escape = Path(self.temporary.name + "-backup-escape")
        escape.mkdir()
        self.addCleanup(lambda: escape.rmdir() if escape.exists() else None)

        def inject_after_authorization(event: str, _path: str | None) -> None:
            if event == "after_prepare":
                nested = self.root / "backups" / "forge-reset-test-0001" / "external"
                nested.mkdir(parents=True)
                (nested / "artifacts").symlink_to(escape, target_is_directory=True)

        service = self.service(fault_hook=inject_after_authorization)
        plan = service.preview()
        with self.assertRaisesRegex(OperationalResetError, "backup external path contains a symlink"):
            service.prepare(
                operation_id="forge-reset-test-0001", expected_plan_digest=str(plan["plan_digest"]),
            )
        self.assertEqual(list(escape.iterdir()), [])
        service.finish(operation_id="forge-reset-test-0001", cancel_before_apply=True)

    def test_crash_before_commit_resumes_without_half_purge(self) -> None:
        self.seed_operational_state(external=False)
        service = self.service()
        receipt = self.prepare(service)
        crashing = self.service(fault_hook=OneShotFault("before_database_commit"))
        with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
            crashing.apply(
                operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
                request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
            )
        observer = sqlite3.connect(self.root / "forge.db")
        self.assertEqual(observer.execute("SELECT COUNT(*) FROM mission_state").fetchone()[0], 1)
        observer.close()
        resumed = service.resume(
            operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        self.assertEqual(resumed["state"], "VERIFIED")

    def test_crash_after_commit_resumes_same_generation(self) -> None:
        self.seed_operational_state(external=False)
        service = self.service()
        receipt = self.prepare(service)
        crashing = self.service(fault_hook=OneShotFault("after_database_commit"))
        with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
            crashing.apply(
                operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
                request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
            )
        self.assertEqual(service.status(operation_id="forge-reset-test-0001")["state"], "DATABASE_APPLIED")
        resumed = service.resume(
            operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        self.assertEqual(resumed["generation_after"], 1)
        self.assertEqual(resumed["state"], "VERIFIED")

    def test_crash_during_artifact_removal_reconciles_from_verified_archive(self) -> None:
        self.seed_operational_state()
        service = self.service()
        receipt = self.prepare(service)
        crashing = self.service(fault_hook=OneShotFault("after_artifact_remove"))
        with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
            crashing.apply(
                operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
                request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
            )
        resumed = service.resume(
            operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        self.assertEqual(resumed["state"], "VERIFIED")
        self.assertEqual(resumed["pending_artifacts"], 0)

    def test_tampered_backup_before_apply_keeps_database_and_maintenance_intact(self) -> None:
        self.seed_operational_state(external=False)
        service = self.service()
        receipt = self.prepare(service)
        backup_marker = self.root / str(receipt["backup_reference"]) / "runtime-instance.json"
        backup_marker.write_text("tampered-before-apply\n", encoding="utf-8")
        with self.assertRaisesRegex(OperationalResetError, "backup digest"):
            service.apply(
                operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
                request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
            )
        observer = sqlite3.connect(self.root / "forge.db")
        try:
            self.assertEqual(observer.execute("SELECT COUNT(*) FROM mission_state").fetchone()[0], 1)
            self.assertEqual(observer.execute("SELECT COUNT(*) FROM action_derivations").fetchone()[0], 1)
            self.assertEqual(observer.execute(
                "SELECT state FROM operational_reset_operations WHERE operation_id='forge-reset-test-0001'"
            ).fetchone()[0], "BACKUP_VERIFIED")
            self.assertEqual(observer.execute(
                "SELECT active_operation_id FROM operational_reset_state WHERE singleton=1"
            ).fetchone()[0], "forge-reset-test-0001")
        finally:
            observer.close()

    def test_tampered_backup_during_database_applied_resume_preserves_active_artifact(self) -> None:
        self.seed_operational_state()
        service = self.service()
        receipt = self.prepare(service)
        crashing = self.service(fault_hook=OneShotFault("after_database_commit"))
        with self.assertRaisesRegex(RuntimeError, "synthetic crash"):
            crashing.apply(
                operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
                request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
            )
        backup_marker = self.root / str(receipt["backup_reference"]) / "runtime-instance.json"
        backup_marker.write_text("tampered-during-resume\n", encoding="utf-8")
        with self.assertRaisesRegex(OperationalResetError, "backup digest"):
            service.resume(
                operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
                request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
            )
        self.assertTrue((self.root / "artifacts" / "operational" / "evidence.json").is_file())
        self.assertEqual(service.status()["active_operation_id"], "forge-reset-test-0001")

    def test_same_operation_is_idempotent_and_new_empty_reset_is_meaningful_noop(self) -> None:
        service = self.service()
        receipt = self.complete(service)
        same = service.finish(operation_id="forge-reset-test-0001", verification_digest=str(receipt["verification_digest"]))
        self.assertEqual(same["generation_after"], receipt["generation_after"])
        plan = service.preview()
        self.assertTrue(plan["no_op"])

    def test_corrupt_backup_blocks_verification_and_maintenance_stays_active(self) -> None:
        self.seed_operational_state(external=False)
        service = self.service()
        receipt = self.prepare(service)
        receipt = service.apply(
            operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        backup = self.root / str(receipt["backup_reference"]) / "runtime-instance.json"
        backup.write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(OperationalResetError, "backup digest"):
            service.verify(
                operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
                request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
            )
        self.assertEqual(service.status()["active_operation_id"], "forge-reset-test-0001")

    def test_tampered_backup_manifest_is_rejected_even_when_referenced_files_are_unchanged(self) -> None:
        self.seed_operational_state(external=False)
        service = self.service()
        receipt = self.prepare(service)
        receipt = service.apply(
            operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        manifest = self.root / str(receipt["backup_reference"]) / "manifest.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["excluded"].append("tampered")
        manifest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(OperationalResetError, "manifest binding"):
            service.verify(
                operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
                request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
            )

    def test_finish_rechecks_delayed_external_data_and_backup_without_rewriting_verification(self) -> None:
        self.seed_operational_state(external=False)
        service = self.service()
        receipt = self.prepare(service)
        receipt = service.apply(
            operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        receipt = service.verify(
            operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        audit_before = int(receipt["audit_events"])
        delayed = self.root / "journals" / "delayed.jsonl"
        delayed.write_text('{"old_callback":true}\n', encoding="utf-8")
        with self.assertRaisesRegex(OperationalResetError, "external operational data"):
            service.finish(
                operation_id="forge-reset-test-0001", verification_digest=str(receipt["verification_digest"]),
            )
        status = service.status(operation_id="forge-reset-test-0001")
        self.assertEqual(status["state"], "VERIFIED")
        self.assertEqual(status["audit_events"], audit_before)
        self.assertEqual(service.status()["active_operation_id"], "forge-reset-test-0001")
        delayed.unlink()
        backup_marker = self.root / str(receipt["backup_reference"]) / "runtime-instance.json"
        backup_marker.write_text("tampered-after-verify\n", encoding="utf-8")
        with self.assertRaisesRegex(OperationalResetError, "backup digest"):
            service.finish(
                operation_id="forge-reset-test-0001", verification_digest=str(receipt["verification_digest"]),
            )
        self.assertEqual(service.status(operation_id="forge-reset-test-0001")["state"], "VERIFIED")
        self.assertEqual(service.status()["active_operation_id"], "forge-reset-test-0001")

    def test_old_callback_and_submission_identities_are_rejected_after_finish(self) -> None:
        self.seed_operational_state(external=False)
        self.database.close()
        self.database = None
        self.complete(self.service())
        database = RuntimeBootstrap(data_root=self.root, forge_version="2.7.21").open()
        try:
            with self.assertRaisesRegex(Exception, "retired"):
                database.save_execution_host_binding("correlation-old", {"correlation_id": "correlation-old"})
            with self.assertRaisesRegex(Exception, "retired"):
                database.create_scheduler_submission({
                    "submission_id": "submission-old", "mission_id": "new-mission",
                    "intent_id": "new-intent", "action_id": "action-old", "iteration": 1,
                    "state": "CREATED", "envelope": {},
                })
            with self.assertRaisesRegex(Exception, "action_derivation_id identity was retired"):
                database.save_action_derivation(self.old_action_derivation())
            with self.assertRaisesRegex(Exception, "mission_id identity was retired"):
                database.create_mission_state({
                    "mission_id": "MISSION-0042", "lifecycle": "ACTIVE", "status": "ACTIVE",
                    "progress": {}, "resume_point": {}, "execution_policy": {},
                })
            tombstone_kinds = {
                row[0] for row in database._connection.execute(
                    "SELECT DISTINCT record_kind FROM operational_reset_tombstones"
                )
            }
            self.assertTrue({
                "mission_id", "action_id", "submission_id", "correlation_id",
                "action_derivation_id", "generation_request_digest",
            } <= tombstone_kinds)
        finally:
            database.close()

    def test_operational_fk_fixture_requires_exact_acknowledgement_and_is_clean_after_reset(self) -> None:
        self.database._connection.execute("PRAGMA foreign_keys=OFF")
        self.database._connection.execute(
            "INSERT INTO mission_runtime_projections VALUES (?,?,?)", ("missing-mission", "digest", "{}")
        )
        self.database._connection.commit()
        plan = self.service().preview()
        self.assertFalse(plan["blockers"])
        self.assertEqual(len(plan["required_fk_acknowledgements"]), 1)
        with self.assertRaisesRegex(OperationalResetError, "must be acknowledged"):
            self.service().prepare(
                operation_id="forge-reset-test-0001", expected_plan_digest=str(plan["plan_digest"])
            )
        receipt = self.service().prepare(
            operation_id="forge-reset-test-0001", expected_plan_digest=str(plan["plan_digest"]),
            acknowledge_operational_fk=plan["required_fk_acknowledgements"],
        )
        receipt = self.service().resume(
            operation_id="forge-reset-test-0001", plan_digest=str(receipt["plan_digest"]),
            request_digest=str(receipt["request_digest"]), backup_digest=str(receipt["backup_digest"]),
        )
        self.assertEqual(receipt["state"], "VERIFIED")

    def test_fk_damage_reaching_preserved_configuration_blocks(self) -> None:
        self.database._connection.execute("PRAGMA foreign_keys=OFF")
        self.database._connection.execute(
            "INSERT INTO planning_provider_security_audit VALUES (?,?,?,?,?,?)",
            ("orphan", "missing-config", "operator", "test", "now", "{}"),
        )
        self.database._connection.commit()
        plan = self.service().preview()
        self.assertIn("FOREIGN_KEY_DAMAGE_OUTSIDE_PURGE_SET", {item["code"] for item in plan["blockers"]})

    def test_operator_envelope_has_stable_cross_product_fields(self) -> None:
        plan = self.service().preview()
        envelope = self.service().operator_envelope("preview", plan)
        self.assertEqual(envelope["contract_version"], "operational-reset-v1")
        self.assertEqual(envelope["product"], "forge")
        self.assertEqual(set(envelope["target"]), {"instance_id", "database_path", "database_identity", "schema_version"})
        self.assertIn("preserved_bindings_digest", envelope)

    def test_cli_error_retains_stable_cross_product_envelope(self) -> None:
        result = subprocess.run(
            (
                sys.executable, "-m", "forge", "--data-root", str(self.root), "server", "reset",
                "prepare", "--operation-id", "short", "--plan-digest", "invalid",
            ),
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 1)
        payload = json.loads(result.stdout)
        required = {
            "contract_version", "product", "command", "operation_id", "state", "allowed", "target",
            "profile", "dataset_generation", "plan_digest", "relevant_revision_digest", "backup", "counts",
            "blockers", "integrity", "preserved_bindings_digest", "details",
        }
        self.assertTrue(required <= set(payload))
        self.assertFalse(payload["allowed"])

    def test_packaged_cli_exposes_real_read_only_preview_and_command_family(self) -> None:
        self.database.close()
        self.database = None
        result = subprocess.run(
            (sys.executable, "-m", "forge", "--data-root", str(self.root), "server", "reset", "preview"),
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["contract_version"], "operational-reset-v1")
        self.assertEqual(payload["command"], "preview")
        self.assertEqual(payload["target"]["instance_id"], self.marker_id())
        help_result = subprocess.run(
            (sys.executable, "-m", "forge", "server", "reset", "--help"),
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(help_result.returncode, 0)
        for command in ("preview", "prepare", "apply", "status", "resume", "verify", "finish"):
            self.assertIn(command, help_result.stdout)

    def marker_id(self) -> str:
        return (self.root / "instance" / "runtime-instance.json").read_text(encoding="utf-8").strip()


if __name__ == "__main__":
    unittest.main()
