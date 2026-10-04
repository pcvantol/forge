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
    args = parser.parse_args(argv)
    try:
        with InstalledDynamicMissionRuntime.open(args.data_root) as runtime:
            result = runtime.derive_two_repository_actions(args.mission_id)
    except (OSError, ValueError, RuntimeError, PermissionError) as error:
        print(json.dumps({"status": "ERROR", "error_type": type(error).__name__}, sort_keys=True))
        return 1
    print(json.dumps(asdict(result), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
