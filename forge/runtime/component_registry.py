"""Canonical, versioned Forge component registry.

The registry is product-owned source truth.  Health consumes its typed check
definitions; it does not maintain a parallel inventory or discover components
from whichever processes happen to be running.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import re

from .health import CheckApplicability, CheckPurpose, HealthCheckDefinition


COMPONENT_REGISTRY_SCHEMA_REVISION = "1.0"
_COMPONENT_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_COMPONENT_KINDS = frozenset({"SERVICE", "LOGICAL", "DEPENDENCY", "TRANSPORT", "STORAGE"})


@dataclass(frozen=True)
class ComponentDefinition:
    component_id: str
    owner: str
    kind: str
    health_checks: tuple[HealthCheckDefinition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or _COMPONENT_ID.fullmatch(self.component_id) is None:
            raise ValueError("component id is invalid")
        if not isinstance(self.owner, str) or not self.owner:
            raise ValueError("component owner is required")
        if self.kind not in _COMPONENT_KINDS:
            raise ValueError("component kind is unsupported")
        if not isinstance(self.health_checks, tuple):
            raise ValueError("component health checks must be an immutable tuple")
        if any(
            not isinstance(item, HealthCheckDefinition) or item.component_id != self.component_id
            for item in self.health_checks
        ):
            raise ValueError("component health checks must be typed and component-bound")


@dataclass(frozen=True)
class ComponentRegistry:
    schema_revision: str
    components: tuple[ComponentDefinition, ...]

    def __post_init__(self) -> None:
        if self.schema_revision != COMPONENT_REGISTRY_SCHEMA_REVISION:
            raise ValueError("component registry schema revision is unsupported")
        if not isinstance(self.components, tuple) or not self.components:
            raise ValueError("component registry must contain typed components")
        if not all(isinstance(item, ComponentDefinition) for item in self.components):
            raise ValueError("component registry must contain typed components")
        component_ids = tuple(item.component_id for item in self.components)
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("component registry ids must be unique")
        check_ids = tuple(item.check_id for item in self.health_definitions)
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("component registry health check ids must be unique")

    @property
    def health_definitions(self) -> tuple[HealthCheckDefinition, ...]:
        return tuple(
            check
            for component in self.components
            for check in component.health_checks
        )

    @property
    def component_ids(self) -> tuple[str, ...]:
        return tuple(item.component_id for item in self.components)


_FRESH = timedelta(seconds=30)


CANONICAL_COMPONENT_REGISTRY = ComponentRegistry(
    COMPONENT_REGISTRY_SCHEMA_REVISION,
    (
        ComponentDefinition(
            "forge_server",
            "forge",
            "SERVICE",
            (
                HealthCheckDefinition(
                    "forge_server", "server_process", CheckPurpose.LIVENESS,
                    CheckApplicability.REQUIRED, _FRESH,
                ),
            ),
        ),
        ComponentDefinition("operations_console", "forge", "SERVICE"),
        ComponentDefinition(
            "dashboard_relay",
            "forge",
            "SERVICE",
            (
                HealthCheckDefinition(
                    "dashboard_relay", "relay_access", CheckPurpose.READINESS,
                    CheckApplicability.OPTIONAL, _FRESH, ("remote_access",), False,
                ),
            ),
        ),
        ComponentDefinition(
            "platform_database",
            "forge",
            "STORAGE",
            (
                HealthCheckDefinition(
                    "platform_database", "runtime_storage", CheckPurpose.READINESS,
                    CheckApplicability.REQUIRED, _FRESH, ("dispatch", "local_work"),
                ),
            ),
        ),
        ComponentDefinition(
            "mission_dispatcher",
            "forge",
            "LOGICAL",
            (
                HealthCheckDefinition(
                    "mission_dispatcher", "dispatcher_state", CheckPurpose.READINESS,
                    CheckApplicability.REQUIRED, _FRESH, ("dispatch",),
                ),
            ),
        ),
        ComponentDefinition("planning_provider", "forge", "DEPENDENCY"),
        ComponentDefinition("codex_runtime", "forge", "DEPENDENCY"),
        ComponentDefinition("python_runtime", "forge", "DEPENDENCY"),
        ComponentDefinition(
            "ep_peer",
            "engineering-platform",
            "DEPENDENCY",
            (
                HealthCheckDefinition(
                    "ep_peer", "execution_peer_binding", CheckPurpose.READINESS,
                    CheckApplicability.REQUIRED, _FRESH, ("dispatch",),
                ),
            ),
        ),
        ComponentDefinition("http_ingress", "forge", "TRANSPORT"),
        ComponentDefinition("cli_ingress", "forge", "TRANSPORT"),
        ComponentDefinition("operational_logging", "forge", "LOGICAL"),
        ComponentDefinition("tailscale_access", "host", "DEPENDENCY"),
    ),
)
