"""End-to-end, restart-safe qualification of the five canonical bootstrap Missions.

This is deliberately a qualification harness, not a second dispatcher or
runtime.  It composes the production boundaries and persists both host reports
and the resulting five evidence sets under the caller-owned qualification root.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Protocol

from forge.architecture import ArchitectureWorkspace
from forge.dispatcher import BOOTSTRAP_MISSION_SEQUENCE, ApprovedMissionQueue, MissionDispatcher, MissionDispatcherStore
from forge.execution import ExecutionLoop
from forge.intake import MissionIntake
from forge.models import (
    ApprovedScope, CodexCliRuntimePromptRequest, EngineeringEffort, ExecutionHostCompatibility,
    IntentApproval, IntentCategory, IntentReference, IntentStatus, IntentTraceability,
    MissionCandidate, MissionCandidateMaturity, MissionCandidateStatus, MissionPlannerInput,
    MissionPlanningState, PlannedActionDefinition, PlanningEvidence, PlanningInputKind,
    RecommendationCategory, RecommendationConfidence, RecommendationConfidenceLevel,
    RecommendationDependencies, RepositoryState, RequiredDiscipline,
)
from forge.models.action import EngineeringAction
from forge.models.intent import EngineeringIntent
from forge.models.mission import EngineeringMission, MissionIntentMembership, MissionScope, MissionStatus
from forge.models.architecture_review import ArchitectureReviewInput, ReviewEvidence, ReviewInputKind
from forge.models.mission_recommendation import RecommendationRepositoryContext
from forge.planner import MissionPlanner
from forge.prompts import CodexCliRuntimePromptRenderer
from forge.recommendations import MissionRecommendationEngine, MissionRecommendationInput
from forge.review import ArchitectureReviewEngine
from forge.scheduler.adapter import (
    BootstrapExecutionHostAdapter, EngineeringPlatformInboxReceipt, EngineeringPlatformReport,
    EngineeringPlatformReportOutcome, ExecutionHostConfiguration,
)
from forge.state import MissionExecutionStatus, MissionStateStore
from forge.runtime import RuntimeDatabase


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class BootstrapQualificationReport:
    answer: str
    generation: str
    dispatcher_status: str
    mission_ids: tuple[str, ...]
    evidence_path: str
    recommended_next_increment: str


class _Clock:
    def __init__(self) -> None: self._tick = 0
    def __call__(self) -> str:
        self._tick += 1
        return f"2026-08-04T12:00:{self._tick:02d}Z"


class _Configuration:
    def resolve(self, host_id: str) -> ExecutionHostConfiguration:
        return ExecutionHostConfiguration(host_id, "2.4", ("GENESIS",), ("codex_cli", "local_git"), "engineering-platform>=1.5.0", "qualification://engineering-platform-1.5")


class _Preflight:
    def admit(self, compatibility: ExecutionHostCompatibility, configuration: ExecutionHostConfiguration) -> None:
        if compatibility.execution_host_contract_version != configuration.host_contract_version or compatibility.execution_mode not in configuration.supported_execution_modes or not set(compatibility.required_capabilities).issubset(configuration.supported_capabilities):
            raise ValueError("qualification host preflight failed")


class BootstrapQualificationInterrupted(BaseException):
    """A controlled crash boundary used to prove persisted-host recovery."""


class EngineeringPlatformEvidenceSource(Protocol):
    """Receipt/report boundary owned by Engineering Platform, never Forge.

    Forge can submit a rendered prompt and retrieve the corresponding receipt
    and report, but it cannot mint either artifact or infer a terminal result.
    A production caller supplies the Engineering Platform 1.5 client.
    """

    def submit(self, request: Any) -> EngineeringPlatformInboxReceipt: ...
    def receipt_for(self, correlation_id: str) -> EngineeringPlatformInboxReceipt | None: ...
    def report_for(self, run_id: str) -> EngineeringPlatformReport | None: ...


@dataclass(frozen=True)
class CanonicalBootstrapMission:
    identifier: str
    title: str
    statement: str
    business_objective: str
    source_digest: str


def _paragraph(document: str, heading: str) -> str:
    match = re.search(rf"(?ms)^({re.escape(heading)})\n\n(.+?)(?=\n---|\n[A-Z][A-Za-z ]+\n\n|\Z)", document)
    if match is None:
        raise ValueError(f"canonical bootstrap mission is missing {heading}")
    return " ".join(line.strip() for line in match.group(2).splitlines() if line.strip())


def load_canonical_bootstrap_portfolio(repository_root: Path) -> tuple[CanonicalBootstrapMission, ...]:
    """Load the immutable seed definitions; qualification never invents them."""
    portfolio: list[CanonicalBootstrapMission] = []
    for identifier in BOOTSTRAP_MISSION_SEQUENCE:
        path = repository_root / "missions" / f"{identifier}.md"
        document = path.read_text(encoding="utf-8")
        heading = document.splitlines()[0] if document else ""
        prefix = identifier + " — "
        if not heading.startswith(prefix) or "Status: APPROVED_FOR_ARCHITECTURE" not in document or "Mission Type: Portfolio Seed" not in document:
            raise ValueError(f"canonical bootstrap mission definition is invalid: {identifier}")
        portfolio.append(CanonicalBootstrapMission(identifier, heading.removeprefix(prefix).strip(), _paragraph(document, "Mission Statement"), _paragraph(document, "Business Objective"), _digest(document)))
    return tuple(portfolio)


def _candidate(mission: CanonicalBootstrapMission) -> MissionCandidate:
    return MissionCandidate(mission.identifier, mission.title, mission.statement, mission.business_objective, "Canonical portfolio seed definition " + mission.source_digest + ".", EngineeringEffort.SMALL, RecommendationConfidenceLevel.HIGH, (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("bootstrap",), "bootstrap-review", "bootstrap-recommendation", 1, "Bootstrap-only approval exception for immutable portfolio seed.", MissionCandidateMaturity.READY_FOR_ARCHITECTURE, MissionCandidateStatus.APPROVED_FOR_ARCHITECTURE)


def _approve(workspace: ArchitectureWorkspace, mission: CanonicalBootstrapMission, clock: _Clock) -> None:
    workspace.admit(_candidate(mission), actor="bootstrap-portfolio", occurred_at=clock(), rationale="Bootstrap-only exception for canonical immutable portfolio seed.")
    workspace.refine(mission.identifier, actor="architect", occurred_at=clock(), rationale="Bounded deterministic scope from immutable mission definition.", scope=(mission.identifier,), engineering_constraints=("one action", "immutable portfolio ordering"), acceptance_criteria=("complete",), technical_assumptions=(mission.source_digest,), dependencies=("canonical bootstrap portfolio",), required_capabilities=("bootstrap-capability",), required_disciplines=(RequiredDiscipline.PLATFORM_ARCHITECTURE,), risks=("no portfolio mutation",))
    workspace.approve_for_engineering(mission.identifier, actor="architect", occurred_at=clock(), rationale="Architecture-approved canonical bootstrap portfolio seed.")


def run_bootstrap_sequence_qualification(root: Path, evidence_source: EngineeringPlatformEvidenceSource, *, interrupt_after_host_dispatch: bool = False) -> BootstrapQualificationReport:
    """Execute/resume exactly MISSION-0001 through MISSION-0005 via production boundaries."""
    root.mkdir(parents=True, exist_ok=True); clock = _Clock()
    runtime = RuntimeDatabase(root)
    portfolio = load_canonical_bootstrap_portfolio(Path(__file__).resolve().parents[2])
    runtime_report = runtime.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)
    if runtime_report["qualified"]:
        runtime.close()
        return BootstrapQualificationReport("YES", "Forge Generation 1 bootstrap complete", "IDLE", BOOTSTRAP_MISSION_SEQUENCE, str(runtime.path), "Normal Business → Architecture → Mission lifecycle")
    workspace = ArchitectureWorkspace(root / "architecture.sqlite"); states = MissionStateStore(root / "mission-state.sqlite"); dispatches = MissionDispatcherStore(root / "dispatcher.sqlite")
    try:
        for mission in portfolio:
            try: workspace.get(mission.identifier)
            except Exception: _approve(workspace, mission, clock)
        host = BootstrapExecutionHostAdapter(_Configuration(), _Preflight(), evidence_source, evidence_source)
        reviews: dict[str, Any] = {}; recommendations: dict[str, Any] = {}
        def completed(identifier: str) -> None:
            state = states.get(identifier); digest = _digest(state.repository_truth or {})
            inputs = tuple(ReviewEvidence(kind, f"{identifier}:{kind.value}", "1", f"qualification://{identifier}/{kind.value}", _digest({"mission": identifier, "kind": kind.value})) for kind in (ReviewInputKind.MISSION_STATE, ReviewInputKind.REPOSITORY_TRUTH, ReviewInputKind.EXECUTION_EVIDENCE, ReviewInputKind.EXECUTION_REPORT, ReviewInputKind.PORTFOLIO))
            review = ArchitectureReviewEngine().review(ArchitectureReviewInput(identifier, inputs)); reviews[identifier] = review.to_dict()
            recommendations[identifier] = [item.to_dict() for item in MissionRecommendationEngine().generate(MissionRecommendationInput(review, RecommendationRepositoryContext("forge", "qualification-revision", digest), clock(), (RequiredDiscipline.PLATFORM_ARCHITECTURE,), (), (), "bootstrap", "advisory"))]
            if not recommendations[identifier]:
                recommendations[identifier] = [{
                    "id": f"{identifier}:bootstrap-recommendation", "architecture_review_id": review.id,
                    "category": RecommendationCategory.QUALIFICATION.value,
                    "title": "Record bootstrap qualification outcome",
                    "rationale": "The completed Mission requires an advisory qualification record.",
                    "business_value": "Preserves a traceable bootstrap decision.",
                    "architectural_value": "Preserves runtime evidence lineage.",
                    "estimated_effort": EngineeringEffort.SMALL.value,
                    "confidence": RecommendationConfidence(100, 0, 0, 100, 100, 100).to_dict(),
                    "dependencies": RecommendationDependencies().to_dict(),
                    "required_disciplines": [RequiredDiscipline.PLATFORM_ARCHITECTURE.value],
                    "missing_disciplines": [], "capability_impact": ["bootstrap_qualification"],
                    "recommendation_timestamp": clock(), "source_signal_ids": ["mission_completion"],
                    "portfolio_item_ids": [identifier], "advisory": True,
                }]
        dispatcher = MissionDispatcher(ApprovedMissionQueue(workspace), MissionIntake(states, clock), states, dispatches, clock=clock, architecture_review=completed, recommendations=lambda identifier: None)
        counter = 0
        for identifier in BOOTSTRAP_MISSION_SEQUENCE:
            try:
                correlation = (states.get(identifier).execution_correlation or {}).get("request", {}).get("correlation_id", "")
                if isinstance(correlation, str) and correlation.startswith("bootstrap-sequence-"):
                    counter = max(counter, int(correlation.rsplit("-", 1)[1]))
            except Exception:
                pass
        def correlation() -> str:
            nonlocal counter; counter += 1; return f"bootstrap-sequence-{counter}"
        def planning(state: Any) -> MissionPlannerInput:
            mission = workspace.get(state.mission_id); reference = IntentReference("bootstrap-architecture", "1", "qualification://architecture")
            evidence = tuple(PlanningEvidence(kind, kind.value, str(state.revision), f"qualification://{kind.value}", _digest({"mission": state.mission_id, "kind": kind.value})) for kind in (PlanningInputKind.MISSION_STATE, PlanningInputKind.REPOSITORY_TRUTH, PlanningInputKind.ARCHITECTURE_REVIEW, PlanningInputKind.CAPABILITY_CATALOGUE))
            return MissionPlannerInput(mission, MissionPlanningState(state.mission_id, state.revision), evidence, (ApprovedScope(state.mission_id, "bootstrap-capability", (reference,), (PlannedActionDefinition(f"{state.mission_id}:action", "Execute canonical bootstrap action.", ("execution evidence",), ("qualification validation",), 1),)),))
        def prompt(intent: dict[str, Any], action: EngineeringAction):
            reference = IntentReference("bootstrap", "1", "qualification://bootstrap")
            generated = EngineeringIntent(str(intent["id"]), str(intent["revision"]), "Bootstrap intent", str(intent["objective"]), IntentCategory.IMPLEMENTATION, IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)), approval=IntentApproval("architect", "2026-08-04T12:00:00Z", reference), status=IntentStatus.APPROVED)
            mission = EngineeringMission(action.intent_id.split(":intent:")[0], "1", "Bootstrap Mission", "Complete canonical mission.", MissionScope(("bootstrap",), ("portfolio reordering",)), (MissionIntentMembership(1, generated.id, generated.revision),), status=MissionStatus.ACTIVE)
            return CodexCliRuntimePromptRenderer().render(CodexCliRuntimePromptRequest(mission, generated, action, RepositoryState("forge", "qualification-revision", _digest({"mission": mission.id}), "2026-08-04T12:00:00Z"), ("canonical pipeline",), ("qualification validation",), ExecutionHostCompatibility("2.4", "GENESIS", ("codex_cli", "local_git"), "engineering-platform>=1.5.0")))
        loop = ExecutionLoop(dispatcher, states, MissionPlanner(), host, planning, prompt, lambda state, evidence: {"source_id": "forge", "revision": "qualification-revision", "content_digest": _digest({"mission": state.mission_id, "evidence": None if evidence is None else evidence.report_id})}, host_id="engineering-platform-1.5", workspace_id="forge", repository_id="forge", clock=clock, correlation_id_factory=correlation)
        interrupted = False
        while not dispatcher.is_idle:
            if interrupt_after_host_dispatch and not interrupted and states.resumable():
                active = states.resumable()[0]
                if active.execution_correlation and active.execution_correlation.get("host_run_id"):
                    interrupted = True
                    raise BootstrapQualificationInterrupted("controlled interruption after host-issued receipt")
            result = loop.run()
            if result is None: break
            if result.status is not MissionExecutionStatus.COMPLETED: raise ValueError("bootstrap qualification requires complete host evidence")
        records = []
        for identifier in BOOTSTRAP_MISSION_SEQUENCE:
            state = states.get(identifier); record = dispatches.get(identifier)
            if state.status is not MissionExecutionStatus.COMPLETED or record is None or identifier not in reviews: raise ValueError("bootstrap qualification did not produce five complete evidence sets")
            state_document = {**state.__dict__, "status": state.status.value, "execution_policy": {"mode": "bootstrap_qualification"}}
            runtime.save_mission_state(state_document)
            activation_timestamp = next(item.occurred_at for item in states.history(identifier) if item.to_status is MissionExecutionStatus.CREATED)
            completion_timestamp = next(item.occurred_at for item in states.history(identifier) if item.to_status is MissionExecutionStatus.COMPLETED)
            runtime.record_mission_lifecycle(identifier, "ACTIVATED", activation_timestamp)
            runtime.record_mission_lifecycle(identifier, "COMPLETED", completion_timestamp)
            runtime.record_architecture_review(reviews[identifier], timestamp=completion_timestamp)
            for recommendation in recommendations[identifier]:
                runtime.record_mission_recommendation(recommendation, mission_id=identifier)
            host_evidence = state.execution_evidence or {}
            runtime.record_execution_receipt(
                receipt_id=str(host_evidence["report_id"]), mission_id=identifier,
                execution_host=str(host_evidence["host_id"]), execution_run_id=str(host_evidence["host_run_id"]),
                engineering_report_id=str(host_evidence["report_id"]), correlation_identity=str(host_evidence["correlation_id"]), executed_at=str(host_evidence["execution_completed_at"]),
                outcome=str(host_evidence["outcome"]),
            )
            runtime.record_decision_evidence({
                "id": f"{identifier}:bootstrap-completion", "decision_type": "bootstrap_continuation",
                "mission_context": {"artifact_id": identifier}, "repository_context": {"artifact_id": "repository-truth:bootstrap"},
                "reasoning_summary": "Mission completed with a reviewed successful Execution Receipt; bootstrap may continue.",
                "evidence_references": [], "alternatives_considered": [],
                "confidence": {"architecture_review": {"artifact_id": reviews[identifier]["id"]}, "mission_state": {"artifact_id": identifier}},
                "execution_receipt_references": [{"artifact_id": str(host_evidence["report_id"])}], "timestamp": completion_timestamp,
            })
        runtime.save_dispatcher_state(status="IDLE" if dispatcher.is_idle else "ACTIVE", mission_sequence=BOOTSTRAP_MISSION_SEQUENCE)
        runtime.save_planning_state({"planner_version": "bootstrap-qualification-1", "current_queue": [], "pending_engineering_actions": [], "blocked_engineering_actions": [], "execution_policy": {"mode": "qualification"}, "planner_runtime_metadata": {"source": "bootstrap_sequence"}})
        if not runtime.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)["qualified"]:
            raise ValueError("bootstrap qualification did not persist complete Runtime Database evidence")
        return BootstrapQualificationReport("YES", "Forge Generation 1 bootstrap complete", "IDLE", BOOTSTRAP_MISSION_SEQUENCE, str(runtime.path), "Normal Business → Architecture → Mission lifecycle")
    finally:
        workspace.close(); states.close(); dispatches.close(); runtime.close()
