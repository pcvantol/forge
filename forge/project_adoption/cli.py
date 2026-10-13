"""Own thin offline preview CLI; supplied bytes never execute."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from forge.project_bootstrap.schema import ContractError, load_json
from forge.project_bootstrap.assets.safe_io import read_regular
from .service import check_input, check_proposal, export, preview, readable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forge-project-adoption", description="Supplied-inventory preview only; no scan, approval or target effects")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ["validate-input", "preview"]:
        item = commands.add_parser(name)
        item.add_argument("--input", type=Path, required=True)
        if name == "preview":
            item.add_argument("--export", type=Path)
    item = commands.add_parser("check-proposal")
    item.add_argument("--proposal", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "check-proposal":
            result = check_proposal(args.proposal)
        else:
            raw, _ = read_regular(args.input)
            value = load_json(raw)
            if args.command == "validate-input":
                check_input(value)
                result = {"state": "VALID_SUPPLIED_INPUT_NOT_INSPECTION"}
            elif args.export:
                result = export(value, args.export)
            else:
                print(readable(preview(value)).decode(), end="")
                return 0
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ContractError, OSError, ValueError, TypeError, KeyError):
        # No exception/path/raw supplied content automatically crosses the CLI error boundary.
        print(json.dumps({"state": "INVALID_OR_UNSUPPORTED_PREVIEW", "error": "INPUT_OR_PROPOSAL_REJECTED"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
