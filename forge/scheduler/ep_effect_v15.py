"""Strict consumer of EP's source-bound effect result v1.1 and terminal v1.6.

EP owns execution and the immutable report. Forge checks the independently
read back bytes before interpreting criterion and source evidence.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from forge.models.execution_host import (
    ExecutionEvidenceOutcome, ExecutionHostEvidence, ExecutionRepositoryEvidence,
    ExecutionRequest,
)
from forge.scheduler.ep_v12 import _host_execution


_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT = re.compile(r"[0-9a-f]{40}\Z")
_TERMINAL_KEYS = frozenset({
    "artifact_type", "contract_version", "submission", "producer", "correlation", "provenance",
    "run", "host_execution", "validation_controls", "repository", "delivery", "report",
    "references", "assurance", "effect_result",
})
_RESULT_KEYS = frozenset({
    "contract_version", "outcome", "terminal", "effect_qualified", "subject", "artifact",
    "validation_controls", "validation_profile", "assurance_reviews", "repair_rounds", "delivery",
})
_SUBJECT_KEYS = frozenset({
    "subject_kind", "subject_id", "subject_digest", "source_revision", "source_snapshot_digest",
    "effect_contract_digest", "criteria_digest", "binding_digest", "repair_ordinal", "candidate_revision",
})
_REVIEW_KEYS = frozenset({
    "reviewer", "status", "subject", "profile_digest", "invocation_id", "contract_version",
    "started_at", "completed_at", "findings", "coverage", "finding_dispositions",
})
_BINDING_KEYS = frozenset({
    "run_id", "submission_id", "project_id", "repository_id", "producer_id", "producer_type",
    "repository", "producer_version", "correlation_id", "mission_id", "engineering_action_id",
    "source_revision", "accepted_request_digest",
})
_REPORT_KEYS = frozenset({
    "contract_version", "artifact_type", "binding", "contract", "contract_digest",
    "source_manifest", "source_manifest_digest", "invocation_id", "repair_ordinal", "result",
})
_BASE_CONTROLS = frozenset({
    "effect_source_binding", "effect_output_integrity", "effect_scope_containment",
    "report_criteria_contract",
})
_DOCUMENT_SUFFIXES = frozenset({".md", ".txt", ".rst", ".adoc", ".mmd", ".puml"})
_ORDERED_BASE_CONTROLS = (
    "effect_source_binding", "effect_output_integrity", "effect_scope_containment",
    "report_criteria_contract",
)
_REVIEW_SURFACES = {
    "quality": frozenset({"approved_criteria", "source_evidence", "meaningful_result",
                          "output_scope", "document_design_content", "validation_controls",
                          "restart_identity"}),
    "security": frozenset({"approved_criteria", "source_evidence", "authority_scope",
                           "sensitive_data", "containment", "artifact_integrity",
                           "restart_identity"}),
}


def _object(value: object, keys: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"EP_EFFECT_{label}_SCHEMA_INVALID")
    return value


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ValueError(f"EP_EFFECT_{label}_DIGEST_INVALID")
    return value


def _revision(value: object, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _GIT.fullmatch(value) is None:
        raise ValueError(f"EP_EFFECT_{label}_REVISION_INVALID")
    return value


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _in_scope(scopes: tuple[str, ...], path: str) -> bool:
    return any(path == scope or scope.endswith("/") and path.startswith(scope) for scope in scopes)


def _source_path(path: object) -> bool:
    return (isinstance(path, str) and 0 < len(path) <= 240
            and re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", path) is not None
            and all(part not in {".", ".."}
                    and part.lower() not in {".git", ".codex", ".agents", ".engineering",
                                             ".ssh", ".aws", ".gitconfig", ".gitattributes",
                                             ".gitmodules", "agents.md"}
                    and not part.lower().startswith(".env")
                    for part in path.split("/")))


def terminal_evidence(
    request: ExecutionRequest, readback: Mapping[str, Any], artifact: bytes,
    result: Mapping[str, Any], *, host_id: str, expected_accepted_digest: str,
) -> ExecutionHostEvidence:
    """Verify both public readbacks, including every approved criterion binding."""
    effect = request.producer_contract.effect_request
    if effect is None or request.repository_revision_binding is None:
        raise ValueError("EP_EFFECT_REQUEST_BINDING_REQUIRED")
    evidence = readback.get("evidence")
    terminal_ref = evidence.get("terminal_artifact") if isinstance(evidence, Mapping) else None
    if (not isinstance(terminal_ref, Mapping)
            or terminal_ref.get("digest") != _digest_bytes(artifact)
            or terminal_ref.get("digest_algorithm") != "sha256"
            or terminal_ref.get("content_type") != "application/json"):
        raise ValueError("EP_EFFECT_TERMINAL_DIGEST_MISMATCH")
    try:
        terminal = json.loads(artifact)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("EP_EFFECT_TERMINAL_INVALID") from error
    terminal = _object(terminal, _TERMINAL_KEYS, "TERMINAL")
    if terminal["artifact_type"] != "EP_TERMINAL_EVIDENCE" or terminal["contract_version"] != "1.6":
        raise ValueError("EP_EFFECT_TERMINAL_V16_REQUIRED")
    _host_execution(terminal)
    result = _object(result, _RESULT_KEYS, "RESULT")
    if terminal["effect_result"] != {key: value for key, value in result.items() if key != "artifact"}:
        raise ValueError("EP_EFFECT_TERMINAL_RESULT_MISMATCH")
    if (result["contract_version"] != "1.1" or result["outcome"] != "COMPLETE"
            or result["terminal"] is not True or result["effect_qualified"] is not True):
        raise ValueError("EP_EFFECT_RESULT_NOT_QUALIFIED")

    submission = _object(terminal["submission"], frozenset({
        "id", "project_id", "repository_id", "accepted_request_digest",
    }), "SUBMISSION")
    read_submission = readback.get("submission")
    if (not isinstance(read_submission, Mapping)
            or any(submission[key] != read_submission.get(key) for key in submission)
            or submission["repository_id"] != request.repository_id
            or submission["accepted_request_digest"] != expected_accepted_digest):
        raise ValueError("EP_EFFECT_ACCEPTED_REQUEST_MISMATCH")
    producer = terminal["producer"]
    identity = request.producer_contract.producer.identity.to_dict()
    if producer != readback.get("producer") or producer != identity:
        raise ValueError("EP_EFFECT_PRODUCER_MISMATCH")
    correlation = terminal["correlation"]
    if (correlation != readback.get("correlation")
            or not isinstance(correlation, Mapping)
            or (correlation.get("correlation_id"), correlation.get("mission_id"),
                correlation.get("engineering_action_id")) !=
               (request.correlation_id, request.mission_id, request.action_id)):
        raise ValueError("EP_EFFECT_CORRELATION_MISMATCH")
    provenance = terminal["provenance"]
    read_provenance = readback.get("provenance")
    if (not isinstance(read_provenance, Mapping)
            or provenance != read_provenance.get("forge_execution")
            or not isinstance(provenance, Mapping)
            or provenance.get("runtime_prompt", {}).get("id") != request.producer_contract.runtime_prompt.id):
        raise ValueError("EP_EFFECT_PROVENANCE_MISMATCH")
    run = terminal["run"]
    read_run, read_result = readback.get("run"), readback.get("result")
    if (not isinstance(run, Mapping) or not isinstance(read_run, Mapping)
            or not isinstance(read_result, Mapping)
            or run.get("id") != read_run.get("id")
            or run.get("outcome") != read_result.get("outcome")
            or run.get("outcome") != "COMPLETE"
            or read_run.get("state") != "COMPLETE"
            or read_run.get("terminal") is not True
            or read_result.get("terminal") is not True
            or run.get("effect_qualified") is not True
            or not isinstance(run.get("execution_duration_ms"), int)
            or isinstance(run["execution_duration_ms"], bool)
            or run["execution_duration_ms"] <= 0
            or any(not isinstance(run.get(key), str) or not run[key]
                   or run[key] != read_run.get(key)
                   for key in ("execution_started_at", "execution_completed_at"))
            or run["execution_duration_ms"] != read_run.get("execution_duration_ms")):
        raise ValueError("EP_EFFECT_RUN_MISMATCH")
    if terminal_ref.get("id") != f"terminal-evidence:{run['id']}":
        raise ValueError("EP_EFFECT_TERMINAL_ID_MISMATCH")
    repository = terminal["repository"]
    delivery = _object(result["delivery"], frozenset({"kind", "revision", "pull_request"}), "DELIVERY")
    if (not isinstance(repository, Mapping)
            or repository.get("id") != request.repository_id
            or repository.get("requested_revision") != effect.source_revision
            or effect.source_revision != request.repository_revision_binding.requested_revision
            or repository.get("execution_baseline") != effect.source_revision
            or repository.get("baseline_transition") != {
                "status": "EXACT", "from": effect.source_revision,
                "to": effect.source_revision, "allowed_to": None,
            }
            or delivery["kind"] != effect.policy.delivery):
        raise ValueError("EP_EFFECT_SOURCE_MISMATCH")
    final_revision = _revision(delivery["revision"], "DELIVERY", nullable=True)
    if (delivery["pull_request"] is not None
            and (type(delivery["pull_request"]) is not int or delivery["pull_request"] < 1)):
        raise ValueError("EP_EFFECT_DELIVERY_SCHEMA_INVALID")
    read_repository = evidence.get("repository") if isinstance(evidence, Mapping) else None
    if (not isinstance(read_repository, Mapping)
            or (read_repository.get("id"), read_repository.get("revision")) !=
               (repository["id"], final_revision)
            or read_result.get("delivery_qualified") is not (final_revision is not None)):
        raise ValueError("EP_EFFECT_READBACK_DELIVERY_MISMATCH")
    if effect.policy.delivery == "EVIDENCE_ONLY":
        if (final_revision is not None or delivery["pull_request"] is not None
                or run.get("delivery_qualified") is not False
                or repository.get("revision") is not None
                or repository.get("revision_required") is not False
                or terminal["delivery"] != {"status": "NOT_DELIVERED", "revision": None}):
            raise ValueError("EP_EFFECT_REPORT_CLAIMS_REPOSITORY_DELIVERY")
    elif (final_revision is None or run.get("delivery_qualified") is not True
          or repository.get("revision") != final_revision
          or repository.get("revision_required") is not True
          or terminal["delivery"] != {"status": "DELIVERED", "revision": final_revision}):
        raise ValueError("EP_EFFECT_GIT_DELIVERY_UNQUALIFIED")

    artifact_ref = _object(result["artifact"], frozenset({
        "id", "digest_algorithm", "digest", "content_type", "content",
    }), "ARTIFACT")
    report = _object(terminal["report"], frozenset({
        "id", "digest_algorithm", "digest", "content_type", "readback_path",
    }), "REPORT")
    expected_path = f"/v1/projects/{submission['project_id']}/submissions/{submission['id']}/effect-result"
    report_digest = _sha(artifact_ref["digest"], "REPORT")
    if (report != {key: artifact_ref[key] for key in (
            "id", "digest_algorithm", "digest", "content_type")}
            | {"readback_path": expected_path}
            or artifact_ref["digest_algorithm"] != "sha256"
            or artifact_ref["content_type"] != "application/json"
            or not isinstance(artifact_ref["id"], str) or not artifact_ref["id"]
            or report_digest != _digest(artifact_ref["content"])):
        raise ValueError("EP_EFFECT_REPORT_BYTES_MISMATCH")
    envelope = _object(artifact_ref["content"], _REPORT_KEYS, "REPORT_ENVELOPE")
    if (envelope["contract_version"] != "1.0" or envelope["artifact_type"] != "EP_EFFECT_RESULT"
            or envelope["contract"] != effect.to_dict()
            or envelope["contract_digest"] != _digest(effect.to_dict())[7:]):
        raise ValueError("EP_EFFECT_APPROVED_CONTRACT_MISMATCH")
    binding = _object(envelope["binding"], _BINDING_KEYS, "BINDING")
    expected_binding = {
        "run_id": run["id"], "submission_id": submission["id"],
        "project_id": submission["project_id"], "repository_id": request.repository_id,
        "producer_id": identity["id"], "producer_type": identity["type"],
        "producer_version": identity["version"], "repository": request.origin_identity,
        "correlation_id": request.correlation_id, "mission_id": request.mission_id,
        "engineering_action_id": request.action_id, "source_revision": effect.source_revision,
        "accepted_request_digest": submission["accepted_request_digest"],
    }
    if binding != expected_binding:
        raise ValueError("EP_EFFECT_REPORT_BINDING_MISMATCH")
    manifest = envelope["source_manifest"]
    if (not isinstance(manifest, Mapping) or not manifest
            or any(not _source_path(path) or not _in_scope(effect.policy.read_paths, path)
                   or not isinstance(digest, str)
                   or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                   for path, digest in manifest.items())
            or envelope["source_manifest_digest"] != _digest(manifest)[7:]):
        raise ValueError("EP_EFFECT_SOURCE_MANIFEST_INVALID")
    subject = _object(result["subject"], _SUBJECT_KEYS, "SUBJECT")
    if (type(subject["repair_ordinal"]) is not int or not 0 <= subject["repair_ordinal"] <= 3
            or subject.get("subject_kind") != "REPORT_ARTIFACT"
            or subject.get("subject_id") != artifact_ref["id"]
            or subject.get("subject_digest") != report_digest
            or subject.get("source_revision") != effect.source_revision
            or subject.get("source_snapshot_digest") != _digest(manifest)
            or subject.get("effect_contract_digest") != _digest(effect.to_dict())
            or subject.get("criteria_digest") != _digest(effect.to_dict()["criteria"])
            or subject.get("binding_digest") != _digest(binding)
            or subject.get("repair_ordinal") != envelope["repair_ordinal"]
            or subject.get("candidate_revision") != repository.get("candidate")):
        raise ValueError("EP_EFFECT_SUBJECT_MISMATCH")
    if (effect.policy.delivery == "EVIDENCE_ONLY" and subject["candidate_revision"] is not None
            or effect.policy.delivery == "GIT"
            and _revision(subject["candidate_revision"], "CANDIDATE") is None):
        raise ValueError("EP_EFFECT_CANDIDATE_MISMATCH")
    rows = envelope.get("result")
    if (not isinstance(rows, Mapping) or set(rows) != {"summary", "criteria", "files"}
            or not isinstance(rows["summary"], str) or len(rows["summary"].strip()) < 40
            or not isinstance(rows["criteria"], list) or not isinstance(rows["files"], list)):
        raise ValueError("EP_EFFECT_CRITERION_REPORT_INVALID")
    expected_ids = {key for key, _ in effect.criteria}
    if {item.get("id") for item in rows["criteria"] if isinstance(item, Mapping)} != expected_ids:
        raise ValueError("EP_EFFECT_CRITERION_SET_MISMATCH")
    criteria = []
    for item in rows["criteria"]:
        if (not isinstance(item, Mapping) or set(item) != {"id", "status", "analysis", "source_paths"}
                or item["status"] != "SATISFIED"
                or not isinstance(item["analysis"], str) or len(item["analysis"].strip()) < 40
                or not isinstance(item["source_paths"], list) or not item["source_paths"]
                or any(path not in manifest for path in item["source_paths"])):
            raise ValueError("EP_EFFECT_CRITERION_EVIDENCE_INVALID")
        criteria.append({"id": item["id"], "analysis_digest": _digest(item["analysis"]),
                         "source_paths": sorted(item["source_paths"])})
    if len(criteria) != len(expected_ids):
        raise ValueError("EP_EFFECT_CRITERION_DUPLICATE")
    if effect.policy.delivery == "EVIDENCE_ONLY" and rows["files"]:
        raise ValueError("EP_EFFECT_REPORT_HAS_FORBIDDEN_FILES")
    if effect.policy.delivery == "GIT":
        if not rows["files"] or len(rows["files"]) > 64:
            raise ValueError("EP_EFFECT_GIT_REPORT_EMPTY")
        output_paths: set[str] = set()
        for item in rows["files"]:
            if (not isinstance(item, Mapping) or set(item) != {"path", "content"}
                    or not _source_path(item["path"])
                    or not _in_scope(effect.policy.write_paths, item["path"])
                    or (effect.policy.mode in {"DOCUMENTATION_ONLY", "ARCHITECTURE_DESIGN_ONLY"}
                        and PurePosixPath(item["path"]).suffix.casefold() not in _DOCUMENT_SUFFIXES)
                    or item["path"].lower() in output_paths
                    or not isinstance(item["content"], str)
                    or not item["content"].strip()):
                raise ValueError("EP_EFFECT_GIT_REPORT_SCOPE_INVALID")
            output_paths.add(item["path"].lower())
    if (envelope["invocation_id"] != f"{run['id']}:effect:{envelope['repair_ordinal']}"
            or subject["repair_ordinal"] != result["repair_rounds"].get("used")):
        raise ValueError("EP_EFFECT_ATTEMPT_BINDING_MISMATCH")
    controls = result["validation_controls"]
    required = set(_BASE_CONTROLS)
    ordered_required = _ORDERED_BASE_CONTROLS
    if effect.policy.mode in {"DOCUMENTATION_ONLY", "ARCHITECTURE_DESIGN_ONLY"}:
        required.add("document_content_links_schema")
        ordered_required += ("document_content_links_schema",)
    if effect.policy.mode == "ARCHITECTURE_DESIGN_ONLY":
        required.add("design_criteria_contract")
        ordered_required += ("design_criteria_contract",)
    if effect.policy.mode == "BOUNDED_REPOSITORY_CHANGE":
        required.add("repository_json")
        ordered_required += ("repository_json",)
    if (not isinstance(controls, list) or not required <= {item.get("validation_id") for item in controls
                                                          if isinstance(item, Mapping)}
            or [item.get("validation_id") for item in controls if isinstance(item, Mapping)] !=
               list(ordered_required)
            or len({item.get("validation_id") for item in controls if isinstance(item, Mapping)}) != len(controls)
            or any(not isinstance(item, Mapping) or set(item) != {
                       "validation_id", "authority", "command_id", "started_at", "completed_at",
                       "exit_code", "profile_digest", "status"}
                   or item.get("status") != "PASS"
                   or type(item.get("exit_code")) is not int or item["exit_code"] != 0
                   or any(not isinstance(item[key], str) or not item[key] for key in (
                       "validation_id", "authority", "command_id", "started_at", "completed_at",
                       "profile_digest", "status"))
                   or _SHA.fullmatch(item["profile_digest"]) is None
                   for item in controls)):
        raise ValueError("EP_EFFECT_CONTROLS_UNQUALIFIED")
    profile_digests = {item["profile_digest"] for item in controls}
    if (len(profile_digests) != 1
            or any(item["command_id"] != f"{run['id']}:effect:{envelope['repair_ordinal']}:{index}"
                   for index, item in enumerate(controls))
            or any(item["authority"] != ("repository_json" if item["validation_id"] == "repository_json"
                                         else "host_control") for item in controls)):
        raise ValueError("EP_EFFECT_CONTROL_BINDING_MISMATCH")
    profile = _object(result["validation_profile"], frozenset({
        "version", "subject", "controls", "validation_bindings"}), "PROFILE")
    bindings = profile["validation_bindings"]
    expected_bindings = ["repository_json"] if effect.policy.mode == "BOUNDED_REPOSITORY_CHANGE" else []
    if (profile["version"] != "effect-validation@1.0" or profile["subject"] != subject
            or profile["controls"] != [[item["validation_id"], item["authority"]] for item in controls]
            or not isinstance(bindings, list)
            or [item.get("validation_id") for item in bindings if isinstance(item, Mapping)] != expected_bindings
            or any(not isinstance(item, Mapping) or set(item) != {"validation_id", "category", "command"}
                   or item["category"] != "repository_json"
                   or not isinstance(item["command"], list) or not item["command"]
                   or any(not isinstance(argument, str) or not argument for argument in item["command"])
                   for item in bindings)):
        raise ValueError("EP_EFFECT_PROFILE_INPUTS_MISMATCH")
    expected_profile = _digest(profile)
    if profile_digests != {expected_profile}:
        raise ValueError("EP_EFFECT_PROFILE_DIGEST_MISMATCH")
    terminal_controls = terminal["validation_controls"]
    if (not isinstance(terminal_controls, Mapping)
            or terminal_controls.get("contract_version") != "1.0"
            or terminal_controls.get("status") != "AVAILABLE"
            or terminal_controls.get("profile_currentness_conflict") is not False
            or terminal_controls.get("profile_reference") != "effect-validation@1.0"
            or terminal_controls.get("profile_selection_source") != "accepted_effect_contract"
            or terminal_controls.get("validation_profile_version") != "effect-validation@1.0"
            or terminal_controls.get("selected_validation_tier") != effect.policy.mode
            or terminal_controls.get("required_validation_controls") != list(ordered_required)
            or terminal_controls.get("candidate_sha") is not None
            or terminal_controls.get("profile_digest") is not None
            or terminal_controls.get("currentness") is not None
            or not isinstance(terminal_controls.get("controls"), Mapping)
            or set(terminal_controls["controls"]) != required):
        raise ValueError("EP_EFFECT_TERMINAL_CONTROLS_MISMATCH")
    for item in controls:
        observed = terminal_controls["controls"][item["validation_id"]]
        if (not isinstance(observed, Mapping)
                or observed.get("validation_id") != item["validation_id"]
                or observed.get("control_identity") != item["validation_id"]
                or observed.get("category") != item["authority"]
                or observed.get("command_id") != item["command_id"]
                or observed.get("currentness") != envelope["repair_ordinal"]
                or observed.get("required_for_profile") is not True
                or observed.get("execution_status") != "EXECUTED"
                or observed.get("result") != "PASS"
                or observed.get("exit_code") != 0):
            raise ValueError("EP_EFFECT_TERMINAL_CONTROL_FAILED")
    host_execution = terminal["host_execution"]
    host_start, host_terminal = host_execution["start"], host_execution["terminal"]
    if (host_start.get("status") != "AVAILABLE"
            or host_start.get("target_commit") != effect.source_revision
            or host_terminal.get("status") != "AVAILABLE"
            or host_terminal.get("worktree_state") != "CLEAN"
            or host_terminal.get("activity", {}).get("provider_invocations", 0) < 1
            or host_terminal.get("activity", {}).get("host_validation_actions", 0) < len(controls)):
        raise ValueError("EP_EFFECT_HOST_EXECUTION_MISMATCH")
    if (effect.policy.delivery == "EVIDENCE_ONLY"
            and (any(host_terminal["diff"].values())
                 or host_terminal["inventory_digest"] != host_start["inventory_digest"]
                 or host_terminal["tracked_file_count"] != host_start["tracked_file_count"])):
        raise ValueError("EP_EFFECT_FORBIDDEN_TARGET_MUTATION")
    reviews = result["assurance_reviews"]
    if (not isinstance(reviews, list) or len(reviews) != 2
            or [item.get("reviewer") for item in reviews if isinstance(item, Mapping)] != ["quality", "security"]
            or any(not isinstance(item, Mapping) or item.get("status") != "PASS"
                   or set(item) != _REVIEW_KEYS
                   or any(not isinstance(item[key], str) or not item[key] for key in (
                       "reviewer", "status", "profile_digest", "invocation_id", "contract_version",
                       "started_at", "completed_at"))
                   or item.get("contract_version") != "3.0" or item.get("subject") != subject
                   or item.get("profile_digest") not in profile_digests
                   or item.get("invocation_id") != f"{run['id']}:{item.get('reviewer')}:effect:{envelope['repair_ordinal']}"
                   or not isinstance(item.get("findings"), list)
                   or any(not isinstance(finding, Mapping)
                          or finding.get("blocking") is not False
                          or finding.get("severity") not in {"LOW", "MEDIUM"}
                          or finding.get("disposition") != "NON_BLOCKING"
                          for finding in item.get("findings", ()))
                   or not isinstance(item.get("finding_dispositions"), list)
                   or any(not isinstance(disposition, Mapping)
                          or set(disposition) != {"finding_id", "disposition", "evidence_ref"}
                          or not isinstance(disposition.get("finding_id"), str)
                          or not disposition["finding_id"]
                          or disposition.get("disposition") != "RESOLVED"
                          or not isinstance(disposition.get("evidence_ref"), str)
                          or not disposition["evidence_ref"]
                          for disposition in item.get("finding_dispositions", ()))
                   for item in reviews)):
        raise ValueError("EP_EFFECT_REVIEWS_UNQUALIFIED")
    for review in reviews:
        coverage = review.get("coverage")
        if (not isinstance(coverage, list)
                or len(coverage) != len(_REVIEW_SURFACES[review["reviewer"]])
                or {item.get("surface") for item in coverage if isinstance(item, Mapping)}
                   != _REVIEW_SURFACES[review["reviewer"]]
                or any(not isinstance(item, Mapping) or set(item) != {
                       "surface", "status", "evidence_ref"}
                       or item["status"] != "REVIEWED" or item["evidence_ref"] != report_digest
                       for item in coverage)):
            raise ValueError("EP_EFFECT_REVIEW_COVERAGE_INCOMPLETE")
    # EP's legacy terminal assurance projection is separate from FME reviews;
    # it can legitimately be NOT_RECORDED for qualified report-only results.
    repair = _object(result["repair_rounds"], frozenset({"used", "maximum"}), "REPAIR")
    if (not isinstance(repair["used"], int) or isinstance(repair["used"], bool)
            or not 0 <= repair["used"] <= 3 or repair["maximum"] != 3):
        raise ValueError("EP_EFFECT_REPAIR_BUDGET_INVALID")
    revision = effect.source_revision if final_revision is None else final_revision
    terminal_digest = _digest_bytes(artifact)
    repository_evidence = ExecutionRepositoryEvidence(
        request.mission_id, request.intent_id, request.intent_revision, request.action_id,
        request.producer_contract.runtime_prompt.id, request.correlation_id, run["id"],
        request.repository_id, revision, artifact_ref["id"], terminal_digest,
        candidate_revision=subject["candidate_revision"],
    )
    retained = {
        "contract_version": "1.0", "mode": effect.policy.mode, "delivery": effect.policy.delivery,
        "source_revision": effect.source_revision, "delivery_revision": final_revision,
        "report_id": artifact_ref["id"], "report_digest": report_digest,
        "source_manifest_digest": _digest(manifest), "subject_digest": subject["subject_digest"],
        "criteria": criteria,
        "controls": sorted(item["validation_id"] for item in controls),
        "reviews": ["quality", "security"],
        "validation_profile_digest": expected_profile,
        "validation_profile_version": profile["version"],
    }
    return ExecutionHostEvidence(
        host_id, request.correlation_id, run["id"], artifact_ref["id"],
        ExecutionEvidenceOutcome.COMPLETE, repository_evidence,
        retry_of_correlation_id=request.retry_of_correlation_id,
        execution_started_at=run.get("execution_started_at"),
        execution_completed_at=run.get("execution_completed_at"),
        execution_duration_ms=run["execution_duration_ms"],
        effect_result=retained,
    )


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()
