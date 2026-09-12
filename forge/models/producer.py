"""Canonical, host-neutral Producer Contract owned by Forge.

This module deliberately contains only immutable interchange data.  A Producer
plans an Engineering Action and presents its Runtime Prompt to an Execution
Host; a Host executes it and owns any receipt, telemetry, report, or evidence
it returns.  No Forge implementation, host transport, or renderer appears in
this contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from forge._version import canonical_version


PRODUCER_CONTRACT_VERSION = "1.0"
FORGE_ACTION_CONTEXT_ENVELOPE_VERSION = "1.0"
FORGE_ACTION_CONTEXT_GENERATOR_ID = "forge-redacted-action-summary"
FORGE_ACTION_CONTEXT_GENERATOR_MODEL = "deterministic-template"
FORGE_ACTION_CONTEXT_GENERATOR_VERSION = "1.0"
_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(api[ _-]?key|authorization|bearer|password|secret|token)\b\s*([:=])\s*[^\s,;]+"
)
_BEARER_CREDENTIAL = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}\b")
_URL_CREDENTIAL = re.compile(r"(?i)(https?://)[^\s/@:]+:[^\s/@]+@")
_KNOWN_TOKEN = re.compile(r"\b(?:sk-[a-zA-Z0-9_-]{12,}|ghp_[a-zA-Z0-9]{12,}|github_pat_[a-zA-Z0-9_]{12,})\b")


def _canonical_digest(value: object) -> str:
    """Return the stable digest used by an immutable interchange document."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def redact_action_summary(value: str) -> str:
    """Create the bounded public-safe text allowed to leave Forge.

    The complete Runtime Prompt remains an Execution Host input. This helper
    deliberately projects only the Action objective and replaces common
    credential forms before the text can enter the producer envelope.
    """
    if not isinstance(value, str):
        raise ValueError("action summary must be text")
    text = " ".join(value.replace("\\x00", " ").split())
    text = _URL_CREDENTIAL.sub(r"\1[REDACTED]@", text)
    text = _KNOWN_TOKEN.sub("[REDACTED]", text)
    text = _BEARER_CREDENTIAL.sub("Bearer [REDACTED]", text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", text)
    if not text:
        raise ValueError("action summary must not be empty")
    return text[:500]


@dataclass(frozen=True)
class ForgeActionContextEnvelope:
    """Redacted, immutable Action summary safe for CENTRAL projection.

    This is intentionally a separate, versioned document: it is neither a
    Runtime Prompt nor the mutable Forge execution-context snapshot. The
    deterministic generator metadata makes the summary's provenance explicit
    without pretending that a model generated it.
    """

    action_id: str
    summary: str
    source_digest: str
    summary_digest: str
    envelope_digest: str
    envelope_version: str = FORGE_ACTION_CONTEXT_ENVELOPE_VERSION
    generator_id: str = FORGE_ACTION_CONTEXT_GENERATOR_ID
    generator_model: str = FORGE_ACTION_CONTEXT_GENERATOR_MODEL
    generator_version: str = FORGE_ACTION_CONTEXT_GENERATOR_VERSION

    @classmethod
    def from_runtime_prompt(cls, runtime_prompt: Any) -> "ForgeActionContextEnvelope":
        """Derive one safe envelope from the immutable Action objective."""
        action_id = getattr(runtime_prompt, "source_action_id", getattr(runtime_prompt, "action_id", None))
        source_digest = getattr(runtime_prompt, "generation_request_digest", getattr(runtime_prompt, "source_digest", None))
        sections = getattr(runtime_prompt, "sections", ())
        objective = next(
            (item for section in sections if getattr(getattr(section, "kind", None), "value", None) == "Objective"
             for item in getattr(section, "content", ()) if isinstance(item, str)),
            None,
        )
        objective = objective if objective is not None else getattr(runtime_prompt, "objective", None)
        if not isinstance(action_id, str) or not action_id or not isinstance(source_digest, str):
            raise ValueError("runtime prompt does not provide immutable Action provenance")
        return cls.create(action_id=action_id, summary=objective, source_digest=source_digest)

    @classmethod
    def create(cls, *, action_id: str, summary: str | None, source_digest: str) -> "ForgeActionContextEnvelope":
        if not isinstance(summary, str):
            raise ValueError("runtime prompt does not provide an Action objective")
        safe_summary = redact_action_summary(summary)
        summary_digest = _canonical_digest(safe_summary)
        document = {
            "envelope_version": FORGE_ACTION_CONTEXT_ENVELOPE_VERSION,
            "action_id": action_id,
            "summary": safe_summary,
            "summary_digest": summary_digest,
            "generator": {
                "id": FORGE_ACTION_CONTEXT_GENERATOR_ID,
                "model": FORGE_ACTION_CONTEXT_GENERATOR_MODEL,
                "version": FORGE_ACTION_CONTEXT_GENERATOR_VERSION,
                "source_digest": source_digest,
            },
        }
        return cls(
            action_id=action_id, summary=safe_summary, source_digest=source_digest,
            summary_digest=summary_digest, envelope_digest=_canonical_digest(document),
        )

    def __post_init__(self) -> None:
        if (self.envelope_version != FORGE_ACTION_CONTEXT_ENVELOPE_VERSION
                or (self.generator_id, self.generator_model, self.generator_version) != (
                    FORGE_ACTION_CONTEXT_GENERATOR_ID,
                    FORGE_ACTION_CONTEXT_GENERATOR_MODEL,
                    FORGE_ACTION_CONTEXT_GENERATOR_VERSION,
                )):
            raise ValueError("action context envelope version or generator is unsupported")
        if (not isinstance(self.action_id, str) or not self.action_id or len(self.action_id) > 128
                or not _SHA256.fullmatch(self.source_digest)
                or not _SHA256.fullmatch(self.summary_digest)
                or not _SHA256.fullmatch(self.envelope_digest)
                or self.summary != redact_action_summary(self.summary)
                or self.summary_digest != _canonical_digest(self.summary)):
            raise ValueError("action context envelope is invalid")
        if self.envelope_digest != _canonical_digest(self._document_without_envelope_digest()):
            raise ValueError("action context envelope digest is invalid")

    def _document_without_envelope_digest(self) -> dict[str, object]:
        return {
            "envelope_version": self.envelope_version,
            "action_id": self.action_id,
            "summary": self.summary,
            "summary_digest": self.summary_digest,
            "generator": {
                "id": self.generator_id,
                "model": self.generator_model,
                "version": self.generator_version,
                "source_digest": self.source_digest,
            },
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._document_without_envelope_digest(), "envelope_digest": self.envelope_digest}


class ProducerType(str, Enum):
    """Built-in Producer type vocabulary; strings retain future extensibility."""

    HUMAN = "HUMAN"
    FORGE = "FORGE"
    EXTERNAL = "EXTERNAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, order=True)
class ProducerIdentity:
    """Immutable traceability identity; it never changes Host semantics."""

    id: str
    type: ProducerType | str
    version: str

    def __post_init__(self) -> None:
        if not self.id or not self.version:
            raise ValueError("producer identity, type, and version are required")
        producer_type = self.type.value if isinstance(self.type, ProducerType) else self.type
        if not _TYPE.fullmatch(producer_type):
            raise ValueError("producer type must be an extensible uppercase identifier")
        object.__setattr__(self, "type", producer_type)

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "type": str(self.type), "version": self.version}


