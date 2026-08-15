"""Minimal deterministic view models for the human-facing Business Workspace."""

from __future__ import annotations

from typing import Any

from forge.models.mission_recommendation import MissionRecommendation
from forge.models.decision_evidence import DecisionEvidence
from forge.lifecycle import MissionRecommendation as LifecycleMissionRecommendation


def render_mission_recommendation(recommendation: MissionRecommendation) -> dict[str, Any]:
    """Render advisory details without changing recommendation or Portfolio state."""
    return {
        "id": recommendation.id,
        "title": recommendation.title,
        "rationale": recommendation.rationale,
        "business_value": recommendation.business_value,
        "expected_engineering_value": recommendation.expected_engineering_value,
        "risk_if_deferred": recommendation.risk_if_deferred,
        "estimated_engineering_effort": recommendation.estimated_effort.value,
        "confidence": recommendation.confidence.to_dict(),
        "required_disciplines": [item.value for item in recommendation.required_disciplines],
        "missing_disciplines": [item.value for item in recommendation.missing_disciplines],
        "dependencies": recommendation.dependencies.to_dict(),
        "origin": recommendation.origin.value,
        "repository_evidence": [item.to_dict() for item in recommendation.repository_evidence],
        "recommendation_source": recommendation.recommendation_source,
        "decision_evidence_references": list(recommendation.decision_evidence_references),
        "architecture_review_reference": recommendation.architecture_review_id,
        "advisory": True,
    }


def render_business_decision_evidence(evidence: DecisionEvidence) -> dict[str, Any]:
    """Expose recommendation rationale without granting or automating approval."""
    return {"id": evidence.id, "decision_type": evidence.decision_type.value, "decision": evidence.decision,
            "reasoning_summary": evidence.reasoning_summary, "alternatives": [item.to_dict() for item in evidence.alternatives_considered],
            "chosen_alternative": evidence.chosen_alternative, "confidence": evidence.confidence.to_dict(),
            "approval_state": evidence.approval_state.value, "advisory": True}


def render_persisted_mission_recommendation(recommendation: LifecycleMissionRecommendation) -> dict[str, Any]:
    """Render lifecycle-owned recommendation fields required for Business review."""
    return {
        "id": recommendation.id, "recommendation_set_id": recommendation.recommendation_set_id,
        "rank": recommendation.rank, "title": recommendation.title,
        "mission_origin": recommendation.mission_origin, "business_value": recommendation.business_value,
        "architectural_value": recommendation.architectural_value, "engineering_value": recommendation.engineering_value,
        "confidence": recommendation.confidence, "dependencies": list(recommendation.dependencies),
        "risk_if_deferred": recommendation.risk_if_deferred, "rationale": recommendation.business_summary,
        "decision_evidence_reference": recommendation.decision_evidence_reference,
        "recommendation_status": recommendation.status.value, "approval_status": "NOT_YET_APPROVED",
        "advisory": True,
    }
