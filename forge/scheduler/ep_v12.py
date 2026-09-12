"""Fail-closed Forge consumer mapping for EP producer readback v1.2."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from forge.models.execution_host import (
    ExecutionEvidenceOutcome,
    ExecutionHostEvidence,
    ExecutionRepositoryEvidence,
)


_OUTCOMES = frozenset(item.value.upper() for item in ExecutionEvidenceOutcome)
_READBACK_KEYS = frozenset({"contract_version", "submission", "producer", "correlation", "provenance", "disposition", "run", "result", "evidence"})


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"EP terminal evidence {name} must be an object")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"EP terminal evidence {name} must be a non-empty string")
    return value


def _sha256(value: Any, name: str) -> str:
    value = _string(value, name)
    if not value.startswith("sha256:") or len(value.removeprefix("sha256:")) != 64:
        raise ValueError(f"EP terminal evidence {name} must be a SHA-256 identity")
    try:
        int(value.removeprefix("sha256:"), 16)
    except ValueError as error:
        raise ValueError(f"EP terminal evidence {name} must be a SHA-256 identity") from error
    return value


def _terminal_outcome(value: Any, name: str) -> str:
    value = _string(value, name).upper()
    if value not in _OUTCOMES:
        raise ValueError(f"EP terminal evidence {name} is not a terminal outcome")
    return value


def _timestamp(value: Any, name: str) -> str:
    value = _string(value, name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"EP terminal evidence {name} is not an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"EP terminal evidence {name} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _duration(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"EP terminal evidence {name} must be a positive integer")
    return value


def _terminal_timing(run: Mapping[str, Any], artifact_run: Mapping[str, Any]) -> tuple[str, str, int]:
    """Validate durable EP timing and bind it to new terminal artifacts.

    EP v2.3.19 binds timing into newly written artifacts. Earlier immutable
    artifacts cannot be retroactively changed, so a wholly absent artifact
    timing triplet remains compatible only when authenticated readback itself
    supplies the complete, internally consistent durable triplet.
    """
    started = _timestamp(run.get("execution_started_at"), "readback execution start")
    completed = _timestamp(run.get("execution_completed_at"), "readback execution completion")
    duration = _duration(run.get("execution_duration_ms"), "readback execution duration")
    expected_duration = round((
        datetime.fromisoformat(completed) - datetime.fromisoformat(started)
    ).total_seconds() * 1000)
    if expected_duration != duration:
        raise ValueError("EP terminal evidence readback execution duration contradicts timestamps")

    artifact_values = tuple(artifact_run.get(key) for key in (
        "execution_started_at", "execution_completed_at", "execution_duration_ms",
    ))
    if any(value is not None for value in artifact_values):
        if any(value is None for value in artifact_values):
            raise ValueError("EP terminal artifact execution timing is incomplete")
        artifact_started = _timestamp(artifact_values[0], "artifact execution start")
        artifact_completed = _timestamp(artifact_values[1], "artifact execution completion")
        artifact_duration = _duration(artifact_values[2], "artifact execution duration")
        if (artifact_started, artifact_completed, artifact_duration) != (started, completed, duration):
            raise ValueError("EP terminal artifact execution timing differs from readback")
    return started, completed, duration


def terminal_evidence(readback: Mapping[str, Any], artifact: bytes, *, host_id: str,
                      receipt_id: str | None = None,
                      resolved_from_host_run_id: str | None = None) -> ExecutionHostEvidence:
    """Map one immutable EP terminal artifact only when every identity agrees.

    Artifact digest integrity establishes byte origin, not semantic identity;
    all readback/artifact fields used below must therefore be explicitly
    present, correctly typed, and mutually consistent.
    """
    if set(readback) != _READBACK_KEYS or readback.get("contract_version") != "1.2":
        raise ValueError("unsupported EP readback contract")
    evidence = _object(readback.get("evidence"), "readback evidence")
    terminal = _object(evidence.get("terminal_artifact"), "terminal artifact reference")
    run = _object(readback.get("run"), "readback run")
    result = _object(readback.get("result"), "readback result")
    provenance_root = _object(readback.get("provenance"), "readback provenance")
    provenance = _object(provenance_root.get("forge_execution"), "Forge provenance")
    correlation = _object(readback.get("correlation"), "readback correlation")
    submission = _object(readback.get("submission"), "readback submission")
    producer = _object(readback.get("producer"), "readback producer")
    repository_readback = _object(evidence.get("repository"), "readback repository")
    if result.get("terminal") is not True or run.get("terminal") is not True:
        raise ValueError("EP terminal evidence terminal flags are incomplete or contradictory")

    artifact_digest = "sha256:" + hashlib.sha256(artifact).hexdigest()
    if _sha256(terminal.get("digest"), "terminal artifact digest") != artifact_digest:
        raise ValueError("EP_TERMINAL_EVIDENCE_DIGEST_MISMATCH")
    try:
        document = json.loads(artifact)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("EP terminal artifact is invalid JSON") from error
    document = _object(document, "artifact document")
    if document.get("artifact_type") != "EP_TERMINAL_EVIDENCE" or document.get("contract_version") != "1.2":
        raise ValueError("unsupported EP terminal artifact contract")

    artifact_correlation = _object(document.get("correlation"), "artifact correlation")
    artifact_provenance = _object(document.get("provenance"), "artifact provenance")
    artifact_run = _object(document.get("run"), "artifact run")
    artifact_report = _object(document.get("report"), "artifact report")
    artifact_submission = _object(document.get("submission"), "artifact submission")
    artifact_producer = _object(document.get("producer"), "artifact producer")
    repository = _object(document.get("repository"), "artifact repository")

    # Required, immutable accepted-request identities cannot be satisfied by
    # the accidental equality of two missing values.
    accepted_readback = _sha256(submission.get("accepted_request_digest"), "readback accepted request digest")
    accepted_artifact = _sha256(artifact_submission.get("accepted_request_digest"), "artifact accepted request digest")
    if accepted_readback != accepted_artifact:
        raise ValueError("EP terminal artifact accepted request digest differs from readback")
    if artifact_correlation != correlation or artifact_producer != producer:
        raise ValueError("EP terminal artifact identity differs from readback")

    provenance_keys = (
        "action_id", "contract_version", "correlation_id", "host_id", "intent_id", "intent_revision",
        "mission_id", "mission_revision", "repository_id", "retry_of_correlation_id", "runtime_prompt",
    )
    # Forge provenance v1.1 adds submitted-envelope attribution. v1.2 adds
    # the separately versioned, redacted Action-context envelope. Historic
    # v1.0 evidence remains byte-for-byte verifiable without invented fields.
    if provenance.get("contract_version") in {"1.1", "1.2"}:
        provenance_keys += ("producer_contract_version", "forge_application_version")
    if provenance.get("contract_version") == "1.2":
        provenance_keys += ("action_context_envelope",)
    expected_provenance = {key: provenance.get(key) for key in provenance_keys}
    if artifact_provenance != expected_provenance:
        raise ValueError("EP terminal artifact provenance differs from readback")
    retry_of_correlation_id = provenance.get("retry_of_correlation_id")
    if retry_of_correlation_id is not None and (not isinstance(retry_of_correlation_id, str) or not retry_of_correlation_id):
        raise ValueError("EP terminal evidence retry correlation is invalid")
    if artifact_run.get("id") != run.get("id"):
        raise ValueError("EP terminal artifact run differs from readback")
    execution_started_at, execution_completed_at, execution_duration_ms = _terminal_timing(run, artifact_run)
    if (artifact_submission.get("id"), artifact_submission.get("project_id"), artifact_submission.get("repository_id")) != (
        submission.get("id"), submission.get("project_id"), submission.get("repository_id"),
    ):
        raise ValueError("EP terminal artifact submission differs from readback")

    outcome = _terminal_outcome(result.get("outcome"), "readback result outcome")
    if (_terminal_outcome(artifact_run.get("outcome"), "artifact run outcome"),
            _terminal_outcome(artifact_report.get("terminal_state"), "artifact report terminal state"),
            _terminal_outcome(run.get("state"), "readback run state")) != (outcome, outcome, outcome):
        raise ValueError("EP terminal outcome fields contradict one another")
    qualified_readback, qualified_artifact = result.get("delivery_qualified"), artifact_run.get("delivery_qualified")
    if not isinstance(qualified_readback, bool) or not isinstance(qualified_artifact, bool) or qualified_readback != qualified_artifact:
        raise ValueError("EP terminal delivery qualification fields contradict one another")

    revision = repository.get("revision")
    if revision is not None and not isinstance(revision, str):
        raise ValueError("EP terminal artifact revision is invalid")
    if (repository.get("id"), revision) != (repository_readback.get("id"), repository_readback.get("revision")):
        raise ValueError("EP terminal artifact repository differs from readback")
    if outcome == "COMPLETE":
        if not qualified_readback or not revision or repository.get("revision_required") is not True:
            raise ValueError("EP complete terminal artifact lacks qualified delivery revision")
    elif qualified_readback:
        # A terminal failed/blocked run is never a Forge successful delivery.
        raise ValueError("EP non-complete terminal evidence cannot be delivery-qualified")

    # EP owns assurance policy. Forge only verifies that the immutable
    # terminal record carries its bound assurance outcome and findings proof.
    # A host-verified Managed no-op has no candidate review to report. EP
    # represents that case explicitly as NOT_RECORDED rather than inventing a
    # profile or review result. Accept only that complete, empty shape; every
    # partial omission remains a contract failure.
    assurance = _object(document.get("assurance"), "artifact assurance")
    repair = _object(assurance.get("repair_rounds"), "assurance repair rounds")
    if any(not isinstance(repair.get(key), int) or isinstance(repair.get(key), bool) or repair[key] < 0 for key in ("used", "maximum")):
        raise ValueError("EP terminal assurance repair rounds are invalid")
    findings = _object(assurance.get("findings"), "assurance findings")
    if any(not isinstance(findings.get(key), int) or isinstance(findings.get(key), bool) or findings[key] < 0 for key in ("open_blocking", "open_non_blocking")):
        raise ValueError("EP terminal assurance finding counts are invalid")
    findings_artifact = findings.get("artifact")
    if findings_artifact is not None:
        findings_artifact = _object(findings_artifact, "assurance findings artifact")
        _string(findings_artifact.get("id"), "assurance findings artifact id")
        if findings_artifact.get("digest_algorithm") != "sha256":
            raise ValueError("EP terminal assurance findings digest algorithm is invalid")
        digest = _string(findings_artifact.get("digest"), "assurance findings artifact digest")
        if len(digest) != 64:
            raise ValueError("EP terminal assurance findings digest is invalid")
        try:
            int(digest, 16)
        except ValueError as error:
            raise ValueError("EP terminal assurance findings digest is invalid") from error
    profile = assurance.get("profile")
    no_assurance_recorded = (
        assurance.get("status") == "NOT_RECORDED"
        and profile is None
        and assurance.get("quality_review") == "NOT_RECORDED"
        and assurance.get("security_review") == "NOT_RECORDED"
        and repair == {"used": 0, "maximum": 3}
        and findings == {"open_blocking": 0, "open_non_blocking": 0, "artifact": None}
    )
    if not no_assurance_recorded:
        if assurance.get("status") not in {"PASS", "FAIL", "UNRESOLVED"}:
            raise ValueError("EP_TERMINAL_ASSURANCE_NOT_RECORDED_INVALID")
        profile = _object(profile, "assurance profile")
        _string(profile.get("version"), "assurance profile version")
        _sha256(profile.get("digest"), "assurance profile digest")
        if not isinstance(profile.get("candidate_sha"), str) or len(profile["candidate_sha"]) != 40:
            raise ValueError("EP terminal assurance candidate identity is invalid")
        if assurance.get("quality_review") not in {"PASS", "FAIL", "UNRESOLVED"} or assurance.get("security_review") not in {"PASS", "FAIL", "UNRESOLVED"}:
            raise ValueError("EP terminal assurance review result is invalid")

    prompt = _object(provenance.get("runtime_prompt"), "runtime prompt")
    report_id = _string(artifact_report.get("id"), "artifact report id")
    repository_evidence = ExecutionRepositoryEvidence(
        _string(correlation.get("mission_id"), "mission id"), _string(provenance.get("intent_id"), "intent id"),
        _string(provenance.get("intent_revision"), "intent revision"), _string(correlation.get("engineering_action_id"), "action id"),
        _string(prompt.get("id"), "runtime prompt id"), _string(correlation.get("correlation_id"), "correlation id"),
        _string(run.get("id"), "run id"), _string(repository.get("id"), "repository id"), revision,
        report_id, artifact_digest,
    )
    references = _object(document.get("references"), "artifact references")
    validation = references.get("validation", ())
    if not isinstance(validation, list):
        raise ValueError("EP terminal validation references are invalid")
    validation_references = tuple(
        item["command"] for item in validation
        if isinstance(item, Mapping) and isinstance(item.get("command"), str) and item["command"]
    )
    return ExecutionHostEvidence(host_id, repository_evidence.correlation_id, repository_evidence.host_run_id,
                                 report_id, ExecutionEvidenceOutcome(outcome.lower()), repository_evidence,
                                 validation_references=validation_references, receipt_id=receipt_id,
                                 retry_of_correlation_id=retry_of_correlation_id,
                                 resolved_from_host_run_id=resolved_from_host_run_id,
                                 execution_started_at=execution_started_at,
                                 execution_completed_at=execution_completed_at,
                                 execution_duration_ms=execution_duration_ms)
