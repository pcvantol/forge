"""Local persistence for already-validated Engineering Planning documents."""

from __future__ import annotations

from pathlib import Path

from forge.core import JsonStore

from .loader import EngineeringPlanningDocument, PlanningDocumentLoader


REGISTRY_VERSION = "0.5"


class PlanningRegistry:
    """Persist Forge planning declarations only; it never approves or executes them."""

    def __init__(self, path: str | Path, loader: PlanningDocumentLoader | None = None) -> None:
        self._store = JsonStore(Path(path))
        self._loader = loader or PlanningDocumentLoader()

    def save(self, document: EngineeringPlanningDocument) -> EngineeringPlanningDocument:
        report = self._loader.load(document.to_dict())
        if not report.valid:
            raise ValueError("planning registry requires a valid planning document")
        self._store.save({"registry_version": REGISTRY_VERSION, "planning_document": document.to_dict()})
        return document

    def load(self) -> EngineeringPlanningDocument | None:
        if not self._store.path.is_file():
            return None
        stored = self._store.load()
        if stored.get("registry_version") != REGISTRY_VERSION or not isinstance(stored.get("planning_document"), dict):
            raise ValueError("planning registry has an unsupported format")
        report = self._loader.load(stored["planning_document"])
        if not report.valid:
            raise ValueError("planning registry contains an invalid planning document")
        return report.document
