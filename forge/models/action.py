"""Immutable contracts for Bootstrap Mission Scheduler Engineering Actions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


ENGINEERING_ACTION_SCHEMA_VERSION = "2.0"


class EngineeringActionStatus(str, Enum):
    READY = "READY"
    ACTIVE = "ACTIVE"
    WAITING_FOR_RESULT = "WAITING_FOR_RESULT"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True, order=True)
class EngineeringAction:
    """One bounded executable unit owned by an Intent, never an executor."""

    order: int
    id: str
    intent_id: str
    intent_revision: str
    objective: str
    expected_evidence: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    status: EngineeringActionStatus = EngineeringActionStatus.READY
    schema_version: str = ENGINEERING_ACTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENGINEERING_ACTION_SCHEMA_VERSION:
            raise ValueError("engineering action schema version is unsupported")
        if self.order < 1 or not all((self.id, self.intent_id, self.intent_revision, self.objective)):
            raise ValueError("engineering action order, identity, intent provenance, and objective are required")
        if not self.expected_evidence or any(not item for item in self.expected_evidence):
            raise ValueError("engineering action expected evidence is required")
        if self.id in self.dependencies or len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("engineering action dependencies must be unique and cannot include itself")
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies)))
        object.__setattr__(self, "expected_evidence", tuple(sorted(self.expected_evidence)))

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["status"] = self.status.value
        document["dependencies"] = list(self.dependencies)
        document["expected_evidence"] = list(self.expected_evidence)
        return document
