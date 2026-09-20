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
import forge.runtime.database as runtime_database
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

    @staticmethod
    def _open_schema38(root):
        # Exercise the retained historical migration with its explicit reader
        # ceiling; current RuntimeBootstrap must otherwise migrate through 39.
        with patch.object(runtime_database, "RUNTIME_SCHEMA_VERSION", 38):
            return RuntimeBootstrap(data_root=root, forge_version="2.7.24").open()

    def _installed_schema37(self) -> None:
        database = self._open_schema38(self.data_root)
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
        migrated = self._open_schema38(copy_root)
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

    def _normal_release_request(self, version="2.7.24", existing_version="2.7.22"):
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
        if version in {"2.7.25", "2.7.26", "2.7.27"}:
            # Captured from the actual installed-composition command used by
            # both workflow stages; only the synthetic wheel binding changes.
            summary = json.loads((Path(__file__).parent / "fixtures" /
                "criterion-completion-installed-summary.json").read_text())
            summary["artifact"]["version"] = version
            summary["artifact"]["wheel_sha256"] = wheel_digest.removeprefix("sha256:")
            document = json.loads(receipt.read_text())
            document["qualification"]["criterion_completion"] = summary
            document["publication_receipt"]["criterion_completion"] = summary
            receipt.write_text(json.dumps(document, sort_keys=True))
        request = update.UpdateRequest(**{
            **self.request.__dict__,
            "operation_id": "forge-update-2724-test-002",
            "version": version,
            "product_source": source,
            "wheel": str(wheel),
            "wheel_sha256": wheel_digest,
            "qualification_receipt": str(receipt),
            "qualification_receipt_sha256": update.file_digest(receipt),
            "existing_version": existing_version,
        })
        return request

    def test_2725_requires_exact_qualifying_and_published_installed_composition(self):
        request = self._normal_release_request("2.7.25", "2.7.24")
        self.assertEqual(update.validate_qualified_artifact(request)["release_route"], "NORMAL")
        receipt = Path(request.qualification_receipt)
        original = json.loads(receipt.read_text())
        for section in ("qualification", "publication_receipt"):
            for mutation in ("missing", "wrong-wheel", "source-only", "missing-case", "duplicate-case",
                             "wrong-count", "false-completion", "lost-history", "malformed-criterion",
                             "wrong-regression-criterion", "wrong-block-reason", "extra-field"):
                with self.subTest(section=section, mutation=mutation):
                    document = json.loads(json.dumps(original))
                    report = document[section]["criterion_completion"]
                    if mutation == "missing":
                        del document[section]["criterion_completion"]
                    elif mutation == "wrong-wheel":
                        report["artifact"]["wheel_sha256"] = "f" * 64
                    elif mutation == "source-only":
                        report["qualification"] = "SOURCE_COMPOSITION_WITH_EXTERNAL_FIXTURES"
                    elif mutation == "missing-case":
                        report["scenarios"].pop()
                    elif mutation == "duplicate-case":
                        report["scenarios"][-1] = report["scenarios"][0]
                    elif mutation == "wrong-count":
                        report["scenarios"][0]["planner_invocations"] = 1
                    elif mutation == "false-completion":
                        report["scenarios"][-1]["status"] = "COMPLETED"
                    elif mutation == "lost-history":
                        report["scenarios"][0]["original_observations_preserved"] = False
                    elif mutation == "malformed-criterion":
                        report["scenarios"][0]["criteria"][0]["criterion"] = []
                    elif mutation == "wrong-regression-criterion":
                        criteria = report["scenarios"][-1]["criteria"]
                        criteria[0]["criterion"], criteria[1]["criterion"] = (
                            criteria[1]["criterion"], criteria[0]["criterion"])
                    elif mutation == "wrong-block-reason":
                        report["scenarios"][-1]["waiting_reason"] = "completion_assessment_failed:VALUEERROR"
                    else:
                        report["scenarios"][-1]["unchecked_claim"] = "PASS"
                    receipt.write_text(json.dumps(document))
                    changed = update.UpdateRequest(**{**request.__dict__,
                        "qualification_receipt_sha256": update.file_digest(receipt)})
                    with self.assertRaises(update.InstalledForgeUpdateError):
                        update.validate_qualified_artifact(changed)

    def test_normal_release_receipt_is_accepted_only_for_supported_normal_transitions(self) -> None:
        request = self._normal_release_request()
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
        migrated = self._open_schema38(copy_root)
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

    def _managed_successor_controller(self, *, fenced: bool = False):
        first = self._controller()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.21"}):
            first._adopt_resolver(first._state())
        previous_bin = self.root / "previous-slot" / "bin"
        previous_bin.mkdir(parents=True)
        previous_python = previous_bin / "python"
        previous_python.write_bytes(b"previous-python")
        previous_forge = previous_bin / "forge"
        previous_forge.write_bytes(b"#!/bin/sh\nexec previous-python -m forge \"$@\"\n")
        previous_forge.chmod(0o700)
        request = update.UpdateRequest(**{
            **self._same_schema_request().__dict__,
            "operation_id": "forge-update-2723-managed-successor-001",
            "resolver_sha256": update.file_digest(previous_forge),
            "existing_interpreter": str(previous_python),
        })
        controller = update.InstalledForgeUpdateController(request, process_reader=lambda: ())
        update._replace_symlink(first.current, os.path.relpath(previous_forge, self.runtime_root))
        state = controller._state()
        if fenced:
            controller.fenced_resolver.parent.mkdir(parents=True, exist_ok=True)
            update._atomic_regular_file(
                controller.fenced_resolver,
                b"#!/bin/sh\necho 'Forge installation maintenance is active' >&2\nexit 75\n",
                mode=0o755,
            )
            update._replace_symlink(
                controller.current, os.path.relpath(controller.fenced_resolver, self.runtime_root),
            )
            state = controller._advance(
                state, "STAGED",
                safety_disposition="UNVERIFIED_OR_MIGRATED_RUNTIME_FENCED",
                last_error=f"path contains a symbolic-link component: {request.resolver}",
            )
        return controller, state, previous_forge

    def test_resolver_adoption_uses_the_selected_entrypoint_for_a_managed_successor(self) -> None:
        controller, state, previous_forge = self._managed_successor_controller()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.22"}):
            adopted = controller._adopt_resolver(state)
        self.assertEqual(adopted["phase"], "ADOPTED")
        self.assertEqual(controller.legacy_entrypoint.read_bytes(), previous_forge.read_bytes())
        self.assertEqual(self.resolver.resolve(), previous_forge.resolve())

    def test_resolver_adoption_recovers_the_recognized_pre_adoption_fence(self) -> None:
        controller, state, previous_forge = self._managed_successor_controller(fenced=True)
        with patch.object(update, "installed_identity", return_value={"version": "2.7.22"}):
            adopted = controller._adopt_resolver(state)
        self.assertEqual(adopted["phase"], "ADOPTED")
        self.assertEqual(controller.legacy_entrypoint.read_bytes(), previous_forge.read_bytes())
        self.assertEqual(self.resolver.resolve(), controller.fenced_resolver.resolve())

    def test_resolver_adoption_rejects_an_unrecognized_managed_current_target(self) -> None:
        controller, state, _previous_forge = self._managed_successor_controller()
        unexpected = self.root / "unexpected-forge"
        unexpected.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        update._replace_symlink(controller.current, os.path.relpath(unexpected, self.runtime_root))
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "unrecognized target"):
            controller._adopt_resolver(state)

    def test_staged_controller_reconciliation_preserves_the_operation_and_audits_rebind(self) -> None:
        controller, state, _previous_forge = self._managed_successor_controller(fenced=True)
        evidence = {
            "wheel_manifest_digest": "sha256:" + "1" * 64,
            "installed_file_count": 7,
            "entrypoint_sha256": "sha256:" + "2" * 64,
        }
        identity = {
            "version": controller.request.version,
            "module": str(controller.slot / "lib/python/site-packages/forge/__init__.py"),
        }
        state = controller._advance(state, "STAGED", candidate=identity, installed_files=evidence)
        controller.slot.mkdir(parents=True)
        update._atomic_json(controller.slot_receipt, {
            "request_digest": controller.request.digest,
            "wheel_manifest_digest": evidence["wheel_manifest_digest"],
            "installed_files": evidence,
        })
        replacement = update.UpdateRequest(**{
            **controller.request.__dict__, "controller_source": "c" * 40,
        })
        recovered = update.InstalledForgeUpdateController(
            replacement, process_reader=lambda: (), reconcile_staged_controller=True,
        )
        with (
            patch.object(update, "assert_selected_installation"),
            patch.object(update, "assert_quiescent"),
            patch.object(update, "_qualified_artifact", return_value=(
                {"wheel_manifest_digest": evidence["wheel_manifest_digest"]}, b"wheel", {},
            )),
            patch.object(update, "_verify_candidate_files", return_value=evidence),
            patch.object(update, "installed_identity", return_value=identity),
        ):
            rebound = recovered._reconcile_staged_controller(
                recovered._state(allow_request_mismatch=True),
                {"user_version": update.transition_schemas(replacement)[0]},
            )
        self.assertEqual(rebound["operation_id"], controller.request.operation_id)
        self.assertEqual(rebound["request_digest"], replacement.digest)
        self.assertEqual(rebound["history"][-1]["event"], "CONTROLLER_RECONCILED")
        slot = update._read_json(recovered.slot_receipt)
        self.assertEqual(slot["request_digest"], replacement.digest)
        self.assertEqual(len(slot["controller_reconciliations"]), 1)

    def test_staged_interpreter_correction_reuses_unadopted_operation(self) -> None:
        controller, state, previous_forge = self._managed_successor_controller()
        mistaken = update.UpdateRequest(**{
            **controller.request.__dict__, "controller_sha256": "sha256:" + "a" * 64,
        })
        state = {**state, "request": mistaken.__dict__, "request_digest": mistaken.digest}
        evidence = {"wheel_manifest_digest": "sha256:" + "1" * 64,
                    "installed_file_count": 7}
        candidate_identity = {"version": controller.request.version,
                              "module": str(controller.slot / "lib/python/site-packages/forge/__init__.py")}
        state = controller._advance(state, "STAGED", candidate=candidate_identity, installed_files=evidence)
        controller.slot.mkdir(parents=True)
        update._atomic_json(controller.slot_receipt, {
            "request_digest": mistaken.digest, "wheel_manifest_digest": evidence["wheel_manifest_digest"],
            "installed_files": evidence,
        })
        prior_wheel = "sha256:" + "4" * 64
        installed_bin = self.runtime_root / "slots" / ("2.7.22-" + "4" * 12) / "bin"
        installed_bin.mkdir(parents=True)
        installed_python = installed_bin / "python"
        installed_python.write_bytes(b"installed-python")
        installed_forge = installed_bin / "forge"
        installed_forge.write_bytes(previous_forge.read_bytes())
        installed_forge.chmod(0o700)
        update._replace_symlink(controller.current, os.path.relpath(installed_forge, self.runtime_root))
        replacement = update.UpdateRequest(**{
            **mistaken.__dict__, "existing_interpreter": str(installed_python),
            "controller_source": "c" * 40, "controller_sha256": update.file_digest(SCRIPT),
        })
        recovered = update.InstalledForgeUpdateController(
            replacement, process_reader=lambda: (), reconcile_staged_controller=True,
        )
        def identity(path, *, cwd):
            if path == Path(mistaken.existing_interpreter):
                return {"version": "2.7.21"}
            if path == installed_python:
                return {"version": "2.7.22", "distribution_version": "2.7.22",
                        "sys_executable": str(path), "module": str(installed_bin.parent / "lib/forge/__init__.py"),
                        "prefix": str(installed_bin.parent)}
            return candidate_identity
        update._atomic_json(installed_bin.parent / "forge-installation-slot.json", {
            "contract_version": update.CONTRACT_VERSION, "version": "2.7.22",
            "wheel_sha256": prior_wheel, "identity": identity(installed_python, cwd=self.runtime_root),
            "installed_files": {"entrypoint_sha256": "sha256:" + "5" * 64},
        })
        with (
            patch.object(update, "assert_selected_installation"),
            patch.object(update, "_qualified_artifact", return_value=(
                {"wheel_manifest_digest": evidence["wheel_manifest_digest"]}, b"wheel", {},
            )),
            patch.object(update, "_verify_candidate_files", return_value=evidence),
            patch.object(update, "installed_identity", side_effect=identity),
        ):
            rebound = recovered._reconcile_staged_controller(
                recovered._state(allow_request_mismatch=True),
                {"user_version": 38, "writer_state": {"dispatcher": [
                    {"status": "IDLE", "active_mission_id": None}], "missions": [],
                    "submissions": [], "generation_permits": [], "planning": [], "operational_reset": []}},
            )
        self.assertEqual(rebound["operation_id"], mistaken.operation_id)
        self.assertEqual(rebound["request_digest"], replacement.digest)
        self.assertEqual(rebound["controller_reconciliations"][-1]["reason"],
                         "PROTECTED_STAGED_INTERPRETER_CORRECTION_BEFORE_ADOPTION")
        self.assertEqual(update._read_json(recovered.slot_receipt)["request_digest"], replacement.digest)

    def test_staged_interpreter_correction_rejects_path_traversal_before_execution(self) -> None:
        controller, state, _previous_forge = self._managed_successor_controller()
        mistaken = update.UpdateRequest(**{
            **controller.request.__dict__, "controller_sha256": "sha256:" + "a" * 64,
        })
        state = {**state, "request": mistaken.__dict__, "request_digest": mistaken.digest}
        controller._advance(state, "STAGED")
        replacement = update.UpdateRequest(**{
            **mistaken.__dict__,
            "existing_interpreter": str(self.runtime_root / "slots" / ".." / "outside" / "bin" / "python"),
            "controller_source": "c" * 40, "controller_sha256": update.file_digest(SCRIPT),
        })
        recovered = update.InstalledForgeUpdateController(
            replacement, process_reader=lambda: (), reconcile_staged_controller=True,
        )
        with (patch.object(update, "assert_selected_installation"),
              patch.object(update, "installed_identity", side_effect=AssertionError("executed untrusted path")),
              self.assertRaisesRegex(update.InstalledForgeUpdateError, "path is not a managed slot")):
            recovered._reconcile_staged_controller(
                recovered._state(allow_request_mismatch=True), {"user_version": 38},
            )

    def test_staged_internal_resolver_request_rebinds_only_to_existing_external_link(self) -> None:
        controller, state, previous_forge = self._managed_successor_controller(fenced=True)
        mistaken = update.UpdateRequest(**{
            **controller.request.__dict__, "resolver": str(controller.stable_resolver),
        })
        state = {
            **state, "request": mistaken.__dict__, "request_digest": mistaken.digest,
            "last_error": "external Forge resolver has an unrecognized managed target",
        }
        evidence = {"wheel_manifest_digest": "sha256:" + "1" * 64}
        identity = {"version": controller.request.version,
                    "module": str(controller.slot / "lib/python/site-packages/forge/__init__.py")}
        state = controller._advance(state, "STAGED", candidate=identity, installed_files=evidence)
        controller.slot.mkdir(parents=True)
        update._atomic_json(controller.slot_receipt, {
            "request_digest": mistaken.digest,
            "wheel_manifest_digest": evidence["wheel_manifest_digest"],
            "installed_files": evidence,
        })
        replacement = update.UpdateRequest(**{
            **controller.request.__dict__, "controller_source": "c" * 40,
        })
        recovered = update.InstalledForgeUpdateController(
            replacement, process_reader=lambda: (), reconcile_staged_controller=True,
        )
        with (
            patch.object(update, "assert_selected_installation"),
            patch.object(update, "assert_quiescent"),
            patch.object(update, "_qualified_artifact", return_value=(
                {"wheel_manifest_digest": evidence["wheel_manifest_digest"]}, b"wheel", {},
            )),
            patch.object(update, "_verify_candidate_files", return_value=evidence),
            patch.object(update, "installed_identity", return_value=identity),
        ):
            rebound = recovered._reconcile_staged_controller(
                recovered._state(allow_request_mismatch=True),
                {"user_version": update.transition_schemas(replacement)[0]},
            )
        self.assertEqual(rebound["request_digest"], replacement.digest)
        self.assertEqual(rebound["controller_reconciliations"][-1]["reason"],
                         "PROTECTED_RESOLVER_CORRECTION_AFTER_PRE_ADOPTION_FAILURE")
        self.assertEqual(recovered._managed_resolver_source(self.resolver, rebound), previous_forge)

    def test_staged_controller_reconciliation_rejects_a_product_change(self) -> None:
        controller, _state, _previous_forge = self._managed_successor_controller(fenced=True)
        changed = update.UpdateRequest(**{
            **controller.request.__dict__, "controller_source": "c" * 40,
            "product_source": "d" * 40,
        })
        recovered = update.InstalledForgeUpdateController(
            changed, process_reader=lambda: (), reconcile_staged_controller=True,
        )
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "conflicts"):
            recovered._reconcile_staged_controller(
                recovered._state(allow_request_mismatch=True), {"user_version": 37},
            )

    def test_run_reuses_a_controller_reconciliation_interrupted_between_audit_writes(self) -> None:
        controller, state, _previous_forge = self._managed_successor_controller(fenced=True)
        evidence = {
            "wheel_manifest_digest": "sha256:" + "1" * 64,
            "installed_file_count": 7,
            "entrypoint_sha256": "sha256:" + "2" * 64,
        }
        identity = {
            "version": controller.request.version,
            "module": str(controller.slot / "lib/python/site-packages/forge/__init__.py"),
        }
        controller._advance(state, "STAGED", candidate=identity, installed_files=evidence)
        controller.slot.mkdir(parents=True)
        update._atomic_json(controller.slot_receipt, {
            "request_digest": controller.request.digest,
            "wheel_manifest_digest": evidence["wheel_manifest_digest"],
            "installed_files": evidence,
        })
        replacement = update.UpdateRequest(**{
            **controller.request.__dict__, "controller_source": "c" * 40,
        })
        schema_before = update.transition_schemas(replacement)[0]
        common_patches = (
            patch.object(update, "database_snapshot", return_value={"user_version": schema_before}),
            patch.object(update, "assert_selected_installation"),
            patch.object(update, "assert_quiescent"),
            patch.object(update, "_qualified_artifact", return_value=(
                {"wheel_manifest_digest": evidence["wheel_manifest_digest"]}, b"wheel", {},
            )),
            patch.object(update, "_verify_candidate_files", return_value=evidence),
            patch.object(update, "installed_identity", return_value=identity),
        )
        interrupted = update.InstalledForgeUpdateController(
            replacement, process_reader=lambda: (),
            reconcile_staged_controller=True,
            interrupt_after="controller_reconciliation_slot",
        )
        with (
            common_patches[0], common_patches[1], common_patches[2],
            common_patches[3], common_patches[4], common_patches[5],
            self.assertRaisesRegex(
                update.InstalledForgeUpdateError, "controller_reconciliation_slot",
            ),
        ):
            interrupted.run()
        slot_after_interrupt = update._read_json(interrupted.slot_receipt)
        state_after_interrupt = update._read_json(interrupted.state_path)
        self.assertEqual(len(slot_after_interrupt["controller_reconciliations"]), 1)
        self.assertNotIn("controller_reconciliations", state_after_interrupt)

        resumed = update.InstalledForgeUpdateController(
            replacement, process_reader=lambda: (),
            reconcile_staged_controller=True, interrupt_after="stage",
        )
        common_patches = (
            patch.object(update, "database_snapshot", return_value={"user_version": schema_before}),
            patch.object(update, "assert_selected_installation"),
            patch.object(update, "assert_quiescent"),
            patch.object(update, "_qualified_artifact", return_value=(
                {"wheel_manifest_digest": evidence["wheel_manifest_digest"]}, b"wheel", {},
            )),
            patch.object(update, "_verify_candidate_files", return_value=evidence),
            patch.object(update, "installed_identity", return_value=identity),
        )
        with (
            common_patches[0], common_patches[1], common_patches[2],
            common_patches[3], common_patches[4], common_patches[5],
            self.assertRaisesRegex(
                update.InstalledForgeUpdateError, "^simulated interruption after stage$",
            ),
        ):
            resumed.run()
        slot_after_resume = update._read_json(resumed.slot_receipt)
        state_after_resume = update._read_json(resumed.state_path)
        self.assertEqual(
            slot_after_resume["controller_reconciliations"],
            state_after_resume["controller_reconciliations"],
        )
        self.assertEqual(len(state_after_resume["controller_reconciliations"]), 1)
        reconciliation_events = [
            event for event in state_after_resume["history"]
            if event.get("event") == "CONTROLLER_RECONCILED"
        ]
        self.assertEqual(len(reconciliation_events), 1)
        self.assertEqual(
            reconciliation_events[0]["at"],
            state_after_resume["controller_reconciliations"][0]["reconciled_at"],
        )

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
        database = self._open_schema38(self.data_root)
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

    def test_wal_source_backup_is_self_contained_after_atomic_rename(self) -> None:
        self._installed_schema37()
        source = self.data_root / "forge.db"
        with sqlite3.connect(source) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        destination = self.root / "backup" / "forge.sqlite3"
        evidence = update._copy_sqlite_backup(source, destination)
        self.assertEqual(evidence["integrity_check"], "ok")
        self.assertFalse(destination.with_name(destination.name + "-wal").exists())
        self.assertFalse(destination.with_name(destination.name + "-shm").exists())
        with sqlite3.connect(destination.resolve().as_uri() + "?mode=ro", uri=True) as readback:
            self.assertEqual(readback.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            self.assertEqual(readback.execute("PRAGMA integrity_check").fetchone()[0], "ok")

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

    def _new_transition(self):
        self._installed_schema37()
        self._open_schema38(self.data_root).close()
        self.request = self._normal_release_request("2.7.25", "2.7.24")
        return update.database_snapshot(self.data_root / "forge.db")

    def _qualified_schema39_copy(self, controller, before):
        copy_root = controller.operation_root / "qualification-copy"
        (copy_root / "instance").mkdir(parents=True)
        (copy_root / "instance" / "runtime-instance.json").write_text(self.runtime_id + "\n")
        update._copy_sqlite_backup(self.data_root / "forge.db", copy_root / "forge.db")
        RuntimeBootstrap(data_root=copy_root, forge_version=self.request.version).open().close()
        after = update.database_snapshot(copy_root / "forge.db")
        update.verify_preservation(before, after, self.request)
        return after

    def test_2724_to_2725_normal_release_and_real_schema39_preserve_history(self):
        before = self._new_transition()
        self.assertEqual(update.validate_qualified_artifact(self.request)["release_route"], "NORMAL")
        self.assertEqual(update.transition_schemas(self.request), (38, 39))
        controller = self._controller()
        self.assertEqual(controller.backup_path.name, "forge-schema38.sqlite3")
        after = self._qualified_schema39_copy(controller, before)
        self.assertEqual(before["user_version"], 38)
        self.assertEqual(after["user_version"], 39)
        self.assertEqual(before["schema_digest"], after["schema_digest"])
        for table in before["tables"]:
            if table != "runtime_metadata":
                self.assertEqual(before["tables"][table], after["tables"][table], table)
        self.assertEqual(before["peer"], after["peer"])
        update.assert_completed_schema(after, {"database_schema_digest": after["schema_digest"]}, self.request)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "schema changed"):
            update.assert_completed_schema(before, {"database_schema_digest": after["schema_digest"]}, self.request)
        with self.assertRaises(update.InstalledForgeUpdateError):
            update.transition_schemas(update.UpdateRequest(**{
                **self.request.__dict__, "existing_version": "2.7.23",
            }))

    def test_schema39_atomic_swap_resume_never_repeats_migration(self):
        before = self._new_transition()
        controller = update.InstalledForgeUpdateController(
            self.request, process_reader=lambda: (), interrupt_after="database_swap",
        )
        self._qualified_schema39_copy(controller, before)
        state = controller._state()
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "database_swap"):
            controller._install_qualified_database(before)
        resumed = self._controller()
        with patch.object(resumed, "_install_qualified_database", side_effect=AssertionError("second migration")):
            reconciled, after = resumed._migrate_live(state, before)
        self.assertEqual(reconciled["phase"], "MIGRATED")
        self.assertEqual(reconciled["safety_disposition"], "CANDIDATE_REQUIRED_SCHEMA_39")
        self.assertEqual(after["user_version"], 39)
        update.verify_preservation(before, after, self.request)
        self.assertEqual((self.data_root / "forge.db").stat().st_mode & 0o777, 0o400)

    def test_schema39_crash_before_swap_keeps_schema38_and_after_migration_fences(self):
        before = self._new_transition()
        controller = update.InstalledForgeUpdateController(
            self.request, process_reader=lambda: (), interrupt_after="database_swap_prepared",
        )
        self._qualified_schema39_copy(controller, before)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "database_swap_prepared"):
            controller._install_qualified_database(before)
        self.assertEqual(update.database_snapshot(self.data_root / "forge.db")["content_digest"], before["content_digest"])
        controller = self._controller()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.24"}):
            state = controller._adopt_resolver(controller._state())
        state = controller._fence(state)
        controller._install_qualified_database(before)
        controller._secure_failure(state, RuntimeError("interrupted"))
        self.assertEqual(self.resolver.resolve(), controller.fenced_resolver.resolve())
        self.assertNotEqual(self.resolver.resolve(), controller.legacy_entrypoint.resolve())

    def _same_schema39_transition(self, *, existing_version="2.7.25", target_version="2.7.26"):
        self._new_transition()
        RuntimeBootstrap(data_root=self.data_root, forge_version=existing_version).open().close()
        before = update.database_snapshot(self.data_root / "forge.db")
        self.request = self._normal_release_request(target_version, existing_version)
        return before

    def test_2725_to_2726_normal_release_preserves_schema39_history(self):
        before = self._same_schema39_transition()
        self.assertEqual(update.validate_qualified_artifact(self.request)["release_route"], "NORMAL")
        self.assertEqual(update.transition_schemas(self.request), (39, 39))
        controller = self._controller()
        self.assertEqual(controller.backup_path.name, "forge-schema39.sqlite3")
        after = self._qualified_schema39_copy(controller, before)
        self.assertEqual(after["user_version"], 39)
        self.assertEqual(after["content_digest"], before["content_digest"])
        self.assertEqual(after["schema_digest"], before["schema_digest"])
        update.verify_preservation(before, after, self.request)
        update.assert_completed_schema(after, {"database_schema_digest": after["schema_digest"]}, self.request)
        with self.assertRaises(update.InstalledForgeUpdateError):
            update.transition_schemas(update.UpdateRequest(**{
                **self.request.__dict__, "existing_version": "2.7.24",
            }))

    def test_2726_rejects_missing_installed_composition_evidence(self):
        self._same_schema39_transition()
        receipt = Path(self.request.qualification_receipt)
        document = json.loads(receipt.read_text())
        del document["qualification"]["criterion_completion"]
        receipt.write_text(json.dumps(document, sort_keys=True))
        changed = update.UpdateRequest(**{
            **self.request.__dict__, "qualification_receipt_sha256": update.file_digest(receipt),
        })
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "noncanonical"):
            update.validate_qualified_artifact(changed)

    def test_terminal_failed_dispatcher_reconciliation_preserves_mission_history(self):
        self._same_schema39_transition(existing_version="2.7.26", target_version="2.7.27")
        path = self.data_root / "forge.db"
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE mission_state SET status='FAILED',document=json_set(document,'$.status','FAILED') WHERE mission_id='MISSION-0001'")
            connection.execute(
                "UPDATE dispatcher_state SET status='ACTIVE',active_mission_id='MISSION-0001',"
                "mission_sequence='[\"MISSION-0001\"]',"
                "document='{\"active_mission_id\":\"MISSION-0001\",\"mission_sequence\":[\"MISSION-0001\"],\"status\":\"ACTIVE\"}' WHERE singleton=1"
            )
        before = update.database_snapshot(path)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "dispatcher"):
            update.assert_quiescent(before)
        with patch.object(update, "installed_identity", return_value={
            "version": self.request.existing_version, "distribution_version": self.request.existing_version,
            "sys_executable": self.request.existing_interpreter,
            "module": str(Path(self.request.existing_interpreter).parent.parent / "lib" / "forge" / "__init__.py"),
            "prefix": str(Path(self.request.existing_interpreter).parent.parent),
        }), update.exclusive_lock(self.data_root / "locks" / "runtime.lock"):
            after = update.reconcile_terminal_dispatcher_for_update(self.request, before, path)
        self.assertEqual(after["writer_state"]["dispatcher"],
                         [{"status": "IDLE", "active_mission_id": None}])
        self.assertEqual(after["tables"]["mission_state"], before["tables"]["mission_state"])
        self.assertEqual(after["tables"]["action_derivations"], before["tables"]["action_derivations"])
        with sqlite3.connect(path) as connection:
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM forge_operational_logs WHERE event='terminal_dispatcher_update_reconciled'"
            ).fetchone()[0], 1)
        replay = update.reconcile_terminal_dispatcher_for_update(self.request, after, path)
        self.assertEqual(replay["content_digest"], after["content_digest"])

    def test_terminal_dispatcher_reconciliation_rejects_active_or_unrelated_mission(self):
        self._same_schema39_transition(existing_version="2.7.26", target_version="2.7.27")
        path = self.data_root / "forge.db"
        with sqlite3.connect(path) as connection:
            connection.execute(
                "UPDATE dispatcher_state SET status='ACTIVE',active_mission_id='MISSION-0001' WHERE singleton=1"
            )
        before = update.database_snapshot(path)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "terminal failed Mission"):
            update.reconcile_terminal_dispatcher_for_update(self.request, before, path)
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE mission_state SET status='FAILED',document=json_set(document,'$.status','FAILED') WHERE mission_id='MISSION-0001'")
            connection.execute(
                "UPDATE dispatcher_state SET active_mission_id='MISSION-OTHER' WHERE singleton=1"
            )
        before = update.database_snapshot(path)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "terminal failed Mission"):
            update.reconcile_terminal_dispatcher_for_update(self.request, before, path)

    def test_terminal_dispatcher_reconciliation_rejects_pending_planning_work(self):
        self._same_schema39_transition(existing_version="2.7.26", target_version="2.7.27")
        path = self.data_root / "forge.db"
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE mission_state SET status='FAILED',document=json_set(document,'$.status','FAILED') WHERE mission_id='MISSION-0001'")
            connection.execute(
                "UPDATE dispatcher_state SET status='ACTIVE',active_mission_id='MISSION-0001' WHERE singleton=1"
            )
            connection.execute(
                "INSERT INTO planning_state VALUES (1,'test','[\"pending\"]','[]','[]','{}','{}','{}')"
            )
        before = update.database_snapshot(path)
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "planning queue"):
            update.reconcile_terminal_dispatcher_for_update(self.request, before, path)
        self.assertEqual(update.database_snapshot(path)["writer_state"]["dispatcher"],
                         [{"status": "ACTIVE", "active_mission_id": "MISSION-0001"}])

    def test_actionful_terminal_dispatcher_requires_bound_ep_disposition(self):
        self._same_schema39_transition(existing_version="2.7.26", target_version="2.7.27")
        path = self.data_root / "forge.db"
        grant_id = "a" * 32
        mission = {
            "mission_id": "MISSION-0001", "status": "FAILED", "waiting_reason": "host_evidence_failed",
            "actions": [{"id": "action-1", "status": "WAITING_FOR_RESULT"}],
            "intents": [{"id": "intent-1"}],
            "execution_correlation": {"request": {"correlation_id": "correlation-1",
                                                   "producer_contract": {"execution_constraints": [
                                                       "ep-merge-delegation:" + grant_id]}}},
            "execution_evidence": {"outcome": "failed"},
            "admission_contract": {"subject_revision": "mission-subject-1",
                                   "mission": {"engineering_constraints": ["ep-merge-delegation:" + grant_id]}},
            "repository_truth": {"revision": "b" * 40,
                                 "source_id": "github-default-head:example/repository:" + "b" * 40},
        }
        binding = {
            "mission_id": "MISSION-0001", "action_id": "action-1", "correlation_id": "correlation-1",
            "submission_id": "submission-1", "host_run_id": "run-1", "project_id": "project-1",
            "repository_id": "repository-1", "submission_receipt": {"accepted_request_digest": "sha256:" + "c" * 64},
        }
        proof = {
            "project": "project-1", "repository": "repository-1",
            "submission": {
                "contract_version": "1.3",
                "submission": {"id": "submission-1", "project_id": "project-1", "repository_id": "repository-1",
                               "accepted_request_digest": "sha256:" + "c" * 64},
                "correlation": {"mission_id": "MISSION-0001", "engineering_action_id": "action-1",
                                "correlation_id": "correlation-1"},
                "run": {"id": "run-1", "operator_resolution": "DISMISSED", "state": "BLOCKED", "terminal": False},
                "disposition": {"state": "DISMISSED", "terminal": True, "execution_eligible": False},
            },
            "delegation": {"status": "REVOKED", "mission_id": "MISSION-0001", "project_id": "project-1",
                           "repository_id": "repository-1", "mission_revision": "mission-subject-1",
                           "delegation_id": grant_id, "github_repository": "example/repository",
                           "base_branch": "main", "roles": ["IMPLEMENTATION"],
                           "revoked_at": "2026-09-20T00:00:00Z"},
        }
        with sqlite3.connect(path) as connection:
            connection.execute("INSERT INTO execution_host_bindings VALUES (?,?)",
                               ("correlation-1", json.dumps(binding)))
        candidate = (Path(self.request.runtime_root) / "slots" /
                     f"{self.request.version}-{self.request.wheel_sha256.removeprefix('sha256:')[:12]}")
        candidate_identity = {"version": self.request.version, "distribution_version": self.request.version,
                              "module": str(candidate / "lib" / "forge" / "__init__.py")}
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
            with patch.object(update, "installed_identity", return_value=candidate_identity), patch.object(
                update, "_run", return_value=SimpleNamespace(stdout=json.dumps(proof))
            ):
                update._prove_terminal_host_authority(self.request, connection, mission)
            proof["submission"]["disposition"]["execution_eligible"] = True
            with patch.object(update, "installed_identity", return_value=candidate_identity), patch.object(
                update, "_run", return_value=SimpleNamespace(stdout=json.dumps(proof))
            ):
                with self.assertRaises(update.InstalledForgeUpdateError):
                    update._prove_terminal_host_authority(self.request, connection, mission)

    def test_2726_to_2727_same_schema_release_preserves_history_and_requires_composition(self):
        before = self._same_schema39_transition(existing_version="2.7.26", target_version="2.7.27")
        self.assertEqual(update.transition_schemas(self.request), (39, 39))
        self.assertEqual(update.validate_qualified_artifact(self.request)["release_route"], "NORMAL")
        controller = self._controller()
        self.assertEqual(controller.backup_path.name, "forge-schema39.sqlite3")
        after = self._qualified_schema39_copy(controller, before)
        self.assertEqual(after["content_digest"], before["content_digest"])
        self.assertEqual(after["schema_digest"], before["schema_digest"])
        update.verify_preservation(before, after, self.request)
        receipt = Path(self.request.qualification_receipt)
        document = json.loads(receipt.read_text())
        del document["qualification"]["criterion_completion"]
        receipt.write_text(json.dumps(document, sort_keys=True))
        changed = update.UpdateRequest(**{
            **self.request.__dict__, "qualification_receipt_sha256": update.file_digest(receipt),
        })
        with self.assertRaisesRegex(update.InstalledForgeUpdateError, "noncanonical"):
            update.validate_qualified_artifact(changed)

    def test_schema39_same_schema_replay_preserves_database_and_fences_after_activation_boundary(self):
        before = self._same_schema39_transition()
        controller = self._controller()
        self._qualified_schema39_copy(controller, before)
        qualified_path = controller.operation_root / "qualification-copy" / "forge.db"
        qualified_connection = sqlite3.connect(qualified_path)
        qualified_connection.execute(
            "UPDATE runtime_metadata SET value=? WHERE key='forge_version'",
            ("2.7.26" if before["metadata"]["forge_version"] != "2.7.26" else "2.7.25",),
        )
        qualified_connection.commit()
        qualified_connection.close()
        with patch.object(update, "installed_identity", return_value={"version": "2.7.25"}):
            state = controller._adopt_resolver(controller._state())
        original_inode = (self.data_root / "forge.db").stat().st_ino
        current = update.database_snapshot(self.data_root / "forge.db")
        qualified = update.database_snapshot(controller.operation_root / "qualification-copy" / "forge.db")
        self.assertEqual(current["content_digest"], before["content_digest"])
        self.assertNotEqual(qualified["content_digest"], before["content_digest"])
        self.assertEqual(qualified["schema_digest"], before["schema_digest"])
        self.assertEqual(qualified["writer_state"], before["writer_state"])
        self.assertEqual(set(qualified["metadata"]), set(before["metadata"]))
        update.verify_preservation(before, qualified, self.request)
        with patch.object(controller, "_install_qualified_database", side_effect=AssertionError("database swap")):
            migrated, after = controller._migrate_live(state, before)
        self.assertEqual(migrated["phase"], "MIGRATED")
        self.assertEqual(migrated["live_migration"]["application_mode"], "UNCHANGED_DATABASE")
        self.assertEqual(after["content_digest"], before["content_digest"])
        self.assertEqual((self.data_root / "forge.db").stat().st_ino, original_inode)
        resumed = self._controller()
        with patch.object(resumed, "_install_qualified_database", side_effect=AssertionError("second swap")):
            reconciled, after = resumed._migrate_live(migrated, before)
        self.assertEqual(reconciled["phase"], "MIGRATED")
        self.assertEqual(reconciled["safety_disposition"], "CANDIDATE_REQUIRED_SCHEMA_39")
        self.assertEqual(after["content_digest"], before["content_digest"])
        resumed._secure_failure(reconciled, RuntimeError("interrupted"))
        self.assertEqual(self.resolver.resolve(), resumed.fenced_resolver.resolve())
        self.assertNotEqual(self.resolver.resolve(), resumed.legacy_entrypoint.resolve())

    def test_2727_same_schema_activation_never_swaps_live_database(self):
        before = self._same_schema39_transition(existing_version="2.7.26", target_version="2.7.27")
        controller = self._controller()
        self._qualified_schema39_copy(controller, before)
        with patch.object(update, "installed_identity", return_value={"version": "2.7.26"}):
            state = controller._adopt_resolver(controller._state())
        original_inode = (self.data_root / "forge.db").stat().st_ino
        with patch.object(controller, "_install_qualified_database", side_effect=AssertionError("database swap")):
            migrated, after = controller._migrate_live(state, before)
        self.assertEqual(migrated["phase"], "MIGRATED")
        self.assertEqual(migrated["live_migration"]["application_mode"], "UNCHANGED_DATABASE")
        self.assertEqual(after["content_digest"], before["content_digest"])
        self.assertEqual((self.data_root / "forge.db").stat().st_ino, original_inode)
        controller._secure_failure(migrated, RuntimeError("interrupted"))
        self.assertEqual(self.resolver.resolve(), controller.fenced_resolver.resolve())

    def test_exact_published_wheel_end_to_end_when_requested(self) -> None:
        wheel_value = os.environ.get("FORGE_EXACT_WHEEL")
        receipt_value = os.environ.get("FORGE_EXACT_RELEASE_RECEIPT")
        if not wheel_value or not receipt_value:
            self.skipTest("exact published wheel paths were not supplied")
        self._installed_schema37()
        wheel = Path(wheel_value).resolve()
        receipt = Path(receipt_value).resolve()
        release = json.loads(receipt.read_text(encoding="utf-8"))
        target_version = release["version"]
        target_schema = 39 if target_version in {"2.7.25", "2.7.26", "2.7.27"} else 38
        previous_version = {"2.7.26": "2.7.25", "2.7.27": "2.7.26"}.get(target_version)
        if previous_version is not None:
            RuntimeBootstrap(data_root=self.data_root, forge_version=previous_version).open().close()
        legacy_interpreter = Path(os.environ.get("FORGE_LEGACY_INTERPRETER", sys.executable))
        try:
            legacy_identity = update.installed_identity(legacy_interpreter, cwd=self.root)
        except update.InstalledForgeUpdateError as error:
            self.skipTest(f"legacy Forge interpreter was not supplied: {error}")
        request = update.UpdateRequest(**{
            **self.request.__dict__,
            "version": target_version,
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
        self.assertEqual(update.database_snapshot(self.data_root / "forge.db")["user_version"], target_schema)
        self.assertEqual(controller.run(), completed)
        self.assertEqual((self.data_root / "forge.db").stat().st_mode & 0o777, 0o600)
        connection = sqlite3.connect(self.data_root / "forge.db")
        connection.execute(f"PRAGMA user_version={target_schema - 1}")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(update.InstalledForgeUpdateError,
                                    "schema changed|selected runtime schema is outside"):
            controller.run()


if __name__ == "__main__":
    unittest.main()
