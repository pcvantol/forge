"""Bootstrap adapter tests keep Engineering Platform details outside scheduler core."""

from __future__ import annotations

import unittest

from forge.models import EngineeringAction, ExecutionRequest, ProviderPromptDefinition, RuntimePrompt, RuntimePromptSection, RuntimePromptSectionKind
from forge.scheduler.adapter import (
    BootstrapExecutionHostAdapter, EngineeringPlatformInboxReceipt, EngineeringPlatformReport,
    EngineeringPlatformReportOutcome,
)


def request() -> ExecutionRequest:
    action = EngineeringAction(1, "action-1", "intent-1", "1", "Objective", ("evidence",))
    prompt = RuntimePrompt("prompt-1", "intent-1", "1", "action-1", ProviderPromptDefinition("provider", "1"), "sha256:" + "b" * 64, tuple(RuntimePromptSection(kind, (kind.value,)) for kind in RuntimePromptSectionKind))
    return ExecutionRequest("bootstrap-ep", "mission-1", "intent-1", "1", "action-1", prompt, "workspace-1", "forge", "correlation-1", "2026-08-01T20:00:00Z")


class Inbox:
    def __init__(self) -> None:
        self.requests = []

    def submit(self, item: object) -> EngineeringPlatformInboxReceipt:
        self.requests.append(item)
        return EngineeringPlatformInboxReceipt("ep-run-1")


class Reports:
    def report_for(self, run_id: str) -> EngineeringPlatformReport | None:
        if run_id != "ep-run-1":
            return None
        return EngineeringPlatformReport("ep-run-1", "ep-report-1", EngineeringPlatformReportOutcome.COMPLETE, "abc123", "sha256:" + "a" * 64)


class BootstrapAdapterTests(unittest.TestCase):
    def test_adapter_translates_canonical_request_to_bootstrap_inbox_and_back(self) -> None:
        inbox = Inbox()
        adapter = BootstrapExecutionHostAdapter(inbox, Reports())
        dispatch = adapter.dispatch(request())
        self.assertEqual(inbox.requests[0].prompt.id, "prompt-1")
        self.assertEqual(inbox.requests[0].correlation_id, "correlation-1")
        evidence = adapter.retrieve_evidence(dispatch)
        assert evidence is not None
        self.assertEqual(evidence.host_run_id, "ep-run-1")
        self.assertEqual(evidence.repository_evidence.action_id, "action-1")


if __name__ == "__main__":
    unittest.main()
