"""Regression coverage for the isolated Bootstrap Execution Host Adapter."""

from __future__ import annotations

import unittest

from forge.models import (
    CodexCliRuntimePromptRequest, EngineeringAction, EngineeringActionStatus,
    EngineeringIntent, ExecutionHostCompatibility, ExecutionRequest,
    IntentApproval, IntentCategory, IntentReference, IntentStatus,
    IntentTraceability, RepositoryState,
)
from forge.models.mission import EngineeringMission, MissionIntentMembership, MissionScope
from forge.prompts import CodexCliRuntimePromptRenderer
from forge.scheduler.adapter import (
    BootstrapExecutionHostAdapter, EngineeringPlatformInboxReceipt,
    EngineeringPlatformReport, EngineeringPlatformReportOutcome,
    ExecutionHostConfiguration,
)


def reference(identifier: str) -> IntentReference:
    return IntentReference(identifier, "1.0", f"local://{identifier}")


def runtime_prompt():
    intent = EngineeringIntent(
        "intent-1", "1.0", "Intent", "Bounded work.", IntentCategory.IMPLEMENTATION,
        IntentTraceability((reference("vision"),), (reference("architecture"),), (reference("roadmap"),),
                           (reference("proposal"),), (reference("repository"),)),
        approval=IntentApproval("architect", "2026-08-03T00:00:00Z", reference("approval")),
        status=IntentStatus.APPROVED,
    )
    mission = EngineeringMission("mission-1", "2.0", "Mission", "Preserve boundaries.",
                                 MissionScope(("adapter",), ("execution",)),
                                 (MissionIntentMembership(1, "intent-1", "1.0"),))
    action = EngineeringAction(1, "action-1", "intent-1", "1.0", "Translate only.",
                               ("clean repository commit",), status=EngineeringActionStatus.ACTIVE)
    return CodexCliRuntimePromptRenderer().render(CodexCliRuntimePromptRequest(
        mission, intent, action,
        RepositoryState("forge", "abc123", "sha256:" + "a" * 64, "2026-08-03T12:00:00Z"),
        ("No execution.", "No prompt mutation."), ("Run focused tests.",),
        ExecutionHostCompatibility("2.3", "GENESIS", ("codex_cli", "local_git"), "engineering-platform>=1.5.0"),
    ))


def request(**overrides: object) -> ExecutionRequest:
    values: dict[str, object] = {
        "host_id": "bootstrap-ep", "mission_id": "mission-1", "intent_id": "intent-1",
        "intent_revision": "1.0", "action_id": "action-1", "runtime_prompt": runtime_prompt(),
        "workspace_id": "workspace-1", "repository_id": "forge", "correlation_id": "correlation-1",
        "dispatched_at": "2026-08-03T12:01:00Z",
    }
    values.update(overrides)
    return ExecutionRequest(**values)  # type: ignore[arg-type]


class Resolver:
    def __init__(self) -> None:
        self.host_ids: list[str] = []

    def resolve(self, host_id: str) -> ExecutionHostConfiguration:
        self.host_ids.append(host_id)
        return ExecutionHostConfiguration(host_id, "2.3", ("GENESIS",), ("codex_cli", "local_git"),
                                          "engineering-platform>=1.5.0", "configured://inbox")


class Preflight:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls = []
        self.fail = fail

    def admit(self, compatibility: object, configuration: object) -> None:
        self.calls.append((compatibility, configuration))
        if self.fail:
            raise ValueError("admission denied")


class Inbox:
    def __init__(self) -> None:
        self.requests = []

    def submit(self, item: object) -> EngineeringPlatformInboxReceipt:
        self.requests.append(item)
        return EngineeringPlatformInboxReceipt("ep-run-1")

    def receipt_for(self, correlation_id: str) -> EngineeringPlatformInboxReceipt | None:
        if correlation_id != "correlation-1" or not self.requests:
            return None
        return EngineeringPlatformInboxReceipt("ep-run-1")


class Reports:
    def report_for(self, run_id: str) -> EngineeringPlatformReport | None:
        if run_id != "ep-run-1":
            return None
        return EngineeringPlatformReport(
            "ep-run-1", "ep-report-1", EngineeringPlatformReportOutcome.COMPLETE, "abc123",
            "sha256:" + "a" * 64, ("validation:focused",), ("diagnostic:none",),
            "2026-08-03T12:01:01Z", "2026-08-03T12:02:01Z",
        )


class BootstrapAdapterTests(unittest.TestCase):
    def adapter(self, inbox: Inbox, preflight: Preflight | None = None) -> BootstrapExecutionHostAdapter:
        return BootstrapExecutionHostAdapter(Resolver(), preflight or Preflight(), inbox, Reports())

    def test_translation_is_deterministic_and_preserves_every_identity(self) -> None:
        inbox = Inbox()
        dispatch = self.adapter(inbox).dispatch(request())
        transaction = inbox.requests[0]
        self.assertEqual(transaction.engineering_prompt, request().runtime_prompt.rendered_text)
        self.assertEqual((transaction.mission_id, transaction.intent_id, transaction.intent_revision, transaction.action_id),
                         ("mission-1", "intent-1", "1.0", "action-1"))
        self.assertEqual((transaction.correlation_id, transaction.original_correlation_id), ("correlation-1", "correlation-1"))
        self.assertEqual(transaction.inbox_location, "configured://inbox")
        self.assertEqual(dispatch.host_run_id, "ep-run-1")

    def test_preflight_precedes_inbox_acceptance(self) -> None:
        inbox = Inbox()
        with self.assertRaisesRegex(ValueError, "admission denied"):
            self.adapter(inbox, Preflight(fail=True)).dispatch(request())
        self.assertEqual(inbox.requests, [])

    def test_retry_creates_a_new_execution_and_preserves_lineage(self) -> None:
        inbox = Inbox()
        retry = request(correlation_id="correlation-2", retry_of_correlation_id="correlation-1",
                        original_correlation_id="correlation-1")
        self.adapter(inbox).dispatch(retry)
        transaction = inbox.requests[0]
        self.assertEqual((transaction.correlation_id, transaction.retry_of_correlation_id, transaction.original_correlation_id),
                         ("correlation-2", "correlation-1", "correlation-1"))

    def test_evidence_translation_is_canonical_and_hides_transport(self) -> None:
        inbox = Inbox()
        evidence = self.adapter(inbox).retrieve_evidence(self.adapter(inbox).dispatch(request()))
        assert evidence is not None
        self.assertEqual(evidence.repository_evidence.runtime_prompt_id, request().runtime_prompt.id)
        self.assertEqual(evidence.validation_references, ("validation:focused",))
        self.assertEqual(evidence.execution_completed_at, "2026-08-03T12:02:01Z")
        self.assertFalse(hasattr(evidence, "inbox_location"))

    def test_adapter_rejects_generic_prompts_and_core_has_no_platform_dependency(self) -> None:
        from forge.models import ProviderPromptDefinition, RuntimePrompt, RuntimePromptSection, RuntimePromptSectionKind
        generic = RuntimePrompt("prompt-1", "intent-1", "1.0", "action-1", ProviderPromptDefinition("provider", "1"),
                                "sha256:" + "b" * 64, tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind))
        with self.assertRaisesRegex(ValueError, "Codex CLI Runtime Prompt"):
            self.adapter(Inbox()).dispatch(request(runtime_prompt=generic))
        from pathlib import Path
        self.assertNotIn("EngineeringPlatform", Path("forge/runtime/runner.py").read_text())


if __name__ == "__main__":
    unittest.main()
