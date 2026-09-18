"""Qualification for the bounded product-owned installed Forge update."""

from __future__ import annotations

import base64
import importlib.util
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
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
        self.root = Path(self.temporary.name).resolve()
        self.data_root = self.root / "Forge Server"
        self.runtime_root = self.root / "Forge Server Runtime"
        self.runtime_root.mkdir()
        self.resolver = self.root / "bin" / "forge"
        self.resolver.parent.mkdir()
        self.resolver.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.resolver.chmod(0o755)
        self.wheel = self.root / "forge_autonomy-2.7.22-py3-none-any.whl"
        metadata = b"Metadata-Version: 2.4\nName: forge-autonomy\nVersion: 2.7.22\n\n"
        wheel_metadata = b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n"
        members = {
            "forge/__init__.py": b"__version__ = '2.7.22'\n",
            "forge_autonomy-2.7.22.dist-info/METADATA": metadata,
            "forge_autonomy-2.7.22.dist-info/WHEEL": wheel_metadata,
        }
        record_name = "forge_autonomy-2.7.22.dist-info/RECORD"
        record = "".join(
            f"{name},sha256={base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b'=').decode()},{len(payload)}\n"
            for name, payload in members.items()
        ) + f"{record_name},,\n"
        with zipfile.ZipFile(self.wheel, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
            archive.writestr(record_name, record)
        self.wheel_digest = update.file_digest(self.wheel)
        self.sdist_digest = "sha256:" + "d" * 64
        self.receipt = self.root / "release-complete.json"
        self.receipt.write_text(json.dumps({
            "state": "RELEASE_COMPLETE", "product": "forge", "component": "forge-autonomy",
            "version": "2.7.22", "source_revision": "a" * 40,
            "operation_id": "forge-release-2.7.22-" + "a" * 40,
            "policy_revision": "forge-bootstrap-release-cadence-v2",
            "artifacts": {"wheel": self.wheel_digest, "sdist": self.sdist_digest},
            "qualification": {
                "exact_main_sha": "a" * 40,
                "qualification": "forge-production-distribution",
                "artifact_digests": {
                    "dist/forge_autonomy-2.7.22-py3-none-any.whl": self.wheel_digest,
                    "dist/forge_autonomy-2.7.22.tar.gz": self.sdist_digest,
                },
            },
            "publication_receipt": {
                "product_source_revision": "a" * 40, "readback": "PASS", "registry": "pypi",
                "original_release_run_conclusion": "failure", "original_release_run_id": "100",
                "reconciliation_contract": "forge-existing-release-reconciliation/v1",
                "reconciliation_run_id": "101", "release_controller_source": "b" * 40,
                "observed_artifact_digests": {
                    "forge_autonomy-2.7.22-py3-none-any.whl": self.wheel_digest,
                    "forge_autonomy-2.7.22.tar.gz": self.sdist_digest,
                },
                "github_release": {
                    "api_url": "https://api.github.com/repos/pcvantol/forge/releases/123",
                    "database_id": 123, "node_id": "release-node", "tag": "forge-v2.7.22",
                    "target_commitish": "a" * 40,
                },
            },
            "cleanup": {
                "result": "COMPLETE", "operation_local_cleanup": "COMPLETE",
                "original_release_run_id": "100", "reconciliation_run_id": "101",
                "reconciliation_contract": "forge-existing-release-reconciliation/v1",
                "release_controller_source": "b" * 40,
                "github_release": {
                    "api_url": "https://api.github.com/repos/pcvantol/forge/releases/123",
                    "database_id": 123, "node_id": "release-node", "draft": False,
                    "target_commitish": "a" * 40, "tag_commit": "a" * 40, "tag": "forge-v2.7.22",
                },
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

    def _same_schema_request(self) -> object:
        return update.UpdateRequest(**{
            **self.request.__dict__,
            "operation_id": "forge-update-2723-test-001",
            "version": "2.7.23",
            "existing_version": "2.7.22",
        })

    def _qualified_schema38_copy(self, controller: object, before: dict[str, object]) -> None:
        copy_root = controller.operation_root / "qualification-copy"
        (copy_root / "instance").mkdir(parents=True)
        (copy_root / "instance" / "runtime-instance.json").write_text(
            self.runtime_id + "\n", encoding="utf-8"
        )
        update._copy_sqlite_backup(self.data_root / "forge.db", copy_root / "forge.db")
        migrated = RuntimeBootstrap(data_root=copy_root, forge_version="2.7.22").open()
        migrated.close()
        update.verify_preservation(
            before, update.database_snapshot(copy_root / "forge.db"), self.request,
        )

    def test_exact_release_complete_artifact_is_accepted_and_mismatch_rejected(self) -> None:
        evidence = update.validate_qualified_artifact(self.request)
        self.assertEqual(evidence["wheel_sha256"], self.wheel_digest)
        changed = update.UpdateRequest(**{**self.request.__dict__, "product_source": "f" * 40})
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "noncanonical"):
            update.validate_qualified_artifact(changed)
        self.wheel.write_bytes(b"changed")
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "wheel digest"):
            update.validate_qualified_artifact(self.request)

    def test_normal_release_receipt_is_accepted_only_for_supported_normal_transitions(self) -> None:
        version = "2.7.24"
        wheel = self.root / f"forge_autonomy-{version}-py3-none-any.whl"
        dist_info = f"forge_autonomy-{version}.dist-info"
        members = {
            "forge/__init__.py": f"__version__ = '{version}'\n".encode(),
            f"{dist_info}/METADATA": (
                f"Metadata-Version: 2.4\nName: forge-autonomy\nVersion: {version}\n\n"
            ).encode(),
            f"{dist_info}/WHEEL": (
                b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n"
            ),
        }
        record_name = f"{dist_info}/RECORD"
        record = "".join(
            f"{name},sha256={base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b'=').decode()},{len(payload)}\n"
            for name, payload in members.items()
        ) + f"{record_name},,\n"
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, payload in members.items():
                archive.writestr(name, payload)
            archive.writestr(record_name, record)
        wheel_digest = update.file_digest(wheel)
        source = "e" * 40
        receipt = self.root / "normal-release-complete.json"
        receipt.write_text(json.dumps({
            "state": "RELEASE_COMPLETE",
            "product": "forge",
            "component": "forge-autonomy",
            "version": version,
            "source_revision": source,
            "operation_id": f"forge-release-{version}-{source}",
            "policy_revision": "forge-bootstrap-release-cadence-v2",
            "artifacts": {"wheel": wheel_digest, "sdist": self.sdist_digest},
            "qualification": {
                "exact_main_sha": source,
                "qualification": "forge-production-distribution",
                "artifact_digests": {
                    f"dist/forge_autonomy-{version}-py3-none-any.whl": wheel_digest,
                    f"dist/forge_autonomy-{version}.tar.gz": self.sdist_digest,
                },
            },
            "publication_receipt": {
                "registry": "pypi",
                "readback": "PASS",
                "observed_artifact_digests": {
                    f"forge_autonomy-{version}-py3-none-any.whl": wheel_digest,
                    f"forge_autonomy-{version}.tar.gz": self.sdist_digest,
                },
            },
            "cleanup": {
                "result": "COMPLETE",
                "temporary_paths": [
                    "published-readback", "published-input/dist", "pending-readback",
                ],
                "github_release": {"draft": False},
            },
        }, sort_keys=True), encoding="utf-8")
        request = update.UpdateRequest(**{
            **self.request.__dict__,
            "operation_id": "forge-update-2724-test-002",
            "version": version,
            "product_source": source,
            "wheel": str(wheel),
            "wheel_sha256": wheel_digest,
            "qualification_receipt": str(receipt),
            "qualification_receipt_sha256": update.file_digest(receipt),
            "existing_version": "2.7.22",
        })

        evidence = update.validate_qualified_artifact(request)

        self.assertEqual(evidence["release_route"], "NORMAL")
        from_2723 = update.UpdateRequest(**{
            **request.__dict__, "existing_version": "2.7.23",
        })
        self.assertEqual(update.validate_qualified_artifact(from_2723)["release_route"], "NORMAL")
        wrong_transition = update.UpdateRequest(**{
            **request.__dict__, "existing_version": "2.7.21",
        })
        with self.assertRaises(update.InstalledForgeUpdateError):
            update.validate_qualified_artifact(wrong_transition)

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

    def test_global_update_lock_precedes_operation_state_and_staging(self) -> None:
        self._installed_schema37()
        controller = self._controller()
        lock = self.runtime_root / "locks" / "installation-update.lock"
        with update.exclusive_lock(lock):
            with self.assertRaisesRegex(update.InstalledForgeUpdateError, "concurrent maintenance"):
                controller.run()
        self.assertFalse(controller.state_path.exists())
        self.assertFalse(controller.slot.exists())

    def test_candidate_venv_is_created_at_its_final_non_relocated_slot(self) -> None:
        controller = self._controller()
        state = controller._state()

        def identity(_interpreter: Path, *, cwd: Path) -> dict[str, str]:
            del cwd
            root = controller.slot.resolve()
            return {
                "version": "2.7.22", "distribution_version": "2.7.22",
                "module": str(root / "lib" / "python" / "site-packages" / "forge" / "__init__.py"),
                "prefix": str(root), "sys_executable": str(root / "bin" / "python"),
            }

        with (
            patch.object(update, "installed_identity", side_effect=identity),
            patch.object(update, "_install_validated_wheel"),
            patch.object(update, "_verify_candidate_files", return_value={
                "wheel_manifest_digest": update._digest_bytes(update._json_bytes({})),
                "installed_file_count": 0, "entrypoint_sha256": "sha256:" + "0" * 64,
            }),
            patch.object(update, "_run", return_value=SimpleNamespace(stdout="", stderr="")),
        ):
            staged = controller._stage(state)
        self.assertEqual(staged["phase"], "STAGED")
        self.assertTrue(controller.slot_receipt.is_file())
        self.assertTrue((controller.slot / "forge-installation-staging.json").is_file())
        self.assertFalse((controller.slot.parent / f".stage-{self.request.operation_id}").exists())

    def test_process_scan_does_not_hide_a_sibling_with_the_same_parent(self) -> None:
        controller = self._controller()
        output = (
            f"{os.getpid()} {os.getppid()} self\n"
            f"99999 {os.getppid()} selected-forge-runtime\n"
        )
        with patch.object(update, "_run", return_value=SimpleNamespace(stdout=output, stderr="")):
            self.assertEqual(controller._processes(), ["selected-forge-runtime"])

    def test_atomic_backup_is_adopted_after_state_write_interruption(self) -> None:
        self._installed_schema37()
        controller = self._controller()
        state = controller._state()
        before = update.database_snapshot(self.data_root / "forge.db")
        update._copy_sqlite_backup(self.data_root / "forge.db", controller.backup_path)
        recovered = controller._backup(state, before)
        self.assertTrue(recovered["backup"]["recovered_after_atomic_backup_write"])
        self.assertEqual(
            update.database_snapshot(controller.backup_path)["content_digest"],
            before["content_digest"],
        )

    def test_complete_fast_path_revalidates_durable_receipt_bytes(self) -> None:
        controller = self._controller()
        state = controller._state()
        update._atomic_json(controller.receipt_path, {
            "request_digest": self.request.digest, "state": "COMPLETE",
        })
        controller._advance(
            state, "COMPLETE", receipt_sha256=update.file_digest(controller.receipt_path),
        )
        update._atomic_json(controller.receipt_path, {
            "request_digest": self.request.digest, "state": "COMPLETE", "tampered": True,
        })
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "receipt changed"):
            controller.run()

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

    def test_resolver_adoption_normalizes_a_prior_operation_fence(self) -> None:
        controller = self._controller()
        controller.fenced_resolver.parent.mkdir(parents=True)
        controller.fenced_resolver.write_text(
            "#!/bin/sh\n"
            "echo 'Forge installation maintenance is active: forge-update-older-001' >&2\n"
            "exit 75\n",
            encoding="utf-8",
        )
        controller.fenced_resolver.chmod(0o755)

        with patch.object(update, "installed_identity", return_value={"version": "2.7.21"}):
            controller._adopt_resolver(controller._state())

        self.assertEqual(
            controller.fenced_resolver.read_bytes(),
            b"#!/bin/sh\necho 'Forge installation maintenance is active' >&2\nexit 75\n",
        )
        self.assertEqual(controller.fenced_resolver.stat().st_mode & 0o777, 0o755)

    def test_resolver_adoption_rejects_an_unrecognized_existing_fence(self) -> None:
        controller = self._controller()
        controller.fenced_resolver.parent.mkdir(parents=True)
        controller.fenced_resolver.write_text("#!/bin/sh\necho compromised\n", encoding="utf-8")

        with (
            patch.object(update, "installed_identity", return_value={"version": "2.7.21"}),
            self.assertRaisesRegex(update.InstalledForgeUpdateError, "fence launcher changed"),
        ):
            controller._adopt_resolver(controller._state())

    def test_crash_before_migration_restores_the_legacy_route(self) -> None:
        controller = self._controller()
        state = controller._state()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.21"}):
            state = controller._adopt_resolver(state)
        state = controller._advance(state, "BACKED_UP", before={"content_digest": "sha256:before"})
        state = controller._fence(state)
        with patch.object(update, "database_snapshot", return_value={
            "user_version": 37, "content_digest": "sha256:before",
        }):
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
        self.assertEqual(self.resolver.resolve(), controller.fenced_resolver.resolve())

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

    def test_noncanonical_receipt_and_unsafe_operation_ids_are_rejected(self) -> None:
        receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        receipt["publication_receipt"]["unexpected"] = "not-allowed"
        self.receipt.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
        changed = update.UpdateRequest(**{
            **self.request.__dict__,
            "qualification_receipt_sha256": update.file_digest(self.receipt),
        })
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "noncanonical"):
            update.validate_qualified_artifact(changed)
        for operation_id in (".", "..", "unsafe/name"):
            with self.assertRaises(update.InstalledForgeUpdateError):
                update.UpdateRequest(**{**self.request.__dict__, "operation_id": operation_id}).validate()

    def test_quiescence_uses_explicit_safe_state_allowlists(self) -> None:
        self._installed_schema37()
        connection = sqlite3.connect(self.data_root / "forge.db")
        connection.execute(
            "INSERT INTO planning_provider_generation_permits VALUES (?,?,?,?,?,?,?,?)",
            ("permit-1", "provider", 1, "sha256:" + "1" * 64, "sha256:" + "2" * 64,
             "INVALIDATED", "now", "now"),
        )
        connection.commit()
        connection.close()
        update.assert_quiescent(update.database_snapshot(self.data_root / "forge.db"))
        connection = sqlite3.connect(self.data_root / "forge.db")
        connection.execute(
            "UPDATE planning_provider_generation_permits SET state='PENDING' WHERE permit_id='permit-1'"
        )
        connection.execute("UPDATE mission_state SET status='CREATED' WHERE mission_id='MISSION-0001'")
        connection.commit()
        connection.close()
        with self.assertRaises(update.InstalledForgeUpdateError):
            update.assert_quiescent(update.database_snapshot(self.data_root / "forge.db"))

    def test_completed_replay_requires_exact_activated_schema38_fingerprint(self) -> None:
        snapshot = {
            "user_version": 38,
            "tables": {name: {} for name in update.NEW_SCHEMA_38_TABLES},
            "schema_digest": "sha256:" + "1" * 64,
        }
        readback = {"database_schema_digest": snapshot["schema_digest"]}
        update.assert_completed_schema(snapshot, readback, self.request)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "schema changed"):
            update.assert_completed_schema(
                {**snapshot, "user_version": 37}, readback, self.request,
            )
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "schema changed"):
            update.assert_completed_schema(
                {**snapshot, "schema_digest": "sha256:" + "2" * 64},
                readback,
                self.request,
            )

    def test_schema38_to_38_transition_preserves_all_runtime_content(self) -> None:
        self._installed_schema37()
        database = RuntimeBootstrap(data_root=self.data_root, forge_version="2.7.22").open()
        database.close()
        before = update.database_snapshot(self.data_root / "forge.db")
        request = self._same_schema_request()

        preservation = update.verify_preservation(before, before, request)

        self.assertEqual(preservation["from_schema"], 38)
        self.assertEqual(preservation["to_schema"], 38)
        self.assertEqual(preservation["added_tables"], [])
        changed = json.loads(json.dumps(before))
        changed["tables"]["operational_reset_audit"]["digest"] = "sha256:" + "9" * 64
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "historical table"):
            update.verify_preservation(before, changed, request)

    def test_atomic_product_migrated_copy_rejects_late_live_mutation(self) -> None:
        self._installed_schema37()
        controller = self._controller()
        before = update.database_snapshot(self.data_root / "forge.db")
        self._qualified_schema38_copy(controller, before)
        connection = sqlite3.connect(self.data_root / "forge.db")
        connection.execute("INSERT INTO mission_id_allocations VALUES (?,?,?)", ("late", "now", "late"))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "changed after"):
            controller._install_qualified_database(before)

    def test_database_swap_is_crash_safe_before_atomic_replace(self) -> None:
        self._installed_schema37()
        controller = update.InstalledForgeUpdateController(
            self.request, process_reader=lambda: (), interrupt_after="database_swap_prepared",
        )
        before = update.database_snapshot(self.data_root / "forge.db")
        self._qualified_schema38_copy(controller, before)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "database_swap_prepared"):
            controller._install_qualified_database(before)
        self.assertEqual(update.database_snapshot(self.data_root / "forge.db")["user_version"], 37)
        self.assertFalse((self.data_root / "forge.db-wal").exists())
        self.assertFalse((self.data_root / "forge.db-shm").exists())

    def test_database_swap_is_crash_safe_after_atomic_replace(self) -> None:
        self._installed_schema37()
        controller = update.InstalledForgeUpdateController(
            self.request, process_reader=lambda: (), interrupt_after="database_swap",
        )
        before = update.database_snapshot(self.data_root / "forge.db")
        self._qualified_schema38_copy(controller, before)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "database_swap"):
            controller._install_qualified_database(before)
        after = update.database_snapshot(self.data_root / "forge.db")
        self.assertEqual(after["user_version"], 38)
        update.verify_preservation(before, after, self.request)
        self.assertEqual((self.data_root / "forge.db").stat().st_mode & 0o777, 0o400)
        self.assertFalse((self.data_root / "forge.db-wal").exists())
        self.assertFalse((self.data_root / "forge.db-shm").exists())

    def test_exact_published_wheel_end_to_end_when_requested(self) -> None:
        wheel_value = os.environ.get("FORGE_EXACT_WHEEL")
        receipt_value = os.environ.get("FORGE_EXACT_RELEASE_RECEIPT")
        if not wheel_value or not receipt_value:
            self.skipTest("exact published wheel paths were not supplied")
        self._installed_schema37()
        wheel = Path(wheel_value).resolve()
        receipt = Path(receipt_value).resolve()
        release = json.loads(receipt.read_text(encoding="utf-8"))
        legacy_interpreter = Path(os.environ.get("FORGE_LEGACY_INTERPRETER", sys.executable))
        try:
            legacy_identity = update.installed_identity(legacy_interpreter, cwd=self.root)
        except update.InstalledForgeUpdateError as error:
            self.skipTest(f"legacy Forge interpreter was not supplied: {error}")
        request = update.UpdateRequest(**{
            **self.request.__dict__,
            "product_source": release["source_revision"],
            "wheel": str(wheel), "wheel_sha256": update.file_digest(wheel),
            "qualification_receipt": str(receipt),
            "qualification_receipt_sha256": update.file_digest(receipt),
            "controller_sha256": update.file_digest(SCRIPT),
            "existing_interpreter": str(legacy_interpreter),
            "existing_version": legacy_identity["version"],
        })
        controller = update.InstalledForgeUpdateController(request, process_reader=lambda: ())
        completed = controller.run()
        self.assertEqual(completed["state"], "COMPLETE")
        self.assertEqual(update.database_snapshot(self.data_root / "forge.db")["user_version"], 38)
        self.assertEqual(controller.run(), completed)
        self.assertEqual((self.data_root / "forge.db").stat().st_mode & 0o777, 0o600)
        connection = sqlite3.connect(self.data_root / "forge.db")
        connection.execute("PRAGMA user_version=37")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "schema changed"):
            controller.run()


if __name__ == "__main__":
    unittest.main()
