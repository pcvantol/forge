"""Stable 0.2 data contracts for Forge's local Foundation Model.

These models describe data only.  They deliberately have no repository,
network, execution, or mutation behaviour.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = "0.2"


class RepositoryRole(str, Enum):
    """A repository's role in a workspace catalog."""

    CANONICAL = "canonical"
    SUPPORTING = "supporting"
    DOCUMENTATION = "documentation"
    CAPABILITY = "capability"


class EngineeringMode(str, Enum):
    """Available engineering maturity modes; bootstrap activation is separate."""

    PROTOTYPE = "prototype"
    MANAGED = "managed"
    PRODUCTION = "production"
    ENTERPRISE = "enterprise"


class GovernanceProfile(str, Enum):
    """Available human-governance profiles; bootstrap activation is separate."""

    SOLO = "solo"
    TWO_PERSON = "two_person"
    TEAM = "team"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class Repository:
    """Repository identity and descriptive metadata, independent of catalog role."""

    id: str
    name: str
    provider: str
    repository: str
    local_path: str
    metadata: dict[str, str] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.provider or not self.repository or not self.local_path:
            raise ValueError("repository identity, name, provider, reference, and local path are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RepositoryCatalog:
    """A role-bearing catalog with exactly one canonical repository."""

    id: str
    entries: dict[RepositoryRole, tuple[str, ...]]
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("catalog id is required")
        canonical = self.entries.get(RepositoryRole.CANONICAL, ())
        if len(canonical) != 1:
            raise ValueError("a repository catalog must contain exactly one canonical repository")
        identifiers = [repository_id for members in self.entries.values() for repository_id in members]
        if any(not repository_id for repository_id in identifiers):
            raise ValueError("catalog repository ids must not be empty")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("a repository may have only one role in a catalog")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "entries": {role.value: list(ids) for role, ids in self.entries.items()},
        }


@dataclass(frozen=True)
class KnowledgeSource:
    """A read-only external evidence provider."""

    id: str
    name: str
    source_type: str
    locator: str
    read_only: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.source_type or not self.locator:
            raise ValueError("knowledge source id, name, type, and locator are required")
        if not self.read_only:
            raise ValueError("Forge knowledge sources must be read-only")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Capability:
    """A declared reusable capability contract, without an implementation."""

    id: str
    name: str
    description: str
    status: str = "declared"
    metadata: dict[str, str] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.description:
            raise ValueError("capability id, name, and description are required")
        if self.status != "declared":
            raise ValueError("bootstrap capabilities may only be declared")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Workspace:
    """A product workspace that refers to separate foundation contracts."""

    id: str
    name: str
    repository_catalog_id: str
    engineering_mode: EngineeringMode
    governance_profile: GovernanceProfile
    metadata: dict[str, str] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.repository_catalog_id:
            raise ValueError("workspace id, name, and repository catalog id are required")

    def to_dict(self) -> dict[str, Any]:
        document = asdict(self)
        document["engineering_mode"] = self.engineering_mode.value
        document["governance_profile"] = self.governance_profile.value
        return document
