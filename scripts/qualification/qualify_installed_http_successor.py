"""Qualify an installed Forge Mission's A -> HTTP EP -> evidence -> B loop.

Run this script with the Python 3.14 interpreter of a non-editable wheel
installation, away from the source checkout. Only the external Codex process,
credential resolver and immutable repository artifact reader are substituted.
The EP simulator speaks the real versioned HTTP boundary in the parent process.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from importlib.metadata import distribution
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from threading import Lock
import time
from typing import Any
from unittest.mock import patch
from zipfile import ZipFile

import forge
import forge.runtime.dynamic_mission as composition
from forge.ep_simulator import EpSimulatorScenario, EpSimulatorServer, EpSimulatorState, SIMULATOR_CONTRACT_VERSION
from forge.execution import ExecutionLoopError, RecoveryAuthorization
from forge.execution_host_configuration import (
    EngineeringPlatformExecutionHostFactory, EngineeringPlatformPeerConfigurationService,
)
from forge.governance_authority import ArchitecturePlanningEvidence
from forge.governance import resolve_governance_profile
from forge.governed_candidate_intake import GovernedCandidateIntake, GovernedCandidateIntakeError
from forge.lifecycle import (MissionCandidate, MissionRecommendation,
                             RecommendationLifecycleStore, RecommendationStatus)
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_observation import canonical_digest
from forge.models.execution_host import ExecutionHostTemporaryUnavailable
from forge.models.mission_recommendation import RequiredDiscipline
from forge.operator_identity import InstallationOperatorService
from forge.planner.codex_cli_session import (
    CodexCliChatGPTSessionPlanningProvider, CodexCliSessionReadinessChecker,
)
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderSecurityService, ProviderAuthenticationMode,
)
from forge.qualification import criterion_completion as fixture
from forge.qualification.producer_fixture_conformance import (
    rejection_matrix, source_receipt, validate_fixture, validate_identity_fixture,
)
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from forge.runtime import RuntimeBootstrap
from forge.runtime.bootstrap import RuntimeResolutionError
from forge.runtime.dynamic_mission import InstalledDynamicMissionError, InstalledDynamicMissionRuntime
from forge.runtime.service import RuntimeServiceBusy
from forge.secure_store import MacOSKeychainSecureStoreAdapter, SecretReference, SecretState
from forge.state.mission_state import MissionStateStoreError


TOKEN = "isolated-qualification-token"
INSTANCE = "isolated-ep-simulator"
CONSUMER = "isolated-forge-consumer"
PROJECT = "isolated-project"
HOST = "synthetic-host"
GOVERNANCE_PROFILE = "solo"
GOVERNANCE_ACTOR = "primary_operator"
SCENARIOS = (
    "partial", "post-assessment-reopen", "single", "effect-declaration-legacy",
    "successor-stale-gap", "successor-proven-gap", "successor-optional",
    "delayed", "pre-send-reopen",
    "host-recovery", "failed-recovery",
    "declined-before-run",
    "concurrent-start", "tampered", "tampered-action", "tampered-run",
    "tampered-repository", "tampered-producer", "tampered-request-digest",
    "artifact-corrupt", "artifact-schema",
    "artifact-withheld", "artifact-unavailable",
    "assurance-blocked", "budget-exhausted", "ambiguous", "ambiguous-recovered",
)
PROVIDER_CASES = ("unavailable", "login-expired", "not-started", "local-rejected", "invalid-output",
                  "scope-expansion", "scope-outside", "unknown-dependency",
                  "missing-human-gate", "missing-risk-input", "ambiguous")


def _child_env(root: Path) -> dict[str, str]:
    """Give every scenario an isolated identity, configuration and scratch root."""
    home, scratch, config = (root / name for name in ("home", "scratch", "config"))
    for directory in (home, scratch, config, config / "gh", config / "codex"):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home), "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch),
        "XDG_CONFIG_HOME": str(config), "GH_CONFIG_DIR": str(config / "gh"),
        "CODEX_HOME": str(config / "codex"), "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "PATH": "/usr/bin:/bin",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "NO_PROXY": "127.0.0.1,localhost,::1", "no_proxy": "127.0.0.1,localhost,::1",
    }


def _with_case_cleanup(root: Path, operation, *args):
    started = time.monotonic()
    try:
        result = operation(root, *args)
        if not isinstance(result, dict):
            raise RuntimeError("installed qualification case returned no result")
        return {**result, "duration_ms": round((time.monotonic() - started) * 1000)}
    finally:
        for directory in ("home", "scratch", "config"):
            path = root / directory
            if path.exists():
                shutil.rmtree(path)


@contextmanager
def _loopback_only():
    """Deny nonfixture network from an installed Forge scenario process."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def allowed(address):
        return (isinstance(address, tuple) and address
                and address[0] in {"127.0.0.1", "::1", "localhost"})

    def checked_connect(sock, address):
        if not allowed(address):
            raise PermissionError("qualification denies non-loopback network")
        return original_connect(sock, address)

    def checked_connect_ex(sock, address):
        if not allowed(address):
            raise PermissionError("qualification denies non-loopback network")
        return original_connect_ex(sock, address)

    def checked_getaddrinfo(host, *args, **kwargs):
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise PermissionError("qualification denies non-loopback name resolution")
        return original_getaddrinfo(host, *args, **kwargs)

    def checked_process(*_args, **_kwargs):
        raise PermissionError("qualification denies real provider, gh, and host subprocesses")

    with patch.object(socket.socket, "connect", checked_connect), \
         patch.object(socket.socket, "connect_ex", checked_connect_ex), \
         patch.object(socket, "getaddrinfo", checked_getaddrinfo), \
         patch.object(subprocess, "run", checked_process), \
         patch.object(subprocess, "Popen", checked_process):
        yield
EP_IDENTITY_READBACK_SOURCE = {
    "repository": "pcvantol/engineering-platform",
    "revision": "66433d7a2260397ec438a3052acae8ef50a84022",
    "product_version": "2.3.109",
    "contract_version": "1.0", "producer_readback_version": "1.3",
    "contract_sha256": "sha256:40d749293ce27c86f5b051d74867bbca01def74b8394ac059dac414a6e4083ca",
    "serializer_sha256": "sha256:c2335e9e4edd3cbe4b56d992527d1e5a64ed9296d482c40bd5fe3e915ceadbd3",
    "http_test_sha256": "sha256:23ddddc26918bb3038983121154c011e71c4b42b17a1c6fe7803a69cda24c35b",
    "producer_state": "PROTECTED_MAIN_SOURCE_AND_INSTALLED_FIE10_QUALIFIED",
}
# These are adversarial EP-boundary fixtures, not Forge preflight stubs.  The
# expected reasons are the product adapter/factory's stable, secret-free errors.
PREFLIGHT_CASES = {
    "readback-absent": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "readback-incompatible": "EP_READBACK_CONTRACT_INCOMPATIBLE",
    "terminal-absent": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "terminal-incompatible": "EP_TERMINAL_CONTRACT_INCOMPATIBLE",
    "wrong-instance": "EP_INSTANCE_IDENTITY_MISMATCH",
    "wrong-consumer": "EP_AUTHENTICATED_CONSUMER_IDENTITY_MISMATCH",
    "wrong-project": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "wrong-repository": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "inactive-consumer": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "inactive-project": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "repository-not-authority": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "repository-unbound": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "scope-unauthorized": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "credential-missing": "EP credential reference is not resolvable: MISSING",
    "credential-revoked": "EP credential reference is not resolvable: REVOKED",
    "credential-invalid": "EP rejected request: 401",
    "http-401": "EP rejected request: 401",
    "http-403": "EP rejected request: 403",
    "declaration-public-version": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "declaration-missing-producer": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "declaration-missing-auth-field": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "effect-request-missing": "EP_EFFECT_CONTRACT_DECLARATION_MALFORMED",
    "effect-result-unsupported": "EP_EFFECT_CONTRACT_DECLARATION_MALFORMED",
    "terminal-effect-only": "EP_TERMINAL_CONTRACT_INCOMPATIBLE",
}
EP_PREFLIGHT_SOURCE = {
    "repository": "pcvantol/engineering-platform",
    "revision": "66433d7a2260397ec438a3052acae8ef50a84022",
    "product_version": "2.3.109",
    "path": "src/engineering_platform/server.py",
    "sha256": "sha256:92e0e8c1c904bbefdf6200328bb9c03a55939b1a2fcf3b131c00ecd7d707013a",
    "declaration_contract": "1.1",
    "producer_readback_contracts": ["1.2", "1.3"],
    "terminal_evidence_contract": "1.4",
    "governed_continuation_contract": "ep-governed-continuation-evidence/v1",
}
GOVERNANCE_CASES = (
    "candidate-alone", "missing-business", "missing-architecture",
    "rejected-business", "rejected-architecture",
    "wrong-business-actor", "wrong-business-role",
    "wrong-architecture-actor", "wrong-architecture-role",
    "stale-candidate", "changed-scope", "changed-criteria", "changed-spec",
)


class _SyntheticCredentialResolver:
    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        assert reference.serialized == "keychain://synthetic/ep"
        return SecretState.RESOLVABLE, TOKEN


class _PreflightCredentialResolver(_SyntheticCredentialResolver):
    def __init__(self, case: str) -> None:
        self.case = case

    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        if self.case == "credential-missing":
            return SecretState.MISSING, None
        if self.case == "credential-revoked":
            return SecretState.REVOKED, None
        if self.case == "credential-invalid":
            return SecretState.RESOLVABLE, "invalid-isolated-token"
        return super().resolve(reference)


