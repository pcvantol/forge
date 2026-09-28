from __future__ import annotations

import base64
from contextlib import redirect_stdout
import csv
from hashlib import sha256
from io import StringIO
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from forge.installed_lifecycle import (
    CONTROL_DIRECTORY,
    InstalledLifecycleError,
    InstalledUninstallDispatcher,
    UninstallRequest,
    UpdateAssessmentRequest,
    assess_update,
    uninstall_status,
    validate_candidate_wheel,
)
from forge.__main__ import main
from forge.runtime import RuntimeBootstrap

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def _digest(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def _write_wheel(root: Path, version: str) -> tuple[Path, str]:
    path = root / f"forge_autonomy-{version}-py3-none-any.whl"
    dist = f"forge_autonomy-{version}.dist-info"
    members = {
        "forge/__init__.py": b'"""candidate"""\n',
        f"{dist}/METADATA": f"Metadata-Version: 2.4\nName: forge-autonomy\nVersion: {version}\n".encode(),
        f"{dist}/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = f"{dist}/RECORD"
    rows = []
    for name, payload in members.items():
        encoded = base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b"=").decode()
        rows.append((name, f"sha256={encoded}", str(len(payload))))
    rows.append((record, "", ""))
    output = StringIO()
    csv.writer(output, lineterminator="\n").writerows(rows)
    members[record] = output.getvalue().encode()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return path, _digest(path.read_bytes())


def _tree_fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): _digest(path.read_bytes())
        for path in sorted(root.rglob("*")) if path.is_file()
    }


class InstalledLifecycleFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.instances_root = self.root / "instances"
        self.instances_root.mkdir()
        self.data_root = self.instances_root / "forge-primary"
        database = RuntimeBootstrap(data_root=self.data_root, forge_version="2.7.34").open()
        self.runtime_id = database.runtime_identity.runtime_id
        self.installation_id = database.metadata["installation_id"]
        database.close()
        self.source = "a" * 40
        self.installed_digest = "sha256:" + "b" * 64

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assessment(self, version: str = "2.7.35", **changes: str) -> dict[str, object]:
        if "candidate_wheel" in changes and "candidate_artifact_digest" in changes:
            wheel, digest = Path(changes["candidate_wheel"]), changes["candidate_artifact_digest"]
        else:
            wheel, digest = _write_wheel(self.root, version)
        values = {
            "data_root": str(self.data_root),
            "runtime_id": self.runtime_id,
            "installation_id": self.installation_id,
            "installed_version": "2.7.34",
            "installed_source": self.source,
            "installed_artifact_digest": self.installed_digest,
            "candidate_version": version,
            "candidate_source": "c" * 40,
            "candidate_wheel": str(wheel),
            "candidate_artifact_digest": digest,
        }
        values.update(changes)
        return assess_update(UpdateAssessmentRequest(**values))

    def uninstall_request(self, **changes: str) -> UninstallRequest:
        values = {
            "operation_id": "forge-uninstall-test-001",
            "instance_id": self.runtime_id,
            "runtime_id": self.runtime_id,
            "installation_id": self.installation_id,
            "data_root": str(self.data_root),
            "instances_root": str(self.instances_root),
        }
        values.update(changes)
        return UninstallRequest(**values)


