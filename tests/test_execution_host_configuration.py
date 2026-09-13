"""Qualification of the durable, secret-free EP peer configuration boundary."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from forge.__main__ import main
from forge.execution_host_configuration import (
    EngineeringPlatformExecutionHostFactory,
    EngineeringPlatformPeerConfigurationService,
    PeerConfigurationConflict,
    PeerConfigurationError,
    read_peer_configuration,
)
from forge.runtime import RuntimeBootstrap
from forge.runtime.database import RUNTIME_SCHEMA_VERSION
from forge.scheduler.ep_http_adapter import EngineeringPlatformHttpExecutionHost
from forge.secure_store import SecretReference, SecretState


SYNTHETIC_SECRET = "EP_QUALIFICATION_BEARER_MATERIAL_G017"


class _Resolver:
    def __init__(self, state: SecretState = SecretState.RESOLVABLE) -> None:
        self.state = state
        self.references: list[str] = []

    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        self.references.append(reference.serialized)
        return self.state, SYNTHETIC_SECRET if self.state is SecretState.RESOLVABLE else None


class _Response:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def read(self, limit: int | None = None) -> bytes:
        return self.value if limit is None else self.value[:limit]


class DurableExecutionHostConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "forge-data"
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.runtime_id = database.runtime_identity.runtime_id
        database.close()
        self.service = EngineeringPlatformPeerConfigurationService(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def values(self, **changes: object) -> dict[str, object]:
        values: dict[str, object] = {
            "binding_id": "ep-primary",
            "endpoint": "https://ep.test",
            "expected_ep_instance_id": "ep-instance-1",
            "execution_host_id": "engineering-platform",
            "ep_project_id": "forge-project",
            "ep_repository_id": "forge-repository",
            "repository_identity": "forge-source",
            "credential_reference": SecretReference.parse("keychain://forge.ep/consumer"),
            "operator_id": "local-admin",
            "occurred_at": "2026-09-10T18:00:00Z",
        }
        values.update(changes)
        return values

    def test_configuration_is_idempotent_guarded_secret_free_and_survives_reopen(self) -> None:
        first = self.service.configure(**self.values())
        same = self.service.configure(**self.values(operator_id="other-admin", occurred_at="2026-09-10T18:01:00Z"))
        self.assertEqual(same, first)
        with self.assertRaises(PeerConfigurationConflict):
            self.service.configure(**self.values(endpoint="https://other.test"))
        with self.assertRaises(PeerConfigurationConflict):
            self.service.configure(**self.values(endpoint="https://other.test", replace=True,
                                                  expected_revision=1, expected_digest="sha256:" + "0" * 64))
        replaced = self.service.configure(**self.values(
            endpoint="https://other.test", replace=True, expected_revision=first.configuration_revision,
            expected_digest=first.configuration_digest, occurred_at="2026-09-10T18:02:00Z",
        ))
        self.assertEqual(replaced.configuration_revision, 2)
        self.assertEqual((replaced.created_at, replaced.updated_at),
                         ("2026-09-10T18:00:00Z", "2026-09-10T18:02:00Z"))

        reopened = read_peer_configuration(self.root).configuration
        self.assertEqual(reopened, replaced)
        persisted = (self.root / "forge.db").read_bytes()
        self.assertNotIn(SYNTHETIC_SECRET.encode(), persisted)
        self.assertIn(b"keychain://forge.ep/consumer", persisted)

    def test_configuration_change_is_recorded_in_the_redacted_operational_journal(self) -> None:
        first = self.service.configure(**self.values())
        self.service.configure(**self.values(operator_id="other-admin", occurred_at="2026-09-10T18:01:00Z"))
        self.service.configure(**self.values(
            endpoint="https://replacement.test", replace=True,
            expected_revision=first.configuration_revision, expected_digest=first.configuration_digest,
            occurred_at="2026-09-10T18:02:00Z",
        ))
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        try:
            page = database.operational_log_page(
                events=("execution_host_configuration_created", "execution_host_configuration_unchanged",
                        "execution_host_configuration_replaced"), page_size=10,
            )
            self.assertEqual(page["total"], 3)
            events = {item["event"] for item in page["items"]}
            self.assertEqual(events, {
                "execution_host_configuration_created", "execution_host_configuration_unchanged",
                "execution_host_configuration_replaced",
            })
            event = next(item for item in page["items"] if item["event"] == "execution_host_configuration_created")
            self.assertEqual((event["component"], event["level"]), ("forge_execution_host", "INFO"))
            self.assertEqual(event["details"]["ep_instance_id"], "ep-instance-1")
            self.assertNotIn("credential_reference", event["details"])
            self.assertNotIn(SYNTHETIC_SECRET, json.dumps(event, sort_keys=True))
        finally:
            database.close()

    def test_factory_reopens_configuration_and_real_keychain_resolver_path_without_constructor_inputs(self) -> None:
        configured = self.service.configure(**self.values())
        resolver = _Resolver()
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        try:
            host = EngineeringPlatformExecutionHostFactory(resolver).from_database(database)
            self.assertIsInstance(host, EngineeringPlatformHttpExecutionHost)
            self.assertEqual(host.config.base_url, configured.endpoint)
            self.assertEqual(host.config.project_id, configured.ep_project_id)
            self.assertEqual(host.config.repository_id, configured.ep_repository_id)
            self.assertEqual(resolver.references, ["keychain://forge.ep/consumer"])
            self.assertNotIn(SYNTHETIC_SECRET, repr(host.config))
        finally:
            database.close()

        observed: list[list[str]] = []
        result = subprocess.CompletedProcess([], 0, stdout=SYNTHETIC_SECRET + "\n", stderr="")
        from forge.secure_store import MacOSKeychainSecureStoreAdapter
        store = MacOSKeychainSecureStoreAdapter(
            runner=lambda argv, **_kwargs: observed.append(argv) or result,
        )
        state, material = store.resolve(SecretReference.parse("keychain://forge.ep/consumer"))
        self.assertEqual((state, material), (SecretState.RESOLVABLE, SYNTHETIC_SECRET))
        self.assertEqual(observed[0], ["/usr/bin/security", "find-generic-password", "-s", "forge.ep",
                                      "-a", "consumer", "-w"])

    def test_missing_unknown_or_unsafe_configuration_fails_closed(self) -> None:
        absent = Path(self.temporary.name) / "absent-root"
        with self.assertRaises(PeerConfigurationError):
            EngineeringPlatformPeerConfigurationService(absent).show()
        self.assertFalse(absent.exists())
        with self.assertRaises(ValueError):
            SecretReference.parse("env://EP_TOKEN/value")
        with self.assertRaises(PeerConfigurationError):
            self.service.configure(**self.values(endpoint="http://ep.internal", allow_loopback_http=True))
        with self.assertRaises(PeerConfigurationError):
            self.service.configure(**self.values(endpoint="https://user:password@ep.test"))
        self.service.configure(**self.values())
        with self.assertRaisesRegex(PeerConfigurationError, "MISSING") as error:
            EngineeringPlatformExecutionHostFactory(_Resolver(SecretState.MISSING)).from_data_root(self.root)
        self.assertNotIn(SYNTHETIC_SECRET, str(error.exception))

    def test_read_only_show_and_status_do_not_change_database_bytes(self) -> None:
        configured = self.service.configure(**self.values())
        before = (self.root / "forge.db").read_bytes()
        self.assertEqual(self.service.show(), configured)
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["--data-root", str(self.root), "status"]), 0)
        self.assertEqual((self.root / "forge.db").read_bytes(), before)
        status = json.loads(output.getvalue())
        self.assertEqual(status["execution_host_peer"]["status"], "CONFIGURED")
        self.assertEqual(status["execution_host_peer"]["live_status"], "NOT_VERIFIED")

    def test_cli_configure_process_exit_and_second_process_readback_are_durable(self) -> None:
        other_root = Path(self.temporary.name) / "subprocess-root"
        command = [sys.executable, "-m", "forge", "--data-root", str(other_root)]
        subprocess.run([*command, "server", "init"], check=True, capture_output=True, text=True)
        configured = subprocess.run([
            *command, "execution-host", "configure", "--binding-id", "ep-primary",
            "--endpoint", "https://ep.test", "--expected-instance-id", "ep-instance-1",
            "--host-id", "engineering-platform", "--project-id", "forge-project",
            "--repository-id", "forge-repository", "--repository-identity", "forge-source",
            "--credential-reference", "keychain://forge.ep/consumer", "--operator-id", "local-admin",
        ], check=True, capture_output=True, text=True)
        database_before = (other_root / "forge.db").read_bytes()
        shown = subprocess.run([*command, "execution-host", "show"], check=True, capture_output=True, text=True)
        self.assertEqual((other_root / "forge.db").read_bytes(), database_before)
        first, second = json.loads(configured.stdout), json.loads(shown.stdout)
        self.assertEqual(first["configuration"], second["configuration"])
        self.assertNotIn(SYNTHETIC_SECRET, configured.stdout + configured.stderr + shown.stdout + shown.stderr)

    def test_cli_preflight_uses_real_service_resolver_and_adapter_and_only_reads_compatibility(self) -> None:
        self.service.configure(**self.values())
        declaration = {
            "contract_version": "1.0",
            "producer": {"id": "engineering-platform", "version": "2.3.0"},
            "instance": {"id": "ep-instance-1"},
            "contracts": {"producer_readback": ["1.2"], "terminal_evidence": ["1.3"]},
        }
        keychain_result = subprocess.CompletedProcess([], 0, stdout=SYNTHETIC_SECRET + "\n", stderr="")
        observed: list[tuple[str, str, str | None]] = []

        def peer(request, *, timeout):
            self.assertEqual(timeout, 10.0)
            observed.append((request.get_method(), request.full_url, request.get_header("Authorization")))
            return _Response(json.dumps(declaration).encode())

        output = StringIO()
        database_before = (self.root / "forge.db").read_bytes()
        with (patch("forge.secure_store.subprocess.run", return_value=keychain_result),
              patch("forge.scheduler.ep_http_adapter._open", side_effect=peer), redirect_stdout(output)):
            code = main(["--data-root", str(self.root), "execution-host", "preflight"])
        self.assertEqual(code, 0)
        report = json.loads(output.getvalue())
        self.assertEqual((report["status"], report["peer_instance_consistency"], report["compatibility"]),
                         ("PASS", "PASS", "PASS"))
        self.assertEqual(report["cryptographic_peer_identity"], "NOT_ASSERTED")
        self.assertEqual(report["project_repository_scope"], "NOT_VERIFIED")
        self.assertEqual(observed,
                         [("GET", "https://ep.test/v1/producer-compatibility", f"Bearer {SYNTHETIC_SECRET}")])
        self.assertNotIn(SYNTHETIC_SECRET, output.getvalue())
        self.assertEqual((self.root / "forge.db").read_bytes(), database_before)

        incompatible = {**declaration, "contracts": {
            "producer_readback": ["1.1"], "terminal_evidence": ["1.1"],
        }}
        failed = StringIO()
        with (patch("forge.secure_store.subprocess.run", return_value=keychain_result),
              patch("forge.scheduler.ep_http_adapter._open",
                    return_value=_Response(json.dumps(incompatible).encode())), redirect_stdout(failed)):
            code = main(["--data-root", str(self.root), "execution-host", "preflight"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(failed.getvalue())["status"], "ERROR")
        self.assertNotIn(SYNTHETIC_SECRET, failed.getvalue())
        self.assertEqual((self.root / "forge.db").read_bytes(), database_before)

    def test_schema_32_migration_preserves_runtime_and_mission_state(self) -> None:
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        database.save_mission_state({
            "mission_id": "mission-existing", "status": "ACTIVE", "progress": {}, "resume": {},
            "execution_policy": {"mode": "test"},
        })
        runtime_id = database.runtime_identity.runtime_id
        database.close()
        connection = sqlite3.connect(self.root / "forge.db")
        connection.execute("DROP TABLE execution_host_peer_configuration")
        connection.execute("UPDATE runtime_metadata SET value='32' WHERE key IN ('schema_version','migration_version','last_migration')")
        connection.execute("PRAGMA user_version=32")
        connection.commit()
        connection.close()

        before = (self.root / "forge.db").read_bytes()
        self.assertIsNone(read_peer_configuration(self.root).configuration)
        self.assertEqual((self.root / "forge.db").read_bytes(), before)
        migrated = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        try:
            self.assertEqual(migrated.runtime_identity.runtime_id, runtime_id)
            self.assertEqual(migrated.get_document("mission_state", "mission-existing")["status"], "ACTIVE")
            self.assertEqual(migrated.metadata["schema_version"], str(RUNTIME_SCHEMA_VERSION))
        finally:
            migrated.close()

    def test_schema_32_migration_rejects_an_incompatible_preexisting_peer_table(self) -> None:
        connection = sqlite3.connect(self.root / "forge.db")
        connection.execute("DROP TABLE execution_host_peer_configuration")
        connection.execute("CREATE TABLE execution_host_peer_configuration (forged TEXT)")
        connection.execute("UPDATE runtime_metadata SET value='32' WHERE key IN ('schema_version','migration_version','last_migration')")
        connection.execute("PRAGMA user_version=32")
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(Exception, "incompatible table shape"):
            RuntimeBootstrap(data_root=self.root, forge_version="test").open()


if __name__ == "__main__":
    unittest.main()