@dataclass(frozen=True)
class Producer:
    """First-class Forge-owned planning producer, independent of any Host."""

    identity: ProducerIdentity
    contract_version: str = PRODUCER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != PRODUCER_CONTRACT_VERSION:
            raise ValueError("producer contract version is unsupported")

    def to_dict(self) -> dict[str, Any]:
        return {"contract_version": self.contract_version, "identity": self.identity.to_dict()}


# The Producer identity is a factual application identity, not the Producer
# Contract schema version.  Hosts must be able to attribute a submitted
# envelope to the Forge build that materialised it.
DEFAULT_FORGE_PRODUCER = Producer(ProducerIdentity("forge", ProducerType.FORGE, canonical_version()))


@dataclass(frozen=True)
class RuntimePromptEnvelope:
    """Host-neutral Runtime Prompt presentation carried across the boundary."""

    id: str
    version: str
    format: str
    content: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.id, self.version, self.format, self.content, self.content_digest)):
            raise ValueError("runtime prompt envelope identity, version, format, content, and digest are required")
        if not self.content_digest.startswith("sha256:"):
            raise ValueError("runtime prompt envelope digest must be sha256")

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "version": self.version, "format": self.format,
                "content": self.content, "content_digest": self.content_digest}


@dataclass(frozen=True, order=True)
class ExecutionReceiptReference:
    """A host-owned receipt reference; Forge only carries it for correlation."""

    host_id: str
    receipt_id: str

    def __post_init__(self) -> None:
        if not self.host_id or not self.receipt_id:
            raise ValueError("execution receipt host and identity are required")

    def to_dict(self) -> dict[str, str]:
        return {"host_id": self.host_id, "receipt_id": self.receipt_id}


