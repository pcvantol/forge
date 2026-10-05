"""Source-level public runtime tests with external Host/provider/byte fixtures.

This module exercises runtime methods and canonical governance, but constructs
the runtime directly; installed normal-factory qualification is separate.
"""
from __future__ import annotations

from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from forge.architecture import ArchitectureWorkspace
from forge.business import BusinessWorkspace
from forge.completion import MissionCompletionEvaluator
from forge.execution import RecoveryAuthorization
from forge.governance_authority import (
    ArchitecturePlanningEvidence,
    CanonicalGovernanceRepository,
    MissionPlanningEvidenceEnvelope,
)
from forge.governed_continuation import GovernedContinuationService
from forge.models.action_derivation import (
    DerivedActionProposal, ProposalProvenance, ProviderInvocationEvidence,
    ProviderSideEffectState, PlanningSnapshot, MissionGapBinding, MissionGapClassification,
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
from forge.runtime.service import RuntimeServiceBusy, RuntimeServiceLock
from forge.runtime.database import RuntimeDatabaseError, RuntimeIntegrityError
from forge.runtime.dynamic_mission import (
    DynamicMissionRunResult, InstalledDynamicMissionError, InstalledDynamicMissionRuntime,
    _InstalledMissionDispatcher,
)
from forge.mission_no_dispatch import main as derive_actions_main
from forge import mission_cli
from forge.mission_lifecycle import MissionLifecycleError, MissionLifecycleService
from forge.scheduler import BootstrapMissionScheduler
from forge.state.mission_state import MissionExecutionStatus
from forge._version import canonical_version
from forge.__main__ import main as forge_main
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from tests.criterion_fixture import ExactRepositoryBytes
from tests.test_action_authority import authority


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
        suffix = "" if self.calls == 1 else f"-{self.calls}"
        objective = ("Deliver the approved status projection." if self.calls == 1
                     else f"Close remaining approved status criterion {self.calls}.")
        evidence_refs = tuple(item.source_id for item in snapshot.evidence)
        unmet = tuple(item.criterion_id for item in snapshot.criteria if item.status.value == "UNSATISFIED")
        gap = (None if self.calls == 1 else MissionGapBinding(
            MissionGapClassification.UNPROVEN_MISSION_CRITERION, unmet, evidence_refs,
            snapshot.digest, objective, (),
        ))
        proposals = (DerivedActionProposal(
            "status-projection-action" + suffix, "durable-status-projection", objective, (),
            ("forge/__main__.py",), ("focused status validation",), ("python -m unittest",), self.calls, False,
            ("protected-delivery",), ("scope-drift",),
            ProposalProvenance(
                derivation_id, snapshot.id, snapshot.digest, "fixture-v1", "fixture", None, evidence_refs,
            ), gap,
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


class _TwoRepositoryProvider(_Provider):
    scopes = ("repository-a", "repository-b")

    def derive_with_planning_input(self, snapshot, planning_input, policy, *, derivation_id,
                                   attempt_authority_id=None, durable_attempt_specification=None,
                                   durable_result_sink=None):
        if durable_attempt_specification is None or durable_result_sink is None:
            raise AssertionError("two-target derivation requires a durable provider result")
        self.calls += 1
        proposals = tuple(DerivedActionProposal(
            f"action-{scope.replace('/', '-')}", scope, f"Observe approved {scope} baseline.", (),
            ("NONE",), ("current repository baseline",), ("independent source readback",),
            index, False, ("protected-delivery",), ("scope-drift",),
            ProposalProvenance(
                derivation_id, snapshot.id, snapshot.digest, "fixture-v1", "fixture", None,
                (f"repository-truth:{scope}",),
            ),
        ) for index, scope in enumerate(self.scopes, 1))
        durable_result_sink(ProviderDerivationResponse(
            ProviderInvocationEvidence(
                "fixture", None, "fixture-v1", _digest({"derivation": derivation_id,
                    "snapshot": snapshot.digest, "authority": attempt_authority_id}),
                snapshot.digest, _digest({"proposals": [item.semantic_digest() for item in proposals]}),
                ProviderSideEffectState.HAPPENED_AND_CONFIRMED, status="completed",
            ), proposals=proposals,
        ))
        return proposals


class _Host:
    def __init__(self) -> None:
        self.config = SimpleNamespace(host_id="engineering-platform", project_id="forge", repository_id="forge",
                                      repository_identity="forge")
        self.dispatches = {}
        self.requests = []
        self.evidence_reads = 0
        self.return_evidence = False
        self.terminal_evidence_remaining = None
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
        if self.terminal_evidence_remaining is not None:
            if self.terminal_evidence_remaining < 1:
                return None
            self.terminal_evidence_remaining -= 1
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
    def test_held_failed_attempt_does_not_block_a_different_selected_mission(self) -> None:
        runtime = object.__new__(InstalledDynamicMissionRuntime)
        held = SimpleNamespace(
            mission_id="MISSION-0006", status=MissionExecutionStatus.BLOCKED,
            actions=(), intents=(), execution_correlation=None,
        )
        selected = SimpleNamespace(mission_id="MISSION-0007", status=MissionExecutionStatus.APPROVED_PLANNABLE)
        runtime.states = SimpleNamespace(resumable=lambda: (held, selected))
        runtime._assert_single_resumable(selected.mission_id)
        with self.assertRaises(InstalledDynamicMissionError):
            runtime._assert_single_resumable(held.mission_id)
        runtime.states = SimpleNamespace(resumable=lambda: (held,))
        runtime._assert_single_resumable(held.mission_id)

    def test_held_dispatcher_is_reconciled_before_new_mission_dispatch(self) -> None:
        held = SimpleNamespace(
            mission_id="MISSION-0006", status=MissionExecutionStatus.BLOCKED,
            actions=(), intents=(), execution_correlation=None,
        )
        selected = SimpleNamespace(
            mission_id="MISSION-0007", status=MissionExecutionStatus.CREATED,
            actions=(), intents=(), execution_correlation=None,
        )
        states = SimpleNamespace(
            get=lambda mission_id: {held.mission_id: held, selected.mission_id: selected}[mission_id],
            resumable=lambda: (held, selected),
        )
        self.runtime.database.save_dispatcher_state(
            status="ACTIVE", mission_sequence=(held.mission_id,), active_mission_id=held.mission_id,
        )
        self.runtime.states = states
        self.runtime._assert_single_resumable(selected.mission_id)
        dispatcher = _InstalledMissionDispatcher(
            self.runtime.database, states, selected.mission_id, lambda: "2026-09-11T16:00:00Z",
        )
        self.assertEqual(dispatcher.dispatch().mission_id, selected.mission_id)
        row = self.runtime.database._connection.execute(
            "SELECT status, active_mission_id FROM dispatcher_state WHERE singleton=1"
        ).fetchone()
        self.assertEqual((row["status"], row["active_mission_id"]), ("ACTIVE", selected.mission_id))
        with self.assertRaises(InstalledDynamicMissionError):
            self.runtime._assert_single_resumable(held.mission_id)

    def test_blocked_mission_with_host_effect_keeps_exclusive_dispatcher(self) -> None:
        held = SimpleNamespace(
            mission_id="MISSION-0006", status=MissionExecutionStatus.BLOCKED,
            actions=({"id": "ACTION-1"},), intents=(), execution_correlation={"host_run_id": "run-1"},
        )
        selected = SimpleNamespace(
            mission_id="MISSION-0007", status=MissionExecutionStatus.CREATED,
            actions=(), intents=(), execution_correlation=None,
        )
        states = SimpleNamespace(
            get=lambda mission_id: {held.mission_id: held, selected.mission_id: selected}[mission_id],
            resumable=lambda: (held, selected),
        )
        self.runtime.database.save_dispatcher_state(
            status="ACTIVE", mission_sequence=(held.mission_id,), active_mission_id=held.mission_id,
        )
        self.runtime.states = states
        with self.assertRaises(InstalledDynamicMissionError):
            self.runtime._assert_single_resumable(selected.mission_id)
        dispatcher = _InstalledMissionDispatcher(
            self.runtime.database, states, selected.mission_id, lambda: "2026-09-11T16:00:00Z",
        )
        with self.assertRaises(InstalledDynamicMissionError):
            dispatcher.dispatch()

    def test_two_runnable_missions_remain_excluded(self) -> None:
        runtime = object.__new__(InstalledDynamicMissionRuntime)
        first = SimpleNamespace(mission_id="MISSION-0007", status=MissionExecutionStatus.APPROVED_PLANNABLE)
        second = SimpleNamespace(mission_id="MISSION-0008", status=MissionExecutionStatus.CREATED)
        runtime.states = SimpleNamespace(resumable=lambda: (first, second))
        with self.assertRaises(InstalledDynamicMissionError):
            runtime._assert_single_resumable(first.mission_id)

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

    def _mission_and_envelope(self, *, two_repositories: bool = False,
                              repository_scopes: tuple[str, str] | None = None,
                              identity_suffix: str = "", maximum_no_progress: int = 2):
        repository, context = self.runtime.repository, self.runtime.repository.operators.context()
        contracts = (CriterionAssessmentContract(
            "status contract declares durable-state provenance", (CriterionEvidenceRequirement(
                "durable-status-source", kind="repository_json", artifact_path="contract.json",
                json_pointer="/source", expected_json='"durable-state"',
            ),)),)
        scope = ((repository_scopes or ("repository-a", "repository-b")) if two_repositories
                 else ("durable-status-projection",))
        sources = tuple(ApprovedRepositoryEvidenceSource(
            item, item if "/" in item else f"example/{item}")
                        for item in scope) if two_repositories else ()
        source = (sources[0] if two_repositories else
                  ApprovedRepositoryEvidenceSource("forge", "synthetic/forge"))
        planning = ArchitecturePlanningEvidence(
            scope, ("NONE",) if two_repositories else ("forge/__main__.py",),
            ("no unrelated runtime work",),
            ("scope-drift",), ("protected-delivery",), ("ep-v1.2",), 16_000, 4_000, "1",
            criterion_assessment_contracts=contracts, maximum_actions=4,
            maximum_consecutive_no_progress_actions=maximum_no_progress, repository_evidence_source=source,
            repository_evidence_sources=sources,
        )
        business = BusinessWorkspace.for_runtime(self.runtime.database, repository, context)
        architecture = ArchitectureWorkspace.for_runtime(self.runtime.database, repository, context)
        candidate_id = "candidate-status-projection" + identity_suffix
        business_decision_id = "business-status-projection" + identity_suffix
        architecture_decision_id = "architecture-status-projection" + identity_suffix
        business.approve(
            decision_id=business_decision_id, candidate_id=candidate_id, revision="1",
            scope=planning.scope, gates=planning.human_gates,
        )
        architecture.approve(
            decision_id=architecture_decision_id, candidate_id=candidate_id, revision="1",
            planning=planning,
        )
        envelope = MissionPlanningEvidenceEnvelope.compose(
            repository, subject_id=candidate_id, subject_revision="1",
            business_decision_id=business_decision_id, architecture_decision_id=architecture_decision_id,
            planning=planning,
        )
        mission_id = self.runtime.database.allocate_next_mission_id(
            source="canonical-governance-envelope:" + envelope.digest, allocated_at="2026-09-11T16:00:00Z",
        )
        mission = ArchitectureMission(
            mission_id, candidate_id, "Durable status projection", "Expose durable dispatcher posture.",
            "Expose a safe status projection.", "Operators can inspect durable state.", architecture_decision_id,
            candidate_id, scope, ("no unrelated runtime work",),
            ("status contract declares durable-state provenance",), ("configured EP v1.2",), ("ep-v1.2",),
            ("status-projection",), (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("scope-drift",),
            ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
            criterion_assessment_contracts=contracts, maximum_actions=4,
            maximum_consecutive_no_progress_actions=maximum_no_progress, repository_evidence_source=source,
            repository_evidence_sources=sources,
        )
        return mission, envelope

    def _admit(self, mission, envelope, *, mode="continuous"):
        admitted = self.runtime.admit(mission, envelope)
        self.runtime.assign_progression_policy(mission.id, {
            "assignment_id": "progression-assignment-" + mission.id.lower(),
            "profile_id": "solo",
            "profile_revision": "1", "policy_revision": "1", "mode": mode,
            "required_decision_role": "platform_architect",
            "higher_scope_obligations": ["protected-delivery"],
            "expected_state_revision": admitted.revision,
        })
        return admitted

    def _progression_principal(self) -> str:
        context = self.runtime.repository.operators.context()
        return "local-operator:v1:" + self.runtime.repository._operator_id(context)

    @staticmethod
    def _truth() -> RepositoryTruthSnapshot:
        return RepositoryTruthSnapshot(
            "forge-initial-truth", "forge", "a" * 40, "2026-09-11T16:00:00Z",
            (RepositoryTruthEvidence(
                "forge-main", "git_commit", "a" * 40, "https://example.invalid/forge",
                "sha256:" + "b" * 64,
            ),),
        )

    def _materialized_no_dispatch(self):
        self.provider = _TwoRepositoryProvider()
        self.runtime.provider = self.provider
        self.host.config = SimpleNamespace(
            base_url="http://127.0.0.1:1", bearer_token="private-fixture",
            expected_instance_id="ep-fixture-1", project_id="project-fixture-1",
            expected_consumer_id="forge-consumer", peer_binding_id="peer-fixture",
            peer_configuration_revision=1, peer_configuration_digest="sha256:" + "e" * 64,
            allow_loopback_http=True, timeout=1.0,
        )
        mission, envelope = self._mission_and_envelope(two_repositories=True)
        self.runtime.admit(mission, envelope)
        heads = {"example/repository-a": "a" * 40, "example/repository-b": "b" * 40}
        selected_peer = SimpleNamespace(
            endpoint=self.host.config.base_url,
            expected_ep_instance_id=self.host.config.expected_instance_id,
            ep_project_id=self.host.config.project_id,
            ep_consumer_id=self.host.config.expected_consumer_id,
            binding_id=self.host.config.peer_binding_id,
            configuration_revision=self.host.config.peer_configuration_revision,
            configuration_digest=self.host.config.peer_configuration_digest,
        )
        with patch("forge.mission_cli._github_default_head", side_effect=lambda name: ("main", heads[name])), \
             patch("forge.runtime.dynamic_mission.read_repository_authority",
                   side_effect=lambda _scope, *, repository_id, **_: authority(repository_id)), \
             patch("forge.runtime.action_intents.read_repository_authority",
                   side_effect=lambda _scope, *, repository_id, **_: authority(repository_id)), \
             patch("forge.execution_host_configuration.EngineeringPlatformExecutionHostFactory.from_database",
                   return_value=self.host), \
             patch("forge.runtime.dynamic_mission.EngineeringPlatformPeerConfigurationStore.load",
                   return_value=selected_peer):
            result = self.runtime.derive_two_repository_actions(mission.id)
        self.assertEqual(result.status, "ACTIONS_MATERIALIZED_NO_DISPATCH")
        return mission, result

    def test_public_lifecycle_archives_quiescent_no_dispatch_mission_and_replays(self) -> None:
        mission, result = self._materialized_no_dispatch()
        successor, envelope = self._mission_and_envelope(
            two_repositories=True, identity_suffix="-successor",
        )
        self._admit(successor, envelope)
        with self.assertRaisesRegex(InstalledDynamicMissionError, "exactly one selected non-terminal Mission"):
            self.runtime._assert_single_resumable(successor.id)
        service = MissionLifecycleService(self.runtime.repository)
        expected_instance = self.runtime.database.runtime_identity.runtime_id
        archived = service.archive_quiescent_no_dispatch(
            mission.id, expected_instance_id=expected_instance, expected_revision=2,
            reason_code="historical_no_dispatch_reconciled", correlation_id="lifecycle-test-1",
            occurred_at="2026-09-11T17:00:00Z",
        )
        self.assertEqual(archived.status, "ARCHIVED")
        self.assertEqual(archived.revision, 3)
        self.assertEqual(archived.to_dict()["archived_is_completion"], False)
        self.assertEqual(archived.to_dict()["host_dispatched"], False)
        state = self.runtime.states.get(mission.id)
        self.assertEqual(tuple(item["id"] for item in state.actions), result.action_ids)
        self.assertEqual(len(state.intents), 2)
        audit = state.state_history[-1]["administrative_audit"]
        self.assertEqual(audit["operator_reference"], archived.operator_reference)
        self.assertEqual(
            audit["authenticated_principal_reference"],
            "local-operator:v1:" + archived.operator_reference,
        )
        self.runtime.close()
        self.runtime = self._open_runtime()
        service = MissionLifecycleService(self.runtime.repository)
        replay = service.archive_quiescent_no_dispatch(
            mission.id, expected_instance_id=expected_instance, expected_revision=2,
            reason_code="historical_no_dispatch_reconciled", correlation_id="lifecycle-test-1",
            occurred_at="2026-09-11T17:01:00Z",
        )
        self.assertEqual(replay, archived)
        log = self.runtime.database._connection.execute(
            "SELECT correlation_id,operator_reference,details FROM forge_operational_logs "
            "WHERE mission_id=? AND event='mission_state_transitioned' AND correlation_id=? LIMIT 1",
            (mission.id, "lifecycle-test-1"),
        ).fetchone()
        self.assertEqual(log["correlation_id"], "lifecycle-test-1")
        self.assertTrue(log["operator_reference"])
        self.assertEqual(json.loads(log["details"])["operation"], "archive_quiescent_no_dispatch")
        self.assertEqual(
            json.loads(log["details"])["authenticated_principal_reference"],
            archived.authenticated_principal_reference,
        )

        self.runtime._assert_single_resumable(successor.id)

    def test_public_lifecycle_fails_closed_on_wrong_stale_or_conflicting_request(self) -> None:
        mission, _ = self._materialized_no_dispatch()
        service = MissionLifecycleService(self.runtime.repository)
        instance_id = self.runtime.database.runtime_identity.runtime_id
        requests = (
            {"expected_instance_id": "wrong-instance", "expected_revision": 2,
             "reason_code": "historical_no_dispatch_reconciled", "correlation_id": "lifecycle-test-2"},
            {"expected_instance_id": instance_id, "expected_revision": 1,
             "reason_code": "historical_no_dispatch_reconciled", "correlation_id": "lifecycle-test-2"},
        )
        for request in requests:
            with self.subTest(request=request), self.assertRaises(MissionLifecycleError):
                service.archive_quiescent_no_dispatch(
                    mission.id, occurred_at="2026-09-11T17:00:00Z", **request,
                )
        archived = service.archive_quiescent_no_dispatch(
            mission.id, expected_instance_id=instance_id, expected_revision=2,
            reason_code="historical_no_dispatch_reconciled", correlation_id="lifecycle-test-2",
            occurred_at="2026-09-11T17:00:00Z",
        )
        self.assertEqual(archived.status, "ARCHIVED")
        with self.assertRaisesRegex(MissionLifecycleError, "different operation"):
            service.archive_quiescent_no_dispatch(
                mission.id, expected_instance_id=instance_id, expected_revision=2,
                reason_code="historical_no_dispatch_reconciled", correlation_id="lifecycle-test-other",
                occurred_at="2026-09-11T17:01:00Z",
            )

        row = self.runtime.database._connection.execute(
            "SELECT document FROM mission_state WHERE mission_id=?", (mission.id,),
        ).fetchone()
        corrupted = json.loads(row["document"])
        corrupted["actions"][0]["revision"] = 99
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "UPDATE mission_state SET document=? WHERE mission_id=?",
                (json.dumps(corrupted, sort_keys=True, separators=(",", ":")), mission.id),
            )
        with self.assertRaisesRegex(MissionLifecycleError, "lineage differs"):
            service.archive_quiescent_no_dispatch(
                mission.id, expected_instance_id=instance_id, expected_revision=2,
                reason_code="historical_no_dispatch_reconciled", correlation_id="lifecycle-test-2",
                occurred_at="2026-09-11T17:02:00Z",
            )

    def test_public_lifecycle_replay_rejects_corrupt_archive_transition_receipt(self) -> None:
        mission, _ = self._materialized_no_dispatch()
        service = MissionLifecycleService(self.runtime.repository)
        request = dict(
            expected_instance_id=self.runtime.database.runtime_identity.runtime_id,
            expected_revision=2, reason_code="historical_no_dispatch_reconciled",
            correlation_id="lifecycle-test-transition", occurred_at="2026-09-11T17:00:00Z",
        )
        service.archive_quiescent_no_dispatch(mission.id, **request)
        row = self.runtime.database._connection.execute(
            "SELECT document FROM mission_state WHERE mission_id=?", (mission.id,),
        ).fetchone()
        corrupted = json.loads(row["document"])
        corrupted["state_history"][-1].update({
            "sequence": 999,
            "to_status": "FAILED",
            "reason": "corrupt-reason",
            "occurred_at": "1900-01-01T00:00:00Z",
        })
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "UPDATE mission_state SET document=? WHERE mission_id=?",
                (json.dumps(corrupted, sort_keys=True, separators=(",", ":")), mission.id),
            )
        with self.assertRaisesRegex(MissionLifecycleError, "different operation"):
            service.archive_quiescent_no_dispatch(mission.id, **request)

    def test_public_lifecycle_fails_closed_on_authority_activity_or_uncertain_lineage(self) -> None:
        mission, _ = self._materialized_no_dispatch()
        service = MissionLifecycleService(self.runtime.repository)
        request = dict(
            expected_instance_id=self.runtime.database.runtime_identity.runtime_id,
            expected_revision=2, reason_code="historical_no_dispatch_reconciled",
            correlation_id="lifecycle-test-3", occurred_at="2026-09-11T17:00:00Z",
        )
        with patch.object(self.runtime.repository.operators, "authorize", return_value=False), \
             self.assertRaises(PermissionError):
            service.archive_quiescent_no_dispatch(mission.id, **request)
        with patch.object(self.runtime.database, "has_active_mission_dispatch", return_value=True), \
             self.assertRaisesRegex(MissionLifecycleError, "active dispatch"):
            service.archive_quiescent_no_dispatch(mission.id, **request)
        with patch.object(self.runtime.database, "durable_action_derivation_readback", return_value=()), \
             self.assertRaisesRegex(MissionLifecycleError, "incomplete or uncertain"):
            service.archive_quiescent_no_dispatch(mission.id, **request)
        row = self.runtime.database._connection.execute(
            "SELECT document FROM mission_state WHERE mission_id=?", (mission.id,),
        ).fetchone()
        completed = json.loads(row["document"])
        completed["completion_history"] = [{"assessment": "historical"}]
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "UPDATE mission_state SET document=? WHERE mission_id=?",
                (json.dumps(completed, sort_keys=True, separators=(",", ":")), mission.id),
            )
        with self.assertRaisesRegex(MissionLifecycleError, "completion"):
            service.archive_quiescent_no_dispatch(mission.id, **request)

    def test_public_lifecycle_replay_rechecks_all_quiescence_evidence(self) -> None:
        mission, _ = self._materialized_no_dispatch()
        service = MissionLifecycleService(self.runtime.repository)
        request = dict(
            expected_instance_id=self.runtime.database.runtime_identity.runtime_id,
            expected_revision=2, reason_code="historical_no_dispatch_reconciled",
            correlation_id="lifecycle-test-4", occurred_at="2026-09-11T17:00:00Z",
        )
        service.archive_quiescent_no_dispatch(mission.id, **request)
        row = self.runtime.database._connection.execute(
            "SELECT document FROM mission_state WHERE mission_id=?", (mission.id,),
        ).fetchone()
        active = json.loads(row["document"])
        active["delegations"] = [{"id": "delegation-after-archive", "status": "ACTIVE"}]
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "UPDATE mission_state SET document=? WHERE mission_id=?",
                (json.dumps(active, sort_keys=True, separators=(",", ":")), mission.id),
            )
        with self.assertRaisesRegex(MissionLifecycleError, "activity"):
            service.archive_quiescent_no_dispatch(mission.id, **request)


    def test_after_action_policy_fences_provider_and_exact_approval_resumes_once(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-governed-continuation", maximum_no_progress=3)
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        waiting = self.runtime.start(mission.id, self._truth())
        self.assertEqual(waiting.status, "WAITING_FOR_EVIDENCE")
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1

        paused = self.runtime.resume(mission.id)

        self.assertEqual(paused.status, "AWAITING_APPROVAL")
        self.assertEqual(self.provider.calls, 1)
        requirement = self.runtime.progression_status(mission.id)["decision_requirement"]
        self.assertEqual(requirement["schema_version"], "forge-decision-requirement/v1")
        self.assertEqual(requirement["completed_action_id"], waiting.action_ids[0])
        self.assertEqual(requirement["status"], "PENDING")
        decision = {
            "schema_version": "forge-progression-decision/v1",
            "decision_id": "decision-governed-continuation-001",
            "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": requirement["policy_revision"],
            "decision": "approve", "reason": "Exact terminal evidence permits the bounded successor.",
        }
        continued = self.runtime.decide_progression(
            mission.id, decision, authenticated_principal_reference=self._progression_principal(),
        )
        self.assertEqual(continued.status, "WAITING_FOR_EVIDENCE", self.runtime.states.get(mission.id).waiting_reason)
        self.assertEqual(self.provider.calls, 2)
        replayed = self.runtime.decide_progression(
            mission.id, decision, authenticated_principal_reference=self._progression_principal(),
        )
        self.assertEqual(replayed.status, "WAITING_FOR_EVIDENCE")
        self.assertEqual(self.provider.calls, 2)
        state = self.runtime.states.get(mission.id)
        self.assertEqual(state.resume["continuation_history"][0]["status"], "CONSUMED")
        self.assertEqual(state.mission["status"], "approved_for_engineering")
        self.assertNotIn("final_acceptance", state.mission)

    def test_continuous_policy_advances_successor_without_human_prompt(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-continuous-successor", maximum_no_progress=3)
        self._admit(mission, envelope, mode="continuous")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        waiting = self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1
        continued = self.runtime.resume(mission.id)
        self.assertEqual(continued.status, "WAITING_FOR_EVIDENCE", self.runtime.states.get(mission.id).waiting_reason)
        self.assertEqual(self.provider.calls, 2)
        self.assertEqual(len(self.host.requests), 2)
        self.assertIsNone(self.runtime.progression_status(mission.id)["decision_requirement"])

    def _assert_nonapproving_progression_decision(self, outcome: str) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-" + outcome)
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        paused = self.runtime.resume(mission.id)
        requirement = self.runtime.progression_status(mission.id)["decision_requirement"]
        decision = {
            "schema_version": "forge-progression-decision/v1",
            "decision_id": "decision-" + outcome + "-001",
            "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": requirement["policy_revision"],
            "decision": outcome, "reason": "Exercise exact non-approval semantics.",
        }
        result = self.runtime.decide_progression(
            mission.id, decision, authenticated_principal_reference=self._progression_principal(),
        )
        self.assertEqual(paused.status, "AWAITING_APPROVAL")
        self.assertEqual(result.status, "AWAITING_APPROVAL")
        self.assertEqual(self.provider.calls, 1)
        replacement = {
            **decision, "decision_id": decision["decision_id"] + "-replacement",
            "decision": "approve", "reason": "A second decision cannot replace the immutable first one.",
        }
        with self.assertRaisesRegex(InstalledDynamicMissionError, "already has a canonical decision"):
            self.runtime.decide_progression(
                mission.id, replacement, authenticated_principal_reference=self._progression_principal(),
            )
        self.assertEqual(self.provider.calls, 1)

    def test_reject_keeps_successor_fenced(self) -> None:
        self._assert_nonapproving_progression_decision("reject")

    def test_defer_keeps_successor_fenced(self) -> None:
        self._assert_nonapproving_progression_decision("defer")

    def test_amend_requires_reconciliation_and_keeps_successor_fenced(self) -> None:
        self._assert_nonapproving_progression_decision("amend")

    def test_stale_progression_decision_fails_without_provider_use(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-stale-decision")
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.runtime.resume(mission.id)
        requirement = self.runtime.progression_status(mission.id)["decision_requirement"]
        request = {
            "schema_version": "forge-progression-decision/v1",
            "decision_id": "decision-stale-001", "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": "sha256:" + "0" * 64,
            "policy_revision": requirement["policy_revision"],
            "decision": "approve", "reason": "This stale evidence must be rejected.",
        }
        with self.assertRaisesRegex(InstalledDynamicMissionError, "stale or bound to another subject"):
            self.runtime.decide_progression(
                mission.id, request, authenticated_principal_reference=self._progression_principal(),
            )
        self.assertEqual(self.provider.calls, 1)

    def test_simultaneous_progression_decision_fails_before_mutation(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-busy-decision")
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1
        self.runtime.resume(mission.id)
        requirement = self.runtime.progression_status(mission.id)["decision_requirement"]
        request = {
            "schema_version": "forge-progression-decision/v1",
            "decision_id": "decision-busy-001", "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": requirement["policy_revision"],
            "decision": "approve", "reason": "Exercise the single-writer mutation lease.",
        }
        with RuntimeServiceLock(self.runtime.database.path).acquire(), self.assertRaises(RuntimeServiceBusy):
            self.runtime.decide_progression(
                mission.id, request, authenticated_principal_reference=self._progression_principal(),
            )
        self.assertIsNone(self.runtime.progression_status(mission.id)["decision"])
        self.assertEqual(self.provider.calls, 1)

    def test_cli_progression_decision_binds_the_current_local_operator(self) -> None:
        captured: dict[str, object] = {}

        class _Runtime:
            database = SimpleNamespace(path=Path(self.root) / "forge.db")
            repository = SimpleNamespace(
                operators=SimpleNamespace(
                    context=lambda: SimpleNamespace(installation_id="installation", generated_uid="operator", binding_version=1),
                    authorize=lambda _context: True,
                ),
                _operator_id=lambda _context: "operator-fingerprint",
            )

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def decide_progression(self, mission_id, document, *, authenticated_principal_reference):
                captured.update({
                    "mission_id": mission_id, "document": document,
                    "principal": authenticated_principal_reference,
                })
                return {"status": "AWAITING_APPROVAL"}

        decision_path = Path(self.temporary.name) / "decision.json"
        decision_path.write_text(json.dumps({"schema_version": "forge-progression-decision/v1"}))
        with patch.object(InstalledDynamicMissionRuntime, "open", return_value=_Runtime()), \
             patch.object(mission_cli, "require_no_controller"), \
             patch.object(mission_cli, "asdict", side_effect=lambda value: value):
            result = mission_cli.progression_decide(str(self.root), "MISSION-0001", str(decision_path))
        self.assertEqual(result["status"], "AWAITING_APPROVAL")
        self.assertEqual(captured["principal"], "local-operator:v1:operator-fingerprint")
        self.assertEqual(captured["mission_id"], "MISSION-0001")

    def test_packaged_cli_exposes_policy_status_and_decision_routes(self) -> None:
        cases = (
            ("progression-policy", "progression_policy", ["--input", "policy.json"]),
            ("progression-status", "progression_status", []),
            ("progression-decide", "progression_decide", ["--input", "decision.json"]),
        )
        for command, function, trailing in cases:
            with self.subTest(command=command), \
                 patch.object(mission_cli, function, return_value={"route": command}) as invoked, \
                 redirect_stdout(StringIO()) as output:
                result = forge_main([
                    "--data-root", str(self.root), "mission", command,
                    "--mission-id", "MISSION-0001", *trailing,
                ])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue()), {"route": command})
            expected = [str(self.root), "MISSION-0001"]
            if trailing:
                expected.append(trailing[-1])
            invoked.assert_called_once_with(*expected)

    def test_packaged_cli_fails_closed_when_mutating_commands_lack_a_data_root(self) -> None:
        commands = (
            ["server", "run", "--credential-file", "credential", "--port", "8765"],
            ["server", "provider-context", "show"],
            ["server", "update-assess", "--runtime-id", "runtime", "--installation-id", "install",
             "--installed-version", "1.0.0", "--installed-source", "source",
             "--installed-artifact-digest", "sha256:" + "1" * 64,
             "--candidate-version", "1.0.1", "--candidate-source", "candidate",
             "--candidate-wheel", "candidate.whl", "--candidate-artifact-digest", "sha256:" + "2" * 64],
            ["health", "snapshot"],
            ["mission", "approve-business", "--input", "mission.json"],
            ["mission", "admit", "--input", "mission.json"],
            ["mission", "progression-policy", "--mission-id", "MISSION-0001", "--input", "policy.json"],
            ["mission", "progression-status", "--mission-id", "MISSION-0001"],
            ["mission", "progression-decide", "--mission-id", "MISSION-0001", "--input", "decision.json"],
            ["operations-api", "--credential-file", "credential"],
        )
        for command in commands:
            with self.subTest(command=command), redirect_stdout(StringIO()) as output:
                result = forge_main(command)
            self.assertEqual(result, 1)
            self.assertEqual(json.loads(output.getvalue())["status"], "ERROR")

    def test_packaged_cli_initializes_and_reads_the_exact_runtime(self) -> None:
        with redirect_stdout(StringIO()) as initialized:
            self.assertEqual(forge_main(["--data-root", str(self.root), "server", "init"]), 0)
        self.assertTrue(json.loads(initialized.getvalue())["initialized"])
        with redirect_stdout(StringIO()) as status:
            self.assertEqual(forge_main(["--data-root", str(self.root), "status"]), 0)
        self.assertEqual(json.loads(status.getvalue())["data_root"], str(self.root.resolve()))

    def test_cli_policy_and_status_use_the_selected_runtime_without_side_effect_adapters(self) -> None:
        captured: dict[str, object] = {}

        class _Runtime:
            database = SimpleNamespace(path=Path(self.root) / "forge.db")

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def assign_progression_policy(self, mission_id, document):
                captured.update({"mission_id": mission_id, "policy": document})
                return {"status": "ASSIGNED"}

            def progression_status(self, mission_id):
                captured["status_mission_id"] = mission_id
                return {"read_only": True}

        policy_path = Path(self.temporary.name) / "policy.json"
        policy_path.write_text(json.dumps({"schema_version": "forge-progression-policy-assignment/v1"}))
        with patch.object(InstalledDynamicMissionRuntime, "open", return_value=_Runtime()), \
             patch.object(mission_cli, "require_no_controller"), \
             patch.object(mission_cli, "RuntimeServiceLock"):
            assigned = mission_cli.progression_policy(str(self.root), "MISSION-0001", str(policy_path))
            status = mission_cli.progression_status(str(self.root), "MISSION-0001")
        self.assertEqual(assigned["status"], "ASSIGNED")
        self.assertTrue(status["read_only"])
        self.assertEqual(captured["mission_id"], "MISSION-0001")
        self.assertEqual(captured["status_mission_id"], "MISSION-0001")

    def test_progression_policy_assignment_replays_without_mutation(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-policy-replay")
        admitted = self.runtime.admit(mission, envelope)
        request = {
            "assignment_id": "progression-assignment-policy-replay",
            "profile_id": "solo", "profile_revision": "1", "policy_revision": "1",
            "mode": "continuous", "required_decision_role": "platform_architect",
            "higher_scope_obligations": ["protected-delivery"],
            "expected_state_revision": admitted.revision,
        }
        assigned = self.runtime.assign_progression_policy(mission.id, request)
        replayed = self.runtime.assign_progression_policy(mission.id, request)
        self.assertEqual(assigned["mission_revision"], replayed["mission_revision"])
        self.assertEqual(replayed["status"], "REPLAYED")
        self.assertEqual(self.provider.calls, 0)

    def test_progression_policy_rejects_noncanonical_profile_mode_and_role(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-policy-resolution")
        admitted = self.runtime.admit(mission, envelope)
        base = {
            "assignment_id": "progression-assignment-policy-resolution",
            "profile_id": "solo", "profile_revision": "1", "policy_revision": "1",
            "mode": "continuous", "required_decision_role": "platform_architect",
            "higher_scope_obligations": ["protected-delivery"],
            "expected_state_revision": admitted.revision,
        }
        for changed, message in (
            ({"profile_id": "enterprise"}, "canonical Solo profile"),
            ({"required_decision_role": "engineering_lead"}, "canonical profile"),
        ):
            with self.subTest(changed=changed), self.assertRaisesRegex(
                InstalledDynamicMissionError, message,
            ):
                self.runtime.assign_progression_policy(mission.id, {**base, **changed})
        self.assertEqual(self.provider.calls, 0)

    def test_progression_policy_assignment_recovers_after_state_write_interruption(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-policy-write-recovery")
        admitted = self.runtime.admit(mission, envelope)
        request = {
            "assignment_id": "progression-assignment-policy-write-recovery",
            "profile_id": "solo", "profile_revision": "1", "policy_revision": "1",
            "mode": "after_action", "required_decision_role": "platform_architect",
            "higher_scope_obligations": ["protected-delivery"],
            "expected_state_revision": admitted.revision,
        }
        with patch.object(
            self.runtime.states, "assign_progression_policy",
            side_effect=RuntimeError("injected state write interruption"),
        ), self.assertRaisesRegex(RuntimeError, "injected"):
            self.runtime.assign_progression_policy(mission.id, request)
        recovered = self.runtime.assign_progression_policy(mission.id, request)
        self.assertEqual(recovered["status"], "ASSIGNED")
        self.assertEqual(self.runtime.states.get(mission.id).revision, admitted.revision + 1)
        rows = self.runtime.database._connection.execute(
            "SELECT decision_id FROM governance_decisions WHERE decision_id=?",
            (request["assignment_id"],),
        ).fetchall()
        self.assertEqual(len(rows), 1)

    def test_pending_fence_survives_restart_and_status_is_effect_free(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-pending-restart")
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1
        self.runtime.resume(mission.id)
        before = self.runtime.progression_status(mission.id)
        self.assertIsNone(before["decision"])
        self.assertEqual(self.provider.calls, 1)
        self.runtime.close()
        self.runtime = self._open_runtime()
        after = self.runtime.progression_status(mission.id)
        self.assertEqual(after["decision_requirement"], before["decision_requirement"])
        self.assertEqual(self.provider.calls, 1)

    def test_revoked_authority_blocks_ready_intent_before_successor_provider(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-revoked-successor")
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1
        self.runtime.resume(mission.id)
        requirement = self.runtime.progression_status(mission.id)["decision_requirement"]
        decision = {
            "schema_version": "forge-progression-decision/v1",
            "decision_id": "decision-revoked-successor-001",
            "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": requirement["policy_revision"],
            "decision": "approve", "reason": "Persist an exact intent before revocation.",
        }
        self.runtime._keep_running = lambda: False
        persisted = self.runtime.decide_progression(
            mission.id, decision, authenticated_principal_reference=self._progression_principal(),
        )
        self.assertEqual(persisted.status, "ACTIVE")
        self.assertEqual(self.runtime.states.get(mission.id).resume["continuation_intent"]["status"], "READY")
        self.runtime._keep_running = lambda: True
        with patch.object(self.runtime.repository.operators, "authorize", return_value=False), \
             self.assertRaisesRegex(Exception, "not authorized"):
            self.runtime.resume(mission.id)
        self.assertEqual(self.provider.calls, 1)

    def test_restart_after_intent_start_reuses_same_approval_and_successor(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-intent-start-restart")
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1
        self.runtime.resume(mission.id)
        requirement = self.runtime.progression_status(mission.id)["decision_requirement"]
        decision = {
            "schema_version": "forge-progression-decision/v1",
            "decision_id": "decision-intent-start-restart-001",
            "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": requirement["policy_revision"],
            "decision": "approve", "reason": "Exercise the durable in-progress fence.",
        }
        from forge.execution.loop import ExecutionLoop
        with patch.object(ExecutionLoop, "_replan_after_evidence", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.runtime.decide_progression(
                    mission.id, decision, authenticated_principal_reference=self._progression_principal(),
                )
        interrupted = self.runtime.states.get(mission.id)
        intent_id = interrupted.resume["continuation_intent"]["intent_id"]
        self.assertEqual(interrupted.resume["continuation_intent"]["status"], "IN_PROGRESS")
        self.runtime.close()
        self.runtime = self._open_runtime()
        resumed = self.runtime.resume(mission.id)
        self.assertEqual(resumed.status, "WAITING_FOR_EVIDENCE")
        self.assertEqual(self.provider.calls, 2)
        history = self.runtime.states.get(mission.id).resume["continuation_history"]
        self.assertEqual([item["intent_id"] for item in history], [intent_id])

    def test_lost_decision_response_replays_after_restart_and_resumes_once(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-decision-restart")
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1
        self.runtime.resume(mission.id)
        requirement = self.runtime.progression_status(mission.id)["decision_requirement"]
        decision = {
            "schema_version": "forge-progression-decision/v1",
            "decision_id": "decision-lost-response-001",
            "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": requirement["policy_revision"],
            "decision": "approve", "reason": "Resume the exact reviewed successor.",
        }
        recorded = GovernedContinuationService(
            self.runtime.database, self.runtime.repository, self.runtime.states, self.runtime.clock,
        ).decide(mission.id, decision, authenticated_principal_reference=self._progression_principal())
        self.assertTrue(recorded["resume_authorized"])
        self.assertEqual(self.runtime.progression_status(mission.id)["decision"]["decision"], "approve")
        self.runtime.close()
        self.runtime = self._open_runtime()
        resumed = self.runtime.decide_progression(
            mission.id, decision, authenticated_principal_reference=self._progression_principal(),
        )
        self.assertEqual(resumed.status, "WAITING_FOR_EVIDENCE")
        self.assertEqual(self.provider.calls, 2)
        self.runtime.decide_progression(
            mission.id, decision, authenticated_principal_reference=self._progression_principal(),
        )
        self.assertEqual(self.provider.calls, 2)

    def test_revoked_decision_capability_and_wrong_replay_principal_fail_closed(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-revoked-decision")
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1
        self.runtime.resume(mission.id)
        requirement = self.runtime.progression_status(mission.id)["decision_requirement"]
        decision = {
            "schema_version": "forge-progression-decision/v1",
            "decision_id": "decision-revoked-001",
            "requirement_id": requirement["requirement_id"],
            "subject_digest": requirement["subject_digest"],
            "mission_state_revision": requirement["mission_state_revision"],
            "evidence_digest": requirement["evidence_digest"],
            "policy_revision": requirement["policy_revision"],
            "decision": "approve", "reason": "Exercise current authority enforcement.",
        }
        service = GovernedContinuationService(
            self.runtime.database, self.runtime.repository, self.runtime.states, self.runtime.clock,
        )
        service.decide(mission.id, decision, authenticated_principal_reference=self._progression_principal())
        with self.assertRaisesRegex(InstalledDynamicMissionError, "principal does not bind"):
            self.runtime.decide_progression(
                mission.id, decision, authenticated_principal_reference="different-admin-principal",
            )
        self.assertEqual(self.provider.calls, 1)
        with patch.object(self.runtime.repository.operators, "authorize", return_value=False), \
             self.assertRaisesRegex(InstalledDynamicMissionError, "not authorized"):
            self.runtime.decide_progression(
                mission.id, decision, authenticated_principal_reference=self._progression_principal(),
            )
        self.assertEqual(self.runtime.states.get(mission.id).status.value, "AWAITING_APPROVAL")
        self.assertEqual(self.provider.calls, 1)

    def test_tampered_policy_assignment_fails_before_provider_or_host(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-tampered-policy")
        self._admit(mission, envelope)
        row = self.runtime.database._connection.execute(
            "SELECT document FROM mission_state WHERE mission_id=?", (mission.id,),
        ).fetchone()
        document = json.loads(row["document"])
        document["execution_policy"]["decision_digest"] = "sha256:" + "0" * 64
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "UPDATE mission_state SET document=? WHERE mission_id=?",
                (json.dumps(document, sort_keys=True, separators=(",", ":")), mission.id),
            )
        with self.assertRaisesRegex(InstalledDynamicMissionError, "canonical assignment decision"):
            self.runtime.start(mission.id, self._truth())
        self.assertEqual(self.provider.calls, 0)
        self.assertEqual(self.host.requests, [])

    def test_wrong_instance_or_mission_decision_fence_fails_closed(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-wrong-fence-subject")
        self._admit(mission, envelope, mode="after_action")
        self.runtime._criterion_observer.reader = ExactRepositoryBytes(
            "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
        )
        self.runtime.start(mission.id, self._truth())
        self.host.return_evidence = True
        self.host.terminal_evidence_remaining = 1
        self.runtime.resume(mission.id)
        row = self.runtime.database._connection.execute(
            "SELECT document FROM mission_state WHERE mission_id=?", (mission.id,),
        ).fetchone()
        original = json.loads(row["document"])

        for field, value in (("instance_id", "another-runtime"), ("mission_id", "MISSION-WRONG")):
            tampered = json.loads(json.dumps(original))
            tampered["pause_reason"][field] = value
            with self.runtime.database._connection:
                self.runtime.database._connection.execute(
                    "UPDATE mission_state SET document=? WHERE mission_id=?",
                    (json.dumps(tampered, sort_keys=True, separators=(",", ":")), mission.id),
                )
            with self.subTest(field=field), self.assertRaisesRegex(
                InstalledDynamicMissionError, "another instance, Mission, or Action",
            ):
                self.runtime.progression_status(mission.id)
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "UPDATE mission_state SET document=? WHERE mission_id=?",
                (json.dumps(original, sort_keys=True, separators=(",", ":")), mission.id),
            )
        self.assertEqual(self.provider.calls, 1)

    def test_missing_progression_policy_fails_before_provider_or_host(self) -> None:
        mission, envelope = self._mission_and_envelope(identity_suffix="-missing-progression-policy")
        self.runtime.admit(mission, envelope)
        with self.assertRaisesRegex(InstalledDynamicMissionError, "policy assignment is missing"):
            self.runtime.start(mission.id, self._truth())
        self.assertEqual(self.provider.calls, 0)
        self.assertEqual(self.host.requests, [])

    def test_admits_zero_actions_then_reopens_same_installed_instance_to_reconcile_terminal_evidence(self) -> None:
        mission, envelope = self._mission_and_envelope()
        admitted = self._admit(mission, envelope)
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
        self.assertEqual(self.host.requests[-1].origin_identity, "synthetic/forge")
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
        self.host.managed_workspace_readiness = lambda: {
            "status": "BLOCKED", "known_blocker": "MANAGED_LEASE_ACTIVE",
            "repository_identity": "synthetic/forge",
        }
        complete = self.runtime.resume(mission.id)
        self.assertEqual(complete.runtime_id, runtime_id)
        self.assertEqual(complete.status, "AWAITING_APPROVAL")
        self.assertEqual(complete.planning_invocations, 1)
        state = self.runtime.states.get(mission.id)
        self.assertTrue(state.completion["all_required_criteria_proven"])
        self.assertEqual(state.execution_history[-1]["receipt_id"], "ep-receipt-status-projection")
        acceptance = self.runtime.progression_status(mission.id)["final_acceptance_requirement"]
        self.assertEqual(acceptance["schema_version"], "forge-final-acceptance-requirement/v1")
        self.assertEqual(acceptance["reason"], "mission_end_acceptance_required")

    def test_two_repository_derivation_is_atomic_durable_and_never_dispatches(self) -> None:
        self.provider = _TwoRepositoryProvider()
        self.runtime.provider = self.provider
        self.host.config = SimpleNamespace(
            base_url="http://127.0.0.1:1", bearer_token="private-fixture", expected_instance_id="ep-fixture-1",
            project_id="project-fixture-1", expected_consumer_id="forge-consumer", peer_binding_id="peer-fixture",
            peer_configuration_revision=1, peer_configuration_digest="sha256:" + "e" * 64,
            allow_loopback_http=True, timeout=1.0,
        )
        mission, envelope = self._mission_and_envelope(two_repositories=True)
        self.runtime.admit(mission, envelope)
        heads = {"example/repository-a": "a" * 40, "example/repository-b": "b" * 40}
        selected_peer = SimpleNamespace(
            endpoint=self.host.config.base_url, expected_ep_instance_id=self.host.config.expected_instance_id,
            ep_project_id=self.host.config.project_id, ep_consumer_id=self.host.config.expected_consumer_id,
            binding_id=self.host.config.peer_binding_id,
            configuration_revision=self.host.config.peer_configuration_revision,
            configuration_digest=self.host.config.peer_configuration_digest,
        )
        with patch("forge.mission_cli._github_default_head", side_effect=lambda name: ("main", heads[name])), \
             patch("forge.runtime.dynamic_mission.read_repository_authority",
                   side_effect=lambda _scope, *, repository_id, **_: authority(repository_id)), \
             patch("forge.runtime.action_intents.read_repository_authority",
                   side_effect=lambda _scope, *, repository_id, **_: authority(repository_id)), \
             patch("forge.execution_host_configuration.EngineeringPlatformExecutionHostFactory.from_database",
                   return_value=self.host), \
             patch("forge.runtime.dynamic_mission.EngineeringPlatformPeerConfigurationStore.load",
                   return_value=selected_peer):
            result = self.runtime.derive_two_repository_actions(mission.id)
            self.assertEqual(result.status, "ACTIONS_MATERIALIZED_NO_DISPATCH")
            self.assertEqual(len(result.action_ids), 2)
            self.assertEqual(self.provider.calls, 1)
            self.assertEqual(self.host.requests, [])
            snapshot = self.runtime.database.read_action_intents(mission.id)
            self.assertEqual(snapshot["source_freshness"], "CURRENT")
            self.assertEqual({item["target"]["repository_id"] for item in snapshot["actions"]},
                             {"repository-a", "repository-b"})
            self.assertTrue(all(item["target_verification"] == "PINNED_CURRENT_UNCHECKED"
                                for item in snapshot["actions"]))
            self.runtime.close()
            self.runtime = self._open_runtime()
            self.assertEqual(self.runtime.derive_two_repository_actions(mission.id), result)
            with patch("forge.runtime.action_intents.read_repository_authority",
                       side_effect=lambda _scope, *, repository_id, **_: authority(
                           repository_id, revision="2" if repository_id == "repository-b" else "1")):
                with self.assertRaisesRegex(RuntimeDatabaseError, "pinned Action authority"):
                    self.runtime.derive_two_repository_actions(mission.id)
            heads["example/repository-b"] = "c" * 40
            with self.assertRaisesRegex(RuntimeDatabaseError, "baseline differs"):
                self.runtime.derive_two_repository_actions(mission.id)
            heads["example/repository-b"] = "b" * 40
            self.host.config.peer_configuration_digest = "sha256:" + "f" * 64
            with self.assertRaisesRegex(RuntimeDatabaseError, "selected EP peer binding differs"):
                self.runtime.derive_two_repository_actions(mission.id)
            self.host.config.peer_configuration_digest = selected_peer.configuration_digest
            self.assertEqual(self.runtime.derive_two_repository_actions(mission.id), result)
        self.assertEqual(self.provider.calls, 1)
        self.assertEqual(self.host.requests, [])
        row = self.runtime.database._connection.execute(
            "SELECT document FROM mission_state WHERE mission_id=?", (mission.id,),
        ).fetchone()
        changed = json.loads(row[0])
        changed["actions"][0]["revision"] = "different-action-revision"
        with self.runtime.database._connection:
            self.runtime.database._connection.execute(
                "UPDATE mission_state SET document=? WHERE mission_id=?",
                (json.dumps(changed, sort_keys=True, separators=(",", ":")), mission.id),
            )
        with self.assertRaisesRegex(RuntimeDatabaseError, "provenance has changed"):
            self.runtime.database.read_action_intents(mission.id)

    def test_full_approved_scopes_bind_distinct_ep_ids_and_replay_without_dispatch(self) -> None:
        scopes = ("example/repository-a", "example/repository-b")
        selected = {scopes[0]: "unrelated-ep-one", scopes[1]: "unrelated-ep-two"}
        self.provider = _TwoRepositoryProvider()
        self.provider.scopes = scopes
        self.runtime.provider = self.provider
        self.host.config = SimpleNamespace(
            base_url="http://127.0.0.1:1", bearer_token="private-fixture", expected_instance_id="ep-fixture-1",
            project_id="project-fixture-1", expected_consumer_id="forge-consumer", peer_binding_id="peer-fixture",
            peer_configuration_revision=1, peer_configuration_digest="sha256:" + "e" * 64,
            allow_loopback_http=True, timeout=1.0,
        )
        mission, envelope = self._mission_and_envelope(
            two_repositories=True, repository_scopes=scopes,
        )
        self._admit(mission, envelope)
        heads = {scopes[0]: "a" * 40, scopes[1]: "b" * 40}
        selected_peer = SimpleNamespace(
            endpoint=self.host.config.base_url, expected_ep_instance_id=self.host.config.expected_instance_id,
            ep_project_id=self.host.config.project_id, ep_consumer_id=self.host.config.expected_consumer_id,
            binding_id=self.host.config.peer_binding_id,
            configuration_revision=self.host.config.peer_configuration_revision,
            configuration_digest=self.host.config.peer_configuration_digest,
        )
        by_ep = {ep_id: scope for scope, ep_id in selected.items()}

        def current_authority(_scope, *, repository_id, github_repository, **_pins):
            if by_ep.get(repository_id) != github_repository:
                raise ValueError("EP grant does not match approved GitHub source")
            document = authority(repository_id)
            document["github_repository"] = github_repository
            return document

        with patch("forge.mission_cli._github_default_head", side_effect=lambda name: ("main", heads[name])), \
             patch("forge.runtime.dynamic_mission.read_repository_authority",
                   side_effect=current_authority), \
             patch("forge.runtime.action_intents.read_repository_authority",
                   side_effect=current_authority), \
             patch("forge.execution_host_configuration.EngineeringPlatformExecutionHostFactory.from_database",
                   return_value=self.host), \
             patch("forge.runtime.dynamic_mission.EngineeringPlatformPeerConfigurationStore.load",
                   return_value=selected_peer):
            with self.assertRaisesRegex(InstalledDynamicMissionError, "bind each approved scope"):
                self.runtime.derive_two_repository_actions(mission.id)
            self.assertEqual(self.provider.calls, 0)
            with self.assertRaisesRegex(ValueError, "grant does not match"):
                self.runtime.derive_two_repository_actions(mission.id, ep_repository_ids={
                    scopes[0]: selected[scopes[1]], scopes[1]: selected[scopes[0]],
                })
            self.assertEqual(self.provider.calls, 0)
            result = self.runtime.derive_two_repository_actions(
                mission.id, ep_repository_ids=selected,
            )
            self.assertEqual(result.status, "ACTIONS_MATERIALIZED_NO_DISPATCH")
            self.assertEqual(self.provider.calls, 1)
            self.assertEqual(self.host.requests, [])
            snapshot = self.runtime.database.read_action_intents(mission.id)
            self.assertEqual({item["target"]["repository_id"] for item in snapshot["actions"]},
                             set(selected.values()))
            self.assertEqual({item["baseline"]["approved_scope_id"] for item in snapshot["actions"]},
                             set(scopes))
            self.runtime.close()
            self.runtime = self._open_runtime()
            self.assertEqual(self.runtime.derive_two_repository_actions(
                mission.id, ep_repository_ids=selected,
            ), result)
            with self.assertRaisesRegex(InstalledDynamicMissionError, "differ from pinned"):
                self.runtime.derive_two_repository_actions(mission.id, ep_repository_ids={
                    scopes[0]: selected[scopes[1]], scopes[1]: selected[scopes[0]],
                })
            with patch("forge.runtime.action_intents.read_repository_authority",
                       side_effect=ValueError("revoked grant")):
                with self.assertRaisesRegex(ValueError, "revoked grant"):
                    self.runtime.derive_two_repository_actions(mission.id, ep_repository_ids=selected)
            heads[scopes[1]] = "c" * 40
            with self.assertRaisesRegex(RuntimeDatabaseError, "baseline differs"):
                self.runtime.derive_two_repository_actions(mission.id, ep_repository_ids=selected)
            heads[scopes[1]] = "b" * 40
            self.assertEqual(self.runtime.derive_two_repository_actions(
                mission.id, ep_repository_ids=selected,
            ), result)
            self.assertEqual(self.provider.calls, 1)
            self.assertEqual(self.host.requests, [])
            row = self.runtime.database._connection.execute(
                "SELECT document FROM mission_action_slot_snapshots WHERE mission_id=?",
                (mission.id,),
            ).fetchone()
            graph = json.loads(row[0])
            graph["approved_repository_bindings"] = None
            encoded = json.dumps(graph, sort_keys=True, separators=(",", ":"))
            with self.runtime.database._connection:
                self.runtime.database._connection.execute(
                    "UPDATE mission_action_slot_snapshots SET document=?,document_digest=? "
                    "WHERE mission_id=?",
                    (encoded, _digest(graph), mission.id),
                )
            with self.assertRaisesRegex(RuntimeDatabaseError, "identity mapping is invalid"):
                self.runtime.database.read_action_intents(mission.id)

    def test_two_repository_authority_drift_keeps_zero_actions(self) -> None:
        self.provider = _TwoRepositoryProvider()
        self.runtime.provider = self.provider
        self.host.config = SimpleNamespace(
            base_url="http://127.0.0.1:1", bearer_token="private-fixture", expected_instance_id="ep-fixture-1",
            project_id="project-fixture-1", expected_consumer_id="forge-consumer", peer_binding_id="peer-fixture",
            peer_configuration_revision=1, peer_configuration_digest="sha256:" + "e" * 64,
            allow_loopback_http=True, timeout=1.0,
        )
        mission, envelope = self._mission_and_envelope(two_repositories=True)
        self.runtime.admit(mission, envelope)
        heads = {"example/repository-a": "a" * 40, "example/repository-b": "b" * 40}
        selected_peer = SimpleNamespace(
            endpoint=self.host.config.base_url, expected_ep_instance_id=self.host.config.expected_instance_id,
            ep_project_id=self.host.config.project_id, ep_consumer_id=self.host.config.expected_consumer_id,
            binding_id=self.host.config.peer_binding_id,
            configuration_revision=self.host.config.peer_configuration_revision,
            configuration_digest=self.host.config.peer_configuration_digest,
        )
        calls = {"repository-a": 0, "repository-b": 0}
        def read_authority(_scope, *, repository_id, **_):
            calls[repository_id] += 1
            return authority(repository_id, revision="2" if calls[repository_id] > 1 else "1")
        with patch("forge.mission_cli._github_default_head", side_effect=lambda name: ("main", heads[name])), \
             patch("forge.runtime.dynamic_mission.read_repository_authority", side_effect=read_authority), \
             patch("forge.runtime.dynamic_mission.EngineeringPlatformPeerConfigurationStore.load",
                   return_value=selected_peer):
            with self.assertRaises(InstalledDynamicMissionError):
                self.runtime.derive_two_repository_actions(mission.id)
        self.assertEqual(self.runtime.states.get(mission.id).status, MissionExecutionStatus.APPROVED_PLANNABLE)
        self.assertEqual(self.runtime.states.get(mission.id).actions, ())
        self.assertEqual(self.runtime.database.read_action_intents(mission.id)["actions"], [])
        self.assertEqual(self.host.requests, [])
        wrong_peer = SimpleNamespace(**{**vars(selected_peer),
                                        "configuration_digest": "sha256:" + "f" * 64})
        with patch("forge.runtime.dynamic_mission.EngineeringPlatformPeerConfigurationStore.load",
                   return_value=wrong_peer):
            with self.assertRaisesRegex(InstalledDynamicMissionError, "selected EP peer changed"):
                self.runtime.derive_two_repository_actions(mission.id)
        self.assertEqual(self.provider.calls, 1)

    def test_peer_replacement_at_atomic_commit_rolls_back_both_actions(self) -> None:
        self.provider = _TwoRepositoryProvider()
        self.runtime.provider = self.provider
        self.host.config = SimpleNamespace(
            base_url="http://127.0.0.1:1", bearer_token="private-fixture", expected_instance_id="ep-fixture-1",
            project_id="project-fixture-1", expected_consumer_id="forge-consumer", peer_binding_id="peer-fixture",
            peer_configuration_revision=1, peer_configuration_digest="sha256:" + "e" * 64,
            allow_loopback_http=True, timeout=1.0,
        )
        mission, envelope = self._mission_and_envelope(two_repositories=True)
        self._admit(mission, envelope)
        selected_peer = SimpleNamespace(
            endpoint=self.host.config.base_url, expected_ep_instance_id=self.host.config.expected_instance_id,
            ep_project_id=self.host.config.project_id, ep_consumer_id=self.host.config.expected_consumer_id,
            binding_id=self.host.config.peer_binding_id,
            configuration_revision=self.host.config.peer_configuration_revision,
            configuration_digest=self.host.config.peer_configuration_digest,
        )
        replaced_peer = SimpleNamespace(**{**vars(selected_peer),
                                           "configuration_digest": "sha256:" + "f" * 64})
        heads = {"example/repository-a": "a" * 40, "example/repository-b": "b" * 40}
        with patch("forge.mission_cli._github_default_head", side_effect=lambda name: ("main", heads[name])), \
             patch("forge.runtime.dynamic_mission.read_repository_authority",
                   side_effect=lambda _scope, *, repository_id, **_: authority(repository_id)), \
             patch("forge.runtime.dynamic_mission.EngineeringPlatformPeerConfigurationStore.load",
                   side_effect=[selected_peer, selected_peer, replaced_peer]):
            with self.assertRaisesRegex(RuntimeDatabaseError, "selected EP peer changed before"):
                self.runtime.derive_two_repository_actions(mission.id)
        self.assertEqual(self.runtime.states.get(mission.id).status, MissionExecutionStatus.APPROVED_PLANNABLE)
        self.assertEqual(self.runtime.states.get(mission.id).actions, ())
        self.assertEqual(self.runtime.database.read_action_intents(mission.id)["actions"], [])
        self.assertEqual(self.host.requests, [])

    def test_invalid_second_action_rolls_back_both_siblings(self) -> None:
        self.provider = _TwoRepositoryProvider()
        self.runtime.provider = self.provider
        self.host.config = SimpleNamespace(
            base_url="http://127.0.0.1:1", bearer_token="private-fixture", expected_instance_id="ep-fixture-1",
            project_id="project-fixture-1", expected_consumer_id="forge-consumer", peer_binding_id="peer-fixture",
            peer_configuration_revision=1, peer_configuration_digest="sha256:" + "e" * 64,
            allow_loopback_http=True, timeout=1.0,
        )
        mission, envelope = self._mission_and_envelope(two_repositories=True)
        self.runtime.admit(mission, envelope)
        heads = {"example/repository-a": "a" * 40, "example/repository-b": "b" * 40}
        selected_peer = SimpleNamespace(
            endpoint=self.host.config.base_url, expected_ep_instance_id=self.host.config.expected_instance_id,
            ep_project_id=self.host.config.project_id, ep_consumer_id=self.host.config.expected_consumer_id,
            binding_id=self.host.config.peer_binding_id,
            configuration_revision=self.host.config.peer_configuration_revision,
            configuration_digest=self.host.config.peer_configuration_digest,
        )
        def invalid_second(_scope, *, repository_id, **_):
            document = authority(repository_id)
            if repository_id == "repository-b":
                document["repository_grant"] = "REVOKED"
            return document
        with patch("forge.mission_cli._github_default_head", side_effect=lambda name: ("main", heads[name])), \
             patch("forge.runtime.dynamic_mission.read_repository_authority", side_effect=invalid_second), \
             patch("forge.runtime.dynamic_mission.EngineeringPlatformPeerConfigurationStore.load",
                   return_value=selected_peer):
            with self.assertRaises(ValueError):
                self.runtime.derive_two_repository_actions(mission.id)
        self.assertEqual(self.runtime.states.get(mission.id).status, MissionExecutionStatus.APPROVED_PLANNABLE)
        self.assertEqual(self.runtime.states.get(mission.id).actions, ())
        for table in ("mission_action_slot_snapshots", "mission_action_intent_revisions"):
            count = self.runtime.database._connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE mission_id=?", (mission.id,),
            ).fetchone()[0]
            self.assertEqual(count, 0)
        self.assertEqual(self.host.requests, [])

    def test_stale_second_repository_head_fails_before_provider_use(self) -> None:
        self.provider = _TwoRepositoryProvider()
        self.runtime.provider = self.provider
        self.host.config = SimpleNamespace(
            base_url="http://127.0.0.1:1", bearer_token="private-fixture", expected_instance_id="ep-fixture-1",
            project_id="project-fixture-1", expected_consumer_id="forge-consumer", peer_binding_id="peer-fixture",
            peer_configuration_revision=1, peer_configuration_digest="sha256:" + "e" * 64,
            allow_loopback_http=True, timeout=1.0,
        )
        mission, envelope = self._mission_and_envelope(two_repositories=True)
        self._admit(mission, envelope)
        selected_peer = SimpleNamespace(
            endpoint=self.host.config.base_url, expected_ep_instance_id=self.host.config.expected_instance_id,
            ep_project_id=self.host.config.project_id, ep_consumer_id=self.host.config.expected_consumer_id,
            binding_id=self.host.config.peer_binding_id,
            configuration_revision=self.host.config.peer_configuration_revision,
            configuration_digest=self.host.config.peer_configuration_digest,
        )
        reads = {"example/repository-a": 0, "example/repository-b": 0}
        def current_head(name):
            reads[name] += 1
            return "main", ("c" * 40 if name == "example/repository-b" and reads[name] > 1
                            else "a" * 40 if name == "example/repository-a" else "b" * 40)
        with patch("forge.mission_cli._github_default_head", side_effect=current_head), \
             patch("forge.runtime.dynamic_mission.EngineeringPlatformPeerConfigurationStore.load",
                   return_value=selected_peer), \
             patch("forge.runtime.dynamic_mission.read_repository_authority",
                   side_effect=lambda _scope, *, repository_id, **_: authority(repository_id)):
            with self.assertRaisesRegex(ValueError, "baseline differs"):
                self.runtime.derive_two_repository_actions(mission.id)
        self.assertEqual(self.provider.calls, 0)
        self.assertEqual(self.runtime.states.get(mission.id).status, MissionExecutionStatus.APPROVED_PLANNABLE)
        self.assertEqual(self.host.requests, [])

    def test_installed_no_dispatch_entrypoint_redacts_failures(self) -> None:
        output = StringIO()
        with patch("forge.mission_no_dispatch.InstalledDynamicMissionRuntime.open",
                   side_effect=ValueError("private-fixture-bearer")), redirect_stdout(output):
            self.assertEqual(derive_actions_main(["--data-root", str(self.root),
                                                  "--mission-id", "MISSION-0001"]), 1)
        self.assertEqual(json.loads(output.getvalue()),
                         {"status": "ERROR", "error_type": "ValueError"})
        self.assertNotIn("private-fixture-bearer", output.getvalue())
        output = StringIO()
        with patch("forge.mission_no_dispatch.InstalledDynamicMissionRuntime.open") as open_runtime, \
             redirect_stdout(output):
            open_runtime.return_value.__enter__.return_value.derive_two_repository_actions.return_value = \
                DynamicMissionRunResult("MISSION-0001", "runtime-1", "ACTIONS_MATERIALIZED_NO_DISPATCH",
                                        ("action-a", "action-b"), None, 1)
            self.assertEqual(derive_actions_main(["--data-root", str(self.root),
                                                  "--mission-id", "MISSION-0001"]), 0)
        self.assertEqual(json.loads(output.getvalue())["action_ids"], ["action-a", "action-b"])
        output = StringIO()
        with patch("forge.mission_no_dispatch.InstalledDynamicMissionRuntime.open") as open_runtime, \
             redirect_stdout(output):
            open_runtime.return_value.__enter__.return_value.derive_two_repository_actions.return_value = \
                DynamicMissionRunResult("MISSION-0001", "runtime-1", "ACTIONS_MATERIALIZED_NO_DISPATCH",
                                        ("action-a", "action-b"), None, 1)
            self.assertEqual(derive_actions_main([
                "--data-root", str(self.root), "--mission-id", "MISSION-0001",
                "--ep-repository-id", "example/repository-a=unrelated-ep-one",
                "--ep-repository-id", "example/repository-b=unrelated-ep-two",
            ]), 0)
            self.assertEqual(
                open_runtime.return_value.__enter__.return_value.derive_two_repository_actions.call_args.kwargs,
                {"ep_repository_ids": {"example/repository-a": "unrelated-ep-one",
                                       "example/repository-b": "unrelated-ep-two"}},
            )
        output = StringIO()
        with patch("forge.mission_no_dispatch.InstalledDynamicMissionRuntime.open") as open_runtime, \
             redirect_stdout(output):
            self.assertEqual(derive_actions_main([
                "--data-root", str(self.root), "--mission-id", "MISSION-0001",
                "--ep-repository-id", "example/repository-a=unrelated-ep-one",
                "--ep-repository-id", "example/repository-a=unrelated-ep-two",
            ]), 1)
            open_runtime.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["status"], "ERROR")

    def test_pre_t0_workspace_origin_must_match_approved_mission_source(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self._admit(mission, envelope)
        self.host.managed_workspace_readiness = lambda: {
            "status": "READY", "repository_identity": "another/repository",
        }
        with self.assertRaisesRegex(
            InstalledDynamicMissionError, "origin differs from the approved Mission source",
        ):
            self.runtime.start(mission.id, self._truth())
        self.assertEqual(self.runtime.states.get(mission.id).status.value, "APPROVED_PLANNABLE")
        self.assertEqual(self.provider.calls, 0)
        self.assertEqual(self.host.requests, [])

    def test_public_readback_surfaces_linked_legacy_confirmed_result_without_generation(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self._admit(mission, envelope)
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
        self._admit(mission, envelope)
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
        self._admit(mission, envelope)
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
        self._admit(mission, envelope)
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
        self.assertEqual(completed.status, "AWAITING_APPROVAL")
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
        self._admit(mission, envelope)
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
        self._admit(mission, envelope)
        waiting = self.runtime.start(mission.id, self._truth())
        self.assertEqual(waiting.status, "WAITING_FOR_EVIDENCE")
        self.runtime.states.transition(
            mission.id, MissionExecutionStatus.FAILED, occurred_at="2026-09-11T16:01:00Z",
            reason="host_evidence_failed",
            execution_evidence={"outcome": "failed", "diagnostic_references": ["runner:host_evidence_failed"]},
        )
        self.host.return_evidence = True

        reconciled = self.runtime.reconcile_terminal_evidence(mission.id)

        self.assertEqual(reconciled.status, "AWAITING_APPROVAL")
        self.assertEqual(len(self.host.requests), 1)
        state = self.runtime.states.get(mission.id)
        self.assertIn("terminal_evidence_reconciliation_requested", [item["reason"] for item in state.state_history])

    def test_completed_terminal_evidence_reconciliation_closes_only_legacy_timing_gap(self) -> None:
        mission, envelope = self._mission_and_envelope()
        self._admit(mission, envelope)
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
