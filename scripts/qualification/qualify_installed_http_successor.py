"""Qualify an installed Forge Mission's A -> HTTP EP -> evidence -> B loop.

Run this script with the Python 3.14 interpreter of a non-editable wheel
installation, away from the source checkout. Only the external Codex process,
credential resolver and immutable repository artifact reader are substituted.
The EP simulator speaks the real versioned HTTP boundary in the parent process.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from hashlib import sha256
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import forge
import forge.runtime.dynamic_mission as composition
from forge.architecture import ArchitectureWorkspace
from forge.business import BusinessWorkspace
from forge.ep_simulator import EpSimulatorScenario, EpSimulatorServer, EpSimulatorState, SIMULATOR_CONTRACT_VERSION
from forge.execution_host_configuration import (
    EngineeringPlatformExecutionHostFactory, EngineeringPlatformPeerConfigurationService,
)
from forge.governance_authority import ArchitecturePlanningEvidence, MissionPlanningEvidenceEnvelope
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
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
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from forge.runtime import RuntimeBootstrap
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.secure_store import MacOSKeychainSecureStoreAdapter, SecretReference, SecretState


TOKEN = "isolated-qualification-token"
INSTANCE = "isolated-ep-simulator"
CONSUMER = "isolated-forge-consumer"
PROJECT = "isolated-project"
HOST = "synthetic-host"
SCENARIOS = ("partial", "single", "tampered", "ambiguous")


class _SyntheticCredentialResolver:
    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        assert reference.serialized == "keychain://synthetic/ep"
        return SecretState.RESOLVABLE, TOKEN


def _installed_wheel(wheel: Path) -> dict[str, str]:
    if sys.version_info[:2] != (3, 14) or not sys.flags.isolated or sys.flags.optimize:
        raise RuntimeError("qualification requires assertion-enabled isolated Python 3.14.x")
    if not wheel.is_file():
        raise RuntimeError("candidate wheel is missing")
    installed = distribution("forge-autonomy")
    direct = json.loads(installed.read_text("direct_url.json") or "{}")
    digest = sha256(wheel.read_bytes()).hexdigest()
    if (direct.get("archive_info", {}).get("hashes", {}).get("sha256") != digest
            or direct.get("dir_info", {}).get("editable")):
        raise RuntimeError("installed distribution is not the exact candidate wheel")
    package = Path(forge.__file__).resolve()
    if not package.is_relative_to(Path(installed.locate_file("forge")).resolve()):
        raise RuntimeError("Forge import did not come from installed site-packages")
    return {"version": installed.version, "wheel_sha256": "sha256:" + digest}


def _open(root: Path, stack: ExitStack) -> InstalledDynamicMissionRuntime:
    transport = fixture._CodexTransport(root)
    checker = CodexCliSessionReadinessChecker(runner=transport, path_usable=lambda _: True)
    stack.enter_context(patch.object(composition.MacOSGeneratedUIDIdentityAdapter, "resolve",
                                     return_value=fixture.IDENTITY))
    stack.enter_context(patch.object(composition, "CodexCliChatGPTSessionPlanningProvider",
        side_effect=lambda configuration: CodexCliChatGPTSessionPlanningProvider(
            configuration, runner=transport, readiness_checker=checker)))
    # The actual persisted-binding factory and HTTP adapter remain production code.
    stack.enter_context(patch.object(composition, "EngineeringPlatformExecutionHostFactory",
                                     lambda: EngineeringPlatformExecutionHostFactory(_SyntheticCredentialResolver())))
    stack.enter_context(patch("forge.completion.repository_observer.GitHubRepositoryArtifactReader.read",
        side_effect=lambda repository, revision, path: fixture._raw_reader(root, repository, revision, path)))
    return stack.enter_context(InstalledDynamicMissionRuntime.open(str(root / "runtime"), provider_id=fixture.PROVIDER))


def _prepare(root: Path, scenario: str, endpoint: str) -> None:
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
    with ExitStack() as stack:
        runtime = _open(root, stack)
        repository, context = runtime.repository, runtime.repository.operators.context()
        options = {"criterion_assessment_contracts": fixture._contracts(), "maximum_actions": 3,
                   "maximum_consecutive_no_progress_actions": 1,
                   "repository_evidence_source": fixture.SOURCE}
        planning = ArchitecturePlanningEvidence(
            ("synthetic-contract",), ("contracts",), ("no behavior claim",),
            ("scope-drift",), ("protected-delivery",), (HOST,), 40000, 8000, "1", **options,
        )
        BusinessWorkspace.for_runtime(runtime.database, repository, context).approve(
            decision_id="business", candidate_id="synthetic-candidate", revision="1",
            scope=planning.scope, gates=planning.human_gates,
        )
        ArchitectureWorkspace.for_runtime(runtime.database, repository, context).approve(
            decision_id="architecture", candidate_id="synthetic-candidate", revision="1", planning=planning,
        )
        envelope = MissionPlanningEvidenceEnvelope.compose(
            repository, subject_id="synthetic-candidate", subject_revision="1",
            business_decision_id="business", architecture_decision_id="architecture", planning=planning,
        )
        mission_id = runtime.database.allocate_next_mission_id(
            source="canonical-governance-envelope:" + envelope.digest,
            allocated_at="2026-09-18T10:00:00Z",
        )
        mission = ArchitectureMission(
            mission_id, "synthetic-candidate", "Synthetic export contract",
            "Publish two explicit JSON properties.", "Provide an inspectable contract.", "Inspectability.",
            "architecture", "synthetic-recommendation", ("synthetic-contract",),
            ("no behavior claim",), (fixture.K1, fixture.K2), ("external fixtures",),
            (HOST,), ("contract",), (RequiredDiscipline.PLATFORM_ARCHITECTURE,),
            ("scope-drift",), ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING, **options,
        )
        admitted = runtime.admit(mission, envelope)
        assert not admitted.actions
        initial = RepositoryTruthSnapshot(
            "initial", fixture.SOURCE.repository_id, "0" * 40, "2026-09-18T09:59:00Z",
            (RepositoryTruthEvidence("initial-revision", "git_commit", "0" * 40,
                "repository://synthetic/initial", fixture._digest("initial")),),
        )
        runtime.start(mission_id, initial)
        fixture._write(root / "population.private.json", {
            "mission_id": mission_id, "scenario": scenario,
            "runtime_id": runtime.database.runtime_identity.runtime_id,
        })
        _capture(root, runtime, "prepare")


def _capture(root: Path, runtime: InstalledDynamicMissionRuntime, phase: str) -> dict:
    mission_id = fixture._read(root / "population.private.json")["mission_id"]
    state = runtime.states._as_document(runtime.states.get(mission_id))
    fixture._write(root / f"{phase}.state.private.json", state)
    fixture._write(root / f"{phase}.process.private.json", {"pid": os.getpid()})
    return state


def _phase(root: Path, scenario: str, phase: str, endpoint: str) -> None:
    if phase == "prepare":
        _prepare(root, scenario, endpoint)
        return
    with ExitStack() as stack:
        runtime = _open(root, stack)
        mission_id = fixture._read(root / "population.private.json")["mission_id"]
        if phase != "readback":
            runtime.resume(mission_id)
        state = _capture(root, runtime, phase)
        admitted = fixture._read(root / "prepare.state.private.json")
        if state["mission"] != admitted["mission"] or state["admission_contract"] != admitted["admission_contract"]:
            raise RuntimeError("approved Mission or admission changed across processes")


def _run_phase(root: Path, scenario: str, phase: str, endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root), "--scenario", scenario,
               "--phase", phase, "--endpoint", endpoint]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed {scenario}/{phase} failed; see private phase log")
    return fixture._read(root / f"{phase}.state.private.json")


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
                  if scenario == "ambiguous" else None),
    )
    fixture._write(root / "artifact-a.json", {
        "report": {"fields": ["report_data"]},
        "policy": {"authorization_required": scenario == "single"},
    })
    fixture._write(root / "artifact-b.json", {
        "report": {"fields": ["report_data"]}, "policy": {"authorization_required": True},
    })
    with EpSimulatorServer(simulator) as server:
        initial = _run_phase(root, scenario, "prepare", server.base_url, wheel)
        assert len(initial["actions"]) == len(simulator.submission_ids()) == 1
        if scenario == "ambiguous":
            return _ambiguous_result(root, simulator, server.base_url, wheel, initial)
        a = simulator.submission_ids()[0]
        simulator.complete(a, delivery_revision="a" * 40)
        if scenario == "tampered":
            readback, artifact = simulator.terminal_documents(a)
            readback["correlation"]["mission_id"] = "wrong-mission"
            simulator.seed_terminal(a, readback, artifact)
        after_a = _run_phase(root, scenario, "after-a", server.base_url, wheel)
        if scenario == "partial":
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
            timeline = [(event["event"], event.get("submission_id")) for event in simulator.audit]
            assert timeline.index(("terminal_produced", a)) < timeline.index(("submission_accepted", b))
            simulator.complete(b, delivery_revision="b" * 40)
            final = _run_phase(root, scenario, "after-b", server.base_url, wheel)
            assert final["status"] == "COMPLETED" and len(final["actions"]) == 2
            assert all(item["status"] == "PROVEN" for item in final["completion"]["criteria"])
        elif scenario == "single":
            final = after_a
            assert final["status"] == "COMPLETED" and len(final["actions"]) == 1
            assert len(simulator.submission_ids()) == 1
        else:
            final = after_a
            assert len(final["actions"]) == len(simulator.submission_ids()) == 1
            assert final["status"] == "FAILED" and final["waiting_reason"] in {
                "host_dispatch_failed", "host_evidence_failed",
            }
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
        readback = _run_phase(root, scenario, "readback", server.base_url, wheel)
        assert readback == final
        assert not any(event["event"] == "submission_duplicate" for event in simulator.audit)
        accepted = [event["submission_id"] for event in simulator.audit if event["event"] == "submission_accepted"]
        assert accepted == list(simulator.submission_ids())
    phases = ["prepare", "after-a", "readback"]
    if scenario == "partial":
        phases += ["replay-b", "after-b"]
    processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
    assert len(processes) == len(phases), "Forge phases must use distinct OS processes"
    return {"scenario": scenario, "status": final["status"],
            "waiting_reason": final["waiting_reason"], "actions": len(final["actions"]),
            "submissions": len(simulator.submission_ids()), "forge_processes": len(processes),
            "phase_statuses": {phase: fixture._read(root / f"{phase}.state.private.json")["status"]
                               for phase in phases},
            "planner_invocations": len(fixture._read(root / "provider-inputs.private.json"))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--phase", choices=("prepare", "after-a", "replay-b", "after-b", "readback",
                                            "ambiguous-replay"))
    parser.add_argument("--endpoint")
    args = parser.parse_args()
    if args.source_revision is not None and (
        len(args.source_revision) != 40 or any(character not in "0123456789abcdef" for character in args.source_revision)
    ):
        parser.error("source revision must be one exact Git commit SHA")
    artifact = _installed_wheel(args.wheel.resolve())
    root = args.output_dir.resolve()
    if args.phase:
        if not args.scenario or not args.endpoint:
            parser.error("child phase requires scenario and loopback endpoint")
        _phase(root, args.scenario, args.phase, args.endpoint)
        return 0
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("qualification output directory must be fresh")
    root.mkdir(parents=True, exist_ok=True)
    scenarios = SCENARIOS if not args.scenario else (args.scenario,)
    report = {"qualification": "INSTALLED_FORGE_HTTP_SUCCESSOR_V1", "artifact": artifact,
              "source_revision": args.source_revision,
              "qualifier_sha256": "sha256:" + sha256(Path(__file__).read_bytes()).hexdigest(),
              "ep_simulator_contract": SIMULATOR_CONTRACT_VERSION,
              "limitations": ["Synthetic approvals and repository JSON, deterministic external Codex transport.",
                              "Local EP HTTP simulator only; no live EP/provider or production Mission claim.",
                              "No EP correlation readback; ambiguous POST fails closed without recovery.",
                              "Bounded serial write-mode subset; not full FCI-CI or FCO."]}
    summaries = []
    for scenario in scenarios:
        try:
            summaries.append(_scenario(root / scenario, scenario, args.wheel.resolve()))
        except Exception as error:
            report.update(result="FAIL", scenarios=summaries,
                          failure={"scenario": scenario, "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report.update(result="PASS", scenarios=summaries)
    fixture._write(root / "installed-http-successor.public.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
