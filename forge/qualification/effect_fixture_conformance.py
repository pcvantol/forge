"""Independent, byte-pinned checks of EP's installed FME HTTP captures."""

from __future__ import annotations

from hashlib import sha256
from importlib.resources import files
import json
from typing import Any


PRODUCER_SOURCE = "bc2e8d6800cc64ef44990ce9412d6b9c1c8824ff"
PRODUCER_VERSION = "2.3.111"
MANIFEST_SHA256 = "4490eb31468028138d4942acda5380464f99fc70cb4666f32278b809a1922896"
CAPTURES = (
    "read_only_assessment-evidence_only.json", "documentation_only-git.json",
    "architecture_design_only-evidence_only.json", "architecture_design_only-git.json",
    "bounded_repository_change-git.json",
)
SCHEMAS = (
    "effect-request-v1.schema.json", "effect-report-envelope-v1.schema.json",
    "effect-result-v1.1.schema.json", "terminal-evidence-v1.6.schema.json",
    "effect-validation-profile-v1.schema.json",
)


class EffectFixtureError(ValueError):
    """The installed producer fixture or its semantic linkage has drifted."""


def _root():
    return files("forge.qualification").joinpath("fixtures", "fme-producer-v1")


def _bytes(name: str) -> bytes:
    try:
        return _root().joinpath(name).read_bytes()
    except OSError as error:
        raise EffectFixtureError(f"EP effect fixture {name} is missing") from error


def _hash(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def source_receipt() -> dict[str, Any]:
    raw = _bytes("manifest.json")
    if _hash(raw) != MANIFEST_SHA256:
        raise EffectFixtureError("EP effect producer manifest bytes changed")
    manifest = json.loads(raw)
    if (manifest.get("producer_source_sha") != PRODUCER_SOURCE
            or manifest.get("producer_version") != PRODUCER_VERSION
            or set(manifest.get("captures_sha256", {})) != {*CAPTURES, "errors.json"}
            or set(manifest.get("schema_sha256", {})) != set(SCHEMAS)
            or set(manifest.get("serializer_sha256", {})) != {
                "effect_readback.py", "server.py", "submission_service.py",
                "effect_evidence.py", "effect_contract.py",
            }):
        raise EffectFixtureError("EP effect producer manifest identity changed")
    for section in ("captures_sha256", "schema_sha256"):
        for name, expected in manifest[section].items():
            if _hash(_bytes(name)) != expected:
                raise EffectFixtureError(f"EP effect producer {name} bytes changed")
    return {"producer_source_sha": PRODUCER_SOURCE, "producer_version": PRODUCER_VERSION,
            "contract_versions": {"request": "1.0", "report_envelope": "1.0",
                                  "result": "1.1", "validation_profile": "1.0", "terminal": "1.6"},
            "manifest_sha256": "sha256:" + MANIFEST_SHA256,
            "capture_sha256": dict(manifest["captures_sha256"]),
            "schema_sha256": dict(manifest["schema_sha256"]),
            "serializer_sha256": dict(manifest["serializer_sha256"])}


def capture(name: str) -> dict[str, Any]:
    if name not in CAPTURES:
        raise EffectFixtureError("unknown EP effect producer capture")
    source_receipt()
    document = json.loads(_bytes(name))
    if (document.get("producer_source_sha") != PRODUCER_SOURCE
            or document.get("producer_version") != PRODUCER_VERSION):
        raise EffectFixtureError("EP effect capture producer identity changed")
    return document


def validate_capture(name: str) -> dict[str, Any]:
    """Check the four published schemas and the independent cross-object joins."""
    from jsonschema import Draft202012Validator, ValidationError

    document = capture(name)
    request = document.get("request")
    result = document.get("effect_result")
    terminal = document.get("terminal_evidence")
    if not all(isinstance(value, dict) for value in (request, result, terminal)):
        raise EffectFixtureError("EP effect capture omits a public HTTP document")
    try:
        envelope = result["artifact"]["content"]
        inputs = (request["constraints"]["effect_contract"], envelope, result, terminal,
                  result["validation_profile"])
        for schema_name, value in zip(SCHEMAS, inputs, strict=True):
            schema = json.loads(_bytes(schema_name))
            Draft202012Validator(schema).validate(value)
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise EffectFixtureError("EP effect capture violates pinned producer schema") from error
    accepted = envelope["binding"]["accepted_request_digest"]
    report_digest = _digest(envelope)
    projection = {key: value for key, value in result.items() if key != "artifact"}
    report = {key: value for key, value in result["artifact"].items() if key != "content"}
    report["readback_path"] = (f"/v1/projects/{envelope['binding']['project_id']}/submissions/"
                               f"{envelope['binding']['submission_id']}/effect-result")
    subject = result["subject"]
    profile = result["validation_profile"]
    profile_digest = _digest(profile)
    if (envelope["contract"] != request["constraints"]["effect_contract"]
            or envelope["contract_digest"] != _digest(envelope["contract"])[7:]
            or envelope["source_manifest_digest"] != _digest(envelope["source_manifest"])[7:]
            or result["artifact"]["digest"] != report_digest
            or subject["subject_digest"] != report_digest
            or subject["binding_digest"] != _digest(envelope["binding"])
            or subject["source_snapshot_digest"] != _digest(envelope["source_manifest"])
            or terminal["submission"]["accepted_request_digest"] != accepted
            or terminal["effect_result"] != projection
            or terminal["report"] != report
            or terminal["run"]["effect_qualified"] != result["effect_qualified"]
            or terminal["run"]["id"] != envelope["binding"]["run_id"]
            or terminal["repository"]["requested_revision"] != envelope["contract"]["source_revision"]
            or result["delivery"]["kind"] != envelope["contract"]["delivery"]):
        raise EffectFixtureError("EP effect capture binding or report digest changed")
    if (profile["subject"] != subject
            or profile["controls"] != [[item["validation_id"], item["authority"]]
                                       for item in result["validation_controls"]]
            or any(item["profile_digest"] != profile_digest
                   for item in (*result["validation_controls"], *result["assurance_reviews"]))):
        raise EffectFixtureError("EP effect capture validation profile changed")
    return {"capture": name, "producer_source_sha": PRODUCER_SOURCE,
            "mode": envelope["contract"]["mode"], "delivery": result["delivery"]["kind"],
            "report_digest": report_digest, "qualified": result["effect_qualified"],
            "control_count": len(result["validation_controls"]),
            "review_count": len(result["assurance_reviews"])}
