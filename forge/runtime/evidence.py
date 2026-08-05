"""Read-only Runtime Database projections for Forge qualification and reports.

Forge owns these projections. Execution Host evidence remains outside this
boundary: only immutable execution-receipt identities are retained here.
"""

from __future__ import annotations

import json
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

    def planning_state(self) -> dict[str, Any]:
        return self._database.get_document("planning_state", "1")

    def execution_receipts(self, mission_id: str) -> tuple[dict[str, str], ...]:
        rows = self._database._connection.execute(
            "SELECT receipt_id, execution_host, execution_run_id, engineering_report_id, correlation_identity, executed_at, outcome "
            "FROM execution_receipts WHERE mission_id = ? ORDER BY executed_at, receipt_id", (mission_id,)
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def mission_qualification(self, mission_id: str) -> dict[str, Any]:
        """Build a qualification strictly from Runtime Database state."""
        try:
            state = self.mission_state(mission_id)
        except RuntimeDatabaseError:
            return {"mission_id": mission_id, "mission_state": None, "architecture_reviews": (),
                    "mission_recommendations": (), "decision_evidence": (), "execution_receipts": (),
                    "mission_lineage": (), "completion_timestamp": None, "mission_outcome": None,
                    "missing_runtime_evidence": (f"{mission_id}:mission_state",), "qualified": False,
                    "ownership": {"runtime_state": "forge_runtime_database", "execution_evidence": "execution_host", "architecture": "repository_truth"}}
        reviews = self._documents("architecture_reviews", "mission_id", mission_id)
        recommendations = self._documents("mission_recommendations", "mission_id", mission_id)
        decisions = self._documents("decision_evidence", "mission_id", mission_id)
        receipts = self.execution_receipts(mission_id)
        lifecycle = self._lifecycle(mission_id)
        successful_receipts = tuple(receipt for receipt in receipts if receipt["outcome"] == "complete")
        decision_receipts = {
            reference["artifact_id"]
            for decision in decisions for reference in decision.get("execution_receipt_references", ())
            if isinstance(reference, dict) and isinstance(reference.get("artifact_id"), str)
        }
        completed = state.get("status") in {"COMPLETE", "COMPLETED"} and state.get("completion") is not None
        expected_lineage = ("ACTIVATED", "COMPLETED")
        actual_lineage = tuple(item["lifecycle"] for item in lifecycle)
        missing: list[str] = []
        if not completed:
            missing.append(f"{mission_id}:complete_mission_state")
        if actual_lineage != expected_lineage:
            missing.append(f"{mission_id}:deterministic_mission_lineage")
        if not reviews:
            missing.append(f"{mission_id}:architecture_review")
        if not recommendations:
            missing.append(f"{mission_id}:mission_recommendation")
        if not decisions:
            missing.append(f"{mission_id}:decision_evidence")
        if len(receipts) != 1 or len(successful_receipts) != 1:
            missing.append(f"{mission_id}:single_successful_execution_receipt")
        elif successful_receipts[0]["receipt_id"] not in decision_receipts:
            missing.append(f"{mission_id}:decision_receipt_lineage")
        receipt = successful_receipts[0] if len(successful_receipts) == 1 else None
        if receipt is not None and not all(receipt[key] for key in (
            "execution_host", "execution_run_id", "engineering_report_id", "correlation_identity", "executed_at", "outcome",
        )):
            missing.append(f"{mission_id}:complete_execution_receipt_identity")
        completion_timestamp = next((item["occurred_at"] for item in lifecycle if item["lifecycle"] == "COMPLETED"), None)
        complete = not missing
        return {
            "mission_id": mission_id, "mission_state": state, "architecture_reviews": reviews,
            "mission_recommendations": recommendations, "decision_evidence": decisions,
            "execution_receipts": receipts, "mission_lifecycle": lifecycle, "mission_lineage": lifecycle,
            "completion_timestamp": completion_timestamp, "mission_outcome": None if receipt is None else receipt["outcome"],
            "execution_host": None if receipt is None else receipt["execution_host"],
            "execution_run_id": None if receipt is None else receipt["execution_run_id"],
            "missing_runtime_evidence": tuple(missing), "qualified": complete,
            "ownership": {"runtime_state": "forge_runtime_database", "execution_evidence": "execution_host", "architecture": "repository_truth"},
        }

    def bootstrap_qualification(self, mission_ids: tuple[str, ...]) -> dict[str, Any]:
        missions = tuple(self.mission_qualification(identifier) for identifier in mission_ids)
        dispatcher = self._database._connection.execute("SELECT status, active_mission_id, mission_sequence FROM dispatcher_state WHERE singleton = 1").fetchone()
        sequence_matches = dispatcher is not None and tuple(json.loads(dispatcher["mission_sequence"])) == mission_ids
        idle = dispatcher is not None and dispatcher["status"] == "IDLE" and dispatcher["active_mission_id"] is None
        lifecycle = tuple(
            (row["mission_id"], row["lifecycle"])
            for row in self._database._connection.execute(
                "SELECT mission_id, lifecycle FROM mission_lifecycle_events ORDER BY mission_id, sequence"
            )
        )
        expected_lifecycle = tuple(item for mission_id in mission_ids for item in ((mission_id, "ACTIVATED"), (mission_id, "COMPLETED")))
        try:
            planning = self.planning_state()
        except RuntimeDatabaseError:
            planning = None
        queue_empty = planning is not None and planning.get("current_queue") == [] and planning.get("pending_engineering_actions") == []
        missing = [item for mission in missions for item in mission["missing_runtime_evidence"]]
        if not sequence_matches:
            missing.append("dispatcher:bootstrap_fifo_sequence")
        if lifecycle != expected_lifecycle:
            missing.append("dispatcher:deterministic_lifecycle_sequence")
        if not idle:
            missing.append("dispatcher:idle")
        if not queue_empty:
            missing.append("approved_mission_queue:empty")
        qualified = bool(missions) and not missing
        return {"mission_ids": mission_ids, "missions": missions,
                "dispatcher_status": None if dispatcher is None else dispatcher["status"],
                "approved_mission_queue": () if planning is None else tuple(planning.get("current_queue", ())),
                "planning_state": planning, "mission_lifecycle": lifecycle,
                "ownership": {"architecture": "repository_truth", "operational_state": "forge_runtime_database", "execution_evidence": "engineering_platform"},
                "missing_runtime_evidence": tuple(missing), "qualified": qualified,
                "source": "runtime_database"}

    def architecture_review_report(self, review_id: str) -> dict[str, Any]:
        review = self.architecture_review(review_id)
        return {"report": "architecture_review", "source": "runtime_database", "review": review,
                "execution_receipts": self.execution_receipts(str(review["mission_id"]))}

    def mission_recommendation_report(self, recommendation_id: str) -> dict[str, Any]:
        recommendation = self.mission_recommendation(recommendation_id)
        return {"report": "mission_recommendation", "source": "runtime_database", "recommendation": recommendation}

    def decision_evidence_report(self, decision_id: str) -> dict[str, Any]:
        decision = self.decision_evidence(decision_id)
        return {"report": "decision_evidence", "source": "runtime_database", "decision": decision,
                "execution_receipts": self.execution_receipts(str(decision["mission_context"]["artifact_id"]))}

    def business_workspace(self, mission_id: str) -> dict[str, Any]:
        evidence = self.mission_qualification(mission_id)
        return {key: evidence[key] for key in ("mission_state", "mission_recommendations", "decision_evidence", "architecture_reviews", "execution_receipts")}

    def architecture_workspace(self, mission_id: str) -> dict[str, Any]:
        return self.business_workspace(mission_id)

    def _documents(self, table: str, column: str, value: str) -> tuple[dict[str, Any], ...]:
        keys = {"architecture_reviews": "review_id", "mission_recommendations": "recommendation_id", "decision_evidence": "decision_id"}
        if table not in keys:
            raise RuntimeDatabaseError("unsupported runtime projection")
        rows = self._database._connection.execute(
            f"SELECT document FROM {table} WHERE {column} = ? ORDER BY {keys[table]}", (value,)
        ).fetchall()
        return tuple(json.loads(row["document"]) for row in rows)

    def _lifecycle(self, mission_id: str) -> tuple[dict[str, str], ...]:
        rows = self._database._connection.execute(
            "SELECT lifecycle, occurred_at FROM mission_lifecycle_events WHERE mission_id = ? ORDER BY sequence", (mission_id,)
        ).fetchall()
        return tuple(dict(row) for row in rows)
