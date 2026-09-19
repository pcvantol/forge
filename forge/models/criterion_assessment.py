"""Approved evidence requirements; these contracts do not assert realization.

Forge decides what an observed control can prove. A requirement names an exact
control and command, but only independently observed evidence can satisfy it.
Neither planner intent nor provider report prose is execution evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping


CRITERION_ASSESSMENT_CONTRACT_SCHEMA_VERSION = "1.0"
CRITERION_VALIDITY_POLICIES = frozenset({"current_revision", "historical_delivery"})


def _digest(document: object) -> str:
    return "sha256:" + sha256(json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{label} must be non-empty text without NUL")


@dataclass(frozen=True, order=True)
class CriterionEvidenceRequirement:
    """One exact approved control contribution required by a criterion."""

    requirement_id: str
    control_identity: str = ""
    command: str = ""
    kind: str = "host_control"
    artifact_path: str = ""
    json_pointer: str = ""
    expected_json: str = ""
    validation_id: str = ""
    validation_profile_version: str = ""
    profile_reference: str = ""
    control_category: str = ""
    control_definition_digest: str = ""
    minimum_test_count: int = 0

    def __post_init__(self) -> None:
        _text(self.requirement_id, "criterion evidence requirement_id")
        if any(not isinstance(getattr(self, name), str) for name in (
                "kind", "control_identity", "command", "artifact_path", "json_pointer", "expected_json",
                "validation_id", "validation_profile_version", "profile_reference",
                "control_category", "control_definition_digest")):
            raise ValueError("criterion evidence requirement fields must be text")
        if self.kind == "host_control":
            for name in ("control_identity", "command"):
                _text(getattr(self, name), f"criterion evidence {name}")
            if any((self.artifact_path, self.json_pointer, self.expected_json)):
                raise ValueError("host control requirement cannot contain repository assertions")
            if self.control_definition_digest and (re.fullmatch(r"sha256:[0-9a-f]{64}", self.control_definition_digest) is None
                                                   or not self.validation_id or not self.validation_profile_version
                                                   or not self.profile_reference or not self.control_category):
                raise ValueError("host control definition requires exact validation identity and profile version")
            if self.control_definition_digest:
                try:
                    command_identity = json.loads(self.command)
                except (ValueError, TypeError) as error:
                    raise ValueError("approved host control command identity must be a JSON argv array") from error
                if (not isinstance(command_identity, list) or not command_identity
                        or any(not isinstance(part, str) or not part for part in command_identity)):
                    raise ValueError("approved host control command identity must be a nonempty JSON argv array")
                object.__setattr__(self, "command", json.dumps(command_identity, separators=(",", ":"),
                                                                ensure_ascii=False))
            if not isinstance(self.minimum_test_count, int) or isinstance(self.minimum_test_count, bool) or self.minimum_test_count < 0:
                raise ValueError("host control minimum test count is invalid")
        elif self.kind == "repository_json":
            if (self.control_identity or self.command or self.validation_id or self.validation_profile_version
                    or self.profile_reference or self.control_category
                    or self.control_definition_digest or self.minimum_test_count):
                raise ValueError("repository assertion cannot contain host control claims")
            if (not isinstance(self.artifact_path, str)
                    or re.fullmatch(r"[A-Za-z0-9_.\-/]+", self.artifact_path) is None
                    or any(part in {"", ".", ".."} for part in self.artifact_path.split("/"))):
                raise ValueError("repository assertion requires a safe relative artifact path")
            if (not isinstance(self.json_pointer, str)
                    or self.json_pointer != "" and not self.json_pointer.startswith("/")
                    or re.search(r"~(?![01])", self.json_pointer)):
                raise ValueError("repository assertion requires a valid JSON pointer")
            if not isinstance(self.expected_json, str) or not self.expected_json:
                raise ValueError("repository assertion requires an explicit JSON expectation")
            try:
                expected = json.loads(self.expected_json, parse_constant=_invalid_json_constant,
                                      object_pairs_hook=_unique_json_object)
                canonical = json.dumps(expected, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False, allow_nan=False)
            except (ValueError, TypeError, RecursionError) as error:
                raise ValueError("repository assertion expected JSON is invalid") from error
            object.__setattr__(self, "expected_json", canonical)
        else:
            raise ValueError("criterion evidence requirement kind is unsupported")

    def to_dict(self) -> dict[str, str]:
        value = {"requirement_id": self.requirement_id, "kind": self.kind}
        if self.kind == "host_control":
            control = {**value, "control_identity": self.control_identity, "command": self.command}
            if self.control_definition_digest:
                control.update({"validation_id": self.validation_id,
                                "validation_profile_version": self.validation_profile_version,
                                "profile_reference": self.profile_reference,
                                "control_category": self.control_category,
                                "control_definition_digest": self.control_definition_digest,
                                "minimum_test_count": self.minimum_test_count})
            return control
        return {**value, "artifact_path": self.artifact_path,
                "json_pointer": self.json_pointer, "expected_json": self.expected_json}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "CriterionEvidenceRequirement":
        if not isinstance(document, Mapping):
            raise ValueError("criterion evidence requirement schema is invalid")
        keys = ({"requirement_id", "kind", "control_identity", "command"}
                if document.get("kind") == "host_control" else
                {"requirement_id", "kind", "artifact_path", "json_pointer", "expected_json"})
        extended = keys | {"validation_id", "validation_profile_version", "profile_reference",
                           "control_category", "control_definition_digest", "minimum_test_count"}
        if set(document) != keys and not (document.get("kind") == "host_control" and set(document) == extended):
            raise ValueError("criterion evidence requirement schema is invalid")
        return cls(**document)


def _invalid_json_constant(value: str) -> None:
    raise ValueError("non-finite JSON values are unsupported")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object keys are unsupported")
        result[key] = value
    return result


@dataclass(frozen=True)
class ApprovedRepositoryEvidenceSource:
    """Approved repository identity for fixed GitHub immutable-blob reads.

    This is a source binding, never an arbitrary URL or a credential reference.
    The runtime independently matches repository_id to its configured Host.
    """

    repository_id: str
    github_repository: str

    def __post_init__(self) -> None:
        _text(self.repository_id, "repository evidence source identity")
        if (not isinstance(self.github_repository, str)
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}",
                                self.github_repository) is None
                or self.github_repository.split("/")[1] in {".", ".."}):
            raise ValueError("repository evidence source requires an exact GitHub owner/repository")

    def to_dict(self) -> dict[str, str]:
        return {"repository_id": self.repository_id, "github_repository": self.github_repository}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "ApprovedRepositoryEvidenceSource":
        if not isinstance(document, Mapping) or set(document) != {"repository_id", "github_repository"}:
            raise ValueError("repository evidence source schema is invalid")
        return cls(**document)


@dataclass(frozen=True)
class CriterionAssessmentContract:
    """A versioned, conjunctive evidence contract for one exact criterion.

