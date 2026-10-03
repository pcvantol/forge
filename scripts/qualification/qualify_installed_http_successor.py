"""Qualify an installed Forge Mission's A -> HTTP EP -> evidence -> B loop.

Run this script with the Python 3.14 interpreter of a non-editable wheel
installation, away from the source checkout. Only the external Codex process,
credential resolver and immutable repository artifact reader are substituted.
The EP simulator speaks the real versioned HTTP boundary in the parent process.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock
from unittest.mock import patch

import forge
import forge.runtime.dynamic_mission as composition
from forge.ep_simulator import EpSimulatorScenario, EpSimulatorServer, EpSimulatorState, SIMULATOR_CONTRACT_VERSION
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
    rejection_matrix, source_receipt, validate_fixture,
)
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
                       runtime: InstalledDynamicMissionRuntime) -> tuple[
                           MissionCandidate, GovernedCandidateIntake,
                           ArchitectureMission, ArchitecturePlanningEvidence]:
    options = {"criterion_assessment_contracts": fixture._contracts(), "maximum_actions": 3,
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
    bridge = GovernedCandidateIntake(lifecycle, runtime, resolve_governance_profile("duo"))
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


def _prepare(root: Path, scenario: str, endpoint: str) -> None:
    _configure(root, endpoint)
    with ExitStack() as stack:
        runtime = _open(root, stack)
        with RecommendationLifecycleStore(root / "governance" / "lifecycle.sqlite") as lifecycle:
            candidate, bridge, mission_preview, planning = _candidate_fixture(lifecycle, runtime)
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
            bridge.approve_business(candidate.id, actor="business_owner",
                                    occurred_at="2026-09-18T09:59:02Z", rationale="Business value approved.",
                                    human_gates=planning.human_gates)
            reject_unapproved("missing-architecture", mission_preview)
            bridge.approve_architecture(candidate.id, mission_preview, planning,
                                        actor="platform_architect", occurred_at="2026-09-18T09:59:03Z",
                                        rationale="Exact technical contract approved.")
            reject_unapproved("changed-objective", replace(
                mission_preview, summary="Unapproved objective."))
            fixture._write(root / "governance-negative.private.json", {"rejected": rejected})
            admitted = bridge.admit(candidate.id, mission_preview, planning,
                                    occurred_at="2026-09-18T10:00:00Z")
        mission_id = admitted.mission_id
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


def _approve_business(bridge: GovernedCandidateIntake, candidate: MissionCandidate,
                      planning: ArchitecturePlanningEvidence) -> None:
    bridge.approve_business(candidate.id, actor="business_owner",
                            occurred_at="2026-09-18T09:59:02Z",
                            rationale="Synthetic Business approval.",
                            human_gates=planning.human_gates)


def _approve_architecture(bridge: GovernedCandidateIntake, candidate: MissionCandidate,
                          preview: ArchitectureMission,
                          planning: ArchitecturePlanningEvidence) -> None:
    bridge.approve_architecture(candidate.id, preview, planning,
                                actor="platform_architect", occurred_at="2026-09-18T09:59:03Z",
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
        role, target = (("business_owner", RecommendationStatus.BUSINESS_REJECTED)
                        if case == "rejected-business" else
                        ("platform_architect", RecommendationStatus.ARCHITECTURE_REJECTED))
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
                bridge = GovernedCandidateIntake(lifecycle, runtime, resolve_governance_profile("duo"))
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


def _run_governance_phase(root: Path, case: str, phase: str,
                          endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root),
               "--governance-case", case, "--phase", phase, "--endpoint", endpoint]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
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
                # Observe every HTTP method before route/auth checks; the simulator
                # audit only records accepted submissions and misses negative traffic.
                with request_lock:
                    requests.append(self.command)
            return parsed

    server.server.RequestHandlerClass = CountingHandler
    return requests


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
        fixture_receipts = []
        fixture_negatives = []
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
            return {**_ambiguous_result(root, simulator, server.base_url, wheel, initial),
                    "governance_rejections": governance_negative,
                    "producer_fixtures": fixture_receipts, "producer_fixture_negatives": fixture_negatives}
        simulator.complete(a, delivery_revision="a" * 40)
        source_readback, source_artifact = simulator.terminal_documents(a)
        fixture_receipts.append(validate_fixture(
            request_a, source_readback, source_artifact, project_id=PROJECT,
            repository_id=fixture.SOURCE.repository_id, submission_id=a,
        ))
        if scenario == "partial":
            fixture_negatives = rejection_matrix(
                request_a, source_readback, source_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=a,
            )
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
            "governance_rejections": governance_negative,
            "producer_fixtures": fixture_receipts,
            "producer_fixture_negatives": fixture_negatives,
            "phase_statuses": {phase: fixture._read(root / f"{phase}.state.private.json")["status"]
                               for phase in phases},
            "planner_invocations": len(fixture._read(root / "provider-inputs.private.json"))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--governance-case", choices=GOVERNANCE_CASES)
    parser.add_argument("--phase", choices=("prepare", "after-a", "replay-b", "after-b", "readback",
                                            "ambiguous-replay", "governance-first", "governance-repeat"))
    parser.add_argument("--endpoint")
    args = parser.parse_args()
    if args.source_revision is not None and (
        len(args.source_revision) != 40 or any(character not in "0123456789abcdef" for character in args.source_revision)
    ):
        parser.error("source revision must be one exact Git commit SHA")
    artifact = _installed_wheel(args.wheel.resolve())
    root = args.output_dir.resolve()
    if args.phase:
        if args.phase.startswith("governance-"):
            if not args.governance_case or not args.endpoint or args.scenario:
                parser.error("governance child phase requires case and loopback endpoint")
            _governance_phase(root, args.governance_case, args.phase, args.endpoint)
            return 0
        if not args.scenario or not args.endpoint or args.governance_case:
            parser.error("child phase requires scenario and loopback endpoint")
        _phase(root, args.scenario, args.phase, args.endpoint)
        return 0
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("qualification output directory must be fresh")
    if args.governance_case and args.scenario:
        parser.error("focused governance and HTTP scenario filters cannot be combined")
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
              "required_governance_cases": list(GOVERNANCE_CASES),
              "required_http_scenarios": list(SCENARIOS),
              "limitations": ["Synthetic Business/Architecture actors and repository JSON; deterministic external Codex transport.",
                              "Local EP HTTP simulator only; no live EP/provider or production Mission claim.",
                              "No EP correlation readback; ambiguous POST fails closed without recovery.",
                              "EP producer v1.2 schema omits two retry-resolution fields emitted by its source; this subset validates source shape, not full schema conformance.",
                              "Bounded serial write-mode subset; not full FCI-CI or FCO."]}
    governance = []
    for case in (GOVERNANCE_CASES if not args.governance_case else (args.governance_case,)):
        try:
            governance.append(_governance_case(root / "governance-matrix" / case, case, args.wheel.resolve()))
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
    if not args.scenario:
        observed = [item["case"] for item in summaries[0]["producer_fixture_negatives"]]
        if observed != report["required_producer_fixture_negatives"]:
            report.update(result="FAIL", scenarios=summaries,
                          failure={"type": "ProducerFixtureMatrixIncomplete"})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report.update(result="FOCUSED_PASS" if args.scenario else "PASS", scenarios=summaries)
    fixture._write(root / "installed-http-successor.public.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
