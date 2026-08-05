"""Read-only Generation 1 completion qualification from Runtime Instance state.

Generation 1 bootstrap is historical engineering, represented by Repository
Truth and Engineering Platform evidence.  It is deliberately not recreated in
the operational Runtime Instance.  This boundary therefore verifies that a
valid Runtime Instance is ready, intentionally empty, and awaiting its first
approved Generation 2 Mission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from forge.runtime import RuntimeDatabase, RuntimeIntegrityError
from forge.runtime.database import RuntimeDatabaseError


@dataclass(frozen=True)
class GenerationOneBootstrapQualificationReport:
    """The immutable-shape result of a single read-only qualification pass."""

    answer: str
    projection: dict[str, Any]
    missing_runtime_evidence: tuple[str, ...]
    recommended_next_increment: str | None

    @property
    def generation_complete(self) -> bool:
        return self.answer == "YES"


def qualify_generation_one_bootstrap(
    database: RuntimeDatabase,
) -> GenerationOneBootstrapQualificationReport:
    """Qualify an empty, integrity-valid operational Runtime Instance.

    The caller owns database resolution and opening.  This function neither
    creates, dispatches, resumes, reconstructs, nor imports bootstrap work.
    Historical execution evidence remains owned by Engineering Platform.
    """

    try:
        database.validate_integrity(record_status=False)
    except RuntimeIntegrityError as error:
        return GenerationOneBootstrapQualificationReport(
            "NO",
            {"source": "runtime_database", "integrity": "failed", "missions": ()},
            (f"runtime_integrity:{error}",),
            None,
        )

    counts = {
        "mission_state": database._connection.execute("SELECT COUNT(*) FROM mission_state").fetchone()[0],
        "decision_evidence": database._connection.execute("SELECT COUNT(*) FROM decision_evidence").fetchone()[0],
        "architecture_reviews": database._connection.execute("SELECT COUNT(*) FROM architecture_reviews").fetchone()[0],
        "mission_recommendations": database._connection.execute("SELECT COUNT(*) FROM mission_recommendations").fetchone()[0],
        "execution_receipts": database._connection.execute("SELECT COUNT(*) FROM execution_receipts").fetchone()[0],
        "mission_lifecycle_events": database._connection.execute("SELECT COUNT(*) FROM mission_lifecycle_events").fetchone()[0],
    }
    dispatcher = database._connection.execute(
        "SELECT status, active_mission_id, mission_sequence FROM dispatcher_state WHERE singleton = 1"
    ).fetchone()
    try:
        planning = database.runtime_evidence().planning_state()
    except RuntimeDatabaseError:
        planning = {"current_queue": [], "pending_engineering_actions": []}
    dispatcher_idle = dispatcher is None or (
        dispatcher["status"] == "IDLE" and dispatcher["active_mission_id"] is None
    )
    queue_empty = planning.get("current_queue") == [] and planning.get("pending_engineering_actions") == []
    empty = not any(counts.values())
    missing: list[str] = []
    if not empty:
        missing.append("runtime_instance:intentionally_empty")
    if not dispatcher_idle:
        missing.append("dispatcher:idle")
    if not queue_empty:
        missing.append("approved_mission_queue:empty")
    projection = {
        "source": "runtime_instance",
        "runtime_identity": database.runtime_identity.to_dict(),
        "historical_bootstrap_mission_ids": (
            "MISSION-0001", "MISSION-0002", "MISSION-0003", "MISSION-0004", "MISSION-0005",
        ),
        "runtime_record_counts": counts,
        "dispatcher_status": "IDLE" if dispatcher is None else dispatcher["status"],
        "approved_mission_queue": tuple(planning.get("current_queue", ())),
        "planning_state": planning,
        "runtime_instance_status": "intentionally_empty" if empty else "operational_state_present",
        "ownership": {
            "historical_architecture": "repository_truth",
            "historical_execution_evidence": "engineering_platform",
            "operational_runtime": "forge_runtime_instance",
        },
        "qualified": not missing,
    }
    return GenerationOneBootstrapQualificationReport(
        "YES" if not missing else "NO",
        projection,
        tuple(missing),
        "Portfolio Intelligence Foundation" if not missing else None,
    )
