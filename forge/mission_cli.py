"""Packaged operator adapter for canonical Mission governance and execution."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
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
from forge.repository_truth import RepositoryTruthEvidence, RepositoryTruthSnapshot
from forge.runtime.bootstrap import RuntimeBootstrap
from forge.runtime.data_root import DataRootResolver
from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.runtime.mission_controller import MissionController, request_stop, require_no_controller
from forge.runtime.service import RuntimeServiceLock
from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter
from forge.state import MissionStateStore


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
    if mission.repository_evidence_source is None:
        raise ValueError("Mission requires an approved repository source for fresh initial Truth")
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
                                  or not req.control_category))
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
    state = MissionStateStore._decode(row[0])
    return {"mission_id": state.mission_id, "status": state.status.value,
            "revision": state.revision, "action_ids": [item["id"] for item in state.actions],
            "planning_invocations": len(state.planning_history), "waiting_reason": state.waiting_reason,
            "completion": state.completion, "read_only": True}


def _github_default_head(repository: str) -> tuple[str, str]:
    """Read the current default-branch commit through the configured gh identity."""
    def read(path: str) -> dict[str, Any]:
        try:
            result = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
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
            or not isinstance(branch, str) or not branch):
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
        if truth is not None:
            truth = _verified_initial_truth(runtime, mission_id, truth)
        return MissionController(runtime, mission_id, poll_seconds=poll_seconds,
                                 maximum_wait_seconds=maximum_wait_seconds).run(initial_truth=truth)


def stop(data_root: str, mission_id: str) -> dict[str, object]:
    root = DataRootResolver(cli_data_root=data_root).resolve()
    accepted = request_stop(root / "forge.db", mission_id)
    return {"mission_id": mission_id, "stop_requested": accepted}
