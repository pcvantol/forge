"""Durable replay boundary for installed Action Derivation.

The provider remains an untrusted, externally side-effecting boundary.  This
module creates a durable attempt before crossing it and stores the typed result
before deterministic validation or Mission-state materialization begins.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping
from uuid import uuid4

from forge.governance_authority import GovernanceCapability, GovernanceDecision
from forge.models.action_derivation import (
    DerivationPolicy,
    DerivedActionProposal,
    GovernanceRefinementRequired,
    MissionGapBinding,
    MissionGapClassification,
    PlanningSnapshot,
    ProposalProvenance,
    ProviderInvocationEvidence,
    ProviderSideEffectState,
)
from forge.models.mission_planner import MissionPlannerInput
from forge.planner.openai_responses import ProviderSubmissionAmbiguous
from forge.planner.provider_adapter import ProviderDerivationResponse
from forge.runtime.database import RuntimeDatabase, RuntimeDatabaseError, RuntimeIntegrityError
from forge.planner.action_derivation import (
    ActionDerivationValidator,
    DerivationResult,
    ProposalValidationError,
    deterministic_validation_failure_code,
    planner_input_from_derivation,
)
from forge.planner.engine import MissionPlanner


DURABLE_RESULT_SCHEMA_VERSION = "1.0"
_MUTABLE_ATTEMPT_FIELDS = frozenset((
    "lifecycle", "processing_phase", "error_code", "exception_type", "error_location",
    "result_kind", "provider_result_digest", "result_payload_digest", "result_metadata_digest",
    "materialized_at", "materialization_digest", "attempt_metadata_digest",
))


class DurableDerivationPhase(str, Enum):
    ATTEMPT_RECORDED = "ATTEMPT_RECORDED"
    GENERATION_IN_PROGRESS = "GENERATION_IN_PROGRESS"
    GENERATION_MAY_HAVE_HAPPENED = "GENERATION_MAY_HAVE_HAPPENED"
    GENERATION_NOT_STARTED = "GENERATION_NOT_STARTED"
    RESULT_AVAILABLE = "RESULT_AVAILABLE"
    VALIDATION_IN_PROGRESS = "VALIDATION_IN_PROGRESS"
    GOVERNANCE_REFINEMENT = "GOVERNANCE_REFINEMENT"
    DETERMINISTIC_REJECTION = "DETERMINISTIC_REJECTION"
    VALIDATED = "VALIDATED"
    MATERIALIZATION_FAILED = "MATERIALIZATION_FAILED"
    MATERIALIZED = "MATERIALIZED"
    CONFIRMED_RESULT_UNAVAILABLE = "CONFIRMED_RESULT_UNAVAILABLE"


class DurableDerivationBlocked(RuntimeDatabaseError):
    """A recorded provider boundary cannot safely make a new model call."""

    def __init__(self, code: str, derivation_id: str) -> None:
        super().__init__(code)
        self.code, self.derivation_id = code, derivation_id


class DurableResultPersistenceError(RuntimeDatabaseError):
    """The provider returned, but its typed result could not be retained.

    This is intentionally separate from a transport error: callers must not
    infer that the external process did not run merely because the local
    receipt write failed.
    """


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _replay_boundary_digest(snapshot: PlanningSnapshot) -> str:
    """Bind replay to semantic planning facts, not our own status bookkeeping.

    A ``CREATED -> BLOCKED`` transition written solely because a provider
    receipt was unavailable changes Mission revision and the synthetic
    MISSION_STATE evidence.  It must not make an explicitly authorized next
    attempt impossible.  Repository truth, approvals/capabilities, criteria,
    execution evidence and the approved Mission remain in this binding.
    """
    return _digest({
        "mission_id": snapshot.mission_id,
        "mission_digest": snapshot.mission_digest,
        "criteria": [item.to_dict() for item in snapshot.criteria],
        "evidence": [item.to_dict() for item in snapshot.evidence
                     if item.kind.value != "mission_state"],
    })


def _evidence_document(value: ProviderInvocationEvidence) -> dict[str, object]:
    result = asdict(value)
    result["side_effect_state"] = value.side_effect_state.value
    return result


def _proposal_document(value: DerivedActionProposal) -> dict[str, object]:
    return {
        "logical_action_id": value.logical_action_id,
        "scope": value.scope,
        "objective": value.objective,
        "dependencies": list(value.dependencies),
        "write_scopes": list(value.write_scopes),
        "expected_evidence": list(value.expected_evidence),
        "validation_strategy": list(value.validation_strategy),
        "priority": value.priority,
        "postponed": value.postponed,
        "human_gates": list(value.human_gates),
        "risk_inputs": list(value.risk_inputs),
        "provenance": asdict(value.provenance),
        "mission_gap": None if value.mission_gap is None else value.mission_gap.to_dict(),
    }


def _refinement_document(value: GovernanceRefinementRequired) -> dict[str, object]:
    return {
        "triggering_evidence": list(value.triggering_evidence),
        "missing_authority": value.missing_authority,
        "affected_scope": value.affected_scope,
        "impact_classification": value.impact_classification,
        "reason": value.reason,
    }


def serialize_provider_response(response: ProviderDerivationResponse, *, derivation_id: str,
                                stored_at: str) -> dict[str, object]:
    """Create the bounded persisted representation, never the raw CLI output."""
    evidence = _evidence_document(response.evidence)
    # The Codex adapter represents a schema/parse failure as its existing
    # governed refinement shape so it can return bounded evidence.  Preserve
    # the adapter's explicit diagnostic instead of misclassifying that
    # contract failure as a substantive governance refinement.
    contract_invalid = response.evidence.status == "contract_invalid"
    if response.proposals is not None:
        kind = "PROPOSALS"
        payload: dict[str, object] = {
            "schema_version": DURABLE_RESULT_SCHEMA_VERSION,
            "evidence": evidence,
            "proposals": [_proposal_document(item) for item in response.proposals],
        }
    else:
        assert response.governance_refinement is not None
        kind = "CONTRACT_INVALID" if contract_invalid else "GOVERNANCE_REFINEMENT"
        payload = {
            "schema_version": DURABLE_RESULT_SCHEMA_VERSION,
            "evidence": evidence,
            "governance_refinement": _refinement_document(response.governance_refinement),
        }
    payload_digest = _digest(payload)
    document: dict[str, object] = {
        "derivation_id": derivation_id,
        "result_kind": kind,
        "result_digest": response.evidence.result_digest,
        "payload_digest": payload_digest,
        "stored_at": stored_at,
        "derivation_request_digest": response.evidence.request_digest,
        "payload": payload,
    }
    # The adapter must be explicit about the raw structured response digest.
    if not isinstance(document["result_digest"], str) or not document["result_digest"]:
        raise RuntimeDatabaseError("confirmed provider result lacks its result digest")
    document["metadata_digest"] = _digest({key: value for key, value in document.items() if key != "payload"})
    return document


def _proposal_from_document(document: Mapping[str, object]) -> DerivedActionProposal:
    try:
        provenance = document["provenance"]
        if not isinstance(provenance, Mapping):
            raise ValueError("proposal provenance is malformed")
        gap_document = document.get("mission_gap")
        gap = None
        if gap_document is not None:
            if not isinstance(gap_document, Mapping):
                raise ValueError("proposal mission gap is malformed")
            gap = MissionGapBinding(
                MissionGapClassification(str(gap_document["classification"])),
                tuple(str(item) for item in gap_document["criterion_ids"]),
                tuple(str(item) for item in gap_document["triggering_evidence_refs"]),
                str(gap_document["planning_snapshot_digest"]), str(gap_document["causal_objective"]),
                tuple(str(item) for item in gap_document.get("mission_caused_by_action_ids", ())),
            )
        return DerivedActionProposal(
            str(document["logical_action_id"]), str(document["scope"]), str(document["objective"]),
            tuple(str(item) for item in document["dependencies"]),
            tuple(str(item) for item in document["write_scopes"]),
            tuple(str(item) for item in document["expected_evidence"]),
            tuple(str(item) for item in document["validation_strategy"]), int(document["priority"]),
            bool(document["postponed"]), tuple(str(item) for item in document["human_gates"]),
            tuple(str(item) for item in document["risk_inputs"]),
            ProposalProvenance(
                str(provenance["derivation_id"]), str(provenance["planning_snapshot_id"]),
                str(provenance["planning_snapshot_digest"]), str(provenance["implementation_version"]),
                str(provenance["provider_id"]),
                None if provenance.get("provider_model") is None else str(provenance["provider_model"]),
                tuple(str(item) for item in provenance["source_evidence_refs"]),
            ), gap,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeDatabaseError("durable action derivation proposal payload is malformed") from error


def deserialize_provider_response(document: Mapping[str, object]) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired:
    """Rehydrate only an integrity-checked result for deterministic replay."""
    payload = document.get("payload")
    if not isinstance(payload, Mapping) or payload.get("schema_version") != DURABLE_RESULT_SCHEMA_VERSION:
        raise RuntimeDatabaseError("durable action derivation result schema is unsupported")
    kind = document.get("result_kind")
    if kind == "PROPOSALS":
        proposals = payload.get("proposals")
        if not isinstance(proposals, list) or not proposals:
            raise RuntimeDatabaseError("durable action derivation proposals are malformed")
        if not all(isinstance(item, Mapping) for item in proposals):
            raise RuntimeDatabaseError("durable action derivation proposals are malformed")
        return tuple(_proposal_from_document(item) for item in proposals)
    if kind == "GOVERNANCE_REFINEMENT":
        value = payload.get("governance_refinement")
        if not isinstance(value, Mapping):
            raise RuntimeDatabaseError("durable action derivation governance refinement is malformed")
        try:
            return GovernanceRefinementRequired(
                tuple(str(item) for item in value["triggering_evidence"]), str(value["missing_authority"]),
                str(value["affected_scope"]), str(value["impact_classification"]), str(value["reason"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeDatabaseError("durable action derivation governance refinement is malformed") from error
    raise RuntimeDatabaseError("durable action derivation result kind is unsupported")


class DurableActionDerivationCoordinator:
    """One installed-runtime coordinator for claim, durable receipt and replay."""

    def __init__(self, database: RuntimeDatabase, provider: object, *, clock=_now) -> None:
        self.database, self.provider, self.clock = database, provider, clock
        self._last_derivation_id: str | None = None

    @property
    def last_derivation_id(self) -> str:
        if self._last_derivation_id is None:
            raise RuntimeDatabaseError("durable action derivation has no current attempt")
        return self._last_derivation_id

    def derive_with_planning_input(
        self, snapshot: PlanningSnapshot, planning_input: MissionPlannerInput, policy: DerivationPolicy,
    ) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired:
        prepare = getattr(self.provider, "prepare_durable_attempt", None)
        derive = getattr(self.provider, "derive_with_planning_input", None)
        if not callable(prepare) or not callable(derive):
            raise RuntimeDatabaseError("installed provider does not support durable Action-Derivation")
        candidate_id = "codex-derivation-" + str(uuid4())
        specification = prepare(snapshot, planning_input, policy, candidate_id)
        if not isinstance(specification, Mapping):
            raise RuntimeDatabaseError("installed provider produced an invalid durable attempt specification")
        attempt = self._attempt_document(specification, candidate_id, snapshot, planning_input)
        legacy_attempts = self.database.legacy_action_derivation_reconciliation(
            snapshot.mission_id, snapshot.digest,
        )
        if legacy_attempts:
            self._last_derivation_id = str(legacy_attempts[0]["derivation_id"])
            raise DurableDerivationBlocked("LEGACY_ATTEMPT_RECONCILIATION_REQUIRED", self._last_derivation_id)
        if not self.database.durable_action_derivation_readback(snapshot.mission_id):
            legacy = self.database.legacy_confirmed_result_unavailable(
                snapshot.mission_id, snapshot.digest, str(specification.get("provider_id") or ""),
            )
            if legacy is not None:
                self._last_derivation_id = str(legacy["audit_id"])
                raise DurableDerivationBlocked("LEGACY_CONFIRMED_RESULT_UNAVAILABLE", self._last_derivation_id)
        persisted, claimed = self.database.begin_durable_action_derivation_attempt(attempt)
        derivation_id = str(persisted["derivation_id"])
        self._last_derivation_id = derivation_id
        if not claimed:
            if (persisted.get("provider_configuration") != attempt.get("provider_configuration")
                    or persisted.get("provider_id") != attempt.get("provider_id")
                    or persisted.get("provider_configuration_revision") != attempt.get("provider_configuration_revision")):
                raise DurableDerivationBlocked("CURRENT_PROVIDER_AUTHORITY_CHANGED", derivation_id)
            return self._replay_or_block(persisted)
        self.database.advance_durable_action_derivation(
            derivation_id, lifecycle="PROVIDER_RUNNING", processing_phase=DurableDerivationPhase.GENERATION_IN_PROGRESS.value,
        )
        return self._invoke_claimed_attempt(
            snapshot, planning_input, policy, derivation_id, attempt_authority_id=None,
            attempt_specification=specification,
        )

    def _invoke_claimed_attempt(
        self, snapshot: PlanningSnapshot, planning_input: MissionPlannerInput, policy: DerivationPolicy,
        derivation_id: str, *, attempt_authority_id: str | None,
        attempt_specification: Mapping[str, object],
    ) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired:
        derive = getattr(self.provider, "derive_with_planning_input", None)
        if not callable(derive):
            raise RuntimeDatabaseError("installed provider does not support durable Action-Derivation")
        attempt = self.database.durable_action_derivation_attempt(derivation_id)
        try:
            derive(
                snapshot, planning_input, policy, derivation_id=derivation_id,
                attempt_authority_id=attempt_authority_id,
                durable_attempt_specification=attempt_specification,
                durable_result_sink=lambda response: self._store_result(
                    derivation_id, attempt, response,
                ),
            )
        except ProviderSubmissionAmbiguous as error:
            self.database.advance_durable_action_derivation(
                derivation_id, lifecycle="FAILED", processing_phase=DurableDerivationPhase.GENERATION_MAY_HAVE_HAPPENED.value,
                error_code="GENERATION_MAY_HAVE_HAPPENED", exception_type=type(error).__name__,
                location="forge.planner.codex_cli_session.invoke",
            )
            raise DurableDerivationBlocked("GENERATION_MAY_HAVE_HAPPENED", derivation_id) from error
        except DurableResultPersistenceError as error:
            self.database.advance_durable_action_derivation(
                derivation_id, lifecycle="FAILED",
                processing_phase=DurableDerivationPhase.CONFIRMED_RESULT_UNAVAILABLE.value,
                error_code="RESULT_PERSISTENCE_FAILED", exception_type=type(error).__name__,
                location="forge.planner.durable_derivation.DurableActionDerivationCoordinator._store_result",
            )
            raise DurableDerivationBlocked("CONFIRMED_RESULT_NOT_DURABLE", derivation_id) from error
        except Exception as error:
            # The typed receipt may already have committed when a caller-side
            # acknowledgement fails.  It is authoritative over that local
            # exception and must be replayed instead of labelled as a second
            # uncertain provider call.
            try:
                persisted_result = self.database.durable_action_derivation_result(derivation_id)
            except RuntimeDatabaseError:
                persisted_result = None
            if persisted_result is not None:
                return self._deserialize_or_reject_contract(
                    derivation_id, persisted_result, record_rejection=True,
                )
            # A local pre-spawn rejection is the sole case that proves no
            # provider process was started.  Every other unclassified boundary
            # failure remains ambiguous and blocks automatic regeneration.
            code = "GENERATION_NOT_STARTED" if type(error).__name__ == "CodexCliInvocationRejected" else "GENERATION_MAY_HAVE_HAPPENED"
            self.database.advance_durable_action_derivation(
                derivation_id, lifecycle="FAILED", processing_phase=(
                    DurableDerivationPhase.GENERATION_NOT_STARTED.value if code == "GENERATION_NOT_STARTED"
                    else DurableDerivationPhase.GENERATION_MAY_HAVE_HAPPENED.value
                ), error_code=code, exception_type=type(error).__name__,
                location="forge.planner.codex_cli_session.invoke",
            )
            raise DurableDerivationBlocked(code, derivation_id) from error
        try:
            persisted_result = self.database.durable_action_derivation_result(derivation_id)
        except RuntimeDatabaseError as error:
            # A typed provider return without the committed sink record must
            # never become a transient success or trigger a fresh generation.
            self.database.advance_durable_action_derivation(
                derivation_id, lifecycle="FAILED", processing_phase=DurableDerivationPhase.CONFIRMED_RESULT_UNAVAILABLE.value,
                error_code="CONFIRMED_RESULT_NOT_DURABLE", exception_type=type(error).__name__,
                location="forge.planner.durable_derivation.derive_with_planning_input",
            )
            raise DurableDerivationBlocked("CONFIRMED_RESULT_NOT_DURABLE", derivation_id) from error
        return self._deserialize_or_reject_contract(derivation_id, persisted_result, record_rejection=True)

    def _attempt_document(self, specification: Mapping[str, object], derivation_id: str,
                          snapshot: PlanningSnapshot, planning_input: MissionPlannerInput) -> dict[str, object]:
        required = ("provider_id", "provider_configuration_revision", "provider_policy_digest",
                    "generation_request_digest", "derivation_request_digest", "adapter_version")
        if any(not isinstance(specification.get(field), str) or not specification[field] for field in required):
            raise RuntimeDatabaseError("durable attempt specification lacks provider provenance")
        document: dict[str, object] = {
            "schema_version": DURABLE_RESULT_SCHEMA_VERSION,
            "derivation_id": derivation_id,
            "mission_id": snapshot.mission_id,
            "mission_revision": snapshot.mission_revision,
            "snapshot_digest": snapshot.digest,
            "replay_boundary_digest": _replay_boundary_digest(snapshot),
            "contract_version": DURABLE_RESULT_SCHEMA_VERSION,
            "provider_configuration": specification["provider_policy_digest"],
            "provider_id": specification["provider_id"],
            "provider_model": specification.get("provider_model"),
            "adapter_version": specification["adapter_version"],
            "provider_configuration_revision": specification["provider_configuration_revision"],
            "effective_policy_digest": specification["provider_policy_digest"],
            "generation_request_digest": specification["generation_request_digest"],
            "derivation_request_digest": specification["derivation_request_digest"],
            "processing_phase": DurableDerivationPhase.ATTEMPT_RECORDED.value,
            "lifecycle": "DERIVATION_REQUESTED",
            "runtime_id": self.database.runtime_identity.runtime_id,
            "installation_id": self.database.metadata.get("installation_id"),
            "planning_snapshot_id": snapshot.id,
            "planning_input_mission_revision": planning_input.mission_state.revision,
            "created_at": self.clock(),
        }
        if not isinstance(document["installation_id"], str) or not document["installation_id"]:
            raise RuntimeDatabaseError("durable action derivation requires an installed runtime")
        metadata = {key: value for key, value in document.items()
                    if key not in _MUTABLE_ATTEMPT_FIELDS}
        document["attempt_metadata_digest"] = _digest(metadata)
        return document

    def _store_result(self, derivation_id: str, attempt: Mapping[str, object], response: object) -> None:
        if not isinstance(response, ProviderDerivationResponse):
            raise DurableResultPersistenceError("durable action derivation result sink received an invalid response")
        try:
            document = serialize_provider_response(response, derivation_id=derivation_id, stored_at=self.clock())
            document.update({
                "attempt_metadata_digest": attempt["attempt_metadata_digest"],
                "provider_id": attempt["provider_id"],
                "provider_model": attempt.get("provider_model"),
                "adapter_version": attempt["adapter_version"],
                "provider_configuration_revision": attempt["provider_configuration_revision"],
                "effective_policy_digest": attempt["effective_policy_digest"],
                "generation_request_digest": attempt["generation_request_digest"],
            })
            document["metadata_digest"] = _digest({
                key: value for key, value in document.items() if key != "payload"
                and key != "metadata_digest"
            })
            self.database.store_durable_action_derivation_result(document)
        except RuntimeDatabaseError as error:
            raise DurableResultPersistenceError("durable action derivation result could not be stored") from error

    def _deserialize_or_reject_contract(
        self, derivation_id: str, result: Mapping[str, object], *, record_rejection: bool,
    ) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired:
        if result.get("result_kind") == "CONTRACT_INVALID":
            # Keep the typed, bounded receipt for audit/readback, but do not
            # turn a parsing failure into a governance decision.
            if record_rejection:
                self.database.advance_durable_action_derivation(
                    derivation_id, lifecycle="VALIDATION_RUNNING",
                    processing_phase=DurableDerivationPhase.VALIDATION_IN_PROGRESS.value,
                )
                self.database.advance_durable_action_derivation(
                    derivation_id, lifecycle="FAILED",
                    processing_phase=DurableDerivationPhase.DETERMINISTIC_REJECTION.value,
                    error_code="PROVIDER_CONTRACT_INVALID", exception_type="ProviderContractError",
                    location="forge.planner.codex_cli_session._parse_response",
                )
            raise DurableDerivationBlocked("PROVIDER_CONTRACT_INVALID", derivation_id)
        return deserialize_provider_response(result)

    def _replay_or_block(self, attempt: Mapping[str, object]) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired:
        derivation_id = str(attempt["derivation_id"])
        phase = str(attempt.get("processing_phase") or "UNKNOWN")
        if phase == DurableDerivationPhase.DETERMINISTIC_REJECTION.value:
            result = self.database.durable_action_derivation_result(derivation_id)
            if result.get("result_kind") == "CONTRACT_INVALID":
                return self._deserialize_or_reject_contract(derivation_id, result, record_rejection=False)
            raise DurableDerivationBlocked("DETERMINISTIC_REJECTION", derivation_id)
        if phase == DurableDerivationPhase.GOVERNANCE_REFINEMENT.value:
            # The result still exists and was already classified.  Replaying
            # it must let the outer loop record BLOCKED without attempting a
            # terminal lifecycle transition again.
            self.database.durable_action_derivation_result(derivation_id)
            raise DurableDerivationBlocked("GOVERNANCE_REFINEMENT_REQUIRED", derivation_id)
        if phase == DurableDerivationPhase.MATERIALIZED.value:
            raise DurableDerivationBlocked("MATERIALIZATION_ALREADY_COMMITTED", derivation_id)
        try:
            return self._deserialize_or_reject_contract(
                derivation_id, self.database.durable_action_derivation_result(derivation_id), record_rejection=False,
            )
        except DurableDerivationBlocked:
            raise
        except RuntimeDatabaseError:
            if phase == DurableDerivationPhase.GENERATION_MAY_HAVE_HAPPENED.value:
                raise DurableDerivationBlocked("GENERATION_MAY_HAVE_HAPPENED", derivation_id)
            if phase in {DurableDerivationPhase.CONFIRMED_RESULT_UNAVAILABLE.value,
                         DurableDerivationPhase.GENERATION_NOT_STARTED.value}:
                raise DurableDerivationBlocked("EXPLICIT_NEW_ATTEMPT_REQUIRED", derivation_id)
            raise DurableDerivationBlocked("EXISTING_ATTEMPT_REQUIRES_RECONCILIATION", derivation_id)

    def begin_validation(self, derivation_id: str) -> None:
        self.database.advance_durable_action_derivation(
            derivation_id, lifecycle="VALIDATION_RUNNING", processing_phase=DurableDerivationPhase.VALIDATION_IN_PROGRESS.value,
        )

    def record_governance_refinement(self, derivation_id: str) -> None:
        self.database.advance_durable_action_derivation(
            derivation_id, lifecycle="GOVERNANCE_REFINEMENT_REQUIRED", processing_phase=DurableDerivationPhase.GOVERNANCE_REFINEMENT.value,
        )

    def record_deterministic_rejection(self, derivation_id: str, code: str, error: Exception) -> None:
        self.database.advance_durable_action_derivation(
            derivation_id, lifecycle="FAILED", processing_phase=DurableDerivationPhase.DETERMINISTIC_REJECTION.value,
            error_code=code, exception_type=type(error).__name__,
            location="forge.planner.action_derivation.ActionDerivationValidator.validate",
        )

    def record_validated(self, derivation_id: str) -> None:
        self.database.advance_durable_action_derivation(
            derivation_id, lifecycle="VALIDATED", processing_phase=DurableDerivationPhase.VALIDATED.value,
        )

    def record_materialization_failure(self, derivation_id: str, error: Exception) -> None:
        self.database.advance_durable_action_derivation(
            derivation_id, lifecycle="MATERIALIZATION_FAILED", processing_phase=DurableDerivationPhase.MATERIALIZATION_FAILED.value,
            error_code="MATERIALIZATION_PERSISTENCE_FAILED", exception_type=type(error).__name__,
            location="forge.execution.loop.ExecutionLoop._plan",
        )

    def authorize_next_attempt(
        self, snapshot: PlanningSnapshot, planning_input: MissionPlannerInput, policy: DerivationPolicy,
        *, predecessor_attempt_id: str, governance_repository: object, operator_context: object,
        rationale: str,
    ) -> dict[str, object]:
        """Reserve, but do not invoke, one explicit successor after lost output.

        A successor is deliberately a new attempt identity.  The reservation is
        durable and may be consumed once only at the later provider boundary;
        merely recording it cannot run Codex or dispatch an Action.
        """
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 512:
            raise ValueError("a bounded explicit next-attempt rationale is required")
        operators = getattr(governance_repository, "operators", None)
        authorize = getattr(operators, "authorize", None)
        if not callable(authorize) or not authorize(operator_context):
            raise PermissionError("trusted operator context is required for a next planning attempt")
        predecessor = self.database.durable_action_derivation_attempt(predecessor_attempt_id)
        if (predecessor.get("mission_id") != snapshot.mission_id
                or predecessor.get("lifecycle") != "FAILED"
                or predecessor.get("processing_phase") != DurableDerivationPhase.CONFIRMED_RESULT_UNAVAILABLE.value):
            raise PermissionError("only a confirmed-result-unavailable attempt can receive a successor")
        try:
            self.database.durable_action_derivation_result(predecessor_attempt_id)
        except RuntimeDatabaseError:
            pass
        else:
            raise RuntimeIntegrityError("a replayable provider result cannot receive a new attempt")
        if predecessor.get("replay_boundary_digest") != _replay_boundary_digest(snapshot):
            raise RuntimeIntegrityError("current planning facts no longer bind the unavailable result")
        mission_state = self.database.get_document("mission_state", snapshot.mission_id)
        if (mission_state.get("status") not in {"CREATED", "BLOCKED"}
                or mission_state.get("actions") or mission_state.get("execution_correlation") is not None
                or self.database.has_active_mission_dispatch(snapshot.mission_id)):
            raise PermissionError("a next planning attempt cannot bypass active Actions or dispatch")
        prepare = getattr(self.provider, "prepare_durable_attempt", None)
        if not callable(prepare):
            raise RuntimeDatabaseError("installed provider does not support durable Action-Derivation")
        decision_id = "durable-action-derivation-reattempt:" + predecessor_attempt_id
        authority_revision = _digest({
            "predecessor_attempt_id": predecessor_attempt_id,
            "replay_boundary_digest": predecessor["replay_boundary_digest"],
            "rationale": rationale.strip(),
        })
        # Deterministic identity makes the authorization safe to resume if a
        # process stops after recording its governance decision but before it
        # can reserve the successor attempt.  A different rationale produces
        # a different revision and fails against the existing decision.
        successor_id = "codex-derivation-successor-" + authority_revision[7:39]
        try:
            governance_repository.record(GovernanceDecision(
                decision_id=decision_id, subject_id=predecessor_attempt_id,
                subject_revision=authority_revision,
                capability=GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION,
                decision="authorized", scope=("DURABLE_ACTION_DERIVATION_REATTEMPT",),
                gates=("confirmed-result-unavailable", "one-successor", "no-active-dispatch"),
                predecessor_digest=str(predecessor["attempt_metadata_digest"]),
                evidence={"kind": "DURABLE_ACTION_DERIVATION_REATTEMPT_V1",
                          "mission_id": snapshot.mission_id,
                          "predecessor_attempt_id": predecessor_attempt_id,
                          "replay_boundary_digest": predecessor["replay_boundary_digest"],
                          "rationale": rationale.strip()},
            ), operator_context)
        except Exception:
            try:
                decision = governance_repository.decision(decision_id)
            except Exception:
                raise
            if not self._is_current_reattempt_decision(
                decision, decision_id, predecessor, snapshot, authority_revision, rationale,
            ):
                raise RuntimeIntegrityError("canonical next-attempt authorization is stale or conflicting") from None
        specification = prepare(snapshot, planning_input, policy, successor_id, decision_id)
        if not isinstance(specification, Mapping):
            raise RuntimeDatabaseError("installed provider produced an invalid successor specification")
        document = self._attempt_document(specification, successor_id, snapshot, planning_input)
        generated_uid = getattr(operator_context, "generated_uid", None)
        if not isinstance(generated_uid, str) or not generated_uid:
            raise PermissionError("trusted operator context has no generated identity")
        document.update({
            "processing_phase": "SUCCESSOR_AUTHORIZED",
            "predecessor_attempt_id": predecessor_attempt_id,
            "next_attempt_decision_id": decision_id,
            "next_attempt_authority_revision": authority_revision,
            "authority_identity": sha256(generated_uid.encode("utf-8")).hexdigest()[:16],
            "reason": "CONFIRMED_RESULT_UNAVAILABLE",
            "rationale": rationale.strip(),
        })
        document["attempt_metadata_digest"] = _digest({
            key: value for key, value in document.items() if key not in _MUTABLE_ATTEMPT_FIELDS
        })
        reserved, claimed = self.database.begin_durable_action_derivation_attempt(document)
        if not claimed or reserved.get("derivation_id") != successor_id:
            raise RuntimeIntegrityError("next planning attempt reservation is conflicting")
        return self._safe_authorization_readback(reserved)

    def consume_authorized_next_attempt(
        self, snapshot: PlanningSnapshot, planning_input: MissionPlannerInput, policy: DerivationPolicy,
        *, successor_attempt_id: str, governance_repository: object, operator_context: object,
    ) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired:
        """Consume exactly one previously authorized successor at its call boundary.

        The caller does not supply an authority token.  The durable reservation
        binds it to the currently trusted native operator and the exact
        successor request before the atomic consume step opens any provider
        process.
        """
        operators = getattr(governance_repository, "operators", None)
        authorize = getattr(operators, "authorize", None)
        if not callable(authorize) or not authorize(operator_context):
            raise PermissionError("trusted operator context is required to consume a next planning attempt")
        reserved = self.database.durable_action_derivation_attempt(successor_attempt_id)
        decision_id = reserved.get("next_attempt_decision_id")
        authority_revision = reserved.get("next_attempt_authority_revision")
        generated_uid = getattr(operator_context, "generated_uid", None)
        if (reserved.get("mission_id") != snapshot.mission_id
                or not isinstance(decision_id, str) or not decision_id
                or not isinstance(authority_revision, str) or not authority_revision
                or not isinstance(generated_uid, str)
                or reserved.get("authority_identity") != sha256(generated_uid.encode("utf-8")).hexdigest()[:16]):
            raise PermissionError("next planning attempt reservation is not usable by this operator")
        predecessor_id = reserved.get("predecessor_attempt_id")
        if not isinstance(predecessor_id, str) or not predecessor_id:
            raise RuntimeIntegrityError("next planning attempt lacks a predecessor")
        predecessor = self.database.durable_action_derivation_attempt(predecessor_id)
        if (predecessor.get("lifecycle") != "FAILED"
                or predecessor.get("processing_phase") != DurableDerivationPhase.CONFIRMED_RESULT_UNAVAILABLE.value
                or predecessor.get("replay_boundary_digest") != _replay_boundary_digest(snapshot)):
            raise RuntimeIntegrityError("next planning attempt no longer binds current planning facts")
        decision = governance_repository.decision(decision_id)
        if not self._is_current_reattempt_decision(
            decision, decision_id, predecessor, snapshot, authority_revision,
            str(reserved.get("rationale") or ""),
        ):
            raise PermissionError("canonical next planning attempt authorization is stale or conflicting")
        mission_state = self.database.get_document("mission_state", snapshot.mission_id)
        if (mission_state.get("status") not in {"CREATED", "BLOCKED"}
                or mission_state.get("actions") or mission_state.get("execution_correlation") is not None
                or self.database.has_active_mission_dispatch(snapshot.mission_id)):
            raise PermissionError("next planning attempt cannot bypass an active dispatch")
        prepare = getattr(self.provider, "prepare_durable_attempt", None)
        if not callable(prepare):
            raise RuntimeDatabaseError("installed provider does not support durable Action-Derivation")
        specification = prepare(snapshot, planning_input, policy, successor_attempt_id, decision_id)
        if not isinstance(specification, Mapping):
            raise RuntimeDatabaseError("installed provider produced an invalid successor specification")
        expected = self._attempt_document(specification, successor_attempt_id, snapshot, planning_input)
        bindings = (
            "snapshot_digest", "replay_boundary_digest", "provider_configuration", "provider_id",
            "provider_configuration_revision", "effective_policy_digest", "generation_request_digest",
            "derivation_request_digest", "runtime_id", "installation_id",
        )
        if any(reserved.get(field) != expected.get(field) for field in bindings):
            raise DurableDerivationBlocked("CURRENT_PROVIDER_AUTHORITY_CHANGED", successor_attempt_id)
        self._last_derivation_id = successor_attempt_id
        if reserved.get("processing_phase") != "SUCCESSOR_AUTHORIZED":
            # A crash after the one-time decision was consumed leaves the
            # successor's durable result/terminal phase authoritative.  It is
            # replayed through the ordinary validator, never re-invoked.
            return self._replay_or_block(reserved)
        self.database.activate_authorized_durable_action_derivation(successor_attempt_id, decision_id)
        return self._invoke_claimed_attempt(
            snapshot, planning_input, policy, successor_attempt_id, attempt_authority_id=decision_id,
            attempt_specification=specification,
        )

    @staticmethod
    def _is_current_reattempt_decision(decision: Mapping[str, object], decision_id: str,
                                       predecessor: Mapping[str, object], snapshot: PlanningSnapshot,
                                       authority_revision: str, rationale: str) -> bool:
        evidence = decision.get("evidence")
        return (
            decision.get("decision_id") == decision_id
            and decision.get("subject_id") == predecessor.get("derivation_id")
            and decision.get("subject_revision") == authority_revision
            and decision.get("capability") == GovernanceCapability.OWNER_PROGRAMME_AUTHORIZATION.value
            and decision.get("decision") == "authorized"
            and decision.get("scope") == ["DURABLE_ACTION_DERIVATION_REATTEMPT"]
            and decision.get("gates") == ["confirmed-result-unavailable", "no-active-dispatch", "one-successor"]
            and decision.get("predecessor_digest") == predecessor.get("attempt_metadata_digest")
            and isinstance(evidence, Mapping)
            and evidence.get("kind") == "DURABLE_ACTION_DERIVATION_REATTEMPT_V1"
            and evidence.get("mission_id") == snapshot.mission_id
            and evidence.get("predecessor_attempt_id") == predecessor.get("derivation_id")
            and evidence.get("replay_boundary_digest") == predecessor.get("replay_boundary_digest")
            and evidence.get("rationale") == rationale.strip()
        )

    @staticmethod
    def _safe_authorization_readback(document: Mapping[str, object]) -> dict[str, object]:
        return {
            "derivation_id": document.get("derivation_id"),
            "predecessor_attempt_id": document.get("predecessor_attempt_id"),
            "next_attempt_decision_id": document.get("next_attempt_decision_id"),
            "processing_phase": document.get("processing_phase"),
            "generation_request_digest": document.get("generation_request_digest"),
            "snapshot_digest": document.get("snapshot_digest"),
        }


class DurableAIMissionPlanner:
    """The canonical planner pipeline with durable provider return/replay."""

    def __init__(self, database: RuntimeDatabase, provider: object,
                 validator: ActionDerivationValidator | None = None,
                 materializer: MissionPlanner | None = None) -> None:
        self._coordinator = DurableActionDerivationCoordinator(database, provider)
        self._validator = validator or ActionDerivationValidator()
        self._materializer = materializer or MissionPlanner()

    @property
    def current_derivation_id(self) -> str:
        return self._coordinator.last_derivation_id

    def record_materialization_failure(self, derivation_id: str, error: Exception) -> None:
        self._coordinator.record_materialization_failure(derivation_id, error)

    def plan(self, planning_input: MissionPlannerInput, policy: DerivationPolicy) -> DerivationResult:
        snapshot = PlanningSnapshot.from_planner_input(planning_input)
        proposed = self._coordinator.derive_with_planning_input(snapshot, planning_input, policy)
        return self._validate_and_materialize(snapshot, planning_input, policy, proposed)

    def plan_authorized_next_attempt(
        self, planning_input: MissionPlannerInput, policy: DerivationPolicy, *, successor_attempt_id: str,
        governance_repository: object, operator_context: object,
    ) -> DerivationResult:
        """Use one existing successor reservation; this is never an automatic retry."""
        snapshot = PlanningSnapshot.from_planner_input(planning_input)
        proposed = self._coordinator.consume_authorized_next_attempt(
            snapshot, planning_input, policy, successor_attempt_id=successor_attempt_id,
            governance_repository=governance_repository, operator_context=operator_context,
        )
        return self._validate_and_materialize(snapshot, planning_input, policy, proposed)

    def _validate_and_materialize(
        self, snapshot: PlanningSnapshot, planning_input: MissionPlannerInput, policy: DerivationPolicy,
        proposed: tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired,
    ) -> DerivationResult:
        derivation_id = self._coordinator.last_derivation_id
        self._coordinator.begin_validation(derivation_id)
        if isinstance(proposed, GovernanceRefinementRequired):
            self._coordinator.record_governance_refinement(derivation_id)
            return DerivationResult(snapshot, None, proposed, None)
        try:
            validated = self._validator.validate(proposed, snapshot, planning_input, policy)
        except ProposalValidationError as error:
            self._coordinator.record_deterministic_rejection(
                derivation_id, deterministic_validation_failure_code(error), error,
            )
            raise
        try:
            plan = self._materializer.plan(planner_input_from_derivation(planning_input, validated))
        except Exception as error:
            self._coordinator.record_validated(derivation_id)
            self._coordinator.record_materialization_failure(derivation_id, error)
            raise
        self._coordinator.record_validated(derivation_id)
        return DerivationResult(snapshot, validated, None, plan)
