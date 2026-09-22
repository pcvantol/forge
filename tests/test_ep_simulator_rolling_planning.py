from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.ep_simulator import EpSimulatorServer, EpSimulatorState
from forge.execution import ExecutionLoop
from forge.models import DerivationPolicy, RepositoryRevisionBinding
from forge.planner import AIMissionPlanner, MissionPlanner
from forge.runtime import RuntimeDatabase
from forge.scheduler.ep_http_adapter import EngineeringPlatformHttpConfiguration, EngineeringPlatformHttpExecutionHost
from forge.state import MissionExecutionStatus, MissionStateStore
from tests.criterion_fixture import seed_pending, terminal_completion
from tests.test_dynamic_mission_capability import (
    DerivationProvider,
    Dispatcher,
    DynamicMissionCapabilityTests,
    digest,
    mission,
    prompt,
)


class _CompletingHttpHost:
    """Complete each accepted simulator submission without bypassing HTTP."""

    def __init__(self, inner: EngineeringPlatformHttpExecutionHost, state: EpSimulatorState) -> None:
        self.inner = inner
        self.state = state
        self.config = inner.config
        self.completed_submissions: set[str] = set()

    def dispatch(self, request):
        dispatch = self.inner.dispatch(request)
        for submission_id in self.state.submission_ids():
            if submission_id not in self.completed_submissions:
                self.state.complete(submission_id)
                self.completed_submissions.add(submission_id)
        return dispatch

    def recover_dispatch(self, request):
        return self.inner.recover_dispatch(request)

    def retrieve_evidence(self, dispatch):
        return self.inner.retrieve_evidence(dispatch)


class EpSimulatorRollingPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.runtime = RuntimeDatabase(self.root)
        self.addCleanup(self.runtime.close)
        self.store = MissionStateStore(self.runtime)
        seed_pending(
            self.store, mission(), self._truth(None, None),
            occurred_at="2026-09-22T12:00:00Z",
        )
        self.dispatcher = Dispatcher()
        self.counter = 0
        self.state = EpSimulatorState(
            project_id="forge",
            repository_id="forge",
            repository_identity="pcvantol/forge",
            consumer_id="forge-consumer",
            instance_id="ep-simulator-rolling",
            bearer_token="simulator-token",
        )
        self.server = EpSimulatorServer(self.state).start()
        self.addCleanup(self.server.stop)
        inner = EngineeringPlatformHttpExecutionHost(
            EngineeringPlatformHttpConfiguration(
                self.server.base_url,
                "forge",
                "simulator-token",
                expected_instance_id="ep-simulator-rolling",
                expected_consumer_id="forge-consumer",
                repository_id="forge",
                repository_identity="pcvantol/forge",
                peer_binding_id="rolling-peer",
                peer_configuration_revision=1,
                peer_configuration_digest="sha256:" + "d" * 64,
                allow_loopback_http=True,
            ),
            self.runtime,
        )
        self.host = _CompletingHttpHost(inner, self.state)

    @staticmethod
    def _prompt(intent, action):
        value = prompt(intent, action)
        return replace(
            value,
            mission_id=mission().id,
            execution_metadata=(
                ("mission_revision", "1"),
                ("provider_definition", value.provider_definition.id),
                ("provider_version", value.provider_definition.version),
            ),
        )

    @staticmethod
    def _binding(_state, _action):
        return RepositoryRevisionBinding(
            "a" * 40,
            None,
            "repository-truth:rolling",
            "sha256:" + "f" * 64,
        )

    @staticmethod
    def _truth(_state, evidence):
        if evidence is None:
            return DynamicMissionCapabilityTests.truth(None, None)
        repository = evidence.repository_evidence
        return {
            "source_id": "forge-repository-truth",
            "revision": repository.repository_revision,
            "locator": f"repository://forge/{repository.repository_revision}",
            "content_digest": repository.content_digest,
        }

    def _loop(self, provider: DerivationProvider, *, complete_all_from_a: bool = False) -> ExecutionLoop:
        def correlation() -> str:
            self.counter += 1
            return f"rolling-correlation-{self.counter}"

        def completion(state, current, truth):
            realized = {"A evidence reconciled"}
            if complete_all_from_a or current.repository_evidence.action_id == "action-b":
                realized.add("B evidence reconciled")
            return terminal_completion(mission(), current, truth, realized)

        return ExecutionLoop(
            self.dispatcher,
            self.store,
            MissionPlanner(),
            self.host,
            DynamicMissionCapabilityTests.planning,
            self._prompt,
            self._truth,
            host_id="engineering-platform",
            workspace_id="forge",
            repository_id="forge",
            repository_identity="pcvantol/forge",
            origin_identity="pcvantol/forge",
            clock=lambda: "2026-09-22T12:00:00Z",
            correlation_id_factory=correlation,
            ai_planner=AIMissionPlanner(provider),
            derivation_policy=DerivationPolicy(
                ("forge/runtime",), ("architecture-review",), ("scope-drift",),
            ),
            completion_evidence=completion,
            runtime_database=self.runtime,
            repository_revision_binding_factory=self._binding,
        )

    def test_http_terminal_a_precedes_second_planning_and_action_b_materialization(self) -> None:
        provider = DerivationProvider()
        loop = self._loop(provider)

        first = loop.run()
        self.assertEqual(first.status, MissionExecutionStatus.WAITING_FOR_EXECUTION)
        self.assertEqual([item["id"] for item in first.actions], ["action-a"])
        self.assertEqual(len(provider.snapshots), 1)
        self.assertEqual(len(self.state.submission_ids()), 1)

        after_a = loop.resume(mission().id)
        self.assertEqual(after_a.status, MissionExecutionStatus.WAITING_FOR_EXECUTION)
        self.assertEqual([item["id"] for item in after_a.actions], ["action-a", "action-b"])
        self.assertEqual([item["status"] for item in after_a.actions], ["COMPLETE", "ACTIVE"])
        self.assertEqual(len(after_a.execution_history), 1)
        self.assertEqual(after_a.execution_history[0]["repository_evidence"]["action_id"], "action-a")
        self.assertEqual(len(provider.snapshots), 2)
        self.assertEqual(
            after_a.planning_history[1]["completed_action_ids_at_derivation"],
            ["action-a"],
        )
        self.assertEqual(len(self.state.submission_ids()), 2)

        final = loop.resume(mission().id)
        self.assertEqual(final.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual([item["id"] for item in final.actions], ["action-a", "action-b"])
        self.assertEqual(len(final.execution_history), 2)
        self.assertEqual(len(provider.snapshots), 2)
        self.assertEqual(len(self.state.submission_ids()), 2)

    def test_http_single_action_completion_does_not_invent_p2_or_b(self) -> None:
        provider = DerivationProvider()
        loop = self._loop(provider, complete_all_from_a=True)

        first = loop.run()
        self.assertEqual(first.status, MissionExecutionStatus.WAITING_FOR_EXECUTION)
        final = loop.resume(mission().id)
        self.assertEqual(final.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual([item["id"] for item in final.actions], ["action-a"])
        self.assertEqual(len(provider.snapshots), 1)
        self.assertEqual(len(self.state.submission_ids()), 1)


if __name__ == "__main__":
    unittest.main()
