"""Local, deterministic registry for read-only knowledge-source declarations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from forge.core import JsonStore
from forge.models import KnowledgeAccessMode, KnowledgeLifecycle, KnowledgeSource, KnowledgeTrustClassification


REGISTRY_VERSION = "0.4"


class KnowledgeSourceRegistry:
    """Persist source declarations locally; it never reads from or writes to a source."""

    def __init__(self, path: str | Path) -> None:
        self._store = JsonStore(Path(path))

    def register(self, source: KnowledgeSource) -> KnowledgeSource:
        """Validate and add one source, rejecting a duplicate identity."""
        self._validate(source)
        sources = {registered.id: registered for registered in self.list()}
        if source.id in sources:
            raise ValueError("knowledge source id is already registered")
        sources[source.id] = source
        self._save(sources.values())
        return source

    def list(self) -> tuple[KnowledgeSource, ...]:
        """Return registered sources in stable identity order."""
        if not self._store.path.is_file():
            return ()
        document = self._store.load()
        if document.get("registry_version") != REGISTRY_VERSION or not isinstance(document.get("sources"), list):
            raise ValueError("knowledge source registry has an unsupported format")
        return tuple(sorted((self._source(item) for item in document["sources"]), key=lambda source: source.id))

    def _save(self, sources: Any) -> None:
        self._store.save({"registry_version": REGISTRY_VERSION, "sources": [source.to_dict() for source in sorted(sources, key=lambda item: item.id)]})

    @staticmethod
    def _validate(source: KnowledgeSource) -> None:
        if source.version == "unversioned" or source.reference == "unspecified":
            raise ValueError("knowledge source registry requires an explicit version and reference")
        if source.schema_version != "0.4":
            raise ValueError("knowledge source registry requires schema version 0.4")
        if source.access_mode is not KnowledgeAccessMode.READ_ONLY or not source.read_only:
            raise ValueError("knowledge source registry permits read-only sources only")

    @staticmethod
    def _source(document: Mapping[str, Any]) -> KnowledgeSource:
        try:
            source = KnowledgeSource(
                id=document["id"], name=document["name"], source_type=document["source_type"], locator=document["locator"],
                read_only=document["read_only"], metadata=dict(document.get("metadata", {})), schema_version=document["schema_version"],
                version=document["version"], reference=document["reference"],
                access_mode=KnowledgeAccessMode(document["access_mode"]),
                trust_classification=KnowledgeTrustClassification(document["trust_classification"]), lifecycle=KnowledgeLifecycle(document["lifecycle"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("knowledge source registry contains invalid source metadata") from error
        KnowledgeSourceRegistry._validate(source)
        return source
