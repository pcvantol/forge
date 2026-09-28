from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from forge.__main__ import main
from forge.installed_lifecycle import InstalledLifecycleError
from forge.preserved_lifecycle import (
    InstalledPreserveDispatcher,
    InstalledPurgeDispatcher,
    InstalledRestoreDispatcher,
    InstanceLifecycleRequest,
    RestoreRequest,
    lifecycle_status,
)
from forge.runtime import RuntimeBootstrap


class PreservedLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.instances_root = self.root / "instances"
        self.instances_root.mkdir()
        self.data_root = self.instances_root / "forge-primary"
        database = RuntimeBootstrap(data_root=self.data_root, forge_version="2.7.35").open()
        self.runtime_id = database.runtime_identity.runtime_id
        self.installation_id = database.metadata["installation_id"]
        database.close()
        self.installed_source = "a" * 40
        self.installed_artifact_digest = "sha256:" + "b" * 64

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self, operation_id: str) -> InstanceLifecycleRequest:
        return InstanceLifecycleRequest(
            operation_id=operation_id,
            instance_id=self.runtime_id,
            runtime_id=self.runtime_id,
            installation_id=self.installation_id,
            installed_version="2.7.35",
            installed_source=self.installed_source,
            installed_artifact_digest=self.installed_artifact_digest,
            data_root=str(self.data_root),
            instances_root=str(self.instances_root),
        )

    def restore_request(self, operation_id: str, preserve: str) -> RestoreRequest:
        return RestoreRequest(
            operation_id=operation_id,
            instance_id=self.runtime_id,
            runtime_id=self.runtime_id,
            installation_id=self.installation_id,
            installed_version="2.7.35",
            installed_source=self.installed_source,
            installed_artifact_digest=self.installed_artifact_digest,
            data_root=str(self.data_root),
            instances_root=str(self.instances_root),
            preserve_operation_id=preserve,
        )

    def test_preserve_and_restore_keep_same_identity_and_data(self) -> None:
        marker = self.data_root / "owner-config.json"
        marker.write_text('{"keep":true}\n', encoding="utf-8")
        preserved = InstalledPreserveDispatcher(self.request("preserve-0001")).run()
        self.assertEqual(preserved["lifecycle_state"], "UNINSTALLED_DATA_PRESERVED")
        self.assertEqual(preserved["instance_identity"], "PRESERVED")
        self.assertEqual(preserved["mutable_instance_data"], "PRESERVED")
        self.assertTrue(preserved["restorable"])
        self.assertEqual(preserved["service_state"], "REMOVED_OR_INACTIVE")
        self.assertEqual(
            preserved["provider_auth_state"], "PRESERVED_REQUIRES_REVERIFICATION"
        )
        self.assertTrue(self.data_root.is_dir())
        self.assertEqual(marker.read_text(encoding="utf-8"), '{"keep":true}\n')

        restored = InstalledRestoreDispatcher(
            self.restore_request("restore-0001", "preserve-0001")
        ).run()
        self.assertEqual(restored["lifecycle_state"], "RESTORE_VALIDATED")
        self.assertEqual(restored["instance_identity"], "PRESERVED")
        self.assertEqual(restored["provider_auth_state"], "PRESERVED_REQUIRES_REVERIFICATION")
        self.assertFalse(restored["ready"])
        self.assertEqual(marker.read_text(encoding="utf-8"), '{"keep":true}\n')

    def test_restore_fails_closed_after_preserved_data_tamper(self) -> None:
        InstalledPreserveDispatcher(self.request("preserve-0001")).run()
        (self.data_root / "tamper").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(InstalledLifecycleError, "no longer matches"):
            InstalledRestoreDispatcher(
                self.restore_request("restore-0001", "preserve-0001")
            ).run()

    def test_restore_rejects_source_or_artifact_identity_drift(self) -> None:
        InstalledPreserveDispatcher(self.request("preserve-0001")).run()
        request = self.restore_request("restore-drift", "preserve-0001")
        changed = RestoreRequest(
            **{
                **request.__dict__,
                "installed_source": "c" * 40,
            }
        )
        with self.assertRaisesRegex(InstalledLifecycleError, "does not authorize"):
            InstalledRestoreDispatcher(changed).run()

    def test_purge_is_destructive_and_invalidates_preserve(self) -> None:
        InstalledPreserveDispatcher(self.request("preserve-0001")).run()
        purge = InstalledPurgeDispatcher(self.request("purge-0001")).run()
        self.assertEqual(purge["lifecycle_state"], "PURGED")
        self.assertFalse(purge["restorable"])
        self.assertFalse(self.data_root.exists())
        with self.assertRaisesRegex(InstalledLifecycleError, "purged instance"):
            InstalledRestoreDispatcher(
                self.restore_request("restore-0001", "preserve-0001")
            ).run()
        status = lifecycle_status(
            str(self.instances_root), self.runtime_id, "purge-0001"
        )
        self.assertEqual(status["state"], "COMPLETE")
        self.assertEqual(status["lifecycle_state"], "PURGED")

    def test_interrupted_preserve_and_restore_resume_same_operation(self) -> None:
        preserve_request = self.request("preserve-interrupt")
        with self.assertRaises(InterruptedError):
            InstalledPreserveDispatcher(
                preserve_request, interrupt_after="verified"
            ).run()
        first = InstalledPreserveDispatcher(preserve_request).run()
        self.assertEqual(first, InstalledPreserveDispatcher(preserve_request).run())

        restore_request = self.restore_request("restore-interrupt", "preserve-interrupt")
        with self.assertRaises(InterruptedError):
            InstalledRestoreDispatcher(
                restore_request, interrupt_after="verified"
            ).run()
        restored = InstalledRestoreDispatcher(restore_request).run()
        self.assertEqual(restored, InstalledRestoreDispatcher(restore_request).run())

    def test_purge_resume_after_underlying_uninstall_is_idempotent(self) -> None:
        request = self.request("purge-interrupt")
        with self.assertRaises(InterruptedError):
            InstalledPurgeDispatcher(request, interrupt_after="uninstalled").run()
        self.assertFalse(self.data_root.exists())
        first = InstalledPurgeDispatcher(request).run()
        second = InstalledPurgeDispatcher(request).run()
        self.assertEqual(first, second)

    def test_sibling_instance_is_unchanged(self) -> None:
        sibling = self.instances_root / "forge-sibling"
        sibling.mkdir()
        marker = sibling / "keep"
        marker.write_text("unchanged", encoding="utf-8")
        InstalledPreserveDispatcher(self.request("preserve-0001")).run()
        self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
        InstalledPurgeDispatcher(self.request("purge-0001")).run()
        self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")

    def test_operation_identity_cannot_be_rebound(self) -> None:
        request = self.request("preserve-rebind")
        with self.assertRaises(InterruptedError):
            InstalledPreserveDispatcher(request, interrupt_after="verified").run()
        changed = InstanceLifecycleRequest(
            **{**request.__dict__, "installation_id": "installation-other"}
        )
        with self.assertRaisesRegex(InstalledLifecycleError, "another lifecycle request"):
            InstalledPreserveDispatcher(changed).run()

    def test_cli_exposes_new_semantics_without_changing_uninstall(self) -> None:
        common = [
            "--operation-id", "preserve-cli-0001",
            "--instances-root", str(self.instances_root),
            "--instance-id", self.runtime_id,
            "--runtime-id", self.runtime_id,
            "--installation-id", self.installation_id,
            "--installed-version", "2.7.35",
            "--installed-source", self.installed_source,
            "--installed-artifact-digest", self.installed_artifact_digest,
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-root", str(self.data_root), "server", "preserve", *common,
            ])
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(output.getvalue())["lifecycle_state"],
            "UNINSTALLED_DATA_PRESERVED",
        )


if __name__ == "__main__":
    unittest.main()
