"""Installed public composition coverage for the real dynamic Mission path."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from forge.architecture import ArchitectureWorkspace
from forge.business import BusinessWorkspace
from forge.completion import MissionCompletionEvaluator
from forge.execution import RecoveryAuthorization
from forge.governance_authority import (
    ArchitecturePlanningEvidence,
    CanonicalGovernanceRepository,
    MissionPlanningEvidenceEnvelope,
)
from forge.models.action_derivation import DerivedActionProposal, ProposalProvenance
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.execution_host import (
    ExecutionDispatch,
    ExecutionEvidenceOutcome,
    ExecutionHostEvidence,
    ExecutionRepositoryEvidence,
)
from forge.models.mission_recommendation import RequiredDiscipline
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from forge.runtime import RuntimeBootstrap
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.scheduler import BootstrapMissionScheduler
from forge.state.mission_state import MissionExecutionStatus
from forge._version import canonical_version


class _Provider:
    def __init__(self) -> None:
        self.calls = 0

    def preflight(self):
        return SimpleNamespace(ready=True, state=SimpleNamespace(value="READY"))

    def derive_with_planning_input(self, snapshot, _planning_input, _policy):
        self.calls += 1
        return (DerivedActionProposal(
            "status-projection-action", "durable-status-projection", "Deliver the approved status projection.", (),
            ("forge/__main__.py",), ("focused status validation",), ("python -m unittest",), 1, False,
            ("protected-delivery",), ("scope-drift",),
            ProposalProvenance(
                f"fixture-derivation-{self.calls}", snapshot.id, snapshot.digest, "fixture-v1", "fixture", None,
                tuple(item.source_id for item in snapshot.evidence),
            ),
        ),)


class _Host:
    def __init__(self) -> None:
        self.config = SimpleNamespace(host_id="engineering-platform", project_id="forge", repository_id="forge",
                                      repository_identity="forge")
        self.dispatches = {}
        self.requests = []
        self.evidence_reads = 0
        self.return_evidence = False
        self.outcome = ExecutionEvidenceOutcome.COMPLETE

    def preflight(self):
        return {"contract_version": "1.0", "producer": {"id": "engineering-platform", "version": "fixture"}}

    def dispatch(self, request):
        dispatch = ExecutionDispatch(request, "ep-run-status-projection")
        self.requests.append(request)
        self.dispatches[request.correlation_id] = dispatch
        return dispatch

    def recover_dispatch(self, request):
        return self.dispatches.get(request.correlation_id)

    def retrieve_evidence(self, dispatch):
        self.evidence_reads += 1
        if not self.return_evidence:
            return None
        request = dispatch.request
        repository = ExecutionRepositoryEvidence(
            request.mission_id, request.intent_id, request.intent_revision, request.action_id,
            request.runtime_prompt.id, request.correlation_id, dispatch.host_run_id, request.repository_id,
            "fixture-protected-revision", "ep-report-status-projection", "sha256:" + "a" * 64,
        )
        return ExecutionHostEvidence(
            request.host_id, request.correlation_id, dispatch.host_run_id, "ep-report-status-projection",
            self.outcome, repository, validation_references=("focused-status-validation",),
            retry_of_correlation_id=request.retry_of_correlation_id,
            original_correlation_id=request.original_correlation_id,
            execution_started_at="2026-09-11T16:00:00Z", execution_completed_at="2026-09-11T16:01:00Z",
            receipt_id="ep-receipt-status-projection", execution_duration_ms=60_000,
        )


class InstalledDynamicMissionRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "forge-server"
        self.identity = NamedOperatorIdentity("e2e-operator", 501)
        self.provider, self.host = _Provider(), _Host()
        self.runtime = self._open_runtime()

    def tearDown(self) -> None:
        self.runtime.close()
        self.temporary.cleanup()

    def _open_runtime(self) -> InstalledDynamicMissionRuntime:
        database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        operators = InstallationOperatorService(database, lambda: self.identity)
        try:
            operators.context()
        except PermissionError:
            operators.first_bind()
        repository = CanonicalGovernanceRepository.for_runtime(database, lambda: self.identity, data_root=self.root)
        return InstalledDynamicMissionRuntime(
            database, repository, data_root=str(self.root), provider=self.provider, host=self.host,
            clock=lambda: "2026-09-11T16:00:00Z",
        )

    def _mission_and_envelope(self):
        repository, context = self.runtime.repository, self.runtime.repository.operators.context()
        planning = ArchitecturePlanningEvidence(
            ("durable-status-projection",), ("forge/__main__.py",), ("no unrelated runtime work",),
            ("scope-drift",), ("protected-delivery",), ("ep-v1.2",), 16_000, 4_000, "1",
        )
        business = BusinessWorkspace.for_runtime(self.runtime.database, repository, context)
        architecture = ArchitectureWorkspace.for_runtime(self.runtime.database, repository, context)
        business.approve(
            decision_id="business-status-projection", candidate_id="candidate-status-projection", revision="1",
            scope=planning.scope, gates=planning.human_gates,
        )
        architecture.approve(
            decision_id="architecture-status-projection", candidate_id="candidate-status-projection", revision="1",
            planning=planning,
        )
        envelope = MissionPlanningEvidenceEnvelope.compose(
            repository, subject_id="candidate-status-projection", subject_revision="1",
            business_decision_id="business-status-projection", architecture_decision_id="architecture-status-projection",
            planning=planning,
        )
        mission_id = self.runtime.database.allocate_next_mission_id(
            source="canonical-governance-envelope:" + envelope.digest, allocated_at="2026-09-11T16:00:00Z",
        )
        mission = ArchitectureMission(
            mission_id, "candidate-status-projection", "Durable status projection", "Expose durable dispatcher posture.",
            "Expose a safe status projection.", "Operators can inspect durable state.", "architecture-status-projection",
            "candidate-status-projection", ("durable-status-projection",), ("no unrelated runtime work",),
            ("status is derived from durable state",), ("configured EP v1.2",), ("ep-v1.2",),
            ("status-projection",), (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("scope-drift",),
            ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
        )
        return mission, envelope

    @staticmethod
    def _truth() -> RepositoryTruthSnapshot:
        return RepositoryTruthSnapshot(
            "forge-initial-truth", "forge", "fixture-initial-revision", "2026-09-11T16:00:00Z",
            (RepositoryTruthEvidence(
                "forge-main", "git_commit", "fixture-initial-revision", "https://example.invalid/forge",
                "sha256:" + "b" * 64,
            ),),
        )

    def test_admits_zero_actions_then_reopens_same_installed_instance_to_reconcile_terminal_evidence(self) -> None:
        mission, envelope = self._mission_and_envelope()
        admitted = self.runtime.admit(mission, envelope)
        self.assertEqual(admitted.status.value, "APPROVED_PLANNABLE")
        self.assertEqual(admitted.actions, ())
        self.assertEqual(admitted.intents, ())

        waiting = self.runtime.start(mission.id, self._truth())
        self.assertEqual(waiting.status, "WAITING_FOR_EVIDENCE")
        self.assertEqual(waiting.planning_invocations, 1)
        self.assertEqual(len(waiting.action_ids), 1)
        planning_context = self.host.requests[-1].producer_contract.planning_context
        self.assertIsNotNone(planning_context)
        self.assertEqual(planning_context.mission_title, "Durable status projection")
        self.assertEqual(planning_context.business_summary, "Expose a safe status projection.")
        self.assertEqual(planning_context.engineering_summary, "Expose durable dispatcher posture.")
        self.assertEqual(planning_context.mission_lifecycle, "ACTIVE")
        self.assertEqual(planning_context.decision_evidence_reference, "architecture-status-projection")
        self.assertTrue(planning_context.envelope_digest.startswith("sha256:"))
        runtime_id = waiting.runtime_id
        self.runtime.close()

        self.host.return_evidence = True
        self.runtime = self._open_runtime()
        complete = self.runtime.resume(mission.id)
        self.assertEqual(complete.runtime_id, runtime_id)
        self.assertEqual(complete.status, "COMPLETED")
        self.assertEqual(complete.planning_invocations, 1)
        state = self.runtime.states.get(mission.id)
        self.assertTrue(state.completion["all_required_criteria_proven"])
        self.assertEqual(state.execution_history[-1]["receipt_id"], "ep-receipt-status-projection")

    def test_public_recovery_retries_only_the_terminal_action_with_durable_lineage(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self.runtime.admit(mission, envelope)
        self.host.return_evidence = True
        self.host.outcome = ExecutionEvidenceOutcome.BLOCKED
        blocked = self.runtime.start(mission.id, self._truth())
        self.assertEqual(blocked.status, "BLOCKED")
        first = self.host.requests[-1]

        self.host.outcome = ExecutionEvidenceOutcome.COMPLETE
        completed = self.runtime.recover(
            mission.id,
            RecoveryAuthorization(
                mission.id, first.action_id, "operator-e2e-recovery-001", "The verified host precondition was corrected.",
            ),
        )
        self.assertEqual(completed.status, "COMPLETED")
        self.assertEqual(len(self.host.requests), 2)
        retry = self.host.requests[-1]
        self.assertEqual(retry.retry_of_correlation_id, first.correlation_id)
        self.assertEqual(retry.original_correlation_id, first.correlation_id)
        self.assertEqual(retry.producer_contract.producer.identity.version, canonical_version())
        state = self.runtime.states.get(mission.id)
        self.assertIn("authorized_recovery", [item["reason"] for item in state.state_history])

    def test_terminal_evidence_reconciliation_never_creates_a_second_dispatch(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self.runtime.admit(mission, envelope)
        waiting = self.runtime.start(mission.id, self._truth())
        self.assertEqual(waiting.status, "WAITING_FOR_EVIDENCE")
        self.runtime.states.transition(
            mission.id, MissionExecutionStatus.FAILED, occurred_at="2026-09-11T16:01:00Z",
            reason="host_evidence_failed",
            execution_evidence={"outcome": "failed", "diagnostic_references": ["runner:host_evidence_failed"]},
        )
        self.host.return_evidence = True

        reconciled = self.runtime.reconcile_terminal_evidence(mission.id)

        self.assertEqual(reconciled.status, "COMPLETED")
        self.assertEqual(len(self.host.requests), 1)
        state = self.runtime.states.get(mission.id)
        self.assertIn("terminal_evidence_reconciliation_requested", [item["reason"] for item in state.state_history])

    def test_completed_terminal_evidence_reconciliation_closes_only_legacy_timing_gap(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self.runtime.admit(mission, envelope)
        waiting = self.runtime.start(mission.id, self._truth())
        self.assertEqual(waiting.status, "WAITING_FOR_EVIDENCE")
        before = self.runtime.states.get(mission.id)
        self.host.return_evidence = True
        loop = self.runtime._loop(mission.id)
        dispatch = ExecutionDispatch(self.host.requests[-1], "ep-run-status-projection")
        evidence = self.host.retrieve_evidence(dispatch)
        self.assertIsNotNone(evidence)
        actions = BootstrapMissionScheduler().reconcile(loop._runner()._actions(before), dispatch, evidence)
        truth = self.runtime._repository_truth(before, evidence)
        completion_evidence = self.runtime._completion_evidence(before, evidence, truth)
        evaluation = MissionCompletionEvaluator().evaluate(
            ArchitectureMission.from_dict(dict(before.mission)), truth,
            (*before.execution_history, self.runtime._execution_evidence_document(evidence)), completion_evidence,
        )
        legacy_evidence = self.runtime._execution_evidence_document(evidence)
        legacy_evidence.update({
            "execution_started_at": None,
            "execution_completed_at": None,
            "execution_duration_ms": None,
        })
        self.runtime.states.transition(
            mission.id, MissionExecutionStatus.ACTIVE, occurred_at="2026-09-11T16:01:00Z",
            reason="historical_terminal_timing_gap", actions=actions,
            execution_evidence=legacy_evidence, repository_truth=truth,
            completion=evaluation.to_dict(),
        )

        completed = self.runtime.reconcile_completed_terminal_evidence(mission.id)

        self.assertEqual(completed.status, "COMPLETED")
        self.assertEqual(len(self.host.requests), 1)
        self.assertEqual(self.host.evidence_reads, 3)
        state = self.runtime.states.get(mission.id)
        self.assertEqual(state.execution_evidence["execution_duration_ms"], 60_000)
        self.assertEqual(state.execution_evidence["execution_started_at"], "2026-09-11T16:00:00Z")
        self.assertTrue(state.completion["all_required_criteria_proven"])
        self.assertIn("completed_terminal_evidence_reconciled", [item["reason"] for item in state.state_history])
        dispatcher = self.runtime.database._connection.execute(
            "SELECT status, active_mission_id FROM dispatcher_state WHERE singleton=1"
        ).fetchone()
        self.assertEqual((dispatcher["status"], dispatcher["active_mission_id"]), ("IDLE", None))
        events = self.runtime.database.operational_log_page(mission_id=mission.id, page_size=20)["items"]
        self.assertCountEqual(
            [event["event"] for event in events if event["event"].startswith("completed_terminal_evidence_")],
            [
                "completed_terminal_evidence_reconciliation_requested",
                "completed_terminal_evidence_reconciled",
            ],
        )
        self.runtime.database.save_dispatcher_state(
            status="ACTIVE", mission_sequence=(mission.id,), active_mission_id=mission.id,
        )
        recovered_dispatcher = self.runtime.reconcile_completed_terminal_evidence(mission.id)
        self.assertEqual(recovered_dispatcher.status, "COMPLETED")
        dispatcher = self.runtime.database._connection.execute(
            "SELECT status, active_mission_id FROM dispatcher_state WHERE singleton=1"
        ).fetchone()
        self.assertEqual((dispatcher["status"], dispatcher["active_mission_id"]), ("IDLE", None))
        self.assertEqual(self.host.evidence_reads, 3)


if __name__ == "__main__":
    unittest.main()
