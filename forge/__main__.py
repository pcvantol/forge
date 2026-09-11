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
    try:
        peer = read_peer_configuration(root).configuration
        if peer is not None:
            result["execution_host_peer"] = {
                "status": "CONFIGURED", "live_status": "NOT_VERIFIED",
                "binding_id": peer.binding_id,
                "configuration_revision": peer.configuration_revision,
                "configuration_digest": peer.configuration_digest,
                "owning_forge_runtime_id": peer.owning_forge_runtime_id,
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
    subparsers.add_parser("status", help="print read-only runtime status as JSON")
    execution_host = subparsers.add_parser("execution-host", help="manage the selected Execution Host peer")
    execution_host_commands = execution_host.add_subparsers(dest="execution_host_command", required=True)
    configure = execution_host_commands.add_parser("configure", help="persist one explicit EP peer binding")
    configure.add_argument("--binding-id", required=True)
    configure.add_argument("--endpoint", required=True)
    configure.add_argument("--expected-instance-id", required=True)
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
                configured = service.show()
                if configured is None:
                    print(json.dumps({"status": "NOT_CONFIGURED"}, sort_keys=True))
                    return 1
                print(json.dumps({"status": "CONFIGURED", "configuration": configured.to_dict()}, sort_keys=True))
            elif args.execution_host_command == "preflight":
                print(json.dumps(service.preflight(), sort_keys=True))
        except (PeerConfigurationError, ValueError) as error:
            return _failure(f"execution-host {args.execution_host_command}", error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
