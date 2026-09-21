"""Canonical, versioned inventory of installed Forge components.

The registry is product inventory, not observed health state.  Consumers such
as health, console projection, service control, and qualification select their
own projections from these immutable declarations.
"""
from __future__ import annotations

from dataclasses import dataclass


COMPONENT_REGISTRY_VERSION = "1.0"


@dataclass(frozen=True)
class ComponentHealthCheck:
    check_id: str
    purpose: str
    applicability: str
    freshness_seconds: int
    capabilities: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class ForgeComponent:
    component_id: str
    kind: str
    health_checks: tuple[ComponentHealthCheck, ...] = ()


_COMPONENT_REGISTRY = (
    ForgeComponent("forge_server", "SERVICE", (
        ComponentHealthCheck("process", "LIVENESS", "REQUIRED", 30),
    )),
    ForgeComponent("operations_console", "SERVICE"),
    ForgeComponent("dashboard_relay", "SERVICE"),
    ForgeComponent("platform_database", "STORAGE", (
        ComponentHealthCheck(
            "storage", "READINESS", "REQUIRED", 300, ("dispatch", "local_work"),
        ),
    )),
    ForgeComponent("mission_dispatcher", "LOGICAL"),
    ForgeComponent("planning_provider", "PROVIDER"),
    ForgeComponent("codex_runtime", "DEPENDENCY"),
    ForgeComponent("python_runtime", "DEPENDENCY"),
    ForgeComponent("ep_peer", "PEER", (
        ComponentHealthCheck("execution_peer", "READINESS", "REQUIRED", 30, ("dispatch",)),
    )),
    ForgeComponent("http_ingress", "TRANSPORT"),
    ForgeComponent("cli_ingress", "TRANSPORT"),
    ForgeComponent("operational_logging", "LOGICAL"),
    ForgeComponent("tailscale_access", "DEPENDENCY"),
)


def component_registry() -> tuple[ForgeComponent, ...]:
    """Return the single immutable installed-component inventory."""
    return _COMPONENT_REGISTRY
