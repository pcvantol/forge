"""Packaged operator adapter for canonical Mission governance and execution."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from typing import Any
from urllib.parse import quote

from forge.governance_authority import (
    ArchitecturePlanningEvidence, CanonicalArchitectureWorkspace,
    CanonicalBusinessWorkspace, CanonicalGovernanceRepository,
    MissionPlanningEvidenceEnvelope,
)
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_observation import canonical_digest
from forge.completion.host_control_observer import approved_observation_selector
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from forge.runtime.bootstrap import RuntimeBootstrap
from forge.runtime.data_root import DataRootResolver
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.runtime.mission_controller import MissionController, request_stop, require_no_controller
from forge.runtime.service import RuntimeServiceLock
from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter
from forge.state import MissionExecutionStatus, MissionStateStore


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _input(path: str) -> dict[str, Any]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("Mission input must be a JSON object")
    return document


def _contract(document: dict[str, Any]) -> tuple[ArchitecturePlanningEvidence, ArchitectureMission]:
    mission_fields = dict(document["mission"])
    mission_fields["id"] = "MISSION-PREVIEW"
    mission_fields["status"] = ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING.value
    mission = ArchitectureMission.from_dict(mission_fields)
    if not mission.is_engineering_ready() or not mission.criterion_assessment_contracts:
        raise ValueError("Mission requires complete engineering readiness and criterion contracts")
    if len(mission.scope) != 1:
        raise ValueError("the installed serial Mission requires exactly one approved scope")
    # EP's versioned Forge provenance contract caps each approved execution
    # constraint at 128 characters. Catch an oversized Mission before Intake
    # allocates an ID or the runner persists an unsendable Action.
    if any(len(value) > 128 for value in mission.engineering_constraints):
        raise ValueError("EP execution constraint exceeds the 128-character host limit")
    if len(mission.engineering_constraints) > 64:
        raise ValueError("EP execution constraints contain more than 64 entries")
    if mission.repository_evidence_source is None:
        raise ValueError("Mission requires an approved repository source for fresh initial Truth")
    delegation = tuple(value for value in mission.engineering_constraints
                       if value.startswith("ep-merge-delegation:"))
    if len(delegation) != 1 or re.fullmatch(r"ep-merge-delegation:[0-9a-f]{32}", delegation[0]) is None:
        raise ValueError("Mission requires one bounded EP merge delegation reference")
    if (any(requirement.kind == "host_control" for contract in mission.criterion_assessment_contracts
            for requirement in contract.requirements)
            and mission.engineering_constraints.count("ep-delivery-control-validation:1") != 1):
        raise ValueError("host control criteria require approved EP delivery-revision validation")
    selectors = [value.split(":", 1)[1] for value in mission.engineering_constraints
                 if value.startswith("ep-delivery-unittest:")]
    if selectors:
        if len(selectors) > 8 or len(set(selectors)) != len(selectors):
            raise ValueError("EP unittest observation selectors must be distinct and bounded")
        approved = {approved_observation_selector(requirement)
                    for contract in mission.criterion_assessment_contracts
                    for requirement in contract.requirements if requirement.kind == "host_control"
                    and requirement.validation_id.startswith("unittest_selector_")}
        if None in approved or set(selectors) != approved:
            raise ValueError("EP unittest selectors require exact approved criterion bindings")
    elif any(requirement.kind == "host_control" and
             requirement.validation_id.startswith("unittest_selector_")
             for contract in mission.criterion_assessment_contracts
             for requirement in contract.requirements):
        raise ValueError("EP unittest criterion lacks its approved execution selector")
    planning = ArchitecturePlanningEvidence.from_dict(document["planning"])
    specification_digest = canonical_digest(mission.to_dict())
    if planning.mission_spec_digest is not None and planning.mission_spec_digest != specification_digest:
        raise ValueError("Mission specification differs from approved planning input")
    planning = replace(planning, mission_spec_digest=specification_digest)
    if (mission.candidate_id != document["candidate_id"]
            or mission.architecture_review_reference != document["architecture_decision_id"]
            or mission.scope != planning.scope
            or mission.criterion_assessment_contracts != planning.criterion_assessment_contracts
            or mission.maximum_actions != planning.maximum_actions
            or mission.maximum_consecutive_no_progress_actions != planning.maximum_consecutive_no_progress_actions
            or mission.repository_evidence_source != planning.repository_evidence_source):
        raise ValueError("Mission and approved planning contract differ")
    if planning.provenance_revision != document["subject_revision"]:
        raise ValueError("planning provenance revision differs from the subject")
    return planning, mission


def _inspect_document(document: dict[str, Any]) -> dict[str, object]:
    planning, mission = _contract(document)
    unsupported = sorted({req.kind for contract in planning.criterion_assessment_contracts
                          for req in contract.requirements if req.kind not in {"repository_json", "host_control"}})
    incomplete_controls = sorted(req.requirement_id for contract in planning.criterion_assessment_contracts
                                 for req in contract.requirements if req.kind == "host_control" and
                                 (not req.control_definition_digest or not req.validation_id
                                  or not req.validation_profile_version or not req.profile_reference
                                  or not req.control_category or req.minimum_test_count < 1))
    return {"status": "VALID" if not unsupported and not incomplete_controls else "UNSUPPORTED_EVIDENCE",
            "candidate_id": mission.candidate_id,
            "criteria": list(mission.acceptance_criteria), "evidence_kinds": sorted({req.kind
            for contract in planning.criterion_assessment_contracts for req in contract.requirements}),
            "unsupported": unsupported, "incomplete_host_controls": incomplete_controls,
            "planning_digest": planning.digest, "allocated": False}


def inspect(path: str) -> dict[str, object]:
    return _inspect_document(_input(path))


def _governance(data_root: str):
    from forge._version import canonical_version
    database = RuntimeBootstrap(data_root=data_root, forge_version=canonical_version()).open()
    try:
        repository = CanonicalGovernanceRepository.for_runtime(
            database, MacOSGeneratedUIDIdentityAdapter().resolve, data_root=data_root)
        return database, repository
    except Exception:
        database.close()
        raise


def approve(data_root: str, path: str, role: str) -> dict[str, object]:
    document = _input(path)
    if _inspect_document(document)["status"] != "VALID":
        raise ValueError("Mission input has unsupported evidence requirements")
    planning, mission = _contract(document)
    database, repository = _governance(data_root)
    try:
        with require_no_controller(database.path), RuntimeServiceLock(database.path).acquire():
            context = repository.operators.context()
            if role == "business":
                digest = CanonicalBusinessWorkspace(repository, context).approve(
                    decision_id=document["business_decision_id"], candidate_id=mission.candidate_id,
                    revision=document["subject_revision"], scope=planning.scope, gates=planning.human_gates)
            else:
                digest = CanonicalArchitectureWorkspace(repository, context).approve(
                    decision_id=document["architecture_decision_id"], candidate_id=mission.candidate_id,
                    revision=document["subject_revision"], planning=planning)
        return {"status": "RECORDED", "role": role, "decision_digest": digest,
                "candidate_id": mission.candidate_id}
    finally:
        database.close()


def admit(data_root: str, path: str) -> dict[str, object]:
    document = _input(path)
    if _inspect_document(document)["status"] != "VALID":
        raise ValueError("Mission input has unsupported evidence requirements")
    planning, mission = _contract(document)
    database, repository = _governance(data_root)
    try:
        with require_no_controller(database.path), RuntimeServiceLock(database.path).acquire():
            envelope = MissionPlanningEvidenceEnvelope.compose(
                repository, subject_id=mission.candidate_id, subject_revision=document["subject_revision"],
                business_decision_id=document["business_decision_id"],
                architecture_decision_id=document["architecture_decision_id"], planning=planning)
            from forge.intake import MissionIntake
            state = MissionStateStore(database, data_root=data_root)
            intake = MissionIntake(state, _now)
            intake.validate_canonical_mission_contract(mission, envelope, repository)
            mission_id = database.allocate_next_mission_id(
                source="canonical-governance-envelope:" + envelope.digest, allocated_at=_now())
            mission = replace(mission, id=mission_id)
            admitted = intake.admit_canonical_approved_mission(mission, envelope, repository)
        return {"status": admitted.status.value, "mission_id": mission_id,
                "envelope_digest": envelope.digest, "action_count": len(admitted.actions)}
    finally:
        database.close()


def status(data_root: str, mission_id: str) -> dict[str, object]:
    root = DataRootResolver(cli_data_root=data_root).resolve()
    database = root / "forge.db"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute("SELECT document FROM mission_state WHERE mission_id = ?", (mission_id,)).fetchone()
        if row is None:
            raise ValueError("unknown Mission")
        planning_attempts = connection.execute(
            "SELECT COUNT(*) FROM action_derivations WHERE mission_id = ?", (mission_id,)).fetchone()[0]
    state = MissionStateStore._decode(row[0])
    attempts = tuple({"correlation_id": item.get("correlation_id"),
                      "host_run_id": item.get("host_run_id"),
                      "receipt_id": item.get("receipt_id"), "outcome": item.get("outcome"),
                      "retry_of_correlation_id": item.get("retry_of_correlation_id")}
                     for item in state.execution_history)
    current = state.current_engineering_action or {}
    truth = state.repository_truth or {}
    return {"mission_id": state.mission_id, "status": state.status.value,
            "revision": state.revision, "action_ids": [item["id"] for item in state.actions],
            "current_action_id": current.get("id"),
            "planning_attempts_recorded": planning_attempts,
            "materialized_plans": sum(bool(item.get("derivation_id")) for item in state.planning_history),
            "planning_invocations": None,
            "repository_revision": truth.get("revision"), "execution_attempts": attempts,
            "recovery_authorizations": sum(item.get("reason") == "authorized_recovery"
                                            for item in state.state_history),
            "waiting_reason": state.waiting_reason, "completion": state.completion, "read_only": True}


def _github_default_head(repository: str) -> tuple[str, str]:
    """Read the current default-branch commit through the configured gh identity."""
    def read(path: str) -> dict[str, Any]:
        try:
            result = subprocess.run(["gh", "api", "--hostname", "github.com",
                                     "-H", "Accept: application/vnd.github+json", path],
                                    capture_output=True, text=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ValueError("approved repository head is unavailable") from error
        if result.returncode:
            raise ValueError("approved repository head is unavailable")
        try:
            value = json.loads(result.stdout)
        except ValueError as error:
            raise ValueError("approved repository head readback is invalid") from error
        if not isinstance(value, dict):
            raise ValueError("approved repository head readback is invalid")
        return value

    metadata = read("repos/" + repository)
    branch = metadata.get("default_branch")
    full_name = metadata.get("full_name")
    if (not isinstance(full_name, str) or full_name.lower() != repository.lower()
            or branch != "main"):
        raise ValueError("approved repository identity or default branch differs")
    commit = read("repos/" + repository + "/commits/" + quote(branch, safe=""))
    revision = commit.get("sha")
    if (not isinstance(revision, str) or len(revision) != 40
            or any(character not in "0123456789abcdef" for character in revision)):
        raise ValueError("approved repository head revision is invalid")
    return branch, revision


def _verified_initial_truth(runtime: InstalledDynamicMissionRuntime, mission_id: str,
                            requested: RepositoryTruthSnapshot) -> RepositoryTruthSnapshot:
    state = runtime.states.get(mission_id)
    mission = ArchitectureMission.from_dict(dict(state.mission))
    source = mission.repository_evidence_source
    if (source is None or source.repository_id != runtime.host.config.repository_id
            or requested.repository_id != source.repository_id):
        raise ValueError("initial Repository Truth lacks an approved matching repository source")
    branch, revision = _github_default_head(source.github_repository)
    if requested.repository_revision != revision:
        raise ValueError("initial Repository Truth is stale or differs from the approved repository head")
    identity = {"repository": source.github_repository, "branch": branch, "revision": revision}
    observed_digest = "sha256:" + sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"))
                                         .encode("utf-8")).hexdigest()
    return RepositoryTruthSnapshot(
        "github-default-head:" + source.github_repository + ":" + revision,
        source.repository_id, revision, _now(),
        (RepositoryTruthEvidence("github-default-head", "git_ref", revision,
                                 "https://github.com/" + source.github_repository + "/tree/" + revision,
                                 observed_digest),))


def _require_ep_mission_capabilities(runtime: InstalledDynamicMissionRuntime, mission_id: str,
                                     *, allow_pending_readback: bool = False) -> bool | None:
    declaration = runtime.host.preflight()
    contracts = declaration.get("contracts") if isinstance(declaration, dict) else None
    required = ("validation_controls", "delivery_revision_validation", "bounded_merge_delegation")
    if (not isinstance(contracts, dict) or any(not isinstance(contracts.get(name), list)
            or "1.0" not in contracts[name] for name in required)):
        raise ValueError("installed EP lacks the required autonomous Mission capabilities")
    state = runtime.states.get(mission_id)
    mission = ArchitectureMission.from_dict(dict(state.mission))
    if (any(value.startswith("ep-delivery-unittest:") for value in mission.engineering_constraints)
            and "1.1" not in contracts["validation_controls"]):
        raise ValueError("installed EP lacks approved unittest observation capability")
    approved = state.admission_contract or {}
    source = mission.repository_evidence_source
    references = [value.split(":", 1)[1] for value in mission.engineering_constraints
                  if re.fullmatch(r"ep-merge-delegation:[0-9a-f]{32}", value)]
    if len(references) != 1 or source is None or not approved.get("subject_revision"):
        raise ValueError("admitted Mission lacks its approved EP merge scope")
    grant = runtime.host.merge_delegation_status(references[0])
    try:
        expiry = datetime.fromisoformat(grant["expires_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("EP merge delegation expiry is invalid") from error
    if (grant.get("mission_id") != mission_id
            or grant.get("mission_revision") != approved["subject_revision"]
            or grant.get("repository_id") != source.repository_id
            or not isinstance(grant.get("github_repository"), str)
            or grant["github_repository"].lower() != source.github_repository.lower()
            or grant.get("base_branch") != "main"
            or not isinstance(grant.get("actor_reference"), str) or not grant["actor_reference"]
            or not isinstance(grant.get("roles"), list)
            or any(not isinstance(role, str) for role in grant["roles"])
            or not {"IMPLEMENTATION", "FINALIZATION", "RECONCILIATION"}.issubset(grant["roles"])):
        raise ValueError("EP merge delegation does not bind the approved active Mission and repository")
    active = (grant.get("status") == "ACTIVE" and grant.get("activated_at") is not None
              and grant.get("revoked_at") is None and expiry.tzinfo is not None
              and expiry > datetime.now(UTC))
    if active:
        return True
    pending = state.execution_correlation or {}
    continuation = (state.resume or {}).get("terminal_continuation")
    if (allow_pending_readback and grant.get("status") in {"EXPIRED", "REVOKED", "DRIFT"}
            and ((state.status is MissionExecutionStatus.WAITING_FOR_EVIDENCE
                  and isinstance(pending.get("host_run_id"), str) and pending["host_run_id"])
                 or (state.status is MissionExecutionStatus.ACTIVE
                     and isinstance(continuation, dict)
                     and continuation.get("mission_complete") is False))):
        return None if grant["status"] == "DRIFT" else False
    raise ValueError("EP merge delegation is inactive for new Mission work")


def run(data_root: str, mission_id: str, *, truth_path: str | None,
        poll_seconds: float, maximum_wait_seconds: float) -> dict[str, object]:
    truth = None
    if truth_path is not None:
        document = _input(truth_path)
        truth = RepositoryTruthSnapshot(
            document["id"], document["repository_id"], document["repository_revision"],
            document["observed_at"], tuple(RepositoryTruthEvidence(**item) for item in document["evidence"]),
            schema_version=document["schema_version"])
    with InstalledDynamicMissionRuntime.open(data_root) as runtime:
        active_grant = _require_ep_mission_capabilities(
            runtime, mission_id, allow_pending_readback=truth is None)
        if truth is not None:
            truth = _verified_initial_truth(runtime, mission_id, truth)
        def grant_current() -> bool | None:
            try:
                return _require_ep_mission_capabilities(
                    runtime, mission_id, allow_pending_readback=True)
            except ValueError as error:
                return False if str(error) == "EP merge delegation is inactive for new Mission work" else None
            except (OSError, RuntimeError):
                return None
        return MissionController(runtime, mission_id, poll_seconds=poll_seconds,
                                 maximum_wait_seconds=maximum_wait_seconds,
                                 readback_only=not active_grant,
                                 grant_current=grant_current).run(initial_truth=truth)


def stop(data_root: str, mission_id: str) -> dict[str, object]:
    root = DataRootResolver(cli_data_root=data_root).resolve()
    accepted = request_stop(root / "forge.db", mission_id)
    return {"mission_id": mission_id, "stop_requested": accepted}
