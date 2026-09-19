"""Deterministic Architecture Mission completion evaluation."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from forge.models.architecture_mission import ArchitectureMission
from forge.models.mission_completion import (
    CanonicalExecutionEvidenceReference,
    MissionCompletionEvaluation,
    MissionCompletionEvidence,
    MissionCriterionEvaluation,
    MissionCriterionEvaluationStatus,
    RepositoryTruthReference,
    mission_criterion_id,
)


class MissionCompletionEvaluationError(ValueError):
    """Completion input is stale, malformed, or outside the approved Mission."""


def _digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _truth_reference(document: Mapping[str, Any]) -> RepositoryTruthReference:
    try:
        values = tuple(document[item] for item in ("source_id", "revision", "locator", "content_digest"))
        if any(not isinstance(item, str) or not item for item in values):
            raise TypeError
        return RepositoryTruthReference(*values)
    except (KeyError, TypeError, ValueError) as error:
        raise MissionCompletionEvaluationError("current Repository Truth provenance is incomplete") from error


def _canonical_execution_references(
    mission_id: str, evidence: Sequence[Mapping[str, Any]],
) -> dict[str, CanonicalExecutionEvidenceReference]:
    references: dict[str, CanonicalExecutionEvidenceReference] = {}
    for document in evidence:
        if document.get("outcome") != "complete":
            continue
        repository = document.get("repository_evidence")
        if not isinstance(repository, Mapping) or repository.get("mission_id") != mission_id:
            continue
        try:
            values = (
                document["receipt_id"], repository["action_id"], document["report_id"],
                repository["repository_revision"], repository["content_digest"],
            )
            if any(not isinstance(item, str) or not item for item in values):
                raise TypeError
            reference = CanonicalExecutionEvidenceReference(*values, candidate_revision=repository.get('candidate_revision'))
        except (KeyError, TypeError, ValueError):
            continue
        if any(document.get(key) != repository.get(key) for key in ("correlation_id", "host_run_id", "report_id")):
            continue
        previous = references.get(reference.receipt_id)
        if previous is not None and previous != reference:
            raise MissionCompletionEvaluationError("execution receipt identity binds conflicting terminal evidence")
        references[reference.receipt_id] = reference
    return references


def _host_control_observation_matches(observation, requirement, validity_policy: str) -> bool:
    if (observation.schema_version != "1.1" or observation.result != "PASS"
            or observation.reason != "APPROVED_HOST_CONTROL_EXECUTED_AND_PASSED"
            or observation.content_digest != observation.repository_evidence_digest
            or observation.observed_json is None):
        return False
    try:
        record = json.loads(observation.observed_json)
    except (TypeError, ValueError):
        return False
    return (isinstance(record, dict)
            and record.get("validation_id") == requirement.validation_id
            and record.get("control_identity") == requirement.control_identity
            and record.get("control_definition_digest") == requirement.control_definition_digest
            and record.get("validation_profile_version") == requirement.validation_profile_version
            and record.get("profile_reference") == requirement.profile_reference
            and record.get("category") == requirement.control_category
            and (record.get("candidate_sha") == observation.repository_revision
                 if validity_policy == "current_revision" else
                 record.get("candidate_sha") in {observation.candidate_revision, observation.repository_revision})
            and record.get("execution_status") == "EXECUTED"
            and record.get("result") == "PASS" and record.get("exit_code") == 0
            and (requirement.minimum_test_count == 0 or
                 isinstance(record.get("test_count"), int)
                 and not isinstance(record["test_count"], bool)
                 and record["test_count"] >= requirement.minimum_test_count))


class MissionCompletionEvaluator:
    """Interpret approved predicates over Forge-observed facts; never provider PASS."""

    def evaluate(self, mission, repository_truth, execution_evidence, evidence):
        if not mission.acceptance_criteria:
            raise MissionCompletionEvaluationError("approved Mission has no acceptance criteria")
        mission_digest = _digest(mission.to_dict())
        truth = _truth_reference(repository_truth)
        identifiers = {mission_criterion_id(mission.id, criterion): criterion for criterion in mission.acceptance_criteria}
        canonical = _canonical_execution_references(mission.id, execution_evidence)
        contracts = {mission_criterion_id(mission.id, item.criterion): item
                     for item in mission.criterion_assessment_contracts}
        bindings = {} if evidence is None else {item.criterion_id: item for item in evidence.bindings}
        if evidence is not None:
            if evidence.mission_id != mission.id or evidence.mission_digest != mission_digest:
                raise MissionCompletionEvaluationError("completion evidence does not bind the approved Mission")
            if set(bindings) - set(identifiers):
                raise MissionCompletionEvaluationError("completion evidence references an unknown Mission criterion")
        evaluations = []
        for criterion_id, criterion in identifiers.items():
            contract, binding = contracts.get(criterion_id), bindings.get(criterion_id)
            reason = None
            if contract is None:
                reason = "APPROVED_ASSESSMENT_CONTRACT_MISSING"
            elif evidence is not None and evidence.schema_version != "2.0":
                reason = "LEGACY_ASSOCIATIONS_ARE_NOT_SUBSTANTIVE_EVIDENCE"
            elif binding is None:
                reason = "MISSING_AUTHORITATIVE_OBSERVATION"
            elif binding.contract_digest != contract.digest:
                reason = "ASSESSMENT_CONTRACT_MISMATCH"
            elif binding.repository_truth != truth:
                reason = "STALE_REPOSITORY_TRUTH"
            elif any(canonical.get(ref.receipt_id) != ref for ref in binding.execution_evidence):
                reason = "NON_CANONICAL_EXECUTION_EVIDENCE"
            references = () if binding is None else binding.execution_evidence
            observations = () if binding is None else binding.observations
            requirement_results = []
            if reason is None:
                reference_map = {ref.receipt_id: ref for ref in references}
                seen = {}
                for observation in observations:
                    reference = reference_map.get(observation.receipt_id)
                    if (reference is None or observation.mission_id != mission.id
                            or observation.mission_digest != mission_digest
                            or observation.criterion_id != criterion_id
                            or observation.contract_digest != contract.digest
                            or observation.action_id != reference.action_id
                            or observation.report_id != reference.report_id
                            or observation.repository_revision != reference.repository_revision
                            or observation.candidate_revision != reference.candidate_revision
                            or observation.repository_evidence_digest != reference.repository_evidence_digest):
                        reason = "OBSERVATION_PROVENANCE_MISMATCH"
                        break
                    identity = (observation.receipt_id, observation.requirement_id)
                    if identity in seen and seen[identity] != observation:
                        raise MissionCompletionEvaluationError("conflicting immutable criterion observations")
                    seen[identity] = observation
                    if observation.requirement_id not in {req.requirement_id for req in contract.requirements}:
                        raise MissionCompletionEvaluationError("observation references unknown criterion requirement")
            if reason is None:
                for requirement in contract.requirements:
                    candidates = [obs for obs in observations if obs.requirement_id == requirement.requirement_id]
                    if contract.validity_policy == "current_revision":
                        candidates = [obs for obs in candidates if obs.repository_revision == truth.revision]
                    source = mission.repository_evidence_source
                    if requirement.kind == "host_control":
                        if not requirement.control_definition_digest:
                            result, why, matched = "UNSATISFIED", "UNSUPPORTED_AUTHORITATIVE_EVIDENCE_SOURCE", ()
                        elif any(obs.source_kind != "host_control" or obs.source_identity != requirement.control_identity
                                 or obs.artifact_path != "ep-terminal-artifact"
                                 or obs.requirement_digest != requirement.digest or obs.json_pointer != ""
                                 for obs in candidates):
                            result, why, matched = "UNSATISFIED", "OBSERVATION_SOURCE_MISMATCH", ()
                        elif not candidates:
                            result, why, matched = "UNSATISFIED", "CURRENT_OBSERVATION_MISSING", ()
                        else:
                            if contract.validity_policy == "historical_delivery":
                                passing = [obs for index, obs in enumerate(candidates)
                                           if _host_control_observation_matches(obs, requirement, contract.validity_policy)
                                           and not any(later.repository_revision == obs.repository_revision
                                                       and not _host_control_observation_matches(later, requirement, contract.validity_policy)
                                                       for later in candidates[index + 1:])]
                                selected = passing[-1] if passing else candidates[-1]
                            else:
                                selected = candidates[-1]
                            proven = _host_control_observation_matches(selected, requirement, contract.validity_policy)
                            result = "PROVEN" if proven else "UNSATISFIED"
                            why = "APPROVED_HOST_CONTROL_EXECUTED_AND_PASSED" if proven else selected.reason
                            matched = (selected.id,)
                    elif requirement.kind != "repository_json":
                        result, why, matched = "UNSATISFIED", "UNSUPPORTED_AUTHORITATIVE_EVIDENCE_SOURCE", ()
                    elif source is None:
                        result, why, matched = "UNSATISFIED", "APPROVED_REPOSITORY_SOURCE_MISSING", ()
                    elif any(obs.source_kind != requirement.kind or obs.source_identity != source.github_repository
                             or obs.artifact_path != requirement.artifact_path
                             or obs.requirement_digest != requirement.digest
                             or obs.json_pointer != requirement.json_pointer for obs in candidates):
                        result, why, matched = "UNSATISFIED", "OBSERVATION_SOURCE_MISMATCH", ()
                    elif not candidates:
                        result, why, matched = "UNSATISFIED", "CURRENT_OBSERVATION_MISSING", ()
                    elif any(len({(obs.content_digest, obs.observed_json, obs.result)
                                  for obs in candidates if obs.repository_revision == revision
                                  and obs.result != 'UNAVAILABLE'}) > 1
                             for revision in {obs.repository_revision for obs in candidates}):
                        result, why, matched = "UNSATISFIED", "CONFLICTING_IMMUTABLE_ARTIFACT_OBSERVATIONS", ()
                    else:
                        # A historical-delivery assertion describes an accomplished event.
                        # A new current-property failure is not a rewrite of that old event.
                        passing = [obs for obs in candidates if obs.result == "PASS"
                                   and obs.observed_json == requirement.expected_json
                                   and obs.content_digest is not None]
                        selected = passing[-1] if passing and contract.validity_policy == "historical_delivery" else candidates[-1]
                        proven = (selected.result == "PASS" and selected.observed_json == requirement.expected_json
                                  and selected.content_digest is not None)
                        result = "PROVEN" if proven else "UNSATISFIED"
                        why = "APPROVED_JSON_ASSERTION_MATCHED" if proven else selected.reason
                        matched = (selected.id,)
                    requirement_results.append({"requirement_id": requirement.requirement_id,
                        "requirement_digest": requirement.digest, "status": result, "reason": why,
                        "observation_ids": list(matched)})
                reason = ("ALL_APPROVED_REQUIREMENTS_PROVEN" if all(item["status"] == "PROVEN" for item in requirement_results)
                          else "REQUIRED_OBSERVATIONS_UNPROVEN")
            status = (MissionCriterionEvaluationStatus.PROVEN if reason == "ALL_APPROVED_REQUIREMENTS_PROVEN"
                      else MissionCriterionEvaluationStatus.UNSATISFIED)
            evaluations.append(MissionCriterionEvaluation(
                criterion_id, criterion, status, reason, references, truth,
                None if contract is None else contract.digest, tuple(requirement_results), observations,
            ))
        return MissionCompletionEvaluation(
            mission.id, mission_digest, tuple(evaluations), None if evidence is None else evidence.digest,
            evidence=evidence,
        )
