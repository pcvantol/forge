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


PRODUCER_CONTRACT_VERSION = "1.0"
_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


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


DEFAULT_FORGE_PRODUCER = Producer(ProducerIdentity("forge", ProducerType.FORGE, "1.0"))


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
    mission_id: str | None = None
    receipt_references: tuple[ExecutionReceiptReference, ...] = ()
    execution_evidence_references: tuple[str, ...] = ()
    contract_version: str = PRODUCER_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.contract_version != PRODUCER_CONTRACT_VERSION:
            raise ValueError("producer contract version is unsupported")
        if not all((self.correlation_id, self.engineering_action_id)):
            raise ValueError("producer contract correlation and engineering action are required")
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
            "receipt_references": [item.to_dict() for item in self.receipt_references],
            "execution_evidence_references": list(self.execution_evidence_references),
        }

    def digest(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(payload).hexdigest()
