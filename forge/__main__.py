"""Read-only command entrypoint for the packaged Forge runtime."""
from __future__ import annotations

import argparse
import json
import sqlite3

from ._version import canonical_version
from .runtime.data_root import DataRootResolver


def _status(data_root: str | None) -> dict[str, object]:
    """Read only the operator-safe instance projection; never initialise it."""
    root = DataRootResolver(cli_data_root=data_root).resolve()
    database = root / "forge.db"
    marker = root / "instance" / "runtime-instance.json"
    result: dict[str, object] = {"product_version": canonical_version(), "data_root": str(root),
                                 "initialized": marker.is_file() and database.is_file(),
                                 "runtime_status": "uninitialized", "execution_host_peer": "not_configured"}
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
        return result
    result.update({"instance_id": metadata.get("runtime_id"), "storage_schema": metadata.get("schema_version"),
                   "runtime_status": metadata.get("status", "unavailable")})
    return result


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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