def _installed_wheel(wheel: Path, *, source_revision: str | None = None,
                     verify_source: bool = False) -> dict[str, Any]:
    if sys.version_info[:2] != (3, 14) or not sys.flags.isolated or sys.flags.optimize:
        raise RuntimeError("qualification requires assertion-enabled isolated Python 3.14.x")
    if not wheel.is_file():
        raise RuntimeError("candidate wheel is missing")
    installed = distribution("forge-autonomy")
    direct = json.loads(installed.read_text("direct_url.json") or "{}")
    wheel_bytes = wheel.read_bytes()
    digest = sha256(wheel_bytes).hexdigest()
    if (direct.get("archive_info", {}).get("hashes", {}).get("sha256") != digest
            or direct.get("dir_info", {}).get("editable")):
        raise RuntimeError("installed distribution is not the exact candidate wheel")
    package_root = Path(installed.locate_file("forge")).resolve()
    package = Path(forge.__file__).resolve()
    if (not package.is_relative_to(package_root)
            or "site-packages" not in package.parts
            or not Path(sys.executable).absolute().is_relative_to(Path(sys.prefix).absolute())):
        raise RuntimeError("Forge import did not come from installed site-packages")
    modules = (
        "forge/__init__.py", "forge/runtime/dynamic_mission.py",
        "forge/scheduler/ep_http_adapter.py", "forge/ep_simulator.py",
    )
    module_digests = {}
    source_files_verified = 0
    installed_files_verified = 0
    source_root = Path(__file__).resolve().parents[2]
    tracked = set()
    if verify_source:
        if source_revision is None or subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True,
        ).strip() != source_revision:
            raise RuntimeError("qualification source revision is not exact HEAD")
        if subprocess.check_output(
            ["git", "-C", str(source_root), "status", "--porcelain"], text=True,
        ).strip():
            raise RuntimeError("qualification source checkout is dirty")
        tracked = set(subprocess.check_output(
            ["git", "-C", str(source_root), "ls-files", "-z", "--", "forge"],
        ).decode("utf-8").split("\0"))
    with ZipFile(BytesIO(wheel_bytes)) as archive:
        for name in archive.namelist():
            if not name.startswith("forge/") or name.endswith("/"):
                continue
            payload = archive.read(name)
            installed_file = Path(installed.locate_file(name)).resolve()
            if (not installed_file.is_relative_to(package_root)
                    or installed_file.read_bytes() != payload):
                raise RuntimeError("installed Forge payload differs from selected wheel")
            installed_files_verified += 1
            if verify_source:
                if name not in tracked or (source_root / name).read_bytes() != payload:
                    raise RuntimeError("wheel product payload differs from exact tracked source")
                source_files_verified += 1
        if installed_files_verified == 0 or verify_source and source_files_verified == 0:
            raise RuntimeError("wheel lacks verified Forge product files")
        for module in modules:
            expected = archive.read(module)
            installed_file = Path(installed.locate_file(module)).resolve()
            if (not installed_file.is_relative_to(package_root)
                    or installed_file.read_bytes() != expected):
                raise RuntimeError("installed Forge module bytes differ from the selected wheel")
            module_digests[module] = "sha256:" + sha256(expected).hexdigest()
    return {"version": installed.version, "wheel_sha256": "sha256:" + digest,
            "module_sha256": module_digests,
            "installed_product_files_verified": installed_files_verified,
            "source_product_files_verified": source_files_verified if verify_source else None}


def _installed_identity_negative(root: Path, wheel: Path) -> dict[str, str]:
    """Require a byte-drifted wheel to fail before any installed scenario starts."""
    root.mkdir(parents=True)
    altered = root / "altered-candidate.whl"
    altered.write_bytes(wheel.read_bytes() + b"qualification-byte-drift")
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(altered), "--output-dir", str(root / "denial")]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False,
                                timeout=30, env=_child_env(root))
        (root / "denial.raw.private.log").write_text(result.stdout + result.stderr)
        denial = fixture._read(root / "denial" / "installed-http-successor.public.json", {})
        if (result.returncode != 1 or denial.get("result") != "FAIL"
                or denial.get("failure") != {"stage": "installed_wheel_identity", "type": "RuntimeError"}):
            raise RuntimeError("installed wheel byte drift did not fail before scenario setup")
        return {"case": "installed-wheel-byte-drift", "result": "REJECTED",
                "stage": "installed_wheel_identity"}
    finally:
        altered.unlink(missing_ok=True)
        for directory in ("home", "scratch", "config"):
            path = root / directory
            if path.exists():
                shutil.rmtree(path)


def _installed_runtime_storage_negatives(root: Path) -> list[dict[str, str]]:
    """Require existing-instance marker/storage errors to preserve identity."""
    bootstrap = RuntimeBootstrap(data_root=root, forge_version="qualification")
    with bootstrap.open() as database:
        original_id = database.runtime_identity.runtime_id
    marker = root / "instance" / "runtime-instance.json"
    database_path = root / "forge.db"
    marker_bytes = marker.read_bytes()
    marker.write_text("foreign-runtime-id\n", encoding="utf-8")
    try:
        try:
            bootstrap.open()
        except RuntimeResolutionError:
            pass
        else:
            raise RuntimeError("wrong Runtime marker reopened or replaced the instance")
    finally:
        marker.write_bytes(marker_bytes)
    with bootstrap.open() as database:
        if database.runtime_identity.runtime_id != original_id:
            raise RuntimeError("marker denial changed installed Runtime identity")
    held = root / "forge.db.held"
    database_path.rename(held)
    try:
        try:
            bootstrap.open()
        except RuntimeResolutionError:
            pass
        else:
            raise RuntimeError("missing Runtime storage initialized a replacement instance")
        if database_path.exists() or marker.read_bytes() != marker_bytes:
            raise RuntimeError("missing Runtime storage changed the selected instance")
    finally:
        held.rename(database_path)
    with bootstrap.open() as database:
        if database.runtime_identity.runtime_id != original_id:
            raise RuntimeError("storage denial changed installed Runtime identity")
    return [{"case": "wrong-runtime-marker", "result": "REJECTED"},
            {"case": "missing-runtime-storage", "result": "REJECTED"}]


def _open(root: Path, stack: ExitStack, *,
          credential_case: str = "", provider_case: str = "") -> InstalledDynamicMissionRuntime:
    transport = fixture._CodexTransport(root)
    if provider_case:
        original = transport

        def fault_transport(command, **kwargs):
            if provider_case == "unavailable" and "--version" in command:
                return subprocess.CompletedProcess(command, 1, "", "")
            if provider_case == "login-expired" and command[-2:] == ["login", "status"]:
                return subprocess.CompletedProcess(command, 1, "Not logged in\n", "")
            if "exec" not in command:
                return original(command, **kwargs)
            fixture._append(root / "provider-attempts.private.json", {"case": provider_case})
            if provider_case == "not-started":
                raise OSError("synthetic process start denial")
            if provider_case == "local-rejected":
                return subprocess.CompletedProcess(command, 2, "", "error: unexpected argument --output-schema")
            if provider_case == "ambiguous":
                raise subprocess.TimeoutExpired(command, 10)
            if provider_case == "invalid-output":
                output = Path(command[command.index("--output-last-message") + 1])
                output.write_text('{"result":{"kind":"proposals","proposals":[{"unbound":true}]}}')
                return subprocess.CompletedProcess(
                    command, 0, '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":50}}\n', "",
                )
            if provider_case in {"scope-expansion", "scope-outside", "unknown-dependency",
                                 "missing-human-gate", "missing-risk-input",
                                 "successor-stale-gap", "successor-proven-gap", "successor-optional"}:
                result = original(command, **kwargs)
                output = Path(command[command.index("--output-last-message") + 1])
                document = json.loads(output.read_text())
                proposal = document["result"]["proposals"][0]
                if provider_case == "scope-expansion":
                    proposal["write_scopes"] = ["unapproved/source"]
                elif provider_case == "scope-outside":
                    proposal["scope"] = "foreign-repository"
                elif provider_case == "unknown-dependency":
                    proposal["dependencies"] = ["foreign-action"]
                elif provider_case == "missing-human-gate":
                    proposal["human_gates"] = []
                elif provider_case == "missing-risk-input":
                    proposal["risk_inputs"] = []
                elif provider_case == "successor-stale-gap":
                    proposal["mission_gap"]["planning_snapshot_digest"] = "sha256:" + "0" * 64
                elif provider_case == "successor-proven-gap":
                    incoming = json.loads(kwargs["input"])
                    proven = [item["criterion_id"] for item in incoming["snapshot"]["criteria"]
                              if item["status"] == "PROVEN"]
                    assert len(proven) == 1
                    proposal["mission_gap"]["criterion_ids"] = proven
                else:
                    proposal["mission_gap"] = None
                output.write_text(json.dumps(document))
                return result
            raise RuntimeError("unsupported provider fault case")

        transport = fault_transport
    checker = CodexCliSessionReadinessChecker(runner=transport, path_usable=lambda _: True)
    stack.enter_context(patch.object(composition.MacOSGeneratedUIDIdentityAdapter, "resolve",
                                     return_value=fixture.IDENTITY))
    stack.enter_context(patch.object(composition, "CodexCliChatGPTSessionPlanningProvider",
        side_effect=lambda configuration: CodexCliChatGPTSessionPlanningProvider(
            configuration, runner=transport, readiness_checker=checker)))
    # The actual persisted-binding factory and HTTP adapter remain production code.
    stack.enter_context(patch.object(composition, "EngineeringPlatformExecutionHostFactory",
                                     lambda: EngineeringPlatformExecutionHostFactory(
                                         _PreflightCredentialResolver(credential_case))))
    stack.enter_context(patch("forge.completion.repository_observer.GitHubRepositoryArtifactReader.read",
        side_effect=lambda repository, revision, path: fixture._raw_reader(root, repository, revision, path)))
    return stack.enter_context(InstalledDynamicMissionRuntime.open(str(root / "runtime"), provider_id=fixture.PROVIDER))


def _configure(root: Path, endpoint: str) -> None:
    assert not (root / "runtime").exists(), "qualification must use a fresh data root"
    with RuntimeBootstrap(data_root=root / "runtime", forge_version="qualification").open() as database:
        operators = InstallationOperatorService(database, lambda: fixture.IDENTITY)
        context = operators.first_bind()
        PlanningProviderSecurityService(database, MacOSKeychainSecureStoreAdapter(), operators).configure(
            configuration_id="synthetic-config", provider_id=fixture.PROVIDER, operator_context=context,
            authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
            provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
            external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
            executable_path="/usr/bin/false", adapter_version="codex-cli-chatgpt-session-v1",
            timeout_seconds=10, input_token_bound=40000, context_token_bound=48000,
            output_token_bound=8000,
        )
    EngineeringPlatformPeerConfigurationService(root / "runtime").configure(
        binding_id="isolated-ep-peer", endpoint=endpoint,
        expected_ep_instance_id=INSTANCE, ep_consumer_id=CONSUMER,
        execution_host_id=HOST, ep_project_id=PROJECT,
        ep_repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository,
        credential_reference=SecretReference.parse("keychain://synthetic/ep"),
        operator_id="isolated-qualification", allow_loopback_http=True,
    )


def _candidate_fixture(lifecycle: RecommendationLifecycleStore,
                       runtime: InstalledDynamicMissionRuntime, *, maximum_actions: int = 3) -> tuple[
                           MissionCandidate, GovernedCandidateIntake,
                           ArchitectureMission, ArchitecturePlanningEvidence]:
    options = {"criterion_assessment_contracts": fixture._contracts(), "maximum_actions": maximum_actions,
               "maximum_consecutive_no_progress_actions": 1,
               "repository_evidence_source": fixture.SOURCE}
    recommendation = MissionRecommendation(
        "synthetic-recommendation", "Synthetic export contract", "qualification",
        "Provide an inspectable contract.", "Publish two explicit JSON properties.",
        "Inspectability.", "Two verified JSON properties.", "No behavior claim.",
        ("repository:synthetic",), "architecture-review:synthetic",
        ("external fixtures",), ("Defer this synthetic proof.",), 90,
        "2026-09-18T09:59:00Z",
    )
    lifecycle.create_recommendation(recommendation, actor="synthetic-portfolio",
                                    rationale="Isolated installed qualification.")
    lifecycle.transition(recommendation.id, RecommendationStatus.RECOMMENDED,
                         actor="synthetic-portfolio", occurred_at="2026-09-18T09:59:01Z",
                         rationale="Candidate is ready for separate governance.")
    candidate = lifecycle.create_candidate(MissionCandidate(
        "synthetic-candidate", recommendation.id, recommendation.title,
        recommendation.engineering_summary, ("synthetic-contract",),
        (fixture.K1, fixture.K2), ("no behavior claim",), recommendation.dependencies,
    ))
    bridge = GovernedCandidateIntake(
        lifecycle, runtime, resolve_governance_profile(GOVERNANCE_PROFILE),
    )
    revision, _, architecture_id = bridge.decision_ids(candidate.id)
    mission_preview = ArchitectureMission(
        "MISSION-PREVIEW", candidate.id, candidate.title, candidate.objective,
        recommendation.business_summary, recommendation.business_value,
        architecture_id, recommendation.id, candidate.scope,
        candidate.architecture_constraints, candidate.acceptance_criteria,
        ("external fixtures",), candidate.dependencies,
        (HOST,), (RequiredDiscipline.PLATFORM_ARCHITECTURE,),
        ("scope-drift",), ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING, **options,
    )
    planning = ArchitecturePlanningEvidence(
        candidate.scope, ("contracts",), candidate.architecture_constraints,
        ("scope-drift",), ("protected-delivery",), candidate.dependencies,
        40000, 8000, revision, mission_spec_digest=canonical_digest(mission_preview.to_dict()),
        **options,
    )
    return candidate, bridge, mission_preview, planning


