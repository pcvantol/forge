"""Deterministic End-to-End Bootstrap Mission Canary qualification scenario."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forge.intake import MissionIntake
from forge.models import (
    CodexCliRuntimePromptRequest, EngineeringAction, EngineeringIntent,
    EngineeringActionStatus, ExecutionHostCompatibility, IntentApproval,
    IntentCategory, IntentReference, IntentStatus, IntentTraceability,
    RepositoryState,
)
from forge.models.execution_host import ExecutionEvidenceOutcome
from forge.models.mission import EngineeringMission, MissionIntentMembership, MissionScope, MissionStatus
from forge.prompts import CodexCliRuntimePromptRenderer
from forge.runtime import BootstrapMissionRunner, RuntimeDatabase
from forge.scheduler import BootstrapMissionScheduler
from forge.scheduler.adapter import (
    BootstrapExecutionHostAdapter, EngineeringPlatformInboxReceipt, EngineeringPlatformReport,
    EngineeringPlatformReportOutcome, ExecutionHostConfiguration,
)
from forge.state import MissionExecutionStatus, MissionStateStore


CANARY_MISSION_ID = "forge-bootstrap-mission-canary"
CANARY_INTENT_ID = "forge-bootstrap-mission-canary-intent"
CANARY_ACTION_ID = "forge-bootstrap-mission-canary-action"
CANARY_CORRELATION_ID = "forge-bootstrap-mission-canary-correlation"
CANARY_HOST_RUN_ID = "forge-bootstrap-mission-canary-host-run"


def _reference(name: str) -> IntentReference:
    return IntentReference(name, "1", f"local://{name}")


@dataclass(frozen=True)
class CanaryQualificationReport:
    answer: str
    mission_id: str
    intent_id: str
    action_id: str
    runtime_prompt_id: str
    execution_host_run_id: str
    correlation_id: str
    evidence_kinds: tuple[str, ...]
    admission_levels: tuple[str, ...]


class _Configuration:
    def resolve(self, host_id: str) -> ExecutionHostConfiguration:
        return ExecutionHostConfiguration(host_id, "2.4", ("GENESIS",), ("codex_cli", "local_git"),
                                          "engineering-platform>=1.5.0", "canary://engineering-platform-1.5")


class _Preflight:
    def __init__(self) -> None:
        self.levels: list[str] = []

    def admit(self, compatibility: ExecutionHostCompatibility, configuration: ExecutionHostConfiguration) -> None:
        if compatibility.execution_host_contract_version != configuration.host_contract_version:
            raise ValueError("Execution Host Preflight Level 1 failed")
        self.levels.append("execution_host_level_1")
        if compatibility.execution_mode not in configuration.supported_execution_modes:
            raise ValueError("Workspace Preflight Level 2 failed")
        self.levels.append("workspace_level_2")
        if not set(compatibility.required_capabilities).issubset(configuration.supported_capabilities):
            raise ValueError("Capability Preflight Level 3 failed")
        self.levels.append("capability_level_3")


class _Inbox:
    def __init__(self) -> None:
        self.request = None

    def submit(self, request: object) -> EngineeringPlatformInboxReceipt:
        self.request = request
        return EngineeringPlatformInboxReceipt(CANARY_HOST_RUN_ID, "forge-bootstrap-mission-canary-receipt", "engineering-platform-1.5", "2026-08-03T23:30:00Z")

    def receipt_for(self, correlation_id: str) -> EngineeringPlatformInboxReceipt | None:
        return EngineeringPlatformInboxReceipt(CANARY_HOST_RUN_ID, "forge-bootstrap-mission-canary-receipt", "engineering-platform-1.5", "2026-08-03T23:30:00Z") if self.request and correlation_id == CANARY_CORRELATION_ID else None


class _Reports:
    def __init__(self, inbox: _Inbox) -> None: self._inbox = inbox

    def report_for(self, run_id: str) -> EngineeringPlatformReport | None:
        request = self._inbox.request
        if run_id != CANARY_HOST_RUN_ID or request is None:
            return None
        return EngineeringPlatformReport(CANARY_HOST_RUN_ID, "forge-bootstrap-mission-canary-report",
            EngineeringPlatformReportOutcome.COMPLETE, "canary-repository-revision", "sha256:" + "c" * 64,
            ("validation:bootstrap-mission-canary",), ("evidence:engineering-platform-1.5",),
            "2026-08-03T23:30:00Z", "2026-08-03T23:31:00Z", "forge-bootstrap-mission-canary-receipt",
            request.execution_host_id, request.correlation_id, request.runtime_prompt_id, request.mission_id,
            request.intent_id, request.intent_revision, request.action_id, execution_duration_ms=60_000)


def run_bootstrap_mission_canary(state_path: Path) -> CanaryQualificationReport:
    """Run the complete adapter pipeline once with deterministic host evidence."""
    reference = _reference("canary-approval")
    intent = EngineeringIntent(CANARY_INTENT_ID, "1", "Bootstrap Mission Canary Intent", "Qualify the pipeline.",
        IntentCategory.IMPLEMENTATION, IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)),
        approval=IntentApproval("architecture", "2026-08-03T23:29:00Z", reference), status=IntentStatus.APPROVED)
    mission = EngineeringMission(CANARY_MISSION_ID, "1", "Bootstrap Mission Canary", "Qualify one bounded Mission.",
        MissionScope(("one deterministic execution",), ("continuous execution",)),
        (MissionIntentMembership(1, intent.id, intent.revision),), status=MissionStatus.ACTIVE)
    action = EngineeringAction(1, CANARY_ACTION_ID, intent.id, intent.revision, "Execute the one qualified canary Action.",
        ("repository evidence",), status=EngineeringActionStatus.READY)
    preflight, inbox = _Preflight(), _Inbox()
    adapter = BootstrapExecutionHostAdapter(_Configuration(), preflight, inbox, _Reports(inbox))
    with MissionStateStore(RuntimeDatabase(state_path.parent)) as store:
        intake = MissionIntake(store, lambda: "2026-08-03T23:29:30Z")
        intake.admit(mission, (intent,), (action,))
        def render(_intent: object, active: EngineeringAction):
            return CodexCliRuntimePromptRenderer().render(CodexCliRuntimePromptRequest(
                mission, intent, active, RepositoryState("forge", "canary-repository-revision", "sha256:" + "c" * 64, "2026-08-03T23:29:30Z"),
                ("one action only",), ("bootstrap canary validation",),
                ExecutionHostCompatibility("2.4", "GENESIS", ("codex_cli", "local_git"), "engineering-platform>=1.5.0"),
            ))
        runner = BootstrapMissionRunner(store, BootstrapMissionScheduler(), adapter, render, host_id="engineering-platform-1.5",
            workspace_id="forge", repository_id="forge", clock=lambda: "2026-08-03T23:29:30Z",
            correlation_id_factory=lambda: CANARY_CORRELATION_ID)
        # Intake owns state creation; the Runner advances that same durable state.
        result = runner.run(CANARY_MISSION_ID)
        if result.status is not MissionExecutionStatus.COMPLETED:
            raise ValueError("Bootstrap Mission Canary did not complete")
        request = result.execution_correlation["request"]
        evidence = result.execution_evidence
        assert evidence is not None
        return CanaryQualificationReport("YES", mission.id, intent.id, action.id, request["runtime_prompt"]["id"],
            result.execution_correlation["host_run_id"], request["correlation_id"],
            ("execution_host", "engineering", "repository", "validation", "mission_completion"), tuple(preflight.levels))
