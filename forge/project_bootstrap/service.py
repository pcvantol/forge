"""Build finite portable proposals from verified installed baseline assets."""
from __future__ import annotations

import hashlib
from importlib.resources import files
import os
from pathlib import Path, PurePosixPath
import stat
import unicodedata
from typing import Any

from . import CONTRACT_VERSION
from .schema import ContractError, canonical, load_json, validate
from .assets import render_core
from .assets.safe_io import read_regular, finite_tree

BASELINE = "portable-docs/1.0.0"
CONTRACT = CONTRACT_VERSION
CATALOG_DIGEST = "757e9c0bc8a7c646badb5c0ae0c6dd024174f4d079b7390a6517ee78da0f375f"
BASE_PATH = "engineering/baselines/portable-docs/1.0.0"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def assets() -> tuple[dict[str, Any], dict[str, bytes]]:
    root = files("forge.project_bootstrap").joinpath("assets")
    catalog_bytes = root.joinpath("catalog.json").read_bytes()
    if digest(catalog_bytes) != CATALOG_DIGEST:
        raise ContractError("installed catalog digest mismatch")
    registry = load_json(catalog_bytes)
    if registry["baseline"] != BASELINE or registry["contract_version"] != CONTRACT:
        raise ContractError("unsupported installed baseline")
    result = {}
    for name, expected in registry["assets"].items():
        safe_path(name)
        raw = root.joinpath(name).read_bytes()
        if digest(raw) != expected:
            raise ContractError("installed baseline asset digest mismatch")
        result[name] = raw
    validate(registry, load_json(result["catalog.schema.json"]))
    return registry, result


def safe_path(name: str) -> None:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or str(path) != name or "\\" in name
            or any(x in {".", "..", ".git"} or x.startswith(".git/") for x in path.parts)
            or not name.isascii() or any(ord(c) < 32 for c in name)):
        raise ContractError("unsafe artifact path")


def check_input(value: Any) -> dict[str, Any]:
    _, selected = assets()
    validate(value, load_json(selected["input.schema.json"]))
    identity = value["identity"]
    if (value["role"] == "authority") != (identity["repository_id"] == identity["authority_repository_id"]):
        raise ContractError("authority/child identity conflict")
    if (value["mode"] == "GENESIS") != (value["host_profile"] == "LOCAL_POSIX"):
        raise ContractError("incompatible host and mode")
    if value["authority_contract_reference"] != identity["authority_repository_id"] + ":engineering/project-contract.json":
        raise ContractError("authority contract reference mismatch")
    return value


def render(value: Any) -> dict[str, bytes]:
    value = check_input(value)
    registry, selected = assets()
    validate(load_json(selected["capability.json"]), load_json(selected["capability.schema.json"]))
    renderer_digest = digest(selected["render_core.py"])
    result = render_core.render(value, registry, selected, renderer_digest, canonical, load_json, safe_path, digest)
    contracts = {"engineering/baseline.lock.json":"baseline-lock", "engineering/project-contract.json":"project-contract", "engineering/repository-governance.json":"governance",
                 "engineering/project.json":"project", "docs/roadmap/capability-dag.json":"dag", "engineering/bootstrap-manifest.json":"manifest"}
    for path, schema_name in contracts.items():
        if path in result:
            validate(load_json(result[path]), load_json(selected[schema_name + ".schema.json"]))
    return result


def export(value: Any, target: Path) -> dict[str, Any]:
    payload = render(value)
    if ".." in target.parts:
        raise ContractError("export traversal rejected")
    # Walk every parent by descriptor without following symlinks; no resolve-based race.
    target = Path(os.path.abspath(target))
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in target.parts[1:-1]:
            try:
                os.stat(".git", dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ContractError("export inside a repository is unsupported")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        try:
            os.stat(".git", dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ContractError("export inside a repository is unsupported")
        os.mkdir(target.name, mode=0o700, dir_fd=fd)  # existing output always conflicts
        root = os.open(target.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            for name, raw in sorted(payload.items()):
                current = os.dup(root)
                try:
                    parts = PurePosixPath(name).parts
                    for part in parts[:-1]:
                        try:
                            os.mkdir(part, mode=0o700, dir_fd=current)
                        except FileExistsError:
                            pass
                        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                        os.close(current)
                        current = child
                    item = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=current)
                    os.fchmod(item, 0o644)
                    with os.fdopen(item, "wb") as handle:
                        handle.write(raw)
                finally:
                    os.close(current)
        finally:
            os.close(root)
    finally:
        os.close(fd)
    return {"state": "RENDERED_PROPOSAL", "manifest_digest": load_json(payload["engineering/bootstrap-manifest.json"])["manifest_digest"], "artifacts": len(payload)}


def check_bundle(target: Path) -> dict[str, Any]:
    try:
        inventory = finite_tree(target)
    except OSError as error:
        raise ContractError("unsafe bundle root") from error
    input_bytes, _ = read_regular(target / "engineering/render-input.json")
    expected = render(load_json(input_bytes))
    if inventory != set(expected):
        raise ContractError("unexpected/missing artifact inventory")
    for name, expected_bytes in expected.items():
        raw, mode = read_regular(target / name)
        if raw != expected_bytes or mode != 0o644:
            raise ContractError("bundle bytes or modes differ from trusted installed renderer")
    return {"state": "VALIDATED_PROPOSAL", "artifacts": len(expected), "manifest_digest": load_json(expected["engineering/bootstrap-manifest.json"])["manifest_digest"]}
