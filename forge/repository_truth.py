"""Immutable, declared Repository Truth inputs for Portfolio Intelligence.

Repository Truth is observed outside this contract.  The contract stores only
revision-pinned, digest-pinned evidence pointers; it never reads a repository,
interprets evidence, or derives a recommendation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

from forge.models.architecture_review import ReviewEvidence, ReviewInputKind


REPOSITORY_TRUTH_SCHEMA_VERSION = "1.0"


def _digest(document: object) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _valid_digest(value: str) -> bool:
    digest = value.removeprefix("sha256:")
    return value.startswith("sha256:") and len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)


@dataclass(frozen=True, order=True)
class RepositoryTruthEvidence:
    """One observable, bounded repository-evidence pointer.

    Evidence content remains at its source.  ``kind`` is deliberately a
    stable, machine-readable category rather than a free-form finding.
    """

    id: str
    kind: str
    revision: str
    locator: str
    content_digest: str

    def __post_init__(self) -> None:
        if not all((self.id, self.kind, self.revision, self.locator)):
            raise ValueError("repository truth evidence identity, kind, revision, and locator are required")
        if not _valid_digest(self.content_digest):
            raise ValueError("repository truth evidence content digest must be a sha256 digest")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class RepositoryTruthSnapshot:
    """A deterministic, immutable Portfolio Intelligence input.

    The snapshot is intentionally input-only: callers supply already-observed
    evidence and a repository revision.  It neither performs repository I/O
    nor records runtime state, creates reviews, or recommends Missions.
    """

    id: str
    repository_id: str
    repository_revision: str
    observed_at: str
    evidence: tuple[RepositoryTruthEvidence, ...]
    schema_version: str = REPOSITORY_TRUTH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REPOSITORY_TRUTH_SCHEMA_VERSION:
            raise ValueError("repository truth snapshot schema version is unsupported")
        if not all((self.id, self.repository_id, self.repository_revision, self.observed_at)):
            raise ValueError("repository truth snapshot identity, revision, and observation time are required")
        if not self.evidence:
            raise ValueError("repository truth snapshot requires observed evidence")
        if len(self.evidence) != len(set(self.evidence)):
            raise ValueError("repository truth snapshot evidence must be unique")
        object.__setattr__(self, "evidence", tuple(sorted(self.evidence)))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "repository_id": self.repository_id,
            "repository_revision": self.repository_revision,
            "observed_at": self.observed_at,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @property
    def content_digest(self) -> str:
        return _digest(self.to_dict())

    def as_review_evidence(self, *, locator: str) -> ReviewEvidence:
        """Expose the one bounded pointer consumed by Architecture Review."""
        if not locator:
            raise ValueError("repository truth review locator is required")
        return ReviewEvidence(
            ReviewInputKind.REPOSITORY_TRUTH,
            self.id,
            self.repository_revision,
            locator,
            self.content_digest,
        )
