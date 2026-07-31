"""Deterministic, local-only validation for Engineering Planning 0.5."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from forge.foundation.loader import ValidationIssue, _LocalSchemaValidator
from forge.models import (
    EngineeringGoal,
    EngineeringIncrementProposal,
    EngineeringPlan,
    EvidenceKind,
    EvidenceReference,
    IncrementDependency,
    PlanStatus,
    RiskLevel,
)


DOCUMENT_TYPE = "forge.engineering_planning"
DOCUMENT_VERSION = "0.5"
_SCHEMA_DIRECTORY = Path(__file__).resolve().parents[2] / "schemas"
_SCHEMA_NAMES = {
    "planning-document-0.5.schema.json",
    "engineering-goal-0.5.schema.json",
    "engineering-increment-proposal-0.5.schema.json",
    "engineering-plan-0.5.schema.json",
    "evidence-reference-0.5.schema.json",
    "common.schema.json",
}


@dataclass(frozen=True)
class EngineeringPlanningDocument:
    """Immutable composition of declarative planning contracts."""

    schema_version: str
    workspace_id: str
    goals: tuple[EngineeringGoal, ...]
    increment_proposals: tuple[EngineeringIncrementProposal, ...]
    plans: tuple[EngineeringPlan, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_type": DOCUMENT_TYPE,
            "schema_version": self.schema_version,
            "workspace_id": self.workspace_id,
            "goals": [goal.to_dict() for goal in self.goals],
            "increment_proposals": [proposal.to_dict() for proposal in self.increment_proposals],
            "plans": [plan.to_dict() for plan in self.plans],
        }


@dataclass(frozen=True)
class PlanningValidationReport:
    """A stable local validation result without source-document values."""

    document_version: str | None
    issues: tuple[ValidationIssue, ...]
    document: EngineeringPlanningDocument | None = None

    @property
    def valid(self) -> bool:
        return not self.issues and self.document is not None


class PlanningDocumentLoader:
    """Load planning documents without reading knowledge or executing plans."""

    def __init__(self, known_knowledge_source_ids: Iterable[str] = ()) -> None:
        self._known_knowledge_source_ids = frozenset(known_knowledge_source_ids)
        self._schemas = MappingProxyType(self._load_schemas())
        self._validator = _LocalSchemaValidator(self._schemas)

    @staticmethod
    def _load_schemas() -> dict[str, Mapping[str, Any]]:
        schemas: dict[str, Mapping[str, Any]] = {}
        for name in sorted(_SCHEMA_NAMES):
            path = _SCHEMA_DIRECTORY / name
            if not path.is_file():
                raise ValueError("required packaged Forge planning schema is unavailable")
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("packaged Forge planning schema must be a JSON object")
            schemas[name] = parsed
        return schemas

    def load(self, source: str | bytes | Mapping[str, Any]) -> PlanningValidationReport:
        parsed, parse_issues = self._parse(source)
        if parse_issues:
            return PlanningValidationReport(None, parse_issues)
        assert parsed is not None
        version, version_issues = self._detect_version(parsed)
        if version_issues:
            return PlanningValidationReport(version, version_issues)
        schema_issues = self._validator.validate(parsed, "planning-document-0.5.schema.json")
        if schema_issues:
            return PlanningValidationReport(version, tuple(sorted(schema_issues)))
        semantic_issues = self._semantic_issues(parsed)
        if semantic_issues:
            return PlanningValidationReport(version, tuple(sorted(semantic_issues)))
        try:
            document = self._construct(parsed)
        except (KeyError, TypeError, ValueError):
            return PlanningValidationReport(version, (ValidationIssue("model", "construction", "$", "cannot construct a valid Engineering Planning Document"),))
        return PlanningValidationReport(version, (), document)

    def load_path(self, path: str | Path) -> PlanningValidationReport:
        try:
            return self.load(Path(path).read_text(encoding="utf-8"))
        except OSError:
            return PlanningValidationReport(None, (ValidationIssue("parse", "read", "$", "cannot read Engineering Planning Document"),))

    @staticmethod
    def _parse(source: str | bytes | Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, tuple[ValidationIssue, ...]]:
        if isinstance(source, Mapping):
            return source, ()
        try:
            parsed = json.loads(source)
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
            return None, (ValidationIssue("parse", "invalid_json", "$", "must be valid JSON"),)
        if not isinstance(parsed, Mapping):
            return None, (ValidationIssue("parse", "root_type", "$", "must be a JSON object"),)
        return parsed, ()

    @staticmethod
    def _detect_version(document: Mapping[str, Any]) -> tuple[str | None, tuple[ValidationIssue, ...]]:
        if document.get("document_type") != DOCUMENT_TYPE:
            return None, (ValidationIssue("version", "document_type", "$.document_type", "must identify a Forge Engineering Planning Document"),)
        version = document.get("schema_version")
        if not isinstance(version, str):
            return None, (ValidationIssue("version", "missing_version", "$.schema_version", "must declare a schema version"),)
        if version != DOCUMENT_VERSION:
            return version, (ValidationIssue("version", "unsupported_version", "$.schema_version", "is not supported by this Forge version"),)
        return version, ()

    def _semantic_issues(self, document: Mapping[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        goals = document["goals"]
        proposals = document["increment_proposals"]
        proposal_ids = {item["id"] for item in proposals}
        goal_ids = {item["id"] for item in goals}
        for name, collection in (("goals", goals), ("increment_proposals", proposals), ("plans", document["plans"])):
            ids = [item["id"] for item in collection]
            if len(ids) != len(set(ids)):
                issues.append(ValidationIssue("semantic", "duplicate_id", f"$.{name}", "contains a duplicate id"))
        for index, proposal in enumerate(proposals):
            if proposal["goal_id"] not in goal_ids:
                issues.append(ValidationIssue("semantic", "goal_reference", f"$.increment_proposals[{index}].goal_id", "references an unknown goal id"))
            for dependency in proposal["dependencies"]:
                if dependency not in proposal_ids:
                    issues.append(ValidationIssue("semantic", "increment_reference", f"$.increment_proposals[{index}].dependencies", "references an unknown increment id"))
        issues.extend(self._evidence_issues(document))
        issues.extend(self._proposal_cycle_issues(proposals))
        for index, goal in enumerate(goals):
            if goal["workspace_id"] != document["workspace_id"]:
                issues.append(ValidationIssue("semantic", "workspace_reference", f"$.goals[{index}].workspace_id", "must match the planning document workspace id"))
        for index, plan in enumerate(document["plans"]):
            ordered = plan["ordered_increment_ids"]
            ordered_ids = set(ordered)
            positions = {increment_id: position for position, increment_id in enumerate(ordered)}
            if plan["workspace_id"] != document["workspace_id"]:
                issues.append(ValidationIssue("semantic", "workspace_reference", f"$.plans[{index}].workspace_id", "must match the planning document workspace id"))
            if any(item not in proposal_ids for item in ordered):
                issues.append(ValidationIssue("semantic", "increment_reference", f"$.plans[{index}].ordered_increment_ids", "references an unknown increment id"))
            for dependency in plan["dependencies"]:
                if dependency["increment_id"] not in ordered_ids or any(item not in ordered_ids for item in dependency["depends_on"]):
                    issues.append(ValidationIssue("semantic", "plan_dependency_reference", f"$.plans[{index}].dependencies", "must reference ordered plan increments"))
                elif any(positions[dependency_id] >= positions[dependency["increment_id"]] for dependency_id in dependency["depends_on"]):
                    issues.append(ValidationIssue("semantic", "dependency_order", f"$.plans[{index}].dependencies", "must precede the increment that depends on it"))
            issues.extend(self._plan_cycle_issues(plan, index))
        return issues

    def _evidence_issues(self, document: Mapping[str, Any]) -> list[ValidationIssue]:
        if not self._known_knowledge_source_ids:
            return []
        issues: list[ValidationIssue] = []
        for path, reference in self._evidence_references(document):
            if reference["kind"] == "knowledge_source" and reference["source_id"] not in self._known_knowledge_source_ids:
                issues.append(ValidationIssue("semantic", "evidence_source_reference", path, "references an unknown knowledge source id"))
        return issues

    @staticmethod
    def _evidence_references(document: Mapping[str, Any]) -> Iterable[tuple[str, Mapping[str, Any]]]:
        for collection in ("goals", "increment_proposals", "plans"):
            for index, item in enumerate(document[collection]):
                for evidence_index, reference in enumerate(item.get("evidence_references", ())):
                    yield f"$.{collection}[{index}].evidence_references[{evidence_index}].source_id", reference

    @staticmethod
    def _proposal_cycle_issues(proposals: list[Mapping[str, Any]]) -> list[ValidationIssue]:
        graph = {item["id"]: tuple(item["dependencies"]) for item in proposals}
        return PlanningDocumentLoader._cycle_issues(graph, "$.increment_proposals", "proposal_dependency_cycle")

    @staticmethod
    def _plan_cycle_issues(plan: Mapping[str, Any], index: int) -> list[ValidationIssue]:
        graph = {item["increment_id"]: tuple(item["depends_on"]) for item in plan["dependencies"]}
        return PlanningDocumentLoader._cycle_issues(graph, f"$.plans[{index}].dependencies", "plan_dependency_cycle")

    @staticmethod
    def _cycle_issues(graph: Mapping[str, tuple[str, ...]], path: str, code: str) -> list[ValidationIssue]:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            cyclic = any(visit(target) for target in graph.get(node, ()) if target in graph)
            visiting.remove(node)
            visited.add(node)
            return cyclic

        return [ValidationIssue("semantic", code, path, "must not contain a dependency cycle")] if any(visit(node) for node in sorted(graph)) else []

    @staticmethod
    def _construct(document: Mapping[str, Any]) -> EngineeringPlanningDocument:
        def references(values: list[Mapping[str, Any]]) -> tuple[EvidenceReference, ...]:
            return tuple(EvidenceReference(EvidenceKind(item["kind"]), item["source_id"], item["source_version"], item["reference"], item["location"]) for item in values)

        goals = tuple(EngineeringGoal(item["id"], item["description"], item["desired_outcome"], item["workspace_id"], references(item.get("evidence_references", [])), item["schema_version"]) for item in document["goals"])
        proposals = tuple(EngineeringIncrementProposal(item["id"], item["goal_id"], item["scope"], item["expected_outcome"], tuple(item["affected_capabilities"]), tuple(item["dependencies"]), RiskLevel(item["risk_level"]), item["rationale"], references(item.get("evidence_references", [])), item["schema_version"]) for item in document["increment_proposals"])
        plans = tuple(EngineeringPlan(item["id"], item["workspace_id"], tuple(item["ordered_increment_ids"]), tuple(IncrementDependency(dependency["increment_id"], tuple(dependency["depends_on"])) for dependency in item["dependencies"]), tuple(item["assumptions"]), PlanStatus(item["status"]), references(item.get("evidence_references", [])), item["schema_version"]) for item in document["plans"])
        return EngineeringPlanningDocument(DOCUMENT_VERSION, document["workspace_id"], goals, proposals, plans)
