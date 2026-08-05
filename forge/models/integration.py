"""Immutable, Forge-owned contracts for coordinating completed work integration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping


INTEGRATION_SCHEMA_VERSION = "1.0"


class IntegrationOutcome(str, Enum):
    COMPLETE = "complete"
    BLOCKED = "blocked"
    WAITING = "waiting_integration"


class IntegrationEventKind(str, Enum):
    MERGE_CONFLICT = "MERGE_CONFLICT"
    INTEGRATION_BLOCKED = "INTEGRATION_BLOCKED"
    WAITING_INTEGRATION = "WAITING_INTEGRATION"
    INTEGRATION_COMPLETE = "INTEGRATION_COMPLETE"


class ConflictResolutionKind(str, Enum):
    NOT_REQUIRED = "not_required"
    DELEGATE = "delegate"
    MANUAL = "manual"


@dataclass(frozen=True, order=True)
class IntegrationUnit:
    """One completed Action's immutable input to Forge integration."""

    id: str
    mission_id: str
    action_id: str
    execution_receipt_id: str
    repository_commit: str
    repository_branch: str
    repository_scope: tuple[str, ...]
    runtime_metadata: tuple[tuple[str, str], ...]
    decision_evidence_references: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    validation_passed: bool = False
    required_approvals_satisfied: bool = False
    schema_version: str = INTEGRATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INTEGRATION_SCHEMA_VERSION or not all((
            self.id, self.mission_id, self.action_id, self.execution_receipt_id,
            self.repository_commit, self.repository_branch,
        )):
            raise ValueError("integration unit requires identity, mission, action, receipt, commit, and branch")
        if not self.repository_scope or any(not value for value in self.repository_scope):
            raise ValueError("integration unit requires a non-empty repository scope")
        if not self.decision_evidence_references or any(not value for value in self.decision_evidence_references):
            raise ValueError("integration unit requires Decision Evidence references")
        if self.id in self.dependencies or len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("integration unit dependencies must be unique and cannot include itself")
        metadata = tuple(sorted(self.runtime_metadata))
        if any(not key or not value for key, value in metadata) or len(metadata) != len(set(metadata)):
            raise ValueError("integration unit runtime metadata must be unique non-empty key-value pairs")
        object.__setattr__(self, "repository_scope", tuple(sorted(set(self.repository_scope))))
        object.__setattr__(self, "runtime_metadata", metadata)
        object.__setattr__(self, "decision_evidence_references", tuple(sorted(set(self.decision_evidence_references))))
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies)))

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["repository_scope"] = list(self.repository_scope)
        document["runtime_metadata"] = [list(item) for item in self.runtime_metadata]
        document["decision_evidence_references"] = list(self.decision_evidence_references)
        document["dependencies"] = list(self.dependencies)
        return document

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "IntegrationUnit":
        return cls(
            str(document["id"]), str(document["mission_id"]), str(document["action_id"]),
            str(document["execution_receipt_id"]), str(document["repository_commit"]),
            str(document["repository_branch"]), tuple(document["repository_scope"]),
            tuple(tuple(item) for item in document["runtime_metadata"]),
            tuple(document["decision_evidence_references"]), tuple(document.get("dependencies", ())),
            bool(document.get("validation_passed", False)), bool(document.get("required_approvals_satisfied", False)),
            str(document.get("schema_version", INTEGRATION_SCHEMA_VERSION)),
        )


@dataclass(frozen=True, order=True)
class IntegrationConflict:
    """A detected conflict; detection never changes repository content."""

    id: str
    unit_ids: tuple[str, ...]
    conflict_type: str
    scopes: tuple[str, ...]
    resolution: ConflictResolutionKind
    required_capability: str | None = None

    def __post_init__(self) -> None:
        if not self.id or len(self.unit_ids) < 2 or not self.conflict_type or not self.scopes:
            raise ValueError("integration conflict requires identity, units, type, and scope")
        if self.resolution is ConflictResolutionKind.DELEGATE and not self.required_capability:
            raise ValueError("delegated integration conflict requires a capability")
        object.__setattr__(self, "unit_ids", tuple(sorted(set(self.unit_ids))))
        object.__setattr__(self, "scopes", tuple(sorted(set(self.scopes))))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "unit_ids": list(self.unit_ids), "conflict_type": self.conflict_type,
                "scopes": list(self.scopes), "resolution": self.resolution.value,
                "required_capability": self.required_capability}


@dataclass(frozen=True)
class IntegrationEvidence:
    """Append-only decision record produced by the Integration Coordinator."""

    id: str
    mission_id: str
    integration_units: tuple[IntegrationUnit, ...]
    timestamp: str
    outcome: IntegrationOutcome
    merge_result: str
    decision_evidence_references: tuple[str, ...]
    execution_receipt_references: tuple[str, ...]
    conflicts: tuple[IntegrationConflict, ...] = ()
    resolution: str = "not_required"
    schema_version: str = INTEGRATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INTEGRATION_SCHEMA_VERSION or not all((self.id, self.mission_id, self.timestamp, self.merge_result, self.resolution)):
            raise ValueError("integration evidence requires identity, mission, timestamp, merge result, and resolution")
        if not self.integration_units or any(unit.mission_id != self.mission_id for unit in self.integration_units):
            raise ValueError("integration evidence requires units from its Mission")
        if not self.decision_evidence_references or not self.execution_receipt_references:
            raise ValueError("integration evidence requires Decision Evidence and Execution Receipt references")
        for name in ("integration_units", "decision_evidence_references", "execution_receipt_references", "conflicts"):
            values = getattr(self, name)
            if len(values) != len(set(values)):
                raise ValueError(f"integration evidence {name} must be unique")
        object.__setattr__(self, "integration_units", tuple(sorted(self.integration_units, key=lambda item: item.id)))
        object.__setattr__(self, "decision_evidence_references", tuple(sorted(self.decision_evidence_references)))
        object.__setattr__(self, "execution_receipt_references", tuple(sorted(self.execution_receipt_references)))
        object.__setattr__(self, "conflicts", tuple(sorted(self.conflicts, key=lambda item: item.id)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id, "mission_id": self.mission_id,
                "integration_units": [item.to_dict() for item in self.integration_units], "timestamp": self.timestamp,
                "outcome": self.outcome.value, "merge_result": self.merge_result,
                "decision_evidence_references": list(self.decision_evidence_references),
                "execution_receipt_references": list(self.execution_receipt_references),
                "conflicts": [item.to_dict() for item in self.conflicts], "resolution": self.resolution}

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "IntegrationEvidence":
        return cls(
            str(document["id"]), str(document["mission_id"]),
            tuple(IntegrationUnit.from_dict(item) for item in document["integration_units"]),
            str(document["timestamp"]), IntegrationOutcome(document["outcome"]), str(document["merge_result"]),
            tuple(document["decision_evidence_references"]), tuple(document["execution_receipt_references"]),
            tuple(IntegrationConflict(str(item["id"]), tuple(item["unit_ids"]), str(item["conflict_type"]), tuple(item["scopes"]),
                                      ConflictResolutionKind(item["resolution"]), item.get("required_capability"))
                  for item in document.get("conflicts", ())), str(document.get("resolution", "not_required")),
            str(document.get("schema_version", INTEGRATION_SCHEMA_VERSION)),
        )

    @property
    def content_digest(self) -> str:
        return "sha256:" + sha256(json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
