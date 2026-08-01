"""Immutable, evidence-only records for engineering that predates Intent governance.

Historical Engineering Intents preserve repository truth without representing a
normal Engineering Intent.  They do not create missing proposals or approvals,
transition through a lifecycle, or authorize or execute work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
import re
from typing import Any


HISTORICAL_ENGINEERING_INTENT_SCHEMA_VERSION = "1.0"


class HistoricalEngineeringIntentStatus(str, Enum):
    """The single, terminal state of a historical record."""

    HISTORICAL = "HISTORICAL"


class HistoricalGovernanceStatus(str, Enum):
    """Closed status used when the historical governance record does not exist."""

    HISTORICAL_NOT_AVAILABLE = "HISTORICAL_NOT_AVAILABLE"


@dataclass(frozen=True)
class HistoricalProposal:
    """Records the absence of a proposal without fabricating one."""

    status: HistoricalGovernanceStatus = HistoricalGovernanceStatus.HISTORICAL_NOT_AVAILABLE

    def __post_init__(self) -> None:
        if self.status is not HistoricalGovernanceStatus.HISTORICAL_NOT_AVAILABLE:
            raise ValueError("historical proposal status must be HISTORICAL_NOT_AVAILABLE")

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status.value,
            "reason": "No proposal existed at the time; Forge must never fabricate one.",
        }


@dataclass(frozen=True)
class HistoricalApproval:
    """Records the absence of an approval workflow without fabricating one."""

    status: HistoricalGovernanceStatus = HistoricalGovernanceStatus.HISTORICAL_NOT_AVAILABLE

    def __post_init__(self) -> None:
        if self.status is not HistoricalGovernanceStatus.HISTORICAL_NOT_AVAILABLE:
            raise ValueError("historical approval status must be HISTORICAL_NOT_AVAILABLE")

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status.value,
            "reason": "No approval workflow existed; Forge must never fabricate historical approval.",
        }


def _validate_digest(content_digest: str, label: str) -> None:
    digest = content_digest.removeprefix("sha256:")
    if not content_digest.startswith("sha256:") or len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{label} content digest must be a sha256 digest")


@dataclass(frozen=True, order=True)
class HistoricalRepositoryEvidence:
    """A reproducible pointer to repository evidence; Forge never retrieves it."""

    repository_id: str
    revision: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.repository_id, self.revision, self.locator, self.content_digest)):
            raise ValueError("historical repository evidence identity, revision, locator, and digest are required")
        _validate_digest(self.content_digest, "historical repository evidence")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class HistoricalImplementationCommit:
    """An implementation commit observed in the repository's historical record."""

    repository_id: str
    commit_sha: str
    locator: str

    def __post_init__(self) -> None:
        if not all((self.repository_id, self.commit_sha, self.locator)):
            raise ValueError("historical implementation commit repository, sha, and locator are required")
        if re.fullmatch(r"[0-9a-f]{7,64}", self.commit_sha) is None:
            raise ValueError("historical implementation commit sha must be a lowercase Git sha")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class HistoricalImplementationReport:
    """An implementation report observed in historical repository documentation."""

    report_id: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.report_id, self.locator, self.content_digest)):
            raise ValueError("historical implementation report identity, locator, and digest are required")
        _validate_digest(self.content_digest, "historical implementation report")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, order=True)
class HistoricalBootstrapDocumentation:
    """A bootstrap document that substantiates historical reconstruction."""

    document_id: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.document_id, self.locator, self.content_digest)):
            raise ValueError("historical bootstrap documentation identity, locator, and digest are required")
        _validate_digest(self.content_digest, "historical bootstrap documentation")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalEngineeringIntent:
    """An immutable, non-executable record of pre-lifecycle engineering."""

    historical_id: str
    title: str
    objective: str
    bootstrap_milestone: str
    reconstructed_at: str
    reconstruction_rationale: str
    repository_evidence: tuple[HistoricalRepositoryEvidence, ...]
    implementation_commits: tuple[HistoricalImplementationCommit, ...] = ()
    implementation_reports: tuple[HistoricalImplementationReport, ...] = ()
    bootstrap_documentation: tuple[HistoricalBootstrapDocumentation, ...] = ()
    proposal: HistoricalProposal = field(default_factory=HistoricalProposal)
    approval: HistoricalApproval = field(default_factory=HistoricalApproval)
    status: HistoricalEngineeringIntentStatus = HistoricalEngineeringIntentStatus.HISTORICAL
    schema_version: str = HISTORICAL_ENGINEERING_INTENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != HISTORICAL_ENGINEERING_INTENT_SCHEMA_VERSION:
            raise ValueError("historical engineering intent schema version is unsupported")
        if not all((
            self.historical_id, self.title, self.objective, self.bootstrap_milestone,
            self.reconstructed_at, self.reconstruction_rationale,
        )):
            raise ValueError("historical intent identity, content, bootstrap milestone, and reconstruction metadata are required")
        try:
            reconstructed_at = datetime.fromisoformat(self.reconstructed_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("historical reconstruction timestamp must be ISO 8601") from error
        if reconstructed_at.tzinfo is None:
            raise ValueError("historical reconstruction timestamp must include a timezone")
        if self.status is not HistoricalEngineeringIntentStatus.HISTORICAL:
            raise ValueError("historical engineering intent status must be HISTORICAL")
        if not isinstance(self.proposal, HistoricalProposal) or not isinstance(self.approval, HistoricalApproval):
            raise ValueError("historical intent governance must record only historical unavailability")
        if not self.repository_evidence:
            raise ValueError("historical intent requires repository evidence")
        if not self.bootstrap_documentation:
            raise ValueError("historical intent requires bootstrap documentation")
        if not self.implementation_commits and not self.implementation_reports:
            raise ValueError("historical intent requires an implementation commit or implementation report")
        for references, reference_type, label in (
            (self.repository_evidence, HistoricalRepositoryEvidence, "repository evidence"),
            (self.implementation_commits, HistoricalImplementationCommit, "implementation commits"),
            (self.implementation_reports, HistoricalImplementationReport, "implementation reports"),
            (self.bootstrap_documentation, HistoricalBootstrapDocumentation, "bootstrap documentation"),
        ):
            if any(not isinstance(reference, reference_type) for reference in references):
                raise ValueError(f"historical intent {label} must use their declared reference type")
            if len(references) != len(set(references)):
                raise ValueError(f"historical intent {label} must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "historical_id": self.historical_id,
            "title": self.title,
            "objective": self.objective,
            "bootstrap_milestone": self.bootstrap_milestone,
            "reconstructed_at": self.reconstructed_at,
            "reconstruction_rationale": self.reconstruction_rationale,
            "repository_evidence": [item.to_dict() for item in self.repository_evidence],
            "implementation_commits": [item.to_dict() for item in self.implementation_commits],
            "implementation_reports": [item.to_dict() for item in self.implementation_reports],
            "bootstrap_documentation": [item.to_dict() for item in self.bootstrap_documentation],
            "proposal": self.proposal.to_dict(),
            "approval": self.approval.to_dict(),
            "status": self.status.value,
        }
