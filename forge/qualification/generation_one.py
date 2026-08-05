"""Read-only Generation 1 Bootstrap qualification from Runtime Database state.

This module deliberately has no dependency on repository mission definitions,
dispatchers, state stores, or an Execution Host.  It projects an already
persisted Runtime Database and reports whether the operational record is
sufficient to qualify Generation 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from forge.runtime import RuntimeDatabase, RuntimeIntegrityError


BOOTSTRAP_MISSION_IDS = (
    "MISSION-0001", "MISSION-0002", "MISSION-0003", "MISSION-0004", "MISSION-0005",
)


class EngineeringPlatformEvidenceResolver(Protocol):
    """Read-only resolver for immutable Engineering Platform receipt identities."""

    def resolves(self, *, execution_host: str, execution_run_id: str,
                 engineering_report_id: str, correlation_identity: str,
                 executed_at: str, outcome: str) -> bool: ...


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
    evidence_resolver: EngineeringPlatformEvidenceResolver | None = None,
) -> GenerationOneBootstrapQualificationReport:
    """Qualify only persisted Runtime Database state, failing closed on integrity.

    The caller owns database resolution and opening.  This function neither
    creates a database nor dispatches, resumes, or reconstructs. It may invoke
    only the caller-supplied read-only resolver for immutable receipt identity;
    Execution Evidence remains outside Forge.
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

    projection = database.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_IDS)
    missing = list(projection["missing_runtime_evidence"])
    receipt_validation: dict[str, tuple[dict[str, Any], ...]] = {}
    for mission in projection["missions"]:
        validations: list[dict[str, Any]] = []
        for receipt in mission["execution_receipts"]:
            resolved = evidence_resolver is not None and evidence_resolver.resolves(
                execution_host=receipt["execution_host"],
                execution_run_id=receipt["execution_run_id"],
                engineering_report_id=receipt["engineering_report_id"],
                correlation_identity=receipt["correlation_identity"],
                executed_at=receipt["executed_at"],
                outcome=receipt["outcome"],
            )
            validations.append({"receipt_id": receipt["receipt_id"], "resolved": resolved})
            if not resolved:
                missing.append(f"{mission['mission_id']}:engineering_platform_evidence")
        receipt_validation[mission["mission_id"]] = tuple(validations)
    projection = {**projection, "execution_receipt_validation": receipt_validation, "qualified": not missing}
    return GenerationOneBootstrapQualificationReport(
        "YES" if not missing else "NO",
        projection,
        tuple(missing),
        "Generation 1 Completion Record" if not missing else None,
    )
