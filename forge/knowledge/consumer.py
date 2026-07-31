"""Deterministic, metadata-only consumption of registered knowledge sources."""

from __future__ import annotations

from dataclasses import dataclass
import re

from forge.models import KnowledgeLifecycle, KnowledgeSource


@dataclass(frozen=True)
class KnowledgeReference:
    """A source declaration exposed as evidence, without extracting its content."""

    source_id: str
    source_name: str
    evidence_location: str
    source_reference: str
    source_version: str
    lifecycle: KnowledgeLifecycle
    trust_classification: str


class ReadOnlyKnowledgeConsumer:
    """Search declared source metadata only; no source access or mutation occurs."""

    def find(self, source: KnowledgeSource, query: str, context: str = "") -> tuple[KnowledgeReference, ...]:
        """Return zero or one stable evidence reference for the requested source."""
        if not isinstance(query, str) or not isinstance(context, str):
            raise ValueError("knowledge query and context must be strings")
        terms = self._terms(query, context)
        haystack = " ".join((source.id, source.name, source.source_type, source.locator, source.reference, source.version, *source.metadata.values())).casefold()
        if terms and not all(term in haystack for term in terms):
            return ()
        return (KnowledgeReference(source.id, source.name, source.locator, source.reference, source.version, source.lifecycle, source.trust_classification.value),)

    @staticmethod
    def _terms(query: str, context: str) -> tuple[str, ...]:
        return tuple(sorted(set(re.findall(r"[\w-]+", f"{query} {context}".casefold()))))
