"""Historical bootstrap qualification readback and legacy execution fence.

The original seed harness has no approved substantive assessment contracts.
Its persisted terminal results remain readable, but new execution cannot use
receipt associations to qualify those Missions under completion v2.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Protocol

from forge.runtime import RuntimeDatabase
from forge.scheduler.adapter import EngineeringPlatformInboxReceipt, EngineeringPlatformReport


BOOTSTRAP_MISSION_SEQUENCE = ("MISSION-0001", "MISSION-0002", "MISSION-0003", "MISSION-0004", "MISSION-0005")


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class BootstrapQualificationReport:
    answer: str
    generation: str
    dispatcher_status: str
    mission_ids: tuple[str, ...]
    evidence_path: str
    recommended_next_increment: str


class BootstrapQualificationInterrupted(BaseException):
    """Retained API name for pre-v2 callers; legacy execution is now blocked."""


class EngineeringPlatformEvidenceSource(Protocol):
    """Receipt/report boundary owned by Engineering Platform, never Forge.

    Forge can submit a rendered prompt and retrieve the corresponding receipt
    and report, but it cannot mint either artifact or infer a terminal result.
    A production caller supplies the Engineering Platform 1.5 client.
    """

    def submit(self, request: Any) -> EngineeringPlatformInboxReceipt: ...
    def receipt_for(self, correlation_id: str) -> EngineeringPlatformInboxReceipt | None: ...
    def report_for(self, run_id: str) -> EngineeringPlatformReport | None: ...


@dataclass(frozen=True)
class CanonicalBootstrapMission:
    identifier: str
    title: str
    statement: str
    business_objective: str
    source_digest: str


def _paragraph(document: str, heading: str) -> str:
    match = re.search(rf"(?ms)^({re.escape(heading)})\n\n(.+?)(?=\n---|\n[A-Z][A-Za-z ]+\n\n|\Z)", document)
    if match is None:
        raise ValueError(f"canonical bootstrap mission is missing {heading}")
    return " ".join(line.strip() for line in match.group(2).splitlines() if line.strip())


def load_canonical_bootstrap_portfolio(repository_root: Path) -> tuple[CanonicalBootstrapMission, ...]:
    """Load the immutable seed definitions; qualification never invents them."""
    portfolio: list[CanonicalBootstrapMission] = []
    for identifier in BOOTSTRAP_MISSION_SEQUENCE:
        path = repository_root / "missions" / f"{identifier}.md"
        document = path.read_text(encoding="utf-8")
        heading = document.splitlines()[0] if document else ""
        prefix = identifier + " — "
        if not heading.startswith(prefix) or "Status: APPROVED_FOR_ARCHITECTURE" not in document or "Mission Type: Portfolio Seed" not in document:
            raise ValueError(f"canonical bootstrap mission definition is invalid: {identifier}")
        portfolio.append(CanonicalBootstrapMission(identifier, heading.removeprefix(prefix).strip(), _paragraph(document, "Mission Statement"), _paragraph(document, "Business Objective"), _digest(document)))
    return tuple(portfolio)


class BootstrapQualificationBlocked(ValueError):
    """Legacy seed execution lacks an approved substantive assessment contract."""


def run_bootstrap_sequence_qualification(
    root: Path, evidence_source: EngineeringPlatformEvidenceSource, *,
    interrupt_after_host_dispatch: bool = False,
) -> BootstrapQualificationReport:
    """Read retained terminal qualification; never execute unassessed seeds.

    The evidence-source and interruption arguments retain API compatibility.
    They cannot authorize host calls or convert historical evidence to v2.
    """
    del evidence_source, interrupt_after_host_dispatch
    load_canonical_bootstrap_portfolio(Path(__file__).resolve().parents[2])
    root.mkdir(parents=True, exist_ok=True)
    runtime = RuntimeDatabase(root)
    try:
        report = runtime.runtime_evidence().bootstrap_qualification(BOOTSTRAP_MISSION_SEQUENCE)
        if report["qualified"]:
            return BootstrapQualificationReport(
                "YES", "Forge Generation 1 bootstrap complete", "IDLE", BOOTSTRAP_MISSION_SEQUENCE,
                str(runtime.path), "Normal Business → Architecture → Mission lifecycle",
            )
        raise BootstrapQualificationBlocked("LEGACY_ASSESSMENT_CONTRACT_MISSING")
    finally:
        runtime.close()
