"""Tests for the immutable, non-executing Engineering Mission model."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import unittest

from forge.models.intent import IntentStatus
from forge.models.mission import (
    EngineeringMission,
    MissionCompletion,
    MissionDependencies,
    MissionDependency,
    MissionEvidence,
    MissionEvidenceKind,
    MissionIntentCompletion,
    MissionIntentMembership,
    MissionScope,
    MissionStatus,
    derive_mission_progress,
    transition_mission,
)


def evidence(kind: MissionEvidenceKind, source_id: str | None = None) -> MissionEvidence:
    return MissionEvidence(
        kind,
        source_id or kind.value,
        "1",
        f"docs/evidence/{kind.value}.md",
        "sha256:" + "a" * 64,
    )


def completion() -> MissionCompletion:
    return MissionCompletion(
        (
            MissionIntentCompletion("intent-1", "1", IntentStatus.VERIFIED),
            MissionIntentCompletion("intent-2", "2", IntentStatus.ARCHIVED),
        ),
        (
            evidence(MissionEvidenceKind.REPOSITORY),
            evidence(MissionEvidenceKind.VALIDATION),
            evidence(MissionEvidenceKind.CONSTITUTIONAL_COMPLIANCE),
        ),
    )


def mission(**changes: object) -> EngineeringMission:
    values: dict[str, object] = {
        "id": "mission-1",
        "revision": "1",
        "title": "Mission model",
        "objective": "Group bounded Engineering Intents without executing them.",
        "scope": MissionScope(("Mission model",), ("Runtime execution",)),
        "intents": (
            MissionIntentMembership(1, "intent-1", "1"),
            MissionIntentMembership(2, "intent-2", "2"),
        ),
        "dependencies": MissionDependencies((MissionDependency("foundation", "1", "Foundation contracts"),)),
    }
    values.update(changes)
    return EngineeringMission(**values)  # type: ignore[arg-type]


class EngineeringMissionTests(unittest.TestCase):
    def test_closed_lifecycle_prohibits_skips_and_terminal_transitions(self) -> None:
        created = mission()
        with self.assertRaisesRegex(ValueError, "not permitted"):
            transition_mission(created, MissionStatus.ACTIVE)
        planning = transition_mission(created, MissionStatus.PLANNING)
        active = transition_mission(planning, MissionStatus.ACTIVE)
        blocked = transition_mission(active, MissionStatus.BLOCKED)
        active = transition_mission(blocked, MissionStatus.ACTIVE)
        completed = transition_mission(replace(active, completion=completion()), MissionStatus.COMPLETED)
        archived = transition_mission(completed, MissionStatus.ARCHIVED)
        self.assertEqual(archived.status, MissionStatus.ARCHIVED)
        with self.assertRaisesRegex(ValueError, "not permitted"):
            transition_mission(archived, MissionStatus.ACTIVE)
        with self.assertRaises(FrozenInstanceError):
            archived.title = "changed"  # type: ignore[misc]

    def test_mission_contains_ordered_revision_pinned_engineering_intents(self) -> None:
        record = mission()
        self.assertEqual([item.intent_id for item in record.intents], ["intent-1", "intent-2"])
        self.assertEqual(record.to_dict()["intents"][1]["intent_revision"], "2")
        with self.assertRaisesRegex(ValueError, "ordered consecutively"):
            mission(intents=(MissionIntentMembership(2, "intent-1", "1"),))
        with self.assertRaisesRegex(ValueError, "unique"):
            mission(intents=(MissionIntentMembership(1, "intent-1", "1"), MissionIntentMembership(2, "intent-1", "1")))

    def test_completion_requires_all_intents_and_required_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "completed and archived"):
            replace(mission(), status=MissionStatus.COMPLETED)
        incomplete = MissionCompletion(
            (MissionIntentCompletion("intent-1", "1", IntentStatus.VERIFIED),),
            (
                evidence(MissionEvidenceKind.REPOSITORY),
                evidence(MissionEvidenceKind.VALIDATION),
                evidence(MissionEvidenceKind.CONSTITUTIONAL_COMPLIANCE),
            ),
        )
        with self.assertRaisesRegex(ValueError, "cover every"):
            transition_mission(replace(transition_mission(transition_mission(mission(), MissionStatus.PLANNING), MissionStatus.ACTIVE), completion=incomplete), MissionStatus.COMPLETED)
        with self.assertRaisesRegex(ValueError, "constitutional compliance"):
            MissionCompletion(
                (MissionIntentCompletion("intent-1", "1", IntentStatus.VERIFIED),),
                (evidence(MissionEvidenceKind.REPOSITORY), evidence(MissionEvidenceKind.VALIDATION)),
            )

    def test_evidence_aggregation_and_progress_are_derived_from_intents(self) -> None:
        record = mission()
        progress = derive_mission_progress(
            record,
            {("intent-1", "1"): IntentStatus.VERIFIED, ("intent-2", "2"): IntentStatus.IMPLEMENTED},
        )
        self.assertEqual(progress.to_dict(), {
            "total_intents": 2,
            "completed_intents": 1,
            "remaining_intent_ids": ["intent-2"],
            "percent_complete": 50,
        })
        completed = transition_mission(
            replace(transition_mission(transition_mission(record, MissionStatus.PLANNING), MissionStatus.ACTIVE), completion=completion()),
            MissionStatus.COMPLETED,
        )
        self.assertEqual({item["kind"] for item in completed.to_dict()["completion"]["evidence"]}, {
            "repository", "validation", "constitutional_compliance",
        })


if __name__ == "__main__":
    unittest.main()
