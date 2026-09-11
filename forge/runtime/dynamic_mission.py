"""Public installed composition for one provider-derived Forge Mission.

The service intentionally composes existing Forge-owned governance, planning,
runtime, prompt, completion, and Execution Host boundaries.  It does not
create approvals, choose a repository revision, or implement an Action.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from types import SimpleNamespace
from typing import Any, Mapping
from uuid import uuid4

from forge.completion import MissionCompletionEvaluator
from forge.execution import ExecutionLoop
from forge.execution_host_configuration import EngineeringPlatformExecutionHostFactory
from forge.governance import ExecutionPolicy, ExecutionPolicyKind
from forge.governance_authority import CanonicalGovernanceRepository, MissionPlanningEvidenceEnvelope
from forge.intake import MissionIntake
from forge.models.action import EngineeringAction
from forge.models.action_derivation import DerivationPolicy, GovernanceRefinementRequired
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.mission_completion import (
    CanonicalExecutionEvidenceReference,
    MissionCompletionEvidence,
    MissionCriterionEvidenceBinding,
    RepositoryTruthReference,
    mission_criterion_id,
)
from forge.models.mission_planner import (
    ApprovedScope,
    MissionCriterionPlanningState,
    MissionPlannerInput,
    MissionPlanningState,
    PlanningEvidence,
    PlanningInputKind,
)
from forge.models.mission_completion import MissionCriterionEvaluationStatus
from forge.models.runtime_prompt import (
    ProviderPromptDefinition,
    RuntimePrompt,
    RuntimePromptSection,
    RuntimePromptSectionKind,
)
from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter
from forge.planner import (
    AIMissionPlanner,
    CodexCliChatGPTSessionPlanningProvider,
    CodexCliChatGPTSessionPlanningProviderConfiguration,
    MissionPlanner,
)
from forge.provider_security import PlanningProviderSecurityService
from forge.repository_truth import RepositoryTruthSnapshot
from forge.runtime.bootstrap import RuntimeBootstrap
from forge.runtime.service import ForgeRuntimeService
from forge.secure_store import MacOSKeychainSecureStoreAdapter
from forge.state import MissionExecutionState, MissionExecutionStatus, MissionStateStore


class InstalledDynamicMissionError(ValueError):
    """An installed Mission cannot safely enter or continue the public runtime."""


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class DynamicMissionRunResult:
    """Redacted result of one public start or resume tick."""

    mission_id: str
    runtime_id: str
    status: str
    action_ids: tuple[str, ...]
    current_action_id: str | None
    planning_invocations: int


class _InstalledMissionDispatcher:
    """Bind the existing loop to one selected installed Runtime Mission only."""

    def __init__(self, database: object, states: MissionStateStore, mission_id: str, clock) -> None:
        self._database, self._states, self._mission_id, self._clock = database, states, mission_id, clock

    def dispatch(self):
        state = self._states.get(self._mission_id)
        if state.status in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED,
                            MissionExecutionStatus.COMPLETED, MissionExecutionStatus.ARCHIVED}:
            return None
        row = self._database._connection.execute(
            "SELECT status, active_mission_id FROM dispatcher_state WHERE singleton = 1"
        ).fetchone()
        if row is not None and row["status"] == "ACTIVE" and row["active_mission_id"] != self._mission_id:
            raise InstalledDynamicMissionError("another Forge Mission is already active")
        if row is None or row["status"] != "ACTIVE":
            self._database.save_dispatcher_state(
                status="ACTIVE", mission_sequence=(self._mission_id,), active_mission_id=self._mission_id,
            )
        return SimpleNamespace(mission_id=self._mission_id)

    def resume(self):
        row = self._database._connection.execute(
            "SELECT status, active_mission_id FROM dispatcher_state WHERE singleton = 1"
        ).fetchone()
        if row is None or row["status"] != "ACTIVE" or row["active_mission_id"] != self._mission_id:
            return None
        return SimpleNamespace(mission_id=self._mission_id)

    def complete(self, mission_id: str):
        if mission_id != self._mission_id:
            raise InstalledDynamicMissionError("dispatcher completion does not match the selected Mission")
        self._database.save_dispatcher_state(status="IDLE", mission_sequence=(mission_id,))
        return None

    def hold(self, mission_id: str, status: MissionExecutionStatus) -> None:
        if mission_id != self._mission_id or status not in {MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED}:
            raise InstalledDynamicMissionError("dispatcher hold does not match the selected terminal Mission")

    def recover(self, mission_id: str):
        if mission_id != self._mission_id:
            raise InstalledDynamicMissionError("dispatcher recovery does not match the selected Mission")
        self._database.save_dispatcher_state(
            status="ACTIVE", mission_sequence=(mission_id,), active_mission_id=mission_id,
        )
        return SimpleNamespace(mission_id=mission_id)


class _OneActionProvider:
    """Keep the first serial canary to one active provider-derived Action."""

    def __init__(self, provider: object) -> None:
        self._provider = provider

    def derive_with_planning_input(self, snapshot, planning_input, derivation_policy):
        result = self._provider.derive_with_planning_input(snapshot, planning_input, derivation_policy)
        if isinstance(result, GovernanceRefinementRequired):
            return result
        if not isinstance(result, tuple) or len(result) != 1:
            raise InstalledDynamicMissionError("the serial installed Mission requires exactly one derived Action per invocation")
        return result


class InstalledDynamicMissionRuntime:
    """Installed, restart-safe composition for a canonically admitted Mission.

    ``admit`` creates only the zero-Action canonical Mission State.  ``start``
    performs read-only provider/host preflight before activating that exact
    state, and ``resume`` operates solely from the persisted state and request
    correlations.  Callers supply independently observed initial Repository
    Truth; Forge never substitutes a checkout or mutable local report for it.
    """

    def __init__(self, database: object, repository: CanonicalGovernanceRepository, *, data_root: str,
                 provider: object, host: object, clock=_now) -> None:
        self.database, self.repository = database, repository
        self.data_root, self.provider, self.host, self.clock = data_root, provider, host, clock
        self.states = MissionStateStore(database, data_root=data_root)
        self._initial_truth: dict[str, dict[str, str]] = {}

    @classmethod
    def open(cls, data_root: str, *, provider_id: str = "codex-chatgpt-session") -> "InstalledDynamicMissionRuntime":
        from forge._version import canonical_version

        database = RuntimeBootstrap(data_root=data_root, forge_version=canonical_version()).open()
        try:
            repository = CanonicalGovernanceRepository.for_runtime(
                database, MacOSGeneratedUIDIdentityAdapter().resolve, data_root=data_root,
            )
            security = PlanningProviderSecurityService(
                database, MacOSKeychainSecureStoreAdapter(), repository.operators,
            )
            configuration = CodexCliChatGPTSessionPlanningProviderConfiguration.from_canonical_session(
                security, provider_id,
            )
            provider = CodexCliChatGPTSessionPlanningProvider(configuration)
            host = EngineeringPlatformExecutionHostFactory().from_database(database)
            return cls(database, repository, data_root=data_root, provider=provider, host=host)
        except Exception:
            database.close()
            raise

    def close(self) -> None:
        self.database.close()

    def __enter__(self) -> "InstalledDynamicMissionRuntime":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def admit(self, mission: ArchitectureMission, envelope: MissionPlanningEvidenceEnvelope) -> MissionExecutionState:
        """Use canonical Mission Intake without creating an Action."""
        if mission.status is not ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING:
            raise InstalledDynamicMissionError("public Mission admission requires Architecture approval")
        if len(mission.scope) != 1:
            raise InstalledDynamicMissionError("the serial installed Mission requires exactly one approved scope")
        state = MissionIntake(self.states, self.clock).admit_canonical_approved_mission(
            mission, envelope, self.repository,
        )
        if state.actions or state.intents or state.status is not MissionExecutionStatus.APPROVED_PLANNABLE:
            raise InstalledDynamicMissionError("canonical Mission Intake did not preserve zero-Action planning state")
        return state

    def preflight(self) -> dict[str, object]:
        """Perform only the configured Codex and EP read-only capability checks."""
        provider_preflight = getattr(self.provider, "preflight", None)
        readiness = provider_preflight() if callable(provider_preflight) else None
        if readiness is not None and not getattr(readiness, "ready", False):
            raise InstalledDynamicMissionError("configured Codex planning session is not ready")
        declaration = self.host.preflight()
        return {
            "provider": "READY" if readiness is None else getattr(getattr(readiness, "state", None), "value", "READY"),
            "execution_host": "PASS",
            "declaration": declaration,
        }

    def start(self, mission_id: str, initial_repository_truth: RepositoryTruthSnapshot) -> DynamicMissionRunResult:
        """Start exactly one admitted zero-Action Mission after read-only preflight."""
        self._assert_single_resumable(mission_id)
        state = self.states.get(mission_id)
        if state.status is not MissionExecutionStatus.APPROVED_PLANNABLE:
            raise InstalledDynamicMissionError("public start requires a canonically admitted zero-Action Mission")
        truth = self._truth_from_snapshot(initial_repository_truth)
        self._assert_repository_scope(initial_repository_truth)
        self.preflight()
        self._initial_truth[mission_id] = truth
        self.states.transition(
            mission_id, MissionExecutionStatus.CREATED, occurred_at=self.clock(),
            reason="public_installed_dynamic_mission_start", repository_truth=truth,
        )
        return self._tick(mission_id)

    def resume(self, mission_id: str) -> DynamicMissionRunResult:
        """Continue the same Mission and persisted host correlation after reopen."""
        self._assert_single_resumable(mission_id)
        state = self.states.get(mission_id)
        if state.status is MissionExecutionStatus.APPROVED_PLANNABLE:
            raise InstalledDynamicMissionError("admitted Mission must be started before it can resume")
        if state.repository_truth is None:
            raise InstalledDynamicMissionError("resumed Mission lacks canonical Repository Truth")
        self._initial_truth[mission_id] = dict(state.repository_truth)
        self.preflight()
        return self._tick(mission_id)

    def _tick(self, mission_id: str) -> DynamicMissionRunResult:
        loop = self._loop(mission_id)
        ForgeRuntimeService(loop, self.states, runtime_database=self.database).tick()
        return self._result(self.states.get(mission_id))

    def _loop(self, mission_id: str) -> ExecutionLoop:
        config = self.host.config
        state = self.states.get(mission_id)
        contract = self._admission_contract(state)
        planning = contract["planning"]
        policy = DerivationPolicy(
            tuple(planning["write_scopes"]), tuple(planning["human_gates"]), tuple(planning["risk_inputs"]),
        )
        return ExecutionLoop(
            _InstalledMissionDispatcher(self.database, self.states, mission_id, self.clock), self.states,
            MissionPlanner(), self.host, self._planning_input,
            lambda intent, action: self._prompt(mission_id, intent, action), self._repository_truth,
            host_id=config.host_id, workspace_id=config.project_id, repository_id=config.repository_id,
            repository_identity=config.repository_identity, clock=self.clock,
            correlation_id_factory=lambda: "forge-runtime-" + str(uuid4()),
            execution_policy=ExecutionPolicy(ExecutionPolicyKind.CONTINUOUS),
            ai_planner=AIMissionPlanner(_OneActionProvider(self.provider)), derivation_policy=policy,
            completion_evidence=self._completion_evidence,
            completion_evaluator=MissionCompletionEvaluator(),
        )

    def _planning_input(self, state: MissionExecutionState) -> MissionPlannerInput:
        mission = ArchitectureMission.from_dict(dict(state.mission))
        contract = self._admission_contract(state)
        planning = contract["planning"]
        truth = state.repository_truth or self._initial_truth.get(state.mission_id)
        if truth is None:
            raise InstalledDynamicMissionError("Mission planning requires canonical Repository Truth")
        evidence: list[PlanningEvidence] = [
            PlanningEvidence(PlanningInputKind.MISSION_STATE, f"mission-state:{state.mission_id}:{state.revision}",
                             str(state.revision), f"runtime://mission/{state.mission_id}/{state.revision}",
                             _digest(self.states._as_document(state))),
            PlanningEvidence(PlanningInputKind.REPOSITORY_TRUTH, str(truth["source_id"]), str(truth["revision"]),
                             str(truth["locator"]), str(truth["content_digest"])),
            PlanningEvidence(PlanningInputKind.ARCHITECTURE_REVIEW, str(contract["architecture_decision_id"]),
                             str(contract["subject_revision"]),
                             f"runtime://governance/{contract['architecture_decision_id']}",
                             _digest(planning)),
            PlanningEvidence(PlanningInputKind.CAPABILITY_CATALOGUE,
                             f"mission-capability:{mission.required_capabilities[0]}",
                             str(contract["subject_revision"]), f"runtime://mission/{mission.id}/capability",
                             _digest({"capability": mission.required_capabilities[0], "mission": mission.id})),
        ]
        if state.execution_history:
            latest = state.execution_history[-1]
            repository = latest.get("repository_evidence")
            if not isinstance(repository, Mapping) or latest.get("outcome") != "complete":
                raise InstalledDynamicMissionError("dynamic replanning requires canonical complete Host evidence")
            receipt_id = latest.get("receipt_id")
            if not isinstance(receipt_id, str) or not receipt_id:
                raise InstalledDynamicMissionError("dynamic replanning evidence lacks a host receipt identity")
            evidence.append(PlanningEvidence(
                PlanningInputKind.EXECUTION_EVIDENCE, receipt_id, str(state.revision),
                f"runtime://execution/{receipt_id}", str(repository["content_digest"]),
            ))
        references = (self._architecture_reference(contract),)
        scopes = tuple(
            ApprovedScope(scope, mission.required_capabilities[0], references, (), allow_provider_derivation=True)
            for scope in mission.scope
        )
        criteria = () if state.completion is None else tuple(
            item for item in state.completion.get("criteria", ()) if isinstance(item, Mapping)
        )
        criterion_states = tuple(
            MissionCriterionPlanningState(
                str(item["criterion_id"]), MissionCriterionEvaluationStatus(str(item["status"])),
            ) for item in criteria
        )
        completed = tuple(sorted(str(item["id"]) for item in state.actions if item["status"] == "COMPLETE"))
        blocked = tuple(sorted(str(item["id"]) for item in state.actions if item["status"] in {"BLOCKED", "FAILED"}))
        return MissionPlannerInput(
            mission, MissionPlanningState(mission.id, state.revision, completed, blocked, criterion_states),
            tuple(evidence), scopes,
        )

    @staticmethod
    def _architecture_reference(contract: Mapping[str, Any]):
        from forge.models.intent import IntentReference
        return IntentReference("architecture-decision", str(contract["subject_revision"]),
                               f"runtime://governance/{contract['architecture_decision_id']}")

    def _prompt(self, mission_id: str, intent: Mapping[str, Any], action: EngineeringAction) -> RuntimePrompt:
        state = self.states.get(mission_id)
        mission = ArchitectureMission.from_dict(dict(state.mission))
        contract = self._admission_contract(state)
        truth = state.repository_truth
        if truth is None:
            raise InstalledDynamicMissionError("Runtime Prompt generation requires canonical Repository Truth")
        source = {
            "mission": mission.to_dict(), "intent": dict(intent), "action": asdict(action),
            "repository_truth": dict(truth), "planning": contract["planning"],
        }
        sections = (
            RuntimePromptSection(RuntimePromptSectionKind.CONTEXT, (f"Mission {mission.id}: {mission.title}",)),
            RuntimePromptSection(RuntimePromptSectionKind.OBJECTIVE, (action.objective,)),
            RuntimePromptSection(RuntimePromptSectionKind.REPOSITORY, (
                f"Repository {self.host.config.repository_id} at {truth['revision']}",
            )),
            RuntimePromptSection(RuntimePromptSectionKind.CONSTRAINTS, tuple(mission.engineering_constraints)),
            RuntimePromptSection(RuntimePromptSectionKind.VALIDATION, tuple(action.expected_evidence)),
            RuntimePromptSection(RuntimePromptSectionKind.DELIVERABLES, tuple(action.expected_evidence)),
        )
        return RuntimePrompt(
            f"forge-runtime-prompt:{_digest(source)[7:]}", action.intent_id, action.intent_revision, action.id,
            ProviderPromptDefinition("forge-installed-dynamic-runtime", "1.0"), _digest(source), sections,
            mission_id=mission.id,
            execution_metadata=(("mission_revision", str(contract["subject_revision"])),),
        )

    @staticmethod
    def _repository_truth(state: MissionExecutionState, evidence: object) -> Mapping[str, Any]:
        if evidence is None:
            if state.repository_truth is None:
                raise InstalledDynamicMissionError("initial Mission planning lacks canonical Repository Truth")
            return dict(state.repository_truth)
        repository = getattr(evidence, "repository_evidence", None)
        receipt_id = getattr(evidence, "receipt_id", None)
        report_id = getattr(evidence, "report_id", None)
        if not repository or not receipt_id or not report_id or not repository.repository_revision:
            raise InstalledDynamicMissionError("terminal Host evidence lacks repository provenance")
        return {
            "source_id": f"execution-receipt:{receipt_id}", "revision": repository.repository_revision,
            "locator": f"execution-host://{getattr(evidence, 'host_id')}/{report_id}",
            "content_digest": repository.content_digest,
        }

    @staticmethod
    def _completion_evidence(state: MissionExecutionState, evidence: object,
                             repository_truth: Mapping[str, Any]) -> MissionCompletionEvidence | None:
        mission = ArchitectureMission.from_dict(dict(state.mission))
        current = asdict(evidence)
        current["outcome"] = getattr(evidence, "outcome").value
        documents = (*state.execution_history, current)
        references: list[CanonicalExecutionEvidenceReference] = []
        for document in documents:
            repository = document.get("repository_evidence")
            if document.get("outcome") != "complete" or not isinstance(repository, Mapping):
                continue
            try:
                references.append(CanonicalExecutionEvidenceReference(
                    str(document["receipt_id"]), str(repository["action_id"]), str(document["report_id"]),
                    str(repository["repository_revision"]), str(repository["content_digest"]),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        if not references:
            return None
        truth = RepositoryTruthReference(
            str(repository_truth["source_id"]), str(repository_truth["revision"]),
            str(repository_truth["locator"]), str(repository_truth["content_digest"]),
        )
        bindings = tuple(
            MissionCriterionEvidenceBinding(mission_criterion_id(mission.id, criterion), tuple(references), truth)
            for criterion in mission.acceptance_criteria
        )
        return MissionCompletionEvidence(mission.id, _digest(mission.to_dict()), bindings)

    def _assert_repository_scope(self, snapshot: RepositoryTruthSnapshot) -> None:
        if snapshot.repository_id != self.host.config.repository_id:
            raise InstalledDynamicMissionError("initial Repository Truth does not match the configured EP repository")

    @staticmethod
    def _truth_from_snapshot(snapshot: RepositoryTruthSnapshot) -> dict[str, str]:
        return {
            "source_id": snapshot.id, "revision": snapshot.repository_revision,
            "locator": f"repository://{snapshot.repository_id}/{snapshot.repository_revision}",
            "content_digest": snapshot.content_digest,
        }

    @staticmethod
    def _admission_contract(state: MissionExecutionState) -> Mapping[str, Any]:
        contract = state.admission_contract
        required = ("planning", "architecture_decision_id", "subject_revision", "envelope_digest")
        if not isinstance(contract, Mapping) or any(not contract.get(item) for item in required):
            raise InstalledDynamicMissionError("Mission lacks its canonical admission contract")
        planning = contract["planning"]
        if not isinstance(planning, Mapping) or any(not planning.get(item) for item in (
            "write_scopes", "human_gates", "risk_inputs",
        )):
            raise InstalledDynamicMissionError("Mission admission planning authority is incomplete")
        return contract

    def _assert_single_resumable(self, mission_id: str) -> None:
        active = tuple(state.mission_id for state in self.states.resumable())
        if active != (mission_id,):
            raise InstalledDynamicMissionError("public runtime requires exactly one selected non-terminal Mission")

    def _result(self, state: MissionExecutionState) -> DynamicMissionRunResult:
        current = state.current_engineering_action or {}
        invocations = sum(1 for item in state.planning_history if item.get("derivation_id"))
        return DynamicMissionRunResult(
            state.mission_id, self.database.runtime_identity.runtime_id, state.status.value,
            tuple(str(item["id"]) for item in state.actions), current.get("id"), invocations,
        )