def _initial_truth() -> RepositoryTruthSnapshot:
    return RepositoryTruthSnapshot(
        "initial", fixture.SOURCE.repository_id, "0" * 40, "2026-09-18T09:59:00Z",
        (RepositoryTruthEvidence("initial-revision", "git_commit", "0" * 40,
            "repository://synthetic/initial", fixture._digest("initial")),),
    )


def _prepare(root: Path, scenario: str, endpoint: str, *, start: bool = True,
             capture_phase: str = "prepare") -> None:
    _configure(root, endpoint)
    with ExitStack() as stack:
        runtime = _open(root, stack)
        with RecommendationLifecycleStore(root / "governance" / "lifecycle.sqlite") as lifecycle:
            candidate, bridge, mission_preview, planning = _candidate_fixture(
                lifecycle, runtime, maximum_actions=1 if scenario == "budget-exhausted" else 3,
            )
            revision = bridge.decision_ids(candidate.id)[0]
            rejected = []

            def reject_unapproved(label: str, proposed: ArchitectureMission) -> None:
                try:
                    bridge.admit(candidate.id, proposed, planning,
                                 occurred_at="2026-09-18T09:59:30Z")
                except GovernedCandidateIntakeError:
                    pass
                else:
                    raise RuntimeError(f"{label} unexpectedly allocated a Mission")
                if (runtime.database._connection.execute(
                        "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0]
                        or runtime.database._connection.execute(
                            "SELECT COUNT(*) FROM mission_state").fetchone()[0]):
                    raise RuntimeError(f"{label} created a Mission before exact approval")
                rejected.append(label)

            reject_unapproved("missing-business", mission_preview)
            bridge.approve_business(candidate.id, actor=GOVERNANCE_ACTOR,
                                    occurred_at="2026-09-18T09:59:02Z", rationale="Business value approved.",
                                    human_gates=planning.human_gates)
            reject_unapproved("missing-architecture", mission_preview)
            bridge.approve_architecture(candidate.id, mission_preview, planning,
                                        actor=GOVERNANCE_ACTOR, occurred_at="2026-09-18T09:59:03Z",
                                        rationale="Exact technical contract approved.")
            reject_unapproved("changed-objective", replace(
                mission_preview, summary="Unapproved objective."))
            fixture._write(root / "governance-negative.private.json", {"rejected": rejected})
            admitted = bridge.admit(candidate.id, mission_preview, planning,
                                    occurred_at="2026-09-18T10:00:00Z")
        mission_id = admitted.mission_id
        assert not admitted.actions
        runtime.assign_progression_policy(mission_id, {
            "assignment_id": "qualification-progression-" + mission_id.lower(),
            "profile_id": GOVERNANCE_PROFILE,
            "profile_revision": "1", "policy_revision": "1", "mode": "continuous",
            "required_decision_role": "platform_architect",
            "higher_scope_obligations": list(planning.human_gates),
            "expected_state_revision": admitted.revision,
        })
        if start:
            if scenario == "pre-send-reopen":
                # Let the real runner persist its immutable request, then
                # interrupt before the first EP POST. The next OS process must
                # send that exact request without another provider turn.
                with patch.object(runtime.host, "dispatch", side_effect=
                                  ExecutionHostTemporaryUnavailable("synthetic pre-send interruption")):
                    runtime.start(mission_id, _initial_truth())
            else:
                runtime.start(mission_id, _initial_truth())
        fixture._write(root / "population.private.json", {
            "mission_id": mission_id, "scenario": scenario,
            "runtime_id": runtime.database.runtime_identity.runtime_id,
        })
        _capture(root, runtime, capture_phase)
        if capture_phase == "preflight-stage":
            fixture._write(root / f"{capture_phase}.peer.private.json",
                           _peer_binding_snapshot(runtime))


def _approve_business(bridge: GovernedCandidateIntake, candidate: MissionCandidate,
                      planning: ArchitecturePlanningEvidence) -> None:
    bridge.approve_business(candidate.id, actor=GOVERNANCE_ACTOR,
                            occurred_at="2026-09-18T09:59:02Z",
                            rationale="Synthetic Business approval.",
                            human_gates=planning.human_gates)


def _approve_architecture(bridge: GovernedCandidateIntake, candidate: MissionCandidate,
                          preview: ArchitectureMission,
                          planning: ArchitecturePlanningEvidence) -> None:
    bridge.approve_architecture(candidate.id, preview, planning,
                                actor=GOVERNANCE_ACTOR, occurred_at="2026-09-18T09:59:03Z",
                                rationale="Synthetic Architecture approval.")


def _expected_denial(operation, error_type: type[Exception]) -> dict[str, str]:
    try:
        operation()
    except error_type as error:
        return {"type": type(error).__name__, "reason": str(error)}
    raise RuntimeError("an unauthorized governance operation unexpectedly succeeded")


def _stage_governance_case(case: str, lifecycle: RecommendationLifecycleStore,
                           candidate: MissionCandidate, bridge: GovernedCandidateIntake,
                           preview: ArchitectureMission,
                           planning: ArchitecturePlanningEvidence) -> tuple[ArchitectureMission, dict | None]:
    prior_denial = None
    needs_business = case in {
        "missing-architecture", "rejected-architecture", "wrong-architecture-actor",
        "wrong-architecture-role", "stale-candidate", "changed-scope",
        "changed-criteria", "changed-spec",
    }
    needs_architecture = case in {
        "stale-candidate", "changed-scope", "changed-criteria", "changed-spec",
    }
    if needs_business:
        _approve_business(bridge, candidate, planning)
    if needs_architecture:
        _approve_architecture(bridge, candidate, preview, planning)
    if case == "missing-business":
        prior_denial = _expected_denial(
            lambda: _approve_architecture(bridge, candidate, preview, planning),
            GovernedCandidateIntakeError)
    elif case in {"rejected-business", "rejected-architecture"}:
        role, target = ((GOVERNANCE_ACTOR, RecommendationStatus.BUSINESS_REJECTED)
                        if case == "rejected-business" else
                        (GOVERNANCE_ACTOR, RecommendationStatus.ARCHITECTURE_REJECTED))
        lifecycle.transition(candidate.recommendation_id, target, actor=role,
                             occurred_at="2026-09-18T09:59:04Z",
                             rationale="Synthetic governance rejection.",
                             references=(candidate.id, planning.provenance_revision))
    elif case in {"wrong-business-actor", "wrong-business-role"}:
        actor = "stranger" if case == "wrong-business-actor" else "platform_architect"
        prior_denial = _expected_denial(
            lambda: bridge.approve_business(
                candidate.id, actor=actor, occurred_at="2026-09-18T09:59:04Z",
                rationale="Unqualified actor.", human_gates=planning.human_gates),
            PermissionError)
    elif case in {"wrong-architecture-actor", "wrong-architecture-role"}:
        actor = "stranger" if case == "wrong-architecture-actor" else "business_owner"
        prior_denial = _expected_denial(
            lambda: bridge.approve_architecture(
                candidate.id, preview, planning, actor=actor,
                occurred_at="2026-09-18T09:59:04Z", rationale="Unqualified actor."),
            PermissionError)
    elif case == "stale-candidate":
        lifecycle.update_candidate(candidate.id, objective="Changed after both decisions.")
    elif case == "changed-scope":
        preview = replace(preview, scope=("unapproved-repository",))
    elif case == "changed-criteria":
        lifecycle.update_candidate(candidate.id, acceptance_criteria=("unapproved criterion",))
    elif case == "changed-spec":
        preview = replace(preview, summary="Unapproved Mission specification.")
    return preview, prior_denial


def _negative_observation(root: Path, lifecycle: RecommendationLifecycleStore,
                          runtime: InstalledDynamicMissionRuntime,
                          bridge: GovernedCandidateIntake, preview: ArchitectureMission,
                          planning: ArchitecturePlanningEvidence) -> dict:
    denial = _expected_denial(
        lambda: bridge.admit("synthetic-candidate", preview, planning,
                             occurred_at="2026-09-18T09:59:30Z"),
        GovernedCandidateIntakeError)
    allocation = lifecycle.allocation_for_recommendation("synthetic-recommendation")
    counts = {
        "lifecycle_allocations": int(allocation is not None),
        "runtime_allocations": runtime.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0],
        "admitted_missions": runtime.database._connection.execute(
            "SELECT COUNT(*) FROM mission_state").fetchone()[0],
        "planner_invocations": len(fixture._read(root / "provider-inputs.private.json", [])),
    }
    if any(counts.values()):
        raise RuntimeError("rejected Candidate caused an allocation, admission or planning effect")
    decisions = [item for item in lifecycle.history("synthetic-recommendation")
                 if item.kind in {"business_decision", "architecture_decision"}]
    for decision in decisions:
        if not {"synthetic-candidate", planning.provenance_revision}.issubset(decision.references):
            raise RuntimeError("governance decision lost the exact Candidate revision")
    return {
        "rejection": denial, "counts": counts,
        "recommendation_status": lifecycle.get_recommendation("synthetic-recommendation").status.value,
        "candidate_revision": canonical_digest(lifecycle.get_candidate("synthetic-candidate").to_dict()),
        "decision_lineage": [{"kind": item.kind, "id": item.id} for item in decisions],
        "canonical_approval_count": runtime.database._connection.execute(
            "SELECT COUNT(*) FROM governance_decisions").fetchone()[0],
        "runtime_instance": runtime.database.runtime_identity.runtime_id,
        "pid": os.getpid(),
    }


