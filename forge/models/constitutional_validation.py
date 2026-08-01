"""Immutable, repository-driven contracts for Constitutional Validation 1.1.

These contracts describe architectural assessment only. They neither obtain
repository knowledge nor enforce, authorize, or modify an outcome.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


CONSTITUTIONAL_VALIDATION_SCHEMA_VERSION = "1.1"


class ConstitutionalAssessmentStatus(str, Enum):
    """The deterministic result of an architectural constitutional assessment."""

    PASS = "PASS"
    WARNING = "WARNING"
    VIOLATION = "VIOLATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ConstitutionalFindingSeverity(str, Enum):
    """The assessment significance of a finding against one article."""

    WARNING = "WARNING"
    VIOLATION = "VIOLATION"


@dataclass(frozen=True, order=True)
class ConstitutionalRule:
    """A declarative representation of one canonical constitutional article."""

    id: str
    title: str
    description: str
    rationale: str
    validation_intent: str

    def __post_init__(self) -> None:
        if not all((self.id, self.title, self.description, self.rationale, self.validation_intent)):
            raise ValueError("constitutional rule id, title, description, rationale, and validation intent are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class ConstitutionalFinding:
    """A stable explanation of a warning or violation against one article."""

    article_id: str
    severity: ConstitutionalFindingSeverity
    explanation: str
    affected_concept: str
    recommendation: str

    def __post_init__(self) -> None:
        if not all((self.article_id, self.explanation, self.affected_concept, self.recommendation)):
            raise ValueError("finding article, explanation, affected concept, and recommendation are required")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["severity"] = self.severity.value
        return document


@dataclass(frozen=True)
class ConstitutionalAssessment:
    """A deterministic, declarative assessment of applicable constitutional rules."""

    subject_id: str
    applicable_rules: tuple[ConstitutionalRule, ...]
    status: ConstitutionalAssessmentStatus
    findings: tuple[ConstitutionalFinding, ...] = field(default_factory=tuple)
    schema_version: str = CONSTITUTIONAL_VALIDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.subject_id:
            raise ValueError("constitutional assessment subject id is required")
        rule_ids = [rule.id for rule in self.applicable_rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("applicable constitutional rule ids must be unique")
        if any(finding.article_id not in rule_ids for finding in self.findings):
            raise ValueError("constitutional findings must reference applicable rules")
        if self.findings != tuple(sorted(self.findings)):
            raise ValueError("constitutional findings must be in stable order")
        if not self.applicable_rules:
            expected_status = ConstitutionalAssessmentStatus.NOT_APPLICABLE
        elif any(finding.severity is ConstitutionalFindingSeverity.VIOLATION for finding in self.findings):
            expected_status = ConstitutionalAssessmentStatus.VIOLATION
        elif self.findings:
            expected_status = ConstitutionalAssessmentStatus.WARNING
        else:
            expected_status = ConstitutionalAssessmentStatus.PASS
        if self.status is not expected_status:
            raise ValueError("constitutional assessment status must match its applicable rules and findings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "applicable_rules": [rule.to_dict() for rule in self.applicable_rules],
            "status": self.status.value,
            "findings": [finding.to_dict() for finding in self.findings],
            "schema_version": self.schema_version,
        }
