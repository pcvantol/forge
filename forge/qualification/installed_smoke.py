"""Small, non-mutating checks used against an installed Forge wheel."""
from __future__ import annotations

from importlib.resources import files

from forge.foundation.loader import FoundationDocumentLoader
from forge.execution_host_configuration import (
    EngineeringPlatformExecutionHostFactory,
    PEER_CONFIGURATION_SCHEMA_VERSION,
)
from forge.planning.loader import PlanningDocumentLoader
from forge.scheduler.ep_http_adapter import EngineeringPlatformHttpExecutionHost


def run() -> None:
    """Prove installed resources and the strict EP v1.2 consumer are present."""
    FoundationDocumentLoader()
    PlanningDocumentLoader()
    if EngineeringPlatformHttpExecutionHost.SUPPORTED_PRODUCER_READBACK_CONTRACTS != ("1.2",):
        raise RuntimeError("installed Forge wheel does not contain the strict EP v1.2 consumer")
    if PEER_CONFIGURATION_SCHEMA_VERSION != "1.0":
        raise RuntimeError("installed Forge wheel does not contain the durable EP peer configuration factory")
    EngineeringPlatformExecutionHostFactory()
    if not files("forge.schemas").joinpath("engineering-platform-peer-configuration-1.0.schema.json").is_file():
        raise RuntimeError("installed Forge wheel omits the EP peer configuration schema")


def assert_runtime_persistence(workspace_root: str, runtime_root: str, forge_version: str) -> None:
    """Open and reopen an explicitly external temporary runtime root."""
    from forge.runtime import RuntimeBootstrap

    first = RuntimeBootstrap(workspace_root, configured_runtime_root=runtime_root, forge_version=forge_version).open()
    identity = first.runtime_identity.runtime_id
    first.close()
    reopened = RuntimeBootstrap(workspace_root, configured_runtime_root=runtime_root, forge_version=forge_version).open()
    try:
        if reopened.runtime_identity.runtime_id != identity:
            raise RuntimeError("installed Forge runtime identity did not persist across reopen")
    finally:
        reopened.close()
