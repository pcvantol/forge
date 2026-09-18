"""Forge-observed immutable facts, separate from host/provider claims."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any


def canonical_digest(value: object) -> str:
    return 'sha256:' + sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                       ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class CriterionObservation:
    mission_id: str
    mission_digest: str
    criterion_id: str
    contract_digest: str
    requirement_id: str
    receipt_id: str
    action_id: str
    report_id: str
    repository_revision: str
    repository_evidence_digest: str
    source_kind: str
    source_identity: str
    artifact_path: str
    content_digest: str | None
    observed_json: str | None
    result: str
    reason: str
    requirement_digest: str = ''
    json_pointer: str = ''
    candidate_revision: str | None = None
    schema_version: str = '1.0'

    def __post_init__(self) -> None:
        if self.schema_version != '1.0' or self.source_kind != 'repository_json':
            raise ValueError('unsupported criterion observation source')
        if not all((self.mission_id, self.criterion_id, self.requirement_id, self.receipt_id,
                    self.action_id, self.report_id, self.repository_revision, self.source_identity,
                    self.artifact_path, self.reason)):
            raise ValueError('criterion observation requires complete provenance')
        for value in (self.mission_digest, self.contract_digest, self.requirement_digest, self.repository_evidence_digest,
                      self.content_digest):
            if value is not None and (not value.startswith('sha256:') or len(value) != 71
                    or any(c not in '0123456789abcdef' for c in value[7:])):
                raise ValueError('invalid criterion observation digest')
        if self.candidate_revision is not None and (len(self.candidate_revision) != 40
                or any(c not in '0123456789abcdef' for c in self.candidate_revision)):
            raise ValueError('invalid observation candidate revision')
        if self.result not in {'PASS', 'FAIL', 'UNAVAILABLE'}:
            raise ValueError('invalid criterion observation result')
        if self.result != 'UNAVAILABLE' and self.content_digest is None:
            raise ValueError('observed criterion facts require content identity')
        if self.observed_json is not None:
            value = json.loads(self.observed_json)
            if json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                          allow_nan=False) != self.observed_json:
                raise ValueError('observed value must be canonical JSON')

    @property
    def id(self) -> str:
        return 'criterion-observation:' + canonical_digest(asdict(self))[7:]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CriterionObservation:
        return cls(**value)
