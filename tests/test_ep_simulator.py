from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.ep_simulator import EpSimulatorScenario, EpSimulatorServer, EpSimulatorState
from forge.models import ExecutionEvidenceOutcome
from forge.models.execution_host import ExecutionHostTemporaryUnavailable
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

    def _host(self, server: EpSimulatorServer, database: RuntimeDatabase | None = None):
        return EngineeringPlatformHttpExecutionHost(
            EngineeringPlatformHttpConfiguration(
                server.base_url, "forge", "sim-token",
                expected_instance_id="sim-ep", expected_consumer_id="forge-consumer",
                repository_id="forge", repository_identity="forge",
                peer_binding_id="sim-peer", peer_configuration_revision=1,
                peer_configuration_digest="sha256:" + "d" * 64,
                allow_loopback_http=True,
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

        dropped = self._state(EpSimulatorScenario(
            name="connection-loss", connection_loss_at=frozenset({"preflight"}),
        ))
        with EpSimulatorServer(dropped) as server:
            with self.assertRaises(ExecutionHostTemporaryUnavailable):
                self._host(server).preflight()


if __name__ == "__main__":
    unittest.main()
