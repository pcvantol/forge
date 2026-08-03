"""Minimal deterministic view models for the human-facing Business Workspace."""

from __future__ import annotations

from typing import Any

from forge.models.mission_recommendation import MissionRecommendation


def render_mission_recommendation(recommendation: MissionRecommendation) -> dict[str, Any]:
    """Render advisory details without changing recommendation or Portfolio state."""
    return {
        "id": recommendation.id,
        "title": recommendation.title,
        "rationale": recommendation.rationale,
        "business_value": recommendation.business_value,
        "estimated_engineering_effort": recommendation.estimated_effort.value,
        "confidence": recommendation.confidence.to_dict(),
        "required_disciplines": [item.value for item in recommendation.required_disciplines],
        "missing_disciplines": [item.value for item in recommendation.missing_disciplines],
        "dependencies": recommendation.dependencies.to_dict(),
        "architecture_review_reference": recommendation.architecture_review_id,
        "advisory": True,
    }
