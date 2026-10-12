"""Thin local CLI for the reusable offline proposal service."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .schema import ContractError, load_json
from .assets.safe_io import read_regular
from .service import assets, check_bundle, check_input, export


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge-project-bootstrap", description="Offline proposal only; no project or Mission effects")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog")
    for name in ["validate-input", "render"]:
        command = commands.add_parser(name)
        command.add_argument("--input", type=Path, required=True)
        if name == "render":
            command.add_argument("--export", type=Path, required=True)
    check = commands.add_parser("check-bundle")
    check.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            result = assets()[0]
        elif args.command == "check-bundle":
            result = check_bundle(args.bundle)
        else:
            raw, _ = read_regular(args.input)
            if len(raw) > 131072:
                raise ContractError("input exceeds limit")
            value = load_json(raw)
            if args.command == "render":
                result = export(value, args.export)
            else:
                check_input(value)
                result = {"state": "VALID_INPUT_PROPOSAL"}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ContractError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"state": "INVALID_OR_UNSUPPORTED_PROPOSAL", "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
