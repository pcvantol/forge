"""Bootstrap Adapter tests use an in-memory Engineering Platform Inbox."""

from __future__ import annotations

import unittest

from forge.models import EngineeringAction, EngineeringActionStatus
from forge.scheduler import BootstrapAdapter, BootstrapMissionScheduler, EngineeringPlatformReport, ReportOutcome, RepositoryEvidence
from forge.prompts import RuntimePromptGenerator
from test_runtime_prompt_generation import request


class Inbox:
    def __init__(self) -> None:
        self.prompts = []

    def submit(self, prompt: object) -> None:
        self.prompts.append(prompt)


class BootstrapAdapterTests(unittest.TestCase):
    def test_adapter_releases_one_active_action_and_reconciles_matching_evidence(self) -> None:
        scheduler = BootstrapMissionScheduler()
        actions = (EngineeringAction(1, "runtime-prompt-action", "runtime-prompt-intent", "1.0", "Objective", ("report",)),)
        active = scheduler.activate(actions)
        prompt = RuntimePromptGenerator().generate(prompt_id="prompt-1", request=request(action=active[0]))
        inbox = Inbox()
        waiting = BootstrapAdapter(inbox, scheduler).release(active, prompt)
        self.assertEqual(waiting[0].status, EngineeringActionStatus.WAITING_FOR_RESULT)
        completed = BootstrapAdapter(inbox, scheduler).reconcile(
            waiting, EngineeringPlatformReport("runtime-prompt-action", "report-1", ReportOutcome.COMPLETE),
            (RepositoryEvidence("runtime-prompt-action", "abc", "report-1", "sha256:" + "a" * 64),),
        )
        self.assertEqual(completed[0].status, EngineeringActionStatus.COMPLETE)
        self.assertEqual(len(inbox.prompts), 1)


if __name__ == "__main__":
    unittest.main()
