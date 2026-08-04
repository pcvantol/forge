"""Execution Workspace projection for Decision Evidence references only."""

from __future__ import annotations

from typing import Any

from forge.models.decision_evidence import DecisionEvidence


def render_execution_decision_evidence_reference(evidence: DecisionEvidence) -> dict[str, Any]:
    """Execution owns its evidence; this projection intentionally duplicates no reasoning."""
    return {"decision_evidence_id": evidence.id, "decision_type": evidence.decision_type.value,
            "repository_truth_reference": evidence.repository_context.to_dict(),
            "execution_evidence_references": [item.to_dict() for item in evidence.execution_evidence_references]}
