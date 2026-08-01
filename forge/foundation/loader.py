"""Deterministic, local-only loading of Forge Foundation Documents.

The loader is deliberately read-only.  It resolves only the schemas packaged
with Forge and never follows a document's ``$schema`` declaration or a remote
reference.  A failed load returns a structured report rather than raising for
ordinary malformed input, so callers get one stable validation outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from forge.models import (
    Capability,
    EngineeringMode,
    GovernanceProfile,
    KnowledgeSource,
    Repository,
    RepositoryCatalog,
    RepositoryRole,
    Workspace,
)


DOCUMENT_TYPE = "forge.foundation_document"
DOCUMENT_VERSION = "0.3"
COMPONENT_VERSION = "0.2"
_SCHEMA_DIRECTORY = Path(__file__).resolve().parents[2] / "schemas"
_SUPPORTED_DOCUMENT_SCHEMAS = {DOCUMENT_VERSION: "foundation-document.schema.json"}


@dataclass(frozen=True, order=True)
class ValidationIssue:
    """A stable validation finding that never includes source document values."""

    stage: str
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class FoundationDocument:
    """Immutable, validated composition of Forge's declarative foundation."""

    schema_version: str
    workspace: Workspace
    repositories: tuple[Repository, ...]
    repository_catalog: RepositoryCatalog
    knowledge_sources: tuple[KnowledgeSource, ...]
    capabilities: tuple[Capability, ...]


@dataclass(frozen=True)
class ValidationReport:
    """The complete deterministic result of one local document load."""

    document_version: str | None
    issues: tuple[ValidationIssue, ...]
    document: FoundationDocument | None = None
    document_path: str | None = None

    @property
    def valid(self) -> bool:
        return not self.issues and self.document is not None

    def to_text(self) -> str:
        """Render a deterministic, human-readable local validation result."""
        document = self.document_path or "<in-memory document>"
        schema = f"v{self.document_version}" if self.document_version else "unresolved"
        models = "Workspace, RepositoryCatalog, KnowledgeSource, Capability" if self.document else "None"
        lines = [
            "Forge Foundation Validation",
            "",
            f"Status: {'PASS' if self.valid else 'FAIL'}",
            "",
            f"Document: {document}",
            f"Schema: {schema}",
            f"Models: {models}",
            f"Errors: {len(self.issues)}",
            "Warnings: 0",
        ]
        if self.issues:
            lines.extend(["", "Errors:"])
            for issue in self.issues:
                lines.extend(
                    [
                        f"- Field: {issue.path}",
                        f"  Violated rule: {issue.message}",
                        f"  Suggested correction: {self._suggestion(issue)}",
                    ]
                )
        return "\n".join(lines)

    @staticmethod
    def _suggestion(issue: ValidationIssue) -> str:
        suggestions = {
            "read": "Provide a readable local Foundation Document path.",
            "invalid_json": "Correct the JSON syntax and try again.",
            "root_type": "Use a JSON object as the Foundation Document root.",
            "document_type": "Set document_type to forge.foundation_document.",
            "missing_version": "Add a supported schema_version field.",
            "unsupported_version": "Use a schema version supported by this Forge installation.",
            "required": "Add the required property identified above.",
            "additional_property": "Remove the unsupported property.",
            "type": "Use the type required by the local schema.",
            "const": "Use the value required by the local schema.",
            "enum": "Choose one of the values declared by the local schema.",
            "pattern": "Use a value that matches the required format.",
            "min_length": "Lengthen the value to the minimum allowed length.",
            "max_length": "Shorten the value to the maximum allowed length.",
            "min_items": "Add enough items to satisfy the schema.",
            "max_items": "Remove items until the schema limit is met.",
            "unique_items": "Remove or change duplicate items.",
            "duplicate_id": "Give each declared component a unique id.",
            "catalog_reference": "Set repository_catalog_id to the declared repository catalog id.",
            "repository_reference": "Reference a repository id declared in repositories.",
            "duplicate_repository_role": "Assign each repository to only one catalog role.",
            "component_version": "Use component schema version 0.2.",
            "construction": "Correct the reported validation problem and try again.",
        }
        return suggestions.get(issue.code, "Correct the value to satisfy the local Foundation contract.")


