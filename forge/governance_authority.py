"""Canonical, installation-bound persistence for bounded governance decisions.

This is the supported application boundary for the three governance
capabilities. It is not IAM and grants neither planning nor execution authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from forge.operator_identity import InstallationOperatorService, OperatorContext
from forge.runtime.database import RuntimeDatabase, _timestamp


class GovernanceCapability(str, Enum):
    BUSINESS_APPROVAL = "BUSINESS_APPROVAL"
    ARCHITECTURE_APPROVAL = "ARCHITECTURE_APPROVAL"
    SECURITY_APPROVAL = "SECURITY_APPROVAL"


@dataclass(frozen=True)
class GovernanceDecision:
    decision_id: str
    subject_id: str
    subject_revision: str
    capability: GovernanceCapability
    decision: str
    scope: tuple[str, ...]
    gates: tuple[str, ...]
    predecessor_digest: str | None = None

    def document(self, installation_id: str, operator_id: str, occurred_at: str) -> dict[str, object]:
        return {
            **asdict(self), "capability": self.capability.value,
            "scope": list(sorted(self.scope)), "gates": list(sorted(self.gates)),
            "installation_id": installation_id, "operator_id": operator_id, "occurred_at": occurred_at,
        }


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class _LocalInstallationBootstrapAuthority:
    """Unexported local-installation bootstrap capability; not an OperatorContext."""
    def __init__(self, database: RuntimeDatabase) -> None:
        self._database = database


class CanonicalGovernanceRepository:
    """The only supported Forge application write path for governance evidence."""

    def __init__(self, database: RuntimeDatabase, operators: InstallationOperatorService) -> None:
        resolved = RuntimeDatabase(database.repository_root)
        try:
            if resolved.path.resolve() != database.path.resolve():
                raise ValueError("governance services require the resolved canonical Runtime Instance")
        finally:
            resolved.close()
        self.database, self.operators = database, operators

    @classmethod
    def _for_test(cls, database: RuntimeDatabase, operators: InstallationOperatorService) -> "CanonicalGovernanceRepository":
        """Explicit isolated-fixture seam; not a supported production constructor."""
        instance = cls.__new__(cls)
        instance.database, instance.operators = database, operators
        return instance

    @classmethod
    def open_canonical(cls, repository_root: str, identity_resolver: object) -> "CanonicalGovernanceRepository":
        database = RuntimeDatabase(repository_root)
        return cls(database, InstallationOperatorService(database, identity_resolver))

    @staticmethod
    def _operator_id(context: OperatorContext) -> str:
        return sha256(context.generated_uid.encode()).hexdigest()[:16]

    def _bootstrap_authority(self) -> _LocalInstallationBootstrapAuthority:
        return _LocalInstallationBootstrapAuthority(self.database)

    def bootstrap_grant(self, authority: _LocalInstallationBootstrapAuthority, context: OperatorContext,
                        capabilities: tuple[GovernanceCapability, ...]) -> None:
        if authority._database is not self.database:
            raise PermissionError("local installation bootstrap authority is required")
        if not self.operators.authorize(context):
            raise PermissionError("trusted operator context is required")
        if not capabilities or len(set(capabilities)) != len(capabilities):
            raise ValueError("explicit unique capabilities required")
        for capability in capabilities:
            occurred_at = _timestamp()
            provenance = {"kind": "LOCAL_INSTALLATION_BOOTSTRAP_V1", "installation_id": context.installation_id,
                          "operator_id": self._operator_id(context), "capability": capability.value}
            grant_digest = _digest(provenance)
            self.database._persist_governance(
                "INSERT INTO governance_capability_grants VALUES (?, ?, ?, ?, ?, ?, ?)",
                (grant_digest, context.installation_id, self._operator_id(context), capability.value,
                 json.dumps(provenance, sort_keys=True, separators=(",", ":")), grant_digest, occurred_at),
            )
            self.database._persist_governance(
                "INSERT INTO governance_authority VALUES (?, ?, ?, ?, ?)",
                (context.installation_id, self._operator_id(context), capability.value, 1, occurred_at),
            )

    def record(self, decision: GovernanceDecision, context: OperatorContext) -> str:
        if not self.operators.authorize(context):
            raise PermissionError("trusted operator context is required")
        operator_id = self._operator_id(context)
        authorized = self.database._connection.execute(
            "SELECT 1 FROM governance_authority WHERE installation_id = ? AND operator_id = ? AND capability = ?",
            (context.installation_id, operator_id, decision.capability.value),
        ).fetchone()
        if authorized is None:
            raise PermissionError("required governance capability is absent")
        document = decision.document(context.installation_id, operator_id, _timestamp())
        digest = _digest(document)
        self.database._persist_governance(
            "INSERT INTO governance_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (decision.decision_id, context.installation_id, decision.subject_id, decision.subject_revision,
             decision.capability.value, decision.predecessor_digest,
             json.dumps(document, sort_keys=True, separators=(",", ":")), digest, document["occurred_at"]),
        )
        return digest

    def decision(self, decision_id: str) -> dict[str, object]:
        row = self.database._connection.execute(
            "SELECT document, digest FROM governance_decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown canonical governance decision")
        document = json.loads(row["document"])
        if _digest(document) != row["digest"]:
            raise ValueError("governance decision digest mismatch")
        return document


@dataclass(frozen=True)
class ArchitecturePlanningEvidence:
    """Typed, machine-verifiable planning constraints and provenance."""

    scope: tuple[str, ...]
    write_scopes: tuple[str, ...]
    non_goals: tuple[str, ...]
    risk_inputs: tuple[str, ...]
    human_gates: tuple[str, ...]
    dependencies: tuple[str, ...]
    context_input_bound: int
    context_output_bound: int
    provenance_revision: str

    def __post_init__(self) -> None:
        if not all((self.scope, self.write_scopes, self.non_goals, self.risk_inputs, self.human_gates,
                    self.dependencies, self.provenance_revision, self.context_input_bound > 0,
                    self.context_output_bound > 0)):
            raise ValueError("planning evidence requires complete typed bounds and provenance")

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        for key in ("scope", "write_scopes", "non_goals", "risk_inputs", "human_gates", "dependencies"):
            value[key] = list(sorted(value[key]))
        return value


@dataclass(frozen=True)
class MissionPlanningEvidenceEnvelope:
    """Immutable digest-pinned Business + Architecture evidence for Intake."""

    installation_id: str
    subject_id: str
    subject_revision: str
    business_decision_id: str
    architecture_decision_id: str
    planning: ArchitecturePlanningEvidence
    digest: str

    @classmethod
    def compose(cls, repository: CanonicalGovernanceRepository, *, subject_id: str, subject_revision: str,
                business_decision_id: str, architecture_decision_id: str,
                planning: ArchitecturePlanningEvidence) -> "MissionPlanningEvidenceEnvelope":
        business, architecture = repository.decision(business_decision_id), repository.decision(architecture_decision_id)
        installation_id = repository.operators.installation_id()
        for decision, capability in ((business, GovernanceCapability.BUSINESS_APPROVAL),
                                     (architecture, GovernanceCapability.ARCHITECTURE_APPROVAL)):
            if (decision["installation_id"] != installation_id or decision["subject_id"] != subject_id
                    or decision["subject_revision"] != subject_revision
                    or decision["capability"] != capability.value or decision["decision"] != "approved"):
                raise ValueError("approval envelope has invalid, stale, conflicting, or cross-installation lineage")
        if planning.provenance_revision != subject_revision:
            raise ValueError("planning evidence revision is stale")
        value = {"installation_id": installation_id, "subject_id": subject_id, "subject_revision": subject_revision,
                 "business_decision_id": business_decision_id, "architecture_decision_id": architecture_decision_id,
                 "planning": planning.to_dict()}
        return cls(installation_id, subject_id, subject_revision, business_decision_id,
                   architecture_decision_id, planning, _digest(value))

    def validate(self, repository: CanonicalGovernanceRepository) -> "MissionPlanningEvidenceEnvelope":
        rebuilt = self.compose(repository, subject_id=self.subject_id, subject_revision=self.subject_revision,
                               business_decision_id=self.business_decision_id,
                               architecture_decision_id=self.architecture_decision_id, planning=self.planning)
        if rebuilt.digest != self.digest:
            raise ValueError("approval/planning envelope digest mismatch")
        return rebuilt


@dataclass(frozen=True)
class CanonicalBusinessWorkspace:
    """Runtime-bound Business approval service; it accepts no database path."""

    repository: CanonicalGovernanceRepository
    context: OperatorContext

    def approve(self, *, decision_id: str, candidate_id: str, revision: str, scope: tuple[str, ...], gates: tuple[str, ...]) -> str:
        return self.repository.record(
            GovernanceDecision(decision_id, candidate_id, revision, GovernanceCapability.BUSINESS_APPROVAL,
                               "approved", scope, gates), self.context)


@dataclass(frozen=True)
class CanonicalArchitectureWorkspace:
    """Runtime-bound Architecture approval service; it accepts no database path."""

    repository: CanonicalGovernanceRepository
    context: OperatorContext

    def approve(self, *, decision_id: str, candidate_id: str, revision: str,
                planning: ArchitecturePlanningEvidence) -> str:
        return self.repository.record(
            GovernanceDecision(decision_id, candidate_id, revision, GovernanceCapability.ARCHITECTURE_APPROVAL,
                               "approved", planning.scope, planning.human_gates), self.context)
