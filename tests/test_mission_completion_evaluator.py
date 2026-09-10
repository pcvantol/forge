"""Evidence-derived Architecture Mission completion contract tests."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import unittest

from forge.completion import MissionCompletionEvaluationError, MissionCompletionEvaluator
from forge.models import (
    ArchitectureMission,
    ArchitectureMissionStatus,
    CanonicalExecutionEvidenceReference,
    MissionCompletionEvidence,
    MissionCriterionEvidenceBinding,
    MissionCriterionEvaluationStatus,
    RepositoryTruthReference,
    RequiredDiscipline,
    mission_criterion_id,
)


def digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def mission() -> ArchitectureMission:
    return ArchitectureMission(
        "mission-completion", "candidate", "Completion", "Evaluate evidence.", "Prove the criteria.", "Safety.",
        "review", "recommendation", ("runtime",), ("bounded",), ("criterion-a", "criterion-b"),
        ("local",), ("none",), ("completion",), (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ("missing evidence",),
        ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
    )


TRUTH = RepositoryTruthReference("forge-truth", "abc123", "repository://forge/abc123", digest("truth"))
REFERENCE = CanonicalExecutionEvidenceReference("receipt-a", "action-a", "report-a", "abc123", digest("repository"))
HOST_EVIDENCE = {
    "receipt_id": "receipt-a", "report_id": "report-a", "outcome": "complete",
    "correlation_id": "correlation-a", "host_run_id": "run-a",
    "repository_evidence": {
        "mission_id": mission().id, "action_id": "action-a", "report_id": "report-a",
        "correlation_id": "correlation-a", "host_run_id": "run-a", "repository_revision": "abc123",
        "content_digest": digest("repository"),
    },
}


class MissionCompletionEvaluatorTests(unittest.TestCase):
    def evidence(self, *criteria: str) -> MissionCompletionEvidence:
        return MissionCompletionEvidence(
            mission().id, digest(mission().to_dict()),
            tuple(MissionCriterionEvidenceBinding(
                mission_criterion_id(mission().id, criterion), (REFERENCE,), TRUTH,
            ) for criterion in criteria),
        )

    def test_every_criterion_requires_explicit_current_canonical_evidence(self) -> None:
        evaluator = MissionCompletionEvaluator()
        missing = evaluator.evaluate(mission(), TRUTH.to_dict(), (HOST_EVIDENCE,), self.evidence("criterion-a"))
        self.assertFalse(missing.all_required_criteria_proven)
        self.assertEqual(
            {item.criterion: item.status for item in missing.criteria},
            {"criterion-a": MissionCriterionEvaluationStatus.PROVEN,
             "criterion-b": MissionCriterionEvaluationStatus.UNSATISFIED},
        )
        complete = evaluator.evaluate(
            mission(), TRUTH.to_dict(), (HOST_EVIDENCE,), self.evidence("criterion-a", "criterion-b"),
        )
        self.assertTrue(complete.all_required_criteria_proven)

    def test_stale_truth_and_noncanonical_host_reference_are_unsatisfied(self) -> None:
        stale_truth = replace(TRUTH, revision="old", locator="repository://forge/old", content_digest=digest("old"))
        stale = MissionCompletionEvidence(
            mission().id, digest(mission().to_dict()),
            (MissionCriterionEvidenceBinding(mission_criterion_id(mission().id, "criterion-a"), (REFERENCE,), stale_truth),),
        )
        result = MissionCompletionEvaluator().evaluate(mission(), TRUTH.to_dict(), (HOST_EVIDENCE,), stale)
        self.assertEqual(next(item for item in result.criteria if item.criterion == "criterion-a").reason,
                         "STALE_REPOSITORY_TRUTH")
        wrong_receipt = replace(REFERENCE, receipt_id="prose-only-provider-claim")
        noncanonical = MissionCompletionEvidence(
            mission().id, digest(mission().to_dict()),
            (MissionCriterionEvidenceBinding(mission_criterion_id(mission().id, "criterion-a"), (wrong_receipt,), TRUTH),),
        )
        result = MissionCompletionEvaluator().evaluate(mission(), TRUTH.to_dict(), (HOST_EVIDENCE,), noncanonical)
        self.assertEqual(next(item for item in result.criteria if item.criterion == "criterion-a").reason,
                         "NON_CANONICAL_EXECUTION_EVIDENCE")

    def test_wrong_mission_or_unknown_criterion_fails_closed(self) -> None:
        with self.assertRaisesRegex(MissionCompletionEvaluationError, "approved Mission"):
            MissionCompletionEvaluator().evaluate(
                mission(), TRUTH.to_dict(), (HOST_EVIDENCE,),
                replace(self.evidence("criterion-a"), mission_digest=digest("wrong")),
            )
        unknown = MissionCompletionEvidence(
            mission().id, digest(mission().to_dict()),
            (MissionCriterionEvidenceBinding("provider-prose", (REFERENCE,), TRUTH),),
        )
        with self.assertRaisesRegex(MissionCompletionEvaluationError, "unknown"):
            MissionCompletionEvaluator().evaluate(mission(), TRUTH.to_dict(), (HOST_EVIDENCE,), unknown)


if __name__ == "__main__":
    unittest.main()