class UpdateAssessmentTests(InstalledLifecycleFixture):
    def test_supported_exact_candidate_is_update_available_without_writes(self) -> None:
        wheel, digest = _write_wheel(self.root, "2.7.35")
        before = _tree_fingerprint(self.root)
        result = self.assessment(candidate_wheel=str(wheel), candidate_artifact_digest=digest)
        self.assertEqual(result["state"], "UPDATE_AVAILABLE")
        self.assertEqual(result["reason_codes"], ["EXACT_SUPPORTED_TRANSITION"])
        self.assertFalse(result["mutating"])
        self.assertEqual(_tree_fingerprint(self.root), before)

    def test_exact_current_artifact_is_up_to_date(self) -> None:
        wheel, digest = _write_wheel(self.root, "2.7.34")
        result = self.assessment(
            "2.7.34", candidate_source=self.source, candidate_wheel=str(wheel),
            candidate_artifact_digest=digest, installed_artifact_digest=digest,
        )
        self.assertEqual(result["state"], "UP_TO_DATE")

    def test_valid_unsupported_transition_is_incompatible(self) -> None:
        self.assertEqual(self.assessment("3.0.0")["state"], "INCOMPATIBLE")

    def test_declared_server_baselines_assess_directly_to_2738(self) -> None:
        wheel, digest = _write_wheel(self.root, "2.7.38")
        for installed in ("2.7.35", "2.7.36", "2.7.37"):
            data_root = self.instances_root / installed
            database = RuntimeBootstrap(data_root=data_root, forge_version=installed).open()
            runtime_id = database.runtime_identity.runtime_id
            installation_id = database.metadata["installation_id"]
            database.close()
            result = assess_update(UpdateAssessmentRequest(
                data_root=str(data_root), runtime_id=runtime_id, installation_id=installation_id,
                installed_version=installed, installed_source="a" * 40,
                installed_artifact_digest="sha256:" + "b" * 64,
                candidate_version="2.7.38", candidate_source="c" * 40,
                candidate_wheel=str(wheel), candidate_artifact_digest=digest,
            ))
            self.assertEqual(result["state"], "UPDATE_AVAILABLE", installed)

    def test_identity_or_artifact_uncertainty_fails_closed(self) -> None:
        self.assertEqual(self.assessment(runtime_id="runtime-wrong")["state"], "UNKNOWN")
        result = self.assessment(candidate_artifact_digest="sha256:" + "0" * 64)
        self.assertEqual(result["state"], "UNKNOWN")
        self.assertEqual(result["reason_codes"], ["ASSESSMENT_FAILED_CLOSED"])

    def test_candidate_wheel_rejects_noncanonical_record(self) -> None:
        wheel, digest = _write_wheel(self.root, "2.7.35")
        with zipfile.ZipFile(wheel, "a") as archive:
            archive.writestr("forge/extra.py", b"unsafe omission")
        with self.assertRaises(InstalledLifecycleError):
            validate_candidate_wheel(wheel, "2.7.35", _digest(wheel.read_bytes()))
        self.assertNotEqual(digest, _digest(wheel.read_bytes()))

    def test_packaged_cli_emits_the_product_owned_assessment(self) -> None:
        wheel, digest = _write_wheel(self.root, "2.7.35")
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-root", str(self.data_root), "server", "update-assess",
                "--runtime-id", self.runtime_id, "--installation-id", self.installation_id,
                "--installed-version", "2.7.34", "--installed-source", self.source,
                "--installed-artifact-digest", self.installed_digest,
                "--candidate-version", "2.7.35", "--candidate-source", "c" * 40,
                "--candidate-wheel", str(wheel), "--candidate-artifact-digest", digest,
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["state"], "UPDATE_AVAILABLE")


