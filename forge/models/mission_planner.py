"""Immutable, repository-only contracts for deterministic Mission planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any

from .action import EngineeringAction
from .architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from .intent import IntentReference


MISSION_PLANNER_SCHEMA_VERSION = "4.2"


class PlanningInputKind(str, Enum):
    """The complete allow-list; conversations, prompts, and hosts have no kind."""

    MISSION_STATE = "mission_state"
    REPOSITORY_TRUTH = "repository_truth"
    REPOSITORY_CONTEXT = "repository_context"
    ARCHITECTURE_REVIEW = "architecture_review"
    CAPABILITY_CATALOGUE = "capability_catalogue"
    ENGINEERING_HISTORY = "engineering_history"
    EXECUTION_EVIDENCE = "execution_evidence"
    HISTORICAL_INTENT = "historical_intent"
    ENGINEERING_ACTION_HISTORY = "engineering_action_history"
    REPOSITORY_MATURITY = "repository_maturity"
    MISSION_REFINEMENT = "mission_refinement"


@dataclass(frozen=True, order=True)
class PlanningEvidence:
    """Digest-pinned evidence that the Planner may consume but never retrieve."""

    kind: PlanningInputKind
    source_id: str
    revision: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        digest = self.content_digest.removeprefix("sha256:")
        if not all((self.source_id, self.revision, self.locator)):
            raise ValueError("planning evidence identity, revision, and locator are required")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError("planning evidence content digest must be a sha256 digest")

    def to_dict(self) -> dict[str, str]:
        document = asdict(self)
        document["kind"] = self.kind.value
        return document


@dataclass(frozen=True, order=True)
class PlannedActionDefinition:
    """One explicitly permitted atomic Action inside an approved scope boundary."""

    id: str
    objective: str
    expected_evidence: tuple[str, ...]
    validation_strategy: tuple[str, ...]
    priority: int = 100
    postponed: bool = False
    merge_key: str | None = None
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.objective or not self.expected_evidence or not self.validation_strategy or self.priority < 1:
            raise ValueError("planned action requires identity, objective, evidence, validation, and positive priority")
        for name in ("expected_evidence", "validation_strategy"):
            values = getattr(self, name)
            if len(values) != len(set(values)) or any(not item for item in values):
                raise ValueError(f"planned action {name} must be unique and non-empty")
            object.__setattr__(self, name, tuple(sorted(values)))
        if self.merge_key == "":
            raise ValueError("planned action merge key must be non-empty when supplied")
        if self.id in self.dependencies or len(self.dependencies) != len(set(self.dependencies)) or any(not item for item in self.dependencies):
            raise ValueError("planned action dependencies must be unique, non-empty, and cannot include itself")
        object.__setattr__(self, "dependencies", tuple(sorted(self.dependencies)))


@dataclass(frozen=True, order=True)
class ApprovedScope:
    """Machine-enforceable mapping from an Architecture Mission boundary to Actions."""

    scope: str
    capability_id: str
    architecture_references: tuple[IntentReference, ...]
    actions: tuple[PlannedActionDefinition, ...]
    allow_provider_derivation: bool = False

    def __post_init__(self) -> None:
        if not self.scope or not self.capability_id or not self.architecture_references or (not self.actions and not self.allow_provider_derivation):
            raise ValueError("approved scope requires scope, capability, architecture references, and actions")
        if len(self.architecture_references) != len(set(self.architecture_references)):
            raise ValueError("approved scope architecture references must be unique")
        if len({action.id for action in self.actions}) != len(self.actions):
            raise ValueError("approved scope action ids must be unique")
        object.__setattr__(self, "architecture_references", tuple(sorted(self.architecture_references)))
        object.__setattr__(self, "actions", tuple(sorted(self.actions, key=lambda item: (item.priority, item.id))))


@dataclass(frozen=True)
class MissionPlanningState:
    """Planner-visible Mission progress, without Runtime or host implementation state."""

    mission_id: str
    revision: int
    completed_action_ids: tuple[str, ...] = ()
    blocked_action_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.mission_id or self.revision < 1:
            raise ValueError("mission planning state requires mission identity and positive revision")
        for name in ("completed_action_ids", "blocked_action_ids"):
            values = getattr(self, name)
            if len(values) != len(set(values)) or any(not item for item in values):
                raise ValueError(f"mission planning state {name} must be unique and non-empty")
            object.__setattr__(self, name, tuple(sorted(values)))


@dataclass(frozen=True)
class MissionPlannerInput:
    """The Planner's entire deterministic, repository-only input boundary."""

    mission: ArchitectureMission
    mission_state: MissionPlanningState
    evidence: tuple[PlanningEvidence, ...]
    approved_scopes: tuple[ApprovedScope, ...]
    schema_version: str = MISSION_PLANNER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MISSION_PLANNER_SCHEMA_VERSION:
            raise ValueError("mission planner input schema version is unsupported")
        if self.mission.status is not ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING:
            raise ValueError("mission planner requires an approved_for_engineering Architecture Mission")
        if self.mission_state.mission_id != self.mission.id:
            raise ValueError("mission planning state must belong to the approved Mission")
        if not self.evidence or not self.approved_scopes:
            raise ValueError("mission planner requires evidence and a complete approved scope map")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("mission planner evidence must be unique")
        kinds = {item.kind for item in self.evidence}
        required = {PlanningInputKind.MISSION_STATE, PlanningInputKind.ARCHITECTURE_REVIEW, PlanningInputKind.CAPABILITY_CATALOGUE}
        if not required <= kinds or not ({PlanningInputKind.REPOSITORY_TRUTH, PlanningInputKind.REPOSITORY_CONTEXT} & kinds):
            raise ValueError("mission planner requires Mission State, Repository Truth, Architecture Review, and Capability Catalogue evidence")
        scopes = {item.scope for item in self.approved_scopes}
        if scopes != set(self.mission.scope):
            raise ValueError("approved scope map must cover exactly the Mission boundaries")
        if {item.capability_id for item in self.approved_scopes} - set(self.mission.required_capabilities):
            raise ValueError("approved scope map may only affect Mission-required capabilities")
        action_ids = [action.id for scope in self.approved_scopes for action in scope.actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("approved scope map action ids must be globally unique")
        object.__setattr__(self, "evidence", tuple(sorted(self.evidence)))
        object.__setattr__(self, "approved_scopes", tuple(sorted(self.approved_scopes, key=lambda item: item.scope)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "mission": self.mission.to_dict(),
                "mission_state": asdict(self.mission_state), "evidence": [item.to_dict() for item in self.evidence],
                "approved_scopes": [{"scope": item.scope, "capability_id": item.capability_id,
                    "architecture_references": [reference.to_dict() for reference in item.architecture_references], "allow_provider_derivation": item.allow_provider_derivation,
                    "actions": [{**asdict(action), "expected_evidence": list(action.expected_evidence), "validation_strategy": list(action.validation_strategy)} for action in item.actions]} for item in self.approved_scopes]}


@dataclass(frozen=True)
class PlannedEngineeringIntent:
    """Planner-owned tactical Intent: planning data only, never an execution authority."""

    id: str
    revision: str
    objective: str
    rationale: str
    architecture_references: tuple[IntentReference, ...]
    capability_impact: tuple[str, ...]
    validation_strategy: tuple[str, ...]
    expected_repository_evidence: tuple[str, ...]
    actions: tuple[EngineeringAction, ...]

    def __post_init__(self) -> None:
        if not all((self.id, self.revision, self.objective, self.rationale)) or not self.architecture_references or not self.capability_impact or not self.validation_strategy or not self.expected_repository_evidence or not self.actions:
            raise ValueError("planned Engineering Intent requires complete tactical planning fields and actions")
        if any(action.intent_id != self.id or action.intent_revision != self.revision for action in self.actions):
            raise ValueError("planned Engineering Intent actions must belong to the exact Intent revision")
        object.__setattr__(self, "architecture_references", tuple(sorted(self.architecture_references)))
        for name in ("capability_impact", "validation_strategy", "expected_repository_evidence"):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))
        object.__setattr__(self, "actions", tuple(sorted(self.actions)))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "revision": self.revision, "objective": self.objective, "rationale": self.rationale,
                "architecture_references": [reference.to_dict() for reference in self.architecture_references],
                "capability_impact": list(self.capability_impact), "validation_strategy": list(self.validation_strategy),
                "expected_repository_evidence": list(self.expected_repository_evidence), "actions": [action.to_dict() for action in self.actions]}


@dataclass(frozen=True)
class MissionPlan:
    """An immutable deterministic plan; it produces no prompt and performs no work."""

    id: str
    mission_id: str
    input_digest: str
    intents: tuple[PlannedEngineeringIntent, ...]
    deferred_action_ids: tuple[str, ...]
    schema_version: str = MISSION_PLANNER_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "id": self.id, "mission_id": self.mission_id,
                "input_digest": self.input_digest, "intents": [item.to_dict() for item in self.intents],
                "deferred_action_ids": list(self.deferred_action_ids)}


def planning_digest(planning_input: MissionPlannerInput) -> str:
    return "sha256:" + sha256(json.dumps(planning_input.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