def _governance_phase(root: Path, case: str, phase: str, endpoint: str) -> None:
    if phase == "governance-first":
        _configure(root, endpoint)
    with ExitStack() as stack:
        runtime = _open(root, stack)
        with RecommendationLifecycleStore(root / "governance" / "lifecycle.sqlite") as lifecycle:
            if phase == "governance-first":
                candidate, bridge, preview, planning = _candidate_fixture(lifecycle, runtime)
                preview, prior_denial = _stage_governance_case(
                    case, lifecycle, candidate, bridge, preview, planning)
                fixture._write(root / "governance-input.private.json", {
                    "preview": preview.to_dict(), "planning": planning.to_dict(),
                    "prior_denial": prior_denial,
                })
            else:
                saved = fixture._read(root / "governance-input.private.json")
                bridge = GovernedCandidateIntake(
                    lifecycle, runtime, resolve_governance_profile(GOVERNANCE_PROFILE),
                )
                preview = ArchitectureMission.from_dict(saved["preview"])
                planning = ArchitecturePlanningEvidence.from_dict(saved["planning"])
            fixture._write(root / f"{phase}.governance.private.json",
                           _negative_observation(root, lifecycle, runtime, bridge, preview, planning))


def _capture(root: Path, runtime: InstalledDynamicMissionRuntime, phase: str) -> dict:
    mission_id = fixture._read(root / "population.private.json")["mission_id"]
    state = runtime.states._as_document(runtime.states.get(mission_id))
    fixture._write(root / f"{phase}.state.private.json", state)
    fixture._write(root / f"{phase}.process.private.json", {"pid": os.getpid()})
    return state


def _phase(root: Path, scenario: str, phase: str, endpoint: str) -> None:
    if phase == "prepare":
        _prepare(root, scenario, endpoint, start=scenario != "concurrent-start")
        return
    with ExitStack() as stack:
        runtime = _open(root, stack, provider_case=(scenario if phase == "after-a" and scenario in {
            "successor-stale-gap", "successor-proven-gap", "successor-optional",
        } else ""))
        population = fixture._read(root / "population.private.json")
        mission_id = population["mission_id"]
        if runtime.database.runtime_identity.runtime_id != population["runtime_id"]:
            raise RuntimeError("fresh Forge process opened a different Runtime Instance")
        if phase == "completed-resume":
            try:
                runtime.resume(mission_id)
            except Exception as error:
                if type(error).__name__ != "InstalledDynamicMissionError":
                    raise
            else:
                raise RuntimeError("completed Mission unexpectedly resumed")
        elif phase in {"accept", "accept-replay"}:
            pending = fixture._read(root / "final-before-accept.state.private.json")["pause_reason"]
            decision = {
                "schema_version": "forge-final-acceptance-decision/v1",
                "decision_id": "installed-business-acceptance-" + scenario,
                "requirement_id": pending["requirement_id"],
                "subject_digest": pending["subject_digest"],
                "mission_state_revision": pending["mission_state_revision"],
                "completion_digest": pending["completion_digest"],
                "terminal_evidence_digest": pending["terminal_evidence_digest"],
                "policy_revision": pending["policy_revision"],
                "decision": "accept", "reason": "The approved Mission evidence is sufficient.",
            }
            context = runtime.repository.operators.context()
            principal = "local-operator:v1:" + runtime.repository._operator_id(context)
            runtime.accept_final_completion(
                mission_id, decision, authenticated_principal_reference=principal,
            )
        elif phase in {"recover-denied", "recover"}:
            active = runtime.states.get(mission_id).current_engineering_action
            if not isinstance(active, dict):
                raise RuntimeError("terminal Action is missing at recovery boundary")
            action_id = active["id"] if phase == "recover" else "foreign-action"
            authorization = RecoveryAuthorization(
                mission_id, action_id, "operator-installed-recovery-001",
                "The simulated terminal blocker was resolved under exact Action authority.",
                "a" * 40,
            )
            if phase == "recover-denied":
                try:
                    runtime.recover(mission_id, authorization)
                except ExecutionLoopError as error:
                    if str(error) != "recovery authorization must name the unresolved Engineering Action":
                        raise
                    fixture._write(root / "recover-denied.private.json", {
                        "type": type(error).__name__, "reason": str(error),
                    })
                else:
                    raise RuntimeError("foreign Action recovery unexpectedly succeeded")
            else:
                runtime.recover(mission_id, authorization)
        elif phase in {"race-start-a", "race-start-b"}:
            (root / f"{phase}.ready.private").write_text(str(os.getpid()))
            deadline = time.monotonic() + 20
            while not (root / "race-go.private").exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("concurrent start barrier timed out")
                time.sleep(0.01)
            try:
                runtime.start(mission_id, _initial_truth())
            except Exception as error:
                fixture._write(root / f"{phase}.race.private.json", {
                    "result": "REJECTED", "type": type(error).__name__, "reason": str(error),
                })
            else:
                fixture._write(root / f"{phase}.race.private.json", {"result": "STARTED"})
        elif phase == "after-a-cut":
            def before_successor() -> bool:
                observed = runtime.states.get(mission_id)
                marker = observed.resume.get("terminal_continuation", {})
                return marker.get("phase") != "ASSESSED"

            runtime._keep_running = before_successor
            runtime.resume(mission_id)
        elif phase != "readback":
            runtime.resume(mission_id)
        state = _capture(root, runtime, phase)
        if phase == "after-a" and scenario in {"successor-stale-gap", "successor-proven-gap",
                                                "successor-optional"}:
            attempts = [json.loads(row["document"]) for row in runtime.database._connection.execute(
                "SELECT document FROM action_derivations ORDER BY derivation_id",
            ).fetchall()]
            fixture._write(root / "successor-validation.private.json", [{
                "processing_phase": item["processing_phase"], "lifecycle": item["lifecycle"],
                "error_code": item.get("error_code"),
            } for item in attempts])
        admitted = fixture._read(root / "prepare.state.private.json")
        if state["mission"] != admitted["mission"] or state["admission_contract"] != admitted["admission_contract"]:
            raise RuntimeError("approved Mission or admission changed across processes")


def _run_phase(root: Path, scenario: str, phase: str, endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root), "--scenario", scenario,
               "--phase", phase, "--endpoint", endpoint]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90,
                            env=_child_env(root))
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed {scenario}/{phase} failed; see private phase log")
    return fixture._read(root / f"{phase}.state.private.json")


def _run_governance_phase(root: Path, case: str, phase: str,
                          endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root),
               "--governance-case", case, "--phase", phase, "--endpoint", endpoint]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90,
                            env=_child_env(root))
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed governance {case}/{phase} failed; see private phase log")
    return fixture._read(root / f"{phase}.governance.private.json")


def _count_ep_http_requests(server: EpSimulatorServer) -> list[str]:
    requests: list[str] = []
    request_lock = Lock()
    base_handler = server.server.RequestHandlerClass

    class CountingHandler(base_handler):
        def parse_request(self) -> bool:
            parsed = super().parse_request()
            if parsed:
                # Observe every HTTP path and method before route/auth checks; the simulator
                # audit only records accepted submissions and misses negative traffic.
                with request_lock:
                    requests.append(f"{self.command} {self.path}")
            return parsed

    server.server.RequestHandlerClass = CountingHandler
    return requests


_REMOVE = object()
_DECLARATION_CHANGES = {
    "readback-absent": (("contracts", "producer_readback"), _REMOVE),
    "readback-incompatible": (("contracts", "producer_readback"), ["1.3"]),
    "terminal-absent": (("contracts", "terminal_evidence"), _REMOVE),
    "terminal-incompatible": (("contracts", "terminal_evidence"), ["1.3"]),
    "inactive-consumer": (("authentication", "consumer_status"), "INACTIVE"),
    "inactive-project": (("authentication", "project_status"), "INACTIVE"),
    "repository-not-authority": (("authentication", "repository_role"), "observer"),
    "repository-unbound": (("authentication", "local_repository_binding"), "UNBOUND"),
    "scope-unauthorized": (("authentication", "submission_authorization"), "DENIED"),
    "declaration-public-version": (("contract_version",), "1.0"),
    "declaration-missing-producer": (("producer",), _REMOVE),
    "declaration-missing-auth-field": (("authentication", "consumer_status"), _REMOVE),
    "effect-request-missing": (("contracts", "effect_request"), _REMOVE),
    "effect-result-unsupported": (("contracts", "effect_result"), ["1.1"]),
    "terminal-effect-only": (("contracts", "terminal_evidence"), ["1.5"]),
}


def _preflight_fixture(case: str) -> tuple[EpSimulatorState, dict | None]:
    """Change only the external EP declaration or HTTP/identity fixture."""
    identities = {
        "wrong-instance": {"instance_id": "foreign-ep-instance"},
        "wrong-consumer": {"consumer_id": "foreign-consumer"},
        "wrong-project": {"project_id": "foreign-project"},
        "wrong-repository": {"repository_id": "foreign-repository"},
    }
    http_status = {"http-401": 401, "http-403": 403}.get(case)
    scenario = (EpSimulatorScenario(preflight_http_status=http_status)
                if http_status is not None else
                EpSimulatorScenario(effect_declaration_supported=True)
                if case in {"effect-request-missing", "effect-result-unsupported",
                            "terminal-effect-only"} else None)
    settings = {
        "project_id": PROJECT, "repository_id": fixture.SOURCE.repository_id,
        "repository_identity": fixture.SOURCE.github_repository, "consumer_id": CONSUMER,
        "instance_id": INSTANCE, "bearer_token": TOKEN, "scenario": scenario,
    }
    settings.update(identities.get(case, {}))
    state = EpSimulatorState(**settings)
    change = _DECLARATION_CHANGES.get(case)
    if change is None:
        return state, None
    declaration = deepcopy(state.compatibility())
    path, replacement = change
    target = declaration
    for segment in path[:-1]:
        target = target[segment]
    if replacement is _REMOVE:
        del target[path[-1]]
    else:
        target[path[-1]] = replacement
    return state, declaration


def _peer_binding_snapshot(runtime: InstalledDynamicMissionRuntime) -> dict:
    """Read the exact selected peer and generation without exposing its document."""
    connection = runtime.database._connection
    binding = connection.execute(
        "SELECT binding_id,configuration_revision,configuration_digest,document "
        "FROM execution_host_peer_configuration WHERE singleton=1"
    ).fetchone()
    generation = connection.execute(
        "SELECT generation,last_digest FROM execution_host_peer_generation WHERE singleton=1"
    ).fetchone()
    if binding is None or generation is None:
        raise RuntimeError("preflight qualification lost the selected EP peer")
    return {
        "binding_id": binding[0], "configuration_revision": binding[1],
        "configuration_digest": binding[2],
        "document_sha256": "sha256:" + sha256(binding[3].encode()).hexdigest(),
        "generation": generation[0], "generation_last_digest": generation[1],
        "detach_operations": connection.execute(
            "SELECT COUNT(*) FROM execution_host_peer_detach_operations"
        ).fetchone()[0],
    }


