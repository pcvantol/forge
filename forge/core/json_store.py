"""Deterministic, human-readable local JSON persistence for foundation data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class JsonStore:
    """Persist a single document locally without database or network dependencies."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, document: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def load(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))
