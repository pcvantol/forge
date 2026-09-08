"""Small, non-mutating checks used against an installed Forge wheel."""
from __future__ import annotations

from forge.foundation.loader import FoundationDocumentLoader
from forge.planning.loader import PlanningDocumentLoader
from forge.scheduler.ep_http_adapter import EngineeringPlatformHttpExecutionHost


def run() -> None:
    """Prove installed resources and the strict EP v1.2 consumer are present."""
    FoundationDocumentLoader()
    PlanningDocumentLoader()
    if EngineeringPlatformHttpExecutionHost.SUPPORTED_PRODUCER_READBACK_CONTRACTS != ("1.2",):
        raise RuntimeError("installed Forge wheel does not contain the strict EP v1.2 consumer")


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