def _preflight_phase(root: Path, case: str, phase: str, endpoint: str) -> None:
    if phase == "preflight-stage":
        _prepare(root, case, endpoint, start=False, capture_phase=phase)
        return
    mission_id = fixture._read(root / "population.private.json")["mission_id"]
    expected_reason = PREFLIGHT_CASES[case]
    expected_type = ("PeerConfigurationError" if case in {"credential-missing", "credential-revoked"}
                     else "ValueError")
    try:
        with ExitStack() as stack:
            runtime = _open(root, stack, credential_case=case)
            runtime.start(mission_id, _initial_truth())
    except Exception as error:
        if type(error).__name__ != expected_type or str(error) != expected_reason:
            raise RuntimeError(f"{case} failed at the wrong product gate") from error
        observed_type, observed_reason = type(error).__name__, str(error)
    else:
        raise RuntimeError(f"{case} unexpectedly started a Mission")
    # Observation reopens the canonical store with a valid synthetic resolver,
    # but performs no preflight, planner call, retarget or submission.
    with ExitStack() as stack:
        runtime = _open(root, stack)
        state = _capture(root, runtime, phase)
        fixture._write(root / f"{phase}.peer.private.json",
                       _peer_binding_snapshot(runtime))
        connection = runtime.database._connection
        counts = {
            "mission_allocations": connection.execute(
                "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0],
            "admitted_missions": connection.execute(
                "SELECT COUNT(*) FROM mission_state").fetchone()[0],
            "execution_bindings": connection.execute(
                "SELECT COUNT(*) FROM execution_host_bindings").fetchone()[0],
            "exchange_audit": connection.execute(
                "SELECT COUNT(*) FROM execution_host_exchange_audit").fetchone()[0],
            "planner_invocations": len(fixture._read(root / "provider-inputs.private.json", [])),
        }
    fixture._write(root / f"{phase}.preflight.private.json", {
        "pid": os.getpid(), "reason": observed_reason, "type": observed_type,
        "status": state["status"], "counts": counts,
    })


def _run_preflight_phase(root: Path, case: str, phase: str,
                         endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root),
               "--preflight-case", case, "--phase", phase, "--endpoint", endpoint]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90,
                            env=_child_env(root))
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed preflight {case}/{phase} failed; see private phase log")
    if phase == "preflight-stage":
        return fixture._read(root / f"{phase}.state.private.json")
    return fixture._read(root / f"{phase}.preflight.private.json")


