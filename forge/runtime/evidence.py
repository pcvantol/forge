"""Read-only Runtime Database projections for Forge qualification and reports.

Forge owns these projections.  Execution Host evidence remains outside this
boundary: only immutable execution-reference identities are retained here.
"""

from __future__ import annotations

from typing import Any

from .database import RuntimeDatabase, RuntimeDatabaseError


class RuntimeEvidence:
    """The single query boundary for Forge operational evidence."""

    def __init__(self, database: RuntimeDatabase) -> None:
        self._database = database

    def mission_state(self, mission_id: str) -> dict[str, Any]:
        return self._database.get_document("mission_state", mission_id)

    def architecture_review(self, review_id: str) -> dict[str, Any]:
        return self._database.get_document("architecture_reviews", review_id)

    def mission_recommendation(self, recommendation_id: str) -> dict[str, Any]:
        return self._database.get_document("mission_recommendations", recommendation_id)

    def decision_evidence(self, decision_id: str) -> dict[str, Any]:
        return self._database.get_document("decision_evidence", decision_id)

    def execution_references(self, mission_id: str) -> tuple[dict[str, str], ...]:
        rows = self._database._connection.execute(
            "SELECT reference_id, execution_host, execution_run_id, correlation, executed_at, outcome "
            "FROM execution_references WHERE mission_id = ? ORDER BY executed_at, reference_id", (mission_id,)
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def mission_qualification(self, mission_id: str) -> dict[str, Any]:
        """Build a qualification strictly from Runtime Database state."""
        try:
            state = self.mission_state(mission_id)
        except RuntimeDatabaseError:
            return {"mission_id": mission_id, "mission_state": None, "architecture_reviews": (),
                    "mission_recommendations": (), "decision_evidence": (), "execution_references": (),
                    "qualified": False, "ownership": {"runtime_state": "forge_runtime_database", "execution_evidence": "execution_host", "architecture": "repository_truth"}}
        reviews = self._documents("architecture_reviews", "mission_id", mission_id)
        recommendations = self._documents("mission_recommendations", "mission_id", mission_id)
        decisions = self._documents("decision_evidence", "mission_id", mission_id)
        references = self.execution_references(mission_id)
        complete = state.get("status") == "COMPLETED" and bool(references) and bool(reviews)
        return {
            "mission_id": mission_id, "mission_state": state, "architecture_reviews": reviews,
            "mission_recommendations": recommendations, "decision_evidence": decisions,
            "execution_references": references, "qualified": complete,
            "ownership": {"runtime_state": "forge_runtime_database", "execution_evidence": "execution_host", "architecture": "repository_truth"},
        }

    def bootstrap_qualification(self, mission_ids: tuple[str, ...]) -> dict[str, Any]:
        missions = tuple(self.mission_qualification(identifier) for identifier in mission_ids)
        return {"mission_ids": mission_ids, "missions": missions, "qualified": bool(missions) and all(item["qualified"] for item in missions),
                "source": "runtime_database"}

    def architecture_review_report(self, review_id: str) -> dict[str, Any]:
        review = self.architecture_review(review_id)
        return {"report": "architecture_review", "source": "runtime_database", "review": review,
                "execution_references": self.execution_references(str(review["mission_id"]))}

    def mission_recommendation_report(self, recommendation_id: str) -> dict[str, Any]:
        recommendation = self.mission_recommendation(recommendation_id)
        return {"report": "mission_recommendation", "source": "runtime_database", "recommendation": recommendation}

    def decision_evidence_report(self, decision_id: str) -> dict[str, Any]:
        decision = self.decision_evidence(decision_id)
        return {"report": "decision_evidence", "source": "runtime_database", "decision": decision,
                "execution_references": self.execution_references(str(decision["mission_context"]["artifact_id"]))}

    def business_workspace(self, mission_id: str) -> dict[str, Any]:
        evidence = self.mission_qualification(mission_id)
        return {key: evidence[key] for key in ("mission_state", "mission_recommendations", "decision_evidence", "architecture_reviews", "execution_references")}

    def architecture_workspace(self, mission_id: str) -> dict[str, Any]:
        return self.business_workspace(mission_id)

    def _documents(self, table: str, column: str, value: str) -> tuple[dict[str, Any], ...]:
        keys = {"architecture_reviews": "review_id", "mission_recommendations": "recommendation_id", "decision_evidence": "decision_id"}
        if table not in keys:
            raise RuntimeDatabaseError("unsupported runtime projection")
        rows = self._database._connection.execute(
            f"SELECT document FROM {table} WHERE {column} = ? ORDER BY {keys[table]}", (value,)
        ).fetchall()
        import json
        return tuple(json.loads(row["document"]) for row in rows)
