"""Minimal deterministic Architecture Workspace detail view."""

from __future__ import annotations

from typing import Any

from forge.models.architecture_mission import ArchitectureMission
from forge.models.decision_evidence import DecisionEvidence


def render_architecture_mission(mission: ArchitectureMission) -> dict[str, Any]:
    return {**mission.to_dict(), "advisory_available": True, "execution_available": False, "repository_mutation_available": False}


def render_architecture_decision_evidence(evidence: DecisionEvidence) -> dict[str, Any]:
    """Expose architecture rationale and traceability without an approval action."""
    return {"id": evidence.id, "decision_type": evidence.decision_type.value, "decision": evidence.decision,
            "reasoning_summary": evidence.reasoning_summary, "required_disciplines": list(evidence.required_disciplines),
            "architecture_constraints": list(evidence.architecture_constraints),
            "traceability": [item.to_dict() for item in evidence.evidence_references], "confidence": evidence.confidence.to_dict(),
            "approval_state": evidence.approval_state.value, "execution_available": False}
