"""Contract-only, restart-safe Bootstrap Mission Runtime orchestration."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.mission_completion import MissionCompletionEvaluation
from forge.models.execution_host import (
    ExecutionDispatch,
    ExecutionEvidenceOutcome,
    ExecutionHost,
    ExecutionHostEvidence,
    ExecutionRequest,
    ExecutionHostTemporaryUnavailable,
)
from forge.models.runtime_prompt import (
    ProviderPromptDefinition,
    RuntimePrompt,
    RuntimePromptSection,
    RuntimePromptSectionKind,
)
from forge.models.codex_runtime_prompt import (
    CodexCliRuntimePrompt, ExecutionHostCompatibility, RepositoryState,
)
from forge.models.producer import (
    ExecutionReceiptReference, ForgeActionContextEnvelope, ForgePlanningContextEnvelope,
    Producer, ProducerContract, ProducerIdentity, RuntimePromptEnvelope,
)
from forge.models.intent import IntentReference
from forge.scheduler import BootstrapMissionScheduler
from forge.state import MissionExecutionState, MissionExecutionStatus, MissionStateStore


class MissionRunnerError(ValueError):
    """Raised when authoritative Mission state cannot drive the Runtime."""


class RuntimePromptFactory(Protocol):
    """The injected derivation boundary; the Runner performs no prompt reasoning."""

    def __call__(self, intent: Mapping[str, Any], action: EngineeringAction) -> RuntimePrompt: ...


class CompletionContextFactory(Protocol):
    """Resolve the final Repository Truth required by a Mission completion."""

    def __call__(self, state: MissionExecutionState, evidence: ExecutionHostEvidence) -> tuple[Mapping[str, Any], MissionCompletionEvaluation]: ...


class ReplanAfterEvidence(Protocol):
    """Validate or materialize bounded successor work after persisted evidence."""

    def __call__(self, state: MissionExecutionState, evidence: ExecutionHostEvidence) -> MissionExecutionState: ...


class EvidenceProgressionGate(Protocol):
    """Optionally pause Forge progression after evidence; Execution Hosts never see it."""

    def __call__(self, state: MissionExecutionState, actions: tuple[EngineeringAction, ...],
                 evidence: ExecutionHostEvidence, mission_complete: bool) -> MissionExecutionState | None: ...


def _document(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Enum):
        return value.value  # type: ignore[return-value]
    if not isinstance(value, Mapping):
        raise MissionRunnerError("runtime persistence requires a mapping")
    return {str(key): _value(item) for key, item in value.items()}


def _value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_value(item) for item in value]
    return value


def _failure_code(error: Exception) -> str:
    """Return only a bounded, redacted contract code for the event journal."""
    candidate = str(error)
    if (
        3 <= len(candidate) <= 128
        and all(character.isupper() or character.isdigit() or character == "_" for character in candidate)
    ):
        return candidate
    return type(error).__name__.upper()


def _action(document: Mapping[str, Any]) -> EngineeringAction:
    return EngineeringAction(
        order=int(document["order"]), id=str(document["id"]), intent_id=str(document["intent_id"]),
        intent_revision=str(document["intent_revision"]), objective=str(document["objective"]),
        expected_evidence=tuple(document["expected_evidence"]), dependencies=tuple(document.get("dependencies", ())),
        status=EngineeringActionStatus(document["status"]), schema_version=str(document["schema_version"]),
    )


def _prompt(document: Mapping[str, Any]) -> RuntimePrompt | CodexCliRuntimePrompt:
    """Restore the exact persisted prompt type; never downgrade a rendered prompt."""
    if "renderer_version" in document and "repository_state" in document:
        mission = document["mission"]
        intent = document["intent"]
        action = document["action"]
        repository = document["repository_state"]
        compatibility = document["compatibility"]
        policy = document.get("policy")
        return CodexCliRuntimePrompt(
            id=str(document["id"]), correlation_id=str(document["correlation_id"]),
            renderer_version=str(document["renderer_version"]), schema_version=str(document["schema_version"]),
            generated_at=str(document["generated_at"]), mission_id=str(mission["id"]),
            mission_revision=str(mission["revision"]), intent_id=str(intent["id"]),
            intent_revision=str(intent["revision"]), action_id=str(action["id"]),
            repository_state=RepositoryState(str(repository["repository_id"]), str(repository["revision"]),
                                             str(repository["state_digest"]), str(repository["captured_at"])),
            compatibility=ExecutionHostCompatibility(
                str(compatibility["execution_host_contract_version"]), str(compatibility["execution_mode"]),
                tuple(compatibility["required_capabilities"]), str(compatibility["minimum_supported_runtime"]),
            ),
            policy_version=None if policy is None else str(policy["version"]),
            policy_digest=None if policy is None else str(policy["digest"]),
            policy_execution_constraints=() if policy is None else tuple(policy["execution_constraints"]),
            objective=str(document["objective"]), expected_repository_evidence=tuple(document["expected_repository_evidence"]),
            constraints=tuple(document["constraints"]), validation=tuple(document["validation"]),
            source_digest=str(document["source_digest"]), rendered_text=str(document["rendered_text"]),
        )
    source_intent = document["source_intent"]
    source_action = document["source_action"]
    provider = document["provider_definition"]
    return RuntimePrompt(
        id=str(document["id"]), source_intent_id=str(source_intent["id"]),
        source_intent_revision=str(source_intent["revision"]), source_action_id=str(source_action["id"]),
        provider_definition=ProviderPromptDefinition(str(provider["id"]), str(provider["version"])),
        generation_request_digest=str(document["generation_request_digest"]),
        sections=tuple(
            RuntimePromptSection(
                RuntimePromptSectionKind(section["kind"]), tuple(section["content"]),
                tuple(IntentReference(str(reference["id"]), str(reference["version"]), str(reference["locator"]))
                      for reference in section.get("references", ())),
            )
            for section in document["sections"]
        ), schema_version=str(document["schema_version"]),
    )


def _request(document: Mapping[str, Any]) -> ExecutionRequest:
    contract_document = document.get("producer_contract")
    contract = None
    # Absence is an explicit historical compatibility route. Presence is a
    # claim that a canonical Producer Contract was persisted, so null or any
    # malformed representation must fail closed rather than silently becoming
    # a freshly synthesized default contract.
    if "producer_contract" in document:
        if not isinstance(contract_document, Mapping):
            raise MissionRunnerError("persisted Producer Contract is malformed")
        try:
            producer = contract_document["producer"]
            prompt = contract_document["runtime_prompt"]
            metadata = contract_document["execution_metadata"]
            constraints = contract_document["execution_constraints"]
            receipts = contract_document.get("receipt_references", ())
            evidence_references = contract_document.get("execution_evidence_references", ())
            context_document = contract_document.get("action_context")
            planning_document = contract_document.get("planning_context")
            if not isinstance(producer, Mapping) or not isinstance(prompt, Mapping) or not isinstance(metadata, Mapping) or not isinstance(constraints, list):
                raise TypeError
            identity = producer["identity"]
            if not isinstance(identity, Mapping) or not isinstance(receipts, list) or not isinstance(evidence_references, list):
                raise TypeError
            def required(value: Any) -> str:
                if not isinstance(value, str) or not value:
                    raise TypeError
                return value
            if any(not isinstance(key, str) or not key or not isinstance(value, str) or not value for key, value in metadata.items()):
                raise TypeError
            if any(not isinstance(item, str) or not item for item in constraints):
                raise TypeError
            if any(not isinstance(item, str) or not item for item in evidence_references):
                raise TypeError
            if any(not isinstance(item, Mapping) or set(item) != {"host_id", "receipt_id"}
                   or not isinstance(item["host_id"], str) or not item["host_id"]
                   or not isinstance(item["receipt_id"], str) or not item["receipt_id"] for item in receipts):
                raise TypeError
            action_context = None
            if context_document is not None:
                if not isinstance(context_document, Mapping) or set(context_document) != {
                    "envelope_version", "action_id", "summary", "summary_digest", "envelope_digest", "generator",
                }:
                    raise TypeError
                generator = context_document["generator"]
                if not isinstance(generator, Mapping) or set(generator) != {"id", "model", "version", "source_digest"}:
                    raise TypeError
                action_context = ForgeActionContextEnvelope(
                    action_id=required(context_document["action_id"]),
                    summary=required(context_document["summary"]),
                    source_digest=required(generator["source_digest"]),
                    summary_digest=required(context_document["summary_digest"]),
                    envelope_digest=required(context_document["envelope_digest"]),
                    envelope_version=required(context_document["envelope_version"]),
                    generator_id=required(generator["id"]),
                    generator_model=required(generator["model"]),
                    generator_version=required(generator["version"]),
                )
            planning_context = None
            if planning_document is not None:
                planning_keys = {
                    "envelope_version", "mission_id", "mission_revision", "intent_id", "intent_revision",
                    "action_id", "mission_title", "business_summary", "engineering_summary",
                    "mission_lifecycle", "decision_evidence_reference", "decision_evidence_reference_digest",
                    "envelope_digest",
                }
                if not isinstance(planning_document, Mapping) or set(planning_document) != planning_keys:
                    raise TypeError
                def optional(value: Any) -> str | None:
                    if value is not None and (not isinstance(value, str) or not value):
                        raise TypeError
                    return value
                planning_context = ForgePlanningContextEnvelope(
                    mission_id=required(planning_document["mission_id"]),
                    mission_revision=required(planning_document["mission_revision"]),
                    intent_id=required(planning_document["intent_id"]),
                    intent_revision=required(planning_document["intent_revision"]),
                    action_id=required(planning_document["action_id"]),
                    mission_title=optional(planning_document["mission_title"]),
                    business_summary=optional(planning_document["business_summary"]),
                    engineering_summary=optional(planning_document["engineering_summary"]),
                    mission_lifecycle=optional(planning_document["mission_lifecycle"]),
                    decision_evidence_reference=optional(planning_document["decision_evidence_reference"]),
                    decision_evidence_reference_digest=optional(planning_document["decision_evidence_reference_digest"]),
                    envelope_digest=required(planning_document["envelope_digest"]),
                    envelope_version=required(planning_document["envelope_version"]),
                )
            mission_id = required(contract_document["mission_id"])
            contract = ProducerContract(
                Producer(ProducerIdentity(required(identity["id"]), required(identity["type"]), required(identity["version"])),
                         required(producer["contract_version"])),
                required(contract_document["correlation_id"]), required(contract_document["engineering_action_id"]),
                RuntimePromptEnvelope(required(prompt["id"]), required(prompt["version"]), required(prompt["format"]),
                                      required(prompt["content"]), required(prompt["content_digest"])),
                tuple(constraints), tuple(metadata.items()), action_context=action_context,
                planning_context=planning_context, mission_id=mission_id,
                receipt_references=tuple(ExecutionReceiptReference(item["host_id"], item["receipt_id"]) for item in receipts),
                execution_evidence_references=tuple(evidence_references), contract_version=required(contract_document["contract_version"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise MissionRunnerError("persisted Producer Contract is malformed") from error
    return ExecutionRequest(
        host_id=str(document["host_id"]), mission_id=str(document["mission_id"]),
        intent_id=str(document["intent_id"]), intent_revision=str(document["intent_revision"]),
        action_id=str(document["action_id"]), runtime_prompt=_prompt(document["runtime_prompt"]),
        workspace_id=str(document["workspace_id"]), repository_id=str(document["repository_id"]),
        correlation_id=str(document["correlation_id"]), dispatched_at=str(document["dispatched_at"]),
        retry_of_correlation_id=document.get("retry_of_correlation_id"),
        original_correlation_id=document.get("original_correlation_id"),
        producer_contract=contract,
        repository_identity=document.get("repository_identity", document["repository_id"]),
    )


def _request_document(request: ExecutionRequest) -> dict[str, Any]:
    """Persist the full request including the canonical Runtime Prompt form."""
    return {
        "host_id": request.host_id,
        "mission_id": request.mission_id,
        "intent_id": request.intent_id,
        "intent_revision": request.intent_revision,
        "action_id": request.action_id,
        "runtime_prompt": request.runtime_prompt.to_dict(),
        "workspace_id": request.workspace_id,
        "repository_id": request.repository_id,
        "repository_identity": request.repository_identity,
        "correlation_id": request.correlation_id,
        "dispatched_at": request.dispatched_at,
        "retry_of_correlation_id": request.retry_of_correlation_id,
        "original_correlation_id": request.original_correlation_id,
        "producer_contract": request.producer_contract.to_dict(),
    }


class BootstrapMissionRunner:
    """Advance exactly one persisted Mission through the Execution Host contract.

    This class deliberately knows nothing of the Bootstrap adapter, inboxes,
    reports, operating-system services, repositories, or AI providers.
    """

    def __init__(
        self,
        store: MissionStateStore,
        scheduler: BootstrapMissionScheduler,
        host: ExecutionHost,
        prompt_factory: RuntimePromptFactory,
        *,
        host_id: str,
        workspace_id: str,
        repository_id: str,
        repository_identity: str | None = None,
        clock: Callable[[], str] | None = None,
        correlation_id_factory: Callable[[], str],
        completion_context: CompletionContextFactory | None = None,
        replan_after_evidence: ReplanAfterEvidence | None = None,
        evidence_progression_gate: EvidenceProgressionGate | None = None,
    ) -> None:
        if not all((host_id, workspace_id, repository_id)):
            raise MissionRunnerError("runtime host, workspace, and repository identities are required")
        self._store = store
        self._scheduler = scheduler
        self._host = host
        self._prompt_factory = prompt_factory
        self._host_id = host_id
        self._workspace_id = workspace_id
        self._repository_id = repository_id
        self._repository_identity = repository_identity or repository_id
        self._clock = clock or (lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))
        self._correlation_id_factory = correlation_id_factory
        self._completion_context = completion_context
        self._replan_after_evidence = replan_after_evidence
        self._evidence_progression_gate = evidence_progression_gate

    def start(self, mission: Any, intents: Sequence[Any], actions: Sequence[Any]) -> MissionExecutionState:
        """Persist the one permitted Mission and make it available to the Runtime."""
        if self._store.resumable():
            raise MissionRunnerError("Bootstrap Runtime supports exactly one non-terminal Mission")
        created = self._store.create(mission, intents, actions, occurred_at=self._now(), resume={"runner": "bootstrap-v1"})
        return self._store.transition(created.mission_id, MissionExecutionStatus.READY, occurred_at=self._now(), reason="runner_started")

    def resume(self, mission_id: str) -> MissionExecutionState:
        """Continue solely from the authoritative persisted Mission snapshot."""
        return self.run(mission_id)

    def run(self, mission_id: str) -> MissionExecutionState:
        """Advance until terminal state or a host has no terminal evidence yet."""
        while True:
            state = self._store.get(mission_id)
            if state.status in {MissionExecutionStatus.COMPLETED, MissionExecutionStatus.AWAITING_APPROVAL,
                                MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED, MissionExecutionStatus.ARCHIVED}:
                return state
            before_revision = state.revision
            state = self._advance(state)
            if state.status in {MissionExecutionStatus.WAITING_FOR_EXECUTION,
                                MissionExecutionStatus.WAITING_FOR_EVIDENCE} and state.revision == before_revision:
                return state

    def _advance(self, state: MissionExecutionState) -> MissionExecutionState:
        if state.status is MissionExecutionStatus.CREATED:
            return self._store.transition(state.mission_id, MissionExecutionStatus.READY, occurred_at=self._now(), reason="runner_resumed")
        if state.status is MissionExecutionStatus.READY:
            return self._store.transition(state.mission_id, MissionExecutionStatus.ACTIVE, occurred_at=self._now(), reason="mission_running")
        if state.status is MissionExecutionStatus.ACTIVE:
            return self._release_action(state)
        if state.status is MissionExecutionStatus.WAITING_FOR_EXECUTION:
            return self._dispatch_or_recover(state)
        if state.status is MissionExecutionStatus.WAITING_FOR_EVIDENCE:
            return self._collect_evidence(state)
        raise MissionRunnerError(f"Mission state {state.status.value} is not runnable")

    def _release_action(self, state: MissionExecutionState) -> MissionExecutionState:
        actions = self._actions(state)
        if self._scheduler.progress(actions).is_complete:
            raise MissionRunnerError("a complete Mission requires terminal execution evidence")
        active = self._scheduler.activate(actions)
        action = next(item for item in active if item.status is EngineeringActionStatus.ACTIVE)
        intent = next((item for item in state.intents if item["id"] == action.intent_id and item["revision"] == action.intent_revision), None)
        if intent is None:
            raise MissionRunnerError("active Action has no persisted Intent")
        prompt = self._prompt_factory(intent, action)
        planning_context = self._planning_context(state, action, prompt)
        retry_of, original = self._recovery_lineage(state, action)
        request = ExecutionRequest(
            self._host_id, state.mission_id, action.intent_id, action.intent_revision, action.id, prompt,
            self._workspace_id, self._repository_id, self._correlation_id_factory(), self._now(),
            retry_of_correlation_id=retry_of, original_correlation_id=original,
            repository_identity=self._repository_identity,
            planning_context=planning_context,
        )
        envelope = {"request": _request_document(request), "host_run_id": None}
        return self._store.transition(
            state.mission_id, MissionExecutionStatus.WAITING_FOR_EXECUTION, occurred_at=self._now(),
            reason="execution_request_persisted", actions=active, execution_correlation=envelope,
        )

    @staticmethod
    def _planning_context(
        state: MissionExecutionState, action: EngineeringAction, prompt: RuntimePrompt,
    ) -> ForgePlanningContextEnvelope | None:
        """Freeze only explicitly supplied Forge planning facts at submission.

        This adapter never reads the mutable display projection and never
        invents summaries for absent facts. Runtime and terminal evidence are
        intentionally not part of the outbound Forge planning context.
        """
        mission = state.mission
        admission = state.admission_contract if isinstance(state.admission_contract, Mapping) else {}

        def supplied(*values: object) -> str | None:
            return next((value for value in values if isinstance(value, str) and value), None)

        mission_revision = supplied(
            getattr(prompt, "mission_revision", None),
            dict(getattr(prompt, "execution_metadata", ())).get("mission_revision"),
            mission.get("revision"), admission.get("subject_revision"),
        )
        # The independently versioned context envelope is mandatory for the
        # installed Forge-to-EP route, whose Runtime Prompt includes an
        # immutable Mission revision.  Older in-process execution hosts do
        # not have that field and must retain their existing behaviour rather
        # than receive a fabricated revision.  They therefore get no planning
        # envelope; the HTTP adapter still fails closed if such a request is
        # sent to EP.
        if mission_revision is None:
            return None
        return ForgePlanningContextEnvelope.create(
            mission_id=state.mission_id,
            mission_revision=mission_revision,
            intent_id=action.intent_id,
            intent_revision=action.intent_revision,
            action_id=action.id,
            mission_title=supplied(mission.get("mission_title"), mission.get("title")),
            business_summary=supplied(mission.get("business_summary"), mission.get("business_objective")),
            engineering_summary=supplied(mission.get("engineering_summary"), mission.get("summary")),
            mission_lifecycle=state.status.value,
            decision_evidence_reference=supplied(
                admission.get("architecture_decision_id"), mission.get("decision_evidence_reference"),
                mission.get("architecture_review_reference"),
            ),
        )

    @staticmethod
    def _recovery_lineage(state: MissionExecutionState, action: EngineeringAction) -> tuple[str | None, str | None]:
        """Carry an authorized retry back to its exact persisted predecessor."""
        authorization = state.resume.get("authorized_recovery") if state.resume else None
        if not isinstance(authorization, Mapping) or authorization.get("action_id") != action.id:
            return None, None
        correlation = state.execution_correlation
        prior = correlation.get("request") if isinstance(correlation, Mapping) else None
        if not isinstance(prior, Mapping) or prior.get("action_id") != action.id:
            raise MissionRunnerError("authorized recovery lacks the prior persisted execution request")
        predecessor = prior.get("correlation_id")
        original = prior.get("original_correlation_id") or predecessor
        if not isinstance(predecessor, str) or not predecessor or not isinstance(original, str) or not original:
            raise MissionRunnerError("authorized recovery has invalid execution correlation lineage")
        return predecessor, original

    def _dispatch_or_recover(self, state: MissionExecutionState) -> MissionExecutionState:
        request = self._persisted_request(state)
        try:
            dispatch = self._host.recover_dispatch(request)
            if dispatch is None:
                dispatch = self._host.dispatch(request)
            # An accepted submission may legitimately have no run yet.  Keep
            # the persisted request in WAITING_FOR_EXECUTION and recover it on
            # a later service tick; do not reclassify that state as failure.
            if dispatch is None:
                return state
            if dispatch.request != request:
                raise MissionRunnerError("execution host acknowledgement did not preserve the persisted request")
        except ExecutionHostTemporaryUnavailable:
            # The request was persisted before dispatch.  A later tick asks for
            # its original acknowledgement before attempting another send.
            return state
        except Exception as error:  # Invalid acknowledgements fail closed.
            return self._host_failure(state, "host_dispatch_failed", error)
        envelope = {"request": _request_document(request), "host_run_id": dispatch.host_run_id}
        return self._store.transition(
            state.mission_id, MissionExecutionStatus.WAITING_FOR_EVIDENCE, occurred_at=self._now(),
            reason="execution_host_acknowledged", actions=self._scheduler.acknowledge(self._actions(state), dispatch),
            execution_correlation=envelope,
        )

    def _collect_evidence(self, state: MissionExecutionState) -> MissionExecutionState:
        try:
            dispatch = self._persisted_dispatch(state)
            evidence = self._host.retrieve_evidence(dispatch)
            if evidence is None:
                return state
            actions = self._scheduler.reconcile(self._actions(state), dispatch, evidence)
        except ExecutionHostTemporaryUnavailable:
            # A temporary read outage is not terminal evidence.
            return state
        except Exception as error:  # Invalid evidence and host failures fail closed.
            return self._host_failure(state, "host_evidence_failed", error)
        evidence_document = _document(evidence)
        if evidence.outcome is ExecutionEvidenceOutcome.BLOCKED:
            return self._store.transition(state.mission_id, MissionExecutionStatus.BLOCKED, occurred_at=self._now(), reason="execution_blocked", actions=actions, execution_evidence=evidence_document)
        if evidence.outcome is ExecutionEvidenceOutcome.FAILED:
            return self._store.transition(state.mission_id, MissionExecutionStatus.FAILED, occurred_at=self._now(), reason="execution_failed", actions=actions, execution_evidence=evidence_document)
        actions_complete = self._scheduler.progress(actions).is_complete
        # Historical direct Runner callers have no approved Architecture Mission
        # criteria.  The composed ExecutionLoop supplies the typed completion
        # boundary below and never takes this compatibility route.
        if self._completion_context is None:
            if self._evidence_progression_gate is not None:
                paused = self._evidence_progression_gate(state, actions, evidence, actions_complete)
                if paused is not None:
                    return paused
            if actions_complete:
                return self._store.transition(
                    state.mission_id, MissionExecutionStatus.COMPLETED, occurred_at=self._now(),
                    reason="legacy_action_plan_completed", actions=actions, execution_evidence=evidence_document,
                )
            if self._replan_after_evidence is not None:
                return self._replan_after_evidence(state, evidence)
            return self._store.transition(state.mission_id, MissionExecutionStatus.ACTIVE, occurred_at=self._now(),
                                          reason="execution_completed", actions=actions, execution_evidence=evidence_document)

        repository_truth, completion = self._completion_context(state, evidence)
        if not isinstance(completion, MissionCompletionEvaluation):
            raise MissionRunnerError("Mission completion context must be a Forge-owned evaluation")
        mission_complete = actions_complete and completion.all_required_criteria_proven
        reconciled = self._store.transition(
            state.mission_id, MissionExecutionStatus.ACTIVE, occurred_at=self._now(),
            reason="terminal_evidence_reconciled", actions=actions, execution_evidence=evidence_document,
            repository_truth=repository_truth, completion=completion.to_dict(),
        )
        if not mission_complete:
            if self._replan_after_evidence is None:
                if actions_complete:
                    return self._store.transition(
                        reconciled.mission_id, MissionExecutionStatus.BLOCKED, occurred_at=self._now(),
                        reason="mission_criteria_unmet_no_valid_successor",
                    )
            else:
                try:
                    reconciled = self._replan_after_evidence(reconciled, evidence)
                except Exception:
                    return self._store.transition(
                        reconciled.mission_id, MissionExecutionStatus.BLOCKED, occurred_at=self._now(),
                        reason="mission_criteria_unmet_no_valid_successor",
                    )
        current_actions = self._actions(reconciled)
        if self._evidence_progression_gate is not None:
            paused = self._evidence_progression_gate(reconciled, current_actions, evidence, mission_complete)
            if paused is not None:
                return paused
        if mission_complete:
            return self._store.transition(
                reconciled.mission_id, MissionExecutionStatus.COMPLETED, occurred_at=self._now(),
                reason="mission_criteria_proven",
            )
        return reconciled

    def _host_failure(self, state: MissionExecutionState, reference: str, error: Exception) -> MissionExecutionState:
        return self._store.transition(
            state.mission_id, MissionExecutionStatus.FAILED, occurred_at=self._now(), reason=reference,
            execution_evidence={
                "outcome": "failed", "diagnostic_references": [f"runner:{reference}"],
                "failure_code": _failure_code(error),
            },
        )

    def _persisted_request(self, state: MissionExecutionState) -> ExecutionRequest:
        if not state.execution_correlation or "request" not in state.execution_correlation:
            raise MissionRunnerError("waiting Mission has no persisted execution request")
        return _request(state.execution_correlation["request"])

    def _persisted_dispatch(self, state: MissionExecutionState) -> ExecutionDispatch:
        request = self._persisted_request(state)
        run_id = state.execution_correlation.get("host_run_id") if state.execution_correlation else None
        if not isinstance(run_id, str) or not run_id:
            raise MissionRunnerError("waiting Mission has no persisted host run identity")
        return ExecutionDispatch(request, run_id)

    @staticmethod
    def _actions(state: MissionExecutionState) -> tuple[EngineeringAction, ...]:
        return tuple(_action(item) for item in state.actions)

    def _now(self) -> str:
        value = self._clock()
        if not value:
            raise MissionRunnerError("runtime clock returned an empty timestamp")
        return value