class _LocalSchemaValidator:
    """Small, dependency-free evaluator for Forge's packaged JSON Schemas.

    Forge uses a constrained JSON Schema subset in its Foundation contracts.
    Keeping this evaluator here makes schema resolution deterministic and
    avoids a runtime package or network requirement during bootstrap.
    """

    def __init__(self, schemas: Mapping[str, Mapping[str, Any]]) -> None:
        self._schemas = schemas

    def validate(self, instance: Any, schema_name: str) -> tuple[ValidationIssue, ...]:
        return tuple(self._validate(instance, self._schemas[schema_name], "$", schema_name))

    def _resolve(self, reference: str, current_schema: str) -> tuple[Mapping[str, Any], str]:
        file_name, separator, fragment = reference.partition("#")
        target_name = file_name or current_schema
        if target_name not in self._schemas:
            raise ValueError("schema reference is not in Forge's local allow-list")
        target: Any = self._schemas[target_name]
        if separator and fragment:
            for segment in fragment.lstrip("/").split("/"):
                target = target[segment.replace("~1", "/").replace("~0", "~")]
        if not isinstance(target, Mapping):
            raise ValueError("schema reference does not resolve to an object")
        return target, target_name

    def _validate(self, instance: Any, schema: Mapping[str, Any], path: str, schema_name: str) -> list[ValidationIssue]:
        if "$ref" in schema:
            target, target_name = self._resolve(str(schema["$ref"]), schema_name)
            return self._validate(instance, target, path, target_name)

        issues: list[ValidationIssue] = []
        expected_type = schema.get("type")
        if expected_type == "object" and (not isinstance(instance, Mapping) or isinstance(instance, bool)):
            return [self._issue("schema", "type", path, "must be an object")]
        if expected_type == "array" and not isinstance(instance, list):
            return [self._issue("schema", "type", path, "must be an array")]
        if expected_type == "string" and not isinstance(instance, str):
            return [self._issue("schema", "type", path, "must be a string")]

        if "const" in schema and not self._json_equal(instance, schema["const"]):
            return [self._issue("schema", "const", path, "must equal the declared constant")]
        if "enum" in schema and not any(self._json_equal(instance, option) for option in schema["enum"]):
            return [self._issue("schema", "enum", path, "must be one of the declared values")]
        if isinstance(instance, str):
            minimum = schema.get("minLength")
            maximum = schema.get("maxLength")
            if minimum is not None and len(instance) < minimum:
                issues.append(self._issue("schema", "min_length", path, "is shorter than allowed"))
            if maximum is not None and len(instance) > maximum:
                issues.append(self._issue("schema", "max_length", path, "is longer than allowed"))
            if "pattern" in schema:
                import re

                if not re.fullmatch(str(schema["pattern"]), instance):
                    issues.append(self._issue("schema", "pattern", path, "does not match the required pattern"))
        if isinstance(instance, Mapping):
            properties = schema.get("properties", {})
            for key in schema.get("required", []):
                if key not in instance:
                    issues.append(self._issue("schema", "required", path, f"is missing required property '{key}'"))
            if schema.get("additionalProperties") is False:
                for key in sorted(instance, key=str):
                    if key not in properties:
                        issues.append(self._issue("schema", "additional_property", f"{path}.[REDACTED]", "contains a property that is not allowed"))
            additional_schema = schema.get("additionalProperties")
            for key in sorted(instance, key=str):
                property_schema = properties.get(key, additional_schema if isinstance(additional_schema, Mapping) else None)
                if isinstance(property_schema, Mapping):
                    issues.extend(self._validate(instance[key], property_schema, f"{path}.{key}", schema_name))
        if isinstance(instance, list):
            if "minItems" in schema and len(instance) < schema["minItems"]:
                issues.append(self._issue("schema", "min_items", path, "has fewer items than required"))
            if "maxItems" in schema and len(instance) > schema["maxItems"]:
                issues.append(self._issue("schema", "max_items", path, "has more items than allowed"))
            if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in instance}) != len(instance):
                issues.append(self._issue("schema", "unique_items", path, "contains duplicate items"))
            item_schema = schema.get("items")
            if isinstance(item_schema, Mapping):
                for index, item in enumerate(instance):
                    issues.extend(self._validate(item, item_schema, f"{path}[{index}]", schema_name))
        return issues

    @staticmethod
    def _issue(stage: str, code: str, path: str, message: str) -> ValidationIssue:
        return ValidationIssue(stage, code, path, message)

    @staticmethod
    def _json_equal(left: Any, right: Any) -> bool:
        """Compare JSON values without Python's bool-is-int equivalence."""
        if isinstance(left, bool) != isinstance(right, bool):
            return False
        return left == right


