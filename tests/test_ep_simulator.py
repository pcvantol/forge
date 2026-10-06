from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from forge.ep_simulator import EpSimulatorScenario, EpSimulatorServer, EpSimulatorState
from forge.models import ExecutionEvidenceOutcome
from forge.models.execution_host import ExecutionHostTemporaryUnavailable
from forge.models.mission_effect import EffectRequest, MissionEffectPolicy
from forge.runtime.database import RuntimeDatabase
from forge.scheduler.ep_http_adapter import EngineeringPlatformHttpConfiguration, EngineeringPlatformHttpExecutionHost
from tests.test_ep_http_adapter import _request


class EpSimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database_path = Path(self.temporary.name) / "forge.db"
        self.database = RuntimeDatabase(Path(self.temporary.name), path=self.database_path, forge_version="test")
        self.addCleanup(lambda: self.database.close())

    def _state(self, scenario: EpSimulatorScenario | None = None) -> EpSimulatorState:
        return EpSimulatorState(
            project_id="forge", repository_id="forge", repository_identity="pcvantol/forge",
            consumer_id="forge-consumer", instance_id="sim-ep", bearer_token="sim-token",
            scenario=scenario,
        )

    def test_identity_capability_only_appears_when_the_scenario_supports_it(self) -> None:
        baseline = self._state().compatibility()["contracts"]
        self.assertEqual(baseline["producer_readback"], ["1.2"])
        self.assertNotIn("submission_identity_readback", baseline)
        supported = self._state(EpSimulatorScenario(identity_readback_supported=True)).compatibility()["contracts"]
        self.assertEqual(supported["producer_readback"], ["1.2", "1.3"])
        self.assertEqual(supported["submission_identity_readback"], ["1.0"])

    def test_legacy_submission_stays_on_terminal_v14_when_ep_advertises_effect_v16(self) -> None:
        state = self._state(EpSimulatorScenario(effect_declaration_supported=True))
        with EpSimulatorServer(state) as server:
            host = self._host(server)
            contracts = host.preflight()["contracts"]
            self.assertEqual(contracts["terminal_evidence"], ["1.4", "1.6"])
            self.assertEqual(contracts["effect_request"], ["1.0"])
            self.assertEqual(contracts["effect_result"], ["1.1"])
            self.assertEqual(contracts["effect_validation_profile"], ["1.0"])
            request = _request()
            self.assertIsNone(host.dispatch(request))
            submission_id, = state.submission_ids()
            state.complete(submission_id, delivery_revision="a" * 40)
            dispatch = host.recover_dispatch(request)
            self.assertIsNotNone(dispatch)
            evidence = host.retrieve_evidence(dispatch)
            self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.COMPLETE)
            self.assertEqual(len(state.submission_ids()), 1)

    def test_effect_request_requires_capability_and_transmits_exact_approved_contract(self) -> None:
        base = _request()
        effect = EffectRequest(
            MissionEffectPolicy("READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY", ("docs/",), ()),
            "a" * 40, (("criterion-1", "Assess the documented architecture boundary."),),
        )
        request = replace(base, producer_contract=replace(base.producer_contract,
                                                           effect_request=effect),
                          effect_request=effect)
        baseline = self._state()
        with EpSimulatorServer(baseline) as server:
            with self.assertRaisesRegex(ValueError, "EP_EFFECT_CAPABILITY_REQUIRED"):
                self._host(server).dispatch(request)
            self.assertEqual(baseline.submission_ids(), ())
        supported = self._state(EpSimulatorScenario(effect_declaration_supported=True))
        with EpSimulatorServer(supported) as server:
            host = self._host(server)
            self.assertIsNone(host.dispatch(request))
            submission_id, = supported.submission_ids()
            payload = supported.submitted_payload(submission_id)
            self.assertEqual(payload["constraints"]["effect_contract"], effect.to_dict())
            self.assertEqual(payload["constraints"]["repository_revision_binding"]["requested_revision"],
                             effect.source_revision)
            supported.complete(submission_id, delivery_revision="b" * 40)
            dispatch = host.recover_dispatch(request)
            self.assertIsNotNone(dispatch)
            with self.assertRaisesRegex(ValueError, "EP_EFFECT_TERMINAL_V16_REQUIRED"):
                host.retrieve_evidence(dispatch)

    def test_historical_effect_declaration_cannot_dispatch_current_profile_bound_request(self) -> None:
        base = _request()
        effect = EffectRequest(
            MissionEffectPolicy("READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY", ("docs/",), ()),
            "a" * 40, (("criterion-1", "Assess the documented architecture boundary."),))
        request = replace(base, producer_contract=replace(base.producer_contract, effect_request=effect),
                          effect_request=effect)
        state = self._state(EpSimulatorScenario(effect_declaration_supported=True))
        legacy = state.compatibility()
        legacy["contracts"]["effect_result"] = ["1.0"]
        legacy["contracts"]["terminal_evidence"] = ["1.4", "1.5"]
        del legacy["contracts"]["effect_validation_profile"]
        with patch.object(state, "compatibility", return_value=legacy), EpSimulatorServer(state) as server:
            host = self._host(server)
            self.assertEqual(host.preflight()["contracts"]["effect_result"], ["1.0"])
            with self.assertRaisesRegex(ValueError, "EP_EFFECT_CAPABILITY_REQUIRED"):
                host.dispatch(request)
            self.assertEqual(state.submission_ids(), ())

    def _host(
        self,
        server: EpSimulatorServer,
        database: RuntimeDatabase | None = None,
        *,
        timeout: float = 10,
    ):
        return EngineeringPlatformHttpExecutionHost(
            EngineeringPlatformHttpConfiguration(
                server.base_url, "forge", "sim-token",
                expected_instance_id="sim-ep", expected_consumer_id="forge-consumer",
                repository_id="forge", repository_identity="forge",
                peer_binding_id="sim-peer", peer_configuration_revision=1,
                peer_configuration_digest="sha256:" + "d" * 64,
                allow_loopback_http=True,
                timeout=timeout,
            ),
            database or self.database,
        )

    def test_real_http_preflight_workspace_and_idempotent_submission(self) -> None:
        state = self._state()
        with EpSimulatorServer(state) as server:
            host = self._host(server)
            self.assertEqual(host.preflight()["instance"]["id"], "sim-ep")
            self.assertEqual(host.managed_workspace_readiness()["status"], "READY")
            request = _request()
            self.assertIsNone(host.dispatch(request))
            self.assertEqual(len(state.submission_ids()), 1)
            self.assertIsNone(host.dispatch(request))
            self.assertEqual(len(state.submission_ids()), 1)
            events = [item["event"] for item in state.audit]
            self.assertIn("submission_accepted", events)

    def test_declined_submission_without_run_fails_closed_on_http_readback(self) -> None:
        state = self._state()
        with EpSimulatorServer(state) as server:
            host = self._host(server)
            request = _request()
            self.assertIsNone(host.dispatch(request))
            submission_id, = state.submission_ids()
            state.decline_before_run(submission_id)
            readback = state.pending_readback(submission_id)
            self.assertEqual(readback["submission"]["state"], "DECLINED")
            self.assertTrue(readback["disposition"]["terminal"])
            self.assertIsNone(readback["run"])
            with self.assertRaisesRegex(ValueError, "EP_DECLINED_BEFORE_RUN"):
                host.recover_dispatch(request)
            with self.assertRaisesRegex(ValueError, "EP_DECLINED_BEFORE_RUN"):
                host.recover_dispatch(request)
            self.assertEqual(state.submission_ids(), (submission_id,))
            self.assertEqual([item["event"] for item in state.audit], [
                "submission_accepted", "submission_declined",
            ])

    def test_accepted_post_lost_response_stays_ambiguous_without_resubmission(self) -> None:
        state = self._state(EpSimulatorScenario(
            name="accepted-response-lost",
            connection_loss_at=frozenset({"submission-after-accept-once"}),
        ))
        with EpSimulatorServer(state) as server:
            request = _request()
            with self.assertRaises(ExecutionHostTemporaryUnavailable):
                self._host(server).dispatch(request)
            self.assertEqual(len(state.submission_ids()), 1)
            self.assertIsNone(self._host(server).recover_dispatch(request))
            with self.assertRaisesRegex(ValueError, "EP_SUBMISSION_OUTCOME_AMBIGUOUS"):
                self._host(server).dispatch(request)
            self.assertEqual(len(state.submission_ids()), 1)
            self.assertEqual(
                [item["event"] for item in state.audit],
                ["submission_accepted", "submission_response_lost"],
            )

    def test_accepted_post_lost_response_recovers_by_producer_identity_without_reposting(self) -> None:
        state = self._state(EpSimulatorScenario(
            name="accepted-response-recovered", identity_readback_supported=True,
            connection_loss_at=frozenset({"submission-after-accept-once"}),
        ))
        with EpSimulatorServer(state) as server:
            request = _request()
            with self.assertRaises(ExecutionHostTemporaryUnavailable):
                self._host(server).dispatch(request)
            self.assertEqual(len(state.submission_ids()), 1)
            self.assertIsNone(self._host(server).recover_dispatch(request))
            binding = self.database.execution_host_binding(request.correlation_id)
            self.assertEqual(binding["submission_id"], state.submission_ids()[0])
            self.assertEqual(binding["submission_receipt"]["submission_id"], binding["submission_id"])
            state.complete(binding["submission_id"])
            recovered = self._host(server).recover_dispatch(request)
            self.assertIsNotNone(recovered)
            evidence = self._host(server).retrieve_evidence(recovered)
            self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.COMPLETE)
            self.assertEqual(len(state.submission_ids()), 1)
            self.assertEqual(
                [event["event"] for event in state.audit].count("submission_accepted"), 1,
            )
            self.assertNotIn("submission_duplicate", [event["event"] for event in state.audit])
            self.assertEqual(
                [event["event"] for event in state.audit].count("submission_identity_read"), 1,
            )

    def test_identity_lookup_absent_or_foreign_remains_fail_closed(self) -> None:
        for label in ("absent", "foreign"):
            with self.subTest(label=label):
                state = self._state(EpSimulatorScenario(
                    name=label, identity_readback_supported=True,
                    connection_loss_at=frozenset({"submission-after-accept-once"}),
                ))
                database = RuntimeDatabase(
                    Path(self.temporary.name),
                    path=Path(self.temporary.name) / f"identity-{label}.db",
                    forge_version="test",
                )
                self.addCleanup(database.close)
                with EpSimulatorServer(state) as server:
                    request = _request()
                    with self.assertRaises(ExecutionHostTemporaryUnavailable):
                        self._host(server, database).dispatch(request)
                    original = state.identity_readback

                    def altered(**values):
                        if label == "absent":
                            raise ValueError("SUBMISSION_IDENTITY_NOT_FOUND")
                        recovered = original(**values)
                        recovered["identity"]["repository_id"] = "foreign-repository"
                        return recovered

                    with patch.object(state, "identity_readback", side_effect=altered):
                        with self.assertRaises(ValueError):
                            self._host(server, database).recover_dispatch(request)
                    binding = database.execution_host_binding(request.correlation_id)
                    self.assertNotIn("submission_id", binding)
                    self.assertEqual(len(state.submission_ids()), 1)
                    self.assertNotIn("submission_duplicate", [event["event"] for event in state.audit])

    def test_success_terminal_evidence_round_trips_through_production_client(self) -> None:
        state = self._state()
        request = _request()
        with EpSimulatorServer(state) as server:
            host = self._host(server)
            self.assertIsNone(host.dispatch(request))
            submission_id = state.submission_ids()[0]
            state.complete(submission_id)
            dispatch = host.recover_dispatch(request)
            self.assertIsNotNone(dispatch)
            evidence = host.retrieve_evidence(dispatch)
            self.assertIsNotNone(evidence)
            self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.COMPLETE)
            self.assertEqual(evidence.repository_evidence.mission_id, request.mission_id)
            self.assertEqual(evidence.repository_evidence.action_id, request.action_id)

    def test_terminal_failure_matrix_uses_same_http_boundary(self) -> None:
        cases = (
            ("provider-failure", "FAILED", "NOT_RECORDED", "NOT_RECORDED", "NOT_RECORDED"),
            ("validation-failure", "BLOCKED", "FAIL", "UNRESOLVED", "UNRESOLVED"),
            ("quality-block", "BLOCKED", "FAIL", "FAIL", "UNRESOLVED"),
            ("security-block", "BLOCKED", "FAIL", "PASS", "FAIL"),
            ("delivery-failure", "FAILED", "PASS", "PASS", "PASS"),
        )
        for index, (label, outcome, assurance, quality, security) in enumerate(cases):
            with self.subTest(label=label):
                state = self._state()
                database = RuntimeDatabase(
                    Path(self.temporary.name),
                    path=Path(self.temporary.name) / f"matrix-{index}.db",
                    forge_version="test",
                )
                self.addCleanup(database.close)
                request = _request()
                with EpSimulatorServer(state) as server:
                    host = self._host(server, database)
                    self.assertIsNone(host.dispatch(request))
                    state.complete(
                        state.submission_ids()[0], outcome=outcome, assurance=assurance,
                        quality_review=quality, security_review=security,
                    )
                    dispatch = host.recover_dispatch(request)
                    evidence = host.retrieve_evidence(dispatch)
                    self.assertEqual(evidence.outcome.value.upper(), outcome)

    def test_delayed_terminal_duplicate_readback_and_restart_reconnect_are_idempotent(self) -> None:
        state = self._state(EpSimulatorScenario(name="delayed", terminal_after_reads=3))
        request = _request()
        server = EpSimulatorServer(state).start()
        try:
            host = self._host(server)
            self.assertIsNone(host.dispatch(request))
            state.complete(state.submission_ids()[0])
            self.assertIsNone(host.recover_dispatch(request))
            self.assertIsNone(host.recover_dispatch(request))
        finally:
            server.stop()

        # EP restart/reconnect: same simulator state, new listener, no new submission.
        with EpSimulatorServer(state) as restarted:
            host = self._host(restarted)
            dispatch = host.recover_dispatch(request)
            evidence = host.retrieve_evidence(dispatch)
            self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.COMPLETE)
            duplicate = host.retrieve_evidence(dispatch)
            self.assertEqual(duplicate.receipt_id, evidence.receipt_id)
            self.assertEqual(len(state.submission_ids()), 1)

    def test_forge_restart_during_polling_reuses_persisted_correlation_without_resubmit(self) -> None:
        state = self._state(EpSimulatorScenario(name="polling", terminal_after_reads=2))
        request = _request()
        with EpSimulatorServer(state) as server:
            host = self._host(server)
            self.assertIsNone(host.dispatch(request))
            state.complete(state.submission_ids()[0])
            self.database.close()
            self.database = RuntimeDatabase(
                Path(self.temporary.name), path=self.database_path, forge_version="test",
            )
            restarted_host = self._host(server, self.database)
            self.assertIsNone(restarted_host.recover_dispatch(request))
            dispatch = restarted_host.recover_dispatch(request)
            evidence = restarted_host.retrieve_evidence(dispatch)
            self.assertEqual(evidence.outcome, ExecutionEvidenceOutcome.COMPLETE)
            self.assertEqual(len(state.submission_ids()), 1)

    def test_wrong_stale_and_conflicting_evidence_fail_closed(self) -> None:
        mutations = (
            ("wrong-mission", lambda r, a: (
                r["correlation"].__setitem__("mission_id", "other-mission"),
                json.loads(a.decode()).get("correlation"),
            )),
            ("wrong-correlation", lambda r, a: (
                r["correlation"].__setitem__("correlation_id", "other-correlation"),
                json.loads(a.decode()).get("correlation"),
            )),
            ("stale-baseline", lambda r, a: (
                None,
                json.loads(a.decode())["repository"].__setitem__("requested_revision", "b" * 40),
            )),
            ("conflicting-artifact", lambda r, a: (
                None,
                json.loads(a.decode())["correlation"].__setitem__("engineering_action_id", "other-action"),
            )),
        )
        for index, (label, _mutation) in enumerate(mutations):
            with self.subTest(label=label):
                state = self._state()
                database = RuntimeDatabase(
                    Path(self.temporary.name),
                    path=Path(self.temporary.name) / f"negative-{index}.db",
                    forge_version="test",
                )
                self.addCleanup(database.close)
                request = _request()
                with EpSimulatorServer(state) as server:
                    host = self._host(server, database)
                    self.assertIsNone(host.dispatch(request))
                    submission_id = state.submission_ids()[0]
                    state.complete(submission_id)
                    readback, raw = state.terminal_documents(submission_id)
                    artifact = json.loads(raw)
                    if label == "wrong-mission":
                        readback["correlation"]["mission_id"] = "other-mission"
                        artifact["correlation"]["mission_id"] = "other-mission"
                    elif label == "wrong-correlation":
                        readback["correlation"]["correlation_id"] = "other-correlation"
                        artifact["correlation"]["correlation_id"] = "other-correlation"
                    elif label == "stale-baseline":
                        artifact["repository"]["requested_revision"] = "b" * 40
                        artifact["repository"]["baseline_transition"]["from"] = "b" * 40
                    else:
                        artifact["correlation"]["engineering_action_id"] = "other-action"
                    state.seed_terminal(
                        submission_id, readback,
                        json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n",
                    )
                    with self.assertRaises(ValueError):
                        dispatch = host.recover_dispatch(request)
                        if dispatch is not None:
                            host.retrieve_evidence(dispatch)

    def test_dirty_workspace_lease_http_timeout_and_connection_loss_are_controllable(self) -> None:
        blocked = self._state(EpSimulatorScenario(
            name="dirty-lease", workspace_clean=False, workspace_busy=True,
            active_lease=True, workspace_status="BLOCKED", workspace_blocker="DIRTY_WORKSPACE",
        ))
        with EpSimulatorServer(blocked) as server:
            readiness = self._host(server).managed_workspace_readiness()
            self.assertFalse(readiness["clean"])
            self.assertTrue(readiness["active_lease"])
            self.assertEqual(readiness["status"], "BLOCKED")

        failed = self._state(EpSimulatorScenario(name="http-failure", preflight_http_status=503))
        with EpSimulatorServer(failed) as server:
            with self.assertRaises(ExecutionHostTemporaryUnavailable):
                self._host(server).preflight()

        timed_out = self._state(EpSimulatorScenario(
            name="timeout", response_delay_seconds=0.05,
        ))
        with EpSimulatorServer(timed_out) as server:
            with self.assertRaises(ExecutionHostTemporaryUnavailable):
                self._host(server, timeout=0.01).preflight()

        dropped = self._state(EpSimulatorScenario(
            name="connection-loss", connection_loss_at=frozenset({"preflight"}),
        ))
        with EpSimulatorServer(dropped) as server:
            with self.assertRaises(ExecutionHostTemporaryUnavailable):
                self._host(server).preflight()


if __name__ == "__main__":
    unittest.main()
