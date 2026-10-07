"""Qualify an installed Forge Mission's A -> HTTP EP -> evidence -> B loop.

Run this script with the Python 3.14 interpreter of a non-editable wheel
installation, away from the source checkout. Only the external Codex process,
credential resolver and immutable repository artifact reader are substituted.
The EP simulator speaks the real versioned HTTP boundary in the parent process.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from importlib.metadata import distribution
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
import socket
import subprocess
import sys
from threading import Lock
import time
import traceback
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit
from zipfile import ZipFile

import forge
import forge.runtime.dynamic_mission as composition
from forge.ep_simulator import EpSimulatorScenario, EpSimulatorServer, EpSimulatorState, SIMULATOR_CONTRACT_VERSION
from forge.execution import ExecutionLoopError, RecoveryAuthorization
from forge.execution_host_configuration import (
    EngineeringPlatformExecutionHostFactory, EngineeringPlatformPeerConfigurationService,
)
from forge.governance_authority import ArchitecturePlanningEvidence
from forge.governance import resolve_governance_profile
from forge.governed_candidate_intake import GovernedCandidateIntake, GovernedCandidateIntakeError
from forge.lifecycle import (MissionCandidate, MissionRecommendation,
                             RecommendationLifecycleStore, RecommendationStatus)
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_assessment import CriterionAssessmentContract, CriterionEvidenceRequirement
from forge.models.criterion_observation import canonical_digest
from forge.models.execution_host import ExecutionHostTemporaryUnavailable
from forge.models.mission_effect import MissionEffectPolicy
from forge.models.mission_recommendation import RequiredDiscipline
from forge.operator_identity import InstallationOperatorService
from forge.planner.codex_cli_session import (
    CodexCliChatGPTSessionPlanningProvider, CodexCliSessionReadinessChecker,
)
from forge.provider_security import (
    CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE, CODEX_CLI_CHATGPT_SESSION_TYPE,
    PlanningProviderSecurityService, ProviderAuthenticationMode,
)
from forge.qualification import criterion_completion as fixture
from forge.qualification.producer_fixture_conformance import (
    rejection_matrix, source_receipt, validate_fixture, validate_identity_fixture,
)
from forge.qualification.effect_fixture_conformance import (
    capture as effect_capture, source_receipt as effect_source_receipt,
)
from forge.qualification.effect_simulator_fixture import qualified_effect_result
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from forge.runtime import RuntimeBootstrap
from forge.runtime.bootstrap import RuntimeResolutionError
from forge.runtime.database import RuntimeIntegrityError
from forge.runtime.dynamic_mission import InstalledDynamicMissionError, InstalledDynamicMissionRuntime
from forge.runtime.service import RuntimeServiceBusy
from forge.secure_store import MacOSKeychainSecureStoreAdapter, SecretReference, SecretState
from forge.state.mission_state import MissionStateStoreError


TOKEN = "isolated-qualification-token"
INSTANCE = "isolated-ep-simulator"
CONSUMER = "isolated-forge-consumer"
PROJECT = "isolated-project"
HOST = "synthetic-host"
GOVERNANCE_PROFILE = "solo"
GOVERNANCE_ACTOR = "primary_operator"
SCENARIOS = (
    "partial", "post-assessment-reopen", "single", "effect-declaration-legacy",
    "successor-stale-gap", "successor-proven-gap", "successor-optional",
    "delayed", "pre-send-reopen",
    "host-recovery", "failed-recovery",
    "declined-before-run",
    "concurrent-start", "tampered", "tampered-action", "tampered-run",
    "tampered-repository", "tampered-producer", "tampered-request-digest",
    "artifact-corrupt", "artifact-schema",
    "artifact-withheld", "artifact-unavailable",
    "assurance-blocked", "budget-exhausted", "ambiguous", "ambiguous-recovered",
    "effect-read-only", "effect-documentation", "effect-design-report",
    "effect-design-git", "effect-repository-change",
)
PROVIDER_CASES = ("unavailable", "login-expired", "not-started", "local-rejected", "invalid-output",
                  "scope-expansion", "scope-outside", "unknown-dependency",
                  "missing-human-gate", "missing-risk-input", "ambiguous")


_WRITE = "BOUNDED_REPOSITORY_CHANGE/GIT"
_READ = "READ_ONLY_ASSESSMENT/EVIDENCE_ONLY"
_DOC = "DOCUMENTATION_ONLY/GIT"
_DESIGN_REPORT = "ARCHITECTURE_DESIGN_ONLY/EVIDENCE_ONLY"
_DESIGN_GIT = "ARCHITECTURE_DESIGN_ONLY/GIT"
_ALL_EFFECT_VARIANTS = (_READ, _DOC, _DESIGN_REPORT, _DESIGN_GIT, _WRITE)
_EFFECT_BASE_SCENARIOS = {
    "effect-read-only": ("READ_ONLY_ASSESSMENT", "EVIDENCE_ONLY", ()),
    "effect-documentation": ("DOCUMENTATION_ONLY", "GIT", ("docs/report.md",)),
    "effect-design-report": ("ARCHITECTURE_DESIGN_ONLY", "EVIDENCE_ONLY", ()),
    "effect-design-git": ("ARCHITECTURE_DESIGN_ONLY", "GIT", ("docs/report.md",)),
    "effect-repository-change": ("BOUNDED_REPOSITORY_CHANGE", "GIT", ("src/boundary.py",)),
}
_EFFECT_LOST_ACK = {name + "-lost-ack": name for name in _EFFECT_BASE_SCENARIOS}
_EFFECT_SUCCESSORS = {name + "-successor": name for name in (
    "effect-read-only", "effect-documentation", "effect-design-report", "effect-design-git",
)}
_EFFECT_SUCCESSOR_REJECTIONS = {
    base + "-successor-effect-expansion": base for base in _EFFECT_SUCCESSORS.values()}
_EFFECT_SUCCESSORS.update(_EFFECT_SUCCESSOR_REJECTIONS)
_EFFECT_SCOPE_TRANSITIONS = {
    "effect-read-only": "effect-documentation",
    "effect-documentation": "effect-repository-change",
    "effect-design-report": "effect-repository-change",
    "effect-design-git": "effect-repository-change",
}
_EFFECT_SCOPE_CASES = {
    name + "-" + outcome: (name, next_scope)
    for name, next_scope in _EFFECT_SCOPE_TRANSITIONS.items()
    for outcome in ("effect-expansion-denied", "approved-new-scope")
}
_EFFECT_REJECTIONS = {
    **{name + "-" + fault: (name, fault)
       for name in _EFFECT_BASE_SCENARIOS
       for fault in ("report-missing", "controls-failed", "review-open")},
    **{name + "-report-corrupt": (name, "report-corrupt")
       for name in ("effect-read-only", "effect-documentation", "effect-design-report",
                    "effect-design-git")},
    **{name + "-" + fault: (name, fault)
       for name in ("effect-read-only", "effect-documentation", "effect-design-report", "effect-design-git")
       for fault in ("report-useless", "criterion-irrelevant")},
    **{name + "-stale-binding": (name, "stale-binding")
       for name in ("effect-read-only", "effect-documentation", "effect-design-report",
                    "effect-design-git")},
    **{name + "-profile-stale": (name, "profile-stale")
       for name in ("effect-read-only", "effect-documentation", "effect-design-report",
                    "effect-design-git", "effect-repository-change")},
    "effect-read-only-host-mutated": ("effect-read-only", "host-mutated"),
    **{"effect-read-only-" + fault: ("effect-read-only", fault)
       for fault in ("review-schema-invalid", "control-time-invalid", "subject-schema-invalid",
                    "review-bool-ordinal", "profile-bool-ordinal", "envelope-bool-ordinal")},
    "effect-read-only-target-effect-probes": ("effect-read-only", "target-effect-probes"),
    "effect-repository-change-write-no-output": ("effect-repository-change", "write-no-output"),
    **{name + "-document-executable": (name, "document-executable")
       for name in ("effect-documentation", "effect-design-git")},
}
_EFFECT_SCENARIOS = {
    **_EFFECT_BASE_SCENARIOS,
    "effect-read-only-no-change": _EFFECT_BASE_SCENARIOS["effect-read-only"],
    "effect-read-only-scope-expansion": _EFFECT_BASE_SCENARIOS["effect-read-only"],
    **{name: _EFFECT_BASE_SCENARIOS[base] for name, base in _EFFECT_LOST_ACK.items()},
    **{name: _EFFECT_BASE_SCENARIOS[base] for name, base in _EFFECT_SUCCESSORS.items()},
    **{name: _EFFECT_BASE_SCENARIOS[base] for name, (base, _) in _EFFECT_REJECTIONS.items()},
    **{name: _EFFECT_BASE_SCENARIOS[base] for name, (base, _) in _EFFECT_SCOPE_CASES.items()},
}
SCENARIOS += ("effect-read-only-no-change", "effect-read-only-scope-expansion") + tuple(
    _EFFECT_LOST_ACK) + tuple(_EFFECT_SUCCESSORS) + tuple(_EFFECT_REJECTIONS) + tuple(
    _EFFECT_SCOPE_CASES)


def _effect_policy(scenario: str) -> MissionEffectPolicy:
    mode, delivery, writes = _EFFECT_SCENARIOS[scenario]
    return MissionEffectPolicy(mode, delivery, ("docs/",), writes)
_FIE_MODE_VARIANTS = {
    **{f"FIE-{number:02d}": (_WRITE,) for number in range(1, 17)},
    "FIE-17": (_READ,), "FIE-18": (_DOC,),
    "FIE-19": (_DESIGN_REPORT, _DESIGN_GIT), "FIE-20": (_READ,),
    "FIE-21": (_READ,),
    "FIE-22": (_READ, _DOC, _DESIGN_REPORT, _DESIGN_GIT),
    "FIE-23": (_READ, _WRITE), "FIE-24": _ALL_EFFECT_VARIANTS,
    "FIE-25": _ALL_EFFECT_VARIANTS,
    "FIE-26": (_READ, _DOC, _DESIGN_REPORT, _DESIGN_GIT),
    "FIE-27": (_READ, _DOC, _DESIGN_REPORT, _DESIGN_GIT),
    "FIE-28": _ALL_EFFECT_VARIANTS,
}
_FIE_SUBSET_EVIDENCE = {
    "FIE-01": ("scenario:single",),
    "FIE-02": ("scenario:partial", "scenario:post-assessment-reopen"),
    "FIE-03": ("scenario:single",),
    "FIE-04": ("governance:candidate-alone", "governance:stale-candidate"),
    "FIE-05": ("preflight:credential-revoked", "provider:login-expired", "scenario:budget-exhausted"),
    "FIE-06": ("provider:unavailable", "provider:invalid-output", "provider:ambiguous"),
    "FIE-07": ("provider:scope-expansion", "provider:unknown-dependency",
               "scenario:successor-stale-gap", "scenario:successor-proven-gap",
               "scenario:successor-optional"),
    "FIE-08": ("preflight:readback-absent", "preflight:wrong-instance",
               "preflight:credential-invalid"),
    "FIE-09": ("scenario:delayed",),
    "FIE-10": ("scenario:ambiguous-recovered",),
    "FIE-11": ("scenario:tampered-request-digest", "scenario:tampered-run",
               "scenario:artifact-corrupt", "scenario:assurance-blocked"),
    "FIE-12": ("scenario:artifact-withheld", "scenario:artifact-unavailable",
               "scenario:declined-before-run"),
    "FIE-13": ("scenario:host-recovery", "scenario:failed-recovery"),
    "FIE-14": ("scenario:concurrent-start", "scenario:partial"),
    "FIE-15": ("scenario:pre-send-reopen", "scenario:post-assessment-reopen",
               "scenario:ambiguous-recovered"),
    "FIE-16": ("identity:installed-wheel-byte-drift", "storage:wrong-runtime-marker",
               "storage:missing-runtime-storage", "storage:unsupported-runtime-schema"),
    "FIE-20": ("preflight:effect-request-missing",),
    "FIE-28": ("preflight:effect-result-unsupported", "scenario:effect-declaration-legacy"),
}
_VARIANT_SCENARIO = {
    _READ: "effect-read-only", _DOC: "effect-documentation",
    _DESIGN_REPORT: "effect-design-report", _DESIGN_GIT: "effect-design-git",
    _WRITE: "effect-repository-change",
}


def _required_fie_cases(family: str, variant: str) -> tuple[str, ...]:
    if family in _FIE_REQUIRED_BASE_CASES:
        return _FIE_REQUIRED_BASE_CASES[family]
    base = _VARIANT_SCENARIO[variant]
    positive = "scenario:" + base
    if family == "FIE-17":
        return (positive, "scenario:effect-read-only-no-change")
    if family == "FIE-18":
        return (positive, "scenario:effect-documentation-document-executable")
    if family == "FIE-19":
        return (positive,) + (("scenario:effect-design-git-document-executable",)
                              if variant == _DESIGN_GIT else ())
    if family == "FIE-20":
        return (positive, "preflight:effect-request-missing",
                "scenario:effect-read-only-scope-expansion")
    if family == "FIE-21":
        return (positive, "scenario:effect-read-only-host-mutated",
                "scenario:effect-read-only-controls-failed",
                "scenario:effect-read-only-target-effect-probes")
    if family == "FIE-22":
        return (positive, *("scenario:" + base + "-" + fault for fault in (
            "report-missing", "report-corrupt", "report-useless", "criterion-irrelevant", "stale-binding")))
    if family == "FIE-23":
        return (("scenario:effect-read-only-no-change", "scenario:effect-read-only-report-missing")
                if variant == _READ else
                (positive, "scenario:effect-repository-change-write-no-output"))
    if family == "FIE-24":
        return (positive, *("scenario:" + base + "-" + fault for fault in (
            "controls-failed", "review-open", "profile-stale")),
                *("scenario:effect-read-only-" + fault for fault in (
                    "review-schema-invalid", "control-time-invalid", "subject-schema-invalid",
                    "review-bool-ordinal", "profile-bool-ordinal", "envelope-bool-ordinal")))
    if family == "FIE-25":
        return (positive, "scenario:" + base + "-lost-ack")
    if family == "FIE-26":
        return (positive, "scenario:" + base + "-successor",
                "scenario:" + base + "-successor-effect-expansion")
    if family == "FIE-27":
        return (positive, "scenario:" + base + "-effect-expansion-denied",
                "scenario:" + base + "-approved-new-scope")
    if family == "FIE-28":
        return (positive, "preflight:effect-result-unsupported",
                "scenario:effect-declaration-legacy")
    raise RuntimeError("unmapped canonical FIE family")


def _fci_manifest(report: dict[str, Any]) -> dict[str, Any]:
    """Require each declared FIE/mode case to have an installed result."""
    roadmap = Path(__file__).resolve().parents[2] / "docs/roadmap/forge-inner-loop-ci-v1.json"
    source = roadmap.read_bytes()
    inventory = json.loads(source)["scenarios"]
    ids = [entry["id"] for entry in inventory]
    expected = [f"FIE-{number:02d}" for number in range(1, 29)]
    if ids != expected or any(entry.get("required") is not True for entry in inventory):
        raise RuntimeError("canonical FIE inventory changed without qualifier reconciliation")
    if set(_FIE_MODE_VARIANTS) != set(expected):
        raise RuntimeError("required FIE mode variants are incomplete")
    observed = {
        *("scenario:" + item["scenario"] for item in report["scenarios"]
          if item.get("qualification_result") == "PASS"),
        *("preflight:" + item["case"] for item in report["preflight_matrix"]
          if item.get("qualification_result") == "PASS"),
        *("governance:" + item["case"] for item in report["governance_matrix"]
          if item.get("qualification_result") == "PASS"),
        *("provider:" + item["case"] for item in report["provider_matrix"]
          if item.get("qualification_result") == "PASS"),
        "identity:" + report["installed_identity_negative"]["case"],
        *("storage:" + item["case"] for item in report["runtime_storage_negatives"]),
    }
    families = []
    for entry in inventory:
        variants = []
        for variant in _FIE_MODE_VARIANTS[entry["id"]]:
            required = _required_fie_cases(entry["id"], variant)
            variants.append({"mode_variant": variant, "required_cases": list(required),
                             "observed_cases": [case for case in required if case in observed],
                             "missing_cases": [case for case in required if case not in observed]})
        missing = [case for variant in variants for case in variant["missing_cases"]]
        evidence = [case for case in _FIE_SUBSET_EVIDENCE.get(entry["id"], ()) if case in observed]
        families.append({
            "id": entry["id"], "name": entry["name"], "required": True,
            "required_mode_variants": list(_FIE_MODE_VARIANTS[entry["id"]]),
            "observed_subset_evidence": evidence,
            "mode_variant_evidence": variants,
            "coverage_state": "COMPLETE_EVIDENCE" if not missing else (
                "PARTIAL_EVIDENCE" if any(variant["observed_cases"] for variant in variants)
                else "NO_EVIDENCE"),
            "result": "PASS" if not missing else "NOT_QUALIFIED",
        })
    complete = all(item["result"] == "PASS" for item in families)
    return {
        "result": "PASS" if complete else "NOT_QUALIFIED",
        "reason": None if complete else "Required installed FIE/mode cases remain unqualified",
        "inventory_sha256": "sha256:" + sha256(source).hexdigest(),
        "families": families,
        "required_mode_variants": list(_ALL_EFFECT_VARIANTS),
    }


def _child_env(root: Path) -> dict[str, str]:
    """Give every scenario an isolated identity, configuration and scratch root."""
    home, scratch, config = (root / name for name in ("home", "scratch", "config"))
    for directory in (home, scratch, config, config / "gh", config / "codex"):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home), "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch),
        "XDG_CONFIG_HOME": str(config), "GH_CONFIG_DIR": str(config / "gh"),
        "CODEX_HOME": str(config / "codex"), "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "PATH": "/usr/bin:/bin",
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "NO_PROXY": "127.0.0.1,localhost,::1", "no_proxy": "127.0.0.1,localhost,::1",
    }


def _with_case_cleanup(root: Path, operation, *args):
    started = time.monotonic()
    try:
        result = operation(root, *args)
        if not isinstance(result, dict):
            raise RuntimeError("installed qualification case returned no result")
    finally:
        for directory in ("home", "scratch", "config", "runtime", "governance",
                          "synthetic-target", "adversarial-target"):
            path = root / directory
            if path.exists():
                shutil.rmtree(path)
    return {**result, "qualification_result": "PASS",
            "duration_ms": round((time.monotonic() - started) * 1000),
            "stage_trace": fixture._read(root / "stage-trace.public.json", []),
            "cleanup": {"owned_home_scratch_config_removed": all(
                not (root / name).exists() for name in ("home", "scratch", "config")),
                "owned_runtime_governance_targets_removed": all(
                    not (root / name).exists() for name in (
                        "runtime", "governance", "synthetic-target", "adversarial-target"))}}


@contextmanager
def _loopback_only(endpoint: str):
    """Permit only the selected simulator socket in an installed Forge process."""
    parsed = urlsplit(endpoint)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.port is None or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError("qualification requires one exact loopback simulator endpoint")
    selected = (parsed.hostname, parsed.port)
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo

    def allowed(address):
        return isinstance(address, tuple) and address[:2] == selected

    def checked_connect(sock, address):
        if not allowed(address):
            raise PermissionError("qualification denies non-simulator network")
        return original_connect(sock, address)

    def checked_connect_ex(sock, address):
        if not allowed(address):
            raise PermissionError("qualification denies non-simulator network")
        return original_connect_ex(sock, address)

    def checked_getaddrinfo(host, *args, **kwargs):
        if host != selected[0]:
            raise PermissionError("qualification denies non-simulator name resolution")
        return original_getaddrinfo(host, *args, **kwargs)

    def checked_process(*_args, **_kwargs):
        raise PermissionError("qualification denies real provider, gh, and host subprocesses")

    with patch.object(socket.socket, "connect", checked_connect), \
         patch.object(socket.socket, "connect_ex", checked_connect_ex), \
         patch.object(socket, "getaddrinfo", checked_getaddrinfo), \
         patch.object(subprocess, "run", checked_process), \
         patch.object(subprocess, "Popen", checked_process):
        yield
EP_IDENTITY_READBACK_SOURCE = {
    "repository": "pcvantol/engineering-platform",
    "revision": "66433d7a2260397ec438a3052acae8ef50a84022",
    "product_version": "2.3.109",
    "contract_version": "1.0", "producer_readback_version": "1.3",
    "contract_sha256": "sha256:40d749293ce27c86f5b051d74867bbca01def74b8394ac059dac414a6e4083ca",
    "serializer_sha256": "sha256:c2335e9e4edd3cbe4b56d992527d1e5a64ed9296d482c40bd5fe3e915ceadbd3",
    "http_test_sha256": "sha256:23ddddc26918bb3038983121154c011e71c4b42b17a1c6fe7803a69cda24c35b",
    "producer_state": "PROTECTED_MAIN_SOURCE_AND_INSTALLED_FIE10_QUALIFIED",
}
# These are adversarial EP-boundary fixtures, not Forge preflight stubs.  The
# expected reasons are the product adapter/factory's stable, secret-free errors.
PREFLIGHT_CASES = {
    "readback-absent": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "readback-incompatible": "EP_READBACK_CONTRACT_INCOMPATIBLE",
    "terminal-absent": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "terminal-incompatible": "EP_TERMINAL_CONTRACT_INCOMPATIBLE",
    "wrong-instance": "EP_INSTANCE_IDENTITY_MISMATCH",
    "wrong-consumer": "EP_AUTHENTICATED_CONSUMER_IDENTITY_MISMATCH",
    "wrong-project": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "wrong-repository": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "inactive-consumer": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "inactive-project": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "repository-not-authority": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "repository-unbound": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "scope-unauthorized": "EP_AUTHENTICATED_CONSUMER_SCOPE_MISMATCH",
    "credential-missing": "EP credential reference is not resolvable: MISSING",
    "credential-revoked": "EP credential reference is not resolvable: REVOKED",
    "credential-invalid": "EP rejected request: 401",
    "http-401": "EP rejected request: 401",
    "http-403": "EP rejected request: 403",
    "declaration-public-version": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "declaration-missing-producer": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "declaration-missing-auth-field": "EP_CAPABILITY_DECLARATION_MALFORMED",
    "effect-request-missing": "EP_EFFECT_CONTRACT_DECLARATION_MALFORMED",
    "effect-result-unsupported": "EP_EFFECT_CONTRACT_DECLARATION_MALFORMED",
    "effect-profile-missing": "EP_EFFECT_CONTRACT_DECLARATION_MALFORMED",
    "terminal-effect-only": "EP_TERMINAL_CONTRACT_INCOMPATIBLE",
}
EP_PREFLIGHT_SOURCE = {
    "repository": "pcvantol/engineering-platform",
    "revision": "66433d7a2260397ec438a3052acae8ef50a84022",
    "product_version": "2.3.109",
    "path": "src/engineering_platform/server.py",
    "sha256": "sha256:92e0e8c1c904bbefdf6200328bb9c03a55939b1a2fcf3b131c00ecd7d707013a",
    "declaration_contract": "1.1",
    "producer_readback_contracts": ["1.2", "1.3"],
    "terminal_evidence_contract": "1.4",
    "governed_continuation_contract": "ep-governed-continuation-evidence/v1",
}
GOVERNANCE_CASES = (
    "candidate-alone", "missing-business", "missing-architecture",
    "rejected-business", "rejected-architecture",
    "wrong-business-actor", "wrong-business-role",
    "wrong-architecture-actor", "wrong-architecture-role",
    "stale-candidate", "changed-scope", "changed-criteria", "changed-spec",
)


_FIE_REQUIRED_BASE_CASES = {
    "FIE-01": ("scenario:single",),
    "FIE-02": ("scenario:partial", "scenario:post-assessment-reopen"),
    "FIE-03": ("scenario:single",),
    "FIE-04": tuple("governance:" + case for case in GOVERNANCE_CASES),
    "FIE-05": ("preflight:credential-revoked", "preflight:scope-unauthorized",
               "provider:login-expired", "scenario:budget-exhausted"),
    "FIE-06": tuple("provider:" + case for case in PROVIDER_CASES),
    "FIE-07": ("provider:scope-expansion", "provider:scope-outside",
               "provider:unknown-dependency", "scenario:successor-stale-gap",
               "scenario:successor-proven-gap", "scenario:successor-optional"),
    "FIE-08": tuple("preflight:" + case for case in PREFLIGHT_CASES),
    "FIE-09": ("scenario:delayed",),
    "FIE-10": ("scenario:ambiguous-recovered",),
    "FIE-11": ("scenario:tampered", "scenario:tampered-action", "scenario:tampered-run",
               "scenario:tampered-repository", "scenario:tampered-producer",
               "scenario:tampered-request-digest", "scenario:artifact-corrupt",
               "scenario:artifact-schema", "scenario:assurance-blocked"),
    "FIE-12": ("scenario:artifact-withheld", "scenario:artifact-unavailable",
               "scenario:declined-before-run"),
    "FIE-13": ("scenario:host-recovery", "scenario:failed-recovery"),
    "FIE-14": ("scenario:concurrent-start", "scenario:partial"),
    "FIE-15": ("scenario:pre-send-reopen", "scenario:post-assessment-reopen",
               "scenario:ambiguous-recovered", "scenario:single"),
    "FIE-16": ("identity:installed-wheel-byte-drift", "storage:wrong-runtime-marker",
               "storage:missing-runtime-storage", "storage:unsupported-runtime-schema"),
}

class _SyntheticCredentialResolver:
    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        assert reference.serialized == "keychain://synthetic/ep"
        return SecretState.RESOLVABLE, TOKEN


class _PreflightCredentialResolver(_SyntheticCredentialResolver):
    def __init__(self, case: str) -> None:
        self.case = case

    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        if self.case == "credential-missing":
            return SecretState.MISSING, None
        if self.case == "credential-revoked":
            return SecretState.REVOKED, None
        if self.case == "credential-invalid":
            return SecretState.RESOLVABLE, "invalid-isolated-token"
        return super().resolve(reference)


def _installed_wheel(wheel: Path, *, source_revision: str | None = None,
                     verify_source: bool = False) -> dict[str, Any]:
    if sys.version_info[:2] != (3, 14) or not sys.flags.isolated or sys.flags.optimize:
        raise RuntimeError("qualification requires assertion-enabled isolated Python 3.14.x")
    if not wheel.is_file():
        raise RuntimeError("candidate wheel is missing")
    installed = distribution("forge-autonomy")
    direct = json.loads(installed.read_text("direct_url.json") or "{}")
    wheel_bytes = wheel.read_bytes()
    digest = sha256(wheel_bytes).hexdigest()
    if (direct.get("archive_info", {}).get("hashes", {}).get("sha256") != digest
            or direct.get("dir_info", {}).get("editable")):
        raise RuntimeError("installed distribution is not the exact candidate wheel")
    package_root = Path(installed.locate_file("forge")).resolve()
    package = Path(forge.__file__).resolve()
    if (not package.is_relative_to(package_root)
            or "site-packages" not in package.parts
            or not Path(sys.executable).absolute().is_relative_to(Path(sys.prefix).absolute())):
        raise RuntimeError("Forge import did not come from installed site-packages")
    modules = (
        "forge/__init__.py", "forge/runtime/dynamic_mission.py",
        "forge/scheduler/ep_http_adapter.py", "forge/ep_simulator.py",
    )
    module_digests = {}
    source_files_verified = 0
    installed_files_verified = 0
    source_root = Path(__file__).resolve().parents[2]
    tracked = set()
    expected_product_files = set()
    source_tree_revision = None
    if verify_source:
        if source_revision is None or subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True,
        ).strip() != source_revision:
            raise RuntimeError("qualification source revision is not exact HEAD")
        if subprocess.check_output(
            ["git", "-C", str(source_root), "status", "--porcelain"], text=True,
        ).strip():
            raise RuntimeError("qualification source checkout is dirty")
        source_version = json.loads((source_root / "product-version.json").read_text())["version"]
        if source_version != installed.version:
            raise RuntimeError("installed wheel version differs from the exact source manifest")
        source_tree_revision = subprocess.check_output(
            ["git", "-C", str(source_root), "rev-parse", "HEAD^{tree}"], text=True).strip()
        tracked = set(subprocess.check_output(
            ["git", "-C", str(source_root), "ls-files", "-z", "--", "forge"],
        ).decode("utf-8").split("\0"))
        expected_product_files = {name for name in tracked if Path(name).suffix in {".py", ".json"}}
    wheel_product_files = set()
    with ZipFile(BytesIO(wheel_bytes)) as archive:
        for name in archive.namelist():
            if not name.startswith("forge/") or name.endswith("/"):
                continue
            wheel_product_files.add(name)
            payload = archive.read(name)
            installed_file = Path(installed.locate_file(name)).resolve()
            if (not installed_file.is_relative_to(package_root)
                    or installed_file.read_bytes() != payload):
                raise RuntimeError("installed Forge payload differs from selected wheel")
            installed_files_verified += 1
            if verify_source:
                if name not in tracked or (source_root / name).read_bytes() != payload:
                    raise RuntimeError("wheel product payload differs from exact tracked source")
                source_files_verified += 1
        if installed_files_verified == 0 or verify_source and source_files_verified == 0:
            raise RuntimeError("wheel lacks verified Forge product files")
        if verify_source and wheel_product_files != expected_product_files:
            raise RuntimeError("candidate wheel omits or adds tracked Forge product files")
        for module in modules:
            expected = archive.read(module)
            installed_file = Path(installed.locate_file(module)).resolve()
            if (not installed_file.is_relative_to(package_root)
                    or installed_file.read_bytes() != expected):
                raise RuntimeError("installed Forge module bytes differ from the selected wheel")
            module_digests[module] = "sha256:" + sha256(expected).hexdigest()
    return {"version": installed.version, "wheel_sha256": "sha256:" + digest,
            "source_tree_revision": source_tree_revision,
            "module_sha256": module_digests,
            "installed_product_files_verified": installed_files_verified,
            "source_product_files_verified": source_files_verified if verify_source else None}


def _installed_identity_negative(root: Path, wheel: Path) -> dict[str, str]:
    """Require a byte-drifted wheel to fail before any installed scenario starts."""
    root.mkdir(parents=True)
    altered = root / "altered-candidate.whl"
    altered.write_bytes(wheel.read_bytes() + b"qualification-byte-drift")
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(altered), "--output-dir", str(root / "denial")]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False,
                                timeout=30, env=_child_env(root))
        (root / "denial.raw.private.log").write_text(result.stdout + result.stderr)
        denial = fixture._read(root / "denial" / "installed-http-successor.public.json", {})
        if (result.returncode != 1 or denial.get("result") != "FAIL"
                or denial.get("failure") != {"stage": "installed_wheel_identity", "type": "RuntimeError"}):
            raise RuntimeError("installed wheel byte drift did not fail before scenario setup")
        return {"case": "installed-wheel-byte-drift", "result": "REJECTED",
                "stage": "installed_wheel_identity"}
    finally:
        altered.unlink(missing_ok=True)
        for directory in ("home", "scratch", "config"):
            path = root / directory
            if path.exists():
                shutil.rmtree(path)


def _installed_runtime_storage_negatives(root: Path) -> list[dict[str, str]]:
    """Require existing-instance marker/storage errors to preserve identity."""
    bootstrap = RuntimeBootstrap(data_root=root, forge_version="qualification")
    with bootstrap.open() as database:
        original_id = database.runtime_identity.runtime_id
    marker = root / "instance" / "runtime-instance.json"
    database_path = root / "forge.db"
    marker_bytes = marker.read_bytes()
    marker.write_text("foreign-runtime-id\n", encoding="utf-8")
    try:
        try:
            bootstrap.open()
        except RuntimeResolutionError:
            pass
        else:
            raise RuntimeError("wrong Runtime marker reopened or replaced the instance")
    finally:
        marker.write_bytes(marker_bytes)
    with bootstrap.open() as database:
        if database.runtime_identity.runtime_id != original_id:
            raise RuntimeError("marker denial changed installed Runtime identity")
    held = root / "forge.db.held"
    database_path.rename(held)
    try:
        try:
            bootstrap.open()
        except RuntimeResolutionError:
            pass
        else:
            raise RuntimeError("missing Runtime storage initialized a replacement instance")
        if database_path.exists() or marker.read_bytes() != marker_bytes:
            raise RuntimeError("missing Runtime storage changed the selected instance")
    finally:
        held.rename(database_path)
    with bootstrap.open() as database:
        if database.runtime_identity.runtime_id != original_id:
            raise RuntimeError("storage denial changed installed Runtime identity")
    with sqlite3.connect(database_path) as connection:
        current_schema = connection.execute("PRAGMA user_version").fetchone()[0]
        connection.execute("PRAGMA user_version=999")
    try:
        try:
            bootstrap.open()
        except RuntimeIntegrityError:
            pass
        else:
            raise RuntimeError("unsupported Runtime schema reopened the instance")
        if not database_path.is_file() or marker.read_bytes() != marker_bytes:
            raise RuntimeError("schema denial replaced the Runtime instance")
    finally:
        with sqlite3.connect(database_path) as connection:
            connection.execute(f"PRAGMA user_version={current_schema}")
    with bootstrap.open() as database:
        if database.runtime_identity.runtime_id != original_id:
            raise RuntimeError("schema denial changed installed Runtime identity")
    return [{"case": "wrong-runtime-marker", "result": "REJECTED"},
            {"case": "missing-runtime-storage", "result": "REJECTED"},
            {"case": "unsupported-runtime-schema", "result": "REJECTED"}]


def _open(root: Path, stack: ExitStack, *,
          credential_case: str = "", provider_case: str = "",
          effect_scenario: str = "") -> InstalledDynamicMissionRuntime:
    transport = fixture._CodexTransport(root)
    if not effect_scenario and (root / "effect-scenario.private.json").exists():
        effect_scenario = fixture._read(root / "effect-scenario.private.json")["scenario"]
    if effect_scenario:
        approved = _effect_policy(effect_scenario)
        original_transport = transport

        def effect_transport(command, **kwargs):
            outcome = original_transport(command, **kwargs)
            if "exec" not in command or outcome.returncode:
                return outcome
            output = Path(command[command.index("--output-last-message") + 1])
            document = json.loads(output.read_text())
            proposal = document["result"]["proposals"][0]
            proposal["write_scopes"] = (["src/"] if effect_scenario == "effect-read-only-scope-expansion"
                                         else list(approved.write_paths))
            if (effect_scenario in _EFFECT_SUCCESSOR_REJECTIONS
                    and len(fixture._read(root / "provider-inputs.private.json")) > 1):
                proposal["write_scopes"] = ["src/unapproved.py"]
            proposal["objective"] = "Assess the approved source criterion: " + proposal["expected_evidence"][0]
            if proposal["mission_gap"] is not None:
                proposal["mission_gap"]["causal_objective"] = proposal["objective"]
            proposal["validation_strategy"] = [
                "Verify the EP source-bound effect report and its exact criterion evidence.",
            ]
            output.write_text(json.dumps(document))
            return outcome

        transport = effect_transport
    if provider_case:
        original = transport

        def fault_transport(command, **kwargs):
            if provider_case == "unavailable" and "--version" in command:
                return subprocess.CompletedProcess(command, 1, "", "")
            if provider_case == "login-expired" and command[-2:] == ["login", "status"]:
                return subprocess.CompletedProcess(command, 1, "Not logged in\n", "")
            if "exec" not in command:
                return original(command, **kwargs)
            fixture._append(root / "provider-attempts.private.json", {"case": provider_case})
            if provider_case == "not-started":
                raise OSError("synthetic process start denial")
            if provider_case == "local-rejected":
                return subprocess.CompletedProcess(command, 2, "", "error: unexpected argument --output-schema")
            if provider_case == "ambiguous":
                raise subprocess.TimeoutExpired(command, 10)
            if provider_case == "invalid-output":
                output = Path(command[command.index("--output-last-message") + 1])
                output.write_text('{"result":{"kind":"proposals","proposals":[{"unbound":true}]}}')
                return subprocess.CompletedProcess(
                    command, 0, '{"type":"turn.completed","usage":{"input_tokens":100,"output_tokens":50}}\n', "",
                )
            if provider_case in {"scope-expansion", "scope-outside", "unknown-dependency",
                                 "missing-human-gate", "missing-risk-input",
                                 "successor-stale-gap", "successor-proven-gap", "successor-optional"}:
                result = original(command, **kwargs)
                output = Path(command[command.index("--output-last-message") + 1])
                document = json.loads(output.read_text())
                proposal = document["result"]["proposals"][0]
                if provider_case == "scope-expansion":
                    proposal["write_scopes"] = ["unapproved/source"]
                elif provider_case == "scope-outside":
                    proposal["scope"] = "foreign-repository"
                elif provider_case == "unknown-dependency":
                    proposal["dependencies"] = ["foreign-action"]
                elif provider_case == "missing-human-gate":
                    proposal["human_gates"] = []
                elif provider_case == "missing-risk-input":
                    proposal["risk_inputs"] = []
                elif provider_case == "successor-stale-gap":
                    proposal["mission_gap"]["planning_snapshot_digest"] = "sha256:" + "0" * 64
                elif provider_case == "successor-proven-gap":
                    incoming = json.loads(kwargs["input"])
                    proven = [item["criterion_id"] for item in incoming["snapshot"]["criteria"]
                              if item["status"] == "PROVEN"]
                    assert len(proven) == 1
                    proposal["mission_gap"]["criterion_ids"] = proven
                else:
                    proposal["mission_gap"] = None
                output.write_text(json.dumps(document))
                return result
            raise RuntimeError("unsupported provider fault case")

        transport = fault_transport
    checker = CodexCliSessionReadinessChecker(runner=transport, path_usable=lambda _: True)
    stack.enter_context(patch.object(composition.MacOSGeneratedUIDIdentityAdapter, "resolve",
                                     return_value=fixture.IDENTITY))
    stack.enter_context(patch.object(composition, "CodexCliChatGPTSessionPlanningProvider",
        side_effect=lambda configuration: CodexCliChatGPTSessionPlanningProvider(
            configuration, runner=transport, readiness_checker=checker)))
    # The actual persisted-binding factory and HTTP adapter remain production code.
    stack.enter_context(patch.object(composition, "EngineeringPlatformExecutionHostFactory",
                                     lambda: EngineeringPlatformExecutionHostFactory(
                                         _PreflightCredentialResolver(credential_case))))
    stack.enter_context(patch("forge.completion.repository_observer.GitHubRepositoryArtifactReader.read",
        side_effect=lambda repository, revision, path: fixture._raw_reader(root, repository, revision, path)))
    return stack.enter_context(InstalledDynamicMissionRuntime.open(str(root / "runtime"), provider_id=fixture.PROVIDER))


def _configure(root: Path, endpoint: str) -> None:
    assert not (root / "runtime").exists(), "qualification must use a fresh data root"
    with RuntimeBootstrap(data_root=root / "runtime", forge_version="qualification").open() as database:
        operators = InstallationOperatorService(database, lambda: fixture.IDENTITY)
        context = operators.first_bind()
        PlanningProviderSecurityService(database, MacOSKeychainSecureStoreAdapter(), operators).configure(
            configuration_id="synthetic-config", provider_id=fixture.PROVIDER, operator_context=context,
            authentication_mode=ProviderAuthenticationMode.EXTERNAL_AUTHENTICATED_SESSION,
            provider_type=CODEX_CLI_CHATGPT_SESSION_PROVIDER_TYPE,
            external_session_type=CODEX_CLI_CHATGPT_SESSION_TYPE,
            executable_path="/usr/bin/false", adapter_version="codex-cli-chatgpt-session-v1",
            timeout_seconds=10, input_token_bound=40000, context_token_bound=48000,
            output_token_bound=8000,
        )
    EngineeringPlatformPeerConfigurationService(root / "runtime").configure(
        binding_id="isolated-ep-peer", endpoint=endpoint,
        expected_ep_instance_id=INSTANCE, ep_consumer_id=CONSUMER,
        execution_host_id=HOST, ep_project_id=PROJECT,
        ep_repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository,
        credential_reference=SecretReference.parse("keychain://synthetic/ep"),
        operator_id="isolated-qualification", allow_loopback_http=True,
    )


def _candidate_fixture(lifecycle: RecommendationLifecycleStore,
                       runtime: InstalledDynamicMissionRuntime, *, maximum_actions: int = 3,
                       effect_scenario: str = "", suffix: str = "") -> tuple[
                           MissionCandidate, GovernedCandidateIntake,
                           ArchitectureMission, ArchitecturePlanningEvidence]:
    if effect_scenario:
        policy = _effect_policy(effect_scenario)
        criterion = "Explain the deployment boundary with source evidence."
        criteria = (criterion, "Explain the approved follow-up boundary with source evidence.") if (
            effect_scenario in _EFFECT_SUCCESSORS) else (criterion,)
        options = {"criterion_assessment_contracts": tuple(
            CriterionAssessmentContract(item, (CriterionEvidenceRequirement(
                "approved-effect-report-" + str(index), kind="effect_report"),),
                validity_policy=("historical_delivery" if effect_scenario in _EFFECT_SUCCESSORS
                                 else "current_revision"))
            for index, item in enumerate(criteria)
        ), "maximum_actions": maximum_actions,
            "maximum_consecutive_no_progress_actions": 1,
            "repository_evidence_source": fixture.SOURCE,
            "effect_policy": policy}
        title = "Assess the deployment boundary"
        objective = "Produce a source-backed report under the approved effect mode."
    else:
        policy = None
        criteria = (fixture.K1, fixture.K2)
        options = {"criterion_assessment_contracts": fixture._contracts(), "maximum_actions": maximum_actions,
                   "maximum_consecutive_no_progress_actions": 1,
                   "repository_evidence_source": fixture.SOURCE}
        title = "Synthetic export contract"
        objective = "Publish two explicit JSON properties."
    recommendation = MissionRecommendation(
        "synthetic-recommendation" + suffix, title, "qualification",
        "Provide an inspectable contract." if policy is None else
        "Clarify the committed deployment boundary for the owner.",
        objective,
        "Inspectability.", "Two verified JSON properties." if policy is None else
        "One reviewed source-backed criterion report.", "No behavior claim.",
        ("repository:synthetic",), "architecture-review:synthetic",
        ("external fixtures",), ("Defer this synthetic proof.",), 90,
        "2026-09-18T09:59:00Z",
    )
    lifecycle.create_recommendation(recommendation, actor="synthetic-portfolio",
                                    rationale="Isolated installed qualification.")
    lifecycle.transition(recommendation.id, RecommendationStatus.RECOMMENDED,
                         actor="synthetic-portfolio", occurred_at="2026-09-18T09:59:01Z",
                         rationale="Candidate is ready for separate governance.")
    candidate = lifecycle.create_candidate(MissionCandidate(
        "synthetic-candidate" + suffix, recommendation.id, recommendation.title,
        recommendation.engineering_summary, ("synthetic-contract",),
        criteria, ("no behavior claim",), recommendation.dependencies,
        effect_policy=policy,
    ))
    bridge = GovernedCandidateIntake(
        lifecycle, runtime, resolve_governance_profile(GOVERNANCE_PROFILE),
    )
    revision, _, architecture_id = bridge.decision_ids(candidate.id)
    mission_preview = ArchitectureMission(
        "MISSION-PREVIEW", candidate.id, candidate.title, candidate.objective,
        recommendation.business_summary, recommendation.business_value,
        architecture_id, recommendation.id, candidate.scope,
        candidate.architecture_constraints, candidate.acceptance_criteria,
        ("external fixtures",), candidate.dependencies,
        (HOST,), (RequiredDiscipline.PLATFORM_ARCHITECTURE,),
        ("scope-drift",), ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING, **options,
    )
    planning = ArchitecturePlanningEvidence(
        candidate.scope, ("contracts",) if policy is None else policy.write_paths,
        candidate.architecture_constraints, ("scope-drift",),
        ("protected-delivery",), candidate.dependencies,
        40000, 8000, revision, mission_spec_digest=canonical_digest(mission_preview.to_dict()),
        **options,
    )
    return candidate, bridge, mission_preview, planning


def _initial_truth(revision: str = "0" * 40) -> RepositoryTruthSnapshot:
    baseline = revision == "0" * 40
    return RepositoryTruthSnapshot(
        "initial" if baseline else "initial-" + revision[:12],
        fixture.SOURCE.repository_id, revision,
        "2026-09-18T09:59:00Z",
        (RepositoryTruthEvidence("initial-revision" if baseline else "initial-revision-" + revision[:12],
            "git_commit", revision,
            "repository://synthetic/initial" if baseline else
            "repository://synthetic/initial/" + revision,
            fixture._digest("initial" if baseline else "initial-" + revision)),),
    )


def _prepare(root: Path, scenario: str, endpoint: str, *, start: bool = True,
             capture_phase: str = "prepare") -> None:
    _configure(root, endpoint)
    if scenario in _EFFECT_SCENARIOS:
        fixture._write(root / "effect-scenario.private.json", {"scenario": scenario})
    with ExitStack() as stack:
        runtime = _open(root, stack, effect_scenario=(scenario if scenario in _EFFECT_SCENARIOS else ""))
        with RecommendationLifecycleStore(root / "runtime" / "governance" / "candidates.sqlite") as lifecycle:
            candidate, bridge, mission_preview, planning = _candidate_fixture(
                lifecycle, runtime, maximum_actions=1 if scenario == "budget-exhausted" else 3,
                effect_scenario=(scenario if scenario in _EFFECT_SCENARIOS else ""),
            )
            revision = bridge.decision_ids(candidate.id)[0]
            rejected = []

            def reject_unapproved(label: str, proposed: ArchitectureMission) -> None:
                try:
                    bridge.admit(candidate.id, proposed, planning,
                                 occurred_at="2026-09-18T09:59:30Z")
                except GovernedCandidateIntakeError:
                    pass
                else:
                    raise RuntimeError(f"{label} unexpectedly allocated a Mission")
                if (runtime.database._connection.execute(
                        "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0]
                        or runtime.database._connection.execute(
                            "SELECT COUNT(*) FROM mission_state").fetchone()[0]):
                    raise RuntimeError(f"{label} created a Mission before exact approval")
                rejected.append(label)

            reject_unapproved("missing-business", mission_preview)
            bridge.approve_business(candidate.id, actor=GOVERNANCE_ACTOR,
                                    occurred_at="2026-09-18T09:59:02Z", rationale="Business value approved.",
                                    human_gates=planning.human_gates)
            reject_unapproved("missing-architecture", mission_preview)
            bridge.approve_architecture(candidate.id, mission_preview, planning,
                                        actor=GOVERNANCE_ACTOR, occurred_at="2026-09-18T09:59:03Z",
                                        rationale="Exact technical contract approved.")
            reject_unapproved("changed-objective", replace(
                mission_preview, summary="Unapproved objective."))
            if scenario in _EFFECT_SCENARIOS:
                disallowed = (MissionEffectPolicy(
                    "BOUNDED_REPOSITORY_CHANGE", "GIT", ("docs/",), ("src/boundary.py",))
                    if _effect_policy(scenario).mode == "DOCUMENTATION_ONLY" else
                    MissionEffectPolicy("DOCUMENTATION_ONLY", "GIT", ("docs/",),
                                        ("docs/report.md",)))
                reject_unapproved("changed-effect", replace(
                    mission_preview, effect_policy=disallowed))
            fixture._write(root / "governance-negative.private.json", {"rejected": rejected})
            admitted = bridge.admit(candidate.id, mission_preview, planning,
                                    occurred_at="2026-09-18T10:00:00Z")
        mission_id = admitted.mission_id
        assert not admitted.actions
        runtime.assign_progression_policy(mission_id, {
            "assignment_id": "qualification-progression-" + mission_id.lower(),
            "profile_id": GOVERNANCE_PROFILE,
            "profile_revision": "1", "policy_revision": "1", "mode": "continuous",
            "required_decision_role": "platform_architect",
            "higher_scope_obligations": list(planning.human_gates),
            "expected_state_revision": admitted.revision,
        })
        if start:
            if scenario == "pre-send-reopen":
                # Let the real runner persist its immutable request, then
                # interrupt before the first EP POST. The next OS process must
                # send that exact request without another provider turn.
                with patch.object(runtime.host, "dispatch", side_effect=
                                  ExecutionHostTemporaryUnavailable("synthetic pre-send interruption")):
                    runtime.start(mission_id, _initial_truth())
            else:
                initial_revision = fixture._read(root / "effect-target.private.json", {}).get(
                    "source_revision", "0" * 40)
                runtime.start(mission_id, _initial_truth(initial_revision))
        fixture._write(root / "population.private.json", {
            "mission_id": mission_id, "scenario": scenario,
            "runtime_id": runtime.database.runtime_identity.runtime_id,
        })
        _capture(root, runtime, capture_phase)
        if capture_phase == "preflight-stage":
            fixture._write(root / f"{capture_phase}.peer.private.json",
                           _peer_binding_snapshot(runtime))


def _approve_business(bridge: GovernedCandidateIntake, candidate: MissionCandidate,
                      planning: ArchitecturePlanningEvidence) -> None:
    bridge.approve_business(candidate.id, actor=GOVERNANCE_ACTOR,
                            occurred_at="2026-09-18T09:59:02Z",
                            rationale="Synthetic Business approval.",
                            human_gates=planning.human_gates)


def _approve_architecture(bridge: GovernedCandidateIntake, candidate: MissionCandidate,
                          preview: ArchitectureMission,
                          planning: ArchitecturePlanningEvidence) -> None:
    bridge.approve_architecture(candidate.id, preview, planning,
                                actor=GOVERNANCE_ACTOR, occurred_at="2026-09-18T09:59:03Z",
                                rationale="Synthetic Architecture approval.")


def _expected_denial(operation, error_type: type[Exception]) -> dict[str, str]:
    try:
        operation()
    except error_type as error:
        return {"type": type(error).__name__, "reason": str(error)}
    raise RuntimeError("an unauthorized governance operation unexpectedly succeeded")


def _stage_governance_case(case: str, lifecycle: RecommendationLifecycleStore,
                           candidate: MissionCandidate, bridge: GovernedCandidateIntake,
                           preview: ArchitectureMission,
                           planning: ArchitecturePlanningEvidence) -> tuple[ArchitectureMission, dict | None]:
    prior_denial = None
    needs_business = case in {
        "missing-architecture", "rejected-architecture", "wrong-architecture-actor",
        "wrong-architecture-role", "stale-candidate", "changed-scope",
        "changed-criteria", "changed-spec",
    }
    needs_architecture = case in {
        "stale-candidate", "changed-scope", "changed-criteria", "changed-spec",
    }
    if needs_business:
        _approve_business(bridge, candidate, planning)
    if needs_architecture:
        _approve_architecture(bridge, candidate, preview, planning)
    if case == "missing-business":
        prior_denial = _expected_denial(
            lambda: _approve_architecture(bridge, candidate, preview, planning),
            GovernedCandidateIntakeError)
    elif case in {"rejected-business", "rejected-architecture"}:
        role, target = ((GOVERNANCE_ACTOR, RecommendationStatus.BUSINESS_REJECTED)
                        if case == "rejected-business" else
                        (GOVERNANCE_ACTOR, RecommendationStatus.ARCHITECTURE_REJECTED))
        lifecycle.transition(candidate.recommendation_id, target, actor=role,
                             occurred_at="2026-09-18T09:59:04Z",
                             rationale="Synthetic governance rejection.",
                             references=(candidate.id, planning.provenance_revision))
    elif case in {"wrong-business-actor", "wrong-business-role"}:
        actor = "stranger" if case == "wrong-business-actor" else "platform_architect"
        prior_denial = _expected_denial(
            lambda: bridge.approve_business(
                candidate.id, actor=actor, occurred_at="2026-09-18T09:59:04Z",
                rationale="Unqualified actor.", human_gates=planning.human_gates),
            PermissionError)
    elif case in {"wrong-architecture-actor", "wrong-architecture-role"}:
        actor = "stranger" if case == "wrong-architecture-actor" else "business_owner"
        prior_denial = _expected_denial(
            lambda: bridge.approve_architecture(
                candidate.id, preview, planning, actor=actor,
                occurred_at="2026-09-18T09:59:04Z", rationale="Unqualified actor."),
            PermissionError)
    elif case == "stale-candidate":
        lifecycle.update_candidate(candidate.id, objective="Changed after both decisions.")
    elif case == "changed-scope":
        preview = replace(preview, scope=("unapproved-repository",))
    elif case == "changed-criteria":
        lifecycle.update_candidate(candidate.id, acceptance_criteria=("unapproved criterion",))
    elif case == "changed-spec":
        preview = replace(preview, summary="Unapproved Mission specification.")
    return preview, prior_denial


def _negative_observation(root: Path, lifecycle: RecommendationLifecycleStore,
                          runtime: InstalledDynamicMissionRuntime,
                          bridge: GovernedCandidateIntake, preview: ArchitectureMission,
                          planning: ArchitecturePlanningEvidence) -> dict:
    denial = _expected_denial(
        lambda: bridge.admit("synthetic-candidate", preview, planning,
                             occurred_at="2026-09-18T09:59:30Z"),
        GovernedCandidateIntakeError)
    allocation = lifecycle.allocation_for_recommendation("synthetic-recommendation")
    counts = {
        "lifecycle_allocations": int(allocation is not None),
        "runtime_allocations": runtime.database._connection.execute(
            "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0],
        "admitted_missions": runtime.database._connection.execute(
            "SELECT COUNT(*) FROM mission_state").fetchone()[0],
        "planner_invocations": len(fixture._read(root / "provider-inputs.private.json", [])),
    }
    if any(counts.values()):
        raise RuntimeError("rejected Candidate caused an allocation, admission or planning effect")
    decisions = [item for item in lifecycle.history("synthetic-recommendation")
                 if item.kind in {"business_decision", "architecture_decision"}]
    for decision in decisions:
        if not {"synthetic-candidate", planning.provenance_revision}.issubset(decision.references):
            raise RuntimeError("governance decision lost the exact Candidate revision")
    return {
        "rejection": denial, "counts": counts,
        "recommendation_status": lifecycle.get_recommendation("synthetic-recommendation").status.value,
        "candidate_revision": canonical_digest(lifecycle.get_candidate("synthetic-candidate").to_dict()),
        "decision_lineage": [{"kind": item.kind, "id": item.id} for item in decisions],
        "canonical_approval_count": runtime.database._connection.execute(
            "SELECT COUNT(*) FROM governance_decisions").fetchone()[0],
        "runtime_instance": runtime.database.runtime_identity.runtime_id,
        "pid": os.getpid(),
    }


def _governance_phase(root: Path, case: str, phase: str, endpoint: str) -> None:
    if phase == "governance-first":
        _configure(root, endpoint)
    with ExitStack() as stack:
        runtime = _open(root, stack)
        with RecommendationLifecycleStore(root / "runtime" / "governance" / "candidates.sqlite") as lifecycle:
            if phase == "governance-first":
                candidate, bridge, preview, planning = _candidate_fixture(lifecycle, runtime)
                preview, prior_denial = _stage_governance_case(
                    case, lifecycle, candidate, bridge, preview, planning)
                fixture._write(root / "governance-input.private.json", {
                    "preview": preview.to_dict(), "planning": planning.to_dict(),
                    "prior_denial": prior_denial,
                })
            else:
                saved = fixture._read(root / "governance-input.private.json")
                bridge = GovernedCandidateIntake(
                    lifecycle, runtime, resolve_governance_profile(GOVERNANCE_PROFILE),
                )
                preview = ArchitectureMission.from_dict(saved["preview"])
                planning = ArchitecturePlanningEvidence.from_dict(saved["planning"])
            fixture._write(root / f"{phase}.governance.private.json",
                           _negative_observation(root, lifecycle, runtime, bridge, preview, planning))


def _capture(root: Path, runtime: InstalledDynamicMissionRuntime, phase: str) -> dict:
    mission_id = fixture._read(root / "population.private.json")["mission_id"]
    state = runtime.states._as_document(runtime.states.get(mission_id))
    fixture._write(root / f"{phase}.state.private.json", state)
    fixture._write(root / f"{phase}.process.private.json", {"pid": os.getpid()})
    return state


def _scope_transition_phase(root: Path, runtime: InstalledDynamicMissionRuntime,
                            scenario: str, phase: str) -> None:
    """Use public governance and runtime paths for a separately approved new scope."""
    old_id = fixture._read(root / "population.private.json")["mission_id"]
    original = fixture._read(root / "readback.state.private.json")
    if runtime.states._as_document(runtime.states.get(old_id)) != original or original["status"] != "COMPLETED":
        raise RuntimeError("the previously completed Mission or allowances changed")
    _, new_effect = _EFFECT_SCOPE_CASES[scenario]
    if phase in {"scope-denied", "new-scope-prepare"}:
        with RecommendationLifecycleStore(root / "runtime" / "governance" / "candidates.sqlite") as lifecycle:
            bridge = GovernedCandidateIntake(
                lifecycle, runtime, resolve_governance_profile(GOVERNANCE_PROFILE))
            proposed = replace(ArchitectureMission.from_dict(original["mission"]),
                               id="MISSION-PREVIEW", effect_policy=_effect_policy(new_effect))
            planning = ArchitecturePlanningEvidence.from_dict(
                original["admission_contract"]["planning"])
            denial = _expected_denial(
                lambda: bridge.admit("synthetic-candidate", proposed, planning,
                                     occurred_at="2026-09-18T10:01:00Z"),
                GovernedCandidateIntakeError)
            if "exact Candidate" not in denial["reason"]:
                raise RuntimeError("scope expansion was not denied by exact Candidate governance")
            fixture._write(root / "scope-denial.private.json", denial)
            if phase == "new-scope-prepare":
                candidate, new_bridge, preview, new_planning = _candidate_fixture(
                    lifecycle, runtime, effect_scenario=new_effect, suffix="-new-scope")
                _approve_business(new_bridge, candidate, new_planning)
                _approve_architecture(new_bridge, candidate, preview, new_planning)
                admitted = new_bridge.admit(
                    candidate.id, preview, new_planning,
                    occurred_at="2026-09-18T10:02:00Z")
                if admitted.actions or admitted.intents:
                    raise RuntimeError("newly approved scope did not admit at zero Actions")
                fixture._write(root / "new-scope-population.private.json", {
                    "mission_id": admitted.mission_id,
                    "candidate_id": candidate.id,
                    "runtime_id": runtime.database.runtime_identity.runtime_id,
                })
                runtime.assign_progression_policy(admitted.mission_id, {
                    "assignment_id": "qualification-progression-" + admitted.mission_id.lower(),
                    "profile_id": GOVERNANCE_PROFILE,
                    "profile_revision": "1", "policy_revision": "1", "mode": "continuous",
                    "required_decision_role": "platform_architect",
                    "higher_scope_obligations": list(new_planning.human_gates),
                    "expected_state_revision": admitted.revision,
                })
                runtime.start(admitted.mission_id,
                              _initial_truth(original["repository_truth"]["revision"]))
    if phase == "scope-denied":
        state = runtime.states._as_document(runtime.states.get(old_id))
    else:
        new_id = fixture._read(root / "new-scope-population.private.json")["mission_id"]
        if phase == "new-scope-after":
            runtime.resume(new_id)
        elif phase == "new-scope-accept":
            pending = fixture._read(root / "new-scope-after.state.private.json")["pause_reason"]
            decision = {
                "schema_version": "forge-final-acceptance-decision/v1",
                "decision_id": "installed-business-acceptance-new-scope-" + scenario,
                "requirement_id": pending["requirement_id"],
                "subject_digest": pending["subject_digest"],
                "mission_state_revision": pending["mission_state_revision"],
                "completion_digest": pending["completion_digest"],
                "terminal_evidence_digest": pending["terminal_evidence_digest"],
                "policy_revision": pending["policy_revision"],
                "decision": "accept", "reason": "The separately approved scope has exact evidence.",
            }
            context = runtime.repository.operators.context()
            principal = "local-operator:v1:" + runtime.repository._operator_id(context)
            runtime.accept_final_completion(new_id, decision,
                                            authenticated_principal_reference=principal)
        elif phase not in {"new-scope-prepare", "new-scope-readback"}:
            raise RuntimeError("unsupported scope-transition phase")
        state = runtime.states._as_document(runtime.states.get(new_id))
    if runtime.states._as_document(runtime.states.get(old_id)) != original:
        raise RuntimeError("new scope changed the previous Mission history or consumed allowances")
    fixture._write(root / f"{phase}.state.private.json", state)
    fixture._write(root / f"{phase}.process.private.json", {"pid": os.getpid()})


def _phase(root: Path, scenario: str, phase: str, endpoint: str) -> None:
    if phase == "prepare":
        _prepare(root, scenario, endpoint, start=scenario != "concurrent-start")
        return
    with ExitStack() as stack:
        runtime = _open(root, stack, provider_case=(scenario if phase == "after-a" and scenario in {
            "successor-stale-gap", "successor-proven-gap", "successor-optional",
        } else ""))
        if scenario in _EFFECT_SCOPE_CASES and phase in {
                "scope-denied", "new-scope-prepare", "new-scope-after",
                "new-scope-accept", "new-scope-readback"}:
            _scope_transition_phase(root, runtime, scenario, phase)
            return
        population = fixture._read(root / "population.private.json")
        mission_id = population["mission_id"]
        if runtime.database.runtime_identity.runtime_id != population["runtime_id"]:
            raise RuntimeError("fresh Forge process opened a different Runtime Instance")
        if phase == "completed-resume":
            try:
                runtime.resume(mission_id)
            except Exception as error:
                if type(error).__name__ != "InstalledDynamicMissionError":
                    raise
            else:
                raise RuntimeError("completed Mission unexpectedly resumed")
        elif phase in {"accept", "accept-replay"}:
            pending = fixture._read(root / "final-before-accept.state.private.json")["pause_reason"]
            decision = {
                "schema_version": "forge-final-acceptance-decision/v1",
                "decision_id": "installed-business-acceptance-" + scenario,
                "requirement_id": pending["requirement_id"],
                "subject_digest": pending["subject_digest"],
                "mission_state_revision": pending["mission_state_revision"],
                "completion_digest": pending["completion_digest"],
                "terminal_evidence_digest": pending["terminal_evidence_digest"],
                "policy_revision": pending["policy_revision"],
                "decision": "accept", "reason": "The approved Mission evidence is sufficient.",
            }
            context = runtime.repository.operators.context()
            principal = "local-operator:v1:" + runtime.repository._operator_id(context)
            runtime.accept_final_completion(
                mission_id, decision, authenticated_principal_reference=principal,
            )
        elif phase in {"recover-denied", "recover"}:
            active = runtime.states.get(mission_id).current_engineering_action
            if not isinstance(active, dict):
                raise RuntimeError("terminal Action is missing at recovery boundary")
            action_id = active["id"] if phase == "recover" else "foreign-action"
            authorization = RecoveryAuthorization(
                mission_id, action_id, "operator-installed-recovery-001",
                "The simulated terminal blocker was resolved under exact Action authority.",
                "a" * 40,
            )
            if phase == "recover-denied":
                try:
                    runtime.recover(mission_id, authorization)
                except ExecutionLoopError as error:
                    if str(error) != "recovery authorization must name the unresolved Engineering Action":
                        raise
                    fixture._write(root / "recover-denied.private.json", {
                        "type": type(error).__name__, "reason": str(error),
                    })
                else:
                    raise RuntimeError("foreign Action recovery unexpectedly succeeded")
            else:
                runtime.recover(mission_id, authorization)
        elif phase in {"race-start-a", "race-start-b"}:
            (root / f"{phase}.ready.private").write_text(str(os.getpid()))
            deadline = time.monotonic() + 20
            while not (root / "race-go.private").exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("concurrent start barrier timed out")
                time.sleep(0.01)
            try:
                runtime.start(mission_id, _initial_truth())
            except Exception as error:
                fixture._write(root / f"{phase}.race.private.json", {
                    "result": "REJECTED", "type": type(error).__name__, "reason": str(error),
                })
            else:
                fixture._write(root / f"{phase}.race.private.json", {"result": "STARTED"})
        elif phase == "after-a-cut":
            def before_successor() -> bool:
                observed = runtime.states.get(mission_id)
                marker = observed.resume.get("terminal_continuation", {})
                return marker.get("phase") != "ASSESSED"

            runtime._keep_running = before_successor
            runtime.resume(mission_id)
        elif phase != "readback":
            runtime.resume(mission_id)
        state = _capture(root, runtime, phase)
        if phase == "after-a" and scenario in {"successor-stale-gap", "successor-proven-gap",
                                                "successor-optional"}:
            attempts = [json.loads(row["document"]) for row in runtime.database._connection.execute(
                "SELECT document FROM action_derivations ORDER BY derivation_id",
            ).fetchall()]
            fixture._write(root / "successor-validation.private.json", [{
                "processing_phase": item["processing_phase"], "lifecycle": item["lifecycle"],
                "error_code": item.get("error_code"),
            } for item in attempts])
        admitted = fixture._read(root / "prepare.state.private.json")
        if state["mission"] != admitted["mission"] or state["admission_contract"] != admitted["admission_contract"]:
            raise RuntimeError("approved Mission or admission changed across processes")


def _run_phase(root: Path, scenario: str, phase: str, endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root), "--scenario", scenario,
               "--phase", phase, "--endpoint", endpoint]
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90,
                            env=_child_env(root), cwd=root)
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed {scenario}/{phase} failed; see private phase log")
    state = fixture._read(root / f"{phase}.state.private.json")
    fixture._append(root / "stage-trace.public.json", {
        "phase": phase, "status": state["status"], "actions": len(state["actions"]),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "all_required_criteria_proven": bool(
            state.get("completion") and state["completion"].get("all_required_criteria_proven")),
    })
    return state


def _run_governance_phase(root: Path, case: str, phase: str,
                          endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root),
               "--governance-case", case, "--phase", phase, "--endpoint", endpoint]
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90,
                            env=_child_env(root), cwd=root)
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed governance {case}/{phase} failed; see private phase log")
    observation = fixture._read(root / f"{phase}.governance.private.json")
    fixture._append(root / "stage-trace.public.json", {
        "phase": phase, "status": "REJECTED", "counts": observation["counts"],
        "duration_ms": round((time.monotonic() - started) * 1000)})
    return observation


def _count_ep_http_requests(server: EpSimulatorServer) -> list[str]:
    requests: list[str] = []
    request_lock = Lock()
    base_handler = server.server.RequestHandlerClass

    class CountingHandler(base_handler):
        def parse_request(self) -> bool:
            parsed = super().parse_request()
            if parsed:
                # Observe every HTTP path and method before route/auth checks; the simulator
                # audit only records accepted submissions and misses negative traffic.
                with request_lock:
                    requests.append(f"{self.command} {self.path}")
            return parsed

    server.server.RequestHandlerClass = CountingHandler
    return requests


_REMOVE = object()
_DECLARATION_CHANGES = {
    "readback-absent": (("contracts", "producer_readback"), _REMOVE),
    "readback-incompatible": (("contracts", "producer_readback"), ["1.3"]),
    "terminal-absent": (("contracts", "terminal_evidence"), _REMOVE),
    "terminal-incompatible": (("contracts", "terminal_evidence"), ["1.3"]),
    "inactive-consumer": (("authentication", "consumer_status"), "INACTIVE"),
    "inactive-project": (("authentication", "project_status"), "INACTIVE"),
    "repository-not-authority": (("authentication", "repository_role"), "observer"),
    "repository-unbound": (("authentication", "local_repository_binding"), "UNBOUND"),
    "scope-unauthorized": (("authentication", "submission_authorization"), "DENIED"),
    "declaration-public-version": (("contract_version",), "1.0"),
    "declaration-missing-producer": (("producer",), _REMOVE),
    "declaration-missing-auth-field": (("authentication", "consumer_status"), _REMOVE),
    "effect-request-missing": (("contracts", "effect_request"), _REMOVE),
    "effect-result-unsupported": (("contracts", "effect_result"), ["9.9"]),
    "effect-profile-missing": (("contracts", "effect_validation_profile"), _REMOVE),
    "terminal-effect-only": (("contracts", "terminal_evidence"), ["1.6"]),
}


def _preflight_fixture(case: str) -> tuple[EpSimulatorState, dict | None]:
    """Change only the external EP declaration or HTTP/identity fixture."""
    identities = {
        "wrong-instance": {"instance_id": "foreign-ep-instance"},
        "wrong-consumer": {"consumer_id": "foreign-consumer"},
        "wrong-project": {"project_id": "foreign-project"},
        "wrong-repository": {"repository_id": "foreign-repository"},
    }
    http_status = {"http-401": 401, "http-403": 403}.get(case)
    scenario = (EpSimulatorScenario(preflight_http_status=http_status)
                if http_status is not None else
                EpSimulatorScenario(effect_declaration_supported=True)
                if case in {"effect-request-missing", "effect-result-unsupported", "effect-profile-missing",
                            "terminal-effect-only"} else None)
    settings = {
        "project_id": PROJECT, "repository_id": fixture.SOURCE.repository_id,
        "repository_identity": fixture.SOURCE.github_repository, "consumer_id": CONSUMER,
        "instance_id": INSTANCE, "bearer_token": TOKEN, "scenario": scenario,
    }
    settings.update(identities.get(case, {}))
    state = EpSimulatorState(**settings)
    change = _DECLARATION_CHANGES.get(case)
    if change is None:
        return state, None
    declaration = deepcopy(state.compatibility())
    path, replacement = change
    target = declaration
    for segment in path[:-1]:
        target = target[segment]
    if replacement is _REMOVE:
        del target[path[-1]]
    else:
        target[path[-1]] = replacement
    return state, declaration


def _peer_binding_snapshot(runtime: InstalledDynamicMissionRuntime) -> dict:
    """Read the exact selected peer and generation without exposing its document."""
    connection = runtime.database._connection
    binding = connection.execute(
        "SELECT binding_id,configuration_revision,configuration_digest,document "
        "FROM execution_host_peer_configuration WHERE singleton=1"
    ).fetchone()
    generation = connection.execute(
        "SELECT generation,last_digest FROM execution_host_peer_generation WHERE singleton=1"
    ).fetchone()
    if binding is None or generation is None:
        raise RuntimeError("preflight qualification lost the selected EP peer")
    return {
        "binding_id": binding[0], "configuration_revision": binding[1],
        "configuration_digest": binding[2],
        "document_sha256": "sha256:" + sha256(binding[3].encode()).hexdigest(),
        "generation": generation[0], "generation_last_digest": generation[1],
        "detach_operations": connection.execute(
            "SELECT COUNT(*) FROM execution_host_peer_detach_operations"
        ).fetchone()[0],
    }


def _preflight_phase(root: Path, case: str, phase: str, endpoint: str) -> None:
    if phase == "preflight-stage":
        _prepare(root, case, endpoint, start=False, capture_phase=phase)
        return
    mission_id = fixture._read(root / "population.private.json")["mission_id"]
    expected_reason = PREFLIGHT_CASES[case]
    expected_type = ("PeerConfigurationError" if case in {"credential-missing", "credential-revoked"}
                     else "ValueError")
    try:
        with ExitStack() as stack:
            runtime = _open(root, stack, credential_case=case)
            runtime.start(mission_id, _initial_truth())
    except Exception as error:
        if type(error).__name__ != expected_type or str(error) != expected_reason:
            raise RuntimeError(f"{case} failed at the wrong product gate") from error
        observed_type, observed_reason = type(error).__name__, str(error)
    else:
        raise RuntimeError(f"{case} unexpectedly started a Mission")
    # Observation reopens the canonical store with a valid synthetic resolver,
    # but performs no preflight, planner call, retarget or submission.
    with ExitStack() as stack:
        runtime = _open(root, stack)
        state = _capture(root, runtime, phase)
        fixture._write(root / f"{phase}.peer.private.json",
                       _peer_binding_snapshot(runtime))
        connection = runtime.database._connection
        counts = {
            "mission_allocations": connection.execute(
                "SELECT COUNT(*) FROM mission_id_allocations").fetchone()[0],
            "admitted_missions": connection.execute(
                "SELECT COUNT(*) FROM mission_state").fetchone()[0],
            "execution_bindings": connection.execute(
                "SELECT COUNT(*) FROM execution_host_bindings").fetchone()[0],
            "exchange_audit": connection.execute(
                "SELECT COUNT(*) FROM execution_host_exchange_audit").fetchone()[0],
            "planner_invocations": len(fixture._read(root / "provider-inputs.private.json", [])),
        }
    fixture._write(root / f"{phase}.preflight.private.json", {
        "pid": os.getpid(), "reason": observed_reason, "type": observed_type,
        "status": state["status"], "counts": counts,
    })


def _run_preflight_phase(root: Path, case: str, phase: str,
                         endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root),
               "--preflight-case", case, "--phase", phase, "--endpoint", endpoint]
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90,
                            env=_child_env(root), cwd=root)
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed preflight {case}/{phase} failed; see private phase log")
    observation = fixture._read(root / f"{phase}.state.private.json" if phase == "preflight-stage"
                                else root / f"{phase}.preflight.private.json")
    fixture._append(root / "stage-trace.public.json", {
        "phase": phase, "status": observation["status"],
        "duration_ms": round((time.monotonic() - started) * 1000)})
    return observation


def _preflight_case(root: Path, case: str, wheel: Path) -> dict:
    root.mkdir(parents=True)
    simulator, declaration = _preflight_fixture(case)
    fixture_identity = {
        "declaration": declaration if declaration is not None else simulator.compatibility(),
        "instance_id": simulator.instance_id, "consumer_id": simulator.consumer_id,
        "project_id": simulator.project_id, "repository_id": simulator.repository_id,
        "preflight_http_status": simulator.scenario.preflight_http_status,
        "credential_mode": ("missing" if case == "credential-missing" else
                            "revoked" if case == "credential-revoked" else
                            "invalid" if case == "credential-invalid" else "valid"),
    }
    fixture_digest = "sha256:" + sha256(json.dumps(
        fixture_identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with ExitStack() as stack:
        if declaration is not None:
            stack.enter_context(patch.object(simulator, "compatibility",
                                             return_value=declaration))
        stack.enter_context(server)
        staged = _run_preflight_phase(root, case, "preflight-stage", server.base_url, wheel)
        first = _run_preflight_phase(root, case, "preflight-first", server.base_url, wheel)
        repeat = _run_preflight_phase(root, case, "preflight-repeat", server.base_url, wheel)
    states = [fixture._read(root / f"{phase}.state.private.json") for phase in (
        "preflight-stage", "preflight-first", "preflight-repeat")]
    processes = [fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in (
        "preflight-stage", "preflight-first", "preflight-repeat")]
    peers = [fixture._read(root / f"{phase}.peer.private.json") for phase in (
        "preflight-stage", "preflight-first", "preflight-repeat")]
    if len(set(processes)) != 3 or states != [staged] * 3:
        raise RuntimeError(f"{case} changed durable Mission state or reused a Forge process")
    if (peers != [peers[0]] * 3 or peers[0]["binding_id"] != "isolated-ep-peer"
            or peers[0]["configuration_revision"] != 1
            or peers[0]["generation"] != 1 or peers[0]["detach_operations"] != 0):
        raise RuntimeError(f"{case} retargeted or detached the selected EP peer")
    if (staged["status"] != "APPROVED_PLANNABLE" or staged["actions"] or staged["intents"]
            or staged["execution_correlation"] is not None):
        raise RuntimeError(f"{case} crossed the Action or execution gate")
    expected_gets = 0 if case in {"credential-missing", "credential-revoked"} else 2
    if (requests != ["GET /v1/producer-compatibility"] * expected_gets
            or simulator.submission_ids() or simulator.audit):
        raise RuntimeError(f"{case} made unexpected listener traffic or EP submission")
    expected_counts = {
        "mission_allocations": 1, "admitted_missions": 1,
        "execution_bindings": 0, "exchange_audit": 0, "planner_invocations": 0,
    }
    if (first["counts"] != repeat["counts"] or first["counts"] != expected_counts
            or any(first[key] != repeat[key] for key in ("reason", "type", "status"))
            or first["reason"] != PREFLIGHT_CASES[case]):
        raise RuntimeError(f"{case} changed its denial or durable counters on restart")
    return {
        "case": case, "result": "REJECTED", "reason": first["reason"],
        "error_type": first["type"], "fixture_sha256": fixture_digest,
        "durable_status": staged["status"],
        "peer_binding_unchanged": True,
        "peer_configuration_digest": peers[0]["configuration_digest"],
        "forge_processes": len(processes), "preflight_gets": len(requests),
        "submission_posts": sum(request.startswith("POST ") for request in requests),
        "ep_accepted_submissions": len(simulator.submission_ids()),
        "counts": first["counts"],
    }


def _governance_case(root: Path, case: str, wheel: Path) -> dict:
    root.mkdir(parents=True)
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
    )
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with server:
        first = _run_governance_phase(root, case, "governance-first", server.base_url, wheel)
        repeat = _run_governance_phase(root, case, "governance-repeat", server.base_url, wheel)
    if first["pid"] == repeat["pid"]:
        raise RuntimeError(f"{case} was not repeated in a fresh Forge process")
    for key in ("rejection", "counts", "recommendation_status", "candidate_revision",
                "decision_lineage", "canonical_approval_count", "runtime_instance"):
        if first[key] != repeat[key]:
            raise RuntimeError(f"{case} changed its rejection or identity on fresh-process repeat")
    expected_status = ("BUSINESS_REJECTED" if case == "rejected-business" else
                       "ARCHITECTURE_REJECTED" if case == "rejected-architecture" else
                       "ARCHITECTURE_APPROVED" if case in {
                           "stale-candidate", "changed-scope", "changed-criteria", "changed-spec"} else
                       "BUSINESS_APPROVED" if case in {
                           "missing-architecture", "wrong-architecture-actor", "wrong-architecture-role"} else
                       "RECOMMENDED")
    if first["recommendation_status"] != expected_status:
        raise RuntimeError(f"{case} has the wrong canonical governance state")
    expected_approvals = (2 if expected_status == "ARCHITECTURE_APPROVED" else
                          1 if expected_status in {"BUSINESS_APPROVED", "ARCHITECTURE_REJECTED"} else 0)
    if first["canonical_approval_count"] != expected_approvals:
        raise RuntimeError(f"{case} persisted an unintended approval")
    if requests:
        raise RuntimeError(f"{case} made an EP HTTP request")
    saved = fixture._read(root / "governance-input.private.json")
    return {
        "case": case, "rejection": first["rejection"],
        "prior_denial": saved["prior_denial"],
        "recommendation_status": first["recommendation_status"],
        "approved_revision": saved["planning"]["provenance_revision"],
        "candidate_revision": first["candidate_revision"],
        "decision_lineage": first["decision_lineage"],
        "canonical_approval_count": first["canonical_approval_count"],
        "counts": {**first["counts"], "ep_requests": len(requests),
                   "ep_accepted_submissions": len(simulator.submission_ids())},
        "forge_processes": 2,
    }


def _ambiguous_result(root: Path, simulator: EpSimulatorState, endpoint: str,
                      wheel: Path, initial: dict) -> dict:
    assert initial["status"] == "WAITING_FOR_EXECUTION"
    assert len(initial["actions"]) == len(simulator.submission_ids()) == 1
    assert [event["event"] for event in simulator.audit] == [
        "submission_accepted", "submission_response_lost",
    ]
    replay = _run_phase(root, "ambiguous", "ambiguous-replay", endpoint, wheel)
    assert replay["status"] == "FAILED" and replay["waiting_reason"] == "host_dispatch_failed"
    assert len(replay["actions"]) == len(simulator.submission_ids()) == 1
    assert len(fixture._read(root / "provider-inputs.private.json")) == 1
    readback = _run_phase(root, "ambiguous", "readback", endpoint, wheel)
    assert readback == replay
    assert [event["event"] for event in simulator.audit] == [
        "submission_accepted", "submission_response_lost",
    ], "ambiguous dispatch must neither resubmit nor derive a successor"
    phases = ("prepare", "ambiguous-replay", "readback")
    processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
    assert len(processes) == len(phases)
    return {"scenario": "ambiguous", "status": replay["status"],
            "waiting_reason": replay["waiting_reason"], "actions": 1,
            "submissions": 1, "forge_processes": len(processes),
            "phase_statuses": {phase: fixture._read(root / f"{phase}.state.private.json")["status"]
                               for phase in phases}, "planner_invocations": 1}


def _faulted_effect_documents(fault: str, readback: dict, result: dict,
                              artifact: bytes) -> tuple[dict, dict, bytes]:
    """Produce a contradictory EP readback while retaining its HTTP byte digest."""
    terminal = json.loads(artifact)
    if fault == "report-corrupt":
        result["artifact"]["content"]["result"]["summary"] = "A tampered report body with stale digest."
    elif fault == "controls-failed":
        terminal["validation_controls"]["controls"]["effect_scope_containment"]["result"] = "FAIL"
    elif fault == "target-effect-probes":
        terminal["validation_controls"]["controls"]["effect_scope_containment"]["result"] = "FAIL"
    elif fault == "review-open":
        result["assurance_reviews"][0]["finding_dispositions"].append({
            "finding_id": "unresolved-review-finding", "disposition": "OPEN",
            "evidence_ref": "simulated-unresolved-review",
        })
    elif fault == "host-mutated":
        terminal["host_execution"]["terminal"]["diff"]["modified"] = 1
    elif fault == "profile-stale":
        for item in (*result["validation_controls"], *result["assurance_reviews"]):
            item["profile_digest"] = "sha256:" + "f" * 64
    elif fault == "stale-binding":
        result["artifact"]["content"]["binding"]["source_revision"] = "f" * 40
    elif fault == "write-no-output":
        result["artifact"]["content"]["result"]["files"].clear()
    elif fault == "document-executable":
        envelope = result["artifact"]["content"]
        envelope["result"]["files"][0]["path"] = "docs/execute.py"
    elif fault == "report-useless":
        result["artifact"]["content"]["result"]["summary"] = ""
    elif fault == "criterion-irrelevant":
        result["artifact"]["content"]["result"]["criteria"][0]["id"] = "unapproved-criterion"
    elif fault == "review-schema-invalid":
        result["assurance_reviews"][0].pop("started_at")
    elif fault == "control-time-invalid":
        result["validation_controls"][0]["started_at"] = None
    elif fault == "subject-schema-invalid":
        result["subject"]["unexpected"] = True
    elif fault == "review-bool-ordinal":
        result["assurance_reviews"][0]["subject"] = {**result["subject"], "repair_ordinal": False}
    elif fault == "profile-bool-ordinal":
        result["validation_profile"]["subject"] = {**result["subject"], "repair_ordinal": False}
        profile_digest = "sha256:" + sha256(json.dumps(result["validation_profile"], sort_keys=True,
            separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()
        for item in (*result["validation_controls"], *result["assurance_reviews"]):
            item["profile_digest"] = profile_digest
    elif fault == "envelope-bool-ordinal":
        result["artifact"]["content"]["repair_ordinal"] = False
        result["artifact"]["content"]["invocation_id"] = f"{terminal['run']['id']}:effect:False"
        for index, item in enumerate(result["validation_controls"]):
            item["command_id"] = f"{terminal['run']['id']}:effect:False:{index}"
        for item in result["assurance_reviews"]:
            item["invocation_id"] = f"{terminal['run']['id']}:{item['reviewer']}:effect:False"
    else:
        raise ValueError("unknown negative effect fixture")
    if fault in {"document-executable", "stale-binding", "write-no-output",
                 "report-useless", "criterion-irrelevant", "envelope-bool-ordinal"}:
        envelope = result["artifact"]["content"]
        report_digest = "sha256:" + sha256(json.dumps(
            envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("ascii")).hexdigest()
        result["artifact"]["digest"] = report_digest
        result["subject"]["subject_digest"] = report_digest
        result["validation_profile"]["subject"] = deepcopy(result["subject"])
        profile_digest = "sha256:" + sha256(json.dumps(
            result["validation_profile"], sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode("ascii")).hexdigest()
        for control in result["validation_controls"]:
            control["profile_digest"] = profile_digest
        for review in result["assurance_reviews"]:
            review["subject"] = deepcopy(result["subject"])
            review["profile_digest"] = profile_digest
            for coverage in review["coverage"]:
                coverage["evidence_ref"] = report_digest
        terminal["report"]["digest"] = report_digest
    terminal["effect_result"] = {key: deepcopy(value) for key, value in result.items()
                                 if key != "artifact"}
    raw = json.dumps(terminal, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"
    readback["evidence"]["terminal_artifact"]["digest"] = "sha256:" + sha256(raw).hexdigest()
    return readback, result, raw


def _target_effect_probes(root: Path, endpoint: str) -> dict[str, Any]:
    """Observe transient forbidden writes on an isolated synthetic EP target."""
    target = root / "adversarial-target"
    (target / "docs").mkdir(parents=True)
    (target / "src").mkdir()
    tracked = target / "src" / "boundary.py"
    untracked = target / "src" / "untracked.py"
    ignored = target / ".ignored-cache"
    outside = root / "outside-target"
    tracked.write_bytes(b"BOUNDARY = 'approved'\n")
    outside.write_bytes(b"outside target sentinel\n")
    baseline = {path.name: path.read_bytes() for path in (tracked, outside)}
    attempts = []
    tracked.write_bytes(b"BOUNDARY = 'reverted forbidden write'\n")
    attempts.append("tracked-write-reverted")
    tracked.write_bytes(baseline[tracked.name])
    for path, label in ((untracked, "untracked-write-reverted"),
                        (ignored, "ignored-write-reverted")):
        path.write_bytes(b"forbidden transient output\n")
        attempts.append(label)
        path.unlink()
    escape = target / "docs" / "escape.md"
    escape.symlink_to(outside)
    assert escape.is_symlink() and escape.resolve() == outside.resolve()
    escape.write_bytes(b"forbidden symlink write\n")
    assert outside.read_bytes() != baseline[outside.name]
    attempts.append("symlink-write-observed-and-reverted")
    outside.write_bytes(baseline[outside.name])
    escape.unlink()
    scratch = root / "synthetic-owned-scratch"
    scratch.mkdir()
    escape = scratch / "report.md"
    escape.symlink_to(tracked)
    escape.write_bytes(b"forbidden write through report path\n")
    attempts.append("scratch-report-target-write-observed-and-reverted")
    tracked.write_bytes(baseline[tracked.name])
    escape.unlink()
    scratch.rmdir()
    with _loopback_only(endpoint):
        try:
            socket.create_connection(("github.com", 443), timeout=1)
        except PermissionError:
            attempts.append("remote-mutation-transport-denied-before-connect")
        else:
            raise RuntimeError("non-simulator remote mutation transport was allowed")
    if ({path.name: path.read_bytes() for path in (tracked, outside)} != baseline
            or untracked.exists() or ignored.exists() or escape.exists()):
        raise RuntimeError("adversarial target probes left a persistent mutation")
    return {"attempts": attempts, "final_target_matches_baseline": True,
            "transient_writes_observed": 5, "forbidden_effects_observed": True,
            "remote_transport_prevented_by_qualifier": True,
            "ep_enforcement": "SIMULATED_VIOLATION_NOT_REAL_SANDBOX_QUALIFICATION"}


def _effect_target_snapshot(target: Path) -> dict[str, str]:
    return {str(path.relative_to(target)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(target.rglob("*")) if path.is_file()
            and ".git" not in path.relative_to(target).parts}


def _fixture_git(root: Path, target: Path, *arguments: str) -> str:
    environment = {**_child_env(root), "GIT_AUTHOR_NAME": "Forge Fixture",
                   "GIT_OPTIONAL_LOCKS": "0",
                   "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                   "GIT_COMMITTER_NAME": "Forge Fixture",
                   "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
                   "GIT_AUTHOR_DATE": "2026-09-18T09:00:00+00:00",
                   "GIT_COMMITTER_DATE": "2026-09-18T09:00:00+00:00"}
    return subprocess.run(["/usr/bin/git", "-C", str(target), *arguments],
                          env=environment, check=True, capture_output=True, text=True,
                          timeout=30).stdout.strip()


def _fixture_git_snapshot(root: Path, target: Path) -> dict[str, Any]:
    return {"head": _fixture_git(root, target, "rev-parse", "HEAD"),
            "refs": _fixture_git(root, target, "show-ref"),
            "index_digest": sha256((target / ".git" / "index").read_bytes()).hexdigest(),
            "status": _fixture_git(root, target, "status", "--porcelain", "--ignored"),
            "file_modes": {str(path.relative_to(target)): path.stat().st_mode & 0o777
                           for path in target.rglob("*") if path.is_file()
                           and ".git" not in path.relative_to(target).parts}}


def _effect_target_fixture(root: Path, scenario: str) -> tuple[Path, dict[str, str], dict[str, str]]:
    """Independently observe the external, isolated repository execution fixture."""
    policy = _effect_policy(scenario)
    source = effect_capture(f"{policy.mode.lower()}-{policy.delivery.lower()}.json")
    paths = source["effect_result"]["artifact"]["content"]["source_manifest"]
    target = root / "synthetic-target"
    for path in (*paths, "src/implementation.py", "tests/test_boundary.py", "config.json",
                 "ordinary-untracked.txt", ".ignored-cache"):
        selected = target / path
        selected.parent.mkdir(parents=True, exist_ok=True)
        selected.write_text("The approved deployment boundary separates planning and host execution.\n")
    baseline = _effect_target_snapshot(target)
    (target / ".gitignore").write_text(".ignored-cache\n")
    _fixture_git(root, target, "init", "-b", "main")
    _fixture_git(root, target, "remote", "add", "origin",
                 "https://github.com/" + fixture.SOURCE.github_repository)
    _fixture_git(root, target, "add", ".gitignore", "docs", "src", "tests", "config.json")
    _fixture_git(root, target, "commit", "-m", "Isolated approved source fixture")
    baseline = _effect_target_snapshot(target)
    fixture._write(root / "effect-target.private.json", {
        "source_revision": _fixture_git(root, target, "rev-parse", "HEAD")})
    return target, baseline, {path: baseline[path] for path in paths}


def _execute_effect_fixture(root: Path, target: Path, baseline: dict[str, str],
                            payload: dict) -> tuple[str | None, dict[str, Any]]:
    effect = payload["constraints"]["effect_contract"]
    policy = MissionEffectPolicy(effect["mode"], effect["delivery"],
                                 tuple(effect["read_paths"]), tuple(effect["write_paths"]))
    example = effect_capture(f"{policy.mode.lower()}-{policy.delivery.lower()}.json")
    outputs = deepcopy(example["effect_result"]["artifact"]["content"]["result"]["files"])
    before = _effect_target_snapshot(target)
    git_before = _fixture_git_snapshot(root, target)
    assert git_before["head"] == effect["source_revision"]
    for output in outputs:
        output["content"] += "\n# evidence criteria: " + ", ".join(
            item["id"] for item in effect["criteria"]) + "\n"
        assert not Path(output["path"]).is_absolute() and ".." not in Path(output["path"]).parts
        path = target / output["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output["content"])
    revision = None
    if policy.delivery == "GIT":
        _fixture_git(root, target, "add", "--", *(output["path"] for output in outputs))
        _fixture_git(root, target, "commit", "-m", "Approved criterion output")
        revision = _fixture_git(root, target, "rev-parse", "HEAD")
    after = _effect_target_snapshot(target)
    git_after = _fixture_git_snapshot(root, target)
    changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
    allowed = policy.write_paths
    assert all(any(path == scope or scope.endswith("/") and path.startswith(scope)
                   for scope in allowed) for path in changed)
    assert all(after.get(path) == digest for path, digest in baseline.items()
               if not any(path == scope or scope.endswith("/") and path.startswith(scope)
                          for scope in allowed))
    if policy.delivery == "EVIDENCE_ONLY":
        assert before == after == baseline and git_before == git_after
    return revision, {"boundary": "CONTROLLED_EXTERNAL_REPOSITORY_FIXTURE",
            "before_file_digests": before, "after_file_digests": after,
            "before_git": git_before, "after_git": git_after,
            "changed_paths": changed, "approved_write_paths": list(allowed),
            "forbidden_effects_observed": False,
            "source_revision": effect["source_revision"],
            "delivery_revision": revision, "revision_boundary": "REAL_ISOLATED_LOCAL_GIT",
            "ordinary_untracked_and_ignored_sentinels_preserved": True}


def _effect_scenario(root: Path, scenario: str, wheel: Path) -> dict:
    """Qualify one governed Mission through the installed Forge/FME HTTP path."""
    root.mkdir()
    lost_ack = scenario in _EFFECT_LOST_ACK
    successor = scenario in _EFFECT_SUCCESSORS
    scope_transition = scenario in _EFFECT_SCOPE_CASES
    fault = _EFFECT_REJECTIONS.get(scenario, (None, None))[1]
    producer = effect_source_receipt()
    target, target_baseline, source_manifest = _effect_target_fixture(root, scenario)
    target_observations = []
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
        scenario=EpSimulatorScenario(
            name=scenario, effect_declaration_supported=True,
            identity_readback_supported=lost_ack,
            connection_loss_at=frozenset({"submission-after-accept-once"}) if lost_ack else frozenset(),
        ),
    )
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with server:
        initial = _run_phase(root, scenario, "prepare", server.base_url, wheel)
        if scenario == "effect-read-only-scope-expansion":
            assert initial["status"] in {"BLOCKED", "FAILED"}
            assert not initial["actions"] and not simulator.submission_ids()
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
            assert "changed-effect" in fixture._read(root / "governance-negative.private.json")["rejected"]
            replay = _run_phase(root, scenario, "readback", server.base_url, wheel)
            assert replay == initial and not simulator.submission_ids()
            assert not any(item.startswith("POST ") for item in requests)
            return {"scenario": scenario, "status": "EXPECTED_REJECTION",
                    "mode": "READ_ONLY_ASSESSMENT", "delivery": "EVIDENCE_ONLY",
                    "approved_write_paths": [], "output_kind": "EVIDENCE_ONLY",
                    "fault": "provider-scope-expansion", "forge_processes": 2,
                    "submission_posts": 0, "submissions": 0,
                    "planner_invocations": 1, "ep_http_requests": len(requests),
                    "canonical_completion_prevented": True}
        assert initial["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
        assert len(initial["actions"]) == len(simulator.submission_ids()) == 1
        assert initial["mission"]["effect_policy"] == _effect_policy(scenario).to_dict()
        assert initial["admission_contract"]["planning"]["write_scopes"] == list(
            _effect_policy(scenario).write_paths)
        submission_id, = simulator.submission_ids()
        payload = simulator.submitted_payload(submission_id)
        effect = payload["constraints"]["effect_contract"]
        assert effect["mode"] == _effect_policy(scenario).mode
        assert effect["delivery"] == _effect_policy(scenario).delivery
        assert effect["write_paths"] == list(_effect_policy(scenario).write_paths)
        assert effect["source_revision"] == fixture._read(root / "effect-target.private.json")["source_revision"]
        revision = None if effect["delivery"] == "EVIDENCE_ONLY" else "a" * 40
        if not fault:
            revision, observation = _execute_effect_fixture(root, target, target_baseline, payload)
            target_observations.append(observation)
        simulator.complete(submission_id, delivery_revision=revision)
        baseline_readback, baseline_artifact = simulator.terminal_documents(submission_id)
        readback, result, terminal = qualified_effect_result(
            payload, baseline_readback, baseline_artifact,
            no_change_conclusion=scenario == "effect-read-only-no-change",
            source_manifest=source_manifest,
        )
        if scenario == "effect-read-only-no-change":
            assert "no repository change" in result["artifact"]["content"]["result"]["summary"]
        target_probe = (_target_effect_probes(root, server.base_url)
                        if fault == "target-effect-probes" else None)
        if fault and fault != "report-missing":
            readback, result, terminal = _faulted_effect_documents(fault, readback, result, terminal)
        binding = {
            "approved_write_paths": list(effect["write_paths"]),
            "approved_read_paths": list(effect["read_paths"]),
            "output_kind": effect["delivery"],
            "output_location": result["artifact"]["id"],
            "received_report_digest": result["artifact"]["digest"],
            "received_terminal_digest": readback["evidence"]["terminal_artifact"]["digest"],
            "profile_digest": result["validation_controls"][0]["profile_digest"],
            "criterion_ids": [item["id"] for item in effect["criteria"]],
            "controls": [item["validation_id"] for item in result["validation_controls"]],
            "reviews": [item["reviewer"] for item in result["assurance_reviews"]],
            "artifact_binding_status": "REJECTED" if fault else "VERIFIED",
            "execution_observation": "SOURCE_PINNED_SIMULATED_EP_RECEIPT",
        }
        simulator.seed_terminal(submission_id, readback, terminal)
        if fault != "report-missing":
            simulator.seed_effect_result(submission_id, result)
        after = _run_phase(root, scenario, "after-a", server.base_url, wheel)
        if scenario in _EFFECT_SUCCESSOR_REJECTIONS:
            assert after["status"] in {"FAILED", "BLOCKED"}
            assert len(after["actions"]) == len(simulator.submission_ids()) == 1
            assert after["execution_history"][0]["outcome"] == "complete"
            proven = {item["criterion_id"] for item in after["completion"]["criteria"]
                      if item["status"] == "PROVEN"}
            assert proven == {item["id"] for item in effect["criteria"]}
            assert sum(item["status"] == "UNSATISFIED" for item in after["completion"]["criteria"]) == 1
            assert after["mission"] == initial["mission"]
            assert after["execution_policy"] == initial["execution_policy"]
            assert len(fixture._read(root / "provider-inputs.private.json")) == 2
            assert _run_phase(root, scenario, "readback", server.base_url, wheel) == after
            assert sum(item.startswith("POST ") for item in requests) == 1
            processes = {fixture._read(root / f"{phase}.process.private.json")["pid"]
                         for phase in ("prepare", "after-a", "readback")}
            assert len(processes) == 3
            return {**binding, "scenario": scenario, "status": "EXPECTED_REJECTION",
                    "mode": effect["mode"], "delivery": effect["delivery"],
                    "fault": "unapproved-successor-effect-expansion", "submissions": 1,
                    "submission_posts": 1, "planner_invocations": 2,
                    "ep_http_requests": len(requests), "forge_processes": len(processes),
                    "history_and_allowances_preserved": True,
                    "target_effect_observations": target_observations,
                    "unapproved_successor_prevented": True}
        if fault:
            assert after["status"] == "FAILED", after.get("waiting_reason")
            expected_code = {
                "report-missing": "VALUEERROR",
                "report-corrupt": "EP_EFFECT_REPORT_BYTES_MISMATCH",
                "report-useless": "EP_EFFECT_CRITERION_REPORT_INVALID",
                "criterion-irrelevant": "EP_EFFECT_CRITERION_SET_MISMATCH",
                "controls-failed": "EP_EFFECT_TERMINAL_CONTROL_FAILED",
                "target-effect-probes": "EP_EFFECT_TERMINAL_CONTROL_FAILED",
                "review-open": "EP_EFFECT_REVIEWS_UNQUALIFIED",
                "review-schema-invalid": "EP_EFFECT_REVIEWS_UNQUALIFIED",
                "control-time-invalid": "EP_EFFECT_CONTROLS_UNQUALIFIED",
                "subject-schema-invalid": "EP_EFFECT_SUBJECT_SCHEMA_INVALID",
                "review-bool-ordinal": "EP_EFFECT_REVIEWS_UNQUALIFIED",
                "profile-bool-ordinal": "EP_EFFECT_PROFILE_INPUTS_MISMATCH",
                "envelope-bool-ordinal": "EP_EFFECT_APPROVED_CONTRACT_MISMATCH",
                "host-mutated": "EP_EFFECT_FORBIDDEN_TARGET_MUTATION",
                "document-executable": "EP_EFFECT_GIT_REPORT_SCOPE_INVALID",
                "profile-stale": "EP_EFFECT_PROFILE_DIGEST_MISMATCH",
                "stale-binding": "EP_EFFECT_REPORT_BINDING_MISMATCH",
                "write-no-output": "EP_EFFECT_GIT_REPORT_EMPTY",
            }[fault]
            assert len(after["actions"]) == 1
            assert after["execution_evidence"]["outcome"] == "failed"
            assert after["execution_evidence"]["failure_code"] == expected_code
            assert not after["completion"] or after["completion"]["all_required_criteria_proven"] is False
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
            repeated = _run_phase(root, scenario, "readback", server.base_url, wheel)
            assert repeated == after
            assert len(simulator.submission_ids()) == 1
            posts = sum(item.startswith("POST ") for item in requests)
            assert posts == 1
            assert not any(item["event"] == "submission_duplicate" for item in simulator.audit)
            phases = ("prepare", "after-a", "readback")
            processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
            assert len(processes) == len(phases)
            return {**binding, "scenario": scenario, "status": "EXPECTED_REJECTION", "fault": fault,
                    "mode": effect["mode"], "delivery": effect["delivery"],
                    "source_revision": effect["source_revision"],
                    "forge_processes": len(processes), "submissions": 1,
                    "submission_posts": posts, "ep_http_requests": len(requests),
                    "planner_invocations": 1,
                    "target_revision_unchanged": revision is None,
                    "canonical_completion_prevented": True,
                    "target_effect_probe": target_probe,
                    "target_fixture_unchanged": _effect_target_snapshot(target) == target_baseline}
        if lost_ack:
            recovered = [item for item in simulator.audit if item["event"] == "submission_identity_read"]
            assert len(recovered) == 1
            assert len(simulator.submission_ids()) == 1
        assert len(after["execution_history"]) == 1
        evidence = after["execution_history"][0]
        assert evidence["effect_result"]["report_digest"] == result["artifact"]["digest"]
        assert evidence["effect_result"]["mode"] == effect["mode"]
        assert len(after["completion"]["criteria"]) == (2 if successor else 1)
        assessments = {item["criterion_id"]: item for item in after["completion"]["criteria"]}
        assert all(assessments[item["id"]]["requirement_results"][0]["reason"] ==
                   "VERIFIED_EP_EFFECT_CRITERION_SATISFIED" for item in effect["criteria"])
        if revision is None:
            assert after["repository_truth"]["revision"] == effect["source_revision"]
            assert after["repository_truth"] == initial["repository_truth"]
            assert evidence["repository_evidence"]["candidate_revision"] is None
            assert result["delivery"]["pull_request"] is None
        else:
            assert after["repository_truth"]["revision"] == revision
            assert evidence["repository_evidence"]["candidate_revision"] is not None
            assert result["delivery"]["pull_request"] is not None
        if successor:
            assert after["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert {item["criterion_id"] for item in after["completion"]["criteria"]
                    if item["status"] == "PROVEN"} == {item["id"] for item in effect["criteria"]}
            assert sum(item["status"] == "UNSATISFIED" for item in after["completion"]["criteria"]) == 1
            assert len(after["actions"]) == len(simulator.submission_ids()) == 2
            assert len(fixture._read(root / "provider-inputs.private.json")) == 2
            next_submission = next(item for item in simulator.submission_ids() if item != submission_id)
            next_payload = simulator.submitted_payload(next_submission)
            next_effect = next_payload["constraints"]["effect_contract"]
            assert next_effect["mode"] == effect["mode"]
            assert next_effect["delivery"] == effect["delivery"]
            assert next_effect["write_paths"] == effect["write_paths"]
            assert next_effect["source_revision"] == (revision or effect["source_revision"])
            next_manifest = {path: _effect_target_snapshot(target)[path] for path in source_manifest}
            next_revision, observation = _execute_effect_fixture(root, target, target_baseline, next_payload)
            target_observations.append(observation)
            simulator.complete(next_submission, delivery_revision=next_revision)
            next_readback, next_artifact = simulator.terminal_documents(next_submission)
            next_readback, result, next_artifact = qualified_effect_result(
                next_payload, next_readback, next_artifact,
                source_manifest=next_manifest)
            simulator.seed_terminal(next_submission, next_readback, next_artifact)
            simulator.seed_effect_result(next_submission, result)
            after = _run_phase(root, scenario, "after-b", server.base_url, wheel)
            assert len(after["execution_history"]) == 2
            assert [item["status"] for item in after["completion"]["criteria"]] == [
                "PROVEN", "PROVEN"]
            revision = next_revision
        assert after["status"] == "AWAITING_APPROVAL", after.get("waiting_reason")
        assert after["completion"]["all_required_criteria_proven"] is True
        fixture._write(root / "final-before-accept.state.private.json", after)
        accepted = _run_phase(root, scenario, "accept", server.base_url, wheel)
        replayed = _run_phase(root, scenario, "accept-replay", server.base_url, wheel)
        assert accepted == replayed and accepted["status"] == "COMPLETED"
        final = _run_phase(root, scenario, "readback", server.base_url, wheel)
        assert final == accepted
        stopped = _run_phase(root, scenario, "completed-resume", server.base_url, wheel)
        assert stopped == final
        if scope_transition:
            denied = _run_phase(root, scenario, "scope-denied", server.base_url, wheel)
            assert denied == final
            assert "exact Candidate" in fixture._read(root / "scope-denial.private.json")["reason"]
            assert len(simulator.submission_ids()) == 1
            assert sum(item.startswith("POST ") for item in requests) == 1
            if scenario.endswith("-effect-expansion-denied"):
                phases = ("prepare", "after-a", "accept", "accept-replay", "readback",
                          "completed-resume", "scope-denied")
                processes = {fixture._read(root / f"{phase}.process.private.json")["pid"]
                             for phase in phases}
                assert len(processes) == len(phases)
                return {**binding, "scenario": scenario, "status": "EXPECTED_REJECTION",
                        "mode": effect["mode"], "delivery": effect["delivery"],
                        "requested_new_effect": _EFFECT_SCOPE_CASES[scenario][1],
                        "forge_processes": len(processes), "submissions": 1,
                        "submission_posts": 1, "ep_http_requests": len(requests),
                        "planner_invocations": 1,
                        "original_mission_completed": True,
                        "scope_expansion_prevented": True,
                        "target_effect_observations": target_observations,
                        "original_allowances_preserved": True}
            new_effect = _EFFECT_SCOPE_CASES[scenario][1]
            fixture._write(root / "effect-scenario.private.json", {"scenario": new_effect})
            new_initial = _run_phase(root, scenario, "new-scope-prepare", server.base_url, wheel)
            assert new_initial["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert len(simulator.submission_ids()) == 2
            new_id = next(item for item in simulator.submission_ids() if item != submission_id)
            new_payload = simulator.submitted_payload(new_id)
            new_request = new_payload["constraints"]["effect_contract"]
            new_policy = _effect_policy(new_effect)
            assert new_request["mode"] == new_policy.mode
            assert new_request["delivery"] == new_policy.delivery
            assert new_request["write_paths"] == list(new_policy.write_paths)
            assert new_request["source_revision"] == final["repository_truth"]["revision"]
            new_manifest = {path: _effect_target_snapshot(target)[path] for path in source_manifest}
            new_revision, observation = _execute_effect_fixture(
                root, target, _effect_target_snapshot(target), new_payload)
            target_observations.append(observation)
            simulator.complete(new_id, delivery_revision=new_revision)
            new_readback, new_artifact = simulator.terminal_documents(new_id)
            new_readback, new_result, new_artifact = qualified_effect_result(
                new_payload, new_readback, new_artifact,
                source_manifest=new_manifest)
            simulator.seed_terminal(new_id, new_readback, new_artifact)
            simulator.seed_effect_result(new_id, new_result)
            new_pending = _run_phase(root, scenario, "new-scope-after", server.base_url, wheel)
            assert new_pending["status"] == "AWAITING_APPROVAL"
            assert new_pending["completion"]["all_required_criteria_proven"] is True
            new_completed = _run_phase(root, scenario, "new-scope-accept", server.base_url, wheel)
            assert new_completed["status"] == "COMPLETED"
            assert _run_phase(root, scenario, "new-scope-readback", server.base_url, wheel) == new_completed
            assert sum(item.startswith("POST ") for item in requests) == 2
            assert len(fixture._read(root / "provider-inputs.private.json")) == 2
        assert len(simulator.submission_ids()) == (2 if successor or scope_transition else 1)
        posts = sum(item.startswith("POST ") for item in requests)
        assert posts == (2 if successor or scope_transition else 1)
        assert any(item.endswith("/effect-result") for item in requests)
        assert not any(item["event"] == "submission_duplicate" for item in simulator.audit)
    phases = ("prepare", "after-a", *(("after-b",) if successor else ()),
              "accept", "accept-replay", "readback", "completed-resume",
              *(("scope-denied", "new-scope-prepare", "new-scope-after",
                 "new-scope-accept", "new-scope-readback") if scope_transition else ()))
    processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
    assert len(processes) == len(phases)
    return {**binding, "scenario": scenario, "status": "COMPLETED", "mode": effect["mode"],
            "delivery": effect["delivery"], "source_revision": effect["source_revision"],
            "delivery_revision": revision, "report_digest": result["artifact"]["digest"],
            "effect_producer_source": producer["producer_source_sha"],
            "forge_processes": len(processes),
            "submissions": 2 if successor or scope_transition else 1,
            "submission_posts": posts, "ep_http_requests": len(requests),
            "planner_invocations": len(fixture._read(root / "provider-inputs.private.json")),
            "target_revision_unchanged": revision is None,
            "per_criterion_proven": True, "successor_derived": successor,
            "criterion_artifact_bindings": [item["effect_result"]
                                             for item in final["execution_history"]],
            "target_effect_observations": target_observations,
            "accepted_post_lost_ack_recovered": lost_ack,
            "approved_new_scope": scope_transition,
            "original_allowances_preserved": scope_transition}


def _scenario(root: Path, scenario: str, wheel: Path, *, observer=None) -> dict:
    if scenario in _EFFECT_SCENARIOS:
        return _effect_scenario(root, scenario, wheel)
    root.mkdir()
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
        scenario=(EpSimulatorScenario(connection_loss_at=frozenset({"submission-after-accept-once"}))
                  if scenario == "ambiguous" else
                  EpSimulatorScenario(
                      name="identity-recovery", identity_readback_supported=True,
                      connection_loss_at=frozenset({"submission-after-accept-once"}),
                  ) if scenario == "ambiguous-recovered" else
                  EpSimulatorScenario(name="delayed-terminal", terminal_after_reads=6)
                  if scenario == "delayed" else
                  EpSimulatorScenario(name="artifact-unavailable", artifact_http_status=404)
                  if scenario == "artifact-unavailable" else
                  EpSimulatorScenario(name="request-digest-readback-fault",
                                      accepted_digest_mismatch_on_readback=True)
                  if scenario == "tampered-request-digest" else
                  EpSimulatorScenario(name="effect-declaration-legacy",
                                      effect_declaration_supported=True)
                  if scenario == "effect-declaration-legacy" else None),
    )
    fixture._write(root / "artifact-a.json", {
        "report": {"fields": ["report_data"]},
        "policy": {"authorization_required": scenario in {
            "single", "effect-declaration-legacy", "delayed", "pre-send-reopen",
            "host-recovery", "failed-recovery",
            "ambiguous-recovered",
        }},
    })
    fixture._write(root / "artifact-b.json", {
        "report": {"fields": ["report_data"]}, "policy": {"authorization_required": True},
    })
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with server:
        initial = _run_phase(root, scenario, "prepare", server.base_url, wheel)
        if scenario == "pre-send-reopen":
            assert initial["status"] == "WAITING_FOR_EXECUTION"
            assert len(initial["actions"]) == 1 and not simulator.submission_ids()
            persisted = initial["execution_correlation"]["request"]
            assert persisted["correlation_id"] and persisted["producer_contract"]
            initial = _run_phase(root, scenario, "send-after-reopen", server.base_url, wheel)
            assert initial["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert initial["execution_correlation"]["request"] == persisted
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
        fixture_receipts = []
        fixture_negatives = []
        recovery_summary = None
        governance_negative = fixture._read(root / "governance-negative.private.json")["rejected"]
        assert governance_negative == ["missing-business", "missing-architecture", "changed-objective"]
        assert len(initial["actions"]) == len(simulator.submission_ids()) == 1
        a = simulator.submission_ids()[0]
        request_a = simulator.submitted_payload(a)
        fixture_receipts.append(validate_fixture(
            request_a, simulator.readback(a), None, project_id=PROJECT,
            repository_id=fixture.SOURCE.repository_id, submission_id=a,
        ))
        if scenario == "ambiguous":
            posts = sum(request.startswith("POST ") for request in requests)
            assert posts == len(simulator.submission_ids()) == 1
            return {**_ambiguous_result(root, simulator, server.base_url, wheel, initial),
                    "governance_rejections": governance_negative,
                    "producer_fixtures": fixture_receipts, "producer_fixture_negatives": fixture_negatives,
                    "submission_posts": posts, "ep_http_requests": len(requests)}
        if scenario == "declined-before-run":
            simulator.decline_before_run(a)
        elif scenario == "assurance-blocked":
            simulator.complete(
                a, outcome="BLOCKED", assurance="FAIL", quality_review="FAIL",
                security_review="UNRESOLVED",
            )
        elif scenario in {"host-recovery", "failed-recovery"}:
            if scenario == "failed-recovery":
                simulator.complete(a, outcome="FAILED", assurance="NOT_RECORDED")
            else:
                simulator.complete(a, outcome="BLOCKED")
        else:
            simulator.complete(a, delivery_revision="a" * 40)
        if scenario == "declined-before-run":
            pass  # No run, artifact or terminal evidence exists in this EP disposition.
        elif scenario == "artifact-withheld":
            simulator.withhold_terminal_artifact(a)
        else:
            source_readback, source_artifact = simulator.terminal_documents(a)
            fixture_receipts.append(validate_fixture(
                request_a, source_readback, source_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=a,
            ))
        if scenario == "artifact-corrupt":
            simulator.corrupt_terminal_artifact(a)
        if scenario in {"partial", "post-assessment-reopen"}:
            fixture_negatives = rejection_matrix(
                request_a, source_readback, source_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=a,
            )
        if scenario in {"tampered", "tampered-action", "tampered-run",
                        "tampered-repository", "tampered-producer", "artifact-schema"}:
            readback, artifact = simulator.terminal_documents(a)
            if scenario == "tampered":
                readback["correlation"]["mission_id"] = "wrong-mission"
            elif scenario == "tampered-action":
                readback["correlation"]["engineering_action_id"] = "wrong-action"
            elif scenario == "tampered-run":
                readback["run"]["id"] = "wrong-run"
            elif scenario == "tampered-repository":
                readback["submission"]["repository_id"] = "wrong-repository"
            elif scenario == "tampered-producer":
                readback["producer"]["id"] = "wrong-producer"
            elif scenario == "artifact-schema":
                document = json.loads(artifact)
                del document["report"]
                artifact = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
            simulator.seed_terminal(a, readback, artifact)
        if scenario == "post-assessment-reopen":
            cut = _run_phase(root, scenario, "after-a-cut", server.base_url, wheel)
            marker = cut["resume"].get("terminal_continuation", {})
            criteria = {item["criterion"]: item for item in cut["completion"]["criteria"]}
            assert marker.get("phase") == "ASSESSED"
            assert criteria[fixture.K1]["status"] == "PROVEN"
            assert criteria[fixture.K2]["status"] == "UNSATISFIED"
            assert len(cut["actions"]) == len(simulator.submission_ids()) == 1
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
        after_a = _run_phase(root, scenario, "after-a", server.base_url, wheel)
        if scenario == "ambiguous-recovered":
            observed = [event["response"] for event in simulator.audit
                        if event["event"] == "submission_identity_read"]
            assert len(observed) == 1
            fixture_receipts.append(validate_identity_fixture(
                request_a, observed[0], source_readback, source_artifact,
                project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
                consumer_id=CONSUMER, instance_id=INSTANCE, submission_id=a,
            ))
        poll_phases: list[str] = []
        if scenario == "delayed":
            assert after_a["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert len(simulator.submission_ids()) == 1
            for index in range(1, 7):
                phase = f"poll-{index}"
                poll_phases.append(phase)
                after_a = _run_phase(root, scenario, phase, server.base_url, wheel)
                assert len(simulator.submission_ids()) == 1
                assert len(fixture._read(root / "provider-inputs.private.json")) == 1
                if after_a["status"] == "AWAITING_APPROVAL":
                    break
                assert after_a["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert after_a["status"] == "AWAITING_APPROVAL"
            assert poll_phases, "delayed terminal evidence did not require a fresh-process poll"
        if scenario in {"partial", "post-assessment-reopen"}:
            criteria = {item["criterion"]: item for item in after_a["completion"]["criteria"]}
            assert criteria[fixture.K1]["status"] == "PROVEN"
            assert criteria[fixture.K2]["status"] == "UNSATISFIED"
            assert len(after_a["actions"]) == len(simulator.submission_ids()) == 2
            continuation = fixture._read(root / "provider-inputs.private.json")[1]["snapshot"]["continuation_context"]
            assert continuation["prior_actions"][0]["id"] == "synthetic-action-a"
            assert continuation["prior_actions"][0]["status"] == "COMPLETE"
            assert continuation["terminal_evidence"][0]["repository_evidence"]["repository_revision"] == "a" * 40
            assert [item["status"] for item in continuation["criterion_assessments"]] == ["PROVEN", "UNSATISFIED"]
            replay = _run_phase(root, scenario, "replay-b", server.base_url, wheel)
            assert len(replay["actions"]) == len(simulator.submission_ids()) == 2
            assert len(fixture._read(root / "provider-inputs.private.json")) == 2
            assert not any(event["event"] == "submission_duplicate" for event in simulator.audit)
            b = next(item for item in simulator.submission_ids() if item != a)
            request_b = simulator.submitted_payload(b)
            fixture_receipts.append(validate_fixture(
                request_b, simulator.readback(b), None, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=b,
            ))
            timeline = [(event["event"], event.get("submission_id")) for event in simulator.audit]
            assert timeline.index(("terminal_produced", a)) < timeline.index(("submission_accepted", b))
            simulator.complete(b, delivery_revision="b" * 40)
            b_readback, b_artifact = simulator.terminal_documents(b)
            fixture_receipts.append(validate_fixture(
                request_b, b_readback, b_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=b,
            ))
            final = _run_phase(root, scenario, "after-b", server.base_url, wheel)
            assert final["status"] == "AWAITING_APPROVAL" and len(final["actions"]) == 2
            assert final["pause_reason"]["schema_version"] == "forge-final-acceptance-requirement/v1"
            assert all(item["status"] == "PROVEN" for item in final["completion"]["criteria"])
        elif scenario in {"host-recovery", "failed-recovery"}:
            assert after_a["status"] == ("FAILED" if scenario == "failed-recovery" else "BLOCKED")
            denied = _run_phase(root, scenario, "recover-denied", server.base_url, wheel)
            assert denied == after_a and len(simulator.submission_ids()) == 1
            recovered = _run_phase(root, scenario, "recover", server.base_url, wheel)
            assert recovered["status"] in {"WAITING_FOR_EXECUTION", "WAITING_FOR_EVIDENCE"}
            assert len(recovered["actions"]) == 1 and len(simulator.submission_ids()) == 2
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
            retry_id = next(item for item in simulator.submission_ids() if item != a)
            retry_request = simulator.submitted_payload(retry_id)
            assert retry_request["correlation_id"] != request_a["correlation_id"]
            fixture_receipts.append(validate_fixture(
                retry_request, simulator.readback(retry_id), None, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=retry_id,
            ))
            simulator.complete(retry_id, delivery_revision="b" * 40)
            retry_readback, retry_artifact = simulator.terminal_documents(retry_id)
            fixture_receipts.append(validate_fixture(
                retry_request, retry_readback, retry_artifact, project_id=PROJECT,
                repository_id=fixture.SOURCE.repository_id, submission_id=retry_id,
            ))
            final = _run_phase(root, scenario, "after-recovery", server.base_url, wheel)
            assert final["status"] == "AWAITING_APPROVAL"
            assert len(final["actions"]) == 1 and len(simulator.submission_ids()) == 2
            assert [item["outcome"] for item in final["execution_history"]] == [
                "failed" if scenario == "failed-recovery" else "blocked", "complete",
            ]
            assert final["execution_history"][-1]["retry_of_correlation_id"] == request_a["correlation_id"]
            assert all(item["status"] == "PROVEN" for item in final["completion"]["criteria"])
            recovery_summary = {
                "denied_foreign_action": fixture._read(root / "recover-denied.private.json")["type"],
                "original_correlation_id": request_a["correlation_id"],
                "retry_correlation_id": retry_request["correlation_id"],
                "retry_of_correlation_id": final["execution_history"][-1]["retry_of_correlation_id"],
                "terminal_outcomes": [item["outcome"] for item in final["execution_history"]],
            }
        elif scenario in {"successor-stale-gap", "successor-proven-gap", "successor-optional"}:
            expected_code = {
                "successor-stale-gap": "STALE_MISSION_GAP_BINDING",
                "successor-proven-gap": "MISSION_CRITERION_ALREADY_PROVEN",
                "successor-optional": "FOLLOW_UP_NOT_CURRENT_MISSION",
            }[scenario]
            attempts = fixture._read(root / "successor-validation.private.json")
            assert len(attempts) == 2
            assert {(item["lifecycle"], item["error_code"]) for item in attempts} == {
                ("MATERIALIZED", None), ("FAILED", expected_code),
            }
            assert after_a["status"] in {"BLOCKED", "FAILED"}
            assert len(after_a["actions"]) == len(simulator.submission_ids()) == 1
            assert len(fixture._read(root / "provider-inputs.private.json")) == 2
            final = after_a
        elif scenario == "declined-before-run":
            final = after_a
            assert final["status"] in {"BLOCKED", "FAILED"}
            assert final["execution_history"][-1]["failure_code"] == "EP_DECLINED_BEFORE_RUN"
            assert len(final["actions"]) == len(simulator.submission_ids()) == 1
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
            assert [event["event"] for event in simulator.audit] == [
                "submission_accepted", "submission_declined",
            ]
        elif scenario == "budget-exhausted":
            final = after_a
            assert final["status"] == "BLOCKED"
            assert len(final["actions"]) == len(simulator.submission_ids()) == 1
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
            assert final["completion"]["all_required_criteria_proven"] is False
        elif scenario in {"single", "effect-declaration-legacy", "delayed",
                         "pre-send-reopen", "ambiguous-recovered"}:
            final = after_a
            assert final["status"] == "AWAITING_APPROVAL" and len(final["actions"]) == 1
            assert final["pause_reason"]["schema_version"] == "forge-final-acceptance-requirement/v1"
            assert len(simulator.submission_ids()) == 1
        else:
            final = after_a
            assert len(final["actions"]) == len(simulator.submission_ids()) == 1
            assert final["status"] in {"BLOCKED", "FAILED"}
            assert final["waiting_reason"] in {
                "host_dispatch_failed", "host_evidence_failed", "execution_blocked",
            }
            assert final["completion"] is None or final["completion"].get("all_required_criteria_proven") is not True
            assert len(fixture._read(root / "provider-inputs.private.json")) == 1
        if scenario in {"partial", "post-assessment-reopen", "single", "effect-declaration-legacy",
                        "delayed", "pre-send-reopen",
                        "host-recovery", "failed-recovery", "ambiguous-recovered"}:
            fixture._write(root / "final-before-accept.state.private.json", final)
            if observer is not None:observer(root,"final-pending",final)
            accepted = _run_phase(root, scenario, "accept", server.base_url, wheel)
            replayed = _run_phase(root, scenario, "accept-replay", server.base_url, wheel)
            assert accepted == replayed
            assert accepted["status"] == "COMPLETED"
            assert accepted["revision"] == final["revision"] + 1
            assert accepted["approval_record"]["decision_reference"] == final["pause_reason"]["requirement_id"]
            final = accepted
            if observer is not None:observer(root,"accepted",final)
        readback = _run_phase(root, scenario, "readback", server.base_url, wheel)
        assert readback == final
        if scenario in {"partial", "post-assessment-reopen", "single", "effect-declaration-legacy",
                        "delayed", "pre-send-reopen",
                        "host-recovery", "failed-recovery", "ambiguous-recovered"}:
            stopped = _run_phase(root, scenario, "completed-resume", server.base_url, wheel)
            assert stopped == final
        assert not any(event["event"] == "submission_duplicate" for event in simulator.audit)
        if scenario == "ambiguous-recovered":
            assert sum(event["event"] == "submission_identity_read" for event in simulator.audit) == 1
            assert sum(event["event"] == "submission_accepted" for event in simulator.audit) == 1
        accepted = [event["submission_id"] for event in simulator.audit if event["event"] == "submission_accepted"]
        assert accepted == list(simulator.submission_ids())
        posts = sum(request.startswith("POST ") for request in requests)
        assert posts == len(simulator.submission_ids()), "Forge repeated an EP submission POST"
    phases = ["prepare", "after-a", "readback"]
    if scenario == "post-assessment-reopen":
        phases.append("after-a-cut")
    if scenario == "pre-send-reopen":
        phases.append("send-after-reopen")
    if scenario in {"partial", "post-assessment-reopen"}:
        phases += ["replay-b", "after-b"]
    if scenario in {"host-recovery", "failed-recovery"}:
        phases += ["recover-denied", "recover", "after-recovery"]
    phases += poll_phases
    if scenario in {"partial", "post-assessment-reopen", "single", "effect-declaration-legacy",
                    "delayed", "pre-send-reopen",
                    "host-recovery", "failed-recovery", "ambiguous-recovered"}:
        phases += ["accept", "accept-replay", "completed-resume"]
    processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
    assert len(processes) == len(phases), "Forge phases must use distinct OS processes"
    return {"scenario": scenario, "status": final["status"],
            "waiting_reason": final["waiting_reason"], "actions": len(final["actions"]),
            "submissions": len(simulator.submission_ids()), "forge_processes": len(processes),
            "governance_rejections": governance_negative,
            "producer_fixtures": fixture_receipts,
            "producer_fixture_negatives": fixture_negatives,
            "phase_statuses": {phase: fixture._read(root / f"{phase}.state.private.json")["status"]
                               for phase in phases},
            "planner_invocations": len(fixture._read(root / "provider-inputs.private.json")),
            "waiting_polls": len(poll_phases),
            "submission_posts": posts, "ep_http_requests": len(requests),
            **({"successor_rejection": expected_code} if scenario in {
                "successor-stale-gap", "successor-proven-gap", "successor-optional",
            } else {}),
            **({"no_run_disposition": {"state": "DECLINED", "failure_code": "EP_DECLINED_BEFORE_RUN"}}
               if scenario == "declined-before-run" else {}),
            **({"recovery": recovery_summary} if recovery_summary is not None else {})}


def _concurrent_start_case(root: Path, wheel: Path) -> dict:
    """Race two installed Forge processes at the public zero-Action start gate."""
    root.mkdir()
    fixture._write(root / "artifact-a.json", {
        "report": {"fields": ["report_data"]},
        "policy": {"authorization_required": True},
    })
    fixture._write(root / "artifact-b.json", {
        "report": {"fields": ["report_data"]},
        "policy": {"authorization_required": True},
    })
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
    )
    server = EpSimulatorServer(simulator)
    requests = _count_ep_http_requests(server)
    with server:
        staged = _run_phase(root, "concurrent-start", "prepare", server.base_url, wheel)
        assert staged["status"] == "APPROVED_PLANNABLE" and not staged["actions"]
        children = []
        handles = []
        try:
            for phase in ("race-start-a", "race-start-b"):
                command = [sys.executable, "-I", str(Path(__file__).resolve()),
                           "--wheel", str(wheel), "--output-dir", str(root),
                           "--scenario", "concurrent-start", "--phase", phase,
                           "--endpoint", server.base_url]
                handle = (root / f"{phase}.raw.private.log").open("w")
                handles.append(handle)
                child = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT,
                                         env=_child_env(root), cwd=root)
                children.append(child)
                deadline = time.monotonic() + 20
                while not (root / f"{phase}.ready.private").exists():
                    if time.monotonic() >= deadline or child.poll() is not None:
                        raise RuntimeError("installed starter did not open the same Runtime Instance")
                    time.sleep(0.01)
            (root / "race-go.private").write_text("start")
            for phase, child in zip(("race-start-a", "race-start-b"), children):
                if child.wait(timeout=90) != 0:
                    raise RuntimeError(f"installed {phase} failed after opening Runtime Instance")
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=5)
            for handle in handles:
                handle.close()
        outcomes = [fixture._read(root / f"{phase}.race.private.json")
                    for phase in ("race-start-a", "race-start-b")]
        rejection = next((item for item in outcomes if item["result"] == "REJECTED"), {})
        expected_rejections = {
            RuntimeServiceBusy.__name__: "canonical runtime is busy",
            MissionStateStoreError.__name__: "mission state transition CREATED -> CREATED is not permitted",
            InstalledDynamicMissionError.__name__: "public start requires a canonically admitted zero-Action Mission",
        }
        if (sorted(item["result"] for item in outcomes) != ["REJECTED", "STARTED"]
                or rejection.get("reason") != expected_rejections.get(rejection.get("type"))
                or len(simulator.submission_ids()) != 1
                or len(fixture._read(root / "provider-inputs.private.json")) != 1):
            raise RuntimeError("concurrent starters crossed the single-flight Action boundary")
        submission_id = simulator.submission_ids()[0]
        payload = simulator.submitted_payload(submission_id)
        pending = validate_fixture(
            payload, simulator.readback(submission_id), None, project_id=PROJECT,
            repository_id=fixture.SOURCE.repository_id, submission_id=submission_id,
        )
        simulator.complete(submission_id, delivery_revision="a" * 40)
        terminal_readback, terminal_artifact = simulator.terminal_documents(submission_id)
        terminal = validate_fixture(
            payload, terminal_readback, terminal_artifact, project_id=PROJECT,
            repository_id=fixture.SOURCE.repository_id, submission_id=submission_id,
        )
        final = _run_phase(root, "concurrent-start", "after-a", server.base_url, wheel)
        assert final["status"] == "AWAITING_APPROVAL" and len(final["actions"]) == 1
        assert all(item["status"] == "PROVEN" for item in final["completion"]["criteria"])
        fixture._write(root / "final-before-accept.state.private.json", final)
        accepted = _run_phase(root, "concurrent-start", "accept", server.base_url, wheel)
        replayed = _run_phase(root, "concurrent-start", "accept-replay", server.base_url, wheel)
        readback = _run_phase(root, "concurrent-start", "readback", server.base_url, wheel)
        stopped = _run_phase(root, "concurrent-start", "completed-resume", server.base_url, wheel)
        assert accepted == replayed == readback == stopped
        assert accepted["status"] == "COMPLETED"
        posts = [request for request in requests if request.startswith("POST ")]
        assert len(posts) == 1 and not any(event["event"] == "submission_duplicate"
                                            for event in simulator.audit)
    phases = ("prepare", "race-start-a", "race-start-b", "after-a",
              "accept", "accept-replay", "readback", "completed-resume")
    processes = {fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in phases}
    assert len(processes) == len(phases)
    return {
        "scenario": "concurrent-start", "status": "COMPLETED", "actions": 1,
        "submissions": 1, "submission_posts": 1, "planner_invocations": 1,
        "forge_processes": len(processes), "race_outcomes": outcomes,
        "producer_fixtures": [pending, terminal],
        "phase_statuses": {phase: fixture._read(root / f"{phase}.state.private.json")["status"]
                           for phase in phases},
    }


def _run_preflight_child(args: argparse.Namespace, parser: argparse.ArgumentParser,
                         root: Path) -> bool:
    if not args.phase or not args.phase.startswith("preflight-"):
        return False
    if not args.preflight_case or not args.endpoint or args.scenario or args.governance_case or args.provider_case:
        parser.error("preflight child phase requires case and loopback endpoint")
    with _loopback_only(args.endpoint):
        _preflight_phase(root, args.preflight_case, args.phase, args.endpoint)
    return True


def _provider_phase(root: Path, case: str, phase: str, endpoint: str) -> None:
    if phase == "provider-stage":
        _prepare(root, case, endpoint, start=False, capture_phase=phase)
        return
    with ExitStack() as stack:
        runtime = _open(root, stack, provider_case=case)
        mission_id = fixture._read(root / "population.private.json")["mission_id"]
        before = runtime.states.get(mission_id)
        failure = None
        try:
            if before.status.value == "APPROVED_PLANNABLE":
                runtime.start(mission_id, _initial_truth())
            else:
                runtime.resume(mission_id)
        except Exception as error:
            failure = {"type": type(error).__name__}
        state = _capture(root, runtime, phase)
        attempts = [json.loads(row["document"]) for row in runtime.database._connection.execute(
            "SELECT document FROM action_derivations ORDER BY derivation_id"
        ).fetchall()]
        fixture._write(root / f"{phase}.provider.private.json", {
            "failure": failure, "status": state["status"], "pid": os.getpid(),
            "attempts": len(fixture._read(root / "provider-attempts.private.json", [])),
            "durable_attempts": [{
                "derivation_id": item["derivation_id"], "processing_phase": item["processing_phase"],
                "lifecycle": item["lifecycle"], "error_code": item.get("error_code"),
            } for item in attempts],
            "durable_results": runtime.database._connection.execute(
                "SELECT COUNT(*) FROM action_derivation_results"
            ).fetchone()[0],
        })


def _run_provider_phase(root: Path, case: str, phase: str,
                        endpoint: str, wheel: Path) -> dict:
    command = [sys.executable, "-I", str(Path(__file__).resolve()),
               "--wheel", str(wheel), "--output-dir", str(root),
               "--provider-case", case, "--phase", phase, "--endpoint", endpoint]
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90,
                            env=_child_env(root), cwd=root)
    (root / f"{phase}.raw.private.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"installed provider {case}/{phase} failed; see private phase log")
    observation = fixture._read(root / f"{phase}.state.private.json" if phase == "provider-stage"
                                else root / f"{phase}.provider.private.json")
    fixture._append(root / "stage-trace.public.json", {
        "phase": phase, "status": observation.get("status", "REJECTED"),
        "duration_ms": round((time.monotonic() - started) * 1000)})
    return observation


def _provider_case(root: Path, case: str, wheel: Path) -> dict:
    root.mkdir(parents=True)
    simulator = EpSimulatorState(
        project_id=PROJECT, repository_id=fixture.SOURCE.repository_id,
        repository_identity=fixture.SOURCE.github_repository, consumer_id=CONSUMER,
        instance_id=INSTANCE, bearer_token=TOKEN,
    )
    with EpSimulatorServer(simulator) as server:
        staged = _run_provider_phase(root, case, "provider-stage", server.base_url, wheel)
        first = _run_provider_phase(root, case, "provider-first", server.base_url, wheel)
        repeat = _run_provider_phase(root, case, "provider-repeat", server.base_url, wheel)
    states = [fixture._read(root / f"{phase}.state.private.json") for phase in (
        "provider-stage", "provider-first", "provider-repeat",
    )]
    processes = [fixture._read(root / f"{phase}.process.private.json")["pid"] for phase in (
        "provider-stage", "provider-first", "provider-repeat",
    )]
    if (len(set(processes)) != 3 or staged["status"] != "APPROVED_PLANNABLE"
            or first["status"] not in {"BLOCKED", "FAILED", "APPROVED_PLANNABLE"}
            or states[1]["actions"] or states[2]["actions"]
            or states[1]["intents"] or states[2]["intents"]
            or simulator.submission_ids()
            or any(event["event"] == "submission_accepted" for event in simulator.audit)):
        raise RuntimeError(f"{case} escaped the provider denial boundary")
    if first["attempts"] != (0 if case in {"unavailable", "login-expired"} else 1) or repeat["attempts"] != first["attempts"]:
        raise RuntimeError(f"{case} generated again after a failed or uncertain attempt")
    if states[1] != states[2]:
        raise RuntimeError(f"{case} changed durable Mission state on fresh-process repeat")
    expected_phase = {
        "unavailable": None,
        "login-expired": None,
        "not-started": "GENERATION_NOT_STARTED",
        "local-rejected": "GENERATION_NOT_STARTED",
        "invalid-output": "DETERMINISTIC_REJECTION",
        "scope-expansion": "DETERMINISTIC_REJECTION",
        "scope-outside": "DETERMINISTIC_REJECTION",
        "unknown-dependency": "DETERMINISTIC_REJECTION",
        "missing-human-gate": "DETERMINISTIC_REJECTION",
        "missing-risk-input": "DETERMINISTIC_REJECTION",
        "ambiguous": "GENERATION_MAY_HAVE_HAPPENED",
    }[case]
    durable = first["durable_attempts"]
    if (len(durable) != (0 if expected_phase is None else 1)
            or (expected_phase is not None and (durable[0]["processing_phase"] != expected_phase
                                                 or durable[0]["lifecycle"] != "FAILED"))
            or repeat["durable_attempts"] != durable
            or repeat["durable_results"] != first["durable_results"]):
        raise RuntimeError(f"{case} did not retain one classified durable attempt")
    return {
        "case": case, "status": first["status"], "attempts": first["attempts"],
        "failure": first["failure"], "repeat_failure": repeat["failure"],
        "durable_attempts": durable, "durable_results": first["durable_results"],
        "submissions": 0, "forge_processes": len(processes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--governance-case", choices=GOVERNANCE_CASES)
    parser.add_argument("--preflight-case", choices=tuple(PREFLIGHT_CASES))
    parser.add_argument("--provider-case", choices=PROVIDER_CASES)
    parser.add_argument("--phase", choices=("prepare", "send-after-reopen", "after-a-cut", "after-a",
                                            "replay-b", "after-b",
                                            "recover-denied", "recover", "after-recovery",
                                            "race-start-a", "race-start-b",
                                            *(f"poll-{index}" for index in range(1, 7)), "accept",
                                            "accept-replay", "completed-resume", "readback",
                                            "scope-denied", "new-scope-prepare", "new-scope-after",
                                            "new-scope-accept", "new-scope-readback",
                                            "ambiguous-replay", "governance-first", "governance-repeat",
                                            "provider-stage", "provider-first", "provider-repeat",
                                            "preflight-stage", "preflight-first", "preflight-repeat"))
    parser.add_argument("--endpoint")
    args = parser.parse_args()
    if args.source_revision is not None and (
        len(args.source_revision) != 40 or any(character not in "0123456789abcdef" for character in args.source_revision)
    ):
        parser.error("source revision must be one exact Git commit SHA")
    root = args.output_dir.resolve()
    try:
        artifact = _installed_wheel(
            args.wheel.resolve(), source_revision=args.source_revision,
            verify_source=not bool(args.phase),
        )
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        if root.exists() and any(root.iterdir()):
            raise RuntimeError("qualification output directory must be fresh") from error
        root.mkdir(parents=True, exist_ok=True)
        report = {
            "qualification": "INSTALLED_FORGE_HTTP_SUCCESSOR_V1",
            "source_revision": args.source_revision, "result": "FAIL",
            "failure": {"stage": "installed_wheel_identity", "type": type(error).__name__},
        }
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 1
    if _run_preflight_child(args, parser, root):
        return 0
    if args.phase:
        if args.phase.startswith("provider-"):
            if not args.provider_case or not args.endpoint or args.scenario or args.governance_case or args.preflight_case:
                parser.error("provider child phase requires one case and loopback endpoint")
            with _loopback_only(args.endpoint):
                _provider_phase(root, args.provider_case, args.phase, args.endpoint)
            return 0
        if args.phase.startswith("governance-"):
            if not args.governance_case or not args.endpoint or args.scenario or args.preflight_case:
                parser.error("governance child phase requires case and loopback endpoint")
            with _loopback_only(args.endpoint):
                _governance_phase(root, args.governance_case, args.phase, args.endpoint)
            return 0
        if not args.scenario or not args.endpoint or args.governance_case or args.preflight_case or args.provider_case:
            parser.error("child phase requires scenario and loopback endpoint")
        with _loopback_only(args.endpoint):
            _phase(root, args.scenario, args.phase, args.endpoint)
        return 0
    if root.exists() and any(root.iterdir()):
        raise RuntimeError("qualification output directory must be fresh")
    if sum(bool(value) for value in (args.governance_case, args.scenario,
                                     args.preflight_case, args.provider_case)) > 1:
        parser.error("focused qualification filters cannot be combined")
    root.mkdir(parents=True, exist_ok=True)
    try:
        producer_source = source_receipt()
    except (OSError, ValueError, KeyError, TypeError) as error:
        report = {"qualification": "INSTALLED_FORGE_HTTP_SUCCESSOR_V1", "artifact": artifact,
                  "source_revision": args.source_revision, "result": "FAIL",
                  "failure": {"stage": "producer_fixture_source", "type": type(error).__name__}}
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 1
    scenarios = SCENARIOS if not args.scenario else (args.scenario,)
    report = {"qualification": "INSTALLED_FORGE_HTTP_SUCCESSOR_V1", "artifact": artifact,
              "source_revision": args.source_revision,
              "qualifier_sha256": "sha256:" + sha256(Path(__file__).read_bytes()).hexdigest(),
              "producer_fixture_source": producer_source,
              "effect_producer_fixture_source": effect_source_receipt(),
              "ep_preflight_source": EP_PREFLIGHT_SOURCE,
              "ep_identity_readback_source": EP_IDENTITY_READBACK_SOURCE,
              "required_producer_fixture_negatives": [
                  "missing-provenance", "changed-provenance", "wrong-version", "changed-digest",
                  "foreign-project", "foreign-repository", "foreign-submission", "foreign-run",
                  "unexpected-field", "missing-field", "queued-operation", "queued-reason",
                  "queued-submission-state",
                  "terminal-run-state", "terminal-delivery-qualified", "changed-artifact-bytes",
                  "artifact-unexpected-field", "artifact-missing-field", "artifact-foreign-run",
                  "artifact-run-timing", "artifact-host-null", "artifact-host-empty",
                  "artifact-host-commit", "artifact-host-digest", "artifact-requested-revision",
                  "artifact-delivery-revision", "artifact-baseline-transition", "artifact-report-id",
              ],
              "ep_simulator_contract": SIMULATOR_CONTRACT_VERSION,
              "required_preflight_cases": list(PREFLIGHT_CASES),
              "required_governance_cases": list(GOVERNANCE_CASES),
              "required_provider_cases": list(PROVIDER_CASES),
              "required_installed_identity_negative": "installed-wheel-byte-drift",
              "required_runtime_storage_negatives": ["wrong-runtime-marker", "missing-runtime-storage",
                                                     "unsupported-runtime-schema"],
              "required_http_scenarios": list(SCENARIOS),
              "test_doubles": ["stateful-loopback-EP-HTTP-simulator",
                               "deterministic-external-Codex-process-transport",
                               "synthetic-operator-identity", "synthetic-secure-store-resolver",
                               "immutable-synthetic-repository-artifact-reader",
                               "isolated-local-Git-execution-fixture"],
              "limitations": ["Synthetic Business/Architecture actors and repository JSON; deterministic external Codex transport.",
                              "Local EP HTTP simulator only; no live EP/provider or production Mission claim.",
                              "EP v1.3 identity readback recovers accepted lost-ack submissions; v1.2-only hosts fail closed.",
                              "EP producer v1.2 schema omits two retry-resolution fields emitted by its source; this subset validates source shape, not full schema conformance.",
                              "Synthetic repository-effect violations qualify Forge rejection, not real EP sandbox enforcement.",
                              "Effect positives use actual local Git source/output commits; remote publication is an EP fixture and sends no GitHub request.",
                              "FIE-27 selects a separately approved new Candidate scope; previous Mission history and allowances remain immutable.",
                              "No outer-loop or live activation qualification."]}
    if not any((args.scenario, args.preflight_case, args.governance_case, args.provider_case)):
        try:
            report["installed_identity_negative"] = _installed_identity_negative(
                root / "installed-identity-negative", args.wheel.resolve(),
            )
            report["runtime_storage_negatives"] = _installed_runtime_storage_negatives(
                root / "runtime-storage-negative",
            )
        except Exception as error:
            report.update(result="FAIL", failure={
                "stage": "installed_identity_negative", "type": type(error).__name__,
            })
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    preflight_cases = ()
    if args.preflight_case:
        preflight_cases = (args.preflight_case,)
    elif not args.governance_case and not args.scenario and not args.provider_case:
        preflight_cases = PREFLIGHT_CASES
    preflight = []
    for case in preflight_cases:
        try:
            preflight.append(_with_case_cleanup(
                root / "preflight-matrix" / case, _preflight_case, case, args.wheel.resolve(),
            ))
        except Exception as error:
            report.update(result="FAIL", preflight_matrix=preflight,
                          failure={"preflight_case": case, "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report["preflight_matrix"] = preflight
    if args.preflight_case:
        report["result"] = "FOCUSED_PASS"
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 0
    governance_cases = ()
    if args.governance_case:
        governance_cases = (args.governance_case,)
    elif not args.scenario and not args.provider_case:
        governance_cases = GOVERNANCE_CASES
    governance = []
    for case in governance_cases:
        try:
            governance.append(_with_case_cleanup(
                root / "governance-matrix" / case, _governance_case, case, args.wheel.resolve(),
            ))
        except Exception as error:
            report.update(result="FAIL", governance_matrix=governance,
                          failure={"governance_case": case, "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report["governance_matrix"] = governance
    if args.governance_case:
        report["result"] = "FOCUSED_PASS"
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 0
    provider_cases = (args.provider_case,) if args.provider_case else (
        PROVIDER_CASES if not args.scenario else ()
    )
    provider_results = []
    for case in provider_cases:
        try:
            provider_results.append(_with_case_cleanup(
                root / "provider-matrix" / case, _provider_case, case, args.wheel.resolve(),
            ))
        except Exception as error:
            report.update(result="FAIL", provider_matrix=provider_results,
                          failure={"provider_case": case, "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report["provider_matrix"] = provider_results
    if args.provider_case:
        report["result"] = "FOCUSED_PASS"
        fixture._write(root / "installed-http-successor.public.json", report)
        print(json.dumps(report, sort_keys=True))
        return 0
    summaries = []
    for scenario in scenarios:
        try:
            if scenario == "concurrent-start":
                summaries.append(_with_case_cleanup(
                    root / scenario, _concurrent_start_case, args.wheel.resolve(),
                ))
            else:
                summaries.append(_with_case_cleanup(
                    root / scenario, _scenario, scenario, args.wheel.resolve(),
                ))
        except Exception as error:
            report.update(result="FAIL", scenarios=summaries,
                          failure={"scenario": scenario, "type": type(error).__name__,
                                   "frames": [{"file": Path(frame.filename).name,
                                               "function": frame.name, "line": frame.lineno}
                                              for frame in traceback.extract_tb(error.__traceback__)],
                                   "stage_trace": fixture._read(
                                       root / scenario / "stage-trace.public.json", [])})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    if not args.scenario:
        observed = [item["case"] for item in summaries[0]["producer_fixture_negatives"]]
        if observed != report["required_producer_fixture_negatives"]:
            report.update(result="FAIL", scenarios=summaries,
                          failure={"type": "ProducerFixtureMatrixIncomplete"})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
    report.update(result=("FOCUSED_PASS" if args.scenario else "PASS"), scenarios=summaries)
    if not args.scenario:
        try:
            report["fci_manifest"] = _fci_manifest(report)
        except (OSError, ValueError, KeyError, RuntimeError, TypeError) as error:
            report.update(result="FAIL", failure={"stage": "fci_manifest", "type": type(error).__name__})
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
        if report["fci_manifest"]["result"] != "PASS":
            report["result"] = "NOT_QUALIFIED"
            report["failure"] = {"stage": "fci_manifest", "type": "RequiredFieCaseMissing"}
            fixture._write(root / "installed-http-successor.public.json", report)
            print(json.dumps(report, sort_keys=True))
            return 1
        report["result"] = "FORGE_INNER_LOOP_CI_PASS"
    fixture._write(root / "installed-http-successor.public.json", report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
