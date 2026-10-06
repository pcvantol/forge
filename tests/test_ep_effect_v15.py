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
    """Build the EP producer projection from its published v1.0/1.5 fields."""
    state.complete(submission_id, delivery_revision=delivery_revision)
    readback, raw = state.terminal_documents(submission_id)
    terminal = json.loads(raw)
    effect = request.effect_request
    assert effect is not None
    fixture_name = f"{effect.policy.mode.lower()}-{effect.policy.delivery.lower()}.json"
    validate_capture(fixture_name)
    producer = capture(fixture_name)
    producer_envelope = producer["effect_result"]["artifact"]["content"]
    run_id = terminal["run"]["id"]
    source_manifest = deepcopy(producer_envelope["source_manifest"])
    rows = deepcopy(producer_envelope["result"])
    rows["criteria"][0]["id"] = effect.criteria[0][0]
    binding = {
        "run_id": run_id, "submission_id": submission_id, "project_id": "forge",
        "repository_id": "forge", "producer_id": "forge", "producer_type": "FORGE",
        "producer_version": "2.7.2", "repository": "pcvantol/forge",
        "correlation_id": request.correlation_id, "mission_id": request.mission_id,
        "engineering_action_id": request.action_id, "source_revision": effect.source_revision,
        "accepted_request_digest": readback["submission"]["accepted_request_digest"],
    }
    report_id = f"effect-result:{run_id}:0"
    envelope = {
        "contract_version": "1.0", "artifact_type": "EP_EFFECT_RESULT", "binding": binding,
        "contract": effect.to_dict(), "contract_digest": _digest(effect.to_dict())[7:],
        "source_manifest": source_manifest, "source_manifest_digest": _digest(source_manifest)[7:],
        "invocation_id": f"{run_id}:effect:0", "repair_ordinal": 0,
        "result": rows,
    }
    report_digest = _digest(envelope)
    subject = {
        "subject_kind": "REPORT_ARTIFACT", "subject_id": report_id, "subject_digest": report_digest,
        "source_revision": effect.source_revision, "source_snapshot_digest": _digest(source_manifest),
        "effect_contract_digest": _digest(effect.to_dict()),
        "criteria_digest": _digest(effect.to_dict()["criteria"]), "binding_digest": _digest(binding),
        "repair_ordinal": 0, "candidate_revision": None if delivery_revision is None else terminal["repository"]["candidate"],
    }
    selected_controls = ["effect_source_binding", "effect_output_integrity",
                         "effect_scope_containment", "report_criteria_contract"]
    if effect.policy.mode in {"DOCUMENTATION_ONLY", "ARCHITECTURE_DESIGN_ONLY"}:
        selected_controls.append("document_content_links_schema")
    if effect.policy.mode == "ARCHITECTURE_DESIGN_ONLY":
        selected_controls.append("design_criteria_contract")
    if effect.policy.mode == "BOUNDED_REPOSITORY_CHANGE":
        selected_controls.append("repository_json")
    started, ended = "2026-09-22T00:00:00+00:00", "2026-09-22T00:00:01+00:00"
    profile_digest = _digest({"subject": subject})
    controls = deepcopy(producer["effect_result"]["validation_controls"])
    assert [item["validation_id"] for item in controls] == selected_controls
    for index, item in enumerate(controls):
        item["command_id"] = f"{run_id}:effect:0:{index}"
        item["profile_digest"] = profile_digest
    reviews = deepcopy(producer["effect_result"]["assurance_reviews"])
    for item in reviews:
        item["subject"] = subject
        item["profile_digest"] = profile_digest
        item["invocation_id"] = f"{run_id}:{item['reviewer']}:effect:0"
        for coverage in item["coverage"]:
            coverage["evidence_ref"] = report_digest
    projection = {
        "contract_version": "1.0", "outcome": "COMPLETE", "terminal": True,
        "effect_qualified": True, "subject": subject,
        "artifact": {"id": report_id, "digest_algorithm": "sha256", "digest": report_digest,
                     "content_type": "application/json", "content": envelope},
        "validation_controls": controls, "assurance_reviews": reviews,
        "repair_rounds": {"used": 0, "maximum": 3},
        "delivery": {"kind": effect.policy.delivery, "revision": delivery_revision,
                     "pull_request": None if delivery_revision is None else 246},
    }
    terminal["contract_version"] = "1.5"
    terminal["assurance"] = deepcopy(producer["terminal_evidence"]["assurance"])
    terminal["effect_result"] = {key: deepcopy(value) for key, value in projection.items() if key != "artifact"}
    terminal["report"] = {key: projection["artifact"][key] for key in (
        "id", "digest_algorithm", "digest", "content_type")}
    terminal["report"]["readback_path"] = f"/v1/projects/forge/submissions/{submission_id}/effect-result"
    terminal["run"]["effect_qualified"] = True
    terminal["run"]["delivery_qualified"] = delivery_revision is not None
    terminal["repository"]["candidate"] = subject["candidate_revision"]
    terminal["repository"]["revision"] = delivery_revision
    terminal["repository"]["revision_required"] = delivery_revision is not None
    terminal["delivery"] = {"status": "DELIVERED" if delivery_revision else "NOT_DELIVERED",
                            "revision": delivery_revision}
    readback["result"]["delivery_qualified"] = delivery_revision is not None
    readback["evidence"]["repository"]["revision"] = delivery_revision
    artifact = json.dumps(terminal, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8") + b"\n"
    readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + sha256(artifact).hexdigest()
    from jsonschema import Draft202012Validator
    from importlib.resources import files
    root = files("forge.qualification").joinpath("fixtures", "fme-producer-v1")
    for name, value in (("effect-request-v1.schema.json", effect.to_dict()),
                        ("effect-report-envelope-v1.schema.json", envelope),
                        ("effect-result-v1.schema.json", projection),
                        ("terminal-evidence-v1.5.schema.json", terminal)):
        Draft202012Validator(json.loads(root.joinpath(name).read_text())).validate(value)
    return readback, projection, artifact


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


if __name__ == "__main__":
    unittest.main()
