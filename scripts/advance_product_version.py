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
import subprocess
import tempfile
from typing import Any

PRODUCT = "forge"
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
OPERATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
OPERATIONS_DIRECTORY = Path(".github/product-version-operations")
POLICY_REVISION = "forge-bootstrap-release-cadence-v2"


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
    if component == "none":
        return f"{major}.{minor}.{patch}"
    if component == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if component == "minor":
        return f"{major}.{minor + 1}.0"
    raise RuntimeError("major requires explicit release authority")


def _atomic_write(path: Path, text: str) -> None:
    mode = path.stat().st_mode if path.exists() else 0o644
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


def _git_head(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("version operation requires a Git worktree with a resolved HEAD")
    return result.stdout.strip()


def _git_branch(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError("release candidate verification requires a named Git branch")
    return result.stdout.strip()


def _operation_path(root: Path, operation_id: str) -> Path:
    if OPERATION_ID.fullmatch(operation_id) is None:
        raise RuntimeError("operation ID must be a stable, non-path identifier")
    return root.resolve() / OPERATIONS_DIRECTORY / f"{operation_id}.json"


def _read_operation(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError("version operation receipt is unreadable") from error
    if not isinstance(payload, dict):
        raise RuntimeError("version operation receipt must be an object")
    return payload


def _operation_input(
    operation_id: str,
    expected_head: str,
    expected_version: str,
    component: str | None,
    exact: str | None,
    event_lineage: str,
    policy_revision: str,
    target: str,
) -> dict[str, str | None]:
    if not event_lineage.strip():
        raise RuntimeError("version operation requires a non-empty event or branch lineage")
    if not policy_revision.strip():
        raise RuntimeError("version operation requires a non-empty policy revision")
    release_class = "EXACT" if exact is not None else {"none": "NO_BUMP", "patch": "PATCH", "minor": "MINOR"}.get(component)
    if release_class is None:
        raise RuntimeError("unsupported bootstrap release classification")
    return {
        "schema_version": "1",
        "operation_id": operation_id,
        "product": PRODUCT,
        "component": "product",
        "policy_revision": policy_revision,
        "event_lineage": event_lineage,
        "expected_head": expected_head,
        "baseline_version": expected_version,
        "requested_bump": component,
        "requested_version": exact,
        "target_version": target,
        "release_class": release_class,
        "classification_rationale": event_lineage,
        "projection_paths": "product-version.json",
    }


def _validate_existing_operation(existing: dict[str, Any], requested: dict[str, str | None]) -> None:
    # Receipt equality, rather than a commit subject or actor, is the idempotency key.
    if existing != requested:
        raise RuntimeError("conflicting reuse of version operation ID")


def verify_release_candidate(root: Path, release_branch: str, approved_head: str, approved_version: str) -> str:
    """Read-only source guard; approval and publication remain external facts."""
    match = re.fullmatch(r"release-(" + VERSION.pattern.removeprefix("^").removesuffix("$") + r")", release_branch)
    if match is None:
        raise RuntimeError("release branch must be exactly release-X.Y.Z")
    branch_version = match.group(1)
    if VERSION.fullmatch(approved_version) is None:
        raise RuntimeError("approved release version must be stable X.Y.Z")
    if branch_version != approved_version:
        raise RuntimeError("release branch version must equal the approved release version")
    _, payload, _ = current(root)
    if payload["version"] != approved_version:
        raise RuntimeError("canonical product version does not equal the approved release version")
    if _git_branch(root) != release_branch:
        raise RuntimeError("current branch is not the declared release branch")
    if _git_head(root) != approved_head:
        raise RuntimeError("current Git head is not the approved exact release source")
    return approved_version


def advance(
    root: Path,
    component: str | None,
    exact: str | None = None,
    expected_version: str | None = None,
    operation_id: str | None = None,
    expected_head: str | None = None,
    event_lineage: str | None = None,
    policy_revision: str = POLICY_REVISION,
) -> str:
    target, payload, parsed = current(root)
    actual = payload["version"]
    if operation_id is None or expected_head is None or expected_version is None or event_lineage is None:
        raise RuntimeError("apply requires operation ID, expected head, expected version, and event lineage")
    if VERSION.fullmatch(expected_version) is None:
        raise RuntimeError("expected version must be stable X.Y.Z")
    # Calculate from the declared baseline, never from a source that may have
    # been changed by an interrupted first attempt.
    version = determine(tuple(int(part) for part in expected_version.split(".")), component, exact)
    requested = _operation_input(
        operation_id, expected_head, expected_version, component, exact, event_lineage, policy_revision, version
    )
    receipt = _operation_path(root, operation_id)
    existing = _read_operation(receipt)
    if existing is not None:
        _validate_existing_operation(existing, requested)
        if actual not in (expected_version, version):
            raise RuntimeError("version operation receipt conflicts with canonical source")
        # A crash after receipt staging but before the source replacement can be
        # resumed. It never derives a fresh bump from the partially changed source.
        if actual == version:
            return version
    else:
        if _git_head(root) != expected_head:
            raise RuntimeError("stale version operation: expected Git head no longer matches")
        if expected_version != actual:
            raise RuntimeError(f"stale version operation: expected {expected_version}, found {actual}")
        receipt.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(receipt, json.dumps(requested, indent=2, sort_keys=True) + "\n")
    if version == actual:
        return version
    payload["version"] = version
    _atomic_write(target, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--bump", choices=("none", "patch", "minor"))
    parser.add_argument("--set-version")
    parser.add_argument("--expected-version")
    parser.add_argument("--operation-id")
    parser.add_argument("--expected-head")
    parser.add_argument("--event-lineage")
    parser.add_argument("--policy-revision", default=POLICY_REVISION)
    parser.add_argument("--verify-release-candidate", action="store_true")
    parser.add_argument("--release-branch")
    parser.add_argument("--approved-head")
    parser.add_argument("--approved-version")
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_release_candidate:
        if args.check or args.plan or args.bump or args.set_version:
            parser.error("--verify-release-candidate is read-only and cannot combine with version mutation modes")
        if not args.release_branch or not args.approved_head or not args.approved_version:
            parser.error("release candidate verification requires branch, approved head, and approved version")
        print(
            "RELEASE_CANDIDATE=PASS version="
            + verify_release_candidate(args.source_root, args.release_branch, args.approved_head, args.approved_version)
        )
    elif args.check:
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
        print(
            "PRODUCT_VERSION="
            + advance(
                args.source_root,
                args.bump,
                args.set_version,
                args.expected_version,
                args.operation_id,
                args.expected_head,
                args.event_lineage,
                args.policy_revision,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
