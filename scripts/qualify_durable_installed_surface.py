#!/usr/bin/env python3
"""Non-generating installed-wheel check for durable Action-Derivation APIs.

Run this with the wheel's Python from a directory outside the source checkout.
It creates an isolated Runtime root, uses only the public configuration and
installed-runtime APIs, and never invokes ``codex exec`` or an Execution Host.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace


def qualify(root: Path) -> dict[str, object]:
    from forge._version import canonical_version
    from forge.operator_identity import InstallationOperatorService, MacOSGeneratedUIDIdentityAdapter
    from forge.planner import CODEX_CLI_CHATGPT_SESSION_ADAPTER_VERSION
    from forge.provider_security import (
        CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
        CODEX_CLI_CHATGPT_SESSION_TYPE,
        PlanningProviderSecurityService,
        ProviderAuthenticationMode,
    )
    from forge.governance_authority import CanonicalGovernanceRepository
    from forge.runtime import RuntimeBootstrap
    import forge.runtime.dynamic_mission as dynamic_mission
    from forge.secure_store import MacOSKeychainSecureStoreAdapter

    database = RuntimeBootstrap(data_root=root, forge_version=canonical_version()).open()
    try:
        adapter = MacOSGeneratedUIDIdentityAdapter()
        operators = InstallationOperatorService(database, adapter.resolve)
        try:
            context = operators.context()
        except PermissionError:
            context = operators.first_bind()
        repository = CanonicalGovernanceRepository.for_runtime(database, adapter.resolve, data_root=str(root))
        security = PlanningProviderSecurityService(database, MacOSKeychainSecureStoreAdapter(), repository.operators)
        configured = security.configure(
            configuration_id="installed-durable-surface-v1",
            provider_id="codex-chatgpt-session",
            reference=None,
            operator_context=context,
            expected_version=0,
            enabled=True,
            authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
            provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
            external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
            executable_path=str(Path(sys.executable).resolve()),
            adapter_version=CODEX_CLI_CHATGPT_SESSION_ADAPTER_VERSION,
            model=None,
            profile=None,
            timeout_seconds=300,
            input_token_bound=16_000,
            context_token_bound=32_768,
            output_token_bound=4_096,
        )
        if configured.get("state") != "UNVERIFIED" or configured.get("ready") is not False:
            raise RuntimeError("isolated external-session configuration has an unexpected public readback")
    finally:
        database.close()

    # ``open`` normally resolves the installed EP credential/peer.  That is
    # intentionally an external boundary, not a requirement for this
    # non-generating planner qualification.  Replace only that factory in the
    # isolated wheel process; provider configuration, native identity, Runtime
    # bootstrap and the public runtime ``open`` route remain real.
    class _QualificationHost:
        config = SimpleNamespace(host_id="qualification-host", project_id="qualification-project",
                                 repository_id="qualification-repository",
                                 repository_identity="qualification-repository")

    class _QualificationHostFactory:
        def from_database(self, _database):
            return _QualificationHost()

    original_factory = dynamic_mission.EngineeringPlatformExecutionHostFactory
    dynamic_mission.EngineeringPlatformExecutionHostFactory = _QualificationHostFactory
    try:
        runtime = dynamic_mission.InstalledDynamicMissionRuntime.open(str(root), provider_id="codex-chatgpt-session")
    finally:
        dynamic_mission.EngineeringPlatformExecutionHostFactory = original_factory
    try:
        # There is intentionally no Mission in this isolated state.  These
        # public calls must reject selection before any start/resume/provider
        # work; their failure proves no source-tree-only helper is required.
        for operation in (
            lambda: runtime.action_derivation_readback("MISSION-ABSENT"),
            lambda: runtime.resume("MISSION-ABSENT"),
        ):
            try:
                operation()
            except dynamic_mission.InstalledDynamicMissionError:
                pass
            else:
                raise RuntimeError("public durable Mission selection unexpectedly accepted an absent Mission")
        return {
            "installed_module": str(Path(__import__("forge").__file__).resolve()),
            "provider_configuration": configured["configuration_id"],
            "configuration_revision": configured["version"],
            "readback": "selection-rejected-without-generation",
            "resume": "selection-rejected-without-generation",
        }
    finally:
        runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    if args.data_root is not None:
        args.data_root.mkdir(parents=True, exist_ok=True)
        outcome = qualify(args.data_root)
    else:
        with TemporaryDirectory(prefix="forge-installed-durable-") as temporary:
            outcome = qualify(Path(temporary) / "runtime")
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
