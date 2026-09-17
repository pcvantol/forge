"""Administration and read-only qualification entrypoint for packaged Forge."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from ._version import canonical_version
from .execution_host_configuration import (
    EngineeringPlatformPeerConfigurationService,
    PeerConfigurationError,
    read_peer_configuration,
)
from .runtime.data_root import DataRootResolver
from .secure_store import CredentialAccessSetupService, SecretReference


def _status(data_root: str | None) -> dict[str, object]:
    """Read only the operator-safe instance projection; never initialise it."""
    root = DataRootResolver(cli_data_root=data_root).resolve()
    database = root / "forge.db"
    marker = root / "instance" / "runtime-instance.json"
    result: dict[str, object] = {"product_version": canonical_version(), "data_root": str(root),
                                 "initialized": marker.is_file() and database.is_file(),
                                 "runtime_status": "uninitialized",
                                 "execution_host_peer": {"status": "NOT_CONFIGURED", "live_status": "NOT_VERIFIED"}}
    if not result["initialized"]:
        return result
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            metadata = dict(connection.execute("SELECT key, value FROM runtime_metadata"))
            dispatcher = connection.execute(
                "SELECT status FROM dispatcher_state WHERE singleton = 1"
            ).fetchone()
            dispatcher_status = "IDLE" if dispatcher is None else dispatcher[0]
            if dispatcher_status not in {"IDLE", "ACTIVE"}:
                raise sqlite3.DatabaseError("invalid durable dispatcher state")
        finally:
            connection.close()
    except sqlite3.Error:
        result["runtime_status"] = "unavailable"
        result["execution_host_peer"] = {
            "status": "ERROR", "live_status": "NOT_VERIFIED", "error": "Forge runtime storage is unavailable",
        }
        return result
    result.update({"instance_id": metadata.get("runtime_id"), "storage_schema": metadata.get("schema_version"),
                   "runtime_status": metadata.get("status", "unavailable")})
    result["dispatcher"] = {"status": dispatcher_status}
    try:
        peer_readback = read_peer_configuration(root)
        peer = peer_readback.configuration
        if peer is not None:
            result["execution_host_peer"] = {
                "status": "CONFIGURED", "live_status": "NOT_VERIFIED",
                "binding_id": peer.binding_id,
                "configuration_revision": peer.configuration_revision,
                "configuration_digest": peer.configuration_digest,
                "owning_forge_runtime_id": peer.owning_forge_runtime_id,
                "ep_consumer_id": peer.ep_consumer_id,
            }
        elif peer_readback.stored_document is not None:
            result["execution_host_peer"] = {
                "status": peer_readback.status,
                "live_status": "NOT_VERIFIED",
                "binding_id": peer_readback.stored_document["binding_id"],
                "configuration_revision": peer_readback.stored_document["configuration_revision"],
                "configuration_digest": peer_readback.stored_document["configuration_digest"],
                "owning_forge_runtime_id": peer_readback.stored_document["owning_forge_runtime_id"],
            }
    except PeerConfigurationError as error:
        result["execution_host_peer"] = {
            "status": "ERROR", "live_status": "NOT_VERIFIED", "error": str(error),
        }
    return result


def _failure(command: str, error: Exception) -> int:
    print(json.dumps({"command": command, "status": "ERROR", "error": str(error)}, sort_keys=True))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Forge mission planning and evidence interpretation runtime.",
    )
    parser.add_argument("--version", action="version", version=canonical_version())
    parser.add_argument("--data-root", help="Forge-owned runtime data root")
    subparsers = parser.add_subparsers(dest="command")
    server = subparsers.add_parser("server", help="manage local Forge storage")
    server_commands = server.add_subparsers(dest="server_command", required=True)
    server_commands.add_parser("init", help="create and validate the configured Forge data root")
    server_commands.add_parser("status", help="print read-only runtime status as JSON")
    reset = server_commands.add_parser("reset", help="operate the Forge-owned operational-history reset")
    reset_commands = reset.add_subparsers(dest="reset_command", required=True)
    reset_commands.add_parser("preview", help="inspect a read-only reset plan")
    prepare_reset = reset_commands.add_parser("prepare", help="authorize maintenance and create a verified backup")
    prepare_reset.add_argument("--operation-id", required=True)
    prepare_reset.add_argument("--plan-digest", required=True)
    prepare_reset.add_argument("--acknowledge-operational-fk", action="append", default=[])
    for name, help_text in (
        ("apply", "apply the authorized destructive reset"),
        ("verify", "verify reset integrity and preserved bindings"),
    ):
        reset_action = reset_commands.add_parser(name, help=help_text)
        reset_action.add_argument("--operation-id", required=True)
        reset_action.add_argument("--plan-digest", required=True)
        reset_action.add_argument("--request-digest", required=True)
        reset_action.add_argument("--backup-digest", required=True)
    reset_status = reset_commands.add_parser("status", help="read durable reset status")
    reset_status.add_argument("--operation-id")
    resume_reset = reset_commands.add_parser("resume", help="reconcile the same interrupted reset operation")
    resume_reset.add_argument("--operation-id", required=True)
    resume_reset.add_argument("--plan-digest", required=True)
    resume_reset.add_argument("--request-digest", required=True)
    resume_reset.add_argument("--backup-digest")
    finish_reset = reset_commands.add_parser("finish", help="safely leave durable maintenance")
    finish_reset.add_argument("--operation-id", required=True)
    finish_reset.add_argument("--verification-digest")
    finish_reset.add_argument("--cancel-before-apply", action="store_true")
    subparsers.add_parser("status", help="print read-only runtime status as JSON")
    execution_host = subparsers.add_parser("execution-host", help="manage the selected Execution Host peer")
    execution_host_commands = execution_host.add_subparsers(dest="execution_host_command", required=True)
    configure = execution_host_commands.add_parser("configure", help="persist one explicit EP peer binding")
    configure.add_argument("--binding-id", required=True)
    configure.add_argument("--endpoint", required=True)
    configure.add_argument("--expected-instance-id", required=True)
    configure.add_argument("--consumer-id", required=True)
    configure.add_argument("--host-id", required=True)
    configure.add_argument("--project-id", required=True)
    configure.add_argument("--repository-id", required=True)
    configure.add_argument("--repository-identity", required=True)
    configure.add_argument("--credential-reference", required=True)
    configure.add_argument("--operator-id", required=True)
    configure.add_argument("--timeout-seconds", type=float, default=10.0)
    configure.add_argument("--allow-loopback-http", action="store_true")
    configure.add_argument("--replace", action="store_true")
    configure.add_argument("--expected-revision", type=int)
    configure.add_argument("--expected-digest")
    execution_host_commands.add_parser("show", help="print the persisted secret-free EP peer binding")
    execution_host_commands.add_parser("preflight", help="perform read-only EP identity and v1.2 compatibility checks")
    credential_access = execution_host_commands.add_parser(
        "credential-access",
        help="perform one explicit local Keychain credential-access setup read",
    )
    credential_access.add_argument("--credential-reference", required=True, action="append")
    credential_access.add_argument(
        "--interactive",
        action="store_true",
        help="explicitly request the one bounded local Keychain access read",
    )
    credential_access.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="bounded interactive setup timeout in seconds (maximum: 120)",
    )
    args = parser.parse_args(argv)
    if args.command == "server" and args.server_command == "init":
        from .runtime import RuntimeBootstrap
        database = RuntimeBootstrap(data_root=args.data_root, forge_version=canonical_version()).open()
        try:
            print(json.dumps(_status(args.data_root), sort_keys=True))
        finally:
            database.close()
    elif args.command == "status" or (args.command == "server" and args.server_command == "status"):
        print(json.dumps(_status(args.data_root), sort_keys=True))
    elif args.command == "server" and args.server_command == "reset":
        from .runtime.operational_reset import ForgeOperationalResetService, OperationalResetError
        service = ForgeOperationalResetService(args.data_root)
        try:
            if args.reset_command == "preview":
                result = service.preview()
            elif args.reset_command == "prepare":
                result = service.prepare(
                    operation_id=args.operation_id,
                    expected_plan_digest=args.plan_digest,
                    acknowledge_operational_fk=args.acknowledge_operational_fk,
                )
            elif args.reset_command in {"apply", "verify"}:
                result = getattr(service, args.reset_command)(
                    operation_id=args.operation_id, plan_digest=args.plan_digest,
                    request_digest=args.request_digest, backup_digest=args.backup_digest,
                )
            elif args.reset_command == "status":
                result = service.status(operation_id=args.operation_id)
            elif args.reset_command == "resume":
                result = service.resume(
                    operation_id=args.operation_id, plan_digest=args.plan_digest,
                    request_digest=args.request_digest, backup_digest=args.backup_digest,
                )
            else:
                result = service.finish(
                    operation_id=args.operation_id, verification_digest=args.verification_digest,
                    cancel_before_apply=args.cancel_before_apply,
                )
            print(json.dumps(service.operator_envelope(args.reset_command, result), sort_keys=True))
        except (OperationalResetError, OSError, sqlite3.Error, PermissionError, ValueError) as error:
            finding = {"code": type(error).__name__, "message": str(error)}
            failure = {
                "operation_id": getattr(args, "operation_id", None),
                "state": "ERROR", "allowed": False, "blockers": [finding],
                "error": str(error),
            }
            try:
                envelope = service.operator_envelope(args.reset_command, failure)
            except Exception:
                # Even an unreadable target retains the coordinator's stable
                # top-level contract; no success or target identity is guessed.
                envelope = {
                    "contract_version": "operational-reset-v1", "product": "forge",
                    "command": args.reset_command, "operation_id": failure["operation_id"],
                    "state": "ERROR", "allowed": False,
                    "target": {
                        "instance_id": None, "database_path": str(service.database_path),
                        "database_identity": None, "schema_version": None,
                    },
                    "profile": "forge-operational-history-v1", "dataset_generation": None,
                    "plan_digest": None, "relevant_revision_digest": None,
                    "backup": None, "counts": {}, "blockers": [finding], "integrity": {},
                    "preserved_bindings_digest": None, "details": failure,
                }
            print(json.dumps(envelope, sort_keys=True))
            return 1
    elif args.command == "execution-host":
        try:
            if args.execution_host_command == "credential-access":
                if len(args.credential_reference) != 1:
                    raise ValueError("credential-access requires exactly one credential reference")
                if args.interactive:
                    print(
                        "macOS may ask you to allow Keychain access by /usr/bin/security. "
                        "This is a macOS Keychain decision, not a Forge-exclusive cryptographic permission.",
                        file=sys.stderr,
                    )
                result = CredentialAccessSetupService(timeout_seconds=args.timeout_seconds).read(
                    SecretReference.parse(args.credential_reference[0]), interactive=args.interactive,
                )
                print(json.dumps(result.to_safe_dict(), sort_keys=True))
                return 0 if result.succeeded else 1
            service = EngineeringPlatformPeerConfigurationService(args.data_root)
            if args.execution_host_command == "configure":
                if args.replace != (args.expected_revision is not None and args.expected_digest is not None):
                    raise PeerConfigurationError(
                        "--replace requires both --expected-revision and --expected-digest; guards are invalid without --replace"
                    )
                configured = service.configure(
                    binding_id=args.binding_id,
                    endpoint=args.endpoint,
                    expected_ep_instance_id=args.expected_instance_id,
                    ep_consumer_id=args.consumer_id,
                    execution_host_id=args.host_id,
                    ep_project_id=args.project_id,
                    ep_repository_id=args.repository_id,
                    repository_identity=args.repository_identity,
                    credential_reference=SecretReference.parse(args.credential_reference),
                    operator_id=args.operator_id,
                    allow_loopback_http=args.allow_loopback_http,
                    timeout_seconds=args.timeout_seconds,
                    replace=args.replace,
                    expected_revision=args.expected_revision,
                    expected_digest=args.expected_digest,
                )
                print(json.dumps({"status": "CONFIGURED", "configuration": configured.to_dict()}, sort_keys=True))
            elif args.execution_host_command == "show":
                readback = service.readback()
                if readback.stored_document is None:
                    print(json.dumps({"status": "NOT_CONFIGURED"}, sort_keys=True))
                    return 1
                print(json.dumps({
                    "status": readback.status,
                    "configuration": readback.stored_document,
                }, sort_keys=True))
                if readback.configuration is None:
                    return 1
            elif args.execution_host_command == "preflight":
                print(json.dumps(service.preflight(), sort_keys=True))
        except (PeerConfigurationError, ValueError) as error:
            return _failure(f"execution-host {args.execution_host_command}", error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
