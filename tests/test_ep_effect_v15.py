"""Serialized EP HTTP effect-result qualification without a live EP process."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.ep_simulator import EpSimulatorScenario, EpSimulatorServer, EpSimulatorState
from forge.models.mission_effect import EffectRequest, MissionEffectPolicy
from forge.qualification.effect_fixture_conformance import CAPTURES, capture, validate_capture
from forge.qualification.effect_simulator_fixture import qualified_effect_result
from forge.runtime.database import RuntimeDatabase
from forge.scheduler.ep_effect_v15 import terminal_evidence
from forge.scheduler.ep_http_adapter import EngineeringPlatformHttpConfiguration, EngineeringPlatformHttpExecutionHost
from tests.test_ep_http_adapter import _request


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=True).encode("ascii")).hexdigest()


def _effect_request(mode: str = "READ_ONLY_ASSESSMENT", delivery: str = "EVIDENCE_ONLY"):
    base = _request()
    writes = () if delivery == "EVIDENCE_ONLY" else (
        ("src/boundary.py",) if mode == "BOUNDED_REPOSITORY_CHANGE" else ("docs/report.md",))
    effect = EffectRequest(MissionEffectPolicy(mode, delivery, ("docs/",), writes),
                           "a" * 40, (("criterion-1", "Assess the documented architecture boundary."),))
    return replace(base, producer_contract=replace(base.producer_contract, effect_request=effect),
                   effect_request=effect)


def _qualified_fixture(state: EpSimulatorState, submission_id: str, request, *,
                       delivery_revision: str | None = None) -> tuple[dict, dict, bytes]:
    """Bind a source-pinned EP producer capture to the accepted HTTP request."""
    assert request.effect_request is not None
    state.complete(submission_id, delivery_revision=delivery_revision)
    readback, raw = state.terminal_documents(submission_id)
    return qualified_effect_result(state.submitted_payload(submission_id), readback, raw)


class EffectV15HttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = RuntimeDatabase(Path(self.temporary.name),
                                        path=Path(self.temporary.name) / "runtime.db", forge_version="test")
        self.addCleanup(self.database.close)

    def _host(self, server, database=None):
        return EngineeringPlatformHttpExecutionHost(EngineeringPlatformHttpConfiguration(
            server.base_url, "forge", "sim-token", expected_instance_id="sim-ep",
            expected_consumer_id="forge-consumer", repository_id="forge",
            repository_identity="forge", peer_binding_id="sim-peer",
            peer_configuration_revision=1, peer_configuration_digest="sha256:" + "d" * 64,
            allow_loopback_http=True), database or self.database)

    def test_all_five_pinned_effect_variants_complete_over_http(self):
        variants = (
            ("READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY"),
            ("DOCUMENTATION_ONLY", "GIT"),
            ("ARCHITECTURE_DESIGN_ONLY", "EVIDENCE_ONLY"),
            ("ARCHITECTURE_DESIGN_ONLY", "GIT"),
            ("BOUNDED_REPOSITORY_CHANGE", "GIT"),
        )
        self.assertEqual(len(CAPTURES), len(variants))
        for mode, delivery in variants:
            with self.subTest(mode=mode, delivery=delivery):
                database = RuntimeDatabase(Path(self.temporary.name),
                    path=Path(self.temporary.name) / f"{mode}-{delivery}.db", forge_version="test")
                self.addCleanup(database.close)
                request = _effect_request(mode, delivery)
                state = EpSimulatorState(project_id="forge", repository_id="forge",
                    repository_identity="pcvantol/forge", consumer_id="forge-consumer",
                    instance_id="sim-ep", bearer_token="sim-token",
                    scenario=EpSimulatorScenario(effect_declaration_supported=True))
                with EpSimulatorServer(state) as server:
                    host = self._host(server, database)
                    self.assertIsNone(host.dispatch(request))
                    submission_id, = state.submission_ids()
                    revision = None if delivery == "EVIDENCE_ONLY" else "b" * 40
                    state.complete(submission_id, delivery_revision=revision)
                    baseline_readback, baseline_artifact = state.terminal_documents(submission_id)
                    readback, result, artifact = qualified_effect_result(
                        state.submitted_payload(submission_id), baseline_readback, baseline_artifact,
                    )
                    state.seed_terminal(submission_id, readback, artifact)
                    state.seed_effect_result(submission_id, result)
                    dispatch = host.recover_dispatch(request)
                    evidence = host.retrieve_evidence(dispatch)
                    self.assertEqual(evidence.effect_result["mode"], mode)
                    self.assertEqual(evidence.effect_result["delivery"], delivery)
                    self.assertEqual(evidence.repository_evidence.repository_revision,
                                     revision or request.effect_request.source_revision)
                    self.assertEqual(evidence.effect_result["report_digest"], result["artifact"]["digest"])
                    self.assertEqual(len(state.submission_ids()), 1)

    def test_read_only_result_uses_source_revision_without_git_delivery(self):
        request = _effect_request()
        state = EpSimulatorState(project_id="forge", repository_id="forge",
                                 repository_identity="pcvantol/forge", consumer_id="forge-consumer",
                                 instance_id="sim-ep", bearer_token="sim-token",
                                 scenario=EpSimulatorScenario(effect_declaration_supported=True))
        with EpSimulatorServer(state) as server:
            host = self._host(server)
            self.assertIsNone(host.dispatch(request))
            submission_id, = state.submission_ids()
            readback, result, artifact = _qualified_fixture(state, submission_id, request)
            state.seed_terminal(submission_id, readback, artifact)
            state.seed_effect_result(submission_id, result)
            dispatch = host.recover_dispatch(request)
            self.assertIsNotNone(dispatch)
            evidence = host.retrieve_evidence(dispatch)
            self.assertEqual(evidence.repository_evidence.repository_revision, "a" * 40)
            self.assertIsNone(evidence.repository_evidence.candidate_revision)
            self.assertEqual(evidence.effect_result["report_digest"], result["artifact"]["digest"])
            self.assertEqual([item["event"] for item in state.audit if item["event"] == "submission_accepted"],
                             ["submission_accepted"])

    def test_tampered_effect_report_is_rejected(self):
        request = _effect_request()
        state = EpSimulatorState(project_id="forge", repository_id="forge",
                                 repository_identity="pcvantol/forge", consumer_id="forge-consumer",
                                 instance_id="sim-ep", bearer_token="sim-token",
                                 scenario=EpSimulatorScenario(effect_declaration_supported=True))
        with EpSimulatorServer(state) as server:
            host = self._host(server)
            host.dispatch(request)
            submission_id, = state.submission_ids()
            readback, result, artifact = _qualified_fixture(state, submission_id, request)
            result["artifact"]["content"]["result"]["criteria"][0]["status"] = "UNSATISFIED"
            state.seed_terminal(submission_id, readback, artifact)
            state.seed_effect_result(submission_id, result)
            dispatch = host.recover_dispatch(request)
            with self.assertRaisesRegex(ValueError, "EP_EFFECT_TERMINAL_RESULT_MISMATCH|EP_EFFECT_REPORT_BYTES_MISMATCH"):
                host.retrieve_evidence(dispatch)

    def test_effect_result_identity_controls_and_reviews_fail_closed(self):
        request = _effect_request()
        state = EpSimulatorState(project_id="forge", repository_id="forge",
                                 repository_identity="pcvantol/forge", consumer_id="forge-consumer",
                                 instance_id="sim-ep", bearer_token="sim-token",
                                 scenario=EpSimulatorScenario(effect_declaration_supported=True))
        with EpSimulatorServer(state) as server:
            self._host(server).dispatch(request)
            submission_id, = state.submission_ids()
            readback, result, artifact = _qualified_fixture(state, submission_id, request)
        original_terminal = json.loads(artifact)
        def stale_profile(result, _terminal, _readback):
            for item in (*result["validation_controls"], *result["assurance_reviews"]):
                item["profile_digest"] = "sha256:" + "f" * 64

        cases = (
            ("terminal-version", lambda r, t, b: t.__setitem__("contract_version", "1.4"),
             "EP_EFFECT_TERMINAL_V15_REQUIRED"),
            ("result-outcome", lambda r, t, b: r.__setitem__("effect_qualified", False),
             "EP_EFFECT_RESULT_NOT_QUALIFIED"),
            ("accepted-digest", lambda r, t, b: b["submission"].__setitem__(
                "accepted_request_digest", "sha256:" + "0" * 64), "EP_EFFECT_ACCEPTED_REQUEST_MISMATCH"),
            ("producer", lambda r, t, b: t["producer"].__setitem__("id", "foreign-producer"),
             "EP_EFFECT_PRODUCER_MISMATCH"),
            ("correlation", lambda r, t, b: t["correlation"].__setitem__("mission_id", "foreign-mission"),
             "EP_EFFECT_CORRELATION_MISMATCH"),
            ("run", lambda r, t, b: t["run"].__setitem__("id", "foreign-run"),
             "EP_EFFECT_RUN_MISMATCH"),
            ("readback-terminal", lambda r, t, b: b["result"].__setitem__("terminal", False),
             "EP_EFFECT_RUN_MISMATCH"),
            ("source", lambda r, t, b: t["repository"].__setitem__("requested_revision", "0" * 40),
             "EP_EFFECT_SOURCE_MISMATCH"),
            ("delivery", lambda r, t, b: r["delivery"].__setitem__("revision", "b" * 40),
             "EP_EFFECT_READBACK_DELIVERY_MISMATCH"),
            ("readback-repository", lambda r, t, b: b["evidence"]["repository"].__setitem__(
                "revision", "b" * 40), "EP_EFFECT_READBACK_DELIVERY_MISMATCH"),
            ("controls", lambda r, t, b: r["validation_controls"].clear(),
             "EP_EFFECT_CONTROLS_UNQUALIFIED"),
            ("stale-profile", stale_profile, "EP_EFFECT_PROFILE_DIGEST_MISMATCH"),
            ("terminal-control", lambda r, t, b: t["validation_controls"]["controls"][
                "effect_scope_containment"].__setitem__("result", "FAIL"),
             "EP_EFFECT_TERMINAL_CONTROL_FAILED"),
            ("read-only-host-diff", lambda r, t, b: t["host_execution"]["terminal"]["diff"].__setitem__(
                "modified", 1), "EP_EFFECT_FORBIDDEN_TARGET_MUTATION"),
            ("reviews", lambda r, t, b: r["assurance_reviews"].clear(),
             "EP_EFFECT_REVIEWS_UNQUALIFIED"),
            ("malformed-finding", lambda r, t, b: r["assurance_reviews"][0]["findings"].append("bad"),
             "EP_EFFECT_REVIEWS_UNQUALIFIED"),
            ("open-disposition", lambda r, t, b: r["assurance_reviews"][0][
                "finding_dispositions"].append({"finding_id": "f-1", "disposition": "OPEN",
                                                 "evidence_ref": "report"}), "EP_EFFECT_REVIEWS_UNQUALIFIED"),
            ("repair-budget", lambda r, t, b: r["repair_rounds"].__setitem__("maximum", 4),
             "EP_EFFECT_REPAIR_BUDGET_INVALID"),
        )
        for label, mutate, expected in cases:
            with self.subTest(label=label):
                current_readback, current_result, terminal = (
                    deepcopy(readback), deepcopy(result), deepcopy(original_terminal))
                mutate(current_result, terminal, current_readback)
                terminal["effect_result"] = {key: deepcopy(value) for key, value in current_result.items()
                                             if key != "artifact"}
                raw = json.dumps(terminal, sort_keys=True, separators=(",", ":")).encode() + b"\n"
                current_readback["evidence"]["terminal_artifact"]["digest"] = (
                    "sha256:" + sha256(raw).hexdigest())
                with self.assertRaisesRegex(ValueError, expected):
                    terminal_evidence(request, current_readback, raw, current_result,
                                      host_id="sim-ep", expected_accepted_digest=(
                                          readback["submission"]["accepted_request_digest"]))

    def test_document_scope_cannot_publish_executable_file(self):
        request = _effect_request("DOCUMENTATION_ONLY", "GIT")
        state = EpSimulatorState(project_id="forge", repository_id="forge",
                                 repository_identity="pcvantol/forge", consumer_id="forge-consumer",
                                 instance_id="sim-ep", bearer_token="sim-token",
                                 scenario=EpSimulatorScenario(effect_declaration_supported=True))
        with EpSimulatorServer(state) as server:
            self._host(server).dispatch(request)
            submission_id, = state.submission_ids()
            readback, result, artifact = _qualified_fixture(
                state, submission_id, request, delivery_revision="b" * 40)
        envelope = result["artifact"]["content"]
        envelope["result"]["files"][0]["path"] = "docs/execute.py"
        report_digest = _digest(envelope)
        result["artifact"]["digest"] = report_digest
        result["subject"]["subject_digest"] = report_digest
        for review in result["assurance_reviews"]:
            review["subject"] = deepcopy(result["subject"])
            for item in review["coverage"]:
                item["evidence_ref"] = report_digest
        terminal = json.loads(artifact)
        terminal["effect_result"] = {key: deepcopy(value) for key, value in result.items()
                                     if key != "artifact"}
        terminal["report"]["digest"] = report_digest
        raw = json.dumps(terminal, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, "EP_EFFECT_GIT_REPORT_SCOPE_INVALID"):
            terminal_evidence(request, readback, raw, result, host_id="sim-ep",
                              expected_accepted_digest=readback["submission"]["accepted_request_digest"])


if __name__ == "__main__":
    unittest.main()
