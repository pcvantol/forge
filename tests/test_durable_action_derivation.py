"""Crash-boundary qualification for durable installed Action Derivation."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from forge.models.action_derivation import (
    DerivationPolicy, DerivedActionProposal, GovernanceRefinementRequired,
    PlanningSnapshot, ProposalProvenance, ProviderInvocationEvidence, ProviderSideEffectState,
)
from forge.planner import DurableAIMissionPlanner
from forge.planner.durable_derivation import (
    DurableActionDerivationCoordinator, DurableDerivationBlocked, serialize_provider_response,
)
from forge.planner.provider_adapter import ProviderDerivationResponse
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.governance_authority import CanonicalGovernanceRepository
from forge.runtime import RuntimeBootstrap
from forge.runtime.database import RuntimeDatabaseError, RuntimeIntegrityError
from forge.state import MissionExecutionStatus, MissionStateStore
from tests.test_action_derivation import input_model


def digest(value: object) -> str:
    import json
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class DurableFixtureProvider:
    """Controlled boundary that behaves like the installed adapter's public hooks."""

    def __init__(self, *, result: str = "proposals", failure: Exception | None = None,
                 revision: str = "1") -> None:
        self.result, self.failure, self.revision, self.calls = result, failure, revision, 0

    @property
    def provider_id(self) -> str:
        return "fixture-codex"

    def prepare_durable_attempt(self, snapshot, _planning_input, _policy, derivation_id, attempt_authority_id=None):
        return {
            "provider_id": "fixture-codex", "provider_configuration_revision": self.revision,
            "provider_model": None, "adapter_version": "fixture-v1",
            "provider_policy_digest": digest({"provider": "fixture-codex", "revision": self.revision}),
            # This is the stable generation boundary.  The distinct typed
            # derivation request remains bound to the persisted attempt below.
            "generation_request_digest": digest({"snapshot": snapshot.digest, "provider": "fixture-codex", "authority": attempt_authority_id}),
            "derivation_request_digest": digest({"derivation": derivation_id, "snapshot": snapshot.digest, "authority": attempt_authority_id}),
        }

    def derive_with_planning_input(self, snapshot, _planning_input, _policy, *, derivation_id,
                                   attempt_authority_id=None, durable_attempt_specification=None,
                                   durable_result_sink):
        if durable_attempt_specification is None:
            raise AssertionError("durable invocation must receive its prepared attempt specification")
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        request_digest = digest({"derivation": derivation_id, "snapshot": snapshot.digest, "authority": attempt_authority_id})
        evidence = ProviderInvocationEvidence(
            "fixture-codex", None, "fixture-v1", request_digest, snapshot.digest,
            digest({"result": self.result, "derivation": derivation_id}),
            ProviderSideEffectState.HAPPENED_AND_CONFIRMED,
            status="contract_invalid" if self.result == "contract_invalid" else "completed",
        )
        if self.result in {"refinement", "contract_invalid"}:
            response = ProviderDerivationResponse(
                evidence, governance_refinement=GovernanceRefinementRequired(
                    tuple(item.source_id for item in snapshot.evidence), "new architecture approval",
                    "fixture scope", "blocked", "fixture needs a governed refinement",
                ),
            )
            durable_result_sink(response)
            return response.governance_refinement
        proposals = tuple(
            DerivedActionProposal(
                action_id, scope,
                ("system prompt: do not persist this provider echo"
                 if self.result == "forbidden" else "Deliver the bounded durable planning slice."), dependencies,
                (("other/write-scope",) if self.result == "invalid" else ("forge/planner",)),
                ("focused evidence",), ("python -m unittest",), priority, False,
                ("architecture-review",), ("scope-drift",),
                ProposalProvenance(
                    derivation_id, snapshot.id, snapshot.digest, "fixture-v1", "fixture-codex", None,
                    tuple(item.source_id for item in snapshot.evidence),
                ),
            )
            for action_id, scope, dependencies, priority in (
                ("durable-contract", "planner-contract", (), 1),
                ("durable-docs", "planner-docs", ("durable-contract",), 2),
            )
        )
        response = ProviderDerivationResponse(evidence, proposals=proposals)
        durable_result_sink(response)
        return proposals


class DurableActionDerivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name) / "forge-server"
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.identity = NamedOperatorIdentity("durable-test", 501)
        operators = InstallationOperatorService(self.database, lambda: self.identity)
        operators.first_bind()
        self.repository = CanonicalGovernanceRepository.for_runtime(
            self.database, lambda: self.identity, data_root=str(self.root),
        )
        self.states = MissionStateStore(self.database, data_root=str(self.root))
        self.input = input_model()
        self.states.create_pending(self.input.mission, occurred_at="2026-09-13T10:00:00Z")
        self.policy = DerivationPolicy(("forge/planner",), ("architecture-review",), ("scope-drift",))

    def tearDown(self) -> None:
        self.database.close()
        self.temporary.cleanup()

    def _reopen(self) -> None:
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.repository = CanonicalGovernanceRepository.for_runtime(
            self.database, lambda: self.identity, data_root=str(self.root),
        )
        self.states = MissionStateStore(self.database, data_root=str(self.root))

    def test_result_is_stored_before_validation_and_replayed_after_reopen_once(self) -> None:
        provider = DurableFixtureProvider()
        snapshot = PlanningSnapshot.from_planner_input(self.input)
        coordinator = DurableActionDerivationCoordinator(self.database, provider)
        original = coordinator.derive_with_planning_input(snapshot, self.input, self.policy)
        self.assertEqual(provider.calls, 1)
        attempt_id = coordinator.last_derivation_id
        self.assertEqual(len(original), 2)
        before = self.database.durable_action_derivation_readback(self.input.mission.id)
        self.assertEqual(before[0]["processing_phase"], "RESULT_AVAILABLE")
        self.assertTrue(before[0]["result_available"])
        self.assertNotIn("payload", before[0])

        self._reopen()
        replayed = DurableAIMissionPlanner(self.database, provider).plan(self.input, self.policy)
        self.assertEqual(provider.calls, 1)
        self.assertEqual([action.id for intent in replayed.plan.intents for action in intent.actions],
                         ["durable-contract", "durable-docs"])
        readback = self.database.durable_action_derivation_readback(self.input.mission.id)[0]
        self.assertEqual(readback["derivation_id"], attempt_id)
        self.assertEqual(readback["processing_phase"], "VALIDATED")

    def test_durable_result_replays_in_a_new_os_process_without_provider_invocation(self) -> None:
        provider = DurableFixtureProvider()
        DurableActionDerivationCoordinator(self.database, provider).derive_with_planning_input(
            PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
        )
        self.assertEqual(provider.calls, 1)
        # Do not carry the provider object over this boundary.  The child must
        # open the same Runtime database and use only the persisted typed
        # result; its fixture reports an invocation if a new model call occurs.
        script = '''
import json
import sys
from forge.models.action_derivation import DerivationPolicy
from forge.planner import DurableAIMissionPlanner
from forge.runtime import RuntimeBootstrap
from tests.test_action_derivation import input_model
from tests.test_durable_action_derivation import DurableFixtureProvider

database = RuntimeBootstrap(data_root=sys.argv[1], forge_version="test").open()
try:
    provider = DurableFixtureProvider()
    result = DurableAIMissionPlanner(
        database, provider,
    ).plan(input_model(), DerivationPolicy(("forge/planner",), ("architecture-review",), ("scope-drift",)))
    print(json.dumps({"provider_calls": provider.calls, "actions": len(result.plan.intents)}))
finally:
    database.close()
'''
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.root)], cwd=str(Path(__file__).resolve().parents[1]),
            env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        observed = json.loads(completed.stdout)
        self.assertEqual(observed["provider_calls"], 0)
        self.assertEqual(observed["actions"], 2)

    def test_concurrent_os_processes_claim_one_provider_boundary(self) -> None:
        counter = self.root / "provider-invocations.txt"
        script = '''
import sys
from forge.models.action_derivation import DerivationPolicy, PlanningSnapshot
from forge.planner.durable_derivation import DurableDerivationBlocked, DurableActionDerivationCoordinator
from forge.runtime import RuntimeBootstrap
from forge.runtime.bootstrap import RuntimeResolutionError
from tests.test_action_derivation import input_model
from tests.test_durable_action_derivation import DurableFixtureProvider

try:
    database = RuntimeBootstrap(data_root=sys.argv[1], forge_version="test").open()
except RuntimeResolutionError:
    # The installed single-writer lease is itself the concurrent-starter
    # protection.  A contender that cannot own it cannot reach a provider.
    raise SystemExit(0)
try:
    provider = DurableFixtureProvider()
    invoke = provider.derive_with_planning_input
    def tracked(*args, **kwargs):
        with open(sys.argv[2], "a", encoding="utf-8") as handle:
            handle.write("invoked\\n")
        return invoke(*args, **kwargs)
    provider.derive_with_planning_input = tracked
    planning_input = input_model()
    try:
        DurableActionDerivationCoordinator(database, provider).derive_with_planning_input(
            PlanningSnapshot.from_planner_input(planning_input), planning_input,
            DerivationPolicy(("forge/planner",), ("architecture-review",), ("scope-drift",)),
        )
    except DurableDerivationBlocked:
        pass
finally:
    database.close()
'''
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        command = [sys.executable, "-c", script, str(self.root), str(counter)]
        self.database.close()
        first = subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[1]), env=environment,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        second = subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[1]), env=environment,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        first_out, first_error = first.communicate(timeout=15)
        second_out, second_error = second.communicate(timeout=15)
        self.assertEqual(first.returncode, 0, first_out + first_error)
        self.assertEqual(second.returncode, 0, second_out + second_error)
        self.assertEqual(counter.read_text(encoding="utf-8").splitlines(), ["invoked"])
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        attempts = self.database.durable_action_derivation_readback(self.input.mission.id)
        self.assertEqual(len(attempts), 1)
        self.assertTrue(attempts[0]["result_available"])

    def test_validated_result_and_actions_history_materialize_atomically_once(self) -> None:
        provider = DurableFixtureProvider()
        planner = DurableAIMissionPlanner(self.database, provider)
        result = planner.plan(self.input, self.policy)
        record = {
            "derivation_id": planner.current_derivation_id,
            "lifecycle": "MATERIALIZED", "planning_snapshot_digest": result.snapshot.digest,
            "validation_status": "PASS", "validated_before_materialization": True,
        }
        materialized = self.states.transition(
            self.input.mission.id, MissionExecutionStatus.READY, occurred_at="2026-09-13T10:01:00Z",
            reason="dynamic_derivation_materialized", intents=result.plan.intents,
            actions=tuple(action for intent in result.plan.intents for action in intent.actions),
            repository_truth={"source_id": "fixture", "revision": "r1", "locator": "fixture://r1", "content_digest": digest("truth")},
            planning_history=(record,), durable_materialization_derivation_id=planner.current_derivation_id,
        )
        self.assertEqual(materialized.status, MissionExecutionStatus.READY)
        self.assertEqual(len(materialized.actions), 2)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(self.database.durable_action_derivation_readback(self.input.mission.id)[0]["processing_phase"], "MATERIALIZED")

        self._reopen()
        persisted = self.states.get(self.input.mission.id)
        self.assertEqual(len(persisted.actions), 2)
        self.assertEqual(len(persisted.planning_history), 1)
        self.assertEqual(provider.calls, 1)

    def test_refinement_and_ambiguity_are_durable_non_generating_outcomes(self) -> None:
        refinement_provider = DurableFixtureProvider(result="refinement")
        result = DurableAIMissionPlanner(self.database, refinement_provider).plan(self.input, self.policy)
        self.assertIsNotNone(result.governance_refinement)
        state = self.database.durable_action_derivation_readback(self.input.mission.id)[0]
        self.assertEqual(state["result_kind"], "GOVERNANCE_REFINEMENT")
        self.assertEqual(state["processing_phase"], "GOVERNANCE_REFINEMENT")

        # A separate Mission identity avoids treating a terminal refinement as
        # an attempt eligible for a different fixture scenario.
        second_document = self.input.mission.to_dict()
        second_document["id"] = "mission-2"
        second = input_model(
            mission=self.input.mission.__class__.from_dict(second_document),
            mission_state=self.input.mission_state.__class__("mission-2", 1),
        )
        self.states.create_pending(second.mission, occurred_at="2026-09-13T10:02:00Z")
        ambiguous = DurableFixtureProvider(failure=__import__("forge.planner.openai_responses", fromlist=["ProviderSubmissionAmbiguous"]).ProviderSubmissionAmbiguous("fixture"))
        with self.assertRaises(DurableDerivationBlocked) as raised:
            DurableAIMissionPlanner(self.database, ambiguous).plan(second, self.policy)
        self.assertEqual(raised.exception.code, "GENERATION_MAY_HAVE_HAPPENED")
        self.assertEqual(ambiguous.calls, 1)
        readback = self.database.durable_action_derivation_readback("mission-2")[0]
        self.assertEqual(readback["processing_phase"], "GENERATION_MAY_HAVE_HAPPENED")
        self._reopen()
        with self.assertRaises(DurableDerivationBlocked) as replay:
            DurableAIMissionPlanner(self.database, ambiguous).plan(second, self.policy)
        self.assertEqual(replay.exception.code, "GENERATION_MAY_HAVE_HAPPENED")
        self.assertEqual(ambiguous.calls, 1)

    def test_terminal_refinement_and_rejection_replay_without_a_lifecycle_rewrite(self) -> None:
        refinement = DurableFixtureProvider(result="refinement")
        first = DurableAIMissionPlanner(self.database, refinement).plan(self.input, self.policy)
        self.assertIsNotNone(first.governance_refinement)
        self._reopen()
        with self.assertRaises(DurableDerivationBlocked) as replayed_refinement:
            DurableAIMissionPlanner(self.database, refinement).plan(self.input, self.policy)
        self.assertEqual(replayed_refinement.exception.code, "GOVERNANCE_REFINEMENT_REQUIRED")
        self.assertEqual(refinement.calls, 1)

        second_document = self.input.mission.to_dict()
        second_document["id"] = "mission-terminal-rejection"
        second = input_model(
            mission=self.input.mission.__class__.from_dict(second_document),
            mission_state=self.input.mission_state.__class__("mission-terminal-rejection", 1),
        )
        self.states.create_pending(second.mission, occurred_at="2026-09-13T10:02:00Z")
        invalid = DurableFixtureProvider(result="invalid")
        with self.assertRaises(__import__("forge.planner.action_derivation", fromlist=["ProposalValidationError"]).ProposalValidationError):
            DurableAIMissionPlanner(self.database, invalid).plan(second, self.policy)
        self._reopen()
        with self.assertRaises(DurableDerivationBlocked) as replayed_rejection:
            DurableAIMissionPlanner(self.database, invalid).plan(second, self.policy)
        self.assertEqual(replayed_rejection.exception.code, "DETERMINISTIC_REJECTION")
        self.assertEqual(invalid.calls, 1)

    def test_legacy_confirmed_external_audit_blocks_new_generation_without_backfill(self) -> None:
        snapshot = PlanningSnapshot.from_planner_input(self.input)
        audit = {
            "state": "HAPPENED_AND_CONFIRMED", "status": "completed",
            "provider_id": "fixture-codex", "snapshot_digest": snapshot.digest,
            "derivation_request_digest": digest("historical-derivation"),
            "request_digest": digest("historical-generation"), "result_digest": digest("historical-result"),
        }
        with self.database._connection:
            self.database._connection.execute(
                "INSERT INTO planning_provider_external_session_config VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("historical-config", "fixture-codex", "CODEX_CLI_CHATGPT_SESSION",
                 "EXTERNAL_AUTHENTICATED_SESSION", "CODEX_CLI_CHATGPT_SESSION", "/usr/bin/true",
                 "fixture-v1", None, 1, "operator", 1, "2026-09-13T10:00:00Z",
                 "2026-09-13T10:00:00Z", None, 30, 16000, 32768, 4096),
            )
            self.database._connection.execute(
                "INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)",
                ("legacy-confirmed", "historical-config", "operator", "invocation",
                 "2026-09-13T10:00:00Z", json.dumps(audit, sort_keys=True)),
            )
        provider = DurableFixtureProvider()
        with self.assertRaises(DurableDerivationBlocked) as blocked:
            DurableAIMissionPlanner(self.database, provider).plan(self.input, self.policy)
        self.assertEqual(blocked.exception.code, "LEGACY_CONFIRMED_RESULT_UNAVAILABLE")
        self.assertEqual(provider.calls, 0)
        legacy = self.database.legacy_confirmed_result_unavailable(
            self.input.mission.id, snapshot.digest, provider.provider_id,
        )
        self.assertEqual(legacy["generation_state"], "HAPPENED_AND_CONFIRMED")
        self.assertFalse(legacy["result_available"])
        self.assertEqual(self.database.durable_action_derivation_readback(self.input.mission.id), ())

    def test_pre_durable_action_derivation_is_readable_and_requires_reconciliation(self) -> None:
        snapshot = PlanningSnapshot.from_planner_input(self.input)
        self.database.save_action_derivation({
            "derivation_id": "legacy-derivation", "mission_id": self.input.mission.id,
            "snapshot_digest": snapshot.digest, "contract_version": "1.0",
            "provider_configuration": digest("legacy-provider"), "lifecycle": "FAILED",
            "generation_request_digest": digest("legacy-request"),
        })
        readback = self.database.durable_action_derivation_readback(self.input.mission.id)
        self.assertEqual(readback[0]["source"], "LEGACY_ACTION_DERIVATION_RECORD")
        self.assertEqual(readback[0]["processing_phase"], "LEGACY_RECONCILIATION_REQUIRED")
        provider = DurableFixtureProvider()
        with self.assertRaises(DurableDerivationBlocked) as blocked:
            DurableAIMissionPlanner(self.database, provider).plan(self.input, self.policy)
        self.assertEqual(blocked.exception.code, "LEGACY_ATTEMPT_RECONCILIATION_REQUIRED")
        self.assertEqual(provider.calls, 0)

    def test_attempt_and_result_integrity_fail_closed_before_replay(self) -> None:
        provider = DurableFixtureProvider()
        coordinator = DurableActionDerivationCoordinator(self.database, provider)
        coordinator.derive_with_planning_input(PlanningSnapshot.from_planner_input(self.input), self.input, self.policy)
        attempt_id = coordinator.last_derivation_id
        attempt = self.database.durable_action_derivation_attempt(attempt_id)
        forged = dict(attempt)
        forged["provider_id"] = "forged-provider"
        with self.database._connection:
            self.database._connection.execute(
                "UPDATE action_derivations SET document=? WHERE derivation_id=?",
                (json.dumps(forged, sort_keys=True, separators=(",", ":")), attempt_id),
            )
        with self.assertRaisesRegex(RuntimeDatabaseError, "metadata integrity"):
            self.database.durable_action_derivation_result(attempt_id)

        # A separately claimed boundary rejects a result whose stated payload
        # digest does not match the structured provider payload.
        fresh_provider = DurableFixtureProvider()
        fresh = DurableActionDerivationCoordinator(self.database, fresh_provider)
        document = self.input.mission.to_dict()
        document["id"] = "mission-manual-result"
        manual_input = input_model(
            mission=self.input.mission.__class__.from_dict(document),
            mission_state=self.input.mission_state.__class__("mission-manual-result", 1),
        )
        self.states.create_pending(manual_input.mission, occurred_at="2026-09-13T10:03:00Z")
        snapshot = PlanningSnapshot.from_planner_input(manual_input)
        specification = fresh_provider.prepare_durable_attempt(snapshot, manual_input, self.policy, "manual-attempt")
        manual = fresh._attempt_document(specification, "manual-attempt", snapshot, manual_input)
        self.database.begin_durable_action_derivation_attempt(manual)
        self.database.advance_durable_action_derivation(
            "manual-attempt", lifecycle="PROVIDER_RUNNING", processing_phase="GENERATION_IN_PROGRESS",
        )
        received = []
        fresh_provider.derive_with_planning_input(
            snapshot, manual_input, self.policy, derivation_id="manual-attempt",
            durable_attempt_specification=specification, durable_result_sink=received.append,
        )
        result = serialize_provider_response(received[0], derivation_id="manual-attempt",
                                             stored_at="2026-09-13T10:00:00Z")
        result.update({
            "attempt_metadata_digest": manual["attempt_metadata_digest"],
            "provider_id": manual["provider_id"], "provider_model": manual["provider_model"],
            "adapter_version": manual["adapter_version"],
            "provider_configuration_revision": manual["provider_configuration_revision"],
            "effective_policy_digest": manual["effective_policy_digest"],
            "generation_request_digest": manual["generation_request_digest"],
            "payload_digest": "sha256:" + "0" * 64,
        })
        result["metadata_digest"] = digest({key: value for key, value in result.items()
                                             if key not in {"payload", "metadata_digest"}})
        with self.assertRaisesRegex(RuntimeDatabaseError, "payload digest"):
            self.database.store_durable_action_derivation_result(result)

    def test_forbidden_provider_payload_and_untrusted_successor_are_denied(self) -> None:
        forbidden = DurableFixtureProvider(result="forbidden")
        with self.assertRaises(DurableDerivationBlocked) as blocked:
            DurableAIMissionPlanner(self.database, forbidden).plan(self.input, self.policy)
        self.assertEqual(blocked.exception.code, "CONFIRMED_RESULT_NOT_DURABLE")
        self.assertEqual(forbidden.calls, 1)

        # A distinct Mission keeps the successor authorization checks focused
        # on the confirmed-result-unavailable predecessor.
        mission_document = self.input.mission.to_dict()
        mission_document["id"] = "mission-successor-authority"
        successor_input = input_model(
            mission=self.input.mission.__class__.from_dict(mission_document),
            mission_state=self.input.mission_state.__class__("mission-successor-authority", 1),
        )
        self.states.create_pending(successor_input.mission, occurred_at="2026-09-13T10:04:00Z")
        unavailable = DurableFixtureProvider()
        original_store = self.database.store_durable_action_derivation_result
        self.database.store_durable_action_derivation_result = lambda _result: (_ for _ in ()).throw(
            RuntimeDatabaseError("fixture store loss")
        )
        try:
            with self.assertRaises(DurableDerivationBlocked):
                DurableAIMissionPlanner(self.database, unavailable).plan(successor_input, self.policy)
        finally:
            self.database.store_durable_action_derivation_result = original_store
        predecessor = self.database.durable_action_derivation_readback("mission-successor-authority")[0]
        coordinator = DurableActionDerivationCoordinator(self.database, unavailable)
        with self.assertRaises(PermissionError):
            coordinator.authorize_next_attempt(
                PlanningSnapshot.from_planner_input(successor_input), successor_input, self.policy,
                predecessor_attempt_id=predecessor["derivation_id"], governance_repository=self.repository,
                operator_context=NamedOperatorIdentity("unbound-operator", 501), rationale="not authorized",
            )
        with self.assertRaises(RuntimeDatabaseError):
            coordinator.authorize_next_attempt(
                PlanningSnapshot.from_planner_input(successor_input), successor_input, self.policy,
                predecessor_attempt_id="wrong-predecessor", governance_repository=self.repository,
                operator_context=self.repository.operators.context(), rationale="wrong predecessor",
            )
        reservation = coordinator.authorize_next_attempt(
            PlanningSnapshot.from_planner_input(successor_input), successor_input, self.policy,
            predecessor_attempt_id=predecessor["derivation_id"], governance_repository=self.repository,
            operator_context=self.repository.operators.context(), rationale="confirmed output is unavailable",
        )
        changed = DurableFixtureProvider(revision="2")
        with self.assertRaises(DurableDerivationBlocked) as stale:
            DurableActionDerivationCoordinator(self.database, changed).consume_authorized_next_attempt(
                PlanningSnapshot.from_planner_input(successor_input), successor_input, self.policy,
                successor_attempt_id=reservation["derivation_id"], governance_repository=self.repository,
                operator_context=self.repository.operators.context(),
            )
        self.assertEqual(stale.exception.code, "CURRENT_PROVIDER_AUTHORITY_CHANGED")
        self.assertEqual(changed.calls, 0)

    def test_explicit_successor_authorization_reserves_once_without_generation(self) -> None:
        unavailable = DurableFixtureProvider()
        original_store = self.database.store_durable_action_derivation_result
        def reject_confirmed_result(_result):
            raise RuntimeDatabaseError("fixture result store interruption")
        self.database.store_durable_action_derivation_result = reject_confirmed_result
        try:
            with self.assertRaises(DurableDerivationBlocked) as blocked:
                DurableAIMissionPlanner(self.database, unavailable).plan(self.input, self.policy)
        finally:
            self.database.store_durable_action_derivation_result = original_store
        self.assertEqual(blocked.exception.code, "CONFIRMED_RESULT_NOT_DURABLE")
        predecessor = self.database.durable_action_derivation_readback(self.input.mission.id)[0]
        self.assertEqual(predecessor["processing_phase"], "CONFIRMED_RESULT_UNAVAILABLE")
        before_calls = unavailable.calls
        coordinator = DurableActionDerivationCoordinator(self.database, unavailable)
        authorization = coordinator.authorize_next_attempt(
            PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
            predecessor_attempt_id=predecessor["derivation_id"], governance_repository=self.repository,
            operator_context=self.repository.operators.context(), rationale="The confirmed result is unavailable for replay.",
        )
        self.assertEqual(unavailable.calls, before_calls)
        self.assertEqual(authorization["processing_phase"], "SUCCESSOR_AUTHORIZED")
        successor = self.database.durable_action_derivation_readback(self.input.mission.id)[1]
        self.assertEqual(successor["predecessor_attempt_id"], predecessor["derivation_id"])
        self.assertEqual(successor["processing_phase"], "SUCCESSOR_AUTHORIZED")
        with self.assertRaises(Exception):
            coordinator.authorize_next_attempt(
                PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
                predecessor_attempt_id=predecessor["derivation_id"], governance_repository=self.repository,
                operator_context=self.repository.operators.context(), rationale="A duplicate successor is forbidden.",
            )
        consumed = coordinator.consume_authorized_next_attempt(
            PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
            successor_attempt_id=successor["derivation_id"], governance_repository=self.repository,
            operator_context=self.repository.operators.context(),
        )
        self.assertEqual(len(consumed), 2)
        self.assertEqual(unavailable.calls, before_calls + 1)
        successor = self.database.durable_action_derivation_readback(self.input.mission.id)[1]
        self.assertEqual(successor["processing_phase"], "RESULT_AVAILABLE")
        # A second caller after the durable receipt is a replay, not a second
        # provider call.  This is the crash boundary before materialization.
        self._reopen()
        replayed = DurableActionDerivationCoordinator(self.database, unavailable).consume_authorized_next_attempt(
            PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
            successor_attempt_id=successor["derivation_id"], governance_repository=self.repository,
            operator_context=self.repository.operators.context(),
        )
        self.assertEqual(len(replayed), 2)
        self.assertEqual(unavailable.calls, before_calls + 1)

    def test_successor_reservation_recovers_an_existing_decision_after_interruption(self) -> None:
        """A committed decision can complete its one reservation after a crash.

        Governance evidence is immutable and belongs to the canonical
        repository.  It cannot share the attempt table's transaction, so the
        equivalent crash-safe boundary is a deterministic decision/revision
        and successor identity: an identical public request resumes the
        reservation, whereas a changed request is rejected.
        """
        unavailable = DurableFixtureProvider()
        original_store = self.database.store_durable_action_derivation_result

        def reject_confirmed_result(_result):
            raise RuntimeDatabaseError("fixture result store interruption")

        self.database.store_durable_action_derivation_result = reject_confirmed_result
        try:
            with self.assertRaises(DurableDerivationBlocked):
                DurableAIMissionPlanner(self.database, unavailable).plan(self.input, self.policy)
        finally:
            self.database.store_durable_action_derivation_result = original_store
        predecessor = self.database.durable_action_derivation_readback(self.input.mission.id)[0]
        coordinator = DurableActionDerivationCoordinator(self.database, unavailable)
        original_begin = self.database.begin_durable_action_derivation_attempt

        def interrupted_begin(document):
            raise RuntimeDatabaseError("fixture interruption after canonical decision")

        self.database.begin_durable_action_derivation_attempt = interrupted_begin
        rationale = "The confirmed result is unavailable for replay."
        try:
            with self.assertRaises(RuntimeDatabaseError):
                coordinator.authorize_next_attempt(
                    PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
                    predecessor_attempt_id=predecessor["derivation_id"], governance_repository=self.repository,
                    operator_context=self.repository.operators.context(), rationale=rationale,
                )
        finally:
            self.database.begin_durable_action_derivation_attempt = original_begin

        # The pre-existing immutable decision is validated, then exactly one
        # successor is reserved; no provider invocation occurs during either
        # authorization call.
        recovered = coordinator.authorize_next_attempt(
            PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
            predecessor_attempt_id=predecessor["derivation_id"], governance_repository=self.repository,
            operator_context=self.repository.operators.context(), rationale=rationale,
        )
        self.assertEqual(unavailable.calls, 1)
        self.assertEqual(recovered["processing_phase"], "SUCCESSOR_AUTHORIZED")
        self.assertEqual(
            len([item for item in self.database.durable_action_derivation_readback(self.input.mission.id)
                 if item.get("predecessor_attempt_id") == predecessor["derivation_id"]]),
            1,
        )
        with self.assertRaises(RuntimeIntegrityError):
            coordinator.authorize_next_attempt(
                PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
                predecessor_attempt_id=predecessor["derivation_id"], governance_repository=self.repository,
                operator_context=self.repository.operators.context(), rationale="A different authority is forbidden.",
            )

    def test_contract_invalid_result_is_not_misreported_as_governance_refinement(self) -> None:
        provider = DurableFixtureProvider(result="contract_invalid")
        with self.assertRaises(DurableDerivationBlocked) as rejected:
            DurableAIMissionPlanner(self.database, provider).plan(self.input, self.policy)
        self.assertEqual(rejected.exception.code, "PROVIDER_CONTRACT_INVALID")
        readback = self.database.durable_action_derivation_readback(self.input.mission.id)[0]
        self.assertEqual(readback["result_kind"], "CONTRACT_INVALID")
        self.assertEqual(readback["processing_phase"], "DETERMINISTIC_REJECTION")
        self._reopen()
        with self.assertRaises(DurableDerivationBlocked) as replay:
            DurableAIMissionPlanner(self.database, provider).plan(self.input, self.policy)
        self.assertEqual(replay.exception.code, "PROVIDER_CONTRACT_INVALID")
        self.assertEqual(provider.calls, 1)

    def test_changed_provider_policy_blocks_replay_without_a_second_generation(self) -> None:
        original = DurableFixtureProvider()
        DurableActionDerivationCoordinator(self.database, original).derive_with_planning_input(
            PlanningSnapshot.from_planner_input(self.input), self.input, self.policy,
        )
        changed = DurableFixtureProvider(revision="2")
        with self.assertRaises(DurableDerivationBlocked) as blocked:
            DurableAIMissionPlanner(self.database, changed).plan(self.input, self.policy)
        self.assertEqual(blocked.exception.code, "CURRENT_PROVIDER_AUTHORITY_CHANGED")
        self.assertEqual(original.calls, 1)
        self.assertEqual(changed.calls, 0)


if __name__ == "__main__":
    unittest.main()
