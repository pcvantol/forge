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
import time
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
_LOCAL_ARGUMENT_REJECTION = re.compile(
    r"(?:unexpected argument|unrecognized (?:argument|option)|unknown (?:argument|option)|"
    r"invalid value .*--(?:output-schema|sandbox)|failed to (?:read|parse) .*schema|"
    r"(?:output|json) schema .*?(?:invalid|unsupported|must be))",
    re.IGNORECASE,
)
_TERMINAL_EVENT_TYPES = frozenset(("turn.completed", "turn.failed", "error"))


class CodexCliSessionReadinessState(str, Enum):
    READY = "READY"
    NOT_INSTALLED = "NOT_INSTALLED"
    NOT_SIGNED_IN = "NOT_SIGNED_IN"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    UNVERIFIED = "UNVERIFIED"


class CodexCliInvocationClassification(str, Enum):
    """The bounded, durable result of one local Codex process attempt."""

    NOT_STARTED = "NOT_STARTED"
    REJECTED_BEFORE_GENERATION = "REJECTED_BEFORE_GENERATION"
    MAY_HAVE_HAPPENED = "MAY_HAVE_HAPPENED"
    COMPLETED_CONTRACT_INVALID = "COMPLETED_CONTRACT_INVALID"
    COMPLETED_VALID = "COMPLETED_VALID"


@dataclass(frozen=True)
class CodexCliInvocationDiagnostic:
    """Secret-free process evidence retained before the temporary directory dies.

    This deliberately records categories and structured event names only.  It
    never persists stderr, the prompt, a model response, command arguments, or
    credential-bearing environment values.
    """

    classification: CodexCliInvocationClassification
    process_started: bool
    exception_type: str | None = None
    errno: int | None = None
    timed_out: bool = False
    elapsed_milliseconds: int | None = None
    returncode: int | None = None
    error_category: str | None = None
    terminal_events: tuple[str, ...] = ()

    def document(self) -> dict[str, object]:
        return {
            "classification": self.classification.value,
            "process_started": self.process_started,
            "exception_type": self.exception_type,
            "errno": self.errno,
            "timed_out": self.timed_out,
            "elapsed_milliseconds": self.elapsed_milliseconds,
            "returncode": self.returncode,
            "error_category": self.error_category,
            "terminal_events": list(self.terminal_events),
        }


@dataclass(frozen=True)
class _CodexCliRunResult:
    document: object | None
    diagnostic: CodexCliInvocationDiagnostic


