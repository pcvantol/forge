"""Read-only Runtime Database projections for Forge qualification and reports.

Forge owns these projections. Execution Host evidence remains outside this
boundary: only immutable execution-receipt identities are retained here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any

from .database import RuntimeDatabase, RuntimeDatabaseError


@dataclass(frozen=True)
class RuntimeDecisionEvidenceReference:
    """A digest-pinned pointer from one Runtime Instance to Decision Evidence.

    The reference deliberately contains no decision reasoning and no host
    evidence.  Its identity binds a Runtime Instance to an immutable Decision
    Evidence record already owned by the Runtime Database.
    """

    runtime_id: str
    repository_identity: str
    decision_id: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        digest = self.content_digest.removeprefix("sha256:")
        if not all((self.runtime_id, self.repository_identity, self.decision_id, self.locator)):
            raise ValueError("runtime decision evidence references require complete identity")
        if not self.content_digest.startswith("sha256:") or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("runtime decision evidence references require a sha256 content digest")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class RuntimeEvidence:
    """The single query boundary for Forge operational evidence."""

    def __init__(self, database: RuntimeDatabase) -> None:
        self._database = database

    def mission_state(self, mission_id: str) -> dict[str, Any]:
        return self._database.get_document("mission_state", mission_id)

    def mission_runtime_projection(self, mission_id: str) -> dict[str, Any]:
        """Reconcile and persist the complete operational view for one active Mission.

        The projection never creates work.  It derives the only executable
        action from the persisted Mission, planning and dispatcher records and
        fails closed when those sources disagree.
        """
        state = self.mission_state(mission_id)
        planning = self.planning_state()
        dispatcher = self._dispatcher_state()
        terminal = state.get("lifecycle") == "COMPLETE" and state.get("status") == "COMPLETE"
        if terminal:
            if dispatcher.get("status") != "IDLE" or dispatcher.get("active_mission_id") is not None:
                raise RuntimeDatabaseError("completed Mission projection requires an idle dispatcher")
            if planning.get("current_queue") or planning.get("pending_engineering_actions"):
                raise RuntimeDatabaseError("completed Mission projection requires an empty approved Mission queue")
        else:
            if dispatcher.get("active_mission_id") != mission_id or dispatcher.get("status") != "ACTIVE":
                raise RuntimeDatabaseError("operational Mission projection requires the active dispatcher Mission")
            if mission_id not in planning.get("current_queue", ()):
                raise RuntimeDatabaseError("operational Mission projection requires the approved Mission queue")
        actions = tuple(state.get("engineering_actions", ()))
        intents = tuple(state.get("engineering_intents", ()))
        if not actions or not intents:
            raise RuntimeDatabaseError("operational Mission projection requires persisted Intents and Actions")
        action_by_id = {item.get("id"): item for item in actions if isinstance(item, dict) and item.get("id")}
        if len(action_by_id) != len(actions):
            raise RuntimeDatabaseError("operational Mission projection requires unique Engineering Actions")
        completed_actions = tuple(item for item in actions if item.get("status") == "COMPLETED")
        ready_actions = tuple(item for item in actions if item.get("status") in {"READY", "ACTIVE"}
                              and all(action_by_id.get(dependency, {}).get("status") == "COMPLETED"
                                      for dependency in item.get("dependencies", ())) )
        blocked_actions = tuple(item for item in actions if item.get("status") == "BLOCKED")
        if terminal:
            if ready_actions or len(completed_actions) != len(actions):
                raise RuntimeDatabaseError("completed Mission projection requires every Engineering Action complete")
            selected, prompt = None, ()
        else:
            if len(ready_actions) != 1:
                raise RuntimeDatabaseError("operational Mission projection requires exactly one executable Engineering Action")
            selected = ready_actions[0]
            if state.get("current_engineering_action", {}).get("id") != selected["id"]:
                raise RuntimeDatabaseError("operational Mission projection current Action is inconsistent")
            prompt = tuple(item for item in state.get("runtime_prompts", ()) if item.get("action_id") == selected["id"]
                           and item.get("status") == "READY_FOR_ENGINEERING_PLATFORM")
            if len(prompt) != 1:
                raise RuntimeDatabaseError("operational Mission projection requires exactly one ready Runtime Prompt")
        completed_intents = tuple(item for item in intents if item.get("status") == "COMPLETED")
        ready_intents = tuple(item for item in intents if item.get("status") in {"APPROVED", "READY", "ACTIVE"})
        blocked_intents = tuple(item for item in intents if item.get("status") == "BLOCKED")
        decision_ids = tuple(state.get("decision_evidence_ids", ()))
        decisions: list[dict[str, Any]] = []
        intake_references: list[dict[str, str]] = []
        for identifier in decision_ids:
            if self._database.has_document("decision_evidence", identifier):
                decisions.append(self.decision_evidence(identifier))
            elif self._database.has_document("mission_intake_evidence", identifier):
                intake_references.append({"artifact_id": identifier, "kind": "mission_intake_evidence"})
            else:
                raise RuntimeDatabaseError("operational Mission projection references unknown Decision Evidence")
        receipt_references = tuple(state.get("execution_receipt_references", ()))
        receipts = self.execution_receipts(mission_id)
        receipt_ids = {item["receipt_id"] for item in receipts}
        if any(reference.get("artifact_id") not in receipt_ids for reference in receipt_references if isinstance(reference, dict)):
            raise RuntimeDatabaseError("operational Mission projection references an unknown Execution Receipt")
        source = {"mission_state": state, "planning_state": planning, "dispatcher_state": dispatcher,
                  "decision_ids": decision_ids, "execution_receipt_references": receipt_references}
        source_digest = "sha256:" + sha256(json.dumps(source, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        projection = {
            "mission_id": mission_id, "mission_lifecycle": state.get("lifecycle"), "mission_progress": state.get("progress"),
            "current_intent": state.get("current_engineering_intent"), "completed_intents": completed_intents,
            "ready_intents": ready_intents, "blocked_intents": blocked_intents,
            "discovered_intents": tuple(state.get("discovered_engineering_intents", ())),
            "discarded_intents": tuple(state.get("discarded_engineering_intents", ())),
            "completed_engineering_actions": completed_actions,
            "remaining_engineering_actions": tuple(item for item in actions if item.get("status") != "COMPLETED"),
            "next_executable_engineering_action": selected, "runtime_prompts": prompt,
            "planning_confidence": self._planning_confidence(tuple(decisions)),
            "decision_evidence_references": tuple(self.decision_evidence_reference(item["id"]).to_dict() for item in decisions),
            "intake_evidence_references": tuple(intake_references),
            "execution_receipt_references": receipt_references, "dispatcher_state": dispatcher,
            "approved_mission_queue": tuple(planning.get("current_queue", ())), "source_digest": source_digest,
        }
        return self._database.save_mission_runtime_projection(projection)

    def persisted_mission_runtime_projection(self, mission_id: str) -> dict[str, Any]:
        """Read the last reconciled operational view without regenerating it."""
        return self._database.get_document("mission_runtime_projections", mission_id)

    def _dispatcher_state(self) -> dict[str, Any]:
        row = self._database._connection.execute("SELECT document FROM dispatcher_state WHERE singleton = 1").fetchone()
        if row is None:
            raise RuntimeDatabaseError("operational Mission projection requires dispatcher state")
        return json.loads(row["document"])

    @staticmethod
    def _planning_confidence(decisions: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
        for decision in reversed(decisions):
            confidence = decision.get("confidence")
            if isinstance(confidence, dict) and confidence:
                return confidence
        return None

    def architecture_review(self, review_id: str) -> dict[str, Any]:
        return self._database.get_document("architecture_reviews", review_id)

    def mission_recommendation(self, recommendation_id: str) -> dict[str, Any]:
        return self._database.get_document("mission_recommendations", recommendation_id)

    def mission_recommendation_history(self, mission_id: str) -> tuple[dict[str, Any], ...]:
        """Return the immutable, Runtime Instance-owned advisory history."""
        return self._documents("mission_recommendations", "mission_id", mission_id)

    def decision_evidence(self, decision_id: str) -> dict[str, Any]:
        return self._database.get_document("decision_evidence", decision_id)

    def decision_evidence_reference(self, decision_id: str) -> RuntimeDecisionEvidenceReference:
        """Return the bounded Runtime Instance pointer for immutable evidence."""
        decision = self.decision_evidence(decision_id)
        document = json.dumps(decision, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        identity = self._database.runtime_identity
        return RuntimeDecisionEvidenceReference(
            identity.runtime_id,
            identity.repository_identity,
            decision_id,
            f"runtime://{identity.runtime_id}/decision-evidence/{decision_id}",
            "sha256:" + sha256(document.encode("utf-8")).hexdigest(),
        )

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

    def bootstrap_qualification(self, mission_ids: tuple[str, ...] | None = None) -> dict[str, Any]:
        """Project the persisted bootstrap portfolio without source reconstruction.

        The dispatcher snapshot is part of the Runtime Instance.  Callers may
        provide an expected sequence only as an integrity assertion; a normal
        Generation 1 qualification reads the portfolio exclusively from that
        persisted snapshot.
        """
        dispatcher = self._database._connection.execute("SELECT status, active_mission_id, mission_sequence FROM dispatcher_state WHERE singleton = 1").fetchone()
        persisted_ids = () if dispatcher is None else tuple(json.loads(dispatcher["mission_sequence"]))
        selected_ids = persisted_ids if mission_ids is None else mission_ids
        sequence_matches = dispatcher is not None and persisted_ids == selected_ids and len(selected_ids) == len(set(selected_ids))
        missions = tuple(self.mission_qualification(identifier) for identifier in selected_ids)
        idle = dispatcher is not None and dispatcher["status"] == "IDLE" and dispatcher["active_mission_id"] is None
        lifecycle = tuple(
            (row["mission_id"], row["lifecycle"])
            for row in self._database._connection.execute(
                "SELECT mission_id, lifecycle FROM mission_lifecycle_events ORDER BY transition_sequence"
            )
        )
        expected_lifecycle = tuple(item for mission_id in selected_ids for item in ((mission_id, "ACTIVATED"), (mission_id, "COMPLETED")))
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
        return {"mission_ids": selected_ids, "missions": missions,
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
        return {"report": "decision_evidence", "source": "runtime_database", "runtime_instance": {
                    "runtime_id": self._database.runtime_identity.runtime_id,
                    "repository_identity": self._database.runtime_identity.repository_identity,
                }, "decision_evidence_reference": self.decision_evidence_reference(decision_id).to_dict(), "decision": decision,
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
