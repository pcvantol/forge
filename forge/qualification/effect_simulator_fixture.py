"""Rebind a pinned EP producer capture to one simulator-accepted Forge Action.

The external EP facts remain simulator data. This transform only changes the
identities and digests that the real EP serializer would derive from its own
accepted request; it does not bypass the Forge HTTP adapter or its verifier.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping

from .effect_fixture_conformance import capture, validate_capture


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def qualified_effect_result(
    payload: Mapping[str, Any], readback: Mapping[str, Any], legacy_terminal: bytes,
    *, no_change_conclusion: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    """Return v1.2 readback, v1.0 result and v1.5 terminal for a bound Action."""
    effect = payload["constraints"]["effect_contract"]
    fixture_name = f"{effect['mode'].lower()}-{effect['delivery'].lower()}.json"
    validate_capture(fixture_name)
    example = capture(fixture_name)
    template = example["effect_result"]["artifact"]["content"]
    terminal = json.loads(legacy_terminal)
    readback = deepcopy(readback)
    run_id = terminal["run"]["id"]
    submission = readback["submission"]
    source_revision = effect["source_revision"]
    binding = {
        "run_id": run_id, "submission_id": submission["id"],
        "project_id": submission["project_id"], "repository_id": payload["repository_id"],
        "producer_id": payload["producer"]["id"], "producer_type": payload["producer"]["type"],
        "producer_version": payload["producer"]["version"],
        "repository": payload["constraints"]["repository_revision_binding"]["repository_identity"],
        "correlation_id": payload["correlation_id"], "mission_id": payload["mission_id"],
        "engineering_action_id": payload["engineering_action_id"],
        "source_revision": source_revision,
        "accepted_request_digest": submission["accepted_request_digest"],
    }
    rows = deepcopy(template["result"])
    if no_change_conclusion:
        if effect["mode"] != "READ_ONLY_ASSESSMENT":
            raise ValueError("no-change report fixture requires read-only assessment")
        rows["summary"] = (
            "The committed architecture already satisfies the approved boundary; "
            "the assessment recommends no repository change.")
        for item in rows["criteria"]:
            item["analysis"] = (
                "The cited committed design establishes the boundary, so this "
                "criterion is met without changing repository content.")
    by_id = {item["id"]: item for item in rows["criteria"]}
    example_id, = by_id
    rows["criteria"] = [{**deepcopy(by_id[example_id]), "id": item["id"]}
                        for item in effect["criteria"]]
    manifest = deepcopy(template["source_manifest"])
    envelope = {
        "contract_version": "1.0", "artifact_type": "EP_EFFECT_RESULT",
        "binding": binding, "contract": deepcopy(effect),
        "contract_digest": _digest(effect)[7:], "source_manifest": manifest,
        "source_manifest_digest": _digest(manifest)[7:],
        "invocation_id": f"{run_id}:effect:0", "repair_ordinal": 0,
        "result": rows,
    }
    report_id = f"effect-result:{run_id}:0"
    report_digest = _digest(envelope)
    delivery = effect["delivery"]
    revision = terminal["repository"]["revision"] if delivery == "GIT" else None
    subject = {
        "subject_kind": "REPORT_ARTIFACT", "subject_id": report_id,
        "subject_digest": report_digest, "source_revision": source_revision,
        "source_snapshot_digest": _digest(manifest),
        "effect_contract_digest": _digest(effect),
        "criteria_digest": _digest(effect["criteria"]),
        "binding_digest": _digest(binding), "repair_ordinal": 0,
        "candidate_revision": terminal["repository"]["candidate"] if revision else None,
    }
    template_result = example["effect_result"]
    controls = deepcopy(template_result["validation_controls"])
    # The simulator does not execute these EP-owned commands. The original
    # capture proves their public shape; this receipt rebinds each observation
    # to the accepted run/subject and remains explicitly simulated evidence.
    profile = _digest({"version": "effect-validation@1.0", "subject": subject,
                       "controls": [[item["validation_id"], item["authority"]] for item in controls],
                       "validation_bindings": []})
    for index, item in enumerate(controls):
        item["command_id"] = f"{run_id}:effect:0:{index}"
        item["profile_digest"] = profile
    reviews = deepcopy(template_result["assurance_reviews"])
    for review in reviews:
        review["subject"] = subject
        review["profile_digest"] = profile
        review["invocation_id"] = f"{run_id}:{review['reviewer']}:effect:0"
        for row in review["coverage"]:
            row["evidence_ref"] = report_digest
    result = {
        "contract_version": "1.0", "outcome": "COMPLETE", "terminal": True,
        "effect_qualified": True, "subject": subject,
        "artifact": {"id": report_id, "digest_algorithm": "sha256",
                     "digest": report_digest, "content_type": "application/json",
                     "content": envelope},
        "validation_controls": controls, "assurance_reviews": reviews,
        "repair_rounds": {"used": 0, "maximum": 3},
        "delivery": {"kind": delivery, "revision": revision,
                     "pull_request": None if revision is None else template_result["delivery"]["pull_request"]},
    }
    terminal["contract_version"] = "1.5"
    terminal["host_execution"] = deepcopy(example["terminal_evidence"]["host_execution"])
    terminal["host_execution"]["start"]["target_commit"] = source_revision
    terminal["validation_controls"] = deepcopy(example["terminal_evidence"]["validation_controls"])
    for item in controls:
        terminal["validation_controls"]["controls"][item["validation_id"]]["command_id"] = item["command_id"]
    terminal["run"]["effect_qualified"] = True
    terminal["run"]["delivery_qualified"] = revision is not None
    terminal["repository"]["candidate"] = subject["candidate_revision"]
    terminal["repository"]["revision"] = revision
    terminal["repository"]["revision_required"] = revision is not None
    terminal["delivery"] = {"status": "DELIVERED" if revision else "NOT_DELIVERED",
                            "revision": revision}
    terminal["report"] = {key: result["artifact"][key] for key in (
        "id", "digest_algorithm", "digest", "content_type")}
    terminal["report"]["readback_path"] = (
        f"/v1/projects/{submission['project_id']}/submissions/{submission['id']}/effect-result")
    terminal["effect_result"] = {key: deepcopy(value) for key, value in result.items() if key != "artifact"}
    if revision is None:
        terminal["assurance"] = deepcopy(example["terminal_evidence"]["assurance"])
    readback["result"]["delivery_qualified"] = revision is not None
    readback["evidence"]["repository"]["revision"] = revision
    raw = json.dumps(terminal, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + sha256(raw).hexdigest()
    return readback, result, raw