class CodexCliInvocationRejected(RuntimeError):
    """A local process failure was proven to precede model generation."""

    def __init__(self, diagnostic: CodexCliInvocationDiagnostic) -> None:
        message = ("Codex process did not start" if diagnostic.classification is CodexCliInvocationClassification.NOT_STARTED
                   else "Codex rejected the local request before generation")
        super().__init__(message)
        self.diagnostic = diagnostic


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
                 adapter_version: str = CODEX_CLI_CHATGPT_SESSION_ADAPTER_VERSION,
                 temporary_directory: Callable[..., object] = tempfile.TemporaryDirectory) -> None:
        self.configuration = configuration
        self._readiness_checker = readiness_checker or CodexCliSessionReadinessChecker()
        self._runner = runner
        self.adapter_version = adapter_version
        self._temporary_directory = temporary_directory

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
            run = self._run_read_only(policy, request, schema)
        finally:
            self.configuration.policy_service._release_generation_permit(permit)
        if run.diagnostic.classification is CodexCliInvocationClassification.NOT_STARTED:
            self._record_invocation(policy, request, request_digest, "NOT_STARTED", _now(), diagnostic=run.diagnostic)
            raise CodexCliInvocationRejected(run.diagnostic)
        if run.diagnostic.classification is CodexCliInvocationClassification.REJECTED_BEFORE_GENERATION:
            self._record_invocation(policy, request, request_digest, "REJECTED_BEFORE_GENERATION", _now(), diagnostic=run.diagnostic)
            raise CodexCliInvocationRejected(run.diagnostic)
        if run.diagnostic.classification is CodexCliInvocationClassification.MAY_HAVE_HAPPENED:
            self._record_invocation(policy, request, request_digest, "MAY_HAVE_HAPPENED", _now(), diagnostic=run.diagnostic)
            raise ProviderSubmissionAmbiguous("Codex submission may have happened; automatic retry is forbidden")
        document = run.document
        if document is None:
            raise RuntimeError("confirmed Codex result is missing its structured document")
        try:
            proposals, refinement = _parse_response(request, document, self.adapter_version)
            status = "completed"
            diagnostic = _replace_diagnostic(run.diagnostic, CodexCliInvocationClassification.COMPLETED_VALID)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            proposals, refinement, status = None, _refinement(request.snapshot, "provider structured output was invalid"), "contract_invalid"
            diagnostic = _replace_diagnostic(run.diagnostic, CodexCliInvocationClassification.COMPLETED_CONTRACT_INVALID)
        completed = _now()
        self._record_invocation(policy, request, request_digest, "HAPPENED_AND_CONFIRMED", completed,
                                status=status, diagnostic=diagnostic, result_digest=_digest(document))
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
                       request: ProviderDerivationRequest, schema: dict[str, object]) -> _CodexCliRunResult:
        """Run once and reduce all local output to bounded, non-secret evidence."""
        began = time.monotonic()
        try:
            temporary = self._temporary_directory(prefix="forge-codex-planning-")
            root = Path(temporary.name)
        except OSError as error:
            # No temporary working root means the executable was never
            # reached.  Keep this narrow: cleanup after a spawn is not a
            # proven pre-generation failure.
            return _CodexCliRunResult(None, _diagnostic(
                CodexCliInvocationClassification.NOT_STARTED, process_started=False,
                exception=error, began=began, error_category="LOCAL_SETUP_FAILURE",
            ))
        outcome: _CodexCliRunResult | None = None
        try:
            schema_path, output_path = root / "response-schema.json", root / "response.json"
            try:
                schema_path.write_text(json.dumps(schema, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            except OSError as error:
                outcome = _CodexCliRunResult(None, _diagnostic(
                    CodexCliInvocationClassification.NOT_STARTED, process_started=False,
                    exception=error, began=began, error_category="LOCAL_SETUP_FAILURE",
                ))
            else:
                command = [str(policy.executable_path)]
                if policy.profile:
                    command.extend(("--profile", policy.profile))
                command.extend(("exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
                                "--sandbox", "read-only", "--skip-git-repo-check",
                                "-C", str(root), "--output-schema", str(schema_path), "--json",
                                "--output-last-message", str(output_path)))
                if policy.model:
                    command.extend(("--model", policy.model))
                command.append("-")
                try:
                    result = self._runner(command, input=json.dumps(_prompt(request), separators=(",", ":")),
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True, timeout=policy.timeout_seconds, check=False, cwd=str(root),
                                          env=_safe_environment())
                except subprocess.TimeoutExpired as error:
                    outcome = _CodexCliRunResult(None, _diagnostic(
                        CodexCliInvocationClassification.MAY_HAVE_HAPPENED, process_started=True,
                        exception=error, timed_out=True, began=began, error_category="TIMEOUT",
                    ))
                except OSError as error:
                    outcome = _CodexCliRunResult(None, _diagnostic(
                        CodexCliInvocationClassification.NOT_STARTED, process_started=False,
                        exception=error, began=began, error_category="PROCESS_START_FAILURE",
                    ))
                except subprocess.SubprocessError as error:
                    # The runner reached a subprocess boundary but cannot
                    # prove that no request was delivered.  Preserve its
                    # type, never its message, and prohibit a retry.
                    outcome = _CodexCliRunResult(None, _diagnostic(
                        CodexCliInvocationClassification.MAY_HAVE_HAPPENED, process_started=True,
                        exception=error, began=began, error_category="PROCESS_FAILURE",
                    ))
                else:
                    events = _terminal_events(getattr(result, "stdout", None))
                    if result.returncode != 0:
                        category = _redacted_error_category(getattr(result, "stderr", None))
                        classification = (CodexCliInvocationClassification.REJECTED_BEFORE_GENERATION
                                          if category in {"LOCAL_ARGUMENT_REJECTED", "OUTPUT_SCHEMA_REJECTED"}
                                          else CodexCliInvocationClassification.MAY_HAVE_HAPPENED)
                        outcome = _CodexCliRunResult(None, _diagnostic(
                            classification, process_started=True, began=began, returncode=result.returncode,
                            error_category=category, terminal_events=events,
                        ))
                    else:
                        try:
                            document = json.loads(output_path.read_text(encoding="utf-8"))
                        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                            # A confirmed zero exit with no valid schema output is a
                            # completed-but-invalid result, never a retry signal.
                            document = {}
                        outcome = _CodexCliRunResult(document, _diagnostic(
                            CodexCliInvocationClassification.COMPLETED_VALID, process_started=True,
                            began=began, returncode=result.returncode, terminal_events=events,
                        ))
        finally:
            try:
                temporary.cleanup()
            except OSError as error:
                if outcome is not None and outcome.diagnostic.process_started:
                    # The process did start, but its ephemeral directory could
                    # not be conclusively cleaned after it ran.  Fail closed
                    # rather than claiming a completed result or no submission.
                    outcome = _CodexCliRunResult(None, _diagnostic(
                        CodexCliInvocationClassification.MAY_HAVE_HAPPENED, process_started=True,
                        exception=error, began=began, error_category="LOCAL_CLEANUP_FAILURE",
                        terminal_events=outcome.diagnostic.terminal_events,
                    ))
        if outcome is None:
            raise RuntimeError("Codex process produced no classified result")
        return outcome

    def _record_invocation(self, policy: PlanningProviderInvocationPolicy, request: ProviderDerivationRequest,
                           request_digest: str, state: str, occurred_at: str, *, status: str | None = None,
                           diagnostic: CodexCliInvocationDiagnostic | None = None,
                           result_digest: str | None = None) -> None:
        inspection = self.configuration.policy_service.inspect(policy.provider_id)
        document = {
            "adapter_version": self.adapter_version, "provider_id": policy.provider_id,
            "provider_type": policy.provider_type, "model": policy.model, "profile": policy.profile,
            "request_digest": request_digest, "snapshot_digest": request.snapshot.digest,
            "derivation_request_digest": request.digest, "state": state, "status": status,
            "result_digest": result_digest,
        }
        if diagnostic is not None:
            document["diagnostic"] = diagnostic.document()
        with self.configuration.policy_service.db._connection:
            self.configuration.policy_service.db._connection.execute(
                "INSERT INTO planning_provider_external_session_audit VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), inspection["configuration_id"], inspection["operator_id"], "invocation",
                 occurred_at, json.dumps(document, sort_keys=True, separators=(",", ":"))),
            )


def _diagnostic(classification: CodexCliInvocationClassification, *, process_started: bool,
                began: float, exception: BaseException | None = None, timed_out: bool = False,
                returncode: int | None = None, error_category: str | None = None,
                terminal_events: tuple[str, ...] = ()) -> CodexCliInvocationDiagnostic:
    errno = getattr(exception, "errno", None)
    return CodexCliInvocationDiagnostic(
        classification, process_started, type(exception).__name__ if exception is not None else None,
        errno if isinstance(errno, int) else None, timed_out,
        max(0, int((time.monotonic() - began) * 1000)),
        returncode if isinstance(returncode, int) else None, error_category, terminal_events,
    )


def _replace_diagnostic(diagnostic: CodexCliInvocationDiagnostic,
                        classification: CodexCliInvocationClassification) -> CodexCliInvocationDiagnostic:
    return CodexCliInvocationDiagnostic(
        classification, diagnostic.process_started, diagnostic.exception_type, diagnostic.errno,
        diagnostic.timed_out, diagnostic.elapsed_milliseconds, diagnostic.returncode,
        diagnostic.error_category, diagnostic.terminal_events,
    )


def _redacted_error_category(stderr: object) -> str:
    """Classify only high-confidence local CLI rejection shapes; keep text private."""
    value = stderr if isinstance(stderr, str) else ""
    # This bounded inspection is intentionally not persisted.  A non-zero
    # process exit alone never proves that Codex did not generate anything.
    if _LOCAL_ARGUMENT_REJECTION.search(value[:8192]) is None:
        return "TERMINAL_FAILURE"
    lowered = value[:8192].lower()
    if "schema" in lowered:
        return "OUTPUT_SCHEMA_REJECTED"
    return "LOCAL_ARGUMENT_REJECTED"


def _terminal_events(stdout: object) -> tuple[str, ...]:
    """Extract only allow-listed terminal event names from ephemeral JSONL."""
    if not isinstance(stdout, str):
        return ()
    events: set[str] = set()
    for line in stdout.splitlines():
        if len(line) > 8192:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = event.get("type") if isinstance(event, dict) else None
        if name in _TERMINAL_EVENT_TYPES:
            events.add(name)
    return tuple(sorted(events))


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
    """Return the supported strict object-root Codex output contract.

    Codex forwards this to Structured Outputs, whose strict contract requires
    an object at the root.  A root union is therefore not used.  The one
    required root property contains the existing proposal-or-refinement union,
    so each branch retains its own strict, non-overlapping semantics rather
    than relying on nullable inactive fields and parser-only pairing.
    """
    proposal_schema = _schema_for_approved_contract(
        scopes, policy.allowed_write_scopes, policy.required_human_gates,
        policy.required_risk_inputs, snapshot,
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["result"],
        "properties": {
            "result": {
                "anyOf": [
                    proposal_schema,
                    {"type": "object", "additionalProperties": False,
                     "required": ["kind", "reason"],
                     "properties": {
                         "kind": {"type": "string", "enum": ["governance_refinement"]},
                         "reason": {"type": "string", "minLength": 1},
                     }},
                ],
            },
        },
    }


def _parse_response(request: ProviderDerivationRequest, document: object,
                    adapter_version: str) -> tuple[tuple[DerivedActionProposal, ...] | None, GovernanceRefinementRequired | None]:
    if not isinstance(document, dict) or set(document) != {"result"} or not isinstance(document.get("result"), dict):
        raise ValueError("structured response is not an object")
    document = document["result"]
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
