"""Contract-only, restart-safe Bootstrap Mission Runtime orchestration."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Mapping, Protocol, Sequence

from forge.models.action import EngineeringAction, EngineeringActionStatus
from forge.models.execution_host import (
    ExecutionDispatch,
    ExecutionEvidenceOutcome,
    ExecutionHost,
    ExecutionHostEvidence,
    ExecutionRequest,
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

    def __call__(self, state: MissionExecutionState, evidence: ExecutionHostEvidence) -> tuple[Mapping[str, Any], Mapping[str, Any]]: ...


class ReplanAfterEvidence(Protocol):
    """Validate the remaining bounded work after one completed Action."""

    def __call__(self, state: MissionExecutionState, actions: tuple[EngineeringAction, ...], evidence: ExecutionHostEvidence) -> None: ...


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
    return ExecutionRequest(
        host_id=str(document["host_id"]), mission_id=str(document["mission_id"]),
        intent_id=str(document["intent_id"]), intent_revision=str(document["intent_revision"]),
        action_id=str(document["action_id"]), runtime_prompt=_prompt(document["runtime_prompt"]),
        workspace_id=str(document["workspace_id"]), repository_id=str(document["repository_id"]),
        correlation_id=str(document["correlation_id"]), dispatched_at=str(document["dispatched_at"]),
        retry_of_correlation_id=document.get("retry_of_correlation_id"),
        original_correlation_id=document.get("original_correlation_id"),
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
        "correlation_id": request.correlation_id,
        "dispatched_at": request.dispatched_at,
        "retry_of_correlation_id": request.retry_of_correlation_id,
        "original_correlation_id": request.original_correlation_id,
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
        clock: Callable[[], str] | None = None,
        correlation_id_factory: Callable[[], str],
        completion_context: CompletionContextFactory | None = None,
        replan_after_evidence: ReplanAfterEvidence | None = None,
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
        self._clock = clock or (lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z"))
        self._correlation_id_factory = correlation_id_factory
        self._completion_context = completion_context
        self._replan_after_evidence = replan_after_evidence

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
            if state.status in {MissionExecutionStatus.COMPLETED, MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED, MissionExecutionStatus.ARCHIVED}:
                return state
            before_revision = state.revision
            state = self._advance(state)
            if state.status is MissionExecutionStatus.WAITING_FOR_EVIDENCE and state.revision == before_revision:
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
        request = ExecutionRequest(
            self._host_id, state.mission_id, action.intent_id, action.intent_revision, action.id, prompt,
            self._workspace_id, self._repository_id, self._correlation_id_factory(), self._now(),
        )
        envelope = {"request": _request_document(request), "host_run_id": None}
        return self._store.transition(
            state.mission_id, MissionExecutionStatus.WAITING_FOR_EXECUTION, occurred_at=self._now(),
            reason="execution_request_persisted", actions=active, execution_correlation=envelope,
        )

    def _dispatch_or_recover(self, state: MissionExecutionState) -> MissionExecutionState:
        request = self._persisted_request(state)
        try:
            dispatch = self._host.recover_dispatch(request)
            if dispatch is None:
                dispatch = self._host.dispatch(request)
            if dispatch.request != request:
                raise MissionRunnerError("execution host acknowledgement did not preserve the persisted request")
        except Exception as error:  # Host errors must become durable terminal state.
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
        except Exception as error:  # Invalid evidence and host failures fail closed.
            return self._host_failure(state, "host_evidence_failed", error)
        evidence_document = _document(evidence)
        if evidence.outcome is ExecutionEvidenceOutcome.BLOCKED:
            return self._store.transition(state.mission_id, MissionExecutionStatus.BLOCKED, occurred_at=self._now(), reason="execution_blocked", actions=actions, execution_evidence=evidence_document)
        if evidence.outcome is ExecutionEvidenceOutcome.FAILED:
            return self._store.transition(state.mission_id, MissionExecutionStatus.FAILED, occurred_at=self._now(), reason="execution_failed", actions=actions, execution_evidence=evidence_document)
        if self._scheduler.progress(actions).is_complete:
            repository_truth = completion = None
            if self._completion_context is not None:
                repository_truth, completion = self._completion_context(state, evidence)
            return self._store.transition(state.mission_id, MissionExecutionStatus.COMPLETED, occurred_at=self._now(), reason="mission_completed", actions=actions, execution_evidence=evidence_document, repository_truth=repository_truth, completion=completion)
        if self._replan_after_evidence is not None:
            self._replan_after_evidence(state, actions, evidence)
        return self._store.transition(state.mission_id, MissionExecutionStatus.ACTIVE, occurred_at=self._now(), reason="execution_completed", actions=actions, execution_evidence=evidence_document)

    def _host_failure(self, state: MissionExecutionState, reference: str, _error: Exception) -> MissionExecutionState:
        return self._store.transition(
            state.mission_id, MissionExecutionStatus.FAILED, occurred_at=self._now(), reason=reference,
            execution_evidence={"outcome": "failed", "diagnostic_references": [f"runner:{reference}"]},
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
