"""Source-level crash checks for the persisted evidence-to-successor boundary.

External fixtures here do not qualify the installed composition or substantive
criterion assessment. The tests isolate orchestration persistence using the
existing dynamic-loop fixtures and the real durable planner coordinator.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace

from forge.execution import ApprovalRecord, ExecutionLoop, ExecutionLoopError, ExecutionPolicy, ExecutionPolicyKind
from forge.models import (
    CanonicalExecutionEvidenceReference, ExecutionEvidenceOutcome,
    MissionCompletionEvidence, MissionCriterionEvidenceBinding, RepositoryTruthReference,
    mission_criterion_id,
)
from forge.models.action_derivation import ProviderInvocationEvidence, ProviderSideEffectState
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from forge.models.criterion_observation import CriterionObservation
from forge.planner.durable_derivation import DurableAIMissionPlanner
from forge.planner.provider_adapter import ProviderDerivationResponse
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime import RuntimeBootstrap, MissionRunnerError
from forge.state import MissionExecutionStatus, MissionStateStore
import tests.test_dynamic_mission_capability as fixture
from tests.criterion_fixture import seed_pending, planning_state, terminal_completion


class SimulatedProcessExit(BaseException):
    """A process exit is not an in-process exception or retry authorization."""


class DurableProvider(fixture.DerivationProvider):
    provider_id = "fixture-provider"

    def prepare_durable_attempt(self, snapshot, _input, _policy, derivation_id,
                                attempt_authority_id=None):
        return {
            "provider_id": self.provider_id, "provider_configuration_revision": "1",
            "provider_model": "fixture-model", "adapter_version": "fixture-v1",
            "provider_policy_digest": fixture.digest("policy"),
            "generation_request_digest": fixture.digest({"snapshot": snapshot.digest}),
            "derivation_request_digest": fixture.digest({"derivation": derivation_id}),
        }

    def derive_with_planning_input(self, snapshot, _input, _policy, *, derivation_id,
                                   durable_attempt_specification=None, durable_result_sink=None,
                                   attempt_authority_id=None):
        if durable_attempt_specification is None or durable_result_sink is None:
            raise AssertionError("durable provider boundary is required")
        # The completed state in the snapshot, rather than this process's call
        # count, chooses fixture output so process recreation cannot affect it.
        self.snapshots.append(snapshot)
        successor = any(item.kind.value == "execution_evidence" for item in snapshot.evidence)
        action_id = "action-b" if successor else "action-a"
        proposal = self.proposal(
            snapshot, action_id, dependencies=("action-a",) if successor else (),
            mission_gap=self.successor_gap(snapshot, action_id) if successor else None,
        )
        proposal = replace(proposal, provenance=replace(proposal.provenance, derivation_id=derivation_id))
        response = ProviderDerivationResponse(
            ProviderInvocationEvidence(
                self.provider_id, "fixture-model", "fixture-v1",
                durable_attempt_specification["derivation_request_digest"], snapshot.digest,
                fixture.digest({"derivation": derivation_id, "action": action_id}),
                ProviderSideEffectState.HAPPENED_AND_CONFIRMED, status="completed",
            ), proposals=(proposal,),
        )
        durable_result_sink(response)
        return (proposal,)


class TerminalContinuationReplayTests(unittest.TestCase):
    tearDown = fixture.DynamicMissionCapabilityTests.tearDown
    truth = staticmethod(fixture.DynamicMissionCapabilityTests.truth)
    loop = fixture.DynamicMissionCapabilityTests.loop

    @staticmethod
    def _mission():
        return replace(fixture.mission(), maximum_actions=4, maximum_consecutive_no_progress_actions=2)

    def planning(self, state):
        source = fixture.DynamicMissionCapabilityTests.planning(state)
        truth = state.repository_truth or self.truth(state, None)
        return replace(source, mission=self._mission(), mission_state=planning_state(state, self._mission(), truth))

    def completion_evidence(self, state, evidence, truth):
        realized = {"A evidence reconciled"}
        if evidence.repository_evidence.action_id == "action-b":
            realized.add("B evidence reconciled")
        return terminal_completion(self._mission(), evidence, truth, realized)

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name) / "runtime"
        self.runtime = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        InstallationOperatorService(self.runtime, lambda: NamedOperatorIdentity("replay-fixture", 501)).first_bind()
        self.runtime_identity = self.runtime.runtime_identity
        self.store = MissionStateStore(self.runtime, data_root=str(self.root))
        seed_pending(self.store, self._mission(), self.truth(None, None), occurred_at="2026-09-10T09:59:00Z")
        self.host, self.dispatcher, self.counter = fixture.Host(), fixture.Dispatcher(), 0

    def _reopen(self):
        self.runtime.close()
        self.runtime = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.store = MissionStateStore(self.runtime, data_root=str(self.root))

    def _interrupt(self, reason: str, *, after: bool = True, exception=None):
        original = self.store.transition

        def transition(*args, **kwargs):
            if kwargs.get("reason") != reason:
                return original(*args, **kwargs)
            if after:
                original(*args, **kwargs)
            raise exception or SimulatedProcessExit(reason)

        self.store.transition = transition

    def _durable_loop(self, provider):
        loop = self.loop(provider)
        loop._ai_planner = DurableAIMissionPlanner(self.runtime, provider)
        return loop

    def test_restart_after_assessment_uses_persisted_evidence_without_reassessment(self):
        provider = fixture.DerivationProvider()
        self._interrupt("terminal_evidence_reconciled")
        with self.assertRaises(SimulatedProcessExit):
            self.loop(provider).run()
        assessed = self.store.get(fixture.mission().id)
        self.assertEqual(assessed.status, MissionExecutionStatus.ACTIVE)
        self.assertEqual(assessed.resume["terminal_continuation"]["phase"], "ASSESSED")
        self.assertEqual(len(provider.snapshots), 1)
        self._reopen()
        original_read = self.host.retrieve_evidence

        def read(dispatch):
            if dispatch.request.action_id == "action-a":
                raise AssertionError("persisted terminal receipt must not be fetched again")
            return original_read(dispatch)

        self.host.retrieve_evidence = read
        loop = self.loop(provider)
        loop._completion_evidence = lambda *args: (_ for _ in ()).throw(
            AssertionError("persisted assessment must not be recreated"))
        waiting = loop.resume(fixture.mission().id)
        self.assertEqual(waiting.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        self.assertEqual(waiting.completion, assessed.completion)
        self.assertEqual(len(waiting.execution_history), 1)
        self.assertEqual(self.host.requests, ["action-a", "action-b"])
        self.assertEqual(len(provider.snapshots), 2)
        loop.resume(fixture.mission().id)
        self.assertEqual(len(provider.snapshots), 2)
        self.assertEqual(self.host.requests, ["action-a", "action-b"])

    def test_restart_after_successor_commit_never_derives_another_successor(self):
        provider = DurableProvider()
        self._interrupt("dynamic_successor_materialized")
        with self.assertRaises(SimulatedProcessExit):
            self._durable_loop(provider).run()
        materialized = self.store.get(fixture.mission().id)
        self.assertEqual(materialized.resume["terminal_continuation"]["phase"], "SUCCESSOR_READY")
        attempts = self.runtime.durable_action_derivation_readback(fixture.mission().id)
        self.assertEqual([item["processing_phase"] for item in attempts], ["MATERIALIZED", "MATERIALIZED"])
        self._reopen()
        new_provider = DurableProvider()
        waiting = self._durable_loop(new_provider).resume(fixture.mission().id)
        self.assertEqual(waiting.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        self.assertEqual(new_provider.snapshots, [])
        self.assertEqual(len(waiting.planning_history), 2)
        self.assertEqual(self.host.requests, ["action-a", "action-b"])

    def test_restart_before_successor_commit_reuses_the_durable_provider_result(self):
        provider = DurableProvider()
        self._interrupt("dynamic_successor_materialized", after=False)
        with self.assertRaises(SimulatedProcessExit):
            self._durable_loop(provider).run()
        before = self.runtime.durable_action_derivation_readback(fixture.mission().id)
        self.assertEqual([item["processing_phase"] for item in before], ["MATERIALIZED", "VALIDATED"])
        self._reopen()
        new_provider = DurableProvider()
        waiting = self._durable_loop(new_provider).resume(fixture.mission().id)
        after = self.runtime.durable_action_derivation_readback(fixture.mission().id)
        self.assertEqual(new_provider.snapshots, [])
        self.assertEqual([item["derivation_id"] for item in after], [item["derivation_id"] for item in before])
        self.assertEqual([item["processing_phase"] for item in after], ["MATERIALIZED", "MATERIALIZED"])
        self.assertEqual(len(waiting.planning_history), 2)
        self.assertEqual(self.host.requests, ["action-a", "action-b"])

    def test_restart_after_full_assessment_completes_without_replanning(self):
        self._durable_loop(DurableProvider()).run()
        self.host.outcomes["action-b"] = ExecutionEvidenceOutcome.COMPLETE
        self._interrupt("terminal_evidence_reconciled")
        with self.assertRaises(SimulatedProcessExit):
            self._durable_loop(DurableProvider()).resume(fixture.mission().id)
        assessed = self.store.get(fixture.mission().id)
        self.assertTrue(assessed.resume["terminal_continuation"]["mission_complete"])
        self._reopen()
        provider = DurableProvider()
        loop = self._durable_loop(provider)
        loop._completion_evidence = lambda *args: (_ for _ in ()).throw(AssertionError("assessment replayed"))
        complete = loop.resume(fixture.mission().id)
        self.assertEqual(complete.status, MissionExecutionStatus.COMPLETED)
        self.assertEqual(complete.completion, assessed.completion)
        self.assertEqual(len(complete.execution_history), 2)
        self.assertEqual(provider.snapshots, [])
        self.assertEqual(self.host.requests, ["action-a", "action-b"])

    def test_successor_storage_error_retains_failed_materialization_evidence(self):
        self._interrupt("dynamic_successor_materialized", after=False, exception=ValueError("STORAGE_UNAVAILABLE"))
        blocked = self._durable_loop(DurableProvider()).run()
        self.assertEqual(blocked.status, MissionExecutionStatus.BLOCKED)
        self.assertEqual([item["id"] for item in blocked.actions], ["action-a"])
        self.assertEqual(self.host.requests, ["action-a"])
        attempts = self.runtime.durable_action_derivation_readback(fixture.mission().id)
        self.assertEqual([item["processing_phase"] for item in attempts], ["MATERIALIZED", "MATERIALIZATION_FAILED"])

    def test_policy_pause_survives_successor_commit_restart_and_consumes_one_approval(self):
        provider = DurableProvider()
        policy = ExecutionPolicy(ExecutionPolicyKind.ENGINEERING_ACTION_REVIEW)
        self._interrupt("dynamic_successor_materialized")
        loop = self._durable_loop(provider)
        loop._execution_policy = policy
        with self.assertRaises(SimulatedProcessExit):
            loop.run()
        self._reopen()
        loop = self._durable_loop(DurableProvider())
        loop._execution_policy = policy
        paused = loop.resume(fixture.mission().id)
        self.assertEqual(paused.status, MissionExecutionStatus.AWAITING_APPROVAL)
        self.assertEqual(self.host.requests, ["action-a"])
        waiting = loop.resume(fixture.mission().id, approval=ApprovalRecord(
            "approval-a", "architect", "2026-09-10T10:02:00Z", "review-a"))
        self.assertEqual(waiting.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        self.assertNotIn("terminal_continuation", waiting.resume)
        self.assertEqual(self.host.requests, ["action-a", "action-b"])
        self.host.outcomes["action-b"] = ExecutionEvidenceOutcome.COMPLETE
        paused_final = loop.resume(fixture.mission().id)
        self.assertEqual(paused_final.status, MissionExecutionStatus.AWAITING_APPROVAL)
        self._reopen()
        loop = self._durable_loop(DurableProvider())
        completed = loop.resume(fixture.mission().id, approval=ApprovalRecord(
            "approval-b", "architect", "2026-09-10T10:03:00Z", "review-b"))
        self.assertEqual(completed.status, MissionExecutionStatus.COMPLETED)
        self.assertNotIn("terminal_continuation", completed.resume)
        self.assertEqual(self.host.requests, ["action-a", "action-b"])
        self.assertEqual(len(completed.execution_history), 2)

    def test_conflicting_continuation_identity_fails_without_host_or_provider_effects(self):
        provider = fixture.DerivationProvider()
        self._interrupt("terminal_evidence_reconciled")
        with self.assertRaises(SimulatedProcessExit):
            self.loop(provider).run()
        self._reopen()
        state = self.store.get(fixture.mission().id)
        self.store.transition(
            state.mission_id, MissionExecutionStatus.ACTIVE, occurred_at="2026-09-10T10:02:00Z",
            reason="synthetic_corruption", resume={**state.resume, "terminal_continuation": {
                **state.resume["terminal_continuation"], "mission_digest": fixture.digest("wrong-mission"),
            }},
        )
        with self.assertRaisesRegex(MissionRunnerError, "malformed or stale"):
            self.loop(provider).resume(state.mission_id)
        self.assertEqual(len(provider.snapshots), 1)
        self.assertEqual(self.host.requests, ["action-a"])

    def test_completion_assessment_failure_preserves_receipt_and_redacts_error(self):
        provider = DurableProvider()
        loop = self._durable_loop(provider)
        loop._completion_evidence = lambda *args: (_ for _ in ()).throw(
            ValueError("private-local-path and provider payload must not be journalled"))
        blocked = loop.run()
        self.assertEqual(blocked.status, MissionExecutionStatus.BLOCKED)
        self.assertEqual(blocked.waiting_reason, "completion_assessment_failed:VALUEERROR")
        self.assertEqual(blocked.execution_evidence["receipt_id"], "receipt-action-a")
        self.assertEqual(blocked.actions[0]["status"], "COMPLETE")
        self.assertEqual(len(provider.snapshots), 1)
        self.assertEqual(self.host.requests, ["action-a"])

    def test_continuation_limits_use_requirement_progress_and_explicit_unsupported_evidence(self):
        state = self.store.get(fixture.mission().id)
        with self.assertRaisesRegex(ExecutionLoopError, "LEGACY_ASSESSMENT_CONTRACT_MISSING"):
            ExecutionLoop._assert_successor_bounds(state, replace(fixture.mission(), criterion_assessment_contracts=(), maximum_actions=None, maximum_consecutive_no_progress_actions=None, repository_evidence_source=None))
        limited = replace(self._mission(), maximum_actions=1, maximum_consecutive_no_progress_actions=1)
        with self.assertRaisesRegex(ExecutionLoopError, "MISSION_ACTION_LIMIT_REACHED"):
            ExecutionLoop._assert_successor_bounds(replace(state, actions=({"id": "a"},)), limited)

        def assessment(proven, *, reason="OBSERVATION_MISSING", observation="receipt-one"):
            return {"criteria": [{"criterion_id": "criterion", "contract_digest": "contract",
                "requirement_results": [{"requirement_id": "requirement", "requirement_digest": "requirement-digest",
                    "status": "PROVEN" if proven else "UNSATISFIED", "reason": reason,
                    "observation_ids": [observation]}]}]}

        first = assessment(True)
        unchanged = assessment(True, observation="different-receipt")
        unchanged_again = assessment(True, observation="third-receipt")
        stalled = replace(state, completion=unchanged_again,
                          completion_history=(first, unchanged, unchanged_again))
        with self.assertRaisesRegex(ExecutionLoopError, "MISSION_NO_PROGRESS_LIMIT_REACHED"):
            ExecutionLoop._assert_successor_bounds(stalled, self._mission())
        # Re-proving a property after actual invalidation is real progress.
        recovered = replace(state, completion=unchanged,
                            completion_history=(first, assessment(False), unchanged))
        ExecutionLoop._assert_successor_bounds(recovered, self._mission())
        unsupported = replace(state, completion=assessment(
            False, reason="UNSUPPORTED_AUTHORITATIVE_EVIDENCE_SOURCE"))
        with self.assertRaisesRegex(ExecutionLoopError, "UNSUPPORTED_AUTHORITATIVE_EVIDENCE_SOURCE"):
            ExecutionLoop._assert_successor_bounds(unsupported, self._mission())

    def test_work_fingerprint_ignores_identity_and_provenance_churn(self):
        original = SimpleNamespace(
            logical_action_id="first", provenance="old-receipt", scope="bounded",
            objective="Implement stable status", write_scopes=("forge/runtime",),
            expected_evidence=("Status properties",), validation_strategy=("status validation",),
        )
        renamed = SimpleNamespace(**{**original.__dict__, "logical_action_id": "second",
                                     "provenance": "new-receipt", "objective": "Implement  stable STATUS"})
        self.assertEqual(ExecutionLoop._work_fingerprint(original), ExecutionLoop._work_fingerprint(renamed))
        renamed.objective = "Implement another property"
        self.assertNotEqual(ExecutionLoop._work_fingerprint(original), ExecutionLoop._work_fingerprint(renamed))


class InitialActionCeilingTests(unittest.TestCase):
    setUp = TerminalContinuationReplayTests.setUp
    tearDown = TerminalContinuationReplayTests.tearDown
    truth = staticmethod(TerminalContinuationReplayTests.truth)
    planning = TerminalContinuationReplayTests.planning
    completion_evidence = TerminalContinuationReplayTests.completion_evidence
    loop = TerminalContinuationReplayTests.loop

    @staticmethod
    def _mission():
        return replace(fixture.mission(), maximum_actions=1, maximum_consecutive_no_progress_actions=1)

    def test_forecast_does_not_consume_approved_action_limit_before_dispatch(self):
        class TwoActions(fixture.DerivationProvider):
            def derive(self, snapshot):
                self.snapshots.append(snapshot)
                first = self.proposal(snapshot, "action-a")
                second = self.proposal(snapshot, "action-c")
                return first, replace(second, provenance=first.provenance)
        provider = TwoActions()
        self.host.outcomes["action-a"] = None
        state = self.loop(provider).run()
        self.assertEqual(state.status, MissionExecutionStatus.WAITING_FOR_EVIDENCE)
        self.assertEqual([item["id"] for item in state.actions], ["action-a"])
        self.assertEqual(state.planning_history[0]["forecast_proposal_ids"], ["action-c"])
        self.assertEqual(self.host.requests, ["action-a"])
        self.assertEqual(len(provider.snapshots), 1)


if __name__ == "__main__":
    unittest.main()
