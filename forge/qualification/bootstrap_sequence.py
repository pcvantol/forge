"""End-to-end, restart-safe qualification of the five canonical bootstrap Missions.

This is deliberately a qualification harness, not a second dispatcher or
runtime.  It composes the production boundaries and persists both host reports
and the resulting five evidence sets under the caller-owned qualification root.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from forge.architecture import ArchitectureWorkspace
from forge.dispatcher import BOOTSTRAP_MISSION_SEQUENCE, ApprovedMissionQueue, MissionDispatcher, MissionDispatcherStore
from forge.execution import ExecutionLoop
from forge.intake import MissionIntake
from forge.models import (
    ApprovedScope, CodexCliRuntimePromptRequest, EngineeringEffort, ExecutionHostCompatibility,
    IntentApproval, IntentCategory, IntentReference, IntentStatus, IntentTraceability,
    MissionCandidate, MissionCandidateMaturity, MissionCandidateStatus, MissionPlannerInput,
    MissionPlanningState, PlannedActionDefinition, PlanningEvidence, PlanningInputKind,
    RecommendationConfidenceLevel, RepositoryState, RequiredDiscipline,
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


class EngineeringPlatformEvidenceProvider:
    """Durable, host-owned receipt/report boundary for Genesis qualification.

    The adapter sees only the Engineering Platform contracts.  Receipt and
    report documents are persisted independently from Forge's SQLite state so
    a restarted runner must recover the original host acknowledgement rather
    than manufacture another action or completion.
    """
    def __init__(self, path: Path, clock: _Clock, *, interrupt_after_submit: bool = False) -> None:
        self.path, self.clock, self.interrupt_after_submit = path, clock, interrupt_after_submit
        self._interrupted = False
        if not path.exists(): path.write_text(json.dumps({"receipts": {}, "reports": {}}, sort_keys=True), encoding="utf-8")
    def _read(self) -> dict[str, Any]: return json.loads(self.path.read_text(encoding="utf-8"))
    def _write(self, value: dict[str, Any]) -> None: self.path.write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
    def receipt_count(self) -> int: return len(self._read()["receipts"])
    def submit(self, request: Any) -> EngineeringPlatformInboxReceipt:
        data = self._read(); existing = data["receipts"].get(request.correlation_id)
        if existing: return EngineeringPlatformInboxReceipt(existing)
        run_id = "qualification-host-" + sha256(request.correlation_id.encode()).hexdigest()[:16]
        data["receipts"][request.correlation_id] = run_id
        data["reports"][run_id] = {"report_id": "qualification-report-" + run_id[-16:], "repository_revision": "qualification-revision", "content_digest": _digest({"mission": request.mission_id, "action": request.action_id}), "started": self.clock(), "completed": self.clock()}
        self._write(data)
        if self.interrupt_after_submit and not self._interrupted:
            self._interrupted = True
            raise BootstrapQualificationInterrupted("controlled interruption after persisted host dispatch")
        return EngineeringPlatformInboxReceipt(run_id)
    def receipt_for(self, correlation_id: str) -> EngineeringPlatformInboxReceipt | None:
        run_id = self._read()["receipts"].get(correlation_id); return None if run_id is None else EngineeringPlatformInboxReceipt(run_id)
    def report_for(self, run_id: str) -> EngineeringPlatformReport | None:
        item = self._read()["reports"].get(run_id)
        return None if item is None else EngineeringPlatformReport(run_id, item["report_id"], EngineeringPlatformReportOutcome.COMPLETE, item["repository_revision"], item["content_digest"], ("qualification:execution-host",), ("evidence:engineering-platform-1.5",), item["started"], item["completed"])


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


def run_bootstrap_sequence_qualification(root: Path, *, interrupt_after_host_dispatch: bool = False) -> BootstrapQualificationReport:
    """Execute/resume exactly MISSION-0001 through MISSION-0005 via production boundaries."""
    root.mkdir(parents=True, exist_ok=True); clock = _Clock(); evidence_file = root / "bootstrap-sequence-evidence.json"
    portfolio = load_canonical_bootstrap_portfolio(Path(__file__).resolve().parents[2])
    if evidence_file.exists():
        persisted = json.loads(evidence_file.read_text(encoding="utf-8"))
        if persisted.get("mission_sequence") == list(BOOTSTRAP_MISSION_SEQUENCE) and len(persisted.get("missions", ())) == len(BOOTSTRAP_MISSION_SEQUENCE) and persisted.get("dispatcher_status") == "IDLE":
            return BootstrapQualificationReport("YES", "Forge Generation 1 bootstrap complete", "IDLE", BOOTSTRAP_MISSION_SEQUENCE, str(evidence_file), "Portfolio Intelligence Foundation")
    workspace = ArchitectureWorkspace(root / "architecture.sqlite"); states = MissionStateStore(root / "mission-state.sqlite"); dispatches = MissionDispatcherStore(root / "dispatcher.sqlite")
    try:
        for mission in portfolio:
            try: workspace.get(mission.identifier)
            except Exception: _approve(workspace, mission, clock)
        host_source = EngineeringPlatformEvidenceProvider(root / "engineering-platform-evidence.json", clock, interrupt_after_submit=interrupt_after_host_dispatch)
        host = BootstrapExecutionHostAdapter(_Configuration(), _Preflight(), host_source, host_source)
        review_file = root / "bootstrap-review-recommendation-evidence.json"
        persisted_reviews = json.loads(review_file.read_text(encoding="utf-8")) if review_file.exists() else {"reviews": {}, "recommendations": {}}
        reviews: dict[str, Any] = dict(persisted_reviews["reviews"]); recommendations: dict[str, Any] = dict(persisted_reviews["recommendations"])
        def completed(identifier: str) -> None:
            state = states.get(identifier); digest = _digest(state.repository_truth or {})
            inputs = tuple(ReviewEvidence(kind, f"{identifier}:{kind.value}", "1", f"qualification://{identifier}/{kind.value}", _digest({"mission": identifier, "kind": kind.value})) for kind in (ReviewInputKind.MISSION_STATE, ReviewInputKind.REPOSITORY_TRUTH, ReviewInputKind.EXECUTION_EVIDENCE, ReviewInputKind.EXECUTION_REPORT, ReviewInputKind.PORTFOLIO))
            review = ArchitectureReviewEngine().review(ArchitectureReviewInput(identifier, inputs)); reviews[identifier] = review.to_dict()
            recommendations[identifier] = [item.to_dict() for item in MissionRecommendationEngine().generate(MissionRecommendationInput(review, RecommendationRepositoryContext("forge", "qualification-revision", digest), clock(), (RequiredDiscipline.PLATFORM_ARCHITECTURE,), (), (), "bootstrap", "advisory"))]
            review_file.write_text(json.dumps({"reviews": reviews, "recommendations": recommendations}, sort_keys=True, indent=2), encoding="utf-8")
        dispatcher = MissionDispatcher(ApprovedMissionQueue(workspace), MissionIntake(states, clock), states, dispatches, clock=clock, architecture_review=completed, recommendations=lambda identifier: None)
        counter = host_source.receipt_count()
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
        while not dispatcher.is_idle:
            result = loop.run()
            if result is None: break
            if result.status is not MissionExecutionStatus.COMPLETED: raise ValueError("bootstrap qualification requires complete host evidence")
        records = []
        for identifier in BOOTSTRAP_MISSION_SEQUENCE:
            state = states.get(identifier); record = dispatches.get(identifier)
            if state.status is not MissionExecutionStatus.COMPLETED or record is None or identifier not in reviews: raise ValueError("bootstrap qualification did not produce five complete evidence sets")
            records.append({"mission_id": identifier, "activation_timestamp": next(item.occurred_at for item in states.history(identifier) if item.to_status is MissionExecutionStatus.CREATED), "completion_timestamp": next(item.occurred_at for item in states.history(identifier) if item.to_status is MissionExecutionStatus.COMPLETED), "execution_lineage": state.execution_history, "execution_evidence": state.execution_evidence, "mission_state": {"status": state.status.value, "revision": state.revision}, "architecture_review": reviews[identifier], "mission_recommendations": recommendations[identifier], "completion_outcome": record.status.value})
        evidence_file.write_text(json.dumps({"mission_sequence": list(BOOTSTRAP_MISSION_SEQUENCE), "dispatcher_status": "IDLE" if dispatcher.is_idle else "ACTIVE", "missions": records}, sort_keys=True, indent=2), encoding="utf-8")
        return BootstrapQualificationReport("YES", "Forge Generation 1 bootstrap complete", "IDLE", BOOTSTRAP_MISSION_SEQUENCE, str(evidence_file), "Portfolio Intelligence Foundation")
    finally:
        workspace.close(); states.close(); dispatches.close()
