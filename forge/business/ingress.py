"""Forge-owned Business Governance Ingress for canonical recommendations.

This composition service deliberately accepts only records in the canonical
RecommendationLifecycleStore.  It has no Engineering Platform dependency and
delegates identity allocation to RuntimeDatabase and downstream work to the
existing MissionRuntimeScheduler.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from forge.governance import GovernanceRole, ResolvedGovernanceProfile
from forge.lifecycle import (
    LifecycleError,
    MissionCandidate,
    RecommendationLifecycleStore,
    RecommendationStatus,
)
from forge.mission_scheduler import MissionRuntimeScheduler, SchedulerResult
from forge.runtime import RuntimeDatabase


@dataclass(frozen=True)
class BusinessGovernanceIngressResult:
    recommendation_id: str
    result: str
    business_decision_id: str | None
    business_approval_status: str | None
    architecture_state: str
    mission_candidate_id: str | None
    mission_id: str | None
    mission_runtime_state: str | None
    scheduler_state: str | None
    decision_evidence_references: tuple[str, ...]


class SchedulerHandoff(Protocol):
    """The scheduler's existing handoff surface; ingress owns no submission."""

    def evaluate(self, mission_id: str) -> SchedulerResult: ...


class BusinessGovernanceIngress:
    """Approve and reconcile one existing recommendation through canonical state."""

    def __init__(self, lifecycle: RecommendationLifecycleStore, runtime: RuntimeDatabase,
                 governance: ResolvedGovernanceProfile, *, scheduler: SchedulerHandoff | None = None) -> None:
        self._lifecycle = lifecycle
        self._runtime = runtime
        self._governance = governance
        self._scheduler = scheduler

    def approve_recommendation(self, recommendation_id: str, *, actor: str | None,
                               occurred_at: str, rationale: str) -> BusinessGovernanceIngressResult:
        if not actor:
            return self._result(recommendation_id, "AUTHORIZATION_REQUIRED", architecture_state="NOT_REACHED")
        allowed = self._governance.role_assignments.get(GovernanceRole.BUSINESS_OWNER, ())
        if actor not in allowed:
            return self._result(recommendation_id, "FORBIDDEN", architecture_state="NOT_REACHED")
        try:
            recommendation = self._lifecycle.resolve_recommendation(recommendation_id)
        except LifecycleError as error:
            result = "AMBIGUOUS" if "ambiguous" in str(error) else "NOT_FOUND"
            return self._result(recommendation_id, result, architecture_state="NOT_REACHED")
        recommendation_id = recommendation.id
        if recommendation.status is RecommendationStatus.RECOMMENDED:
            recommendation = self._lifecycle.transition(
                recommendation_id, RecommendationStatus.BUSINESS_APPROVED, actor=actor,
                occurred_at=occurred_at, rationale=rationale,
                references=(recommendation.decision_evidence_reference,),
            )
        elif recommendation.status not in {
            RecommendationStatus.BUSINESS_APPROVED, RecommendationStatus.ARCHITECTURE_APPROVED,
            RecommendationStatus.MISSION_ALLOCATED,
        }:
            return self._result(recommendation_id, "INVALID_LIFECYCLE_STATE",
                                architecture_state=recommendation.status.value)
        if recommendation.status is RecommendationStatus.BUSINESS_APPROVED:
            return self._current(recommendation_id, "WAITING_ARCHITECTURE_APPROVAL",
                                 architecture_state="WAITING_ARCHITECTURE_APPROVAL")
        return self._reconcile_approved(recommendation_id, occurred_at)

    def _reconcile_approved(self, recommendation_id: str, occurred_at: str) -> BusinessGovernanceIngressResult:
        allocation = self._lifecycle.allocation_for_recommendation(recommendation_id)
        candidate = self._lifecycle.candidate_for_recommendation(recommendation_id)
        if allocation is None:
            if candidate is None:
                recommendation = self._lifecycle.get_recommendation(recommendation_id)
                candidate = MissionCandidate(
                    id="candidate:" + sha256(recommendation_id.encode()).hexdigest()[:20],
                    recommendation_id=recommendation_id, title=recommendation.title,
                    objective=recommendation.engineering_summary,
                    scope=(recommendation.business_summary,),
                    acceptance_criteria=(recommendation.engineering_value,),
                    architecture_constraints=(recommendation.architectural_value,),
                    dependencies=recommendation.dependencies,
                )
                self._lifecycle.create_candidate(candidate)
            allocation = self._lifecycle.allocate(
                candidate.id, actor="forge", occurred_at=occurred_at,
                rationale="Canonical Business and Architecture approvals permit Mission allocation.",
                allocate_mission_id=lambda source, timestamp: self._runtime.allocate_next_mission_id(
                    source=f"recommendation:{source}", allocated_at=timestamp),
            )
        self._initialize_runtime(allocation.mission_id, recommendation_id, candidate.id, occurred_at, allocation)
        scheduler_state = "SCHEDULER_ELIGIBLE"
        if self._scheduler is not None:
            scheduler_state = self._scheduler.evaluate(allocation.mission_id).state
        return self._current(recommendation_id, "APPROVED_AND_ACTIVATED",
                             architecture_state="ARCHITECTURE_APPROVED", scheduler_state=scheduler_state)

    def _initialize_runtime(self, mission_id: str, recommendation_id: str, candidate_id: str,
                            occurred_at: str, allocation: object) -> None:
        try:
            self._runtime.get_document("mission_state", mission_id)
            runtime_exists = True
        except Exception:
            runtime_exists = False
            # Runtime Decision Evidence has a foreign-key relationship to its
            # Mission.  Reserve only the canonical operational record first;
            # the complete initialized graph is written below.
            self._runtime.save_mission_state({
                "mission_id": mission_id, "lifecycle": "ALLOCATED", "status": "ALLOCATED",
                "progress": {"percent_complete": 0}, "resume": {"phase": "governance_activation"},
                "execution_policy": {"mode": "mission_review", "execution_authorized": False},
            })
        if not self._runtime.has_document("decision_evidence", f"{mission_id}-governance-activation-1"):
            self._runtime.record_decision_evidence({
                "id": f"{mission_id}-governance-activation-1", "decision_type": "mission_planning",
                "timestamp": occurred_at, "mission_context": {"artifact_id": mission_id},
                "repository_context": {"artifact_id": "forge-governance"},
                "reasoning_summary": "Allocated canonical Mission is activated from immutable governance evidence.",
                "evidence_references": [{"artifact_id": item} for item in (
                    recommendation_id, candidate_id, allocation.business_decision_evidence_id,
                    allocation.architecture_decision_evidence_id, allocation.allocation_decision_evidence_id)],
                "alternatives_considered": [{"id": "wait", "reason": "Both required approvals are already recorded."}],
                "chosen_alternative": "activate", "confidence": {"score": 100, "mission_state": {"artifact_id": mission_id}},
                "execution_receipt_references": [],
            })
        if not runtime_exists:
            intent_id, action_id = f"{mission_id}-intent-1", f"{mission_id}-action-1"
            intent = {"id": intent_id, "title": "Approved Mission activation", "objective": "Execute the approved bounded Mission.", "status": "APPROVED"}
            action = {"id": action_id, "intent_id": intent_id, "objective": "Start the approved Mission according to its canonical scope.", "status": "READY", "dependencies": []}
            self._runtime.save_mission_state({
                "mission_id": mission_id, "mission_title": self._lifecycle.get_recommendation(recommendation_id).title,
                "mission_recommendation_status": "MISSION_ALLOCATED", "business_summary": self._lifecycle.get_recommendation(recommendation_id).business_summary,
                "engineering_summary": self._lifecycle.get_recommendation(recommendation_id).engineering_summary,
                "lifecycle": "ACTIVE", "status": "ACTIVE", "progress": {"percent_complete": 0},
                "resume": {"phase": "autonomous_scheduler"}, "execution_policy": {"mode": "mission_review", "execution_authorized": True},
                "governance": {"business_approval": "approved", "architecture_approval": "approved"},
                "engineering_intents": [intent], "engineering_actions": [action],
                "current_engineering_intent": intent, "current_engineering_action": action,
                "runtime_prompts": [{"id": f"scheduler-prompt:{action_id}:1", "action_id": action_id, "intent_id": intent_id, "status": "READY_FOR_ENGINEERING_PLATFORM"}],
                "decision_evidence_ids": [f"{mission_id}-governance-activation-1"], "execution_receipt_references": [],
            })
            self._runtime.record_mission_lifecycle(mission_id, "allocated", occurred_at)
            self._runtime.record_mission_lifecycle(mission_id, "active", occurred_at)
            self._runtime.save_dispatcher_state(status="ACTIVE", mission_sequence=(mission_id,), active_mission_id=mission_id)
            self._runtime.save_planning_state({"planner_version": "business-governance-ingress-1", "current_queue": [mission_id],
                "pending_engineering_actions": [action_id], "blocked_engineering_actions": [],
                "execution_policy": {"mode": "mission_review", "execution_authorized": True},
                "planner_runtime_metadata": {"scheduler_state": "READY"}})
            self._runtime.runtime_evidence().mission_runtime_projection(mission_id)

    def _current(self, recommendation_id: str, result: str, *, architecture_state: str,
                 scheduler_state: str | None = None) -> BusinessGovernanceIngressResult:
        recommendation = self._lifecycle.get_recommendation(recommendation_id)
        history = self._lifecycle.history(recommendation_id)
        decisions = tuple(item.id for item in history)
        business = next((item.id for item in history if item.kind == "business_decision"), None)
        candidate = self._lifecycle.candidate_for_recommendation(recommendation_id)
        allocation = self._lifecycle.allocation_for_recommendation(recommendation_id)
        runtime_state = None
        if allocation is not None:
            runtime_state = self._runtime.get_document("mission_state", allocation.mission_id).get("lifecycle")
        return BusinessGovernanceIngressResult(recommendation_id, result, business,
            "APPROVED" if business else None, architecture_state, None if candidate is None else candidate.id,
            None if allocation is None else allocation.mission_id, runtime_state, scheduler_state, decisions)

    @staticmethod
    def _result(recommendation_id: str, result: str, *, architecture_state: str) -> BusinessGovernanceIngressResult:
        return BusinessGovernanceIngressResult(recommendation_id, result, None, None, architecture_state,
                                               None, None, None, None, ())
