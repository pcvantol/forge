"""Independent, source-pinned checks for the serial-write EP test fixtures.

The fixture oracle deliberately does not call Forge's EP adapter or simulator
serializer. Its pinned rules come from EP's immutable producer source and wire
contract, which are recorded in ``PRODUCER_SOURCE`` below.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping


PRODUCER_SOURCE = {
    "repository": "pcvantol/engineering-platform",
    "revision": "5838f496538805c6012cbd6399217bc8b907102e",
    "serializer_path": "src/engineering_platform/submission_service.py",
    "serializer_sha256": "sha256:2c5c9e413179f1102034d042d89a2ffeb7b254cea176690cd73c8e4ee6f98a67",
    "host_evidence_path": "src/engineering_platform/execution_host_evidence.py",
    "host_evidence_sha256": "sha256:54cf158dc9a8337c85bf3cd398c2ed2b08dc76be90eadc52f2805deb30bee2e7",
    "schema_path": "src/engineering_platform/schemas/producer-readback-v1.2.schema.json",
    "schema_sha256": "sha256:2381647f1d35695c6d826b86ff52c294325f76aa984ae66984d722d696ff8c15",
    "contract_path": "docs/engineering/EP_PRODUCER_READBACK_CONTRACT.md",
    "contract_sha256": "sha256:6b72a08a7e2430c6c6f8331589fb3b42b8159e8d9cfa788f6d9faf22b503d242",
    "readback_contract": "1.2",
    "terminal_contract": "1.4",
}
_SCHEMA = Path(__file__).resolve().parents[1] / "schemas/ep-producer-readback-v1.2.schema.json"
_READBACK = frozenset((
    "contract_version", "submission", "producer", "correlation", "provenance",
    "disposition", "run", "result", "evidence",
))
_DISPOSITION = frozenset((
    "state", "terminal", "execution_eligible", "revision", "operation_id",
    "event_reference", "reason", "actor_reference", "recorded_at",
    "resolution_submission_id", "retry_parent_run_id",
))
_TERMINAL = frozenset((
    "artifact_type", "contract_version", "submission", "producer", "correlation",
    "provenance", "run", "host_execution", "validation_controls", "repository",
    "delivery", "report", "references", "assurance",
))
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")


class ProducerFixtureError(ValueError):
    """One observed EP fixture diverged from its pinned producer evidence."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProducerFixtureError(reason)


