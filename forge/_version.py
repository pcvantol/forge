"""Resolve Forge's canonical version without creating a second allocator."""
from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as installed_version
from pathlib import Path
import re


_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def _source_version() -> str | None:
    """Read the sole source of authority when this is a source distribution."""
    manifest = Path(__file__).resolve().parents[1] / "product-version.json"
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidate = value.get("version") if isinstance(value, dict) else None
    return candidate if isinstance(candidate, str) and _VERSION.fullmatch(candidate) else None


def canonical_version() -> str:
    """Return the source manifest version or installed distribution metadata."""
    source = _source_version()
    if source is not None:
        return source
    try:
        value = installed_version("forge-autonomy")
    except PackageNotFoundError as error:
        raise RuntimeError("Forge version metadata is unavailable") from error
    if _VERSION.fullmatch(value) is None:
        raise RuntimeError("Forge version metadata is not a stable X.Y.Z version")
    return value


__version__ = canonical_version()