Every requirement must be satisfied. Contributions may come from multiple
Actions. Validity is assessed separately against Repository Truth: historical
delivery and currently valid behavior deliberately have distinct policies.
"""

    criterion: str
    requirements: tuple[CriterionEvidenceRequirement, ...]
    validity_policy: str = "current_revision"
    schema_version: str = CRITERION_ASSESSMENT_CONTRACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.criterion, "criterion")
        if self.schema_version != CRITERION_ASSESSMENT_CONTRACT_SCHEMA_VERSION:
            raise ValueError("criterion assessment contract schema version is unsupported")
        if not isinstance(self.validity_policy, str) or self.validity_policy not in CRITERION_VALIDITY_POLICIES:
            raise ValueError("criterion assessment validity policy is unsupported")
        if (not isinstance(self.requirements, tuple) or not self.requirements
                or any(not isinstance(item, CriterionEvidenceRequirement) for item in self.requirements)):
            raise ValueError("criterion assessment requires typed evidence requirements")
        identifiers = tuple(item.requirement_id for item in self.requirements)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("criterion evidence requirement identities must be unique")
        controls = tuple((item.kind, item.control_identity, item.command, item.validation_id,
                          item.control_definition_digest, item.artifact_path,
                          item.json_pointer) for item in self.requirements)
        if len(controls) != len(set(controls)):
            raise ValueError("criterion evidence requirements must name distinct controls")
        object.__setattr__(self, "requirements", tuple(sorted(self.requirements)))

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "criterion": self.criterion,
                "requirements": [item.to_dict() for item in self.requirements],
                "validity_policy": self.validity_policy}

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> "CriterionAssessmentContract":
        if (not isinstance(document, Mapping)
                or set(document) != {"schema_version", "criterion", "requirements", "validity_policy"}
                or not isinstance(document["requirements"], list)):
            raise ValueError("criterion assessment contract schema is invalid")
        return cls(document["criterion"], tuple(CriterionEvidenceRequirement.from_dict(item)
                                               for item in document["requirements"]),
                   document["validity_policy"], document["schema_version"])


def validate_criterion_contracts(
    contracts: tuple[CriterionAssessmentContract, ...],
    maximum_actions: int | None,
    maximum_consecutive_no_progress_actions: int | None,
    repository_evidence_source: ApprovedRepositoryEvidenceSource | None = None,
) -> tuple[CriterionAssessmentContract, ...]:
    """Normalize approved requirements without adding any runtime permission."""
    if not isinstance(contracts, tuple) or any(not isinstance(item, CriterionAssessmentContract) for item in contracts):
        raise ValueError("criterion assessment contracts must be a typed tuple")
    criteria = tuple(item.criterion for item in contracts)
    if len(criteria) != len(set(criteria)):
        raise ValueError("criterion assessment contracts must have unique exact criteria")
    if repository_evidence_source is not None and not isinstance(repository_evidence_source, ApprovedRepositoryEvidenceSource):
        raise ValueError("repository evidence source must be typed")
    if (any(item.kind == "repository_json" for contract in contracts for item in contract.requirements)
            and repository_evidence_source is None):
        raise ValueError("repository assertions require an approved repository evidence source")
    ceilings = (maximum_actions, maximum_consecutive_no_progress_actions)
    if contracts or any(value is not None for value in ceilings):
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in ceilings):
            raise ValueError("criterion continuation requires explicit positive Action ceilings")
        if maximum_consecutive_no_progress_actions > maximum_actions:
            raise ValueError("no-progress Action ceiling cannot exceed maximum Actions")
    # The same requirement ID cannot silently mean a different control for
    # another criterion. Reuse of the exact requirement remains explicit.
    requirements: dict[str, CriterionEvidenceRequirement] = {}
    for contract in contracts:
        for requirement in contract.requirements:
            if requirements.get(requirement.requirement_id, requirement) != requirement:
                raise ValueError("criterion evidence requirement identity is conflicting")
            requirements[requirement.requirement_id] = requirement
    return tuple(sorted(contracts, key=lambda item: item.criterion))
