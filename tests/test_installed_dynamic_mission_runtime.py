"""Source-level public runtime tests with external Host/provider/byte fixtures.

This module exercises runtime methods and canonical governance, but constructs
the runtime directly; installed normal-factory qualification is separate.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from hashlib import sha256
import json
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
from forge.models.action_derivation import (
    DerivedActionProposal, ProposalProvenance, ProviderInvocationEvidence,
    ProviderSideEffectState, PlanningSnapshot,
)
from forge.planner.provider_adapter import ProviderDerivationResponse
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
from forge.runtime.database import RuntimeDatabaseError, RuntimeIntegrityError
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.scheduler import BootstrapMissionScheduler
from forge.state.mission_state import MissionExecutionStatus
from forge._version import canonical_version
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from tests.criterion_fixture import ExactRepositoryBytes


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class _Provider:
    def __init__(self) -> None:
        self.calls = 0

    def preflight(self):
        return SimpleNamespace(ready=True, state=SimpleNamespace(value="READY"))

    @property
    def provider_id(self) -> str:
        return "fixture"

    def prepare_durable_attempt(self, snapshot, _planning_input, _policy, derivation_id,
                                attempt_authority_id=None):
        request = _digest({"derivation": derivation_id, "snapshot": snapshot.digest,
                           "authority": attempt_authority_id})
        return {
            "provider_id": "fixture", "provider_configuration_revision": "1",
            "provider_model": None, "adapter_version": "fixture-v1",
            "provider_policy_digest": _digest({"provider": "fixture", "revision": 1}),
            "generation_request_digest": _digest({"snapshot": snapshot.digest, "provider": "fixture",
                                                    "authority": attempt_authority_id}),
            "derivation_request_digest": request,
        }

    def derive_with_planning_input(self, snapshot, _planning_input, _policy, *, derivation_id,
                                   attempt_authority_id=None, durable_attempt_specification=None,
                                   durable_result_sink=None):
        if durable_attempt_specification is None:
            raise AssertionError("durable invocation must use the prepared attempt specification")
        self.calls += 1
        proposals = (DerivedActionProposal(
            "status-projection-action", "durable-status-projection", "Deliver the approved status projection.", (),
            ("forge/__main__.py",), ("focused status validation",), ("python -m unittest",), 1, False,
            ("protected-delivery",), ("scope-drift",),
            ProposalProvenance(
                derivation_id, snapshot.id, snapshot.digest, "fixture-v1", "fixture", None,
                tuple(item.source_id for item in snapshot.evidence),
            ),
        ),)
        if durable_result_sink is None:
            return proposals
        response = ProviderDerivationResponse(
            ProviderInvocationEvidence(
                "fixture", None, "fixture-v1",
                _digest({"derivation": derivation_id, "snapshot": snapshot.digest,
                         "authority": attempt_authority_id}),
                snapshot.digest, _digest({"result": "status-projection", "derivation": derivation_id}),
                ProviderSideEffectState.HAPPENED_AND_CONFIRMED, status="completed",
            ), proposals=proposals,
        )
        durable_result_sink(response)
        return proposals


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
        run_id = "ep-run-status-projection" + (f"-retry-{len(self.requests)}" if self.requests else "")
        dispatch = ExecutionDispatch(request, run_id)
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
        suffix = "" if dispatch.host_run_id == "ep-run-status-projection" else "-" + dispatch.host_run_id
        report_id = "ep-report-status-projection" + suffix
        repository = ExecutionRepositoryEvidence(
            request.mission_id, request.intent_id, request.intent_revision, request.action_id,
            request.runtime_prompt.id, request.correlation_id, dispatch.host_run_id, request.repository_id,
            "c" * 40, report_id, "sha256:" + "a" * 64,
        )
        return ExecutionHostEvidence(
            request.host_id, request.correlation_id, dispatch.host_run_id, report_id,
            self.outcome, repository, validation_references=("focused-status-validation",),
            retry_of_correlation_id=request.retry_of_correlation_id,
            original_correlation_id=request.original_correlation_id,
            execution_started_at="2026-09-11T16:00:00Z", execution_completed_at="2026-09-11T16:01:00Z",
            receipt_id="ep-receipt-status-projection" + suffix, execution_duration_ms=60_000,
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
        runtime = InstalledDynamicMissionRuntime(
            database, repository, data_root=str(self.root), provider=self.provider, host=self.host,
            clock=lambda: "2026-09-11T16:00:00Z",
        )
        runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"durable-state"}'},
        )
        return runtime

    def _mission_and_envelope(self):
        repository, context = self.runtime.repository, self.runtime.repository.operators.context()
        contracts = (CriterionAssessmentContract(
            "status contract declares durable-state provenance", (CriterionEvidenceRequirement(
                "durable-status-source", kind="repository_json", artifact_path="contract.json",
                json_pointer="/source", expected_json='"durable-state"',
            ),)),)
        source = ApprovedRepositoryEvidenceSource("forge", "synthetic/forge")
        planning = ArchitecturePlanningEvidence(
            ("durable-status-projection",), ("forge/__main__.py",), ("no unrelated runtime work",),
            ("scope-drift",), ("protected-delivery",), ("ep-v1.2",), 16_000, 4_000, "1",
            criterion_assessment_contracts=contracts, maximum_actions=4,
            maximum_consecutive_no_progress_actions=2, repository_evidence_source=source,
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
            ("status contract declares durable-state provenance",), ("configured EP v1.2",), ("ep-v1.2",),
            ("status-projection",), (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("scope-drift",),
            ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
            criterion_assessment_contracts=contracts, maximum_actions=4,
            maximum_consecutive_no_progress_actions=2, repository_evidence_source=source,
        )
        return mission, envelope

    @staticmethod
    def _truth() -> RepositoryTruthSnapshot:
        return RepositoryTruthSnapshot(
            "forge-initial-truth", "forge", "a" * 40, "2026-09-11T16:00:00Z",
            (RepositoryTruthEvidence(
                "forge-main", "git_commit", "a" * 40, "https://example.invalid/forge",
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
        readback = self.runtime.action_derivation_readback(mission.id)
        self.assertEqual(len(readback), 1)
        self.assertEqual(readback[0]["processing_phase"], "MATERIALIZED")
        self.assertTrue(readback[0]["result_available"])
        self.assertNotIn("payload", readback[0])
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

    def test_public_readback_surfaces_linked_legacy_confirmed_result_without_generation(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self.runtime.admit(mission, envelope)
        state = self.runtime.states.get(mission.id)
        self.runtime._initial_truth[mission.id] = self.runtime._truth_from_snapshot(self._truth())
        snapshot = PlanningSnapshot.from_planner_input(self.runtime._planning_input(state))
        audit = {
            "state": "HAPPENED_AND_CONFIRMED", "status": "completed", "provider_id": "fixture",
            "snapshot_digest": snapshot.digest, "derivation_request_digest": _digest("legacy-derivation"),
            "request_digest": _digest("legacy-generation"), "result_digest": _digest("legacy-result"),
        }
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "INSERT INTO planning_provider_external_session_config VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("fixture-config", "fixture", "CODEX_CLI_CHATGPT_SESSION",
                 "EXTERNAL_AUTHENTICATED_SESSION", "CODEX_CLI_CHATGPT_SESSION", "/usr/bin/true",
                 "fixture-v1", None, 1, "operator", 1, "2026-09-11T16:00:00Z",
                 "2026-09-11T16:00:00Z", None, 30, 16000, 32768, 4096),
            )
            self.runtime.database._connection.execute(
                "INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)",
                ("legacy-confirmed", "fixture-config", "operator", "invocation",
                 "2026-09-11T16:00:00Z", json.dumps(audit, sort_keys=True)),
            )
        readback = self.runtime.action_derivation_readback(mission.id)
        self.assertEqual(readback[0]["source"], "LEGACY_EXTERNAL_SESSION_AUDIT")
        self.assertEqual(readback[0]["generation_state"], "HAPPENED_AND_CONFIRMED")
        self.assertFalse(readback[0]["result_available"])
        self.assertEqual(self.provider.calls, 0)

    def test_public_legacy_audit_can_authorize_and_replay_one_successor_without_regeneration(self) -> None:
        """A linked, audit-only result is a predecessor without being backfilled.

        The setup intentionally has no ``action_derivations`` row or provider
        payload.  All observed behaviour below crosses the installed public
        runtime surface; the fixture SQL represents only the immutable
        external-session boundary that predates durable result storage.
        """
        mission, envelope = self._mission_and_envelope()
        self.runtime.admit(mission, envelope)
        truth = self.runtime._truth_from_snapshot(self._truth())
        self.runtime.states.transition(
            mission.id, MissionExecutionStatus.CREATED, occurred_at="2026-09-11T16:00:00Z",
            reason="fixture_legacy_audit_predecessor", repository_truth=truth,
        )
        state = self.runtime.states.get(mission.id)
        snapshot = PlanningSnapshot.from_planner_input(self.runtime._planning_input(state))
        audit = {
            "state": "HAPPENED_AND_CONFIRMED", "status": "completed", "provider_id": "fixture",
            "snapshot_digest": snapshot.digest, "derivation_request_digest": _digest("legacy-derivation"),
            "request_digest": _digest("legacy-generation"), "result_digest": _digest("legacy-result"),
        }
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "INSERT INTO planning_provider_external_session_config VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("fixture-config", "fixture", "CODEX_CLI_CHATGPT_SESSION",
                 "EXTERNAL_AUTHENTICATED_SESSION", "CODEX_CLI_CHATGPT_SESSION", "/usr/bin/true",
                 "fixture-v1", None, 1, "operator", 1, "2026-09-11T16:00:00Z",
                 "2026-09-11T16:00:00Z", None, 30, 16000, 32768, 4096),
            )
            self.runtime.database._connection.execute(
                "INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)",
                ("legacy-confirmed-predecessor", "fixture-config", "operator", "invocation",
                 "2026-09-11T16:00:00Z", json.dumps(audit, sort_keys=True)),
            )

        readback = self.runtime.action_derivation_readback(mission.id)
        self.assertEqual(len(readback), 1)
        self.assertEqual(readback[0]["source"], "LEGACY_EXTERNAL_SESSION_AUDIT")
        self.assertEqual(readback[0]["audit_id"], "legacy-confirmed-predecessor")
        self.assertEqual(self.provider.calls, 0)
        self.assertEqual(self.runtime.database.durable_action_derivation_readback(mission.id), ())

        reservation = self.runtime.authorize_next_planning_attempt(
            mission.id, predecessor_audit_id=readback[0]["audit_id"],
            rationale="The confirmed legacy result is unavailable for replay.",
        )
        self.assertEqual(self.provider.calls, 0)
        self.assertEqual(reservation["predecessor_source"], "LEGACY_EXTERNAL_SESSION_AUDIT")
        with self.assertRaises(RuntimeIntegrityError):
            self.runtime.authorize_next_planning_attempt(
                mission.id, predecessor_audit_id=readback[0]["audit_id"],
                rationale="A second successor for the same legacy audit is forbidden.",
            )

        original_transition = self.runtime.states.transition
        self.runtime.states.transition = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeDatabaseError("fixture interruption after validation")
        )
        try:
            with self.assertRaises(RuntimeDatabaseError):
                self.runtime.resume_authorized_next_planning_attempt(
                    mission.id, successor_attempt_id=reservation["derivation_id"],
                )
        finally:
            self.runtime.states.transition = original_transition
        self.assertEqual(self.provider.calls, 1)

        self.runtime.close()
        self.runtime = self._open_runtime()
        replayed = self.runtime.resume_authorized_next_planning_attempt(
            mission.id, successor_attempt_id=reservation["derivation_id"],
        )
        self.assertEqual(replayed.status, "READY")
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(len(replayed.action_ids), 1)
        attempts = self.runtime.action_derivation_readback(mission.id)
        self.assertEqual(len(attempts), 1)
        successor = attempts[0]
        self.assertEqual(successor["processing_phase"], "MATERIALIZED")
        self.assertEqual(successor["predecessor_source"], "LEGACY_EXTERNAL_SESSION_AUDIT")
        self.assertEqual(successor["predecessor_audit_id"], "legacy-confirmed-predecessor")

    def test_public_legacy_audit_successor_rejects_unbound_other_and_ambiguous_evidence(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self.runtime.admit(mission, envelope)
        self.runtime.states.transition(
            mission.id, MissionExecutionStatus.CREATED, occurred_at="2026-09-11T16:00:00Z",
            reason="fixture_legacy_audit_rejections", repository_truth=self.runtime._truth_from_snapshot(self._truth()),
        )
        state = self.runtime.states.get(mission.id)
        snapshot = PlanningSnapshot.from_planner_input(self.runtime._planning_input(state))
        audit = {
            "state": "HAPPENED_AND_CONFIRMED", "status": "completed", "provider_id": "fixture",
            "snapshot_digest": snapshot.digest, "derivation_request_digest": _digest("legacy-derivation"),
            "request_digest": _digest("legacy-generation"),
        }
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "INSERT INTO planning_provider_external_session_config VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("fixture-config", "fixture", "CODEX_CLI_CHATGPT_SESSION",
                 "EXTERNAL_AUTHENTICATED_SESSION", "CODEX_CLI_CHATGPT_SESSION", "/usr/bin/true",
                 "fixture-v1", None, 1, "operator", 1, "2026-09-11T16:00:00Z",
                 "2026-09-11T16:00:00Z", None, 30, 16000, 32768, 4096),
            )
            self.runtime.database._connection.execute(
                "INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)",
                ("legacy-audit-one", "fixture-config", "operator", "invocation",
                 "2026-09-11T16:00:00Z", json.dumps(audit, sort_keys=True)),
            )
            self.runtime.database._connection.execute(
                "INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)",
                ("legacy-audit-two", "fixture-config", "operator", "invocation",
                 "2026-09-11T16:00:01Z", json.dumps(audit, sort_keys=True)),
            )
            other_mission_audit = {**audit, "snapshot_digest": "sha256:" + "f" * 64}
            self.runtime.database._connection.execute(
                "INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)",
                ("another-mission-audit", "fixture-config", "operator", "invocation",
                 "2026-09-11T16:00:02Z", json.dumps(other_mission_audit, sort_keys=True)),
            )

        # The audit is observable but two confirmed invocations on one
        # planning boundary are deliberately not interchangeable authority.
        legacy = self.runtime.action_derivation_readback(mission.id)[0]
        self.assertEqual(legacy["source"], "LEGACY_EXTERNAL_SESSION_AUDIT")
        with self.assertRaises(RuntimeIntegrityError):
            self.runtime.authorize_next_planning_attempt(
                mission.id, predecessor_audit_id=legacy["audit_id"],
                rationale="Ambiguous legacy evidence cannot authorize a successor.",
            )
        original_authorize = self.runtime.repository.operators.authorize
        self.runtime.repository.operators.authorize = lambda _context: False
        try:
            with self.assertRaises(PermissionError):
                self.runtime.authorize_next_planning_attempt(
                    mission.id, predecessor_audit_id="legacy-audit-one",
                    rationale="An unbound operator cannot authorize a successor.",
                )
        finally:
            self.runtime.repository.operators.authorize = original_authorize

        with self.assertRaises(RuntimeDatabaseError):
            self.runtime.authorize_next_planning_attempt(
                mission.id, predecessor_audit_id="another-mission-audit",
                rationale="An audit from another Mission planning boundary is not authority.",
            )
        self.assertEqual(self.provider.calls, 0)

    def test_public_recovery_retries_only_the_terminal_action_with_durable_lineage(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self.runtime.admit(mission, envelope)
        self.host.return_evidence = True
        self.host.outcome = ExecutionEvidenceOutcome.BLOCKED
        blocked = self.runtime.start(mission.id, self._truth())
        self.assertEqual(blocked.status, "BLOCKED")
        first = self.host.requests[-1]
        self.assertEqual(first.repository_revision_binding.requested_revision, "a" * 40)
        self.assertIsNone(first.repository_revision_binding.allowed_baseline_revision)

        self.host.outcome = ExecutionEvidenceOutcome.COMPLETE
        completed = self.runtime.recover(
            mission.id,
            RecoveryAuthorization(
                mission.id, first.action_id, "operator-e2e-recovery-001", "The verified host precondition was corrected.",
                "b" * 40,
            ),
        )
        self.assertEqual(completed.status, "COMPLETED")
        self.assertEqual(len(self.host.requests), 2)
        retry = self.host.requests[-1]
        self.assertEqual(retry.retry_of_correlation_id, first.correlation_id)
        self.assertEqual(retry.original_correlation_id, first.correlation_id)
        self.assertEqual(retry.repository_revision_binding.allowed_baseline_revision, "b" * 40)
        self.assertEqual(retry.repository_revision_binding.transition_authority_id, "operator-e2e-recovery-001")
        self.assertEqual(retry.producer_contract.producer.identity.version, canonical_version())
        state = self.runtime.states.get(mission.id)
        self.assertIn("authorized_recovery", [item["reason"] for item in state.state_history])
        # A future partial-completion planning boundary must retain the old
        # blocker without mistaking it for successful execution evidence.
        planning = self.runtime._planning_input(state)
        context = planning.mission_state.continuation_context.to_dict()
        self.assertEqual([item["outcome"] for item in context["terminal_evidence"]], ["blocked", "complete"])
        from forge.models.mission_planner import PlanningInputKind
        references = [item.source_id for item in planning.evidence
                      if item.kind is PlanningInputKind.EXECUTION_EVIDENCE]
        self.assertEqual(references, [state.execution_history[-1]["receipt_id"]])

    def test_public_successor_reservation_is_explicit_and_does_not_dispatch(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self.runtime.admit(mission, envelope)
        original_store = self.runtime.database.store_durable_action_derivation_result
        def fail_confirmed_store(_result):
            raise RuntimeDatabaseError("qualification result store interruption")
        self.runtime.database.store_durable_action_derivation_result = fail_confirmed_store
        try:
            blocked = self.runtime.start(mission.id, self._truth())
        finally:
            self.runtime.database.store_durable_action_derivation_result = original_store
        self.assertEqual(blocked.status, "BLOCKED")
        predecessor = self.runtime.action_derivation_readback(mission.id)[0]
        self.assertEqual(predecessor["processing_phase"], "CONFIRMED_RESULT_UNAVAILABLE")
        reservation = self.runtime.authorize_next_planning_attempt(
            mission.id, predecessor_attempt_id=predecessor["derivation_id"],
            rationale="The confirmed provider result was not retained for replay.",
        )
        self.assertEqual(self.provider.calls, 1)
        planned = self.runtime.resume_authorized_next_planning_attempt(
            mission.id, successor_attempt_id=reservation["derivation_id"],
        )
        self.assertEqual(planned.status, "READY")
        self.assertEqual(self.provider.calls, 2)
        self.assertEqual(self.host.requests, [])
        successor = self.runtime.action_derivation_readback(mission.id)[1]
        self.assertEqual(successor["processing_phase"], "MATERIALIZED")

        # Only the ordinary public resume crosses the existing EP boundary.
        waiting = self.runtime.resume(mission.id)
        self.assertEqual(waiting.status, "WAITING_FOR_EVIDENCE")
        self.assertEqual(len(self.host.requests), 1)

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
