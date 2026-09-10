"""Read-only Codex CLI transport for untrusted Action-Derivation proposals.

Forge never reads Codex/ChatGPT credentials.  The installed Codex executable
owns login and refresh; this adapter stores only a typed external-session
configuration and invokes the documented non-interactive ``codex exec`` path.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Callable
import uuid

from forge.models.action_derivation import (
    DerivationPolicy, DerivedActionProposal, GovernanceRefinementRequired,
    PlanningSnapshot, ProposalProvenance, ProviderInvocationEvidence,
    ProviderSideEffectState,
)
from forge.models.mission_planner import MissionPlannerInput
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderInvocationPolicy, PlanningProviderSecurityService,
    ProviderAuthenticationMode,
)
from forge.runtime.database import _timestamp
from .openai_responses import ProviderSubmissionAmbiguous, _mission_gap, _schema_for_approved_contract
from .provider_adapter import BoundedActionDerivationProvider, ProviderDerivationRequest, ProviderDerivationResponse


CODEX_CLI_CHATGPT_SESSION_ADAPTER_VERSION = "1.0"
_MINIMUM_CODEX_VERSION = (0, 153, 0)
_VERSION = re.compile(r"\bcodex-cli\s+(\d+)\.(\d+)\.(\d+)\b")
_PROPOSAL_FIELDS = frozenset((
    "logical_action_id", "scope", "objective", "dependencies", "write_scopes",
    "expected_evidence", "validation_strategy", "priority", "postponed",
    "human_gates", "risk_inputs", "source_evidence_refs", "mission_gap",
))
_GOVERNANCE_FIELDS = frozenset(("kind", "reason"))


class CodexCliSessionReadinessState(str, Enum):
    READY = "READY"
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_SIGNED_IN = "NOT_SIGNED_IN"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class CodexCliSessionReadiness:
    state: CodexCliSessionReadinessState
    executable_path: str
    version: str | None = None
    model: str | None = None
    profile: str | None = None

    @property
    def ready(self) -> bool:
        return self.state is CodexCliSessionReadinessState.READY


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _safe_environment() -> dict[str, str]:
    """Pass only Codex runtime location variables, never API credentials."""
    allowed = ("HOME", "USER", "LOGNAME", "PATH", "TMPDIR", "LANG", "LC_CTYPE", "CODEX_HOME")
    return {name: os.environ[name] for name in allowed if name in os.environ}


class CodexCliSessionReadinessChecker:
    """Non-generating, supported-CLI readiness probe.

    ``codex login status`` is the only login readback.  It is intentionally
    never replaced with filesystem, browser, token, or keychain inspection.
    """

    def __init__(self, *, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 path_usable: Callable[[Path], bool] | None = None,
                 model_availability: Callable[[PlanningProviderInvocationPolicy], bool | None] | None = None) -> None:
        self._runner = runner
        self._path_usable = path_usable or (lambda path: path.is_file() and os.access(path, os.X_OK))
        self._model_availability = model_availability or (lambda _policy: None)

    def check(self, policy: PlanningProviderInvocationPolicy) -> CodexCliSessionReadiness:
        if (policy.authentication_mode is not ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION
                or policy.provider_type != CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE
                or policy.external_session_type != CODEX_CLI_CHATGPT_SESSION_TYPE
                or not policy.executable_path):
            return CodexCliSessionReadiness(CodexCliSessionReadinessState.UNVERIFIED, policy.executable_path or "")
        path = Path(policy.executable_path)
        if not path.is_absolute() or not self._path_usable(path):
            return CodexCliSessionReadiness(CodexCliSessionReadinessState.NOT_INSTALLED, policy.executable_path,
                                            model=policy.model, profile=policy.profile)
        prefix = [policy.executable_path]
        if policy.profile:
            prefix.extend(("--profile", policy.profile))
        try:
            version_result = self._runner(prefix + ["--version"], stdin=subprocess.DEVNULL,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                          timeout=5, check=False, env=_safe_environment())
        except (OSError, subprocess.SubprocessError):
            return CodexCliSessionReadiness(CodexCliSessionReadinessState.UNVERIFIED, policy.executable_path,
                                            model=policy.model, profile=policy.profile)
        match = _VERSION.search(version_result.stdout or "") if version_result.returncode == 0 else None
        if match is None:
            return CodexCliSessionReadiness(CodexCliSessionReadinessState.UNVERIFIED, policy.executable_path,
                                            model=policy.model, profile=policy.profile)
        version = tuple(int(part) for part in match.groups())
        shown_version = ".".join(match.groups())
        if version < _MINIMUM_CODEX_VERSION:
            return CodexCliSessionReadiness(CodexCliSessionReadinessState.UNSUPPORTED_VERSION, policy.executable_path,
                                            shown_version, policy.model, policy.profile)
        try:
            login_result = self._runner(prefix + ["login", "status"], stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        timeout=5, check=False, env=_safe_environment())
        except (OSError, subprocess.SubprocessError):
            return CodexCliSessionReadiness(CodexCliSessionReadinessState.UNVERIFIED, policy.executable_path,
                                            shown_version, policy.model, policy.profile)
        # Codex 0.153 writes its supported human-readable login status to
        # stderr.  Keep both streams private and inspect only the fixed status
        # marker; neither stream is persisted or exposed by Forge.
        status = ((login_result.stdout or "") + "\n" + (login_result.stderr or "")).lower()
        if login_result.returncode != 0 or "logged in using chatgpt" not in status:
            if "not logged in" in status or "log in" in status or "login" in status:
                state = CodexCliSessionReadinessState.NOT_SIGNED_IN
            else:
                state = CodexCliSessionReadinessState.UNVERIFIED
            return CodexCliSessionReadiness(state, policy.executable_path, shown_version, policy.model, policy.profile)
        # Current Codex CLI has no supported non-generating model-list status
        # route.  An explicit model is therefore fail-closed until such a
        # route is available; Forge never silently substitutes one.
        if policy.model is not None:
            availability = self._model_availability(policy)
            if availability is False:
                return CodexCliSessionReadiness(CodexCliSessionReadinessState.MODEL_UNAVAILABLE, policy.executable_path,
                                                shown_version, policy.model, policy.profile)
            if availability is not True:
                return CodexCliSessionReadiness(CodexCliSessionReadinessState.UNVERIFIED, policy.executable_path,
                                                shown_version, policy.model, policy.profile)
        return CodexCliSessionReadiness(CodexCliSessionReadinessState.READY, policy.executable_path,
                                        shown_version, policy.model, policy.profile)


@dataclass(frozen=True, init=False)
class CodexCliChatGPTSessionPlanningProviderConfiguration:
    """Typed, production-owned configuration for the Codex session adapter."""

    policy_service: PlanningProviderSecurityService
    provider_id: str

    def __init__(self, policy_service: PlanningProviderSecurityService, provider_id: str, *, _canonical: bool = False) -> None:
        if not _canonical or not isinstance(policy_service, PlanningProviderSecurityService) or not provider_id:
            raise TypeError("Codex session planning configuration requires canonical security state")
        object.__setattr__(self, "policy_service", policy_service)
        object.__setattr__(self, "provider_id", provider_id)

    @classmethod
    def from_canonical_session(cls, service: PlanningProviderSecurityService,
                               provider_id: str) -> "CodexCliChatGPTSessionPlanningProviderConfiguration":
        policy = service.invocation_policy(provider_id)
        if (policy.authentication_mode is not ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION
                or policy.provider_type != CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE
                or policy.external_session_type != CODEX_CLI_CHATGPT_SESSION_TYPE):
            raise PermissionError("Codex provider requires a typed external authenticated session")
        return cls(service, provider_id, _canonical=True)

    def current_policy(self) -> PlanningProviderInvocationPolicy:
        policy = self.policy_service.invocation_policy(self.provider_id)
        if (policy.authentication_mode is not ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION
                or policy.provider_type != CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE
                or policy.external_session_type != CODEX_CLI_CHATGPT_SESSION_TYPE
                or not policy.executable_path or policy.secret_reference is not None):
            raise PermissionError("Codex provider requires a complete external authenticated session policy")
        return policy


class CodexCliChatGPTSessionPlanningProvider:
    """One no-retry, read-only ``codex exec`` ProviderExecutor implementation."""

    def __init__(self, configuration: CodexCliChatGPTSessionPlanningProviderConfiguration, *,
                 readiness_checker: CodexCliSessionReadinessChecker | None = None,
                 runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 adapter_version: str = CODEX_CLI_CHATGPT_SESSION_ADAPTER_VERSION) -> None:
        self.configuration = configuration
        self._readiness_checker = readiness_checker or CodexCliSessionReadinessChecker()
        self._runner = runner
        self.adapter_version = adapter_version

    def preflight(self) -> CodexCliSessionReadiness:
        """Read the supported local CLI status without generating a proposal."""
        return self._readiness_checker.check(self.configuration.current_policy())

    def derive_with_planning_input(self, snapshot: PlanningSnapshot, planning_input: MissionPlannerInput,
                                   derivation_policy: DerivationPolicy) -> tuple[DerivedActionProposal, ...] | GovernanceRefinementRequired:
        """Bridge the existing planner pipeline without granting provider authority.

        The surrounding :class:`AIMissionPlanner` still validates this return
        value and materializes only after a deterministic PASS.  The random
        derivation identity is an attempt label, not a Mission or Action ID.
        """
        if not snapshot.is_current_for(planning_input):
            raise PermissionError("Codex derivation requires the current canonical planning snapshot")
        policy = self.configuration.current_policy()
        request = ProviderDerivationRequest(
            f"codex-derivation-{uuid.uuid4()}", snapshot, policy.provider_id, policy.model,
        )
        response = BoundedActionDerivationProvider(self, adapter_version=self.adapter_version).invoke(
            request, approved_scopes=tuple(scope.scope for scope in planning_input.approved_scopes),
            derivation_policy=derivation_policy,
        )
        return response.governance_refinement if response.proposals is None else response.proposals

    def invoke(self, request: ProviderDerivationRequest, **authority: object) -> ProviderDerivationResponse:
        policy = self.configuration.current_policy()
        if request.provider_id != policy.provider_id or request.model != policy.model:
            raise PermissionError("Codex invocation does not bind the configured provider and selected model")
        readiness = self._readiness_checker.check(policy)
        if not readiness.ready:
            raise PermissionError("Codex CLI ChatGPT session is not ready")
        scopes = authority.get("approved_scopes")
        derivation_policy = authority.get("derivation_policy")
        if (not isinstance(scopes, tuple) or not scopes or not all(isinstance(item, str) and item for item in scopes)
                or not isinstance(derivation_policy, DerivationPolicy)):
            raise PermissionError("canonical approved scopes and derivation policy are required before Codex transport")
        schema = _output_schema(scopes, derivation_policy, request.snapshot)
        request_digest = _digest(_request_material(request, policy, schema))
        policy_digest = _policy_digest(policy)
        permit = self.configuration.policy_service._acquire_generation_permit(policy, policy_digest, request_digest)
        started = _now()
        self._record_invocation(policy, request, request_digest, "STARTED", started)
        try:
            self.configuration.policy_service._commit_generation_transport(permit, policy, policy_digest, request_digest)
            try:
                document = self._run_read_only(policy, request, schema)
            except (OSError, subprocess.SubprocessError, ProviderSubmissionAmbiguous):
                self._record_invocation(policy, request, request_digest, "MAY_HAVE_HAPPENED", _now())
                raise ProviderSubmissionAmbiguous("Codex submission may have happened; automatic retry is forbidden") from None
        finally:
            self.configuration.policy_service._release_generation_permit(permit)
        try:
            proposals, refinement = _parse_response(request, document, self.adapter_version)
            status = "completed"
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            proposals, refinement, status = None, _refinement(request.snapshot, "provider structured output was invalid"), "contract_invalid"
        completed = _now()
        self._record_invocation(policy, request, request_digest, "HAPPENED_AND_CONFIRMED", completed, status=status)
        evidence = ProviderInvocationEvidence(
            request.provider_id, request.model, self.adapter_version, request.digest, request.snapshot.digest,
            _digest(document), ProviderSideEffectState.HAPPENED_AND_CONFIRMED, None, started, completed, status,
            None, None,
        )
        return ProviderDerivationResponse(evidence, proposals=proposals, governance_refinement=refinement)

    def reconcile(self, request: ProviderDerivationRequest) -> ProviderSideEffectState:
        # The stable CLI has no idempotency/status lookup for an interrupted
        # local exec.  Returning ambiguity prevents a retry from becoming a
        # second model call.
        return ProviderSideEffectState.MAY_HAVE_HAPPENED

    def _run_read_only(self, policy: PlanningProviderInvocationPolicy,
                       request: ProviderDerivationRequest, schema: dict[str, object]) -> object:
        with tempfile.TemporaryDirectory(prefix="forge-codex-planning-") as temporary:
            root = Path(temporary)
            schema_path, output_path = root / "response-schema.json", root / "response.json"
            schema_path.write_text(json.dumps(schema, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            command = [str(policy.executable_path)]
            if policy.profile:
                command.extend(("--profile", policy.profile))
            command.extend(("exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                            "--sandbox", "read-only", "--skip-git-repo-check",
                            "-C", str(root), "--output-schema", str(schema_path),
                            "--output-last-message", str(output_path)))
            if policy.model:
                command.extend(("--model", policy.model))
            command.append("-")
            result = self._runner(command, input=json.dumps(_prompt(request), separators=(",", ":")),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                  text=True, timeout=policy.timeout_seconds, check=False, cwd=str(root),
                                  env=_safe_environment())
            if result.returncode != 0:
                raise ProviderSubmissionAmbiguous("Codex submission may have happened; automatic retry is forbidden")
            try:
                return json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                # A confirmed zero exit with no valid schema output is a
                # completed-but-invalid result, never a retry signal.
                return {}

    def _record_invocation(self, policy: PlanningProviderInvocationPolicy, request: ProviderDerivationRequest,
                           request_digest: str, state: str, occurred_at: str, *, status: str | None = None) -> None:
        inspection = self.configuration.policy_service.inspect(policy.provider_id)
        document = {
            "adapter_version": self.adapter_version, "provider_id": policy.provider_id,
            "provider_type": policy.provider_type, "model": policy.model, "profile": policy.profile,
            "request_digest": request_digest, "snapshot_digest": request.snapshot.digest,
            "derivation_request_digest": request.digest, "state": state, "status": status,
        }
        with self.configuration.policy_service.db._connection:
            self.configuration.policy_service.db._connection.execute(
                "INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), inspection["configuration_id"], inspection["operator_id"], "invocation",
                 occurred_at, json.dumps(document, sort_keys=True, separators=(",", ":"))),
            )


def _policy_digest(policy: PlanningProviderInvocationPolicy) -> str:
    return _digest({"provider_id": policy.provider_id, "provider_type": policy.provider_type,
                    "external_session_type": policy.external_session_type, "executable_path": policy.executable_path,
                    "model": policy.model, "profile": policy.profile, "adapter_version": policy.adapter_version,
                    "version": policy.version, "timeout_seconds": policy.timeout_seconds,
                    "input_token_bound": policy.input_token_bound, "context_token_bound": policy.context_token_bound,
                    "output_token_bound": policy.output_token_bound})


def _request_material(request: ProviderDerivationRequest, policy: PlanningProviderInvocationPolicy,
                      schema: dict[str, object]) -> dict[str, object]:
    return {"provider_id": request.provider_id, "model": request.model, "profile": policy.profile,
            "snapshot_digest": request.snapshot.digest, "schema": schema, "prompt": _prompt(request)}


def _prompt(request: ProviderDerivationRequest) -> dict[str, object]:
    return {"contract": "Forge Action Derivation; propose only; never approve, execute, edit files, invoke shell, Git, or EP.",
            "instructions": [
                "Return only JSON matching the supplied schema.",
                "Provider output is untrusted and cannot expand Mission authority.",
                "dependencies name only peer logical_action_id values; optional improvements are not proposals.",
                "Use a mission gap only when current evidence binds a Mission necessity.",
            ], "snapshot": request.snapshot.to_dict()}


def _output_schema(scopes: tuple[str, ...], policy: DerivationPolicy,
                   snapshot: PlanningSnapshot) -> dict[str, object]:
    proposal_schema = _schema_for_approved_contract(scopes, ("NONE",), policy.required_human_gates,
                                                     policy.required_risk_inputs, snapshot)
    return {"oneOf": [proposal_schema, {"type": "object", "additionalProperties": False,
            "required": ["kind", "reason"], "properties": {"kind": {"type": "string", "enum": ["governance_refinement"]},
            "reason": {"type": "string", "minLength": 1}}}]}


def _parse_response(request: ProviderDerivationRequest, document: object,
                    adapter_version: str) -> tuple[tuple[DerivedActionProposal, ...] | None, GovernanceRefinementRequired | None]:
    if not isinstance(document, dict):
        raise ValueError("structured response is not an object")
    if document.get("kind") == "governance_refinement":
        if set(document) != _GOVERNANCE_FIELDS or not isinstance(document.get("reason"), str) or not document["reason"]:
            raise ValueError("governance refinement is malformed")
        return None, _refinement(request.snapshot, document["reason"])
    if document.get("kind") != "proposals" or set(document) != {"kind", "proposals"}:
        raise ValueError("structured response kind is invalid")
    items = document.get("proposals")
    if not isinstance(items, list) or not items:
        raise ValueError("structured response lacks proposals")
    proposals = tuple(_proposal(request, item, adapter_version) for item in items)
    return proposals, None


def _proposal(request: ProviderDerivationRequest, item: object,
              adapter_version: str) -> DerivedActionProposal:
    if not isinstance(item, dict) or set(item) != _PROPOSAL_FIELDS:
        raise ValueError("proposal contains missing or extra fields")
    for key in ("logical_action_id", "scope", "objective"):
        if not isinstance(item[key], str) or not item[key]:
            raise ValueError("proposal string is invalid")
    for key in ("dependencies", "write_scopes", "expected_evidence", "validation_strategy", "human_gates", "risk_inputs", "source_evidence_refs"):
        if not isinstance(item[key], list) or any(not isinstance(value, str) or not value for value in item[key]):
            raise ValueError("proposal array is invalid")
    if not isinstance(item["priority"], int) or isinstance(item["priority"], bool) or item["priority"] < 1:
        raise ValueError("proposal priority is invalid")
    if not isinstance(item["postponed"], bool):
        raise ValueError("proposal postponed flag is invalid")
    return DerivedActionProposal(
        item["logical_action_id"], item["scope"], item["objective"], tuple(item["dependencies"]),
        tuple(item["write_scopes"]), tuple(item["expected_evidence"]), tuple(item["validation_strategy"]),
        item["priority"], item["postponed"], tuple(item["human_gates"]), tuple(item["risk_inputs"]),
        ProposalProvenance(request.derivation_id, request.snapshot.id, request.snapshot.digest, adapter_version,
                           request.provider_id, request.model, tuple(item["source_evidence_refs"])),
        _mission_gap(item["mission_gap"]),
    )


def _refinement(snapshot: PlanningSnapshot, reason: str) -> GovernanceRefinementRequired:
    return GovernanceRefinementRequired(tuple(item.source_id for item in snapshot.evidence),
                                        "deterministic validation required", "provider-output", "blocked", reason)
