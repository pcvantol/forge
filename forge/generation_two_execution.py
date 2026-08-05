"""Bounded activation and planning for the first operational Generation 2 Mission."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from forge.runtime.database import RuntimeDatabase, RuntimeDatabaseError


MISSION_ID = "MISSION-0006"
ACTIVATION_TIMESTAMP = "2026-08-05T18:31:03Z"
PLANNING_DECISION_ID = f"{MISSION_ID}-planning-decision-1"
INTENT_REPOSITORY_EVIDENCE = f"{MISSION_ID}-intent-repository-runtime-evidence"
INTENT_RECOMMENDATION_BOUNDARY = f"{MISSION_ID}-intent-mission-candidate-boundary"
ACTION_REPOSITORY_TRUTH = f"{MISSION_ID}-action-repository-truth"
ACTION_RUNTIME_EVIDENCE = f"{MISSION_ID}-action-runtime-evidence"
ACTION_MISSION_CANDIDATES = f"{MISSION_ID}-action-mission-candidates"


def _digest(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GenerationTwoExecutionPlanReceipt:
    mission_id: str
    lifecycle_state: str
    engineering_intent_ids: tuple[str, ...]
    engineering_action_ids: tuple[str, ...]
    active_action_id: str
    decision_evidence_id: str
    runtime_prompt_id: str


def _intent(intent_id: str, *, title: str, objective: str, action_ids: tuple[str, ...], depends_on: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "schema_version": "1.2",
        "id": intent_id,
        "revision": "1",
        "title": title,
        "objective": objective,
        "category": "Implementation",
        "status": "APPROVED",
        "approval": {
            "approved_by": "owner-authorized-genesis-transaction",
            "approved_at": ACTIVATION_TIMESTAMP,
            "decision_reference": {"id": PLANNING_DECISION_ID, "version": "1", "locator": "runtime:decision_evidence"},
        },
        "relationships": ([{"kind": "depends_on", "target_intent_id": dependency} for dependency in depends_on]),
        "traceability": {
            "vision": [{"id": MISSION_ID, "version": "1", "locator": "missions/active/MISSION-0006.md"}],
            "architecture": [{"id": "portfolio-intelligence-foundation", "version": "1", "locator": "docs/architecture/generation-1-transition.md"}],
            "roadmap": [{"id": "generation-2", "version": "1", "locator": "README.md"}],
            "proposal": [{"id": "MISSION-0006-intake-evidence-1", "version": "1", "locator": "runtime:mission_intake_evidence"}],
            "repository": [{"id": "forge", "version": "HEAD", "locator": "repository-truth/README.md"}],
        },
        "actions": list(action_ids),
    }


def _action(action_id: str, *, intent_id: str, objective: str, expected_evidence: tuple[str, ...], dependencies: tuple[str, ...] = (), status: str = "READY") -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "id": action_id,
        "intent_id": intent_id,
        "intent_revision": "1",
        "objective": objective,
        "expected_evidence": list(expected_evidence),
        "dependencies": list(dependencies),
        "status": status,
    }


def activate_and_plan_portfolio_intelligence(runtime: RuntimeDatabase) -> GenerationTwoExecutionPlanReceipt:
    """Persist the next executable action without claiming host execution evidence.

    Only the dispatcher-selected active Mission may enter this transition. The
    resulting prompt reference is ready for Engineering Platform; execution
    receipts remain absent until that host returns them.
    """
    dispatcher = runtime._connection.execute("SELECT status, active_mission_id FROM dispatcher_state WHERE singleton = 1").fetchone()
    if dispatcher is None or dispatcher["status"] != "ACTIVE" or dispatcher["active_mission_id"] != MISSION_ID:
        raise RuntimeDatabaseError("exactly the configured active Mission is required for Generation 2 planning")
    state = runtime.get_document("mission_state", MISSION_ID)
    if state.get("lifecycle") not in {"REGISTERED", "ACTIVE"}:
        raise RuntimeDatabaseError("Generation 2 Mission is not eligible for activation")
    if runtime.has_document("decision_evidence", PLANNING_DECISION_ID):
        if state.get("lifecycle") != "ACTIVE":
            raise RuntimeDatabaseError("existing planning evidence requires an active Mission state")
        return GenerationTwoExecutionPlanReceipt(
            MISSION_ID, "ACTIVE", (INTENT_REPOSITORY_EVIDENCE, INTENT_RECOMMENDATION_BOUNDARY),
            (ACTION_REPOSITORY_TRUTH, ACTION_RUNTIME_EVIDENCE, ACTION_MISSION_CANDIDATES),
            ACTION_REPOSITORY_TRUTH, PLANNING_DECISION_ID,
            f"codex-cli-runtime-prompt:{_digest(ACTION_REPOSITORY_TRUTH).removeprefix('sha256:')}",
        )

    intents = (
        _intent(INTENT_REPOSITORY_EVIDENCE,
                title="Repository Truth and Runtime Evidence Foundation",
                objective="Establish bounded Repository Truth and Runtime Evidence inputs for portfolio analysis.",
                action_ids=(ACTION_REPOSITORY_TRUTH, ACTION_RUNTIME_EVIDENCE)),
        _intent(INTENT_RECOMMENDATION_BOUNDARY,
                title="Governed Mission Candidate Recommendation Boundary",
                objective="Keep Mission Candidate recommendations advisory and separate from Business and Architecture approval.",
                action_ids=(ACTION_MISSION_CANDIDATES,), depends_on=(INTENT_REPOSITORY_EVIDENCE,)),
    )
    actions = (
        _action(ACTION_REPOSITORY_TRUTH, intent_id=INTENT_REPOSITORY_EVIDENCE,
                objective="Implement the bounded Repository Truth input required by Portfolio Intelligence.",
                expected_evidence=("repository truth contract", "focused regression coverage"), status="ACTIVE"),
        _action(ACTION_RUNTIME_EVIDENCE, intent_id=INTENT_REPOSITORY_EVIDENCE,
                objective="Connect Runtime Instance and Decision Evidence through bounded, immutable references.",
                expected_evidence=("runtime evidence contract", "focused regression coverage"), dependencies=(ACTION_REPOSITORY_TRUTH,)),
        _action(ACTION_MISSION_CANDIDATES, intent_id=INTENT_RECOMMENDATION_BOUNDARY,
                objective="Implement the advisory Mission Candidate recommendation boundary without approval or execution authority.",
                expected_evidence=("advisory recommendation contract", "focused regression coverage"), dependencies=(ACTION_RUNTIME_EVIDENCE,)),
    )
    prompt_id = f"codex-cli-runtime-prompt:{_digest(ACTION_REPOSITORY_TRUTH).removeprefix('sha256:')}"
    runtime_prompt = {
        "id": prompt_id,
        "action_id": ACTION_REPOSITORY_TRUTH,
        "intent_id": INTENT_REPOSITORY_EVIDENCE,
        "status": "READY_FOR_ENGINEERING_PLATFORM",
        "content_digest": _digest(f"{MISSION_ID}:{ACTION_REPOSITORY_TRUTH}:1"),
    }
    updated_state = {
        **state,
        "lifecycle": "ACTIVE",
        "status": "ACTIVE",
        "progress": {"percent_complete": 0, "completed_engineering_intents": 0, "remaining_engineering_intents": 2,
                     "completed_engineering_actions": 0, "remaining_engineering_actions": 3},
        "resume": {"phase": "engineering_platform_execution", "next_action_id": ACTION_REPOSITORY_TRUTH},
        "execution_policy": {"mode": "mission_review", "execution_authorized": True},
        "engineering_intents": list(intents),
        "engineering_actions": list(actions),
        "current_engineering_intent": intents[0],
        "current_engineering_action": actions[0],
        "runtime_prompts": [runtime_prompt],
        "decision_evidence_ids": ["MISSION-0006-intake-evidence-1", PLANNING_DECISION_ID],
        "execution_receipt_references": [],
    }
    runtime.save_mission_state(updated_state)
    if not runtime.has_mission_lifecycle(MISSION_ID, "active"):
        runtime.record_mission_lifecycle(MISSION_ID, "active", ACTIVATION_TIMESTAMP)
    runtime.save_planning_state({
        "planner_version": "generation-2-mission-planning-1",
        "current_queue": [MISSION_ID],
        "pending_engineering_actions": [ACTION_RUNTIME_EVIDENCE, ACTION_MISSION_CANDIDATES],
        "blocked_engineering_actions": [],
        "execution_policy": {"mode": "mission_review", "execution_authorized": True},
        "planner_runtime_metadata": {
            "engineering_intents": list(intents), "engineering_actions": list(actions),
            "active_engineering_action": ACTION_REPOSITORY_TRUTH, "runtime_prompts": [runtime_prompt],
            "decision_evidence_ids": ["MISSION-0006-intake-evidence-1", PLANNING_DECISION_ID],
        },
    })
    runtime.record_decision_evidence({
        "id": PLANNING_DECISION_ID,
        "decision_type": "mission_planning",
        "timestamp": ACTIVATION_TIMESTAMP,
        "mission_context": {"artifact_id": MISSION_ID},
        "repository_context": {"artifact_id": "forge-repository-truth"},
        "reasoning_summary": "The dispatcher has one active approved Mission; the first action is selected before dependent actions.",
        "evidence_references": [{"artifact_id": "MISSION-0006-intake-evidence-1"}],
        "alternatives_considered": [
            {"id": "defer", "reason": "Leaves the approved active Mission without its required executable plan."},
            {"id": "parallel", "reason": "Violates the one-action-at-a-time execution boundary."},
            {"id": "sequential", "reason": "Selected: preserves dependencies and host receipt ownership."},
        ],
        "chosen_alternative": "sequential",
        "confidence": {"score": 86, "mission_state": {"artifact_id": MISSION_ID}},
        "execution_receipt_references": [],
    })
    return GenerationTwoExecutionPlanReceipt(
        MISSION_ID, "ACTIVE", tuple(item["id"] for item in intents), tuple(item["id"] for item in actions),
        ACTION_REPOSITORY_TRUTH, PLANNING_DECISION_ID, prompt_id,
    )
