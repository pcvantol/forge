"""Current EP and repository-head checks for immutable parallel Action targets."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hashlib import sha256
from importlib.resources import files
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from forge.governance_authority import ArchitecturePlanningEvidence
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_assessment import ApprovedRepositoryEvidenceSource
from forge.models.mission_recommendation import RequiredDiscipline
from forge.runtime import RuntimeBootstrap
from forge.runtime.action_authority import (
    RepositoryAuthorityError, RepositoryAuthorityScope, read_repository_authority,
)
from forge.runtime.action_intents import ActionIntentError, ActionIntentLedger


MISSION_ID = "MISSION-FIXTURE-1"
SHA_A = "a" * 40
SHA_B = "b" * 40
REQUEST_DIGEST = "sha256:" + "c" * 64


def authority(repository_id: str, *, revision: str = "1") -> dict[str, object]:
    return {
        "contract_version": "ep-repository-consumer-authority/v1",
        "instance_id": "ep-fixture-1", "project_id": "project-fixture-1", "project_status": "ACTIVE",
        "repository_id": repository_id, "repository_role": "child",
        "authority_repository_id": "repository-a",
        "github_repository": "example/" + repository_id,
        "local_repository_binding": "BOUND", "consumer_id": "forge-consumer",
        "consumer_status": "ACTIVE", "repository_grant": "ACTIVE",
        "submission_authorization": "PARALLEL_ACTION_INTAKE", "dispatch_authorized": False,
        "binding_revision": "sha256:" + revision * 64,
        "authority_digest": "sha256:" + revision * 64,
        "provenance": {"source": "EP_CENTRAL_AND_BOUND_ATTACHMENT",
                       "attachment_schema_version": "1.0", "attachment_digest": "sha256:" + "d" * 64},
    }


class AuthorityBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.responses = {"repository-a": authority("repository-a"),
                          "repository-b": authority("repository-b", revision="2")}
        responses = self.responses

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                repository_id = self.path.split("/")[-2]
                document = responses.get(repository_id)
                permitted = (
                    self.headers.get("Authorization") == "Bearer scoped-token"
                    and self.headers.get("EP-Instance-ID") == "ep-fixture-1"
                    and self.headers.get("EP-Consumer-ID") == "forge-consumer"
                    and document is not None
                    and self.headers.get("EP-GitHub-Repository") == document["github_repository"]
                )
                if not permitted:
                    self.send_response(403)
                    self.end_headers()
                    return
                if (self.headers.get("EP-Authority-Revision") not in
                    (None, document["binding_revision"]) or
                    self.headers.get("EP-Authority-Digest") not in
                    (None, document["authority_digest"])):
                    self.send_response(409)
                    self.end_headers()
                    return
                raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *_: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.scope = RepositoryAuthorityScope(
            f"http://127.0.0.1:{self.server.server_port}", "scoped-token",
            "ep-fixture-1", "project-fixture-1", "forge-consumer",
            "peer-fixture", 1, "sha256:" + "e" * 64, allow_loopback_http=True,
        )
        self.root = Path(self.temporary.name) / "installed"
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        self.addCleanup(self.database.close)
        graph = json.loads(files("forge").joinpath("api/parallel-action-peer-graph-v1.json").read_text())
        state = {
            "mission_id": MISSION_ID,
            "mission": {"id": MISSION_ID, "status": "approved_for_engineering",
                        "scope": ["repository-a", "repository-b"],
                        "repository_evidence_sources": [
                            {"repository_id": item, "github_repository": "example/" + item}
                            for item in ("repository-a", "repository-b")]},
            "revision": 1,
            "actions": [{"id": item["action_id"], "dependencies": [
                edge["predecessor_action_id"] for edge in item["dependencies"]]}
                for item in graph["actions"]],
            "status": "READY", "lifecycle": "READY", "progress": {}, "resume": {},
            "execution_policy": {"mode": "serial"},
        }
        self.database.create_mission_state(state)
        self.database.record_mission_action_slots(graph)

    def test_http_scope_and_schema_fail_closed(self) -> None:
        observed = read_repository_authority(
            self.scope, repository_id="repository-a", github_repository="example/repository-a")
        self.assertFalse(observed["dispatch_authorized"])
        with self.assertRaises(RepositoryAuthorityError):
            read_repository_authority(
                self.scope, repository_id="repository-a", github_repository="example/wrong")
        self.responses["repository-a"] = {**observed, "dispatch_authorized": True}
        with self.assertRaises(RepositoryAuthorityError):
            read_repository_authority(
                self.scope, repository_id="repository-a", github_repository="example/repository-a")

    def test_inactive_or_mismatched_ep_readback_never_grants_authority(self) -> None:
        original = self.responses["repository-a"]
        changes = (
            {"instance_id": "other-instance"}, {"project_id": "other-project"},
            {"consumer_id": "other-consumer"}, {"repository_id": "repository-b"},
            {"project_status": "SUSPENDED"}, {"consumer_status": "REVOKED"},
            {"repository_grant": "REVOKED"}, {"local_repository_binding": "UNBOUND"},
            {"submission_authorization": "NONE"},
            {"provenance": {**original["provenance"], "attachment_digest": "invalid"}},
        )
        for changed in changes:
            with self.subTest(changed=changed):
                self.responses["repository-a"] = {**original, **changed}
                with self.assertRaises(RepositoryAuthorityError):
                    read_repository_authority(
                        self.scope, repository_id="repository-a",
                        github_repository="example/repository-a")
        self.responses["repository-a"] = original

    def test_two_targets_restart_and_changed_authority_or_baseline(self) -> None:
        ledger = ActionIntentLedger(self.database._connection)  # noqa: SLF001 - controlled ledger integration
        ledger.materialize(MISSION_ID)
        for action_id in ("ACTION-A", "ACTION-B"):
            ledger.bind(MISSION_ID, action_id, expected_slot_revision=1,
                        correlation_id="correlation-" + action_id, request_digest=REQUEST_DIGEST)
        heads = {"example/repository-a": SHA_A, "example/repository-b": SHA_B}
        with patch("forge.mission_cli._github_default_head", side_effect=lambda repo: ("main", heads[repo])):
            a = ledger.verify(MISSION_ID, "ACTION-A", self.scope, assert_selected_peer=lambda: None)
            b = ledger.verify(MISSION_ID, "ACTION-B", self.scope, assert_selected_peer=lambda: None)
            self.assertEqual((a["baseline"]["revision"], b["baseline"]["revision"]), (SHA_A, SHA_B))
            self.assertEqual(a["target_verification"], "VERIFIED")
            self.assertFalse(a["dispatch_authorized"])
            self.assertEqual(ledger.read(MISSION_ID)["actions"][0]["target_verification"],
                             "PINNED_CURRENT_UNCHECKED")
            self.database.close()
            self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
            ledger = ActionIntentLedger(self.database._connection)  # noqa: SLF001
            self.assertEqual(ledger.verify(MISSION_ID, "ACTION-A", self.scope,
                                           assert_selected_peer=lambda: None)["authority"], a["authority"])
            self.responses["repository-a"] = authority("repository-a", revision="3")
            with self.assertRaises(RepositoryAuthorityError):
                ledger.verify(MISSION_ID, "ACTION-A", self.scope, assert_selected_peer=lambda: None)
            self.assertEqual(ledger.verify(MISSION_ID, "ACTION-B", self.scope,
                                           assert_selected_peer=lambda: None)["authority"], b["authority"])
            heads["example/repository-b"] = "f" * 40
            with self.assertRaises(ActionIntentError):
                ledger.verify(MISSION_ID, "ACTION-B", self.scope, assert_selected_peer=lambda: None)

    def test_peer_change_during_http_readback_cannot_commit_verification(self) -> None:
        ledger = ActionIntentLedger(self.database._connection)
        ledger.materialize(MISSION_ID)
        ledger.bind(MISSION_ID, "ACTION-A", expected_slot_revision=1,
                    correlation_id="correlation-A", request_digest=REQUEST_DIGEST)
        def changed_peer() -> None:
            raise ActionIntentError("selected EP peer changed")

        with patch("forge.mission_cli._github_default_head", return_value=("main", SHA_A)):
            with self.assertRaisesRegex(ActionIntentError, "selected EP peer changed"):
                ledger.verify(MISSION_ID, "ACTION-A", self.scope,
                              assert_selected_peer=changed_peer)
        self.assertEqual(ledger.read(MISSION_ID)["actions"][0]["target_verification"], "UNVERIFIED")

    def test_missing_stored_baseline_provenance_fails_closed_after_restart(self) -> None:
        ledger = ActionIntentLedger(self.database._connection)
        ledger.materialize(MISSION_ID)
        ledger.bind(MISSION_ID, "ACTION-A", expected_slot_revision=1,
                    correlation_id="correlation-A", request_digest=REQUEST_DIGEST)
        with patch("forge.mission_cli._github_default_head", return_value=("main", SHA_A)):
            ledger.verify(MISSION_ID, "ACTION-A", self.scope, assert_selected_peer=lambda: None)
        connection = self.database._connection
        row = connection.execute(
            "SELECT document FROM mission_action_intent_revisions "
            "WHERE action_id='ACTION-A' AND slot_revision=3",
        ).fetchone()
        damaged = json.loads(row[0])
        damaged["baseline"]["approved_source_digest"] = "sha256:" + "0" * 64
        raw = json.dumps(damaged, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' "
            "AND name='mission_action_intent_revisions_immutable_update'",
        ).fetchone()[0]
        with connection:
            connection.execute("DROP TRIGGER mission_action_intent_revisions_immutable_update")
            connection.execute(
                "UPDATE mission_action_intent_revisions SET document=?,document_digest=? "
                "WHERE action_id='ACTION-A' AND slot_revision=3",
                (raw, "sha256:" + sha256(raw.encode()).hexdigest()),
            )
            connection.execute(trigger)
        self.database.close()
        self.database = RuntimeBootstrap(data_root=self.root, forge_version="test").open()
        with self.assertRaisesRegex(ActionIntentError, "baseline is inconsistent"):
            ActionIntentLedger(self.database._connection).read(MISSION_ID)


class ApprovedSourceTests(unittest.TestCase):
    def test_two_approved_sources_round_trip_without_weakening_serial_source(self) -> None:
        sources = (
            ApprovedRepositoryEvidenceSource("repository-b", "example/repository-b"),
            ApprovedRepositoryEvidenceSource("repository-a", "example/repository-a"),
        )
        mission = ArchitectureMission(
            id="MISSION-PREVIEW", candidate_id="candidate", title="Bounded proof",
            summary="Two independent targets", business_objective="Observe approved scope",
            business_value="Evidence", architecture_review_reference="architecture-decision",
            mission_recommendation_reference="recommendation",
            scope=("repository-a", "repository-b"), engineering_constraints=("no dispatch",),
            acceptance_criteria=("independent authority",), technical_assumptions=("two grants",),
            dependencies=("approved scope",), required_capabilities=("ep readback",),
            required_disciplines=(RequiredDiscipline.PLATFORM_ARCHITECTURE,),
            risks=("stale head",), status=ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
            repository_evidence_sources=sources,
        )
        self.assertEqual(
            [item["repository_id"] for item in mission.to_dict()["repository_evidence_sources"]],
            ["repository-a", "repository-b"],
        )
        self.assertEqual(ArchitectureMission.from_dict(mission.to_dict()), mission)
        planning = ArchitecturePlanningEvidence(
            mission.scope, ("none",), ("no dispatch",), ("stale head",),
            ("owner approval",), mission.dependencies, 1024, 512, "candidate-revision",
            repository_evidence_sources=sources,
        )
        self.assertEqual(ArchitecturePlanningEvidence.from_dict(planning.to_dict()), planning)
        with self.assertRaisesRegex(ValueError, "match exact Mission scope"):
            ArchitectureMission.from_dict({**mission.to_dict(),
                "repository_evidence_sources": [sources[0].to_dict()]})
