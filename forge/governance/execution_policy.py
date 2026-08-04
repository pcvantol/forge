"""Forge-owned execution progression policy, independent of Execution Hosts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

EXECUTION_POLICY_SCHEMA_VERSION = "1.0"


class ExecutionPolicyKind(str, Enum):
    CONTINUOUS = "continuous"
    ENGINEERING_ACTION_REVIEW = "engineering_action_review"
    ENGINEERING_INTENT_REVIEW = "engineering_intent_review"
    CAPABILITY_REVIEW = "capability_review"
    MISSION_REVIEW = "mission_review"
    CUSTOM = "custom"


class PauseBoundary(str, Enum):
    ENGINEERING_ACTION = "engineering_action"
    ENGINEERING_INTENT = "engineering_intent"
    CAPABILITY = "capability"
    MISSION = "mission"


@dataclass(frozen=True)
class ExecutionPolicy:
    """A versioned pause rule; it never changes Mission or host behaviour."""

    kind: ExecutionPolicyKind
    custom_boundaries: tuple[PauseBoundary, ...] = ()
    schema_version: str = EXECUTION_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXECUTION_POLICY_SCHEMA_VERSION:
            raise ValueError("execution policy schema version is unsupported")
        if self.kind is ExecutionPolicyKind.CUSTOM and not self.custom_boundaries:
            raise ValueError("custom execution policy requires at least one pause boundary")
        if self.kind is not ExecutionPolicyKind.CUSTOM and self.custom_boundaries:
            raise ValueError("only custom execution policy may define pause boundaries")
        if len(self.custom_boundaries) != len(set(self.custom_boundaries)):
            raise ValueError("custom execution policy pause boundaries must be unique")

    @property
    def boundaries(self) -> tuple[PauseBoundary, ...]:
        fixed = {
            ExecutionPolicyKind.CONTINUOUS: (),
            ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW: (PauseBoundary.ENGINEERING_ACTION,),
            ExecutionPolicyKind.ENGINEERING_INTENT_REVIEW: (PauseBoundary.ENGINEERING_INTENT,),
            ExecutionPolicyKind.CAPABILITY_REVIEW: (PauseBoundary.CAPABILITY,),
            ExecutionPolicyKind.MISSION_REVIEW: (PauseBoundary.MISSION,),
        }
        return self.custom_boundaries if self.kind is ExecutionPolicyKind.CUSTOM else fixed[self.kind]

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "kind": self.kind.value,
                "custom_boundaries": [item.value for item in self.custom_boundaries]}

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ExecutionPolicy":
        return cls(ExecutionPolicyKind(str(value["kind"])),
                   tuple(PauseBoundary(str(item)) for item in value.get("custom_boundaries", ())),
                   str(value.get("schema_version", EXECUTION_POLICY_SCHEMA_VERSION)))


@dataclass(frozen=True)
class ApprovalRecord:
    """Auditable human approval that authorizes one exact persisted pause."""

    approval_id: str
    approved_by: str
    approved_at: str
    decision_reference: str

    def __post_init__(self) -> None:
        if not all((self.approval_id, self.approved_by, self.approved_at, self.decision_reference)):
            raise ValueError("approval record requires identity, actor, time, and decision reference")

    def to_dict(self) -> dict[str, str]:
        return {"approval_id": self.approval_id, "approved_by": self.approved_by,
                "approved_at": self.approved_at, "decision_reference": self.decision_reference}
