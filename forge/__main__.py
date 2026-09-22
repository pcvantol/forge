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
    server_run = server_commands.add_parser("run", help="run the persistent foreground Forge Server")
    server_run.add_argument("--credential-file", required=True)
    server_run.add_argument("--host", default="127.0.0.1")
    server_run.add_argument("--port", required=True, type=int)
    server_run.add_argument("--provider-id", default="codex-chatgpt-session")
    server_run.add_argument("--tick-interval", type=float, default=0.25)
    provider_context = server_commands.add_parser(
        "provider-context", help="manage the instance-owned provider execution context"
    )
    provider_context_commands = provider_context.add_subparsers(dest="provider_context_command", required=True)
    provider_context_show = provider_context_commands.add_parser("show", help="read one secret-free provider context")
    provider_context_show.add_argument("--provider-id", default="codex-chatgpt-session")
    provider_context_configure = provider_context_commands.add_parser(
        "configure", help="write one guarded, secret-free provider context"
    )
    provider_context_configure.add_argument("--provider-id", default="codex-chatgpt-session")
    provider_context_configure.add_argument("--provider-type", required=True)
    provider_context_configure.add_argument("--executable-path", required=True)
    provider_context_configure.add_argument("--provider-home", required=True)
    provider_context_configure.add_argument("--provider-config-home", required=True)
    provider_context_configure.add_argument("--profile")
    provider_context_configure.add_argument("--expected-digest")
    reset = server_commands.add_parser("reset", help="operate the Forge-owned operational-history reset")
    reset_commands = reset.add_subparsers(dest="reset_command", required=True)
    reset_commands.add_parser("preview", help="inspect a read-only reset plan")
    prepare_reset = reset_commands.add_parser("prepare", help="authorize maintenance and create a verified backup")
    prepare_reset.add_argument("--operation-id", required=True)
    prepare_reset.add_argument("--plan-digest", required=True)
    prepare_reset.add_argument("--acknowledge-operational-fk", action="append", default=[])
    for name, help_text in (
        ("revalidate", "revalidate the exact prepared operation without changing it"),
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
    health = subparsers.add_parser("health", help="assess installed Forge health without mutation")
    health_commands = health.add_subparsers(dest="health_command", required=True)
    health_snapshot = health_commands.add_parser("snapshot", help="print one bounded installed-health snapshot")
    health_snapshot.add_argument("--timeout-seconds", type=float, default=2.0)
    mission = subparsers.add_parser("mission", help="govern and run one selected Mission")
    mission_commands = mission.add_subparsers(dest="mission_command", required=True)
    for name, description in (
        ("inspect", "validate Mission input and evidence fit without allocation"),
        ("approve-business", "record canonical Business approval"),
        ("approve-architecture", "record canonical Architecture approval"),
        ("admit", "allocate and admit the canonically approved Mission"),
    ):
        command = mission_commands.add_parser(name, help=description)
        command.add_argument("--input", required=True)
    for name, description in (
        ("run", "start once and control the selected Mission to a terminal or declared stop"),
        ("reopen", "continue the same durable Mission execution"),
        ("status", "read the exact Mission status and result"),
        ("stop", "request a controlled foreground stop"),
    ):
        command = mission_commands.add_parser(name, help=description)
        command.add_argument("--mission-id", required=True)
        if name == "run":
            command.add_argument("--repository-truth", required=True)
        if name in {"run", "reopen"}:
            command.add_argument("--poll-seconds", type=float, default=1.0)
            command.add_argument("--maximum-wait-seconds", type=float, default=3600.0)
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
    operations_api = subparsers.add_parser("operations-api", help="serve authenticated read-only runtime projections")
    operations_api.add_argument("--credential-file", required=True)
    operations_api.add_argument("--host", default="127.0.0.1")
    operations_api.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if args.command == "server" and args.server_command == "run":
        if args.data_root is None:
            return _failure("server run", ValueError("--data-root is required for Forge Server"))
        try:
            from .server_runtime import ForgeServerRuntime
            ForgeServerRuntime(
                data_root=args.data_root, credential_file=args.credential_file,
                host=args.host, port=args.port, provider_id=args.provider_id,
                tick_interval=args.tick_interval,
            ).serve_forever()
            return 0
        except (OSError, ValueError, RuntimeError, PermissionError) as error:
            return _failure("server run", error)
    if args.command == "server" and args.server_command == "provider-context":
        if args.data_root is None:
            return _failure("server provider-context", ValueError("--data-root is required for provider-context"))
        try:
            from .provider_context import ProviderExecutionContextService
            from .runtime.service import RuntimeServiceLock
            service = ProviderExecutionContextService(args.data_root)
            if args.provider_context_command == "show":
                result = service.read(args.provider_id).to_safe_dict()
            else:
                root = DataRootResolver(cli_data_root=args.data_root).resolve()
                with RuntimeServiceLock(root / "forge.db").acquire():
                    result = service.configure(
                        provider_id=args.provider_id, provider_type=args.provider_type,
                        executable_path=args.executable_path, provider_home=args.provider_home,
                        provider_config_home=args.provider_config_home, profile=args.profile,
                        expected_digest=args.expected_digest,
                    ).to_safe_dict()
            print(json.dumps(result, sort_keys=True))
            return 0
        except (OSError, ValueError, RuntimeError, PermissionError) as error:
            return _failure("server provider-context", error)
    if args.command == "health":
        if args.data_root is None:
            return _failure("health snapshot", ValueError("--data-root is required for health snapshot"))
        try:
            from .installed_health import InstalledHealthError, installed_health_snapshot
            result = installed_health_snapshot(args.data_root, timeout_seconds=args.timeout_seconds)
            print(json.dumps(result, sort_keys=True))
            return 0 if result["outcome"] == "HEALTHY" else 2
        except InstalledHealthError as error:
            print(json.dumps({
                "command": "health snapshot",
                "status": "ERROR",
                "error": {"code": error.code, "message": str(error)},
            }, sort_keys=True))
            return 1
        except (OSError, ValueError) as error:
            return _failure("health snapshot", error)
    if args.command == "mission":
        from . import mission_cli
        try:
            command = args.mission_command
            if command == "inspect":
                result = mission_cli.inspect(args.input)
            elif command in {"approve-business", "approve-architecture"}:
                if args.data_root is None:
                    raise ValueError("--data-root is required for Mission governance")
                result = mission_cli.approve(args.data_root, args.input,
                                             "business" if command == "approve-business" else "architecture")
            elif command == "admit":
                if args.data_root is None:
                    raise ValueError("--data-root is required for Mission admission")
                result = mission_cli.admit(args.data_root, args.input)
            elif command == "status":
                result = mission_cli.status(args.data_root, args.mission_id)
            elif command == "stop":
                result = mission_cli.stop(args.data_root, args.mission_id)
            else:
                if args.data_root is None:
                    raise ValueError("--data-root is required for Mission execution")
                result = mission_cli.run(args.data_root, args.mission_id,
                    truth_path=args.repository_truth if command == "run" else None,
                    poll_seconds=args.poll_seconds, maximum_wait_seconds=args.maximum_wait_seconds)
            print(json.dumps(result, sort_keys=True))
            if command == "inspect":
                return 0 if result["status"] == "VALID" else 2
            if command == "stop":
                return 0 if result["stop_requested"] else 2
            if command in {"run", "reopen"}:
                return 0 if result["status"] == "COMPLETED" else 2
            return 0
        except (OSError, ValueError, KeyError, sqlite3.Error, RuntimeError, PermissionError) as error:
            return _failure("mission " + args.mission_command, error)
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
            elif args.reset_command in {"revalidate", "apply", "verify"}:
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
    elif args.command == "operations-api":
        if args.data_root is None:
            return _failure("operations-api", ValueError("--data-root is required for operations-api"))
        try:
            from .operations_read_api import serve
            serve(args.data_root, args.credential_file, host=args.host, port=args.port)
        except (OSError, ValueError) as error:
            return _failure("operations-api", error)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