class FoundationDocumentLoader:
    """Load one Foundation Document through Forge's fixed validation pipeline."""

    def __init__(self) -> None:
        self._schemas = MappingProxyType(self._load_local_schemas(_SCHEMA_DIRECTORY))
        self._validator = _LocalSchemaValidator(self._schemas)

    @staticmethod
    def _load_local_schemas(directory: Path) -> dict[str, Mapping[str, Any]]:
        names = {
            "foundation-document.schema.json",
            "workspace.schema.json",
            "repository.schema.json",
            "repository-catalog.schema.json",
            "knowledge-source.schema.json",
            "capability.schema.json",
            "engineering-mode.schema.json",
            "governance-profile.schema.json",
            "common.schema.json",
        }
        schemas: dict[str, Mapping[str, Any]] = {}
        for name in sorted(names):
            path = directory / name
            if not path.is_file():
                raise ValueError("required packaged Forge schema is unavailable")
            parsed = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("packaged Forge schema must be a JSON object")
            schemas[name] = parsed
        return schemas

    def load(self, source: str | bytes | Mapping[str, Any]) -> ValidationReport:
        """Parse, validate, and construct a Foundation Document without mutation."""
        parsed, parse_issues = self._parse(source)
        if parse_issues:
            return ValidationReport(None, parse_issues)
        assert parsed is not None
        version, version_issues = self._detect_version(parsed)
        if version_issues:
            return ValidationReport(version, version_issues)
        assert version is not None
        schema_name = _SUPPORTED_DOCUMENT_SCHEMAS[version]
        schema_issues = self._validator.validate(parsed, schema_name)
        if schema_issues:
            return ValidationReport(version, tuple(sorted(schema_issues)))
        semantic_issues = self._semantic_issues(parsed)
        if semantic_issues:
            return ValidationReport(version, tuple(sorted(semantic_issues)))
        try:
            document = self._construct(parsed)
        except (KeyError, TypeError, ValueError):
            return ValidationReport(version, (ValidationIssue("model", "construction", "$", "cannot construct a valid Foundation Document"),))
        return ValidationReport(version, (), document)

    def load_path(self, path: str | Path) -> ValidationReport:
        """Read a local JSON file and pass it through the same pipeline."""
        document_path = str(Path(path))
        try:
            report = self.load(Path(path).read_text(encoding="utf-8"))
        except OSError:
            return ValidationReport(
                None,
                (ValidationIssue("parse", "read", "$", "cannot read Foundation Document"),),
                document_path=document_path,
            )
        return ValidationReport(report.document_version, report.issues, report.document, document_path)

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
            return None, (ValidationIssue("version", "document_type", "$.document_type", "must identify a Forge Foundation Document"),)
        version = document.get("schema_version")
        if not isinstance(version, str):
            return None, (ValidationIssue("version", "missing_version", "$.schema_version", "must declare a schema version"),)
        if version not in _SUPPORTED_DOCUMENT_SCHEMAS:
            return version, (ValidationIssue("version", "unsupported_version", "$.schema_version", "is not supported by this Forge version"),)
        return version, ()

    @staticmethod
    def _semantic_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for collection_name in ("repositories", "knowledge_sources", "capabilities"):
            identifiers = [item["id"] for item in document[collection_name]]
            for identifier in sorted({value for value in identifiers if identifiers.count(value) > 1}):
                issues.append(ValidationIssue("semantic", "duplicate_id", f"$.{collection_name}", "contains a duplicate id"))
        catalog = document["repository_catalog"]
        if document["workspace"]["repository_catalog_id"] != catalog["id"]:
            issues.append(ValidationIssue("semantic", "catalog_reference", "$.workspace.repository_catalog_id", "does not resolve to repository_catalog"))
        repository_ids = {item["id"] for item in document["repositories"]}
        assigned: list[str] = []
        for role, identifiers in catalog["entries"].items():
            for identifier in identifiers:
                assigned.append(identifier)
                if identifier not in repository_ids:
                    issues.append(ValidationIssue("semantic", "repository_reference", f"$.repository_catalog.entries.{role}", "references an unknown repository id"))
        for identifier in sorted({value for value in assigned if assigned.count(value) > 1}):
            issues.append(ValidationIssue("semantic", "duplicate_repository_role", "$.repository_catalog.entries", "assigns a repository id more than once"))
        for component_name, component in FoundationDocumentLoader._components(document):
            if component.get("schema_version") != COMPONENT_VERSION:
                issues.append(ValidationIssue("semantic", "component_version", component_name, "must use the supported component schema version"))
        return issues

    @staticmethod
    def _components(document: Mapping[str, Any]) -> tuple[tuple[str, Mapping[str, Any]], ...]:
        components: list[tuple[str, Mapping[str, Any]]] = [
            ("$.workspace", document["workspace"]),
            ("$.repository_catalog", document["repository_catalog"]),
        ]
        for name in ("repositories", "knowledge_sources", "capabilities"):
            components.extend((f"$.{name}[{index}]", item) for index, item in enumerate(document[name]))
        return tuple(components)

    @staticmethod
    def _construct(document: Mapping[str, Any]) -> FoundationDocument:
        def metadata(item: Mapping[str, Any]) -> dict[str, str]:
            return dict(item.get("metadata", {}))

        repositories = tuple(Repository(metadata=metadata(item), **{key: item[key] for key in ("id", "name", "provider", "repository", "local_path", "schema_version")}) for item in document["repositories"])
        catalog_data = document["repository_catalog"]
        catalog = RepositoryCatalog(
            id=catalog_data["id"],
            entries={RepositoryRole(role): tuple(ids) for role, ids in catalog_data["entries"].items()},
            schema_version=catalog_data["schema_version"],
        )
        workspace_data = document["workspace"]
        workspace = Workspace(
            id=workspace_data["id"],
            name=workspace_data["name"],
            repository_catalog_id=workspace_data["repository_catalog_id"],
            engineering_mode=EngineeringMode(workspace_data["engineering_mode"]),
            governance_profile=GovernanceProfile(workspace_data["governance_profile"]),
            metadata=metadata(workspace_data),
            schema_version=workspace_data["schema_version"],
        )
        sources = tuple(KnowledgeSource(metadata=metadata(item), **{key: item[key] for key in ("id", "name", "source_type", "locator", "read_only", "schema_version")}) for item in document["knowledge_sources"])
        capabilities = tuple(Capability(metadata=metadata(item), **{key: item[key] for key in ("id", "name", "description", "status", "schema_version")}) for item in document["capabilities"])
        return FoundationDocument(DOCUMENT_VERSION, workspace, repositories, catalog, sources, capabilities)
