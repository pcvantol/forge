#!/usr/bin/env python3
"""Inspect Forge's built artifacts without mutating their source checkout."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tarfile
import zipfile


FORBIDDEN_PARTS = frozenset((".git", ".engineering", "node_modules", "__pycache__", ".venv", "venv", "tests", "test-results", "artifacts", "logs"))
FORBIDDEN_SUFFIXES = (".db", ".sqlite", ".log", ".pyc")


def _forbidden(name: str, *, source: bool = False) -> bool:
    parts = Path(name).parts
    forbidden = FORBIDDEN_PARTS - ({"tests"} if source else set())
    return any(part in forbidden for part in parts) or name.endswith(FORBIDDEN_SUFFIXES)


def _wheel_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        return archive.namelist()


def _sdist_names(path: Path) -> list[str]:
    with tarfile.open(path, "r:gz") as archive:
        return archive.getnames()


def _check_wheel(path: Path) -> list[str]:
    names = _wheel_names(path)
    errors = [f"forbidden wheel entry: {name}" for name in names if _forbidden(name)]
    if not any(name.startswith("forge/") and name.endswith(".py") for name in names):
        errors.append("wheel omits Forge runtime code")
    if not any(name.endswith(".dist-info/METADATA") for name in names):
        errors.append("wheel omits distribution metadata")
    if not any(name.startswith("forge/schemas/") and name.endswith(".json") for name in names):
        errors.append("wheel omits required Forge schema resources")
    return errors


def _check_sdist(path: Path) -> list[str]:
    names = _sdist_names(path)
    errors = [f"forbidden sdist entry: {name}" for name in names if _forbidden(name, source=True)]
    if not any(name.endswith("/product-version.json") for name in names):
        errors.append("sdist omits canonical product-version.json")
    if not any(name.endswith("/forge/__init__.py") for name in names):
        errors.append("sdist omits Forge runtime code")
    if not any(name.endswith("/schemas/foundation-document.schema.json") for name in names):
        errors.append("sdist omits source schema resources")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    args = parser.parse_args(argv)
    errors = _check_wheel(args.wheel) + _check_sdist(args.sdist)
    print(json.dumps({"wheel": args.wheel.name, "sdist": args.sdist.name, "errors": errors}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
