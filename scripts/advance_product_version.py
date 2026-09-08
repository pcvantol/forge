#!/usr/bin/env python3
"""Inspect, plan, or explicitly apply Forge's product-version.json change.

This repository-local boundary does not commit, publish, or qualify releases.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile

PRODUCT = "forge"
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def current(root: Path) -> tuple[Path, dict[str, object], tuple[int, int, int]]:
    target = root.resolve() / "product-version.json"
    try:
        payload = json.loads(target.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("canonical product version manifest is unreadable") from error
    if not isinstance(payload, dict):
        raise RuntimeError("canonical product version manifest must be an object")
    if payload.get("schema_version") != 1 or isinstance(payload.get("schema_version"), bool):
        raise RuntimeError("canonical product version manifest has an unsupported schema")
    if payload.get("product") != PRODUCT:
        raise RuntimeError(f"canonical product version manifest must identify {PRODUCT}")
    value = payload.get("version")
    if not isinstance(value, str) or VERSION.fullmatch(value) is None:
        raise RuntimeError("canonical product version must be stable X.Y.Z")
    return target, payload, tuple(int(part) for part in value.split("."))


def determine(parsed: tuple[int, int, int], component: str | None, exact: str | None) -> str:
    if (component is None) == (exact is None):
        raise RuntimeError("provide exactly one requested bump or exact target version")
    if exact is not None:
        if VERSION.fullmatch(exact) is None:
            raise RuntimeError("the requested release version must be stable X.Y.Z")
        return exact
    major, minor, patch = parsed
    if component == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if component == "minor":
        return f"{major}.{minor + 1}.0"
    raise RuntimeError("major requires explicit release authority")


def _atomic_write(path: Path, text: str) -> None:
    mode = path.stat().st_mode
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def advance(root: Path, component: str | None, exact: str | None = None, expected_version: str | None = None) -> str:
    target, payload, (major, minor, patch) = current(root)
    actual = payload["version"]
    if expected_version is not None and expected_version != actual:
        raise RuntimeError(f"stale version operation: expected {expected_version}, found {actual}")
    version = determine((major, minor, patch), component, exact)
    if version == actual:
        return version
    payload["version"] = version
    _atomic_write(target, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--bump", choices=("patch", "minor"))
    parser.add_argument("--set-version")
    parser.add_argument("--expected-version")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        if args.bump or args.set_version or args.plan:
            parser.error("--check cannot change or plan a version")
        _, payload, _ = current(args.source_root)
        print(f"PRODUCT_VERSION=PASS version={payload['version']}")
    elif args.plan:
        if (args.bump is None) == (args.set_version is None):
            parser.error("--plan requires exactly one requested version operation")
        _, payload, parsed = current(args.source_root)
        print(json.dumps({"product": PRODUCT, "baseline": payload["version"], "target": determine(parsed, args.bump, args.set_version), "writes": []}, sort_keys=True))
    else:
        print(f"PRODUCT_VERSION={advance(args.source_root, args.bump, args.set_version, args.expected_version)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
