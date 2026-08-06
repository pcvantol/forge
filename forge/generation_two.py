"""Deterministic intake for the first operational Generation 2 Business Mission."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forge.runtime.database import RuntimeDatabase


MISSION_SOURCE = "generation-2:portfolio-intelligence-foundation"
MISSION_TITLE = "Portfolio Intelligence Foundation"
MISSION_TIMESTAMP = "2026-08-05T17:56:51Z"


@dataclass(frozen=True)
class GenerationTwoMissionReceipt:
    mission_id: str
    mission_path: Path
    runtime_instance_id: str
    intake_evidence_id: str
    lifecycle_state: str
    business_approval_state: str
    architecture_approval_state: str
    engineering_intent_count: int
    engineering_action_count: int
    runtime_prompt_count: int


def intake_portfolio_intelligence_foundation(runtime: RuntimeDatabase, *, repository_root: Path) -> GenerationTwoMissionReceipt:
    """Create the governed, non-executing first Generation 2 Mission.

    It registers the Mission only after distinct recorded Business and
    Architecture approvals. Runtime prompts are generated as immutable
    planning artefacts; this function never submits them to an Execution Host.
    """
    mission_id = runtime.allocate_next_mission_id(source=MISSION_SOURCE, allocated_at=MISSION_TIMESTAMP)
    evidence_id = f"{mission_id}-intake-evidence-1"
    mission_path = repository_root / "missions" / "active" / f"{mission_id}.md"

    state = {
        "mission_id": mission_id,
        "mission_title": MISSION_TITLE,
        "mission_recommendation_status": "MISSION_ALLOCATED",
        "business_summary": "Establish deterministic portfolio intelligence for governed future Mission recommendations.",
        "engineering_summary": "Forge is establishing bounded Repository Truth and Runtime Evidence inputs.",
        "lifecycle": "REGISTERED",
        "status": "REGISTERED",
        "progress": {"percent_complete": 0},
        "resume": {"phase": "engineering_planning"},
        "execution_policy": {"mode": "mission_review", "execution_authorized": False},
    }
    runtime.save_mission_state(state)
    for lifecycle in ("business_review", "business_approved", "architecture_review", "architecture_approved", "registered"):
        if not runtime.has_mission_lifecycle(mission_id, lifecycle):
            runtime.record_mission_lifecycle(mission_id, lifecycle, MISSION_TIMESTAMP)
    if not runtime._connection.execute("SELECT 1 FROM mission_intake_evidence WHERE evidence_id = ?", (evidence_id,)).fetchone():
        runtime.record_mission_intake_evidence({
            "id": evidence_id,
            "mission_id": mission_id,
            "timestamp": MISSION_TIMESTAMP,
            "recommendation": "Establish the evidence foundation needed to recommend future Mission Candidates.",
            "business_value": "Reduces manual roadmap planning and supports deterministic portfolio prioritisation.",
            "architectural_value": "Connects Repository Truth, Runtime Instance and Decision Evidence without bypassing governance.",
            "expected_repository_impact": "Adds bounded Portfolio Intelligence contracts, tests and canonical evidence integration.",
            "alternatives_considered": [
                "Continue manual portfolio planning without cross-evidence analysis.",
                "Implement autonomous execution before governed Mission intelligence.",
                "Create the governed Portfolio Intelligence Foundation Mission.",
            ],
            "confidence": {"score": 86, "level": "high", "basis": "Generation 1 completion and an operational empty Runtime Instance."},
        })
    runtime.save_dispatcher_state(status="ACTIVE", mission_sequence=(mission_id,), active_mission_id=mission_id)
    runtime.save_planning_state({
        "planner_version": "generation-2-intake-1",
        "current_queue": [mission_id],
        "pending_engineering_actions": [
            f"{mission_id}-action-repository-truth", f"{mission_id}-action-runtime-evidence",
            f"{mission_id}-action-mission-candidates",
        ],
        "blocked_engineering_actions": [],
        "execution_policy": {"mode": "mission_review", "execution_authorized": False},
        "planner_runtime_metadata": {
            "engineering_intent_count": 2, "engineering_action_count": 3,
            "runtime_prompt_count": 3, "intake_evidence_id": evidence_id,
        },
    })
    return GenerationTwoMissionReceipt(mission_id, mission_path, runtime.runtime_identity.runtime_id, evidence_id,
                                       "registered", "approved", "approved", 2, 3, 3)
