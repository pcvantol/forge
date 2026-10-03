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
from typing import Any, Mapping


PRODUCER_SOURCE = {
    "repository": "pcvantol/engineering-platform",
    "revision": "5838f496538805c6012cbd6399217bc8b907102e",
    "serializer_path": "src/engineering_platform/submission_service.py",
    "serializer_sha256": "sha256:2c5c9e413179f1102034d042d89a2ffeb7b254cea176690cd73c8e4ee6f98a67",
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
    _require(disposition["state"] == "QUEUED" and disposition["terminal"] is False and
             disposition["execution_eligible"] is True and disposition["revision"] == 0,
             "v1.2 queued disposition")
    result = _object(readback["result"], frozenset((
        "outcome", "terminal", "delivery_qualified",
    )), "result")
    evidence = _object(readback["evidence"], frozenset((
        "status", "terminal_artifact", "repository",
    )), "evidence")
    _require(evidence["repository"]["id"] == repository_id, "evidence repository")
    if artifact_bytes is None:
        _require(readback["run"] is None and result == {
            "outcome": "NOT_STARTED", "terminal": False, "delivery_qualified": False,
        }, "pending run")
        _require(evidence["status"] == "NOT_TERMINAL" and
                 evidence["terminal_artifact"] is None, "pending evidence")
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
    _require(isinstance(run["id"], str) and run["terminal"] is True,
             "terminal run identity")
    run_id = run["id"]
    artifact_run = _object(artifact["run"], frozenset((
        "id", "outcome", "delivery_qualified", "execution_started_at",
        "execution_completed_at", "execution_duration_ms",
    )), "artifact run")
    _require(artifact_run["id"] == run_id, "artifact run binding")
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
    _object(artifact["delivery"], frozenset(("status", "revision")), "artifact delivery")
    _object(artifact["report"], frozenset(("id", "terminal_state")), "artifact report")
    _object(artifact["references"], frozenset((
        "finalization", "quality", "repair", "validation",
    )), "artifact references")
    _object(artifact["assurance"], frozenset((
        "status", "profile", "quality_review", "security_review", "repair_rounds", "findings",
    )), "artifact assurance")
    _require(artifact_repository["id"] == repository_id and
             artifact_run["outcome"] == result["outcome"] and
             artifact["report"]["terminal_state"] == result["outcome"] and
             evidence["repository"]["revision"] == artifact_repository["revision"] and
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