class UninstallDispatcherTests(InstalledLifecycleFixture):
    def test_removes_only_exact_instance_and_replays_receipt(self) -> None:
        other = self.instances_root / "forge-other"
        other.mkdir()
        (other / "keep").write_text("other", encoding="utf-8")
        dispatcher = InstalledUninstallDispatcher(self.uninstall_request(), clock=lambda: "2026-09-27T00:00:00Z")
        first = dispatcher.run()
        second = dispatcher.run()
        self.assertEqual(first, second)
        self.assertEqual(first["state"], "COMPLETE")
        self.assertEqual(first["mutable_instance_data"], "REMOVED")
        self.assertEqual(first["immutable_runtime_slots"], "PRESERVED")
        self.assertFalse(self.data_root.exists())
        self.assertEqual((other / "keep").read_text(encoding="utf-8"), "other")
        status = uninstall_status(str(self.instances_root), self.runtime_id, "forge-uninstall-test-001")
        self.assertEqual(status["state"], "COMPLETE")
        self.assertEqual(status["receipt_digest"], first["receipt_digest"])

    def test_resume_after_durable_detach_does_not_target_another_instance(self) -> None:
        request = self.uninstall_request()
        interrupted = InstalledUninstallDispatcher(request, interrupt_after="detached")
        with self.assertRaises(InterruptedError):
            interrupted.run()
        self.assertFalse(self.data_root.exists())
        self.assertTrue(interrupted.quarantine.exists())
        receipt = InstalledUninstallDispatcher(request).run()
        self.assertEqual(receipt["state"], "COMPLETE")
        self.assertFalse(interrupted.quarantine.exists())

    def test_resume_after_verification_revalidates_exact_target(self) -> None:
        request = self.uninstall_request()
        with self.assertRaises(InterruptedError):
            InstalledUninstallDispatcher(request, interrupt_after="verified").run()
        status = uninstall_status(str(self.instances_root), self.runtime_id, request.operation_id)
        self.assertEqual(status["state"], "IN_PROGRESS")
        self.assertEqual(status["phase"], "VERIFIED")
        self.assertTrue(self.data_root.exists())
        receipt = InstalledUninstallDispatcher(request).run()
        self.assertEqual(receipt["state"], "COMPLETE")

    def test_resume_after_removal_reconstructs_terminal_receipt(self) -> None:
        request = self.uninstall_request()
        with self.assertRaises(InterruptedError):
            InstalledUninstallDispatcher(request, interrupt_after="removed").run()
        self.assertFalse(self.data_root.exists())
        self.assertEqual(InstalledUninstallDispatcher(request).run()["state"], "COMPLETE")

    def test_missing_initial_target_and_corrupt_terminal_receipt_fail_closed(self) -> None:
        missing = self.instances_root / "missing"
        request = self.uninstall_request(data_root=str(missing))
        with self.assertRaisesRegex(InstalledLifecycleError, "disappeared"):
            InstalledUninstallDispatcher(request).run()
        dispatcher = InstalledUninstallDispatcher(self.uninstall_request(operation_id="forge-uninstall-corrupt"))
        dispatcher.run()
        dispatcher.receipt_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(InstalledLifecycleError, "inconsistent"):
            dispatcher.run()

    def test_active_mission_blocks_removal_and_preserves_instance(self) -> None:
        connection = sqlite3.connect(self.data_root / "forge.db")
        connection.execute(
            "INSERT INTO dispatcher_state VALUES (1,'ACTIVE',NULL,'[]','{}')"
        )
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(InstalledLifecycleError, "not durably idle"):
            InstalledUninstallDispatcher(self.uninstall_request()).run()
        self.assertTrue((self.data_root / "forge.db").is_file())

    def test_wrong_identity_and_nested_path_fail_before_removal(self) -> None:
        with self.assertRaisesRegex(InstalledLifecycleError, "does not bind"):
            InstalledUninstallDispatcher(self.uninstall_request(runtime_id="runtime-wrong"))
        nested = self.data_root / "nested"
        nested.mkdir()
        with self.assertRaisesRegex(InstalledLifecycleError, "direct managed"):
            InstalledUninstallDispatcher(self.uninstall_request(data_root=str(nested)))
        self.assertTrue(self.data_root.exists())

    def test_symbolic_link_in_instance_fails_closed(self) -> None:
        (self.data_root / "unsafe-link").symlink_to(self.root / "outside")
        with self.assertRaisesRegex(InstalledLifecycleError, "symbolic link"):
            InstalledUninstallDispatcher(self.uninstall_request()).run()
        self.assertTrue(self.data_root.exists())

    def test_hardlinked_file_fails_closed(self) -> None:
        foreign = self.root / "foreign-hardlink-source"
        foreign.write_text("foreign", encoding="utf-8")
        (self.data_root / "unsafe-hardlink").hardlink_to(foreign)
        self.assertEqual((self.data_root / "unsafe-hardlink").stat().st_nlink, 2)
        with self.assertRaisesRegex(InstalledLifecycleError, "hardlinked"):
            InstalledUninstallDispatcher(self.uninstall_request()).run()
        self.assertTrue(self.data_root.exists())

    def test_group_or_world_writable_tree_fails_closed(self) -> None:
        self.data_root.chmod(0o777)
        with self.assertRaisesRegex(InstalledLifecycleError, "group/world writable"):
            InstalledUninstallDispatcher(self.uninstall_request(operation_id="unsafe-root")).run()
        self.data_root.chmod(0o700)

        unsafe_directory = self.data_root / "unsafe-directory"
        unsafe_directory.mkdir(mode=0o700)
        unsafe_directory.chmod(0o772)
        with self.assertRaisesRegex(InstalledLifecycleError, "group/world writable"):
            InstalledUninstallDispatcher(self.uninstall_request(operation_id="unsafe-directory")).run()
        unsafe_directory.chmod(0o700)

        unsafe_file = self.data_root / "unsafe-file"
        unsafe_file.write_text("unsafe", encoding="utf-8")
        unsafe_file.chmod(0o666)
        with self.assertRaisesRegex(InstalledLifecycleError, "group/world writable"):
            InstalledUninstallDispatcher(self.uninstall_request(operation_id="unsafe-file")).run()
        self.assertTrue(self.data_root.exists())

    @unittest.skipIf(fcntl is None, "POSIX lock qualification")
    def test_live_server_lock_blocks_uninstall(self) -> None:
        lock = (self.data_root / "locks" / "forge-server-runtime.lock").open("a+")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(InstalledLifecycleError, "concurrent runtime activity"):
                InstalledUninstallDispatcher(self.uninstall_request()).run()
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()
        self.assertTrue(self.data_root.exists())

    def test_completed_operation_refuses_recreated_target(self) -> None:
        dispatcher = InstalledUninstallDispatcher(self.uninstall_request())
        dispatcher.run()
        self.data_root.mkdir()
        with self.assertRaisesRegex(InstalledLifecycleError, "recreated"):
            dispatcher.run()

    def test_operation_id_cannot_be_rebound(self) -> None:
        request = self.uninstall_request()
        with self.assertRaises(InterruptedError):
            InstalledUninstallDispatcher(request, interrupt_after="verified").run()
        changed = self.uninstall_request(installation_id="installation-other")
        with self.assertRaisesRegex(InstalledLifecycleError, "another uninstall request"):
            InstalledUninstallDispatcher(changed).run()

    def test_invalid_request_shapes_are_rejected(self) -> None:
        with self.assertRaisesRegex(InstalledLifecycleError, "safe opaque identity"):
            InstalledUninstallDispatcher(self.uninstall_request(operation_id="../escape"))
        with self.assertRaisesRegex(InstalledLifecycleError, "absolute"):
            InstalledUninstallDispatcher(self.uninstall_request(instances_root="relative"))

    def test_control_evidence_is_outside_removed_root(self) -> None:
        dispatcher = InstalledUninstallDispatcher(self.uninstall_request())
        receipt = dispatcher.run()
        self.assertTrue(dispatcher.receipt_path.is_file())
        self.assertTrue(dispatcher.receipt_path.is_relative_to(self.instances_root / CONTROL_DIRECTORY))
        self.assertEqual(json.loads(dispatcher.receipt_path.read_text())["receipt_digest"], receipt["receipt_digest"])

    def test_packaged_cli_dispatches_and_reads_durable_uninstall(self) -> None:
        common = [
            "--operation-id", "forge-uninstall-cli-001", "--instances-root", str(self.instances_root),
            "--instance-id", self.runtime_id,
        ]
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([
                "--data-root", str(self.data_root), "server", "uninstall", *common,
                "--runtime-id", self.runtime_id, "--installation-id", self.installation_id,
            ])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["state"], "COMPLETE")
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["server", "uninstall-status", *common])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["state"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