def _preflight_case(root: Path, case: str, wheel: Path) -> dict:
    root.mkdir(parents=True)
    simulator, declaration = _preflight_fixture(case)
    fixture_identity = {
        "declaration": declaration if declaration is not None else simulator.compatibility(),
        "instance_id": simulator.instance_id, "consumer_id": simulator.consumer_id,
        "project_id": simulator.project_id, "repository_id": simulator.repository_id,
        "preflight_http_status": simulator.scenario.preflight_http_status,
        "credential_mode": ("missing" if case == "credential-missing" else
                            "revoked" if case == "credential-revoked" else
                            "invalid" if case == "credential-invalid" else "valid"),
    }
    fixture_digest = "sha256:" + sha256(json.dumps(
        fixture_identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with ExitStack() as stack:
        if declaration is not None:
            stack.enter_context(patch.object(simulator, "compatibility",
                                             return_value=declaration))
        stack.enter_context(server)
        staged = _run_preflight_phase(root, case, "preflight-stage", server.base_url, wheel)
        first = _run_preflight_phase(root, case, "preflight-first", server.base_url, wheel)
        repeat = _run_preflight_phase(root, case, "preflight-repeat", server.base_url, wheel)
    states = [fixture._read(root / f"{phase}.state.private.json") for phase in (
        "preflight-stage", "preflight-first", "preflight-repeat")]
    processes = [fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in (
        "preflight-stage", "preflight-first", "preflight-repeat")]
    peers = [fixture._read(root / f"{phase}.peer.private.json") for phase in (
        "preflight-stage", "preflight-first", "preflight-repeat")]
    if len(set(processes)) != 3 or states != [staged] * 3:
        raise RuntimeError(f"{case} changed durable Mission state or reused a Forge process")
    if (peers != [peers[0]] * 3 or peers[0]["binding_id"] != "isolated-ep-peer"
            or peers[0]["configuration_revision"] != 1
            or peers[0]["generation"] != 1 or peers[0]["detach_operations"] != 0):
        raise RuntimeError(f"{case} retargeted or detached the selected EP peer")
    if (staged["status"] != "APPROVED_PLANNABLE" or staged["actions"] or staged["intents"]
            or staged["execution_correlation"] is not None):
        raise RuntimeError(f"{case} crossed the Action or execution gate")
    expected_gets = 0 if case in {"credential-missing", "credential-revoked"} else 2
    if (requests != ["GET /v1/producer-compatibility"] * expected_gets
            or simulator.submission_ids() or simulator.audit):
        raise RuntimeError(f"{case} made unexpected listener traffic or EP submission")
    expected_counts = {
        "mission_allocations": 1, "admitted_missions": 1,
        "execution_bindings": 0, "exchange_audit": 0, "planner_invocations": 0,
    }
    if (first["counts"] != repeat["counts"] or first["counts"] != expected_counts
            or any(first[key] != repeat[key] for key in ("reason", "type", "status"))
            or first["reason"] != PREFLIGHT_CASES[case]):
        raise RuntimeError(f"{case} changed its denial or durable counters on restart")
    return {
        "case": case, "result": "REJECTED", "reason": first["reason"],
        "error_type": first["type"], "fixture_sha256": fixture_digest,
        "durable_status": staged["status"],
        "peer_binding_unchanged": True,
        "peer_configuration_digest": peers[0]["configuration_digest"],
        "forge_processes": len(processes), "preflight_gets": len(requests),
        "submission_posts": sum(request.startswith("POST ") for request in requests),
        "ep_accepted_submissions": len(simulator.submission_ids()),
        "counts": first["counts"],
    }


def _governance_case(root: Path, case: str, wheel: Path) -> dict:
    root.mkdir(parents=True)
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
    )
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with server:
        first = _run_governance_phase(root, case, "governance-first", server.base_url, wheel)
        repeat = _run_governance_phase(root, case, "governance-repeat", server.base_url, wheel)
    if first["pid"] == repeat["pid"]:
        raise RuntimeError(f"{case} was not repeated in a fresh Forge process")
    for key in ("rejection", "counts", "recommendation_status", "candidate_revision",
                "decision_lineage", "canonical_approval_count", "runtime_instance"):
        if first[key] != repeat[key]:
            raise RuntimeError(f"{case} changed its rejection or identity on fresh-process repeat")
    expected_status = ("BUSINESS_REJECTED" if case == "rejected-business" else
                       "ARCHITECTURE_REJECTED" if case == "rejected-architecture" else
                       "ARCHITECTURE_APPROVED" if case in {
                           "stale-candidate", "changed-scope", "changed-criteria", "changed-spec"} else
                       "BUSINESS_APPROVED" if case in {
                           "missing-architecture", "wrong-architecture-actor", "wrong-architecture-role"} else
                       "RECOMMENDED")
    if first["recommendation_status"] != expected_status:
        raise RuntimeError(f"{case} has the wrong canonical governance state")
    expected_approvals = (2 if expected_status == "ARCHITECTURE_APPROVED" else
                          1 if expected_status in {"BUSINESS_APPROVED", "ARCHITECTURE_REJECTED"} else 0)
    if first["canonical_approval_count"] != expected_approvals:
        raise RuntimeError(f"{case} persisted an unintended approval")
    if requests:
        raise RuntimeError(f"{case} made an EP HTTP request")
    saved = fixture._read(root / "governance-input.private.json")
    return {
        "case": case, "rejection": first["rejection"],
        "prior_denial": saved["prior_denial"],
        "recommendation_status": first["recommendation_status"],
        "approved_revision": saved["planning"]["provenance_revision"],
        "candidate_revision": first["candidate_revision"],
        "decision_lineage": first["decision_lineage"],
        "canonical_approval_count": first["canonical_approval_count"],
        "counts": {**first["counts"], "ep_requests": len(requests),
                   "ep_accepted_submissions": len(simulator.submission_ids())},
        "forge_processes": 2,
    }


def _ambiguous_result(root: Path, simulator: EpSimulatorState, endpoint: str,
                      wheel: Path, initial: dict) -> dict:
    assert initial["status"] == "WAITING_FOR_EXECUTION"
    assert len(initial["actions"]) == len(simulator.submission_ids()) == 1
    assert [event["event"] for event in simulator.audit] == [
        "submission_accepted", "submission_response_lost",
    ]
    replay = _run_phase(root, "ambiguous", "ambiguous-replay", endpoint, wheel)
    assert replay["status"] == "FAILED" and replay["waiting_reason"] == "host_dispatch_failed"
    assert len(replay["actions"]) == len(simulator.submission_ids()) == 1
    assert len(fixture._read(root / "provider-inputs.private.json")) == 1
    readback = _run_phase(root, "ambiguous", "readback", endpoint, wheel)
    assert readback == replay
    assert [event["event"] for event in simulator.audit] == [
        "submission_accepted", "submission_response_lost",
    ], "ambiguous dispatch must neither resubmit nor derive a successor"
    phases = ("prepare", "ambiguous-replay", "readback")
    processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
    assert len(processes) == len(phases)
    return {"scenario": "ambiguous", "status": replay["status"],
            "waiting_reason": replay["waiting_reason"], "actions": 1,
            "submissions": 1, "forge_processes": len(processes),
            "phase_statuses": {phase: fixture._read(root / f"{phase}.state.private.json")["status"]
                               for phase in phases}, "planner_invocations": 1}


def _scenario(root: Path, scenario: str, wheel: Path) -> dict:
    root.mkdir()
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
        scenario=(EpSimulatorScenario(connection_loss_at=frozenset({"submission-after-accept-once"}))
                  if scenario == "ambiguous" else
                  EpSimulatorScenario(
                      name="identity-recovery", identity_readback_supported=True,
                      connection_loss_at=frozenset({"submission-after-accept-once"}),
                  ) if scenario == "ambiguous-recovered" else
                  EpSimulatorScenario(name="delayed-terminal", terminal_after_reads=6)
                  if scenario == "delayed" else
                  EpSimulatorScenario(name="artifact-unavailable", artifact_http_status=404)
                  if scenario == "artifact-unavailable" else
                  EpSimulatorScenario(name="request-digest-readback-fault",
                                      accepted_digest_mismatch_on_readback=True)
                  if scenario == "tampered-request-digest" else
                  EpSimulatorScenario(name="effect-declaration-legacy",
                                      effect_declaration_supported=True)
                  if scenario == "effect-declaration-legacy" else None),
    )
    fixture._write(root / "artifact-a.json", {
        "report": {"fields": ["report_data"]},
        "policy": {"authorization_required": scenario in {
            "single", "effect-declaration-legacy", "delayed", "pre-send-reopen",
            "host-recovery", "failed-recovery",
            "ambiguous-recovered",
        }},
    })
    fixture._write(root / "artifact-b.json", {
        "report": {"fields": ["report_data"]}, "policy": {"authorization_required": True},
    })
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with server:
        initial = _run_phase(root, scenario, "prepare", server.base_url, wheel)
        if scenario == "pre-send-reopen":
            assert initial["status"] == "WAITING_FOR_EXECUTION"
            assert len(initial["actions"]) == 1 and not simulator.submission_ids()
            persisted = initial["execution_correlation"]["request"]
            assert persisted["correlation_id"] and persisted["producer_contract"]
            initial = _run_phase(root, scenario, "send-after-reopen", server.base_url, wheel)
            assert initial["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert initial["execution_correlation"]["request"] == persisted
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
        fixture_receipts = []
        fixture_negatives = []
        recovery_summary = None
        governance_negative = fixture._read(root / "governance-negative.private.json")["rejected"]
        assert governance_negative == ["missing-business", "missing-architecture", "changed-objective"]
        assert len(initial["actions"]) == len(simulator.submission_ids()) == 1
        a = simulator.submission_ids()[0]
        request_a = simulator.submitted_payload(a)
        fixture_receipts.append(validate_fixture(
            request_a, simulator.readback(a), None, project_id=PROJECT,
            repository_id=fixture.SOURCE.repository_id, submission_id=a,
        ))
        if scenario == "ambiguous":
            posts = sum(request.startswith("POST ") for request in requests)
            assert posts == len(simulator.submission_ids()) == 1
            return {**_ambiguous_result(root, simulator, server.base_url, wheel, initial),
                    "governance_rejections": governance_negative,
                    "producer_fixtures": fixture_receipts, "producer_fixture_negatives": fixture_negatives,
                    "submission_posts": posts, "ep_http_requests": len(requests)}
        if scenario == "declined-before-run":
            simulator.decline_before_run(a)
        elif scenario == "assurance-blocked":
            simulator.complete(
                a, outcome="BLOCKED", assurance="FAIL", quality_review="FAIL",
                security_review="UNRESOLVED",
            )
        elif scenario in {"host-recovery", "failed-recovery"}:
            if scenario == "failed-recovery":
                simulator.complete(a, outcome="FAILED", assurance="NOT_RECORDED")
            else:
                simulator.complete(a, outcome="BLOCKED")
        else:
            simulator.complete(a, delivery_revision="a" * 40)
        if scenario == "declined-before-run":
            pass  # No run, artifact or terminal evidence exists in this EP disposition.
        elif scenario == "artifact-withheld":
            simulator.withhold_terminal_artifact(a)
        else:
            source_readback, source_artifact = simulator.terminal_documents(a)
            fixture_receipts.append(validate_fixture(
                request_a, source_readback, source_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=a,
            ))
        if scenario == "artifact-corrupt":
            simulator.corrupt_terminal_artifact(a)
        if scenario in {"partial", "post-assessment-reopen"}:
            fixture_negatives = rejection_matrix(
                request_a, source_readback, source_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=a,
            )
        if scenario in {"tampered", "tampered-action", "tampered-run",
                        "tampered-repository", "tampered-producer", "artifact-schema"}:
            readback, artifact = simulator.terminal_documents(a)
            if scenario == "tampered":
                readback["correlation"]["mission_id"] = "wrong-mission"
            elif scenario == "tampered-action":
                readback["correlation"]["engineering_action_id"] = "wrong-action"
            elif scenario == "tampered-run":
                readback["run"]["id"] = "wrong-run"
            elif scenario == "tampered-repository":
                readback["submission"]["repository_id"] = "wrong-repository"
            elif scenario == "tampered-producer":
                readback["producer"]["id"] = "wrong-producer"
            elif scenario == "artifact-schema":
                document = json.loads(artifact)
                del document["report"]
                artifact = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
            simulator.seed_terminal(a, readback, artifact)
        if scenario == "post-assessment-reopen":
            cut = _run_phase(root, scenario, "after-a-cut", server.base_url, wheel)
            marker = cut["resume"].get("terminal_continuation", {})
            criteria = {item["criterion"]: item for item in cut["completion"]["criteria"]}
            assert marker.get("phase") == "ASSESSED"
            assert criteria[fixture.K1]["status"] == "PROVEN"
            assert criteria[fixture.K2]["status"] == "UNSATISFIED"
            assert len(cut["actions"]) == len(simulator.submission_ids()) == 1
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
        after_a = _run_phase(root, scenario, "after-a", server.base_url, wheel)
        if scenario == "ambiguous-recovered":
            observed = [event["response"] for event in simulator.audit
                        if event["event"] == "submission_identity_read"]
            assert len(observed) == 1
            fixture_receipts.append(validate_identity_fixture(
                request_a, observed[0], source_readback, source_artifact,
                project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
                consumer_id=CONSUMER, instance_id=INSTANCE, submission_id=a,
            ))
        poll_phases: list[str] = []
        if scenario == "delayed":
            assert after_a["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert len(simulator.submission_ids()) == 1
            for index in range(1, 7):
                phase = f"poll-{index}"
                poll_phases.append(phase)
                after_a = _run_phase(root, scenario, phase, server.base_url, wheel)
                assert len(simulator.submission_ids()) == 1
                assert len(fixture._read(root / "provider-inputs.private.json")) == 1
                if after_a["status"] == "AWAITING_APPROVAL":
                    break
                assert after_a["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert after_a["status"] == "AWAITING_APPROVAL"
            assert poll_phases, "delayed terminal evidence did not require a fresh-process poll"
        if scenario in {"partial", "post-assessment-reopen"}:
            criteria = {item["criterion"]: item for item in after_a["completion"]["criteria"]}
            assert criteria[fixture.K1]["status"] == "PROVEN"
            assert criteria[fixture.K2]["status"] == "UNSATISFIED"
            assert len(after_a["actions"]) == len(simulator.submission_ids()) == 2
            continuation = fixture._read(root / "provider-inputs.private.json")[1]["snapshot"]["continuation_context"]
            assert continuation["prior_actions"][0]["id"] == "synthetic-action-a"
            assert continuation["prior_actions"][0]["status"] == "COMPLETE"
            assert continuation["terminal_evidence"][0]["repository_evidence"]["repository_revision"] == "a" * 40
            assert [item["status"] for item in continuation["criterion_assessments"]] == ["PROVEN", "UNSATISFIED"]
            replay = _run_phase(root, scenario, "replay-b", server.base_url, wheel)
            assert len(replay["actions"]) == len(simulator.submission_ids()) == 2
            assert len(fixture._read(root / "provider-inputs.private.json")) == 2
            assert not any(event["event"] == "submission_duplicate" for event in simulator.audit)
            b = next(item for item in simulator.submission_ids() if item != a)
            request_b = simulator.submitted_payload(b)
            fixture_receipts.append(validate_fixture(
                request_b, simulator.readback(b), None, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=b,
            ))
            timeline = [(event["event"], event.get("submission_id")) for event in simulator.audit]
            assert timeline.index(("terminal_produced", a)) < timeline.index(("submission_accepted", b))
            simulator.complete(b, delivery_revision="b" * 40)
            b_readback, b_artifact = simulator.terminal_documents(b)
            fixture_receipts.append(validate_fixture(
                request_b, b_readback, b_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=b,
            ))
            final = _run_phase(root, scenario, "after-b", server.base_url, wheel)
            assert final["status"] == "AWAITING_APPROVAL" and len(final["actions"]) == 2
            assert final["pause_reason"]["schema_version"] == "forge-final-acceptance-requirement/v1"
            assert all(item["status"] == "PROVEN" for item in final["completion"]["criteria"])
        elif scenario in {"host-recovery", "failed-recovery"}:
            assert after_a["status"] == ("FAILED" if scenario == "failed-recovery" else "BLOCKED")
            denied = _run_phase(root, scenario, "recover-denied", server.base_url, wheel)
            assert denied == after_a and len(simulator.submission_ids()) == 1
            recovered = _run_phase(root, scenario, "recover", server.base_url, wheel)
            assert recovered["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert len(recovered["actions"]) == 1 and len(simulator.submission_ids()) == 2
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
            retry_id = next(item for item in simulator.submission_ids() if item != a)
            retry_request = simulator.submitted_payload(retry_id)
            assert retry_request["correlation_id"] != request_a["correlation_id"]
            fixture_receipts.append(validate_fixture(
                retry_request, simulator.readback(retry_id), None, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=retry_id,
            ))
            simulator.complete(retry_id, delivery_revision="b" * 40)
            retry_readback, retry_artifact = simulator.terminal_documents(retry_id)
            fixture_receipts.append(validate_fixture(
                retry_request, retry_readback, retry_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=retry_id,
            ))
            final = _run_phase(root, scenario, "after-recovery", server.base_url, wheel)
            assert final["status"] == "AWAITING_APPROVAL"
            assert len(final["actions"]) == 1 and len(simulator.submission_ids()) == 2
            assert [item["outcome"] for item in final["execution_history"]] == [
                "failed" if scenario == "failed-recovery" else "blocked", "complete",
            ]
            assert final["execution_history"][-1]["retry_of_correlation_id"] == request_a["correlation_id"]
            assert all(item["status"] == "PROVEN" for item in final["completion"]["criteria"])
            recovery_summary = {
                "denied_foreign_action": fixture._read(root / "recover-denied.private.json")["type"],
                "original_correlation_id": request_a["correlation_id"],
                "retry_correlation_id": retry_request["correlation_id"],
                "retry_of_correlation_id": final["execution_history"][-1]["retry_of_correlation_id"],
                "terminal_outcomes": [item["outcome"] for item in final["execution_history"]],
            }
        elif scenario in {"successor-stale-gap", "successor-proven-gap", "successor-optional"}:
            expected_code = {
                "successor-stale-gap": "STALE_MISSION_GAP_BINDING",
                "successor-proven-gap": "MISSION_CRITERION_ALREADY_PROVEN",
                "successor-optional": "FOLLOW_UP_NOT_CURRENT_MISSION",
            }[scenario]
            attempts = fixture._read(root / "successor-validation.private.json")
            assert len(attempts) == 2
            assert {(item["lifecycle"], item["error_code"]) for item in attempts} == {
                ("MATERIALIZED", None), ("FAILED", expected_code),
            }
            assert after_a["status"] in {"BLOCKED", "FAILED"}
            assert len(after_a["actions"]) == len(simulator.submission_ids()) == 1
            assert len(fixture._read(root / "provider-inputs.private.json")) == 2
            final = after_a
        elif scenario == "declined-before-run":
            final = after_a
            assert final["status"] in {"BLOCKED", "FAILED"}
            assert final["execution_history"][-1]["failure_code"] == "EP_DECLINED_BEFORE_RUN"
            assert len(final["actions"]) == len(simulator.submission_ids()) == 1
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
            assert [event["event"] for event in simulator.audit] == [
                "submission_accepted", "submission_declined",
            ]
        elif scenario == "budget-exhausted":
            final = after_a
            assert final["status"] == "BLOCKED"
            assert len(final["actions"]) == len(simulator.submission_ids()) == 1
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
            assert final["completion"]["all_required_criteria_proven"] is False
        elif scenario in {"single", "effect-declaration-legacy", "delayed",
                         "pre-send-reopen", "ambiguous-recovered"}:
            final = after_a
            assert final["status"] == "AWAITING_APPROVAL" and len(final["actions"]) == 1
            assert final["pause_reason"]["schema_version"] == "forge-final-acceptance-requirement/v1"
            assert len(simulator.submission_ids()) == 1
        else:
            final = after_a
            assert len(final["actions"]) == len(simulator.submission_ids()) == 1
            assert final["status"] in {"BLOCKED", "FAILED"}
            assert final["waiting_reason"] in {
                "host_dispatch_failed", "host_evidence_failed", "execution_blocked",
            }
            assert final["completion"] is None or final["completion"].get("all_required_criteria_proven") is not True
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
        if scenario in {"partial", "post-assessment-reopen", "single", "effect-declaration-legacy",
                        "delayed", "pre-send-reopen",
                        "host-recovery", "failed-recovery", "ambiguous-recovered"}:
            fixture._write(root / "final-before-accept.state.private.json", final)
            accepted = _run_phase(root, scenario, "accept", server.base_url, wheel)
            replayed = _run_phase(root, scenario, "accept-replay", server.base_url, wheel)
            assert accepted == replayed
            assert accepted["status"] == "COMPLETED"
            assert accepted["revision"] == final["revision"] + 1
            assert accepted["approval_record"]["decision_reference"] == final["pause_reason"]["requirement_id"]
            final = accepted
        readback = _run_phase(root, scenario, "readback", server.base_url, wheel)
        assert readback == final
        if scenario in {"partial", "post-assessment-reopen", "single", "effect-declaration-legacy",
                        "delayed", "pre-send-reopen",
                        "host-recovery", "failed-recovery", "ambiguous-recovered"}:
            stopped = _run_phase(root, scenario, "completed-resume", server.base_url, wheel)
            assert stopped == final
        assert not any(event["event"] == "submission_duplicate" for event in simulator.audit)
        if scenario == "ambiguous-recovered":
            assert sum(event["event"] == "submission_identity_read" for event in simulator.audit) == 1
            assert sum(event["event"] == "submission_accepted" for event in simulator.audit) == 1
        accepted = [event["submission_id"] for event in simulator.audit if event["event"] == "submission_accepted"]
        assert accepted == list(simulator.submission_ids())
        posts = sum(request.startswith("POST ") for request in requests)
        assert posts == len(simulator.submission_ids()), "Forge repeated an EP submission POST"
    phases = ["prepare", "after-a", "readback"]
    if scenario == "post-assessment-reopen":
        phases.append("after-a-cut")
    if scenario == "pre-send-reopen":
        phases.append("send-after-reopen")
    if scenario in {"partial", "post-assessment-reopen"}:
        phases += ["replay-b", "after-b"]
    if scenario in {"host-recovery", "failed-recovery"}:
        phases += ["recover-denied", "recover", "after-recovery"]
    phases += poll_phases
    if scenario in {"partial", "post-assessment-reopen", "single", "effect-declaration-legacy",
                    "delayed", "pre-send-reopen",
                    "host-recovery", "failed-recovery", "ambiguous-recovered"}:
        phases += ["accept", "accept-replay", "completed-resume"]
    processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
    assert len(processes) == len(phases), "Forge phases must use distinct OS processes"
    return {"scenario": scenario, "status": final["status"],
            "waiting_reason": final["waiting_reason"], "actions": len(final["actions"]),
            "submissions": len(simulator.submission_ids()), "forge_processes": len(processes),
            "governance_rejections": governance_negative,
            "producer_fixtures": fixture_receipts,
            "producer_fixture_negatives": fixture_negatives,
            "phase_statuses": {phase: fixture._read(root / f"{phase}.state.private.json")["status"]
                               for phase in phases},
            "planner_invocations": len(fixture._read(root / "provider-inputs.private.json")),
            "waiting_polls": len(poll_phases),
            "submission_posts": posts, "ep_http_requests": len(requests),
            **({"successor_rejection": expected_code} if scenario in {
                "successor-stale-gap", "successor-proven-gap", "successor-optional",
            } else {}),
            **({"no_run_disposition": {"state": "DECLINED", "failure_code": "EP_DECLINED_BEFORE_RUN"}}
               if scenario == "declined-before-run" else {}),
            **({"recovery": recovery_summary} if recovery_summary is not None else {})}


def _concurrent_start_case(root: Path, wheel: Path) -> dict:
    """Race two installed Forge processes at the public zero-Action start gate."""
    root.mkdir()
    fixture._write(root / "artifact-a.json", {
        "report": {"fields": ["report_data"]},
        "policy": {"authorization_required": True},
    })
    fixture._write(root / "artifact-b.json", {
        "report": {"fields": ["report_data"]},
        "policy": {"authorization_required": True},
    })
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
    )
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with server:
        staged = _run_phase(root, "concurrent-start", "prepare", server.base_url, wheel)
        assert staged["status"] == "APPROVED_PLANNABLE" and not staged["actions"]
        children = []
        handles = []
        try:
            for phase in ("race-start-a", "race-start-b"):
                command = [sys.executable, "-I", str(Path(__file__).resolve()),
                           "--wheel", str(wheel), "--output-dir", str(root),
                           "--scenario", "concurrent-start", "--phase", phase,
                           "--endpoint", server.base_url]
                handle = (root / f"{phase}.raw.private.log").open("w")
                handles.append(handle)
                child = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT,
                                         env=_child_env(root))
                children.append(child)
                deadline = time.monotonic() + 20
                while not (root / f"{phase}.ready.private").exists():
                    if time.monotonic() >= deadline or child.poll() is not None:
                        raise RuntimeError("installed starter did not open the same Runtime Instance")
                    time.sleep(0.01)
            (root / "race-go.private").write_text("start")
            for phase, child in zip(("race-start-a", "race-start-b"), children):
                if child.wait(timeout=90) != 0:
                    raise RuntimeError(f"installed {phase} failed after opening Runtime Instance")
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
            for handle in handles:
                handle.close()
        outcomes = [fixture._read(root / f"{phase}.race.private.json")
                    for phase in ("race-start-a", "race-start-b")]
        rejection = next((item for item in outcomes if item["result"] == "REJECTED"), {})
        expected_rejections = {
            RuntimeServiceBusy.__name__: "canonical runtime is busy",
            MissionStateStoreError.__name__: "mission state transition CREATED -> CREATED is not permitted",
            InstalledDynamicMissionError.__name__: "public start requires a canonically admitted zero-Action Mission",
        }
        if (sorted(item["result"] for item in outcomes) != ["REJECTED", "STARTED"]
                or rejection.get("reason") != expected_rejections.get(rejection.get("type"))
                or len(simulator.submission_ids()) != 1
                or len(fixture._read(root / "provider-inputs.private.json")) != 1):
            raise RuntimeError("concurrent starters crossed the single-flight Action boundary")
        submission_id = simulator.submission_ids()[0]
        payload = simulator.submitted_payload(submission_id)
        pending = validate_fixture(
            payload, simulator.readback(submission_id), None, project_id=PROJECT,
            repository_id=fixture.SOURCE.repository_id, submission_id=submission_id,
        )
        simulator.complete(submission_id, delivery_revision="a" * 40)
        terminal_readback, terminal_artifact = simulator.terminal_documents(submission_id)
        terminal = validate_fixture(
            payload, terminal_readback, terminal_artifact, project_id=PROJECT,
            repository_id=fixture.SOURCE.repository_id, submission_id=submission_id,
        )
        final = _run_phase(root, "concurrent-start", "after-a", server.base_url, wheel)
        assert final["status"] == "AWAITING_APPROVAL" and len(final["actions"]) == 1
        assert all(item["status"] == "PROVEN" for item in final["completion"]["criteria"])
        fixture._write(root / "final-before-accept.state.private.json", final)
        accepted = _run_phase(root, "concurrent-start", "accept", server.base_url, wheel)
        replayed = _run_phase(root, "concurrent-start", "accept-replay", server.base_url, wheel)
        readback = _run_phase(root, "concurrent-start", "readback", server.base_url, wheel)
        stopped = _run_phase(root, "concurrent-start", "completed-resume", server.base_url, wheel)
        assert accepted == replayed == readback == stopped
        assert accepted["status"] == "COMPLETED"
        posts = [request for request in requests if request.startswith("POST ")]
        assert len(posts) == 1 and not any(event["event"] == "submission_duplicate"
                                            for event in simulator.audit)
    phases = ("prepare", "race-start-a", "race-start-b", "after-a",
              "accept", "accept-replay", "readback", "completed-resume")
    processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
    assert len(processes) == len(phases)
    return {
        "scenario": "concurrent-start", "status": "COMPLETED", "actions": 1,
        "submissions": 1, "submission_posts": 1, "planner_invocations": 1,
        "forge_processes": len(processes), "race_outcomes": outcomes,
        "producer_fixtures": [pending, terminal],
        "phase_statuses": {phase: fixture._read(root / f"{phase}.state.private.json")["status"]
                           for phase in phases},
    }


def _run_preflight_child(args: argparse.Namespace, parser: argparse.ArgumentParser,
                         root: Path) -> bool:
    if not args.phase or not args.phase.startswith("preflight-"):
        return False
    if not args.preflight_case or not args.endpoint or args.scenario or args.governance_case or args.provider_case:
        parser.error("preflight child phase requires case and loopback endpoint")
    with _loopback_only():
        _preflight_phase(root, args.preflight_case, args.phase, args.endpoint)
    return True


def _provider_phase(root: Path, case: str, phase: str, endpoint: str) -> None:
    if phase == "provider-stage":
        _prepare(root, case, endpoint, start=False, capture_phase=phase)
        return
    with ExitStack() as stack:
        runtime = _open(root, stack, provider_case=case)
        mission_id = fixture._read(root / "population.private.json")["mission_id"]
        before = runtime.states.get(mission_id)
        failure = None
        try:
            if before.status.value == "APPROVED_PLANNABLE":
                runtime.start(mission_id, _initial_truth())
            else:
                runtime.resume(mission_id)
        except Exception as error:
            failure = {"type": type(error).__name__}
        state = _capture(root, runtime, phase)
        attempts = [json.loads(row["document"]) for row in runtime.database._connection.execute(
            "SELECT document FROM action_derivations ORDER BY derivation_id"
        ).fetchall()]
        fixture._write(root / f"{phase}.provider.private.json", {
            "failure": failure, "status": state["status"], "pid": os.getpid(),
            "attempts": len(fixture._read(root / "provider-attempts.private.json", [])),
            "durable_attempts": [{
                "derivation_id": item["derivation_id"], "processing_phase": item["processing_phase"],
                "lifecycle": item["lifecycle"], "error_code": item.get("error_code"),
            } for item in attempts],
            "durable_results": runtime.database._connection.execute(
                "SELECT COUNT(*) FROM action_derivation_results"
            ).fetchone()[0],
        })


def _run_provider_phase(root: Path, case: str, phase: str,
                        endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root),
               "--provider-case", case, "--phase", phase, "--endpoint", endpoint]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90,
                            env=_child_env(root))
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed provider {case}/{phase} failed; see private phase log")
    return fixture._read(root / f"{phase}.state.private.json" if phase == "provider-stage"
                         else root / f"{phase}.provider.private.json")


