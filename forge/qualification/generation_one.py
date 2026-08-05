"""Read-only Generation 1 Bootstrap qualification from Runtime Database state.

This module deliberately has no dependency on repository mission definitions,
dispatchers, state stores, or an Execution Host.  It projects an already
persisted Runtime Database and reports whether the operational record is
sufficient to qualify Generation 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from forge.dispatcher import BOOTSTRAP_MISSION_SEQUENCE
from forge.runtime import RuntimeDatabase, RuntimeIntegrityError


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


def qualify_generation_one_bootstrap(database: RuntimeDatabase) -> GenerationOneBootstrapQualificationReport:
    """Qualify only persisted Runtime Database state, failing closed on integrity.

    The caller owns database resolution and opening.  This function neither
    creates a database nor dispatches, resumes, reconstructs, or contacts an
    Execution Host.  Execution Evidence is represented solely by the immutable
    receipt references already held by Forge.
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

    projection = database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)
    missing = tuple(projection["missing_runtime_evidence"])
    return GenerationOneBootstrapQualificationReport(
        "YES" if projection["qualified"] else "NO",
        projection,
        missing,
        "Portfolio Intelligence Foundation" if projection["qualified"] else None,
    )
