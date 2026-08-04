"""Contract-bound, deterministic Bootstrap Mission Scheduler regression tests."""

from __future__ import annotations

from dataclasses import replace
import unittest

from forge.models import (
    EngineeringAction, EngineeringActionStatus, ExecutionDispatch, ExecutionEvidenceOutcome,
    ExecutionHostEvidence, ExecutionRepositoryEvidence, ExecutionRequest, ProviderPromptDefinition,
    RuntimePrompt, RuntimePromptSection, RuntimePromptSectionKind,
)
from forge.scheduler import BootstrapMissionScheduler


def action(order: int, identifier: str, intent_id: str = "intent-1", dependencies: tuple[str, ...] = ()) -> EngineeringAction:
    return EngineeringAction(order, identifier, intent_id, "1", identifier, ("repository evidence",), dependencies)


def prompt(item: EngineeringAction) -> RuntimePrompt:
    return RuntimePrompt(
        f"prompt-{item.id}", item.intent_id, item.intent_revision, item.id,
        ProviderPromptDefinition("provider", "1"), "sha256:" + "b" * 64,
        tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind),
    )


def request(item: EngineeringAction, *, correlation: str = "correlation-1", retry_of: str | None = None) -> ExecutionRequest:
    return ExecutionRequest("fake-host", "mission-1", item.intent_id, item.intent_revision, item.id, prompt(item), "workspace-1", "forge", correlation, "2026-08-01T20:00:00Z", retry_of)


def evidence(dispatch: ExecutionDispatch, outcome: ExecutionEvidenceOutcome = ExecutionEvidenceOutcome.COMPLETE) -> ExecutionHostEvidence:
    item = dispatch.request
    repository = ExecutionRepositoryEvidence(item.mission_id, item.intent_id, item.intent_revision, item.action_id, item.runtime_prompt.id, item.correlation_id, dispatch.host_run_id, item.repository_id, "abc123", "report-1", "sha256:" + "a" * 64)
    return ExecutionHostEvidence(item.host_id, item.correlation_id, dispatch.host_run_id, "report-1", outcome, repository, retry_of_correlation_id=item.retry_of_correlation_id, execution_started_at="2026-08-04T10:00:00Z", execution_completed_at="2026-08-04T10:01:00Z", receipt_id="receipt-1", execution_duration_ms=60_000)


class FakeExecutionHost:
    """A deterministic provider-neutral host; it has no Bootstrap Platform knowledge."""

    def __init__(self, result: ExecutionHostEvidence | None = None) -> None:
        self.requests: list[ExecutionRequest] = []
        self.result = result

    def dispatch(self, item: ExecutionRequest) -> ExecutionDispatch:
        self.requests.append(item)
        return ExecutionDispatch(item, "fake-run-1")

    def retrieve_evidence(self, dispatch: ExecutionDispatch) -> ExecutionHostEvidence | None:
        return self.result


class BootstrapMissionSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = BootstrapMissionScheduler()

    def dispatched(self, actions: tuple[EngineeringAction, ...], *, correlation: str = "correlation-1", retry_of: str | None = None) -> tuple[tuple[EngineeringAction, ...], ExecutionDispatch, FakeExecutionHost]:
        active = self.scheduler.activate(actions)
        active_action = next(item for item in active if item.status is EngineeringActionStatus.ACTIVE)
        host = FakeExecutionHost()
        waiting, dispatch = self.scheduler.dispatch(active, request(active_action, correlation=correlation, retry_of=retry_of), host)
        return waiting, dispatch, host

    def test_scheduler_dispatches_through_fake_contract_host_without_bootstrap_platform(self) -> None:
        waiting, dispatch, host = self.dispatched((action(1, "one"),))
        self.assertEqual(waiting[0].status, EngineeringActionStatus.WAITING_FOR_RESULT)
        self.assertEqual(host.requests, [dispatch.request])

    def test_correct_run_bound_complete_advances_exactly_one_action(self) -> None:
        waiting, dispatch, host = self.dispatched((action(1, "one"), action(2, "two", dependencies=("one",))))
        host.result = evidence(dispatch)
        completed = self.scheduler.reconcile_from_host(waiting, dispatch, host)
        self.assertEqual(completed[0].status, EngineeringActionStatus.COMPLETE)
        self.assertEqual(completed[1].status, EngineeringActionStatus.READY)
        self.assertEqual(self.scheduler.next_action(completed).id, "two")

    def test_stale_or_unrelated_complete_evidence_is_rejected(self) -> None:
        waiting, dispatch, _ = self.dispatched((action(1, "one"),))
        item = evidence(dispatch)
        stale = replace(item, correlation_id="earlier-run", repository_evidence=replace(item.repository_evidence, correlation_id="earlier-run"))
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.scheduler.reconcile(waiting, dispatch, stale)
        unrelated = replace(evidence(dispatch), repository_evidence=replace(evidence(dispatch).repository_evidence, action_id="other"))
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.scheduler.reconcile(waiting, dispatch, unrelated)

    def test_blocked_and_failed_evidence_halt_mission_without_successor(self) -> None:
        for outcome, status in ((ExecutionEvidenceOutcome.BLOCKED, EngineeringActionStatus.BLOCKED), (ExecutionEvidenceOutcome.FAILED, EngineeringActionStatus.FAILED)):
            with self.subTest(outcome=outcome):
                waiting, dispatch, _ = self.dispatched((action(1, "one"), action(2, "two", dependencies=("one",))))
                stopped = self.scheduler.reconcile(waiting, dispatch, evidence(dispatch, outcome))
                self.assertEqual(stopped[0].status, status)
                self.assertIsNone(self.scheduler.next_action(stopped))

    def test_unknown_or_contradictory_terminal_evidence_fails_closed(self) -> None:
        waiting, dispatch, _ = self.dispatched((action(1, "one"),))
        unknown = replace(evidence(dispatch), outcome="unknown")
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.scheduler.reconcile(waiting, dispatch, unknown)  # type: ignore[arg-type]
        item = evidence(dispatch)
        contradictory = replace(item, host_run_id="other-run", repository_evidence=replace(item.repository_evidence, host_run_id="other-run"))
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.scheduler.reconcile(waiting, dispatch, contradictory)

    def test_actions_not_intents_are_released_and_intent_completion_is_action_derived(self) -> None:
        actions = (action(1, "one", "intent-1"), action(2, "two", "intent-1", ("one",)), action(3, "three", "intent-2", ("two",)))
        self.assertEqual(self.scheduler.next_action(actions).id, "one")
        waiting, dispatch, _ = self.dispatched(actions)
        first_complete = self.scheduler.reconcile(waiting, dispatch, evidence(dispatch))
        self.assertFalse(self.scheduler.intent_progress(first_complete)[0].is_complete)
        waiting, dispatch, _ = self.dispatched(first_complete)
        second_complete = self.scheduler.reconcile(waiting, dispatch, evidence(dispatch))
        self.assertTrue(self.scheduler.intent_progress(second_complete)[0].is_complete)
        self.assertFalse(self.scheduler.progress(second_complete).is_complete)

    def test_mission_completion_requires_all_intents_and_actions(self) -> None:
        actions = (action(1, "one", "intent-1"), action(2, "two", "intent-2", ("one",)))
        waiting, dispatch, _ = self.dispatched(actions)
        partial = self.scheduler.reconcile(waiting, dispatch, evidence(dispatch))
        self.assertFalse(self.scheduler.progress(partial).is_complete)
        waiting, dispatch, _ = self.dispatched(partial)
        complete = self.scheduler.reconcile(waiting, dispatch, evidence(dispatch))
        self.assertTrue(self.scheduler.progress(complete).is_complete)

    def test_retry_evidence_cannot_be_confused_with_original_run(self) -> None:
        waiting, dispatch, _ = self.dispatched((action(1, "one"),), correlation="retry-2", retry_of="original-1")
        item = evidence(dispatch)
        original = replace(item, correlation_id="original-1", retry_of_correlation_id=None, repository_evidence=replace(item.repository_evidence, correlation_id="original-1"))
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.scheduler.reconcile(waiting, dispatch, original)


if __name__ == "__main__":
    unittest.main()
