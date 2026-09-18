"""Repository byte fixtures for source-level criterion/planner tests.

These helpers use the production observer and evaluator. The byte-reader is an
explicit external boundary fixture; injected loop helpers are not installed
normal-composition qualification.
"""
from __future__ import annotations

from dataclasses import replace
import json

from forge.completion.repository_observer import RepositoryCriterionObserver, RepositoryObservationUnavailable
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from forge.models.criterion_observation import canonical_digest
from forge.models.mission_completion import (
    CanonicalExecutionEvidenceReference, MissionCompletionEvidence, MissionCriterionEvidenceBinding,
    RepositoryTruthReference, mission_criterion_id,
)
from forge.models.mission_planner import (
    MissionContinuationContext, MissionPlanningState, MissionCriterionPlanningState,
)
from forge.models.mission_completion import MissionCriterionEvaluationStatus
from forge.governance_authority import ArchitecturePlanningEvidence


def approved_contract_mission(mission):
    return replace(mission, criterion_assessment_contracts=tuple(
        CriterionAssessmentContract(criterion, (CriterionEvidenceRequirement(
            f"requirement-{index}", kind="repository_json", artifact_path="contract.json",
            json_pointer=f"/criterion-{index}", expected_json="true",
        ),)) for index, criterion in enumerate(mission.acceptance_criteria)
    ), maximum_actions=8, maximum_consecutive_no_progress_actions=3,
        repository_evidence_source=ApprovedRepositoryEvidenceSource("forge", "synthetic/forge"))


class ExactRepositoryBytes:
    def __init__(self, repository, revision, artifacts):
        self.repository, self.revision, self.artifacts = repository, revision, artifacts
        self.reads = []

    def read(self, repository, revision, path):
        self.reads.append((repository, revision, path))
        if (repository, revision) != (self.repository, self.revision):
            raise RepositoryObservationUnavailable("FIXTURE_SOURCE_OR_REVISION_MISMATCH")
        if path not in self.artifacts:
            raise RepositoryObservationUnavailable("REPOSITORY_ARTIFACT_ABSENT")
        return self.artifacts[path]


def observed_completion(mission, reference, truth, artifact):
    reader = ExactRepositoryBytes(
        mission.repository_evidence_source.github_repository, reference.repository_revision,
        {"contract.json": json.dumps(artifact, sort_keys=True).encode()},
    )
    observations = RepositoryCriterionObserver(reader).observe(mission, reference, "forge")
    bindings = tuple(MissionCriterionEvidenceBinding(
        mission_criterion_id(mission.id, contract.criterion), (reference,),
        RepositoryTruthReference(**truth),
        tuple(item for item in observations if item.contract_digest == contract.digest), contract.digest,
    ) for contract in mission.criterion_assessment_contracts)
    return MissionCompletionEvidence(mission.id, canonical_digest(mission.to_dict()), bindings)


def terminal_completion(mission, evidence, truth, realized_criteria):
    repository = evidence.repository_evidence
    reference = CanonicalExecutionEvidenceReference(
        evidence.receipt_id, repository.action_id, evidence.report_id,
        repository.repository_revision, repository.content_digest,
        candidate_revision=repository.candidate_revision,
    )
    artifact = {f"criterion-{index}": criterion in realized_criteria
                for index, criterion in enumerate(mission.acceptance_criteria)}
    return observed_completion(mission, reference, truth, artifact)


def approved_planning(mission):
    return ArchitecturePlanningEvidence(
        mission.scope, ("forge/runtime",), mission.engineering_constraints or ("bounded",),
        mission.risks or ("scope-drift",), ("fixture-policy",),
        mission.dependencies or ("none",), 16_000, 4_000, "1",
        criterion_assessment_contracts=mission.criterion_assessment_contracts,
        maximum_actions=mission.maximum_actions,
        maximum_consecutive_no_progress_actions=mission.maximum_consecutive_no_progress_actions,
        repository_evidence_source=mission.repository_evidence_source,
    ).to_dict()


def planning_state(state, mission, truth):
    context = MissionContinuationContext.from_runtime(
        mission, planning=approved_planning(mission), actions=state.actions,
        execution_history=state.execution_history, completion=state.completion,
        repository_truth=truth, delegations=state.delegations,
    )
    criteria = () if state.completion is None else tuple(MissionCriterionPlanningState(
        item["criterion_id"], MissionCriterionEvaluationStatus(item["status"]),
    ) for item in state.completion["criteria"])
    return MissionPlanningState(mission.id, state.revision, criterion_states=criteria,
                                continuation_context=context)


def seed_pending(store, mission, truth, *, occurred_at):
    """Seed approved-input state for generic loop unit tests only.

    This fixture is deliberately not canonical approval/intake evidence. The
    installed-runtime suites exercise the actual governance writers instead.
    """
    store.create_pending(mission, occurred_at=occurred_at)
    document = store._runtime.get_document("mission_state", mission.id)
    document["admission_contract"] = {"planning": approved_planning(mission), "test_fixture": True}
    document["repository_truth"] = dict(truth)
    store._runtime.save_mission_state(document)
