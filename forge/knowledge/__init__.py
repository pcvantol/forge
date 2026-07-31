"""Read-only knowledge-source registration and deterministic consumption."""

from .consumer import KnowledgeReference, ReadOnlyKnowledgeConsumer
from .registry import KnowledgeSourceRegistry

__all__ = ["KnowledgeReference", "KnowledgeSourceRegistry", "ReadOnlyKnowledgeConsumer"]