def _provider_case(root: Path, case: str, wheel: Path) -> dict:
    root.mkdir(parents=True)
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
    )
    with EpSimulatorServer(simulator) as server:
        staged = _run_provider_phase(root, case, "provider-stage", server.base_url, wheel)
        first = _run_provider_phase(root, case, "provider-first", server.base_url, wheel)
        repeat = _run_provider_phase(root, case, "provider-repeat", server.base_url, wheel)
    states = [fixture._read(root / f"{phase}.state.private.json") for phase in (
        "provider-stage", "provider-first", "provider-repeat",
    )]
    processes = [fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in (
        "provider-stage", "provider-first", "provider-repeat",
    )]
    if (len(set(processes)) != 3 or staged["status"] != "APPROVED_PLANNABLE"
            or first["status"] not in {"BLOCKED", "FAILED", "APPROVED_PLANNABLE"}
            or states[1]["actions"] or states[2]["actions"]
            or states[1]["intents"] or states[2]["intents"]
            or simulator.submission_ids()
            or any(event["event"] == "submission_accepted" for event in simulator.audit)):
        raise RuntimeError(f"{case} escaped the provider denial boundary")
    if first["attempts"] != (0 if case in {"unavailable", "login-expired"} else 1) or repeat["attempts"] != first["attempts"]:
        raise RuntimeError(f"{case} generated again after a failed or uncertain attempt")
    if states[1] != states[2]:
        raise RuntimeError(f"{case} changed durable Mission state on fresh-process repeat")
    expected_phase = {
        "unavailable": None,
        "login-expired": None,
        "not-started": "GENERATION_NOT_STARTED",
        "local-rejected": "GENERATION_NOT_STARTED",
        "invalid-output": "DETERMINISTIC_REJECTION",
        "scope-expansion": "DETERMINISTIC_REJECTION",
        "scope-outside": "DETERMINISTIC_REJECTION",
        "unknown-dependency": "DETERMINISTIC_REJECTION",
        "missing-human-gate": "DETERMINISTIC_REJECTION",
        "missing-risk-input": "DETERMINISTIC_REJECTION",
        "ambiguous": "GENERATION_MAY_HAVE_HAPPENED",
    }[case]
    durable = first["durable_attempts"]
    if (len(durable) != (0 if expected_phase is None else 1)
            or (expected_phase is not None and (durable[0]["processing_phase"] != expected_phase
                                                 or durable[0]["lifecycle"] != "FAILED"))
            or repeat["durable_attempts"] != durable
            or repeat["durable_results"] != first["durable_results"]):
        raise RuntimeError(f"{case} did not retain one classified durable attempt")
    return {
        "case": case, "status": first["status"], "attempts": first["attempts"],
        "failure": first["failure"], "repeat_failure": repeat["failure"],
        "durable_attempts": durable, "durable_results": first["durable_results"],
        "submissions": 0, "forge_processes": len(processes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--governance-case", choices=GOVERNANCE_CASES)
    parser.add_argument("--preflight-case", choices=tuple(PREFLIGHT_CASES))
    parser.add_argument("--provider-case", choices=PROVIDER_CASES)
    parser.add_argument("--phase", choices=("prepare", "send-after-reopen", "after-a-cut", "after-a",
                                            "replay-b", "after-b",
                                            "recover-denied", "recover", "after-recovery",
                                            "race-start-a", "race-start-b",
                                            *(f"poll-{index}" for index in range(1, 7)), "accept",
                                            "accept-replay", "completed-resume", "readback",
                                            "ambiguous-replay", "governance-first", "governance-repeat",
                                            "provider-stage", "provider-first", "provider-repeat",
                                            "preflight-stage", "preflight-first", "preflight-repeat"))
    parser.add_argument("--endpoint")
    args = parser.parse_args()
    if args.source_revision is not None and (
        len(args.source_revision) != 40 or any(character not in "0123456789abcdef" for character in args.source_revision)
    ):
        parser.error("source revision must be one exact Git commit SHA")
    root = args.output_dir.resolve()
    try:
        artifact = _installed_wheel(
            args.wheel.resolve(), source_revision=args.source_revision,
            verify_source=not bool(args.phase),
        )
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        if root.exists() and any(root.iterdir()):
            raise RuntimeError("qualification output directory must be fresh") from error
        root.mkdir(parents=True, exist_ok=True)
        report = {
            "qualification": "INSTALLED_FORGE_HTTP_SUCCESSOR_V1",
            "source_revision": args.source_revision, "result": "FAIL",
            "failure": {"stage": "installed_wheel_identity", "type": type(error).__name__},
        }
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 1
    if _run_preflight_child(args, parser, root):
        return 0
    if args.phase:
        if args.phase.startswith("provider-"):
            if not args.provider_case or not args.endpoint or args.scenario or args.governance_case or args.preflight_case:
                parser.error("provider child phase requires one case and loopback endpoint")
            with _loopback_only():
                _provider_phase(root, args.provider_case, args.phase, args.endpoint)
            return 0
        if args.phase.startswith("governance-"):
            if not args.governance_case or not args.endpoint or args.scenario or args.preflight_case:
                parser.error("governance child phase requires case and loopback endpoint")
            with _loopback_only():
                _governance_phase(root, args.governance_case, args.phase, args.endpoint)
            return 0
        if not args.scenario or not args.endpoint or args.governance_case or args.preflight_case or args.provider_case:
            parser.error("child phase requires scenario and loopback endpoint")
        with _loopback_only():
            _phase(root, args.scenario, args.phase, args.endpoint)
        return 0
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("qualification output directory must be fresh")
    if sum(bool(value) for value in (args.governance_case, args.scenario,
                                     args.preflight_case, args.provider_case)) > 1:
        parser.error("focused qualification filters cannot be combined")
    root.mkdir(parents=True, exist_ok=True)
    try:
        producer_source = source_receipt()
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"qualification": "INSTALLED_FORGE_HTTP_SUCCESSOR_V1", "artifact": artifact,
                  "source_revision": args.source_revision, "result": "FAIL",
                  "failure": {"stage": "producer_fixture_source", "type": type(error).__name__}}
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 1
    scenarios = SCENARIOS if not args.scenario else (args.scenario,)
    report = {"qualification": "INSTALLED_FORGE_HTTP_SUCCESSOR_V1", "artifact": artifact,
              "source_revision": args.source_revision,
              "qualifier_sha256": "sha256:" + sha256(Path(__file__).read_bytes()).hexdigest(),
              "producer_fixture_source": producer_source,
              "ep_preflight_source": EP_PREFLIGHT_SOURCE,
              "ep_identity_readback_source": EP_IDENTITY_READBACK_SOURCE,
              "required_producer_fixture_negatives": [
                  "missing-provenance", "changed-provenance", "wrong-version", "changed-digest",
                  "foreign-project", "foreign-repository", "foreign-submission", "foreign-run",
                  "unexpected-field", "missing-field", "queued-operation", "queued-reason",
                  "queued-submission-state",
                  "terminal-run-state", "terminal-delivery-qualified", "changed-artifact-bytes",
                  "artifact-unexpected-field", "artifact-missing-field", "artifact-foreign-run",
                  "artifact-run-timing", "artifact-host-null", "artifact-host-empty",
                  "artifact-host-commit", "artifact-host-digest", "artifact-requested-revision",
                  "artifact-delivery-revision", "artifact-baseline-transition", "artifact-report-id",
              ],
              "ep_simulator_contract": SIMULATOR_CONTRACT_VERSION,
              "required_preflight_cases": list(PREFLIGHT_CASES),
              "required_governance_cases": list(GOVERNANCE_CASES),
              "required_provider_cases": list(PROVIDER_CASES),
              "required_installed_identity_negative": "installed-wheel-byte-drift",
              "required_runtime_storage_negatives": ["wrong-runtime-marker", "missing-runtime-storage"],
              "required_http_scenarios": list(SCENARIOS),
              "test_doubles": ["stateful-loopback-EP-HTTP-simulator",
                               "deterministic-external-Codex-process-transport",
                               "synthetic-operator-identity", "synthetic-secure-store-resolver",
                               "immutable-synthetic-repository-artifact-reader"],
              "limitations": ["Synthetic Business/Architecture actors and repository JSON; deterministic external Codex transport.",
                              "Local EP HTTP simulator only; no live EP/provider or production Mission claim.",
                              "EP v1.3 identity readback recovers accepted lost-ack submissions; v1.2-only hosts fail closed.",
                              "EP producer v1.2 schema omits two retry-resolution fields emitted by its source; this subset validates source shape, not full schema conformance.",
                              "Bounded serial write-mode subset; not full FCI-CI or FCO."]}
    if not any((args.scenario, args.preflight_case, args.governance_case, args.provider_case)):
        try:
            report["installed_identity_negative"] = _installed_identity_negative(
                root / "installed-identity-negative", args.wheel.resolve(),
            )
            report["runtime_storage_negatives"] = _installed_runtime_storage_negatives(
                root / "runtime-storage-negative",
            )
        except Exception as error:
            report.update(result="FAIL", failure={
                "stage": "installed_identity_negative", "type": type(error).__name__,
            })
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    preflight_cases = ()
    if args.preflight_case:
        preflight_cases = (args.preflight_case,)
    elif not args.governance_case and not args.scenario and not args.provider_case:
        preflight_cases = PREFLIGHT_CASES
    preflight = []
    for case in preflight_cases:
        try:
            preflight.append(_with_case_cleanup(
                root / "preflight-matrix" / case, _preflight_case, case, args.wheel.resolve(),
            ))
        except Exception as error:
            report.update(result="FAIL", preflight_matrix=preflight,
                          failure={"preflight_case": case, "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report["preflight_matrix"] = preflight
    if args.preflight_case:
        report["result"] = "FOCUSED_PASS"
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 0
    governance_cases = ()
    if args.governance_case:
        governance_cases = (args.governance_case,)
    elif not args.scenario and not args.provider_case:
        governance_cases = GOVERNANCE_CASES
    governance = []
    for case in governance_cases:
        try:
            governance.append(_with_case_cleanup(
                root / "governance-matrix" / case, _governance_case, case, args.wheel.resolve(),
            ))
        except Exception as error:
            report.update(result="FAIL", governance_matrix=governance,
                          failure={"governance_case": case, "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report["governance_matrix"] = governance
    if args.governance_case:
        report["result"] = "FOCUSED_PASS"
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 0
    provider_cases = (args.provider_case,) if args.provider_case else (
        PROVIDER_CASES if not args.scenario else ()
    )
    provider_results = []
    for case in provider_cases:
        try:
            provider_results.append(_with_case_cleanup(
                root / "provider-matrix" / case, _provider_case, case, args.wheel.resolve(),
            ))
        except Exception as error:
            report.update(result="FAIL", provider_matrix=provider_results,
                          failure={"provider_case": case, "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report["provider_matrix"] = provider_results
    if args.provider_case:
        report["result"] = "FOCUSED_PASS"
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 0
    summaries = []
    for scenario in scenarios:
        try:
            if scenario == "concurrent-start":
                summaries.append(_with_case_cleanup(
                    root / scenario, _concurrent_start_case, args.wheel.resolve(),
                ))
            else:
                summaries.append(_with_case_cleanup(
                    root / scenario, _scenario, scenario, args.wheel.resolve(),
                ))
        except Exception as error:
            report.update(result="FAIL", scenarios=summaries,
                          failure={"scenario": scenario, "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    if not args.scenario:
        observed = [item["case"] for item in summaries[0]["producer_fixture_negatives"]]
        if observed != report["required_producer_fixture_negatives"]:
            report.update(result="FAIL", scenarios=summaries,
                          failure={"type": "ProducerFixtureMatrixIncomplete"})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report.update(result=("FOCUSED_PASS" if args.scenario else "PASS"), scenarios=summaries)
    fixture._write(root / "installed-http-successor.public.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
