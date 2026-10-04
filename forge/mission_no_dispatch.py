"""Installed entrypoint for approved two-repository Action derivation."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="forge-mission-derive-actions",
        description="Derive two approved repository Actions without Host dispatch.",
    )
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument(
        "--ep-repository-id", action="append", default=[], metavar="APPROVED_SCOPE=EP_ID",
        help="select one EP repository ID for each exact approved Mission scope",
    )
    args = parser.parse_args(argv)
    try:
        bindings: dict[str, str] = {}
        for pair in args.ep_repository_id:
            scope, separator, repository_id = pair.partition("=")
            if not separator or not scope or not repository_id or scope in bindings:
                raise ValueError("EP repository ID selections must be unique exact scope=ID pairs")
            bindings[scope] = repository_id
        with InstalledDynamicMissionRuntime.open(args.data_root) as runtime:
            result = runtime.derive_two_repository_actions(
                args.mission_id, ep_repository_ids=bindings or None,
            )
    except (OSError, ValueError, RuntimeError, PermissionError) as error:
        print(json.dumps({"status": "ERROR", "error_type": type(error).__name__}, sort_keys=True))
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
