"""Installed Forge Server Runtime V1 qualification.

Run only from a fresh installed distribution, outside a source checkout.  The
qualification uses synthetic roots and credentials and never contacts a real
Engineering Platform or provider.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen

from forge._version import canonical_version
from forge.ep_simulator import EpSimulatorServer, EpSimulatorState
from forge.models import (
    ExecutionEvidenceOutcome,
    ExecutionRequest,
    ForgeActionContextEnvelope,
    ForgePlanningContextEnvelope,
    Producer,
    ProducerContract,
    ProducerIdentity,
    ProviderPromptDefinition,
    RepositoryRevisionBinding,
    RuntimePrompt,
    RuntimePromptEnvelope,
    RuntimePromptSection,
    RuntimePromptSectionKind,
)
from forge.runtime import RuntimeBootstrap
from forge.runtime.database import RuntimeDatabase
from forge.scheduler.ep_http_adapter import (
    EngineeringPlatformHttpConfiguration,
    EngineeringPlatformHttpExecutionHost,
)


def _digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _port() -> int:
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


def _credential(root: Path) -> Path:
    value = root / "server-token"
    value.write_text("synthetic-installed-server-token\n", encoding="utf-8")
    value.chmod(0o600)
    return value


def _request() -> ExecutionRequest:
    sections = tuple(
        RuntimePromptSection(kind, (kind.value + " qualification",))
        for kind in RuntimePromptSectionKind
    )
    prompt = RuntimePrompt(
        "installed-server-runtime-prompt",
        "installed-intent",
        "1",
        "installed-action",
        ProviderPromptDefinition("installed-provider", "1"),
        "sha256:" + "a" * 64,
        sections,
        mission_id="MISSION-INSTALLED-SERVER",
        execution_metadata=(
            ("mission_revision", "1"),
            ("provider_definition", "installed-provider"),
            ("provider_version", "1"),
        ),
    )
    context = ForgeActionContextEnvelope.create(
        action_id="installed-action",
        summary="Exercise the installed Forge EP HTTP boundary.",
        source_digest=prompt.generation_request_digest,
    )
    planning = ForgePlanningContextEnvelope.create(
        mission_id="MISSION-INSTALLED-SERVER",
        mission_revision="1",
        intent_id="installed-intent",
        intent_revision="1",
        action_id="installed-action",
        mission_title="Installed Server qualification",
        business_summary="Qualify packaging and transport.",
        engineering_summary="Exercise installed Server and EP simulator bytes.",
        mission_lifecycle="ACTIVE",
        decision_evidence_reference="architecture-review:installed-server",
    )
    binding = RepositoryRevisionBinding(
        "a" * 40, None, "repository-truth:installed-server", "sha256:" + "f" * 64,
    )
    contract = ProducerContract(
        Producer(ProducerIdentity("forge", "FORGE", canonical_version())),
        "installed-server-correlation",
        "installed-action",
        RuntimePromptEnvelope(
            prompt.id, "1.0", "text/markdown",
            "installed Forge Server qualification prompt",
            _digest(b"installed Forge Server qualification prompt"),
        ),
        ("Execute only the supplied Runtime Prompt.",),
        (
            ("intent_id", "installed-intent"),
            ("intent_revision", "1"),
            ("mission_revision", "1"),
            ("repository_id", "forge"),
            ("workspace_id", "forge"),
        ),
        action_context=context,
        planning_context=planning,
        mission_id="MISSION-INSTALLED-SERVER",
        repository_revision_binding=binding,
    )
    return ExecutionRequest(
        "engineering-platform",
        "MISSION-INSTALLED-SERVER",
        "installed-intent",
        "1",
        "installed-action",
        prompt,
        "forge",
        "forge",
        "installed-server-correlation",
        "2026-09-22T00:00:00Z",
        producer_contract=contract,
        repository_revision_binding=binding,
        repository_identity="pcvantol/forge",
        origin_identity="pcvantol/forge",
    )


def _read_instance(port: int) -> dict[str, object]:
    request = Request(
        f"http://127.0.0.1:{port}/v1/instance",
        headers={"Authorization": "Bearer synthetic-installed-server-token"},
    )
    with urlopen(request, timeout=1) as response:
        value = json.loads(response.read())
    if not isinstance(value, dict):
        raise RuntimeError("installed Server instance readback is malformed")
    return value


def _start_server(root: Path, port: int) -> subprocess.Popen[str]:
    environment = os.environ.copy()
    for name in ("HOME", "USER", "LOGNAME", "CODEX_HOME", "PYTHONPATH"):
        environment.pop(name, None)
    return subprocess.Popen(
        [
            sys.executable, "-I", "-m", "forge", "--data-root", str(root),
            "server", "run", "--credential-file", str(_credential(root)),
            "--host", "127.0.0.1", "--port", str(port), "--tick-interval", "0.05",
        ],
        cwd=tempfile.gettempdir(),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait(port: int, process: subprocess.Popen[str]) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out, err = process.communicate()
            raise RuntimeError("installed Forge Server terminated early: " + (err or out)[-1000:])
        try:
            return _read_instance(port)
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("installed Forge Server did not become reachable")


def run() -> dict[str, object]:
    version = canonical_version()
    if distribution("forge-autonomy").version != version:
        raise RuntimeError("installed distribution version differs from canonical Forge version")

    with tempfile.TemporaryDirectory(prefix="forge-server-installed-") as temporary:
        root = Path(temporary)
        roots = tuple(
            (root / name).resolve()
            for name in ("instance-a", "instance-b")
        )
        for item in roots:
            RuntimeBootstrap(data_root=item, forge_version=version).open().close()
        ports = (_port(), _port())
        if ports[0] == ports[1]:
            ports = (ports[0], _port())
        processes = tuple(_start_server(item, port) for item, port in zip(roots, ports))
        try:
            instances = tuple(_wait(port, process) for port, process in zip(ports, processes))
            identities = tuple(str(item["instance"]["instance_id"]) for item in instances)
            if identities[0] == identities[1]:
                raise RuntimeError("installed multi-instance qualification reused an instance identity")
            if tuple(int(item["listener"]["port"]) for item in instances) != ports:
                raise RuntimeError("installed multi-instance listener readback differs")
            if tuple(Path(str(item["instance"]["data_root"])) for item in instances) != roots:
                raise RuntimeError("installed multi-instance roots differ")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                try:
                    process.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)
                if process.returncode != 0:
                    raise RuntimeError("installed Forge Server did not stop cleanly")

        state = EpSimulatorState(
            project_id="forge",
            repository_id="forge",
            repository_identity="pcvantol/forge",
            consumer_id="forge-consumer",
            instance_id="installed-ep-simulator",
            bearer_token="installed-simulator-token",
        )
        runtime_database = RuntimeDatabase(root / "http-client")
        try:
            with EpSimulatorServer(state) as server:
                host = EngineeringPlatformHttpExecutionHost(
                    EngineeringPlatformHttpConfiguration(
                        server.base_url,
                        "forge",
                        "installed-simulator-token",
                        expected_instance_id="installed-ep-simulator",
                        expected_consumer_id="forge-consumer",
                        repository_id="forge",
                        repository_identity="pcvantol/forge",
                        peer_binding_id="installed-simulator-peer",
                        peer_configuration_revision=1,
                        peer_configuration_digest="sha256:" + "d" * 64,
                        allow_loopback_http=True,
                    ),
                    runtime_database,
                )
                if host.preflight()["instance"]["id"] != "installed-ep-simulator":
                    raise RuntimeError("installed EP simulator preflight identity differs")
                request = _request()
                if host.dispatch(request) is not None:
                    raise RuntimeError("accepted installed simulator submission unexpectedly had a run")
                submission_id = state.submission_ids()[0]
                state.complete(submission_id)
                dispatch = host.recover_dispatch(request)
                if dispatch is None:
                    raise RuntimeError("installed simulator terminal dispatch is unavailable")
                evidence = host.retrieve_evidence(dispatch)
                if evidence is None or evidence.outcome is not ExecutionEvidenceOutcome.COMPLETE:
                    raise RuntimeError("installed simulator terminal evidence did not round-trip")
        finally:
            runtime_database.close()

        return {
            "qualification": "FORGE_SERVER_RUNTIME_V1_INSTALLED_ARTIFACT",
            "version": version,
            "server_instances": 2,
            "multi_instance": "PASS",
            "headless_foreground": "PASS",
            "clean_sigterm": "PASS",
            "ep_simulator_real_http_boundary": "PASS",
            "ep_simulator_submissions": len(state.submission_ids()),
            "production_ep_contacted": False,
            "production_provider_contacted": False,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    result = run()
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "forge-server-runtime-v1.public.json").write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
