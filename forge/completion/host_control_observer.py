"""Interpret EP-owned validation records without executing a command."""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any, Mapping

from forge.models.criterion_observation import CriterionObservation, canonical_digest
from forge.models.mission_completion import mission_criterion_id


_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _valid_digest(value: object) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def approved_observation_selector(requirement) -> str | None:
    """Identify an EP unittest observation from its exact approved binding."""
    try:
        command = json.loads(requirement.command)
    except (TypeError, ValueError):
        return None
    if (not isinstance(command, list) or len(command) != 4
            or command[:3] != ["{python}", "-m", "unittest"]
            or not isinstance(command[3], str)):
        return None
    selector = command[3]
    if (len(selector) > 100 or re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+", selector) is None):
        return None
    validation_id = "unittest_selector_" + sha256(selector.encode("utf-8")).hexdigest()[:16]
    if (requirement.validation_id != validation_id
            or requirement.control_identity != "python3 -m unittest " + selector
            or requirement.control_category != "repository"
            or requirement.validation_profile_version != "1.0"
            or requirement.profile_reference != "validation-profile-registry:FULL@1.0"):
        return None
    return selector


def _control_matches(requirement, context: Mapping[str, Any], run_id: str,
                     validated_revision: str | None) -> tuple[bool, str, dict[str, object] | None]:
    if not requirement.control_definition_digest:
        return False, "APPROVED_CONTROL_DEFINITION_MISSING", None
    version = context.get("contract_version")
    if version not in {"1.0", "1.1"} or context.get("status") != "AVAILABLE":
        return False, "HOST_CONTROL_EVIDENCE_UNAVAILABLE", None
    currentness = context.get("currentness")
    if (validated_revision is None or context.get("candidate_sha") != validated_revision
            or context.get("profile_currentness_conflict") is not False
            or not isinstance(currentness, int) or isinstance(currentness, bool) or currentness < 0
            or not _valid_digest(context.get("profile_digest"))):
        return False, "HOST_CONTROL_CANDIDATE_OR_PROFILE_MISMATCH", None
    if (context.get("validation_profile_version") != requirement.validation_profile_version
            or context.get("profile_reference") != requirement.profile_reference):
        return False, "HOST_CONTROL_PROFILE_VERSION_MISMATCH", None
    controls = context.get("controls")
    required = context.get("required_validation_controls")
    if not isinstance(controls, Mapping) or not isinstance(required, list):
        return False, "HOST_CONTROL_BINDINGS_INVALID", None
    observation_controls = context.get("observation_validation_controls", []) if version == "1.1" else []
    if not isinstance(observation_controls, list):
        return False, "HOST_CONTROL_BINDINGS_INVALID", None
    required_binding = required.count(requirement.validation_id) == 1
    observation_matches = [item for item in observation_controls
                           if isinstance(item, Mapping)
                           and item.get("validation_id") == requirement.validation_id]
    observation_binding = (version == "1.1" and len(observation_matches) == 1
                           and approved_observation_selector(requirement) is not None)
    if required_binding == observation_binding:
        return False, "HOST_CONTROL_BINDING_MISSING_OR_DUPLICATE", None
    command_identity = json.loads(requirement.command)
    definition = {"validation_profile_version": context["validation_profile_version"],
                  "profile_reference": context["profile_reference"],
                  "validation_id": requirement.validation_id,
                  "category": requirement.control_category,
                  "control_identity": requirement.control_identity,
                  "command_identity": command_identity}
    digest = "sha256:" + sha256(_canonical(definition).encode("utf-8")).hexdigest()
    if digest != requirement.control_definition_digest:
        return False, "HOST_CONTROL_DEFINITION_MISMATCH", None
    control = (controls.get(requirement.validation_id) if required_binding
               else observation_matches[0])
    if not isinstance(control, Mapping):
        return False, "HOST_CONTROL_RECORD_MISSING", None
    if (control.get("validation_id") != requirement.validation_id
            or control.get("category") != requirement.control_category
            or control.get("control_identity") != requirement.control_identity
            or control.get("control_definition_digest") != digest
            or control.get("required_for_profile") is not required_binding
            or control.get("currentness") != currentness):
        return False, "HOST_CONTROL_RECORD_CONFLICT", None
    if (control.get("execution_status") != "EXECUTED" or control.get("result") != "PASS"
            or control.get("evidence_authority") != "command_terminal"
            or control.get("evidence_ref") != "command_terminal"
            or control.get("exit_code") != 0
            or not isinstance(control.get("command_id"), str) or not control["command_id"]):
        return False, "HOST_CONTROL_NOT_EXECUTED_AND_PASSED", None
    detail = control.get("result_detail")
    if not isinstance(detail, Mapping):
        return False, "HOST_CONTROL_RESULT_DETAIL_MISSING", None
    if (detail.get("status") != "AVAILABLE" or detail.get("capture_status") != "AVAILABLE"
            or detail.get("schema") != "deterministic-validation-result-detail-v1"
            or detail.get("run_id") != run_id
            or detail.get("command_id") != control["command_id"]
            or detail.get("validation_id") != requirement.validation_id
            or detail.get("exit_code") != 0
            or not isinstance(detail.get("artifact_id"), str) or not detail["artifact_id"]
            or not _valid_digest(detail.get("digest")) or not _valid_digest(detail.get("output_digest"))):
        return False, "HOST_CONTROL_RESULT_DETAIL_INVALID", None
    count = detail.get("test_count")
    if requirement.minimum_test_count and (not isinstance(count, int) or isinstance(count, bool)
                                          or count < requirement.minimum_test_count
                                          or detail.get("test_count_source") != "unittest_terminal_summary"):
        return False, "HOST_CONTROL_TEST_COUNT_INSUFFICIENT", None
    return True, "APPROVED_HOST_CONTROL_EXECUTED_AND_PASSED", {
        "validation_id": requirement.validation_id, "control_identity": requirement.control_identity,
        "control_definition_digest": digest, "validation_profile_version": requirement.validation_profile_version,
        "profile_reference": requirement.profile_reference, "category": requirement.control_category,
        "candidate_sha": validated_revision, "run_id": run_id, "command_id": control["command_id"],
        "result_detail_digest": detail["digest"], "output_digest": detail["output_digest"],
        "test_count": count, "execution_status": "EXECUTED", "result": "PASS", "exit_code": 0,
    }


class HostControlCriterionObserver:
    def observe(self, mission, reference, evidence) -> tuple[CriterionObservation, ...]:
        context = evidence.validation_controls
        observations = []
        for contract in mission.criterion_assessment_contracts:
            for requirement in contract.requirements:
                if requirement.kind != "host_control":
                    continue
                control_context = context if isinstance(context, Mapping) else {}
                delivered = reference.repository_revision
                candidate = reference.candidate_revision
                if (contract.validity_policy == "current_revision" and candidate != delivered
                        and control_context.get("candidate_sha") == candidate):
                    valid, reason, measured = False, "HOST_CONTROL_DELIVERY_REVISION_NOT_VALIDATED", None
                else:
                    expected_revision = (delivered if contract.validity_policy == "current_revision" else
                                         delivered if control_context.get("candidate_sha") == delivered else candidate)
                    valid, reason, measured = _control_matches(
                        requirement, control_context, evidence.host_run_id, expected_revision)
                observations.append(CriterionObservation(
                    mission.id, canonical_digest(mission.to_dict()), mission_criterion_id(mission.id, contract.criterion),
                    contract.digest, requirement.requirement_id, reference.receipt_id, reference.action_id,
                    reference.report_id, reference.repository_revision, reference.repository_evidence_digest,
                    "host_control", requirement.control_identity, "ep-terminal-artifact",
                    reference.repository_evidence_digest if valid else None,
                    _canonical(measured) if valid else None, "PASS" if valid else "UNAVAILABLE", reason,
                    requirement_digest=requirement.digest, candidate_revision=reference.candidate_revision,
                    schema_version="1.1",
                ))
        return tuple(observations)
