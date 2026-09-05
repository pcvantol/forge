"""Deterministic Bootstrap Mission Runner tests."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.models import (
    EngineeringAction, EngineeringIntent, EngineeringActionStatus, ExecutionDispatch, ExecutionRequest,
    ExecutionEvidenceOutcome, ExecutionHostEvidence, ExecutionRepositoryEvidence,
    IntentApproval, IntentCategory, IntentReference, IntentStatus, IntentTraceability, ProviderPromptDefinition,
    RuntimePrompt, RuntimePromptSection, RuntimePromptSectionKind,
)
from forge.models.mission import EngineeringMission, MissionIntentMembership, MissionScope
from forge.models.codex_runtime_prompt import CodexCliRuntimePromptRequest, ExecutionHostCompatibility, RepositoryState
from forge.prompts import CodexCliRuntimePromptRenderer
from forge.runtime import BootstrapMissionRunner, MissionRunnerError
from forge.scheduler import BootstrapMissionScheduler
from forge.state import MissionExecutionStatus, MissionStateStore
from forge.runtime import RuntimeDatabase


def intent(identifier: str) -> EngineeringIntent:
    reference = IntentReference("source", "1", "docs/source.md")
    return EngineeringIntent(identifier, "1", identifier, f"Complete {identifier}.", IntentCategory.IMPLEMENTATION,
                             IntentTraceability((reference,), (reference,), (reference,), (reference,), (reference,)))


def mission(*identifiers: str) -> EngineeringMission:
    return EngineeringMission("mission-1", "1", "Mission", "Complete actions.", MissionScope(("runner",), ("planner",)),
                              tuple(MissionIntentMembership(index, item, "1") for index, item in enumerate(identifiers, 1)))


def action(order: int, identifier: str, *, dependency: str | None = None) -> EngineeringAction:
    return EngineeringAction(order, identifier, identifier, "1", f"Run {identifier}.", ("repository evidence",),
                             () if dependency is None else (dependency,))


def prompt_factory(intent_document: object, item: EngineeringAction) -> RuntimePrompt:
    assert isinstance(intent_document, dict)
    return RuntimePrompt(
        f"prompt-{item.id}", item.intent_id, item.intent_revision, item.id,
        ProviderPromptDefinition("test", "1"), "sha256:" + "b" * 64,
        tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind),
    )


class Host:
    def __init__(self, outcomes: dict[str, ExecutionEvidenceOutcome] | None = None, *, dispatch_fails: bool = False) -> None:
        self.outcomes = outcomes or {}
        self.dispatch_fails = dispatch_fails
        self.dispatches: dict[str, ExecutionDispatch] = {}
        self.requests: list[str] = []

    def dispatch(self, request: object) -> ExecutionDispatch:
        if self.dispatch_fails:
            raise RuntimeError("host unavailable")
        assert hasattr(request, "correlation_id")
        self.requests.append(request.action_id)  # type: ignore[attr-defined]
        dispatch = ExecutionDispatch(request, f"run-{request.correlation_id}")  # type: ignore[arg-type,attr-defined]
        self.dispatches[request.correlation_id] = dispatch  # type: ignore[attr-defined]
        return dispatch

    def recover_dispatch(self, request: object) -> ExecutionDispatch | None:
        return self.dispatches.get(request.correlation_id)  # type: ignore[attr-defined]

    def retrieve_evidence(self, dispatch: ExecutionDispatch) -> ExecutionHostEvidence | None:
        outcome = self.outcomes.get(dispatch.request.action_id)
        if outcome is None:
            return None
        request = dispatch.request
        repository = ExecutionRepositoryEvidence(request.mission_id, request.intent_id, request.intent_revision,
                                                  request.action_id, request.runtime_prompt.id, request.correlation_id,
                                                  dispatch.host_run_id, request.repository_id, "abc123", f"report-{request.action_id}",
                                                  "sha256:" + "a" * 64)
        return ExecutionHostEvidence(request.host_id, request.correlation_id, dispatch.host_run_id,
                                     f"report-{request.action_id}", outcome, repository,
                                     execution_started_at="2026-08-04T10:00:00Z", execution_completed_at="2026-08-04T10:01:00Z",
                                     receipt_id=f"receipt-{request.action_id}", execution_duration_ms=60_000)


class BootstrapMissionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.runtime = RuntimeDatabase(Path(self.directory.name)); self.store = MissionStateStore(self.runtime)
        self.counter = 0

    def tearDown(self) -> None:
        self.runtime.close()
        self.directory.cleanup()

    def runner(self, host: Host) -> BootstrapMissionRunner:
        def correlation() -> str:
            self.counter += 1
            return f"correlation-{self.counter}"
        return BootstrapMissionRunner(self.store, BootstrapMissionScheduler(), host, prompt_factory,
                                      host_id="test-host", workspace_id="workspace-1", repository_id="forge",
                                      clock=lambda: "2026-08-01T20:00:00Z", correlation_id_factory=correlation)

    def test_start_persists_the_single_ready_mission(self) -> None:
        runner = self.runner(Host())
        state = runner.start(mission("one"), (intent("one"),), (action(1, "one"),))
        self.assertEqual(state.status, MissionExecutionStatus.READY)
        with self.assertRaisesRegex(MissionRunnerError, "exactly one"):
            runner.start(mission("two"), (intent("two"),), (action(1, "two"),))

    def test_successful_execution_loop_completes_sequential_actions(self) -> None:
        host = Host({"one": ExecutionEvidenceOutcome.COMPLETE, "two": ExecutionEvidenceOutcome.COMPLETE})
        runner = self.runner(host)
        runner.start(mission("one", "two"), (intent("one"), intent("two")), (action(1, "one"), action(2, "two", dependency="one")))
        state = runner.run("mission-1")
        self.assertEqual(state.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual([item["status"] for item in state.actions], ["COMPLETE", "COMPLETE"])
        self.assertEqual(host.requests, ["one", "two"])

    def test_blocked_execution_is_terminal(self) -> None:
        runner = self.runner(Host({"one": ExecutionEvidenceOutcome.BLOCKED}))
        runner.start(mission("one"), (intent("one"),), (action(1, "one"),))
        self.assertEqual(runner.run("mission-1").status, MissionExecutionStatus.BLOCKED)

    def test_failed_execution_is_terminal(self) -> None:
        runner = self.runner(Host({"one": ExecutionEvidenceOutcome.FAILED}))
        runner.start(mission("one"), (intent("one"),), (action(1, "one"),))
        self.assertEqual(runner.run("mission-1").status, MissionExecutionStatus.FAILED)

    def test_execution_host_failure_is_persisted_as_failed(self) -> None:
        runner = self.runner(Host(dispatch_fails=True))
        runner.start(mission("one"), (intent("one"),), (action(1, "one"),))
        state = runner.run("mission-1")
        self.assertEqual(state.status, MissionExecutionStatus.FAILED)
        self.assertEqual(state.execution_evidence["diagnostic_references"], ["runner:host_dispatch_failed"])  # type: ignore[index]

    def test_resume_after_restart_recovers_persisted_dispatch_without_regeneration(self) -> None:
        host = Host()
        first = self.runner(host)
        first.start(mission("one"), (intent("one"),), (action(1, "one"),))
        waiting = first.run("mission-1")
        self.assertEqual(waiting.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        self.store.close()
        self.store = MissionStateStore(self.runtime)
        host.outcomes["one"] = ExecutionEvidenceOutcome.COMPLETE
        resumed = self.runner(host).resume("mission-1")
        self.assertEqual(resumed.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual(host.requests, ["one"])

    def test_waiting_execution_resume_uses_durable_host_recovery(self) -> None:
        host = Host()
        runner = self.runner(host)
        runner.start(mission("one"), (intent("one"),), (action(1, "one"),))
        self.store.transition("mission-1", MissionExecutionStatus.ACTIVE, occurred_at="2026-08-01T20:00:00Z", reason="test")
        state = runner._release_action(self.store.get("mission-1"))  # noqa: SLF001
        request = state.execution_correlation["request"]  # type: ignore[index]
        dispatched = host.dispatch(runner._persisted_request(state))  # noqa: SLF001
        self.assertEqual(dispatched.request.correlation_id, request["correlation_id"])
        host.outcomes["one"] = ExecutionEvidenceOutcome.COMPLETE
        self.assertEqual(runner.resume("mission-1").status, MissionExecutionStatus.COMPLETED)
        self.assertEqual(host.requests, ["one"])

    def test_runtime_core_has_no_bootstrap_adapter_or_platform_dependency(self) -> None:
        source = (Path(__file__).parents[1] / "forge" / "runtime" / "runner.py").read_text()
        for forbidden in ("scheduler.adapter", "EngineeringPlatform", "Inbox", "iCloud", "launchd"):
            self.assertNotIn(forbidden, source)

    def test_persisted_codex_prompt_restores_its_type_and_retry_lineage(self) -> None:
        approved = EngineeringIntent(
            "one", "1", "one", "Complete one.", IntentCategory.IMPLEMENTATION, intent("one").traceability,
            approval=IntentApproval("architect", "now", IntentReference("approval", "1", "local://approval")),
            status=IntentStatus.APPROVED,
        )
        active = EngineeringAction(1, "one", "one", "1", "Run one.", ("repository evidence",), status=EngineeringActionStatus.ACTIVE)
        rendered = CodexCliRuntimePromptRenderer().render(CodexCliRuntimePromptRequest(
            EngineeringMission("mission-1", "1", "Mission", "Complete actions.", MissionScope(("runner",), ("planner",)), (MissionIntentMembership(1, "one", "1"),)),
            approved, active, RepositoryState("forge", "abc", "sha256:" + "a" * 64, "now"), ("bounded",), ("test",),
            ExecutionHostCompatibility("2.4", "GENESIS", ("codex_cli",), "platform>=1.5"),
        ))
        from forge.runtime.runner import _request, _request_document
        request = ExecutionRequest(
            "host", "mission-1", "one", "1", "one", rendered, "workspace", "forge", "retry-2", "now", "retry-1", "retry-1")
        restored = _request(_request_document(request))
        self.assertIsInstance(restored.runtime_prompt, type(rendered))
        self.assertEqual(restored.original_correlation_id, "retry-1")


if __name__ == "__main__":
    unittest.main()