def _object(value: Any, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    _require(isinstance(value, dict) and value.keys() == fields, f"{label} fields")
    return value


def _canonical_bytes(value: Any) -> bytes:
    """EP submission_service.py canonical artifact encoding, with one LF."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8") + b"\n"


def _digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _host_digest(value: Any) -> str:
    """EP execution_host_evidence.py hashes canonical JSON without an LF."""
    return _digest(_canonical_bytes(value)[:-1])


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_queued_disposition(disposition: Mapping[str, Any]) -> None:
    _require(disposition == {
        "state": "QUEUED", "terminal": False, "execution_eligible": True,
        "revision": 0, "operation_id": None, "event_reference": None,
        "reason": "NOT_RECORDED", "actor_reference": "NOT_RECORDED",
        "recorded_at": None, "resolution_submission_id": None,
        "retry_parent_run_id": None,
    }, "v1.2 queued disposition")


def _validate_host_execution(value: Any, baseline: str) -> None:
    host = _object(value, frozenset(("contract_version", "start", "terminal")),
                   "host execution")
    _require(host["contract_version"] == "1.0", "host execution version")
    start = _object(host["start"], frozenset((
        "status", "target_branch", "target_commit", "checkout_identity_digest",
        "tracked_file_count", "inventory_digest",
    )), "host start")
    _require(start["status"] == "AVAILABLE" and start["target_branch"] == "main" and
             start["target_commit"] == baseline and
             _nonnegative_int(start["tracked_file_count"]) and
             isinstance(start["inventory_digest"], str) and
             _SHA256.fullmatch(start["inventory_digest"]) is not None,
             "host start snapshot")
    checkout = {key: start[key] for key in (
        "target_branch", "target_commit", "inventory_digest",
    )}
    _require(start["checkout_identity_digest"] == _host_digest(checkout),
             "host checkout identity")
    terminal = _object(host["terminal"], frozenset((
        "status", "tracked_file_count", "inventory_digest", "worktree_state",
        "diff", "activity",
    )), "host terminal")
    diff = _object(terminal["diff"], frozenset((
        "modified", "created", "deleted", "renamed",
    )), "host diff")
    activity = _object(terminal["activity"], frozenset((
        "provider_invocations", "host_validation_actions",
    )), "host activity")
    _require(terminal["status"] == "AVAILABLE" and
             terminal["worktree_state"] == "CLEAN" and
             _nonnegative_int(terminal["tracked_file_count"]) and
             isinstance(terminal["inventory_digest"], str) and
             _SHA256.fullmatch(terminal["inventory_digest"]) is not None and
             all(_nonnegative_int(item) for item in (*diff.values(), *activity.values())),
             "host terminal snapshot")


def _validate_repository_delivery(
    payload: Mapping[str, Any], repository: Mapping[str, Any],
    delivery: Mapping[str, Any], *, repository_id: str, outcome: str,
    delivery_qualified: bool,
) -> None:
    binding = payload["constraints"]["repository_revision_binding"]
    requested = binding["requested_revision"]
    allowed = binding["allowed_baseline_revision"]
    baseline = allowed or requested
    _require(isinstance(requested, str) and _REVISION.fullmatch(requested) is not None and
             (allowed is None or isinstance(allowed, str) and
              _REVISION.fullmatch(allowed) is not None), "request revision binding")
    _require(repository["id"] == repository_id and
             repository["requested_revision"] == requested and
             repository["execution_baseline"] == baseline and
             repository["baseline_transition"] == {
                 "status": "ALLOWED" if allowed is not None else "EXACT",
                 "from": requested, "to": baseline, "allowed_to": allowed,
             }, "artifact repository binding")
    revision = repository["revision"]
    _require((revision is None or isinstance(revision, str) and
              _REVISION.fullmatch(revision) is not None) and
             repository["revision_required"] is (outcome == "COMPLETE") and
             delivery == {
                 "status": "DELIVERED" if delivery_qualified else "NOT_DELIVERED",
                 "revision": revision,
             } and (not delivery_qualified or revision is not None),
             "artifact delivery binding")


def source_receipt(schema_path: Path = _SCHEMA) -> dict[str, Any]:
    raw = schema_path.read_bytes()
    _require(_digest(raw) == PRODUCER_SOURCE["schema_sha256"], "producer schema bytes")
    schema = json.loads(raw)
    _require(schema.get("properties", {}).get("contract_version", {}).get("const") == "1.2",
             "producer schema version")
    _require(set(schema.get("required", ())) == _READBACK, "producer readback root schema")
    for field in ("submission", "producer", "correlation", "provenance", "result", "evidence"):
        _require(schema["properties"][field].get("additionalProperties") is False,
                 f"producer {field} schema policy")
    return {**PRODUCER_SOURCE, "schema_fixture_sha256": _digest(raw),
            "source_schema_discrepancy": (
                "Producer source/tests emit resolution_submission_id and retry_parent_run_id "
                "in v1.2 disposition; the pinned v1.2 schema omits them. "
                "The serial-write gate validates the emitted source shape."
            )}


def _accepted_request_digest(payload: Mapping[str, Any]) -> str:
    accepted = {
        "repository_id": payload["repository_id"],
        "producer": payload["producer"],
        "prompt_digest": sha256(payload["prompt"].encode("utf-8")).hexdigest(),
        "constraints": payload["constraints"],
        "correlation_id": payload["correlation_id"],
        "mission_id": payload["mission_id"],
        "engineering_action_id": payload["engineering_action_id"],
    }
    return _digest(_canonical_bytes(accepted))


def validate_fixture(
    payload: Mapping[str, Any], readback: Mapping[str, Any], artifact_bytes: bytes | None,
    *, project_id: str, repository_id: str, submission_id: str,
) -> dict[str, str | None]:
    """Verify one observed EP seam without using Forge's digest helpers."""
    _object(readback, _READBACK, "readback")
    _require(readback["contract_version"] == "1.2", "readback version")
    submission = _object(readback["submission"], frozenset((
        "id", "project_id", "repository_id", "state", "admission", "transport",
        "created_at", "accepted_request_digest",
    )), "submission")
    _require((submission["id"], submission["project_id"], submission["repository_id"])
             == (submission_id, project_id, repository_id), "submission scope")
    _require(submission["state"] == "QUEUED", "submission queue state")
    _require(submission["accepted_request_digest"] == _accepted_request_digest(payload),
             "accepted request digest")
    _require(submission["admission"] == "ADMITTED" and submission["transport"] == "HTTP",
             "submission admission")
    producer = _object(readback["producer"], frozenset(("id", "type", "version")), "producer")
    _require(producer == payload["producer"], "producer identity")
    correlation = _object(readback["correlation"], frozenset((
        "correlation_id", "mission_id", "engineering_action_id",
    )), "correlation")
    _require(correlation == {key: payload[key] for key in correlation}, "correlation identity")
    provenance = _object(readback["provenance"], frozenset(("status", "forge_execution")),
                         "provenance")
    _require(provenance["status"] == "PERSISTED" and
             provenance["forge_execution"] == payload["constraints"]["forge_execution"],
             "accepted provenance")
    disposition = _object(readback["disposition"], _DISPOSITION, "disposition")
    _validate_queued_disposition(disposition)
    result = _object(readback["result"], frozenset((
        "outcome", "terminal", "delivery_qualified",
    )), "result")
    evidence = _object(readback["evidence"], frozenset((
        "status", "terminal_artifact", "repository",
    )), "evidence")
    evidence_repository = _object(evidence["repository"],
                                  frozenset(("id", "revision")), "evidence repository")
    _require(evidence_repository["id"] == repository_id, "evidence repository")
    if artifact_bytes is None:
        _require(readback["run"] is None and result == {
            "outcome": "NOT_STARTED", "terminal": False, "delivery_qualified": False,
        }, "pending run")
        _require(evidence["status"] == "NOT_TERMINAL" and
                 evidence["terminal_artifact"] is None and
                 evidence_repository["revision"] is None, "pending evidence")
        return {"submission_id": submission_id, "run_id": None,
                "accepted_request_digest": submission["accepted_request_digest"],
                "artifact_sha256": None, "fixture_sha256": _digest(_canonical_bytes(readback))}
    _require(isinstance(artifact_bytes, bytes), "terminal artifact type")
    try:
        artifact = json.loads(artifact_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProducerFixtureError("terminal artifact JSON") from error
    _require(artifact_bytes == _canonical_bytes(artifact), "terminal canonical bytes")
    _object(artifact, _TERMINAL, "terminal artifact")
    _require(artifact["artifact_type"] == "EP_TERMINAL_EVIDENCE" and
             artifact["contract_version"] == "1.4", "terminal contract")
    run = _object(readback["run"], frozenset((
        "id", "state", "terminal", "operator_resolution", "updated_at",
        "execution_started_at", "execution_completed_at", "execution_duration_ms",
    )), "terminal run")
    _require(isinstance(run["id"], str) and run["id"] and run["terminal"] is True and
             run["operator_resolution"] == "NONE" and
             run["state"] == result["outcome"] and result["terminal"] is True and
             isinstance(result["delivery_qualified"], bool),
             "terminal run identity")
    run_id = run["id"]
    artifact_run = _object(artifact["run"], frozenset((
        "id", "outcome", "delivery_qualified", "execution_started_at",
        "execution_completed_at", "execution_duration_ms",
    )), "artifact run")
    _require(artifact_run["id"] == run_id and
             artifact_run["outcome"] == run["state"] and
             artifact_run["delivery_qualified"] is result["delivery_qualified"] and
             all(artifact_run[key] == run[key] for key in (
                 "execution_started_at", "execution_completed_at", "execution_duration_ms",
             )) and run["updated_at"] == run["execution_completed_at"] and
             _nonnegative_int(run["execution_duration_ms"]),
             "artifact run binding")
    artifact_submission = _object(artifact["submission"], frozenset((
        "id", "project_id", "repository_id", "accepted_request_digest",
    )), "artifact submission")
    _require(artifact_submission == {
        "id": submission_id, "project_id": project_id, "repository_id": repository_id,
        "accepted_request_digest": submission["accepted_request_digest"],
    }, "artifact submission binding")
    _require(artifact["producer"] == producer and artifact["correlation"] == correlation and
             artifact["provenance"] == provenance["forge_execution"],
             "artifact identity/provenance")
    artifact_repository = _object(artifact["repository"], frozenset((
        "id", "requested_revision", "execution_baseline", "baseline_transition",
        "candidate", "revision", "revision_required",
    )), "artifact repository")
    delivery = _object(artifact["delivery"], frozenset(("status", "revision")),
                       "artifact delivery")
    report = _object(artifact["report"], frozenset(("id", "terminal_state")),
                     "artifact report")
    _object(artifact["references"], frozenset((
        "finalization", "quality", "repair", "validation",
    )), "artifact references")
    _object(artifact["assurance"], frozenset((
        "status", "profile", "quality_review", "security_review", "repair_rounds", "findings",
    )), "artifact assurance")
    _validate_repository_delivery(payload, artifact_repository, delivery,
                                  repository_id=repository_id, outcome=run["state"],
                                  delivery_qualified=result["delivery_qualified"])
    _validate_host_execution(artifact["host_execution"],
                             artifact_repository["execution_baseline"])
    _require(report == {"id": "report:" + run_id, "terminal_state": run["state"]} and
             evidence_repository["revision"] == artifact_repository["revision"] and
             evidence["status"] == "AVAILABLE", "artifact result binding")
    controls = _object(artifact["validation_controls"],
                       frozenset(("contract_version", "status")), "validation controls")
    _require(controls == {"contract_version": "1.0", "status": "UNAVAILABLE"},
             "synthetic validation control authority")
    terminal = _object(evidence["terminal_artifact"], frozenset((
        "id", "content_type", "digest_algorithm", "digest",
    )), "terminal reference")
    artifact_digest = _digest(artifact_bytes)
    _require(terminal == {"id": "terminal-evidence:" + run_id,
                          "content_type": "application/json", "digest_algorithm": "sha256",
                          "digest": artifact_digest}, "terminal bytes/digest binding")
    return {"submission_id": submission_id, "run_id": run_id,
            "accepted_request_digest": submission["accepted_request_digest"],
            "artifact_sha256": artifact_digest,
            "fixture_sha256": _digest(_canonical_bytes({
                "request": payload, "readback": readback, "artifact_sha256": artifact_digest,
            }))}


def rejection_matrix(payload: Mapping[str, Any], readback: Mapping[str, Any],
                     artifact_bytes: bytes, *, project_id: str, repository_id: str,
                     submission_id: str) -> list[dict[str, str]]:
    """Prove the same oracle accepts valid input and rejects targeted drift."""
    validate_fixture(payload, readback, artifact_bytes, project_id=project_id,
                     repository_id=repository_id, submission_id=submission_id)
    cases: list[tuple[str, dict[str, Any], bytes]] = []

    def changed(name: str, path: tuple[str, ...], value: Any) -> None:
        document = deepcopy(readback)
        target = document
        for key in path[:-1]:
            target = target[key]
        if value is _MISSING:
            del target[path[-1]]
        else:
            target[path[-1]] = value
        cases.append((name, document, artifact_bytes))

    changed("missing-provenance", ("provenance",), _MISSING)
    changed("changed-provenance", ("provenance", "forge_execution"), {"contract_version": "wrong"})
    changed("wrong-version", ("contract_version",), "1.3")
    changed("changed-digest", ("evidence", "terminal_artifact", "digest"), "sha256:" + "0" * 64)
    changed("foreign-project", ("submission", "project_id"), "foreign-project")
    changed("foreign-repository", ("submission", "repository_id"), "foreign-repository")
    changed("foreign-submission", ("submission", "id"), "foreign-submission")
    changed("foreign-run", ("run", "id"), "foreign-run")
    changed("unexpected-field", ("submission", "unexpected"), "value")
    changed("missing-field", ("submission", "accepted_request_digest"), _MISSING)
    changed("queued-operation", ("disposition", "operation_id"), "fake-operator-operation")
    changed("queued-reason", ("disposition", "reason"), "MANUAL_OVERRIDE")
    changed("queued-submission-state", ("submission", "state"), "CANCELLED")
    changed("terminal-run-state", ("run", "state"), "FAILED")
    changed("terminal-delivery-qualified", ("result", "delivery_qualified"), False)
    cases.append(("changed-artifact-bytes", deepcopy(readback), artifact_bytes + b" "))

    def changed_artifact(name: str, path: tuple[str, ...], value: Any) -> None:
        artifact = json.loads(artifact_bytes)
        target = artifact
        for key in path[:-1]:
            target = target[key]
        if value is _MISSING:
            del target[path[-1]]
        else:
            target[path[-1]] = value
        raw = _canonical_bytes(artifact)
        document = deepcopy(readback)
        document["evidence"]["terminal_artifact"]["digest"] = _digest(raw)
        cases.append((name, document, raw))

    changed_artifact("artifact-unexpected-field", ("run", "unexpected"), "value")
    changed_artifact("artifact-missing-field", ("validation_controls",), _MISSING)
    changed_artifact("artifact-foreign-run", ("run", "id"), "foreign-run")
    changed_artifact("artifact-run-timing", ("run", "execution_started_at"), "foreign-time")
    changed_artifact("artifact-host-null", ("host_execution",), None)
    changed_artifact("artifact-host-empty", ("host_execution",), {})
    changed_artifact("artifact-host-commit", ("host_execution", "start", "target_commit"), "f" * 40)
    changed_artifact("artifact-host-digest", ("host_execution", "start", "checkout_identity_digest"),
                     "sha256:" + "0" * 64)
    changed_artifact("artifact-requested-revision", ("repository", "requested_revision"), "f" * 40)
    changed_artifact("artifact-delivery-revision", ("delivery", "revision"), "f" * 40)
    changed_artifact("artifact-baseline-transition", ("repository", "baseline_transition", "to"),
                     "f" * 40)
    changed_artifact("artifact-report-id", ("report", "id"), "report:foreign-run")
    results = []
    for name, document, raw in cases:
        try:
            validate_fixture(payload, document, raw, project_id=project_id,
                             repository_id=repository_id, submission_id=submission_id)
        except ProducerFixtureError as error:
            results.append({"case": name, "result": "REJECTED", "reason": str(error)})
        else:
            raise ProducerFixtureError(f"negative fixture {name} was accepted")
    return results


_MISSING = object()
