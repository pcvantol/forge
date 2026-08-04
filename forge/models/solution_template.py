"""Versioned, reusable, advisory Solution Template contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .mission_recommendation import EngineeringEffort, RequiredDiscipline


SOLUTION_TEMPLATE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class TemplateMissionCandidate:
    key: str
    title: str
    objective: str
    value: str
    disciplines: tuple[RequiredDiscipline, ...]
    dependencies: tuple[str, ...] = ()
    effort: EngineeringEffort = EngineeringEffort.MEDIUM

    def __post_init__(self) -> None:
        if not all((self.key, self.title, self.objective, self.value)) or not self.disciplines:
            raise ValueError("template mission candidate requires complete business context and disciplines")
        for name in ("disciplines", "dependencies"):
            values = getattr(self, name)
            if len(values) != len(set(values)) or any(not value for value in values):
                raise ValueError(f"template candidate {name} must be unique and non-empty")
            object.__setattr__(self, name, tuple(sorted(values, key=lambda value: value.value if isinstance(value, RequiredDiscipline) else value)))


@dataclass(frozen=True)
class SolutionTemplate:
    """An immutable catalogue asset. It is never an approval or execution request."""

    identifier: str
    version: str
    name: str
    purpose: str
    typical_users: tuple[str, ...]
    typical_stakeholders: tuple[str, ...]
    business_objectives: tuple[str, ...]
    typical_capabilities: tuple[str, ...]
    recommended_mission_candidates: tuple[TemplateMissionCandidate, ...]
    architecture_patterns: tuple[str, ...]
    engineering_disciplines: tuple[RequiredDiscipline, ...]
    risks: tuple[str, ...]
    compliance_considerations: tuple[str, ...]
    implementation_phases: tuple[str, ...]
    schema_version: str = SOLUTION_TEMPLATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SOLUTION_TEMPLATE_SCHEMA_VERSION or not all((self.identifier, self.version, self.name, self.purpose)):
            raise ValueError("solution template requires supported versioned identity and purpose")
        for name in ("typical_users", "typical_stakeholders", "business_objectives", "typical_capabilities", "recommended_mission_candidates", "architecture_patterns", "engineering_disciplines", "risks", "compliance_considerations", "implementation_phases"):
            values = getattr(self, name)
            if not values or len(values) != len(set(values)):
                raise ValueError(f"solution template {name} must be populated and unique")
            object.__setattr__(self, name, tuple(sorted(values, key=lambda value: value.key if isinstance(value, TemplateMissionCandidate) else value.value if isinstance(value, RequiredDiscipline) else value)))

    @property
    def reference(self) -> str:
        return f"solution-template:{self.identifier}@{self.version}"
