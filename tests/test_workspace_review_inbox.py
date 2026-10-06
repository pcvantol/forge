"""Separate review-principal lifecycle and real Forge Server HTTP qualification."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from http.client import HTTPConnection
import json
from pathlib import Path
from threading import Barrier, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker

from forge.governance_authority import CanonicalGovernanceRepository
from forge.governed_continuation import workspace_review_request_digest
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderSecurityService, ProviderAuthenticationMode,
)
from forge.runtime import RuntimeBootstrap
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.server_runtime import ForgeServerRuntime, existing_instance
from forge.state.mission_state import MissionExecutionStatus
from forge.workspace_review_grant import WorkspaceReviewGrant, main as grant_main
from forge.workspace_review_inbox import scoped_item
from tests.criterion_fixture import ExactRepositoryBytes
from tests import test_installed_dynamic_mission_runtime as runtime_fixture


SCHEMA = json.loads((Path(__file__).parents[1] / "forge" / "api" /
                     "workspace-review-inbox-v1.json").read_text(encoding="utf-8"))


def _schema(name: str, value: object) -> None:
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator(SCHEMA | {"$ref": f"#/$defs/{name}"},
                         format_checker=FormatChecker()).validate(value)


def _expiry(days: int = 1) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _request(port: int, method: str, path: str, token: str | None,
             body: dict | None = None) -> tuple[int, dict]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        connection.request(method, path, body=None if body is None else json.dumps(body),
                           headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class WorkspaceReviewInboxTests(unittest.TestCase):
    def setUp(self) -> None:
        # Existing canonical governance fixture creates approved Missions and
        # synthetic external provider/Host boundaries. HTTP and Forge services
        # below are real, with only the external-runtime factory injected.
        self.fixture = runtime_fixture.InstalledDynamicMissionRuntimeTests(
            methodName="test_after_action_policy_fences_provider_and_exact_approval_resumes_once"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.grant = WorkspaceReviewGrant(self.root, existing_instance(self.root).instance_id)

    def _mission(self, suffix: str, *, paused: bool = False) -> str:
        mission, envelope = self.fixture._mission_and_envelope(identity_suffix=suffix)
        self.fixture._admit(mission, envelope, mode="after_action")
        if paused:
            self.fixture.runtime._criterion_observer.reader = ExactRepositoryBytes(
                "synthetic/forge", "c" * 40, {"contract.json": b'{"source":"not-yet"}'},
            )
            started = self.fixture.runtime.start(mission.id, self.fixture._truth())
            self.assertEqual(started.status, "WAITING_FOR_EVIDENCE")
            self.fixture.host.return_evidence = True
            self.fixture.host.terminal_evidence_remaining = 1
            resumed = self.fixture.runtime.resume(mission.id)
            self.assertEqual(resumed.status, "AWAITING_APPROVAL")
        return mission.id

    def _issue(self, principal: str, missions: tuple[str, ...]) -> tuple[str, str]:
        token_path = self.root / (principal + "-review-token")
        receipt = self.grant.issue(principal_id=principal, mission_ids=missions,
                                   expires_at=_expiry(), token_path=token_path)
        return token_path.read_text(encoding="utf-8").strip(), str(receipt["grant_id"])

    def _server(self) -> tuple[ForgeServerRuntime, Thread]:
        credential = self.root / "server-token"
        credential.write_text("admin-secret\n", encoding="utf-8")
        credential.chmod(0o600)
        server = ForgeServerRuntime(data_root=self.root, credential_file=credential,
                                    host="127.0.0.1", port=0)
        identity_patch = patch("forge.runtime.dynamic_mission.MacOSGeneratedUIDIdentityAdapter",
                               return_value=SimpleNamespace(resolve=lambda: self.fixture.identity))
        identity_patch.start()
        self.addCleanup(identity_patch.stop)
        worker = Thread(target=server.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 3)
        self.addCleanup(server.server.server_close)
        self.addCleanup(server.server.shutdown)
        return server, worker

    def _open_adapted_runtime(self, data_root: str, *, provider_id: str) -> InstalledDynamicMissionRuntime:
        # The listener has a fresh thread/SQLite connection per request.
        # Share only the synthetic external adapters, never the fixture's DB.
        database = RuntimeBootstrap(data_root=data_root, forge_version="test").open()
        repository = CanonicalGovernanceRepository.for_runtime(
            database, lambda: self.fixture.identity, data_root=self.root,
        )
        runtime = InstalledDynamicMissionRuntime(
            database, repository, data_root=str(self.root),
            provider=self.fixture.provider, host=self.fixture.host,
            clock=lambda: "2026-09-11T16:00:00Z",
        )
        runtime._criterion_observer.reader = self.fixture.runtime._criterion_observer.reader
        return runtime

    def test_grants_are_private_expiring_revocable_and_bound_to_existing_missions(self) -> None:
        mission_a = self._mission("-review-grant-a")
        mission_b = self._mission("-review-grant-b")
        with self.assertRaises(ValueError):
            self.grant.issue(principal_id="reviewer-a", mission_ids=("MISSING",),
                             expires_at=_expiry(), token_path=self.root / "missing-token")
        with self.assertRaises(ValueError):
            self.grant.issue(principal_id="reviewer-a", mission_ids=(mission_a,),
                             expires_at=_expiry(91), token_path=self.root / "late-token")
        first, identifier = self._issue("reviewer-a", (mission_a,))
        second, _ = self._issue("reviewer-b", (mission_b,))
        self.assertNotEqual(first, second)
        self.assertEqual(self.grant.path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(first, self.grant.path.read_text(encoding="utf-8"))
        self.assertEqual(self.grant.authenticate("Bearer " + first).principal_id, "reviewer-a")
        self.assertFalse(self.grant.authorizes_reference(
            self.grant.authenticate("Bearer " + first).reference, mission_b,
            role="platform_architect", role_actor="primary_operator",
            capability="ARCHITECTURE_APPROVAL",
        ))
        self.assertIsNone(WorkspaceReviewGrant(self.root, "foreign-instance").authenticate(
            "Bearer " + first,
        ))
        with self.assertRaises(ValueError):
            self.grant.issue(principal_id="reviewer-a", mission_ids=(mission_a,),
                             expires_at=_expiry(), token_path=self.root / "duplicate-token")
        self.assertEqual(self.grant.revoke(identifier)["state"], "REVOKED")
        self.assertIsNone(self.grant.authenticate("Bearer " + first))
        self.assertIsNotNone(self.grant.authenticate("Bearer " + second))
        self.assertEqual(self.grant.revoke(identifier)["revision"], 2)
        original = self.grant.path.read_bytes()
        malformed = json.loads(original)
        malformed["records"][1]["state"] = ["ACTIVE"]
        self.grant.path.write_text(json.dumps(malformed), encoding="utf-8")
        self.assertIsNone(self.grant.authenticate("Bearer " + second))
        self.grant.path.write_bytes(original)
        expired = json.loads(original)
        expired["records"][1]["expires_at"] = "2026-01-01T00:00:00Z"
        self.grant.path.write_text(json.dumps(expired), encoding="utf-8")
        self.assertIsNone(self.grant.authenticate("Bearer " + second))
        self.grant.path.write_bytes(original)
        self.grant.path.chmod(0o644)
        self.assertIsNone(self.grant.authenticate("Bearer " + second))

    def test_two_principals_real_http_scope_decision_replay_and_readback(self) -> None:
        mission_a = self._mission("-review-http-a", paused=True)
        alice, alice_grant = self._issue("reviewer-alice", (mission_a,))
        same_mission_other, _ = self._issue("reviewer-other", (mission_a,))
        server, worker = self._server()
        port = server.server.server_port
        with patch.object(InstalledDynamicMissionRuntime, "open",
                          side_effect=self._open_adapted_runtime):
            status, inbox = _request(port, "GET", "/v1/reviews", alice)
            self.assertEqual(status, 200, inbox)
            _schema("inbox", inbox)
            self.assertEqual(inbox["scope"]["mission_ids"], [mission_a])
            self.assertTrue(inbox["scope"]["complete_within_scope"])
            self.assertEqual([item["mission_id"] for item in inbox["items"]], [mission_a])
            self.assertEqual(inbox["items"][0]["review_kind"], "PROGRESSION")
            self.assertEqual(set(inbox["items"][0]["allowed_outcomes"]),
                             {"approve", "reject", "amend", "defer"})
            self.assertIsNotNone(inbox["items"][0]["action_result"]["evidence_reference"])
            self.assertEqual(inbox["items"][0]["action_result"]["outcome"], "complete")
            self.assertEqual(inbox["items"][0]["action_result"]["evidence_reference"]["receipt_id"],
                             "ep-receipt-status-projection")
            status, detail = _request(port, "GET", f"/v1/reviews/missions/{mission_a}", alice)
            self.assertEqual(status, 200)
            _schema("item", detail)
            self.assertEqual(detail["requirement"]["required_role"], "platform_architect")
            self.assertEqual(_request(port, "GET", "/v1/reviews", "admin-secret")[0], 403)
            self.assertEqual(_request(port, "GET", "/v1/status", alice)[0], 403)
            self.assertEqual(_request(port, "POST", f"/v1/reviews/missions/{mission_a}/decisions",
                                      alice, {"actor": "primary_operator"})[0], 409)
            self.assertEqual(self.fixture.provider.calls, 1)
            requirement = detail["requirement"]
            command = {
                "contract_version": "forge-workspace-review-decision/v1",
                "operation_id": "review-alice-approve-001",
                "requirement_id": requirement["requirement_id"],
                "subject_digest": requirement["subject_digest"],
                "mission_state_revision": requirement["mission_state_revision"],
                "evidence_digest": requirement["evidence_digest"],
                "policy_revision": requirement["policy_revision"],
                "decision": "approve", "reason": "Exact completed Action evidence accepted.",
            }
            _schema("decision_request", command)
            decision_path = f"/v1/reviews/missions/{mission_a}/decisions"
            operation_path = decision_path + "/" + command["operation_id"]
            for malformed in (
                command | {"mission_state_revision": command["mission_state_revision"] + 1},
                command | {"mission_state_revision": float(command["mission_state_revision"])},
                command | {"mission_state_revision": True},
                command | {"subject_digest": "sha256:" + "0" * 64},
                command | {"evidence_digest": "sha256:not-a-digest"},
                command | {"role_actor": "primary_operator"},
                command | {"decision": []},
            ):
                self.assertEqual(_request(port, "POST", decision_path, alice, malformed)[0], 409)
            self.assertEqual(self.fixture.provider.calls, 1)
            status, recorded = _request(port, "POST", decision_path, alice, command)
            self.assertEqual(status, 201, recorded)
            _schema("decision_response", recorded)
            self.assertTrue(recorded["recorded"])
            self.assertEqual(recorded["operation"]["operation_id"], command["operation_id"])
            self.assertEqual(recorded["operation"]["request_digest"],
                             workspace_review_request_digest(mission_a, command))
            self.assertNotEqual(recorded["operation"]["request_digest"],
                                workspace_review_request_digest(
                                    mission_a, command | {"reason": "Changed intent"}))
            self.assertEqual(self.fixture.provider.calls, 2)
            server.server.shutdown()
            server.server.server_close()
            worker.join(timeout=3)
            restarted, _ = self._server()
            port = restarted.server.server_port
            status, recovered = _request(port, "GET", operation_path, alice)
            self.assertEqual(status, 200, recovered)
            _schema("operation_response", recovered)
            self.assertEqual(recovered["operation"], recorded["operation"])
            self.assertEqual(recovered["current"]["allowed_outcomes"], [])
            self.assertEqual(_request(port, "GET", operation_path, same_mission_other)[0], 404)
            replay_status, replay = _request(port, "POST", decision_path, alice, command)
            self.assertEqual(replay_status, 200, replay)
            self.assertFalse(replay["recorded"])
            self.assertEqual(replay["operation"], recorded["operation"])
            self.assertEqual(self.fixture.provider.calls, 2)
            self.assertEqual(_request(port, "POST", decision_path, alice,
                                      command | {"reason": "Changed intent"})[0], 409)
            self.assertEqual(_request(port, "POST", decision_path, same_mission_other,
                                      command)[0], 403)
            mission_b = self._mission("-review-http-b")
            bob, _ = self._issue("reviewer-bob", (mission_b,))
            self.assertEqual(_request(port, "GET", f"/v1/reviews/missions/{mission_b}", alice)[0], 403)
            self.assertEqual(_request(port, "GET", f"/v1/reviews/missions/{mission_a}", bob)[0], 403)
            self.assertEqual(_request(port, "POST", decision_path, bob, command)[0], 403)
            self.grant.revoke(alice_grant)
            self.assertEqual(_request(port, "GET", operation_path, alice)[0], 401)
            self.assertEqual(_request(port, "GET", "/v1/reviews", bob)[0], 200)

    def test_mission_end_acceptance_is_readable_but_has_no_progression_decision(self) -> None:
        mission, envelope = self.fixture._mission_and_envelope(identity_suffix="-review-final")
        self.fixture._admit(mission, envelope, mode="continuous")
        started = self.fixture.runtime.start(mission.id, self.fixture._truth())
        self.assertEqual(started.status, "WAITING_FOR_EVIDENCE")
        self.fixture.host.return_evidence = True
        self.fixture.host.managed_workspace_readiness = lambda: {
            "status": "BLOCKED", "known_blocker": "MANAGED_LEASE_ACTIVE",
            "repository_identity": "synthetic/forge",
        }
        result = self.fixture.runtime.resume(mission.id)
        self.assertEqual(result.status, "AWAITING_APPROVAL")
        token, _ = self._issue("reviewer-final", (mission.id,))
        server, _ = self._server()
        with patch.object(InstalledDynamicMissionRuntime, "open",
                          side_effect=self._open_adapted_runtime):
            path = f"/v1/reviews/missions/{mission.id}"
            status, detail = _request(server.server.server_port, "GET", path, token)
            self.assertEqual(status, 200, detail)
            _schema("item", detail)
            self.assertEqual(detail["review_kind"], "FINAL_ACCEPTANCE")
            self.assertEqual(detail["requirement"]["required_role"], "business_owner")
            self.assertEqual(detail["allowed_outcomes"], [])
            requirement = detail["requirement"]
            command = {
                "contract_version": "forge-workspace-review-decision/v1",
                "operation_id": "wrong-final-as-progression-001",
                "requirement_id": requirement["requirement_id"],
                "subject_digest": requirement["subject_digest"],
                "mission_state_revision": requirement["mission_state_revision"],
                "evidence_digest": "sha256:" + "0" * 64,
                "policy_revision": requirement["policy_revision"],
                "decision": "approve", "reason": "Must remain a separate owner acceptance.",
            }
            self.assertEqual(_request(server.server.server_port, "POST", path + "/decisions",
                                      token, command)[0], 403)

    def test_canonical_intake_without_policy_is_a_scoped_no_review_item(self) -> None:
        mission, envelope = self.fixture._mission_and_envelope(identity_suffix="-review-intake")
        admitted = self.fixture.runtime.admit(mission, envelope)
        self.assertEqual(admitted.status, MissionExecutionStatus.APPROVED_PLANNABLE)
        token, _ = self._issue("reviewer-intake", (mission.id,))
        server, _ = self._server()
        database_path = self.root / "forge.db"
        before_database = sha256(database_path.read_bytes()).hexdigest()
        before_metadata = self.fixture.runtime.database.metadata
        with patch.object(InstalledDynamicMissionRuntime, "open",
                          side_effect=AssertionError("read invoked execution adapters")):
            port = server.server.server_port
            status, inbox = _request(port, "GET", "/v1/reviews", token)
            self.assertEqual(status, 200, inbox)
            _schema("inbox", inbox)
            self.assertEqual(inbox["scope"]["mission_ids"], [mission.id])
            self.assertEqual(len(inbox["items"]), 1)
            self.assertEqual(inbox["items"][0]["review_kind"], "NONE")
            self.assertEqual(inbox["items"][0]["allowed_outcomes"], [])
            detail_status, detail = _request(port, "GET",
                                             f"/v1/reviews/missions/{mission.id}", token)
            self.assertEqual(detail_status, 200, detail)
            _schema("item", detail)
        self.assertEqual(sha256(database_path.read_bytes()).hexdigest(), before_database)
        self.assertEqual(self.fixture.runtime.database.metadata, before_metadata)

    def test_scoped_projection_redacts_free_text_and_marks_blocker_scope(self) -> None:
        mission_id = self._mission("-review-redaction", paused=True)
        token, _ = self._issue("reviewer-redaction", (mission_id,))
        principal = self.grant.authenticate("Bearer " + token)
        self.assertIsNotNone(principal)
        state = self.fixture.runtime.states.get(mission_id)
        current = self.fixture.runtime.progression_status(mission_id)
        requirement = dict(current["decision_requirement"])
        requirement["continuation_scope"] = ["repo Bearer private-review-token"]
        fake = SimpleNamespace(
            states=SimpleNamespace(get=lambda _: replace(
                state, mission=state.mission | {"title": "Bearer private-title-token"},
            )),
            progression_status=lambda _: current | {"decision_requirement": requirement},
        )
        item = scoped_item(fake, principal, mission_id)
        _schema("item", item)
        self.assertTrue(item["requirement"]["blocking_scope_redacted"])
        self.assertNotIn("private-review-token", json.dumps(item))
        self.assertNotIn("private-title-token", json.dumps(item))

    def test_read_snapshot_keeps_one_mission_revision_during_concurrent_transition(self) -> None:
        mission, envelope = self.fixture._mission_and_envelope(identity_suffix="-review-snapshot")
        self.fixture.runtime.admit(mission, envelope)
        token, _ = self._issue("reviewer-snapshot", (mission.id,))
        principal = self.grant.authenticate("Bearer " + token)
        self.assertIsNotNone(principal)
        with patch("forge.runtime.dynamic_mission.MacOSGeneratedUIDIdentityAdapter",
                   return_value=SimpleNamespace(resolve=lambda: self.fixture.identity)):
            with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as reader:
                before = reader.states.get(mission.id)
                self.fixture.runtime.states.transition(
                    mission.id, MissionExecutionStatus.CREATED,
                    occurred_at="2026-09-11T16:00:00Z", reason="snapshot_isolation_test",
                )
                item = scoped_item(reader, principal, mission.id)
        self.assertEqual(item["lifecycle_state"], "APPROVED_PLANNABLE")
        self.assertEqual(item["mission_state_revision"], before.revision)

    def test_real_runtime_composition_records_one_scoped_decision(self) -> None:
        mission_id = self._mission("-review-real-composition", paused=True)
        token, _ = self._issue("reviewer-composed", (mission_id,))
        service = PlanningProviderSecurityService(
            self.fixture.runtime.database, SimpleNamespace(),
            self.fixture.runtime.repository.operators,
        )
        service.configure(
            configuration_id="review-qualifier-codex",
            provider_id="codex-chatgpt-session",
            operator_context=self.fixture.runtime.repository.operators.context(),
            authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
            provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
            external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
            executable_path="/usr/bin/true", adapter_version="1.0",
            timeout_seconds=30, input_token_bound=16000,
            context_token_bound=32768, output_token_bound=4096,
        )
        server, _ = self._server()
        with patch("forge.runtime.dynamic_mission.CodexCliChatGPTSessionPlanningProvider",
                   return_value=self.fixture.provider), \
             patch("forge.runtime.dynamic_mission.EngineeringPlatformExecutionHostFactory.from_database",
                   return_value=self.fixture.host):
            port = server.server.server_port
            detail_status, detail = _request(
                port, "GET", f"/v1/reviews/missions/{mission_id}", token,
            )
            self.assertEqual(detail_status, 200, detail)
            requirement = detail["requirement"]
            command = {
                "contract_version": "forge-workspace-review-decision/v1",
                "operation_id": "review-real-composition-defer-001",
                "requirement_id": requirement["requirement_id"],
                "subject_digest": requirement["subject_digest"],
                "mission_state_revision": requirement["mission_state_revision"],
                "evidence_digest": requirement["evidence_digest"],
                "policy_revision": requirement["policy_revision"],
                "decision": "defer", "reason": "Installed composition keeps successor fenced.",
            }
            path = f"/v1/reviews/missions/{mission_id}/decisions"
            recorded_status, recorded = _request(port, "POST", path, token, command)
            self.assertEqual(recorded_status, 201, recorded)
            _schema("decision_response", recorded)
            self.assertEqual(recorded["operation"]["request_digest"],
                             workspace_review_request_digest(mission_id, command))
            self.assertEqual(_request(port, "POST", path, token, command)[0], 200)

    def test_external_gate_never_exposes_local_approval(self) -> None:
        mission_id = self._mission("-review-external")
        states = self.fixture.runtime.states
        for status in (MissionExecutionStatus.CREATED, MissionExecutionStatus.READY,
                       MissionExecutionStatus.WAITING_EXTERNAL_CAPABILITY,
                       MissionExecutionStatus.WAITING_EXTERNAL_APPROVAL):
            states.transition(mission_id, status, occurred_at="2026-09-11T16:00:00Z",
                              reason="external_gate_projection_qualification")
        token, _ = self._issue("reviewer-external", (mission_id,))
        server, _ = self._server()
        with patch.object(InstalledDynamicMissionRuntime, "open",
                          side_effect=self._open_adapted_runtime):
            status, detail = _request(server.server.server_port, "GET",
                                      f"/v1/reviews/missions/{mission_id}", token)
            self.assertEqual(status, 200, detail)
            _schema("item", detail)
            self.assertEqual(detail["review_kind"], "EXTERNAL_GATE")
            self.assertIsNone(detail["requirement"])
            self.assertEqual(detail["allowed_outcomes"], [])

    def test_concurrent_identical_operation_records_one_canonical_decision(self) -> None:
        mission_id = self._mission("-review-concurrent", paused=True)
        token, _ = self._issue("reviewer-concurrent", (mission_id,))
        server, _ = self._server()
        port = server.server.server_port
        with patch.object(InstalledDynamicMissionRuntime, "open",
                          side_effect=self._open_adapted_runtime):
            _, detail = _request(port, "GET", f"/v1/reviews/missions/{mission_id}", token)
            requirement = detail["requirement"]
            command = {
                "contract_version": "forge-workspace-review-decision/v1",
                "operation_id": "review-concurrent-defer-001",
                "requirement_id": requirement["requirement_id"],
                "subject_digest": requirement["subject_digest"],
                "mission_state_revision": requirement["mission_state_revision"],
                "evidence_digest": requirement["evidence_digest"],
                "policy_revision": requirement["policy_revision"],
                "decision": "defer", "reason": "Hold the exact successor fence.",
            }
            path = f"/v1/reviews/missions/{mission_id}/decisions"
            barrier = Barrier(3)
            def submit() -> tuple[int, dict]:
                barrier.wait()
                return _request(port, "POST", path, token, command)
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(submit)
                second = pool.submit(submit)
                barrier.wait()
                responses = (first.result(timeout=5), second.result(timeout=5))
            statuses = [status for status, _ in responses]
            self.assertEqual(statuses.count(201), 1, responses)
            self.assertIn(next(status for status in statuses if status != 201), {200, 503}, responses)
            for status, body in responses:
                if status == 503:
                    self.assertIn(body["error"]["code"],
                                  {"REVIEW_BUSY", "REVIEW_UNAVAILABLE"}, responses)
                else:
                    self.assertEqual(body["operation"]["operation_id"], command["operation_id"])
            read_status, readback = _request(port, "GET", path + "/" + command["operation_id"], token)
            self.assertEqual(read_status, 200, readback)
            replay_status, replay = _request(port, "POST", path, token, command)
            self.assertEqual(replay_status, 200, replay)
            self.assertEqual(replay["operation"], readback["operation"])
            self.assertEqual(self.fixture.provider.calls, 1)
            row = self.fixture.runtime.database._connection.execute(
                "SELECT COUNT(*) FROM governance_decisions WHERE decision_id=?",
                (command["operation_id"],),
            ).fetchone()
            self.assertEqual(row[0], 1)

    def _nonapproving_outcome(self, outcome: str) -> None:
        mission_id = self._mission("-review-" + outcome, paused=True)
        token, _ = self._issue("reviewer-" + outcome, (mission_id,))
        server, _ = self._server()
        with patch.object(InstalledDynamicMissionRuntime, "open",
                          side_effect=self._open_adapted_runtime):
            port = server.server.server_port
            status, detail = _request(port, "GET", f"/v1/reviews/missions/{mission_id}", token)
            self.assertEqual(status, 200, detail)
            requirement = detail["requirement"]
            command = {
                "contract_version": "forge-workspace-review-decision/v1",
                "operation_id": "review-" + outcome + "-001",
                "requirement_id": requirement["requirement_id"],
                "subject_digest": requirement["subject_digest"],
                "mission_state_revision": requirement["mission_state_revision"],
                "evidence_digest": requirement["evidence_digest"],
                "policy_revision": requirement["policy_revision"],
                "decision": outcome, "reason": "Keep successor fenced after review.",
            }
            calls = self.fixture.provider.calls
            path = f"/v1/reviews/missions/{mission_id}/decisions"
            status, recorded = _request(port, "POST", path, token, command)
            self.assertEqual(status, 201, recorded)
            self.assertEqual(recorded["current"]["review_kind"], "PROGRESSION")
            self.assertEqual(recorded["current"]["decision"]["outcome"], outcome)
            self.assertEqual(recorded["current"]["allowed_outcomes"], [])
            self.assertEqual(self.fixture.provider.calls, calls)
            self.assertEqual(_request(port, "POST", path, token, command)[0], 200)
            self.assertEqual(self.fixture.provider.calls, calls)

    def test_reject_keeps_successor_fenced(self) -> None:
        self._nonapproving_outcome("reject")

    def test_amend_keeps_successor_fenced(self) -> None:
        self._nonapproving_outcome("amend")

    def test_defer_keeps_successor_fenced(self) -> None:
        self._nonapproving_outcome("defer")

    def test_owner_cli_issues_and_revokes_without_printing_bearer(self) -> None:
        mission_id = self._mission("-review-cli")
        token_path = self.root / "cli-review-token"
        with patch("builtins.print") as output:
            self.assertEqual(grant_main([
                "--data-root", str(self.root), "issue", "--principal-id", "reviewer-cli",
                "--mission-id", mission_id, "--expires-at", _expiry(),
                "--token-file", str(token_path),
            ]), 0)
        receipt = json.loads(output.call_args.args[0])
        self.assertNotIn(token_path.read_text(encoding="utf-8").strip(), output.call_args.args[0])
        with patch("builtins.print") as output:
            self.assertEqual(grant_main([
                "--data-root", str(self.root), "revoke", "--grant-id", receipt["grant_id"],
            ]), 0)
        self.assertEqual(json.loads(output.call_args.args[0])["state"], "REVOKED")


if __name__ == "__main__":
    unittest.main()
