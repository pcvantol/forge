"""Immutable, repository-only contracts for deterministic Mission planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .action import EngineeringAction
from .architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from .intent import IntentReference
from .mission_completion import MissionCriterionEvaluationStatus


MISSION_PLANNER_SCHEMA_VERSION = "4.3"
MAX_CONTINUATION_CONTEXT_BYTES = 131_072


@dataclass(frozen=True)
class MissionContinuationContext:
    """Immutable bounded planning facts; observed artifact values stay private."""

    document_json: str

    def __post_init__(self) -> None:
        if (not isinstance(self.document_json, str)
                or len(self.document_json.encode("utf-8")) > MAX_CONTINUATION_CONTEXT_BYTES):
            raise ValueError("Mission continuation context exceeds its byte bound")
        document = json.loads(self.document_json)
        if (not isinstance(document, dict) or set(document) - {"verified_delegations"} != {
                "schema_version", "mission_id", "approved_planning", "criterion_assessments",
                "prior_actions", "terminal_evidence", "repository_truth"}
                or document["schema_version"] != "1.0"):
            raise ValueError("Mission continuation context schema is invalid")
        if json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False) != self.document_json:
            raise ValueError("Mission continuation context must be canonical JSON")
        if (not isinstance(document["approved_planning"], dict)
                or not isinstance(document["repository_truth"], dict)
                or any(not isinstance(document[key], list) for key in (
                    "criterion_assessments", "prior_actions", "terminal_evidence"))):
            raise ValueError("Mission continuation context collections are invalid")
        delegations = document.get("verified_delegations", [])
        if (not isinstance(delegations, list) or any(
                not isinstance(item, dict) or set(item) != {"delegation_id", "action_id", "outcome"}
                or item["outcome"] != "verified_external_completion"
                or not isinstance(item["delegation_id"], str) or not item["delegation_id"]
                or not isinstance(item["action_id"], str) or not item["action_id"]
                for item in delegations)):
            raise ValueError("Mission continuation verified delegation is invalid")
        observation_keys = {
            "observation_id", "mission_id", "mission_digest", "criterion_id", "contract_digest", "requirement_id",
            "receipt_id", "action_id", "report_id", "repository_revision", "repository_evidence_digest",
            "source_kind", "source_identity", "artifact_path", "content_digest", "result", "reason",
            "requirement_digest", "json_pointer", "candidate_revision",
        }
        for assessment in document["criterion_assessments"]:
            if (not isinstance(assessment, dict) or set(assessment) != {
                    "criterion_id", "criterion", "contract_digest", "status", "reason",
                    "requirement_results", "observation_summaries"}
                    or assessment["status"] not in {"PROVEN", "UNSATISFIED"}
                    or not isinstance(assessment["reason"], str) or not assessment["reason"]
                    or not isinstance(assessment["requirement_results"], list)
                    or not isinstance(assessment["observation_summaries"], list)):
                raise ValueError("Mission continuation criterion assessment is invalid")
            for result in assessment["requirement_results"]:
                if not isinstance(result, dict) or set(result) != {
                        "requirement_id", "requirement_digest", "status", "reason", "observation_ids"}:
                    raise ValueError("Mission continuation requirement result is invalid")
            if any(not isinstance(observation, dict) or set(observation) != observation_keys
                   for observation in assessment["observation_summaries"]):
                raise ValueError("Mission continuation permits observation provenance only")

    def to_dict(self) -> dict[str, Any]:
        # Returning a fresh document cannot mutate a claimed planning snapshot.
        return json.loads(self.document_json)

    @classmethod
    def from_runtime(
        cls, mission: ArchitectureMission, *, planning: Mapping[str, Any],
        actions: Sequence[Mapping[str, Any]], execution_history: Sequence[Mapping[str, Any]],
        completion: Mapping[str, Any] | None, repository_truth: Mapping[str, Any],
        delegations: Sequence[Mapping[str, Any]] = (),
    ) -> "MissionContinuationContext":
        from .criterion_observation import CriterionObservation
        from .mission_completion import mission_criterion_id

        planning_keys = (
            "scope", "write_scopes", "non_goals", "risk_inputs", "human_gates", "dependencies",
            "context_input_bound", "context_output_bound", "provenance_revision",
            "criterion_assessment_contracts", "maximum_actions",
            "maximum_consecutive_no_progress_actions", "repository_evidence_source",
        )
        required_planning_keys = set(planning_keys) - {"repository_evidence_source"}
        if not required_planning_keys <= set(planning):
            raise ValueError("Mission continuation context lacks approved planning authority")
        approved = {key: planning[key] for key in planning_keys if key in planning}
        rows = () if completion is None else completion.get("criteria", ())
        assessments = {item["criterion_id"]: item for item in rows}
        if len(assessments) != len(rows):
            raise ValueError("Mission continuation contains conflicting criterion assessments")
        allowed_ids = {mission_criterion_id(mission.id, item.criterion) for item in mission.criterion_assessment_contracts}
        if set(assessments) - allowed_ids:
            raise ValueError("Mission continuation contains unknown criterion assessments")
        projected = []
        contributions: dict[str, list[dict[str, str]]] = {}
        for contract in mission.criterion_assessment_contracts:
            criterion_id = mission_criterion_id(mission.id, contract.criterion)
            assessment = assessments.get(criterion_id)
            summary = {"criterion_id": criterion_id, "criterion": contract.criterion,
                       "contract_digest": contract.digest,
                       "status": "UNSATISFIED" if assessment is None else assessment["status"],
                       "reason": "NOT_ASSESSED" if assessment is None else assessment["reason"],
                       "requirement_results": [], "observation_summaries": []}
            if assessment is not None:
                summary["requirement_results"] = [
                    {key: item[key] for key in ("requirement_id", "requirement_digest", "status", "reason", "observation_ids")}
                    for item in assessment.get("requirement_results", ())
                ]
                for raw in assessment.get("observations", ()):
                    observation = CriterionObservation.from_dict(dict(raw))
                    summary["observation_summaries"].append({
                        "observation_id": observation.id,
                        **{key: raw[key] for key in (
                            "mission_id", "mission_digest", "criterion_id", "contract_digest", "requirement_id",
                            "receipt_id", "action_id", "report_id", "repository_revision", "repository_evidence_digest",
                            "source_kind", "source_identity", "artifact_path", "content_digest", "result", "reason",
                            "requirement_digest", "json_pointer", "candidate_revision",
                        )},
                    })
                    contributions.setdefault(observation.action_id, []).append({
                        "criterion_id": criterion_id, "requirement_id": observation.requirement_id,
                        "observation_id": observation.id, "observation_result": observation.result,
                    })
            projected.append(summary)
        prior = [{**{key: item[key] for key in (
            "id", "order", "intent_id", "intent_revision", "objective", "expected_evidence", "dependencies", "status",
        )}, "observed_contributions": contributions.get(str(item["id"]), [])} for item in actions]
        terminals = []
        verified_delegations = []
        for item in execution_history:
            if item.get("outcome") == "verified_external_completion":
                delegation = next((value for value in delegations
                                   if value.get("id") == item.get("delegation_id")), None)
                if (delegation is None or delegation.get("result_state") != "accepted"
                        or not isinstance(delegation.get("verification"), Mapping)
                        or delegation["verification"].get("verified") is not True
                        or delegation.get("action_id") not in {action["id"] for action in prior}):
                    raise ValueError("Mission continuation delegation lacks verified Action lineage")
                verified_delegations.append({"delegation_id": delegation["id"],
                                             "action_id": delegation["action_id"],
                                             "outcome": "verified_external_completion"})
                continue
            repository = item.get("repository_evidence")
            if not isinstance(repository, Mapping):
                if (item.get("outcome") == "failed"
                        and set(item) <= {"outcome", "diagnostic_references", "failure_code"}
                        and item.get("diagnostic_references") in (
                            ["runner:host_dispatch_failed"], ["runner:host_evidence_failed"])):
                    terminals.append({"outcome": "failed", "receipt_id": None,
                                      "repository_evidence": None,
                                      "reason": "HOST_EVIDENCE_UNAVAILABLE"})
                    continue
                raise ValueError("Mission continuation terminal evidence lacks repository identity")
            terminals.append({
                **{key: item.get(key) for key in ("host_id", "correlation_id", "host_run_id", "report_id", "receipt_id", "outcome")},
                "repository_evidence": {
                    **{key: repository[key] for key in (
                        "mission_id", "intent_id", "intent_revision", "action_id", "runtime_prompt_id",
                        "correlation_id", "host_run_id", "repository_id", "repository_revision", "report_id", "content_digest",
                    )},
                    **({"candidate_revision": repository["candidate_revision"]}
                       if "candidate_revision" in repository else {}),
                },
            })
        document = {"schema_version": "1.0", "mission_id": mission.id, "approved_planning": approved,
                    "criterion_assessments": projected, "prior_actions": prior,
                    "terminal_evidence": terminals,
                    "repository_truth": {key: repository_truth[key] for key in ("source_id", "revision", "locator", "content_digest")}}
        if verified_delegations:
            document["verified_delegations"] = verified_delegations
        return cls(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))


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
class MissionCriterionPlanningState:
    """Forge-derived status of one approved Mission criterion at planning time."""

    criterion_id: str
    status: MissionCriterionEvaluationStatus

    def __post_init__(self) -> None:
        if not self.criterion_id:
            raise ValueError("Mission criterion planning state requires criterion identity")
        if not isinstance(self.status, MissionCriterionEvaluationStatus):
            raise ValueError("Mission criterion planning state status is invalid")


@dataclass(frozen=True)
class MissionPlanningState:
    """Planner-visible Mission progress, without Runtime or host implementation state."""

    mission_id: str
    revision: int
    completed_action_ids: tuple[str, ...] = ()
    blocked_action_ids: tuple[str, ...] = ()
    criterion_states: tuple[MissionCriterionPlanningState, ...] = ()
    continuation_context: MissionContinuationContext | None = None

    def __post_init__(self) -> None:
        if not self.mission_id or self.revision < 1:
            raise ValueError("mission planning state requires mission identity and positive revision")
        for name in ("completed_action_ids", "blocked_action_ids"):
            values = getattr(self, name)
            if len(values) != len(set(values)) or any(not item for item in values):
                raise ValueError(f"mission planning state {name} must be unique and non-empty")
            object.__setattr__(self, name, tuple(sorted(values)))
        criterion_ids = tuple(item.criterion_id for item in self.criterion_states)
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Mission criterion planning states must be unique")
        object.__setattr__(self, "criterion_states", tuple(sorted(
            self.criterion_states, key=lambda item: item.criterion_id,
        )))
        if self.continuation_context is not None and not isinstance(self.continuation_context, MissionContinuationContext):
            raise ValueError("Mission continuation context must be typed")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        if self.continuation_context is None:
            document.pop("continuation_context")
        else:
            document["continuation_context"] = self.continuation_context.to_dict()
        return document


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
        context = self.mission_state.continuation_context
        if self.mission.criterion_assessment_contracts:
            if context is None:
                raise ValueError("contract-bearing Mission planning requires continuation context")
            document = context.to_dict()
            approved = document["approved_planning"]
            mission_document = self.mission.to_dict()
            if (document["mission_id"] != self.mission.id or any(
                    approved.get(key) != mission_document.get(key) for key in (
                        "criterion_assessment_contracts", "maximum_actions", "maximum_consecutive_no_progress_actions",
                        "repository_evidence_source", "scope"))):
                raise ValueError("Mission continuation context differs from the approved Mission")
            from .mission_completion import mission_criterion_id
            expected_criteria = {mission_criterion_id(self.mission.id, item.criterion): item
                                 for item in self.mission.criterion_assessment_contracts}
            assessments = document["criterion_assessments"]
            if (len(assessments) != len(expected_criteria)
                    or {item.get("criterion_id") for item in assessments} != set(expected_criteria)
                    or any(item.get("criterion") != expected_criteria[item["criterion_id"]].criterion
                           or item.get("contract_digest") != expected_criteria[item["criterion_id"]].digest
                           for item in assessments)):
                raise ValueError("Mission continuation context omits or changes approved criteria")
            statuses = {item.criterion_id: item.status.value for item in self.mission_state.criterion_states}
            if any(item["status"] != statuses.get(item["criterion_id"], "UNSATISFIED") for item in assessments):
                raise ValueError("Mission continuation assessments contradict criterion state")
            previous_ids = {item["id"] for item in document["prior_actions"]}
            if (len(previous_ids) != len(document["prior_actions"])
                    or not (set(self.mission_state.completed_action_ids) | set(self.mission_state.blocked_action_ids)) <= previous_ids):
                raise ValueError("Mission continuation context omits prior Action history")
            completed_receipts = {item["repository_evidence"]["action_id"] for item in document["terminal_evidence"]
                                  if item["outcome"] == "complete" and item["receipt_id"]}
            completed_receipts.update(item["action_id"] for item in document.get("verified_delegations", ()))
            if not set(self.mission_state.completed_action_ids) <= completed_receipts:
                raise ValueError("Mission continuation context omits completed Action receipts")
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
                "mission_state": self.mission_state.to_dict(), "evidence": [item.to_dict() for item in self.evidence],
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
