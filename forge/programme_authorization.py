"""Bounded, programme-scoped owner authorization.

This module deliberately records authority through ``CanonicalGovernanceRepository``.
It does not write GitHub statuses, replace reviews, or turn a chat instruction into
qualification evidence.  Each candidate head is qualified independently.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Iterable

from forge.governance_authority import (
    CanonicalGovernanceRepository,
    GovernanceCapability,
    GovernanceDecision,
)
from forge.operator_identity import OperatorContext

_SHA = re.compile(r"^[0-9a-f]{40}$")
_PROGRAMME_KIND = "OWNER_PROGRAMME_AUTHORIZATION_V1"


@dataclass(frozen=True)
class ProgrammeAuthorization:
    """Immutable owner grant with deliberately narrow execution boundaries."""

    authorization_id: str
    programme_id: str
    owner_login: str
    owner_account_binding: str
    source_reference: str
    repositories: tuple[str, ...]
    allowed_scopes: tuple[str, ...]
    expires_at: str
    repair_attempt_limit: int = 3
    merge_method: str = "squash"

    def __post_init__(self) -> None:
        if not all((self.authorization_id, self.programme_id, self.owner_login,
                    self.owner_account_binding, self.source_reference,
                    self.repositories, self.allowed_scopes, self.expires_at)):
            raise ValueError("programme authorization requires complete provenance and boundaries")
        if self.repair_attempt_limit < 0 or self.merge_method != "squash":
            raise ValueError("only bounded repair and qualified squash merge are supported")
        _parse_time(self.expires_at)

    def document(self) -> dict[str, object]:
        value = asdict(self)
        value["repositories"] = sorted(self.repositories)
        value["allowed_scopes"] = sorted(self.allowed_scopes)
        value["kind"] = _PROGRAMME_KIND
        return value


@dataclass(frozen=True)
class CandidateQualification:
    repository: str
    pull_request: int
    head_sha: str
    base_branch: str
    changed_scopes: tuple[str, ...]
    technical_qualification_passed: bool
    ci_passed: bool
    reviews_passed: bool
    security_passed: bool
    owner_workflow_evidence: str
    owner_workflow_head_sha: str
    merge_method: str = "squash"
    mission_id: str | None = None
    action_id: str | None = None

    def __post_init__(self) -> None:
        if (self.pull_request <= 0 or not _SHA.fullmatch(self.head_sha)
                or not self.base_branch or not self.owner_workflow_evidence
                or self.owner_workflow_head_sha != self.head_sha):
            raise ValueError("candidate requires an exact head, base branch, and workflow evidence")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must be timezone aware")
    return parsed.astimezone(timezone.utc)


class ProgrammeAuthorizationGate:
    """Fail-closed policy gate for the approved autonomy programme."""

    def __init__(self, repository: CanonicalGovernanceRepository, context: OperatorContext,
                 now=lambda: datetime.now(timezone.utc)) -> None:
        self.repository, self.context, self.now = repository, context, now

    def record_authorization(self, authorization: ProgrammeAuthorization) -> str:
        return self.repository.record(GovernanceDecision(
            decision_id=authorization.authorization_id,
            subject_id=authorization.programme_id,
            subject_revision=authorization.authorization_id,
            capability=GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION,
            decision="authorized",
            scope=authorization.allowed_scopes,
            gates=("exact-head-qualification", "ci", "reviews", "security", "owner-workflow"),
            evidence=authorization.document(),
        ), self.context)

    def qualify(self, authorization_id: str, candidate: CandidateQualification) -> str:
        authorization = self._authorization(authorization_id)
        self._validate_candidate(authorization, candidate)
        return self.repository.record(GovernanceDecision(
            decision_id=f"{authorization_id}:pr-{candidate.pull_request}:{candidate.head_sha}",
            subject_id=f"{authorization.programme_id}:pr-{candidate.pull_request}",
            subject_revision=candidate.head_sha,
            capability=GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION,
            decision="qualified",
            scope=candidate.changed_scopes,
            gates=("exact-head-qualification", "ci", "reviews", "security", "owner-workflow", "squash"),
            predecessor_digest=self._decision_digest(authorization_id),
            evidence={"kind": "EXACT_HEAD_QUALIFICATION_V1", **asdict(candidate),
                      "authorization_id": authorization_id},
        ), self.context)

    def record_repair_attempt(self, authorization_id: str, candidate: CandidateQualification) -> str:
        authorization = self._authorization(authorization_id)
        self._validate_candidate(authorization, candidate, require_passes=False)
        if not candidate.mission_id or not candidate.action_id:
            raise PermissionError("repair authorization requires the Forge Mission and Engineering Action lineage")
        existing = self._repair_attempts(authorization_id, candidate.mission_id, candidate.action_id)
        if existing >= authorization.repair_attempt_limit:
            raise PermissionError("bounded repair budget exhausted for this Engineering Action lineage")
        attempt = existing + 1
        return self.repository.record(GovernanceDecision(
            decision_id=f"{authorization_id}:repair:{candidate.mission_id}:{candidate.action_id}:{attempt}",
            subject_id=f"{authorization.programme_id}:repair:{candidate.mission_id}:{candidate.action_id}:attempt-{attempt}",
            subject_revision=candidate.head_sha,
            capability=GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION,
            decision="repair-authorized",
            scope=candidate.changed_scopes,
            gates=("same-approved-scope", "exact-head"),
            predecessor_digest=self._decision_digest(authorization_id),
            evidence={"kind": "BOUNDED_ACTION_REPAIR_ATTEMPT_V2", "authorization_id": authorization_id,
                      "mission_id": candidate.mission_id, "action_id": candidate.action_id,
                      "pull_request": candidate.pull_request, "head_sha": candidate.head_sha,
                      "attempt": attempt},
        ), self.context)

    def _authorization(self, authorization_id: str) -> ProgrammeAuthorization:
        record = self.repository.decision(authorization_id)
        if record.get("capability") != GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION.value or record.get("decision") != "authorized":
            raise PermissionError("owner programme authorization is absent")
        evidence = record.get("evidence")
        if not isinstance(evidence, dict) or evidence.get("kind") != _PROGRAMME_KIND:
            raise PermissionError("owner programme authorization provenance is invalid")
        return ProgrammeAuthorization(**{key: evidence[key] for key in ProgrammeAuthorization.__dataclass_fields__})

    def _validate_candidate(self, authorization: ProgrammeAuthorization, candidate: CandidateQualification,
                            *, require_passes: bool = True) -> None:
        if self.now() > _parse_time(authorization.expires_at):
            raise PermissionError("owner programme authorization has expired")
        if candidate.repository not in authorization.repositories:
            raise PermissionError("repository is outside owner-authorized programme scope")
        if not set(candidate.changed_scopes).issubset(authorization.allowed_scopes):
            raise PermissionError("candidate diff expands the authorized scope")
        if candidate.merge_method != authorization.merge_method:
            raise PermissionError("only qualified squash merge is allowed")
        if require_passes and not all((candidate.technical_qualification_passed, candidate.ci_passed,
                                       candidate.reviews_passed, candidate.security_passed)):
            raise PermissionError("candidate has not passed all required qualification gates")

    def _decision_digest(self, decision_id: str) -> str:
        row = self.repository.database._connection.execute(
            "SELECT digest FROM governance_decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            raise PermissionError("authorization evidence is absent")
        return row["digest"]

    def _repair_attempts(self, authorization_id: str, mission_id: str, action_id: str) -> int:
        rows = self.repository.database._connection.execute(
            "SELECT document FROM governance_decisions WHERE capability = ?",
            (GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION.value,),
        ).fetchall()
        import json
        return sum(
            1 for row in rows
            if (lambda evidence: evidence.get("authorization_id") == authorization_id and (
                (evidence.get("kind") == "BOUNDED_ACTION_REPAIR_ATTEMPT_V2"
                 and evidence.get("mission_id") == mission_id and evidence.get("action_id") == action_id)
                # V1 had no Action identity. Count it conservatively rather
                # than silently resetting a pre-existing programme budget.
                or evidence.get("kind") == "BOUNDED_REPAIR_ATTEMPT_V1"
            ))(json.loads(row["document"]).get("evidence", {}))
        )