@dataclass(frozen=True)
class ProducerContract:
    """The canonical Producer-to-Execution-Host envelope.

    Receipts and evidence references remain Host-owned values.  Their presence
    here establishes correlation only and grants the Producer no execution or
    telemetry ownership.
    """

    producer: Producer
    correlation_id: str
    engineering_action_id: str
    runtime_prompt: RuntimePromptEnvelope
    execution_constraints: tuple[str, ...]
    execution_metadata: tuple[tuple[str, str], ...]
    action_context: ForgeActionContextEnvelope | None = None
    mission_id: str | None = None
    receipt_references: tuple[ExecutionReceiptReference, ...] = ()
    execution_evidence_references: tuple[str, ...] = ()
    contract_version: str = PRODUCER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != PRODUCER_CONTRACT_VERSION:
            raise ValueError("producer contract version is unsupported")
        if not all((self.correlation_id, self.engineering_action_id)):
            raise ValueError("producer contract correlation and engineering action are required")
        if self.action_context is not None and self.action_context.action_id != self.engineering_action_id:
            raise ValueError("producer contract Action context must match its engineering action")
        if not self.execution_constraints or any(not value for value in self.execution_constraints):
            raise ValueError("producer contract execution constraints are required")
        if len(self.execution_constraints) != len(set(self.execution_constraints)):
            raise ValueError("producer contract execution constraints must be unique")
        metadata = tuple(sorted(self.execution_metadata))
        if any(not key or not value for key, value in metadata) or len({key for key, _ in metadata}) != len(metadata):
            raise ValueError("producer contract execution metadata keys and values must be unique and non-empty")
        if len(self.receipt_references) != len(set(self.receipt_references)):
            raise ValueError("producer contract receipt references must be unique")
        if any(not value for value in self.execution_evidence_references) or len(self.execution_evidence_references) != len(set(self.execution_evidence_references)):
            raise ValueError("producer contract execution evidence references must be unique and non-empty")
        object.__setattr__(self, "execution_constraints", tuple(sorted(self.execution_constraints)))
        object.__setattr__(self, "execution_metadata", metadata)
        object.__setattr__(self, "receipt_references", tuple(sorted(self.receipt_references)))
        object.__setattr__(self, "execution_evidence_references", tuple(sorted(self.execution_evidence_references)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "producer": self.producer.to_dict(),
            "correlation_id": self.correlation_id,
            "mission_id": self.mission_id,
            "engineering_action_id": self.engineering_action_id,
            "runtime_prompt": self.runtime_prompt.to_dict(),
            "execution_constraints": list(self.execution_constraints),
            "execution_metadata": {key: value for key, value in self.execution_metadata},
            "action_context": None if self.action_context is None else self.action_context.to_dict(),
            "receipt_references": [item.to_dict() for item in self.receipt_references],
            "execution_evidence_references": list(self.execution_evidence_references),
        }

    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()
