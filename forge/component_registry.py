"""Canonical, versioned inventory of installed Forge components.

The registry is product-owned data.  Health readers project this inventory; they
do not discover components from processes, the filesystem, or peer products.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


COMPONENT_REGISTRY_VERSION = "1.0"


@dataclass(frozen=True)
class ComponentHealthCheck:
    check_id: str
    purpose: str
    applicability: str
    freshness_timeout_seconds: int
    capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "purpose": self.purpose,
            "applicability": self.applicability,
            "freshness_timeout_seconds": self.freshness_timeout_seconds,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class ComponentDefinition:
    component_id: str
    name: str
    kind: str
    authority: str
    health_checks: tuple[ComponentHealthCheck, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "kind": self.kind,
            "authority": self.authority,
            "health_checks": [item.to_dict() for item in self.health_checks],
        }


_SNAPSHOT_CAPABILITY = ("installed_health_snapshot",)
_COMPONENTS = (
    ComponentDefinition(
        "forge_server", "Forge Server", "SERVICE", "forge_runtime",
        (ComponentHealthCheck("installed_reader", "LIVENESS", "REQUIRED", 30),),
    ),
    ComponentDefinition("operations_console", "Operations Console", "SERVICE", "forge_console"),
    ComponentDefinition("dashboard_relay", "Dashboard Relay", "SERVICE", "forge_access"),
    ComponentDefinition(
        "platform_database", "Platform Database", "STORAGE", "forge_runtime",
        (ComponentHealthCheck(
            "database_integrity", "READINESS", "REQUIRED", 30, _SNAPSHOT_CAPABILITY,
        ),),
    ),
    ComponentDefinition(
        "mission_dispatcher", "Mission Dispatcher", "LOGICAL", "forge_runtime",
        (ComponentHealthCheck(
            "dispatcher_state", "READINESS", "REQUIRED", 30, _SNAPSHOT_CAPABILITY,
        ),),
    ),
    ComponentDefinition("planning_provider", "Planning Provider", "LOGICAL", "forge_runtime"),
    ComponentDefinition("codex_runtime", "Codex Runtime", "DEPENDENCY", "external_runtime"),
    ComponentDefinition("python_runtime", "Python Runtime", "DEPENDENCY", "forge_installation"),
    ComponentDefinition("ep_peer", "Engineering Platform Peer", "EXTERNAL", "engineering_platform"),
    ComponentDefinition("http_ingress", "HTTP Ingress", "TRANSPORT", "forge_server"),
    ComponentDefinition("cli_ingress", "CLI Ingress", "TRANSPORT", "forge_installation"),
    ComponentDefinition("operational_logging", "Operational Logging", "SUBSYSTEM", "forge_runtime"),
    ComponentDefinition("tailscale_access", "Tailscale Access", "EXTERNAL", "host_network"),
)


def canonical_component_registry() -> tuple[ComponentDefinition, ...]:
    """Return the one immutable registry in stable component-id order."""
    return tuple(sorted(_COMPONENTS, key=lambda item: item.component_id))


def component_registry_projection() -> dict[str, object]:
    """Return a digest-bound wire projection of the canonical registry."""
    components = [item.to_dict() for item in canonical_component_registry()]
    encoded = json.dumps(
        {"schema_version": COMPONENT_REGISTRY_VERSION, "components": components},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": COMPONENT_REGISTRY_VERSION,
        "digest": "sha256:" + sha256(encoded).hexdigest(),
        "components": components,
    }
