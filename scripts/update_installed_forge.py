#!/usr/bin/env python3
"""Bounded product-owned update controller for one installed Forge runtime.

This is an external maintenance provisioner, not a Forge Runtime command.  It
stages one exact qualified wheel in an immutable slot, takes the canonical
runtime mutation lock, creates and verifies a SQLite backup, qualifies Forge's
own migration on an isolated copy, fences the legacy command resolver, invokes
the candidate's owning migrator, and atomically activates the candidate.

The durable operation is intentionally narrow: callers must supply every
installation, artifact, source, identity, interpreter, and resolver binding.
It never starts a service, Mission, planner, provider, reset, or EP submission.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterator, Mapping, Sequence
import uuid
import zipfile

try:
    import fcntl
except ImportError:  # pragma: no cover - supported installation target is POSIX.
    fcntl = None  # type: ignore[assignment]


CONTRACT_VERSION = "forge-installed-update/v1"
SUPPORTED_TRANSITIONS = {
    ("2.7.21", "2.7.22"): (37, 38),
    ("2.7.22", "2.7.23"): (38, 38),
    ("2.7.22", "2.7.24"): (38, 38),
    ("2.7.23", "2.7.24"): (38, 38),
    ("2.7.24", "2.7.25"): (38, 39),
    ("2.7.25", "2.7.26"): (39, 39),
    ("2.7.26", "2.7.27"): (39, 39),
}
SAME_SCHEMA_39_TRANSITIONS = frozenset({
    ("2.7.25", "2.7.26"), ("2.7.26", "2.7.27"),
})
NORMAL_RELEASE_TRANSITIONS = frozenset({
    ("2.7.22", "2.7.23"),
    ("2.7.22", "2.7.24"),
    ("2.7.23", "2.7.24"),
    ("2.7.24", "2.7.25"),
    ("2.7.25", "2.7.26"),
    ("2.7.26", "2.7.27"),
})
PHASE_ORDER = {
    phase: index for index, phase in enumerate((
        "PREPARED", "STAGED", "ADOPTED", "BACKED_UP", "MIGRATION_QUALIFIED",
        "FENCED", "MIGRATED", "ACTIVATING", "ACTIVATED", "COMPLETE",
    ))
}
NEW_SCHEMA_38_TABLES = frozenset({
    "operational_reset_state",
    "operational_reset_operations",
    "operational_reset_audit",
    "operational_reset_tombstones",
    "operational_reset_artifact_steps",
})
VOLATILE_METADATA_KEYS = frozenset({
    "schema_version", "migration_version", "last_migration", "forge_version",
    "database_version", "last_access_at", "integrity_status",
})
SAFE_MISSION_STATES = frozenset({
    "BLOCKED", "FAILED", "COMPLETED", "ARCHIVED", "INTEGRATION_BLOCKED", "INTEGRATION_COMPLETE",
})
SAFE_SUBMISSION_STATES = frozenset({"RECONCILED", "BLOCKED", "FAILED", "SUPERSEDED"})
TERMINAL_PERMIT_STATES = frozenset({"INVALIDATED", "INVALIDATED_BY_OPERATIONAL_RESET"})


class InstalledForgeUpdateError(RuntimeError):
    """The selected installation cannot be updated without weakening a gate."""


def transition_schemas(request: "UpdateRequest") -> tuple[int, int]:
    try:
        return SUPPORTED_TRANSITIONS[(request.existing_version, request.version)]
    except KeyError as error:
        raise InstalledForgeUpdateError(
            "this bounded controller does not support the selected Forge version transition"
        ) from error


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def _digest_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _assert_no_symlink_components(path: Path) -> None:
    if not path.is_absolute():
        raise InstalledForgeUpdateError(f"path must be absolute: {path}")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        if stat.S_ISLNK(mode):
            raise InstalledForgeUpdateError(f"path contains a symbolic-link component: {current}")


def _read_regular_bytes(path: Path) -> bytes:
    _assert_no_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise InstalledForgeUpdateError(f"required regular file is unavailable: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise InstalledForgeUpdateError(f"required regular file is unavailable: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def file_digest(path: Path) -> str:
    _assert_no_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise InstalledForgeUpdateError(f"required regular file is unavailable: {path}") from error
    digest = sha256()
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise InstalledForgeUpdateError(f"required regular file is unavailable: {path}")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    finally:
        os.close(descriptor)
    return "sha256:" + digest.hexdigest()


def _safe_directory(path: Path, *, create: bool = False) -> Path:
    if not path.is_absolute():
        raise InstalledForgeUpdateError(f"path must be absolute: {path}")
    _assert_no_symlink_components(path)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    _assert_no_symlink_components(path)
    if not path.is_dir():
        raise InstalledForgeUpdateError(f"directory is unavailable or unsafe: {path}")
    return path


def _atomic_json(path: Path, value: object) -> None:
    _safe_directory(path.parent, create=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(name)
    os.chmod(temporary, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_json_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_regular_file(path: Path, payload: bytes, *, mode: int) -> None:
    """Replace one managed regular file without exposing partial bytes."""
    _safe_directory(path.parent, create=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(_read_regular_bytes(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstalledForgeUpdateError(f"durable JSON evidence is unreadable: {path}") from error
    if not isinstance(value, dict):
        raise InstalledForgeUpdateError(f"durable JSON evidence is not an object: {path}")
    return value


def _replace_symlink(path: Path, target: str) -> None:
    _safe_directory(path.parent, create=True)
    temporary = path.with_name(f".{path.name}.link-{secrets.token_hex(16)}")
    temporary.symlink_to(target)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def _resolved_link(path: Path) -> Path:
    if not path.is_symlink():
        raise InstalledForgeUpdateError(f"managed resolver is not a symlink: {path}")
    return path.resolve(strict=True)


def _environment() -> dict[str, str]:
    environment = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if os.environ.get("HOME"):
        environment["HOME"] = os.environ["HOME"]
    return environment


def _run(arguments: Sequence[str], *, cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            tuple(arguments), cwd=cwd, env=_environment(), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=True,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        stdout = getattr(error, "stdout", "") or ""
        stderr = getattr(error, "stderr", "") or ""
        diagnostic = (stdout + "\n" + stderr).strip()[-2000:]
        raise InstalledForgeUpdateError(
            f"bounded subprocess failed: {arguments[0]}: {diagnostic or type(error).__name__}"
        ) from error


def installed_identity(interpreter: Path, *, cwd: Path) -> dict[str, Any]:
    program = """
import importlib.metadata, json, pathlib, sys
import forge
from forge._version import canonical_version
print(json.dumps({
    "version": canonical_version(),
    "distribution_version": importlib.metadata.version("forge-autonomy"),
    "module": str(pathlib.Path(forge.__file__).resolve()),
    "sys_executable": sys.executable,
    "resolved_sys_executable": str(pathlib.Path(sys.executable).resolve()),
    "prefix": str(pathlib.Path(sys.prefix).resolve()),
}, sort_keys=True))
"""
    result = _run((str(interpreter), "-B", "-I", "-c", program), cwd=cwd)
    try:
        identity = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InstalledForgeUpdateError("installed identity readback is malformed") from error
    if not isinstance(identity, dict):
        raise InstalledForgeUpdateError("installed identity readback is malformed")
    return identity


@dataclass(frozen=True)
class UpdateRequest:
    operation_id: str
    version: str
    product_source: str
    wheel: str
    wheel_sha256: str
    qualification_receipt: str
    qualification_receipt_sha256: str
    controller_source: str
    controller_sha256: str
    data_root: str
    runtime_root: str
    runtime_id: str
    installation_id: str
    peer_configuration_digest: str
    resolver: str
    resolver_sha256: str
    existing_interpreter: str
    existing_version: str
    base_python: str

    def validate(self) -> None:
        identifiers = (self.operation_id, self.runtime_id, self.installation_id)
        if any(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is None
            or value in {".", ".."}
            for value in identifiers
        ):
            raise InstalledForgeUpdateError("operation and installation identities must be filesystem-safe")
        transition_schemas(self)
        for label, digest in (
            ("wheel", self.wheel_sha256), ("qualification receipt", self.qualification_receipt_sha256),
            ("controller", self.controller_sha256), ("resolver", self.resolver_sha256),
            ("peer configuration", self.peer_configuration_digest),
        ):
            if not digest.startswith("sha256:") or len(digest) != 71:
                raise InstalledForgeUpdateError(f"{label} digest is invalid")
        if len(self.product_source) != 40 or len(self.controller_source) != 40:
            raise InstalledForgeUpdateError("source revisions must be exact 40-character revisions")
        paths = (
            self.wheel, self.qualification_receipt, self.data_root, self.runtime_root,
            self.resolver, self.existing_interpreter, self.base_python,
        )
        if any(not Path(value).is_absolute() for value in paths):
            raise InstalledForgeUpdateError("all installation paths must be absolute")

    @property
    def digest(self) -> str:
        return _digest_bytes(_json_bytes(asdict(self)))


def _validated_wheel(request: UpdateRequest) -> tuple[bytes, dict[str, str]]:
    wheel = Path(request.wheel)
    expected_name = f"forge_autonomy-{request.version}-py3-none-any.whl"
    if wheel.name != expected_name:
        raise InstalledForgeUpdateError("wheel filename does not match the selected product and version")
    wheel_bytes = _read_regular_bytes(wheel)
    if _digest_bytes(wheel_bytes) != request.wheel_sha256:
        raise InstalledForgeUpdateError("wheel digest does not match the selected qualified artifact")
    dist_info = f"forge_autonomy-{request.version}.dist-info"
    try:
        with zipfile.ZipFile(BytesIO(wheel_bytes)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise InstalledForgeUpdateError("wheel contains duplicate member paths")
            for info in infos:
                parts = Path(info.filename).parts
                mode = info.external_attr >> 16
                if (
                    info.filename.startswith("/") or "\\" in info.filename or ".." in parts
                    or not parts or parts[0] not in {"forge", dist_info}
                    or stat.S_ISLNK(mode)
                ):
                    raise InstalledForgeUpdateError("wheel contains an unsafe or unexpected member path")
            metadata_name = f"{dist_info}/METADATA"
            wheel_metadata_name = f"{dist_info}/WHEEL"
            record_name = f"{dist_info}/RECORD"
            if any(name not in names for name in (metadata_name, wheel_metadata_name, record_name)):
                raise InstalledForgeUpdateError("wheel metadata is missing or ambiguous")
            metadata = BytesParser().parsebytes(archive.read(metadata_name))
            wheel_metadata = BytesParser().parsebytes(archive.read(wheel_metadata_name))
            if (
                metadata.get("Name") != "forge-autonomy"
                or metadata.get("Version") != request.version
                or wheel_metadata.get("Root-Is-Purelib") != "true"
                or "py3-none-any" not in wheel_metadata.get_all("Tag", [])
            ):
                raise InstalledForgeUpdateError("wheel package metadata does not match the supported Forge artifact")
            rows = list(csv.reader(StringIO(archive.read(record_name).decode("utf-8"))))
            if any(len(row) != 3 for row in rows):
                raise InstalledForgeUpdateError("wheel RECORD is malformed")
            records = {row[0]: (row[1], row[2]) for row in rows}
            files = [info for info in infos if not info.is_dir()]
            if len(records) != len(rows) or set(records) != {info.filename for info in files}:
                raise InstalledForgeUpdateError("wheel RECORD does not exactly enumerate the artifact")
            manifest: dict[str, str] = {}
            for info in files:
                payload = archive.read(info.filename)
                manifest[info.filename] = _digest_bytes(payload)
                recorded_hash, recorded_size = records[info.filename]
                if info.filename == record_name:
                    if recorded_hash or recorded_size:
                        raise InstalledForgeUpdateError("wheel RECORD self-entry is not canonical")
                    continue
                encoded = base64.urlsafe_b64encode(sha256(payload).digest()).rstrip(b"=").decode("ascii")
                if recorded_hash != f"sha256={encoded}" or recorded_size != str(len(payload)):
                    raise InstalledForgeUpdateError("wheel RECORD does not bind an artifact member")
    except (UnicodeDecodeError, zipfile.BadZipFile) as error:
        raise InstalledForgeUpdateError("wheel is not a valid canonical ZIP artifact") from error
    return wheel_bytes, manifest


def _validate_criterion_qualification(report: object, request: UpdateRequest) -> None:
    """Require the exact installed composition evidence added by release 2.7.25."""
    expected = {
        "partial": ("COMPLETED", 2), "single": ("COMPLETED", 1),
        "misleading": ("COMPLETED", 2), "invalid": ("BLOCKED", 1),
        "missing": ("BLOCKED", 1), "no-progress": ("BLOCKED", 1),
        "limit": ("BLOCKED", 1), "regression": ("BLOCKED", 2),
    }
    row_keys = {"scenario", "status", "waiting_reason", "criteria", "actions", "assessments",
                "planner_invocations", "submissions", "original_observations_preserved",
                "same_mission_and_approval", "separate_process_reopen"}
    if (
        not isinstance(report, Mapping)
        or set(report) != {"qualification", "artifact", "scenarios", "limitations"}
        or report.get("qualification") != "INSTALLED_COMPOSITION_WITH_EXTERNAL_FIXTURES"
        or report.get("artifact") != {
            "version": request.version,
            "wheel_sha256": request.wheel_sha256.removeprefix("sha256:"),
        }
        or not isinstance(report.get("scenarios"), list)
        or len(report["scenarios"]) != len(expected)
        or not isinstance(report.get("limitations"), list)
        or not report["limitations"]
        or any(not isinstance(item, str) or not item for item in report["limitations"])
    ):
        raise InstalledForgeUpdateError("installed criterion qualification is noncanonical")
    seen = set()
    for row in report["scenarios"]:
        if (not isinstance(row, Mapping) or set(row) != row_keys
                or not isinstance(row.get("scenario"), str)):
            raise InstalledForgeUpdateError("installed criterion scenario is noncanonical")
        name = row["scenario"]
        if name not in expected or name in seen:
            raise InstalledForgeUpdateError("installed criterion scenarios are missing or duplicated")
        seen.add(name)
        status, count = expected[name]
        expected_proven = ({"SYNTHETIC-K1", "SYNTHETIC-K2"} if status == "COMPLETED" else
                           {"SYNTHETIC-K1"} if name == "limit" else
                           {"SYNTHETIC-K2"} if name == "regression" else set())
        expected_reason = (None if status == "COMPLETED" else
                           "MISSION_ACTION_LIMIT_REACHED" if name in {"limit", "regression"} else
                           "MISSION_NO_PROGRESS_LIMIT_REACHED")
        criteria = row.get("criteria")
        if (
            row.get("status") != status
            or any(type(row.get(key)) is not int or row[key] != count
                   for key in ("actions", "assessments", "planner_invocations", "submissions"))
            or any(row.get(key) is not True for key in (
                "original_observations_preserved", "same_mission_and_approval", "separate_process_reopen",
            ))
            or not isinstance(criteria, list) or len(criteria) != 2
            or any(not isinstance(item, Mapping) or set(item) != {"criterion", "status", "reason"}
                   for item in criteria)
            or any(not isinstance(item.get("criterion"), str)
                   or not isinstance(item.get("status"), str) for item in criteria)
            or {item.get("criterion") for item in criteria} != {"SYNTHETIC-K1", "SYNTHETIC-K2"}
            or any(item.get("status") not in {"PROVEN", "UNSATISFIED"} for item in criteria)
            or {item["criterion"] for item in criteria if item["status"] == "PROVEN"} != expected_proven
            or row.get("waiting_reason") != expected_reason
            or any(item.get("reason") != (
                "ALL_APPROVED_REQUIREMENTS_PROVEN" if item["status"] == "PROVEN"
                else "REQUIRED_OBSERVATIONS_UNPROVEN"
            ) for item in criteria)
        ):
            raise InstalledForgeUpdateError("installed criterion outcome does not qualify the release")


def _normal_release_evidence(
    request: UpdateRequest, receipt: Mapping[str, Any], manifest: Mapping[str, str],
    receipt_path: Path,
) -> dict[str, Any]:
    """Validate current normal-release transitions without weakening 2.7.22 recovery."""
    expected_name = f"forge_autonomy-{request.version}-py3-none-any.whl"
    sdist_name = f"forge_autonomy-{request.version}.tar.gz"
    qualification = receipt.get("qualification")
    artifacts = receipt.get("artifacts")
    publication = receipt.get("publication_receipt")
    cleanup = receipt.get("cleanup")
    expected_top = {
        "product", "component", "version", "source_revision", "operation_id", "policy_revision",
        "artifacts", "state", "qualification", "publication_receipt", "cleanup",
    }
    sdist_digest = artifacts.get("sdist") if isinstance(artifacts, Mapping) else None
    exact_artifacts = {"wheel": request.wheel_sha256, "sdist": sdist_digest}
    exact_qualified = {
        f"dist/{expected_name}": request.wheel_sha256,
        f"dist/{sdist_name}": sdist_digest,
    }
    exact_observed = {expected_name: request.wheel_sha256, sdist_name: sdist_digest}
    composition_keys = {"criterion_completion"} if request.version in {"2.7.25", "2.7.26", "2.7.27"} else set()
    if (
        (request.existing_version, request.version) not in NORMAL_RELEASE_TRANSITIONS
        or set(receipt) != expected_top
        or receipt.get("state") != "RELEASE_COMPLETE"
        or receipt.get("product") != "forge"
        or receipt.get("component") != "forge-autonomy"
        or receipt.get("version") != request.version
        or receipt.get("source_revision") != request.product_source
        or receipt.get("operation_id") != f"forge-release-{request.version}-{request.product_source}"
        or receipt.get("policy_revision") != "forge-bootstrap-release-cadence-v2"
        or not isinstance(artifacts, Mapping)
        or set(artifacts) != {"wheel", "sdist"}
        or dict(artifacts) != exact_artifacts
        or not isinstance(sdist_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", sdist_digest) is None
        or not isinstance(qualification, Mapping)
        or set(qualification) != {"artifact_digests", "exact_main_sha", "qualification"} | composition_keys
        or qualification.get("exact_main_sha") != request.product_source
        or qualification.get("qualification") != "forge-production-distribution"
        or qualification.get("artifact_digests") != exact_qualified
        or not isinstance(publication, Mapping)
        or set(publication) != {"observed_artifact_digests", "readback", "registry"} | composition_keys
        or publication.get("observed_artifact_digests") != exact_observed
        or publication.get("readback") != "PASS"
        or publication.get("registry") != "pypi"
        or not isinstance(cleanup, Mapping)
        or set(cleanup) != {"github_release", "result", "temporary_paths"}
        or cleanup.get("result") != "COMPLETE"
        or cleanup.get("temporary_paths") != [
            "published-readback", "published-input/dist", "pending-readback",
        ]
        or cleanup.get("github_release") != {"draft": False}
    ):
        raise InstalledForgeUpdateError(
            "normal release-complete publication, policy, or cleanup lineage is noncanonical"
        )
    if composition_keys:
        _validate_criterion_qualification(qualification["criterion_completion"], request)
        _validate_criterion_qualification(publication["criterion_completion"], request)
    return {
        "wheel": str(Path(request.wheel)),
        "wheel_sha256": request.wheel_sha256,
        "wheel_manifest_digest": _digest_bytes(_json_bytes(dict(manifest))),
        "receipt": str(receipt_path),
        "receipt_sha256": request.qualification_receipt_sha256,
        "release_operation_id": receipt.get("operation_id"),
        "release_route": "NORMAL",
    }


def _qualified_artifact(request: UpdateRequest) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    wheel_bytes, manifest = _validated_wheel(request)
    expected_name = f"forge_autonomy-{request.version}-py3-none-any.whl"
    sdist_name = f"forge_autonomy-{request.version}.tar.gz"
    receipt_path = Path(request.qualification_receipt)
    receipt_bytes = _read_regular_bytes(receipt_path)
    if _digest_bytes(receipt_bytes) != request.qualification_receipt_sha256:
        raise InstalledForgeUpdateError("qualification receipt digest changed")
    try:
        receipt = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstalledForgeUpdateError("qualification receipt is malformed") from error
    if not isinstance(receipt, dict):
        raise InstalledForgeUpdateError("qualification receipt is malformed")
    if (request.existing_version, request.version) in NORMAL_RELEASE_TRANSITIONS:
        return (
            _normal_release_evidence(request, receipt, manifest, receipt_path),
            wheel_bytes,
            manifest,
        )
    qualification = receipt.get("qualification")
    artifacts = receipt.get("artifacts")
    publication = receipt.get("publication_receipt")
    cleanup = receipt.get("cleanup")
    release = publication.get("github_release") if isinstance(publication, dict) else None
    cleanup_release = cleanup.get("github_release") if isinstance(cleanup, dict) else None
    expected_top = {
        "product", "component", "version", "source_revision", "operation_id", "policy_revision",
        "artifacts", "state", "qualification", "publication_receipt", "cleanup",
    }
    expected_publication = {
        "github_release", "observed_artifact_digests", "original_release_run_conclusion",
        "original_release_run_id", "product_source_revision", "readback", "reconciliation_contract",
        "reconciliation_run_id", "registry", "release_controller_source",
    }
    expected_cleanup = {
        "github_release", "operation_local_cleanup", "original_release_run_id",
        "reconciliation_contract", "reconciliation_run_id", "release_controller_source", "result",
    }
    expected_public_release = {"api_url", "database_id", "node_id", "tag", "target_commitish"}
    expected_cleanup_release = {
        "api_url", "database_id", "draft", "node_id", "tag", "tag_commit", "target_commitish",
    }
    sdist_digest = artifacts.get("sdist") if isinstance(artifacts, dict) else None
    release_controller = publication.get("release_controller_source") if isinstance(publication, dict) else None
    original_run = publication.get("original_release_run_id") if isinstance(publication, dict) else None
    reconciliation_run = publication.get("reconciliation_run_id") if isinstance(publication, dict) else None
    database_id = release.get("database_id") if isinstance(release, dict) else None
    expected_api = f"https://api.github.com/repos/pcvantol/forge/releases/{database_id}"
    exact_artifacts = {"wheel": request.wheel_sha256, "sdist": sdist_digest}
    exact_qualified = {f"dist/{expected_name}": request.wheel_sha256, f"dist/{sdist_name}": sdist_digest}
    exact_observed = {expected_name: request.wheel_sha256, sdist_name: sdist_digest}
    if (
        set(receipt) != expected_top
        or receipt.get("state") != "RELEASE_COMPLETE"
        or receipt.get("product") != "forge" or receipt.get("component") != "forge-autonomy"
        or receipt.get("version") != request.version or receipt.get("source_revision") != request.product_source
        or receipt.get("operation_id") != f"forge-release-{request.version}-{request.product_source}"
        or receipt.get("policy_revision") != "forge-bootstrap-release-cadence-v2"
        or not isinstance(artifacts, dict) or set(artifacts) != {"wheel", "sdist"}
        or artifacts != exact_artifacts or not isinstance(sdist_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", sdist_digest) is None
        or not isinstance(qualification, dict) or set(qualification) != {
            "artifact_digests", "exact_main_sha", "qualification"
        }
        or qualification.get("exact_main_sha") != request.product_source
        or qualification.get("qualification") != "forge-production-distribution"
        or qualification.get("artifact_digests") != exact_qualified
        or not isinstance(publication, dict) or set(publication) != expected_publication
        or publication.get("product_source_revision") != request.product_source
        or publication.get("readback") != "PASS" or publication.get("registry") != "pypi"
        or publication.get("original_release_run_conclusion") != "failure"
        or publication.get("reconciliation_contract") != "forge-existing-release-reconciliation/v1"
        or publication.get("observed_artifact_digests") != exact_observed
        or not isinstance(original_run, str) or not original_run.isdigit()
        or not isinstance(reconciliation_run, str) or not reconciliation_run.isdigit()
        or not isinstance(release_controller, str) or re.fullmatch(r"[0-9a-f]{40}", release_controller) is None
        or not isinstance(release, dict) or set(release) != expected_public_release
        or release.get("api_url") != expected_api or not isinstance(database_id, int) or database_id <= 0
        or not isinstance(release.get("node_id"), str) or not release.get("node_id")
        or release.get("tag") != f"forge-v{request.version}"
        or release.get("target_commitish") != request.product_source
        or not isinstance(cleanup, dict) or set(cleanup) != expected_cleanup
        or cleanup.get("result") != "COMPLETE" or cleanup.get("operation_local_cleanup") != "COMPLETE"
        or cleanup.get("original_release_run_id") != original_run
        or cleanup.get("reconciliation_run_id") != reconciliation_run
        or cleanup.get("release_controller_source") != release_controller
        or cleanup.get("reconciliation_contract") != "forge-existing-release-reconciliation/v1"
        or not isinstance(cleanup_release, dict) or set(cleanup_release) != expected_cleanup_release
        or cleanup_release.get("api_url") != release.get("api_url")
        or cleanup_release.get("database_id") != database_id
        or cleanup_release.get("node_id") != release.get("node_id")
        or cleanup_release.get("draft") is not False
        or cleanup_release.get("tag") != release.get("tag")
        or cleanup_release.get("target_commitish") != request.product_source
        or cleanup_release.get("tag_commit") != request.product_source
    ):
        raise InstalledForgeUpdateError("release-complete publication, policy, or cleanup lineage is noncanonical")
    evidence = {
        "wheel": str(Path(request.wheel)), "wheel_sha256": request.wheel_sha256,
        "wheel_manifest_digest": _digest_bytes(_json_bytes(manifest)),
        "receipt": str(receipt_path), "receipt_sha256": request.qualification_receipt_sha256,
        "release_operation_id": receipt.get("operation_id"),
        "release_controller_source": release_controller,
        "original_release_run_id": original_run, "reconciliation_run_id": reconciliation_run,
    }
    return evidence, wheel_bytes, manifest


def validate_qualified_artifact(request: UpdateRequest) -> dict[str, Any]:
    evidence, _, _ = _qualified_artifact(request)
    return evidence


def _sqlite_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return value


def _table_digest(connection: sqlite3.Connection, table: str) -> tuple[int, str]:
    quoted = '"' + table.replace('"', '""') + '"'
    rows = [
        [_sqlite_value(value) for value in row]
        for row in connection.execute(f"SELECT * FROM {quoted}").fetchall()
    ]
    rows.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return len(rows), _digest_bytes(_json_bytes(rows))


def database_snapshot(path: Path, *, existing_connection: sqlite3.Connection | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise InstalledForgeUpdateError(f"runtime database is unavailable or unsafe: {path}")
    owns_connection = existing_connection is None
    try:
        connection = existing_connection or sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        if owns_connection:
            connection.execute("PRAGMA query_only=ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        tables = sorted(row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ))
        schema_objects = [dict(row) for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        )]
        table_metrics = {
            table: {"count": count, "digest": digest}
            for table in tables
            for count, digest in (_table_digest(connection, table),)
        }
        metadata = dict(connection.execute("SELECT key,value FROM runtime_metadata"))
        protected_metadata = {
            key: value for key, value in metadata.items() if key not in VOLATILE_METADATA_KEYS
        }
        peer_row = connection.execute(
            "SELECT binding_id,configuration_revision,configuration_digest,document "
            "FROM execution_host_peer_configuration WHERE singleton=1"
        ).fetchone() if "execution_host_peer_configuration" in tables else None
        peer = None if peer_row is None else {
            "binding_id": peer_row[0], "configuration_revision": peer_row[1],
            "configuration_digest": peer_row[2], "document_digest": _digest_bytes(str(peer_row[3]).encode()),
        }
        dispatcher = [dict(row) for row in connection.execute(
            "SELECT status,active_mission_id FROM dispatcher_state"
        )] if "dispatcher_state" in tables else []
        missions = [dict(row) for row in connection.execute(
            "SELECT mission_id,status FROM mission_state ORDER BY mission_id"
        )] if "mission_state" in tables else []
        submissions = [dict(row) for row in connection.execute(
            "SELECT submission_id,state FROM scheduler_submissions ORDER BY submission_id"
        )] if "scheduler_submissions" in tables else []
        permits = [dict(row) for row in connection.execute(
            "SELECT permit_id,state FROM planning_provider_generation_permits ORDER BY permit_id"
        )] if "planning_provider_generation_permits" in tables else []
        planning = [dict(row) for row in connection.execute(
            "SELECT current_queue,pending_engineering_actions,blocked_engineering_actions FROM planning_state"
        )] if "planning_state" in tables else []
        reset = [dict(row) for row in connection.execute(
            "SELECT dataset_generation,active_operation_id,state FROM operational_reset_state"
        )] if "operational_reset_state" in tables else []
    except sqlite3.Error as error:
        raise InstalledForgeUpdateError("runtime database readback failed") from error
    finally:
        if owns_connection and "connection" in locals():
            connection.close()
    snapshot = {
        "database": str(path), "integrity_check": integrity,
        "foreign_key_check": foreign_keys, "user_version": user_version,
        "schema_digest": _digest_bytes(_json_bytes(schema_objects)),
        "metadata": metadata, "protected_metadata_digest": _digest_bytes(_json_bytes(protected_metadata)),
        "tables": table_metrics, "peer": peer,
        "writer_state": {
            "dispatcher": dispatcher, "missions": missions, "submissions": submissions,
            "generation_permits": permits, "planning": planning, "operational_reset": reset,
        },
    }
    logical = {key: value for key, value in snapshot.items() if key != "database"}
    snapshot["content_digest"] = _digest_bytes(_json_bytes(logical))
    snapshot["snapshot_digest"] = _digest_bytes(_json_bytes(snapshot))
    return snapshot


def assert_selected_installation(request: UpdateRequest, snapshot: Mapping[str, Any]) -> None:
    metadata = snapshot.get("metadata")
    peer = snapshot.get("peer")
    if not isinstance(metadata, Mapping):
        raise InstalledForgeUpdateError("runtime metadata readback is missing")
    if metadata.get("runtime_id") != request.runtime_id:
        raise InstalledForgeUpdateError("selected data root belongs to a different runtime")
    if metadata.get("installation_id") != request.installation_id:
        raise InstalledForgeUpdateError("selected data root belongs to a different installation")
    schema_before, schema_after = transition_schemas(request)
    if snapshot.get("user_version") not in {schema_before, schema_after}:
        raise InstalledForgeUpdateError("selected runtime schema is outside the bounded update path")
    if not isinstance(peer, Mapping) or peer.get("configuration_digest") != request.peer_configuration_digest:
        raise InstalledForgeUpdateError("selected peer configuration changed")
    marker = Path(request.data_root) / "instance" / "runtime-instance.json"
    if marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8").strip() != request.runtime_id:
        raise InstalledForgeUpdateError("runtime instance marker does not bind the selected runtime")


def assert_quiescent(snapshot: Mapping[str, Any]) -> None:
    writer = snapshot.get("writer_state")
    if not isinstance(writer, Mapping):
        raise InstalledForgeUpdateError("writer-state readback is missing")
    dispatcher = writer.get("dispatcher")
    if not isinstance(dispatcher, list) or len(dispatcher) != 1 or any(
        row.get("status") != "IDLE" or row.get("active_mission_id") is not None
        for row in dispatcher if isinstance(row, Mapping)
    ):
        raise InstalledForgeUpdateError("Forge dispatcher is not durably idle")
    missions = writer.get("missions") or []
    if any(not isinstance(row, Mapping) or row.get("status") not in SAFE_MISSION_STATES for row in missions):
        raise InstalledForgeUpdateError("Forge has non-terminal or non-paused Mission state")
    submissions = writer.get("submissions") or []
    if any(not isinstance(row, Mapping) or row.get("state") not in SAFE_SUBMISSION_STATES for row in submissions):
        raise InstalledForgeUpdateError("Forge has a non-terminal scheduler submission")
    permits = writer.get("generation_permits") or []
    if any(isinstance(row, Mapping) and row.get("state") not in TERMINAL_PERMIT_STATES for row in permits):
        raise InstalledForgeUpdateError("Forge has an active provider-generation permit")
    for row in writer.get("planning") or []:
        if not isinstance(row, Mapping):
            raise InstalledForgeUpdateError("Forge planning state is malformed")
        for key in ("current_queue", "pending_engineering_actions", "blocked_engineering_actions"):
            try:
                value = json.loads(str(row.get(key)))
            except json.JSONDecodeError as error:
                raise InstalledForgeUpdateError("Forge planning queue is unreadable") from error
            if value:
                raise InstalledForgeUpdateError("Forge planning queue is not empty")
    reset = writer.get("operational_reset") or []
    if any(not isinstance(row, Mapping) or row.get("active_operation_id") is not None or row.get("state") != "IDLE"
           for row in reset):
        raise InstalledForgeUpdateError("Forge operational reset maintenance is active")


def _prove_terminal_host_authority(
    request: UpdateRequest, connection: sqlite3.Connection, mission: Mapping[str, Any],
) -> None:
    """Prove that an Actionful failed Mission has no remaining EP execution authority."""
    actions = mission.get("actions", [])
    if not isinstance(actions, list):
        raise InstalledForgeUpdateError("terminal Mission Actions are unreadable")
    if not actions:
        if mission.get("execution_correlation") is not None or mission.get("intents"):
            raise InstalledForgeUpdateError("failed Mission has possible Host effect")
        return
    correlation = mission.get("execution_correlation")
    evidence = mission.get("execution_evidence")
    if (mission.get("status") != "FAILED" or mission.get("waiting_reason") != "host_evidence_failed"
            or not isinstance(correlation, Mapping) or not isinstance(correlation.get("request"), Mapping)
            or not isinstance(evidence, Mapping) or evidence.get("outcome") != "failed"):
        raise InstalledForgeUpdateError("Actionful Mission lacks the bounded terminal Host failure")
    correlation_id = correlation["request"].get("correlation_id")
    if not isinstance(correlation_id, str):
        raise InstalledForgeUpdateError("failed Mission lacks its Host correlation")
    rows = connection.execute(
        "SELECT document FROM execution_host_bindings WHERE correlation_id=?", (correlation_id,),
    ).fetchall()
    if len(rows) != 1:
        raise InstalledForgeUpdateError("failed Mission lacks exactly one persisted Host binding")
    binding = json.loads(rows[0][0])
    mission_id = mission["mission_id"]
    if (binding.get("mission_id") != mission_id or binding.get("correlation_id") != correlation_id
            or binding.get("action_id") not in {action.get("id") for action in actions if isinstance(action, Mapping)}
            or not isinstance(binding.get("submission_id"), str)
            or not isinstance(binding.get("submission_receipt"), Mapping)):
        raise InstalledForgeUpdateError("failed Mission Host binding is incomplete")
    all_bindings = connection.execute(
        "SELECT document FROM execution_host_bindings WHERE json_extract(document,'$.mission_id')=?", (mission_id,),
    ).fetchall()
    if len(all_bindings) != 1 or any(action.get("status") == "IN_PROGRESS" for action in actions):
        raise InstalledForgeUpdateError("failed Mission has another possible Host execution")
    references = re.findall(r"ep-merge-delegation:([0-9a-f]{32})", json.dumps(mission, sort_keys=True))
    if len(set(references)) != 1:
        raise InstalledForgeUpdateError("failed Mission lacks one exact delegation binding")
    # Resolve the installed peer credential inside the selected isolated
    # interpreter. The bearer token never crosses stdout, argv, or an audit
    # record. HTTP redirects are rejected and responses are bounded.
    program = """
import importlib.metadata,json,pathlib,sys
from urllib.parse import quote
from urllib.request import Request,build_opener,HTTPRedirectHandler
import forge
from forge.execution_host_configuration import EngineeringPlatformExecutionHostFactory
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs): return None
if importlib.metadata.version('forge-autonomy') != sys.argv[4] or not pathlib.Path(forge.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()):
 raise SystemExit('installed Forge package provenance changed')
host=EngineeringPlatformExecutionHostFactory().from_data_root(pathlib.Path(sys.argv[1]))
project=host.config.project_id
opener=build_opener(NoRedirect())
def get(suffix):
 req=Request(host.config.base_url.rstrip('/')+'/v1/projects/'+quote(project,safe='')+suffix,headers={'Authorization':'Bearer '+host.config.bearer_token,'EP-Producer-Readback-Contract':'1.3'})
 with opener.open(req,timeout=10) as response:
  raw=response.read(1048577)
  if len(raw)>1048576: raise ValueError('EP proof exceeds bound')
  return json.loads(raw)
print(json.dumps({'submission':get('/submissions/'+quote(sys.argv[2],safe='')),'delegation':get('/merge-delegations/'+quote(sys.argv[3],safe='')),'project':project,'repository':host.config.repository_id},sort_keys=True))
"""
    response = _run((request.existing_interpreter, "-B", "-I", "-c", program,
                     request.data_root, binding["submission_id"], references[0], request.existing_version),
                    cwd=Path(request.runtime_root), timeout=35)
    try:
        proof = json.loads(response.stdout)
        submission, grant = proof["submission"], proof["delegation"]
        record, linked, disposition = submission["submission"], submission["correlation"], submission["disposition"]
        receipt = binding["submission_receipt"]
        if (submission.get("contract_version") != "1.3"
                or proof["project"] != binding["project_id"] or proof["repository"] != binding["repository_id"]
                or record["id"] != binding["submission_id"] or record["project_id"] != binding["project_id"]
                or record["repository_id"] != binding["repository_id"]
                or record["accepted_request_digest"] != receipt["accepted_request_digest"]
                or linked["mission_id"] != mission_id or linked["engineering_action_id"] != binding["action_id"]
                or linked["correlation_id"] != correlation_id
                or submission["run"]["id"] != binding["host_run_id"]
                or submission["run"]["operator_resolution"] != "DISMISSED"
                or submission["run"]["terminal"] is not True
                or disposition["state"] != "DISMISSED" or disposition["terminal"] is not True
                or disposition["execution_eligible"] is not False
                or grant["status"] not in {"REVOKED", "EXPIRED"}
                or grant["mission_id"] != mission_id or grant["project_id"] != binding["project_id"]
                or grant["repository_id"] != binding["repository_id"]
                or grant["mission_revision"] != mission["repository_truth"]["revision"]
                or grant["status"] == "REVOKED" and not grant.get("revoked_at")):
            raise InstalledForgeUpdateError("EP does not prove terminal submission and revoked delegation")
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise InstalledForgeUpdateError("EP terminal authority proof is incomplete") from error


def reconcile_terminal_dispatcher_for_update(
    request: UpdateRequest, snapshot: Mapping[str, Any], database_path: Path,
) -> dict[str, Any]:
    """Release only a stale dispatcher projection bound to a terminal Mission.

    The caller owns the controller, runtime mutation, bootstrap and update
    locks and has excluded a live Forge process. Mission and Action history is
    never rewritten. The canonical database writer records the transition.
    """
    writer = snapshot.get("writer_state")
    if not isinstance(writer, Mapping):
        raise InstalledForgeUpdateError("writer-state readback is missing")
    dispatcher = writer.get("dispatcher")
    if not isinstance(dispatcher, list) or len(dispatcher) != 1 or not isinstance(dispatcher[0], Mapping):
        raise InstalledForgeUpdateError("Forge dispatcher state is malformed")
    current = dispatcher[0]
    if current.get("status") == "IDLE":
        assert_quiescent(snapshot)
        return dict(snapshot)
    mission_id = current.get("active_mission_id")
    missions = writer.get("missions")
    if (current.get("status") != "ACTIVE" or not isinstance(mission_id, str)
            or not mission_id or not isinstance(missions, list)
            or sum(row.get("mission_id") == mission_id and row.get("status") in {"FAILED", "BLOCKED"}
                   for row in missions if isinstance(row, Mapping)) != 1):
        raise InstalledForgeUpdateError("active dispatcher is not bound to one terminal failed Mission")
    candidate_writer = dict(writer)
    candidate_writer["dispatcher"] = [{"status": "IDLE", "active_mission_id": None}]
    assert_quiescent({**snapshot, "writer_state": candidate_writer})

    # The updater already holds the bootstrap lock. RuntimeBootstrap.open()
    # would try to acquire it a second time and deadlock/fail. This narrowly
    # scoped product maintenance writer uses the existing selected database
    # under all four updater locks; it never opens a second RuntimeBootstrap.
    identity = installed_identity(Path(request.existing_interpreter), cwd=Path(request.runtime_root))
    if (identity.get("version") != request.existing_version
            or identity.get("distribution_version") != request.existing_version
            or Path(str(identity.get("sys_executable"))).resolve() != Path(request.existing_interpreter).resolve()
            or not Path(str(identity.get("module"))).is_relative_to(Path(str(identity.get("prefix"))))):
        raise InstalledForgeUpdateError("selected installed Forge package provenance changed")
    try:
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=1000")
        connection.execute("BEGIN IMMEDIATE")
        bound = connection.execute(
            "SELECT status,active_mission_id,mission_sequence,document FROM dispatcher_state WHERE singleton=1"
        ).fetchone()
        mission = connection.execute(
            "SELECT status,document FROM mission_state WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if (bound is None or bound["status"] != "ACTIVE" or bound["active_mission_id"] != mission_id
                or mission is None or mission["status"] not in {"FAILED", "BLOCKED"}):
            raise InstalledForgeUpdateError("terminal dispatcher binding changed before reconciliation")
        document = json.loads(mission["document"])
        if document.get("mission_id") != mission_id or document.get("status") != mission["status"]:
            raise InstalledForgeUpdateError("terminal Mission document conflicts with its state")
        _prove_terminal_host_authority(request, connection, document)
        sequence = json.loads(bound["mission_sequence"])
        if not isinstance(sequence, list) or mission_id not in sequence:
            raise InstalledForgeUpdateError("dispatcher sequence does not include its bound Mission")
        new_document = {"status": "IDLE", "active_mission_id": None, "mission_sequence": sequence}
        changed = connection.execute(
            "UPDATE dispatcher_state SET status='IDLE',active_mission_id=NULL,document=? "
            "WHERE singleton=1 AND status='ACTIVE' AND active_mission_id=? AND document=?",
            (json.dumps(new_document, sort_keys=True, separators=(",", ":")), mission_id, bound["document"]),
        ).rowcount
        if changed != 1:
            raise InstalledForgeUpdateError("terminal dispatcher changed during reconciliation")
        connection.execute(
            "INSERT INTO forge_operational_logs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("forge-operational-log-" + str(uuid.uuid4()), "forge_mission_runtime", "INFO",
             "terminal_dispatcher_update_reconciled", mission_id, None, None, None, None, _now(),
             json.dumps({"event_contract_version": "1.0", "operation": "terminal_dispatcher_update_reconciliation",
                         "previous_state": "ACTIVE", "new_state": "IDLE", "result_state": mission["status"]},
                        sort_keys=True, separators=(",", ":"))),
        )
        connection.commit()
    except (sqlite3.Error, ValueError, TypeError) as error:
        raise InstalledForgeUpdateError("terminal dispatcher reconciliation could not prove or commit state") from error
    finally:
        if "connection" in locals():
            connection.close()
    reconciled = database_snapshot(database_path)
    assert_quiescent(reconciled)
    return reconciled


def assert_completed_schema(
    snapshot: Mapping[str, Any], installed_readback: Mapping[str, Any], request: UpdateRequest,
) -> None:
    tables = snapshot.get("tables")
    expected_digest = installed_readback.get("database_schema_digest")
    _schema_before, schema_after = transition_schemas(request)
    if (
        snapshot.get("user_version") != schema_after
        or not isinstance(tables, Mapping)
        or not NEW_SCHEMA_38_TABLES.issubset(tables)
        or not isinstance(expected_digest, str)
        or snapshot.get("schema_digest") != expected_digest
    ):
        raise InstalledForgeUpdateError("completed runtime schema changed from the activated schema")


def verify_preservation(before: Mapping[str, Any], after: Mapping[str, Any], request: UpdateRequest) -> dict[str, Any]:
    schema_before, schema_after = transition_schemas(request)
    if before.get("user_version") != schema_before:
        raise InstalledForgeUpdateError("source runtime schema is outside the selected update path")
    if after.get("integrity_check") != "ok" or after.get("foreign_key_check") != []:
        raise InstalledForgeUpdateError("migrated runtime failed SQLite integrity validation")
    if after.get("user_version") != schema_after:
        raise InstalledForgeUpdateError("Forge owning migration did not reach the selected target schema")
    before_metadata, after_metadata = before.get("metadata"), after.get("metadata")
    if not isinstance(before_metadata, Mapping) or not isinstance(after_metadata, Mapping):
        raise InstalledForgeUpdateError("migration metadata readback is incomplete")
    for key, expected in (
        ("runtime_id", request.runtime_id), ("installation_id", request.installation_id),
    ):
        if before_metadata.get(key) != expected or after_metadata.get(key) != expected:
            raise InstalledForgeUpdateError(f"migration changed selected {key}")
    if after.get("protected_metadata_digest") != before.get("protected_metadata_digest"):
        raise InstalledForgeUpdateError("migration changed protected runtime metadata")
    if after.get("peer") != before.get("peer"):
        raise InstalledForgeUpdateError("migration changed the configured Forge-to-EP peer binding")
    before_tables, after_tables = before.get("tables"), after.get("tables")
    if not isinstance(before_tables, Mapping) or not isinstance(after_tables, Mapping):
        raise InstalledForgeUpdateError("migration table readback is incomplete")
    for table, metric in before_tables.items():
        if table == "runtime_metadata":
            continue
        if after_tables.get(table) != metric:
            raise InstalledForgeUpdateError(f"migration changed historical table contents: {table}")
    new_tables = set(after_tables) - set(before_tables)
    expected_new_tables = set(NEW_SCHEMA_38_TABLES) if schema_before == 37 else set()
    if new_tables != expected_new_tables:
        raise InstalledForgeUpdateError("migration produced an unexpected target-schema table set")
    reset = after.get("writer_state", {}).get("operational_reset", [])
    if schema_before == 37:
        expected_counts = {table: 0 for table in NEW_SCHEMA_38_TABLES}
        expected_counts["operational_reset_state"] = 1
        if any(after_tables[table]["count"] != count for table, count in expected_counts.items()):
            raise InstalledForgeUpdateError("migration initialized unexpected operational-reset data")
        if reset != [{"dataset_generation": 0, "active_operation_id": None, "state": "IDLE"}]:
            raise InstalledForgeUpdateError("schema-38 reset state is not an idle, fresh control record")
    elif reset != before.get("writer_state", {}).get("operational_reset", []):
        raise InstalledForgeUpdateError("update changed preserved operational-reset state")
    return {
        "status": "PASS", "from_schema": schema_before, "to_schema": schema_after,
        "preserved_table_count": len(before_tables) - 1,
        "added_tables": sorted(new_tables),
        "protected_metadata_digest": after.get("protected_metadata_digest"),
        "peer_configuration_digest": request.peer_configuration_digest,
    }


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    if fcntl is None:
        raise InstalledForgeUpdateError("POSIX installation locking is unavailable")
    _safe_directory(path.parent, create=True)
    if path.is_symlink():
        raise InstalledForgeUpdateError(f"installation lock path is unsafe: {path}")
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise InstalledForgeUpdateError(f"concurrent maintenance owns lock: {path}") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _copy_sqlite_backup(source: Path, destination: Path) -> dict[str, Any]:
    _safe_directory(destination.parent, create=True)
    if destination.exists() or destination.is_symlink():
        raise InstalledForgeUpdateError("installation backup already exists without matching durable evidence")
    descriptor, name = tempfile.mkstemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        source_connection = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        destination_connection = sqlite3.connect(temporary)
        source_connection.backup(destination_connection)
        destination_connection.commit()
        # The online backup inherits WAL mode. Before the temporary database is
        # renamed, make it self-contained: WAL sidecars retain the temporary
        # basename and a read-only integrity check cannot open the renamed DB.
        if destination_connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0] != "delete":
            raise InstalledForgeUpdateError("SQLite backup journal finalization failed")
        if destination_connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise InstalledForgeUpdateError("SQLite backup integrity check failed")
        if destination_connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise InstalledForgeUpdateError("SQLite backup foreign-key check failed")
        destination_connection.close()
        source_connection.close()
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except sqlite3.Error as error:
        raise InstalledForgeUpdateError("consistent SQLite backup failed") from error
    finally:
        for connection_name in ("destination_connection", "source_connection"):
            connection = locals().get(connection_name)
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.Error:
                    pass
        if temporary.exists():
            temporary.unlink()
    verification = database_snapshot(destination)
    return {
        "path": str(destination), "sha256": file_digest(destination),
        "size": destination.stat().st_size, "integrity_check": verification["integrity_check"],
        "foreign_key_check": verification["foreign_key_check"],
        "snapshot_digest": verification["snapshot_digest"],
    }


def _candidate_migrate(
    executable: Path, data_root: Path, *, cwd: Path, target_schema: int,
) -> dict[str, Any]:
    result = _run((str(executable), "--data-root", str(data_root), "server", "init"), cwd=cwd)
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InstalledForgeUpdateError("candidate migration readback is malformed") from error
    if output.get("storage_schema") != str(target_schema) or output.get("initialized") is not True:
        raise InstalledForgeUpdateError("candidate migration did not return the target-schema installed readback")
    return output


def _candidate_site_packages(slot: Path) -> Path:
    candidates = [path for path in (slot / "lib").glob("python*/site-packages") if path.is_dir()]
    if len(candidates) != 1:
        raise InstalledForgeUpdateError("candidate virtual environment has ambiguous site-packages")
    return _safe_directory(candidates[0])


def _entrypoint_bytes(slot: Path) -> bytes:
    return (
        "#!/bin/sh\n"
        f"exec {shlex.quote(str(slot / 'bin' / 'python'))} -B -m forge \"$@\"\n"
    ).encode("utf-8")


def _install_validated_wheel(slot: Path, wheel_bytes: bytes, manifest: Mapping[str, str]) -> None:
    site_packages = _candidate_site_packages(slot)
    if any(site_packages.iterdir()):
        raise InstalledForgeUpdateError("fresh candidate site-packages is not empty")
    with zipfile.ZipFile(BytesIO(wheel_bytes)) as archive:
        for info in archive.infolist():
            target = site_packages.joinpath(*Path(info.filename).parts)
            if info.is_dir():
                _safe_directory(target, create=True)
                continue
            _safe_directory(target.parent, create=True)
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(archive.read(info.filename))
                handle.flush()
                os.fsync(handle.fileno())
    entrypoint = slot / "bin" / "forge"
    descriptor = os.open(
        entrypoint,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o700,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(_entrypoint_bytes(slot))
        handle.flush()
        os.fsync(handle.fileno())
    _verify_candidate_files(slot, manifest)


def _verify_candidate_files(slot: Path, manifest: Mapping[str, str]) -> dict[str, Any]:
    site_packages = _candidate_site_packages(slot)
    for cache in list(site_packages.rglob("__pycache__")):
        _assert_no_symlink_components(cache)
        if not cache.is_dir():
            raise InstalledForgeUpdateError("candidate bytecode cache path is unsafe")
        for child in cache.rglob("*"):
            _assert_no_symlink_components(child)
        shutil.rmtree(cache)
    actual: dict[str, str] = {}
    for path in site_packages.rglob("*"):
        _assert_no_symlink_components(path)
        if path.is_file():
            relative = path.relative_to(site_packages).as_posix()
            actual[relative] = file_digest(path)
    if actual != dict(manifest):
        expected = dict(manifest)
        missing = sorted(set(expected) - set(actual))
        unexpected = sorted(set(actual) - set(expected))
        changed = sorted(name for name in set(actual) & set(expected) if actual[name] != expected[name])
        raise InstalledForgeUpdateError(
            "candidate installed files do not match the exact wheel manifest: "
            f"missing={missing[:5]}, unexpected={unexpected[:5]}, changed={changed[:5]}"
        )
    entrypoint = slot / "bin" / "forge"
    if _read_regular_bytes(entrypoint) != _entrypoint_bytes(slot):
        raise InstalledForgeUpdateError("candidate command entry point changed")
    return {
        "wheel_manifest_digest": _digest_bytes(_json_bytes(dict(manifest))),
        "installed_file_count": len(actual),
        "entrypoint_sha256": file_digest(entrypoint),
    }


class InstalledForgeUpdateController:
    def __init__(
        self,
        request: UpdateRequest,
        *,
        process_reader: Callable[[], Sequence[str]] | None = None,
        interrupt_after: str | None = None,
        reconcile_staged_controller: bool = False,
    ) -> None:
        request.validate()
        self.request = request
        self.data_root = Path(request.data_root)
        self.runtime_root = Path(request.runtime_root)
        self.database = self.data_root / "forge.db"
        self.operation_root = self.data_root / "artifacts" / "installation" / request.operation_id
        self.state_path = self.operation_root / "operation.json"
        self.receipt_path = self.operation_root / "receipt.json"
        self.backup_root = self.data_root / "backups" / "installation" / request.operation_id
        self.backup_path = self.backup_root / (
            "forge-schema39.sqlite3" if (request.existing_version, request.version) in SAME_SCHEMA_39_TRANSITIONS
            else "forge-schema38.sqlite3" if (request.existing_version, request.version) == ("2.7.24", "2.7.25")
            else "forge-schema37.sqlite3"
        )
        self.slot = self.runtime_root / "slots" / f"{request.version}-{request.wheel_sha256.removeprefix('sha256:')[:12]}"
        self.slot_receipt = self.slot / "forge-installation-slot.json"
        self.slot_claim = self.slot.parent / f".{self.slot.name}.{request.operation_id}.owner.json"
        self.current = self.runtime_root / "current"
        self.stable_resolver = self.runtime_root / "bin" / "forge"
        self.fenced_resolver = self.runtime_root / "fenced" / "forge"
        self.legacy_entrypoint = self.runtime_root / "legacy" / (
            request.resolver_sha256.removeprefix("sha256:")[:16] + "-forge"
        )
        self.process_reader = process_reader or self._processes
        self.interrupt_after = interrupt_after
        self.reconcile_staged_controller = reconcile_staged_controller

    def _state(self, *, allow_request_mismatch: bool = False) -> dict[str, Any]:
        if self.state_path.exists():
            state = _read_json(self.state_path)
            if state.get("contract_version") != CONTRACT_VERSION:
                raise InstalledForgeUpdateError("durable update operation conflicts with the requested target")
            if state.get("request") != asdict(self.request) and not allow_request_mismatch:
                raise InstalledForgeUpdateError("durable update operation conflicts with the requested target")
            return state
        state = {
            "contract_version": CONTRACT_VERSION, "operation_id": self.request.operation_id,
            "request": asdict(self.request), "request_digest": self.request.digest,
            "phase": "PREPARED", "created_at": _now(), "updated_at": _now(),
            "history": [{"phase": "PREPARED", "at": _now()}],
        }
        _atomic_json(self.state_path, state)
        return state

    def _reconcile_staged_controller(
        self, state: dict[str, Any], live: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Rebind only a source-corrected controller before any live effect."""
        previous = state.get("request")
        requested = asdict(self.request)
        if not isinstance(previous, Mapping) or set(previous) != set(requested):
            raise InstalledForgeUpdateError("durable update operation conflicts with the requested target")
        changed = {key for key in requested if previous.get(key) != requested[key]}
        resolver_correction = (
            "resolver" in changed
            and changed.issubset({"resolver", "controller_source", "controller_sha256"})
            and previous.get("resolver") == str(self.stable_resolver)
            and Path(self.request.resolver) != self.stable_resolver
            and previous.get("resolver_sha256") == requested["resolver_sha256"]
            and state.get("last_error") == "external Forge resolver has an unrecognized managed target"
        )
        controller_correction = (
            changed.issubset({"controller_source", "controller_sha256"})
            and state.get("last_error")
            == f"path contains a symbolic-link component: {self.request.resolver}"
        )
        if not changed or not (resolver_correction or controller_correction):
            raise InstalledForgeUpdateError("durable update operation conflicts with the requested target")
        previous_request = UpdateRequest(**dict(previous))
        if (
            state.get("request_digest") != previous_request.digest
            or state.get("phase") != "STAGED"
            or state.get("safety_disposition") != "UNVERIFIED_OR_MIGRATED_RUNTIME_FENCED"
            or any(
                key in state
                for key in (
                    "before", "backup", "migration_qualification", "live_migration",
                    "installed_readback", "receipt_sha256",
                )
            )
            or self.receipt_path.exists()
            or self.backup_path.exists()
        ):
            raise InstalledForgeUpdateError("controller reconciliation is not a pre-migration staged recovery")
        schema_before, _schema_after = transition_schemas(self.request)
        assert_selected_installation(self.request, live)
        assert_quiescent(live)
        if live.get("user_version") != schema_before:
            raise InstalledForgeUpdateError("controller reconciliation source schema changed")
        if file_digest(Path(__file__)) != self.request.controller_sha256:
            raise InstalledForgeUpdateError("replacement controller bytes do not match the protected candidate")
        qualification, _, manifest = _qualified_artifact(self.request)
        slot_receipt = _read_json(self.slot_receipt)
        if slot_receipt.get("request_digest") not in {previous_request.digest, self.request.digest}:
            raise InstalledForgeUpdateError("staged candidate belongs to a different operation request")
        if slot_receipt.get("wheel_manifest_digest") != qualification["wheel_manifest_digest"]:
            raise InstalledForgeUpdateError("staged candidate artifact changed during controller reconciliation")
        file_evidence = _verify_candidate_files(self.slot, manifest)
        if slot_receipt.get("installed_files") != file_evidence or state.get("installed_files") != file_evidence:
            raise InstalledForgeUpdateError("staged candidate evidence changed during controller reconciliation")
        identity = installed_identity(self.slot / "bin" / "python", cwd=self.runtime_root)
        if state.get("candidate") != identity or identity.get("version") != self.request.version:
            raise InstalledForgeUpdateError("staged candidate identity changed during controller reconciliation")
        if (
            not Path(self.request.resolver).is_symlink()
            or os.readlink(self.request.resolver) != str(self.stable_resolver)
            or not self.stable_resolver.is_symlink()
            or os.readlink(self.stable_resolver) != "../current"
            or not self.current.is_symlink()
            or self.current.resolve(strict=True) != self.fenced_resolver.resolve(strict=True)
        ):
            raise InstalledForgeUpdateError("controller reconciliation requires the recorded maintenance fence")
        reconciliation_identity = {
            "reason": (
                "PROTECTED_RESOLVER_CORRECTION_AFTER_PRE_ADOPTION_FAILURE"
                if resolver_correction else
                "PROTECTED_CONTROLLER_CORRECTION_AFTER_MANAGED_RESOLVER_PRE_ADOPTION_FAILURE"
            ),
            "previous_controller_source": previous_request.controller_source,
            "previous_controller_sha256": previous_request.controller_sha256,
            "previous_request_digest": previous_request.digest,
            "replacement_controller_source": self.request.controller_source,
            "replacement_controller_sha256": self.request.controller_sha256,
            "replacement_request_digest": self.request.digest,
        }
        state_reconciliations = state.get("controller_reconciliations", [])
        slot_reconciliations = slot_receipt.get("controller_reconciliations", [])
        if not isinstance(state_reconciliations, list) or not isinstance(slot_reconciliations, list):
            raise InstalledForgeUpdateError("controller reconciliation audit history is malformed")
        if slot_reconciliations == state_reconciliations:
            reconciliation = {**reconciliation_identity, "reconciled_at": _now()}
            slot_reconciliations = [*state_reconciliations, reconciliation]
            _atomic_json(self.slot_receipt, {
                **slot_receipt,
                "request_digest": self.request.digest,
                "controller_reconciliations": slot_reconciliations,
            })
            self._interrupt("controller_reconciliation_slot")
        elif (
            len(slot_reconciliations) == len(state_reconciliations) + 1
            and slot_reconciliations[:-1] == state_reconciliations
            and isinstance(slot_reconciliations[-1], Mapping)
            and {
                key: slot_reconciliations[-1].get(key) for key in reconciliation_identity
            } == reconciliation_identity
            and isinstance(slot_reconciliations[-1].get("reconciled_at"), str)
        ):
            reconciliation = dict(slot_reconciliations[-1])
        else:
            raise InstalledForgeUpdateError("controller reconciliation audit history conflicts")
        history = list(state.get("history", []))
        history.append({"phase": "STAGED", "event": "CONTROLLER_RECONCILED", "at": reconciliation["reconciled_at"]})
        updated = {
            **state,
            "request": requested,
            "request_digest": self.request.digest,
            "controller_reconciliations": slot_reconciliations,
            "history": history,
            "updated_at": reconciliation["reconciled_at"],
        }
        _atomic_json(self.state_path, updated)
        return updated

    def _advance(self, state: dict[str, Any], phase: str, **evidence: object) -> dict[str, Any]:
        current_phase = str(state.get("phase", "PREPARED"))
        effective_phase = phase
        if PHASE_ORDER.get(current_phase, -1) > PHASE_ORDER.get(phase, -1):
            effective_phase = current_phase
        updated = {**state, **evidence, "phase": effective_phase, "updated_at": _now()}
        history = list(state.get("history", []))
        if effective_phase != current_phase or phase == current_phase:
            history.append({"phase": effective_phase, "at": updated["updated_at"]})
        updated["history"] = history
        _atomic_json(self.state_path, updated)
        return updated

    def _interrupt(self, point: str) -> None:
        if self.interrupt_after == point:
            raise InstalledForgeUpdateError(f"simulated interruption after {point}")

    def _processes(self) -> Sequence[str]:
        result = _run(("/bin/ps", "-axo", "pid=,ppid=,command="), cwd=self.runtime_root, timeout=30)
        processes: list[str] = []
        own = {os.getpid(), os.getppid()}
        for line in result.stdout.splitlines():
            fields = line.strip().split(None, 2)
            if len(fields) != 3:
                continue
            try:
                pid, parent = int(fields[0]), int(fields[1])
            except ValueError:
                continue
            if pid in own:
                continue
            processes.append(fields[2])
        return processes

    def _assert_no_runtime_process(self) -> None:
        needles = (
            self.request.data_root, self.request.resolver, self.request.existing_interpreter,
            str(self.runtime_root / "venv"), str(self.slot),
        )
        matches = [command for command in self.process_reader() if any(needle in command for needle in needles)]
        if matches:
            raise InstalledForgeUpdateError("a selected Forge runtime process is still active")

    def _stage(self, state: dict[str, Any]) -> dict[str, Any]:
        qualification, wheel_bytes, manifest = _qualified_artifact(self.request)
        if file_digest(Path(__file__)) != self.request.controller_sha256:
            raise InstalledForgeUpdateError("installation controller bytes do not match the protected candidate")
        if self.slot_receipt.exists():
            receipt = _read_json(self.slot_receipt)
            if (
                receipt.get("request_digest") != self.request.digest
                or receipt.get("wheel_manifest_digest") != qualification["wheel_manifest_digest"]
            ):
                raise InstalledForgeUpdateError("immutable candidate slot belongs to a different request")
            file_evidence = _verify_candidate_files(self.slot, manifest)
            if receipt.get("installed_files") != file_evidence:
                raise InstalledForgeUpdateError("immutable candidate slot evidence changed")
        else:
            # Venv entry points embed their creation path.  Claim the final
            # path first; an interrupted, unreceipted slot is quarantined and
            # rebuilt from the pinned bytes rather than trusted or relocated.
            _safe_directory(self.slot.parent, create=True)
            if self.slot.is_symlink():
                raise InstalledForgeUpdateError("candidate staging path is unsafe")
            claim = {
                "contract_version": CONTRACT_VERSION,
                "request_digest": self.request.digest,
                "operation_id": self.request.operation_id,
            }
            claim_preexisting = self.slot_claim.exists()
            if claim_preexisting:
                observed_claim = _read_json(self.slot_claim)
                if any(observed_claim.get(key) != value for key, value in claim.items()):
                    raise InstalledForgeUpdateError("candidate slot claim belongs to a different request")
            else:
                _atomic_json(self.slot_claim, {**claim, "created_at": _now()})
            staging_owner = self.slot / "forge-installation-staging.json"
            if self.slot.exists():
                if not self.slot.is_dir():
                    raise InstalledForgeUpdateError("unreceipted candidate slot is unsafe")
                if staging_owner.is_file():
                    owner = _read_json(staging_owner)
                    if any(owner.get(key) != value for key, value in claim.items()):
                        raise InstalledForgeUpdateError("unreceipted candidate slot belongs to a different request")
                elif not claim_preexisting or any(self.slot.iterdir()):
                    raise InstalledForgeUpdateError("unreceipted candidate slot has no matching operation owner")
                abandoned = self.slot.parent / f".{self.slot.name}.abandoned-{secrets.token_hex(16)}"
                os.replace(self.slot, abandoned)
            self.slot.mkdir(mode=0o700)
            _atomic_json(staging_owner, {**claim, "created_at": _now()})
            _run((self.request.base_python, "-m", "venv", "--without-pip", str(self.slot)), cwd=self.runtime_root)
            candidate_python = self.slot / "bin" / "python"
            _install_validated_wheel(self.slot, wheel_bytes, manifest)
            file_evidence = _verify_candidate_files(self.slot, manifest)
            identity = installed_identity(candidate_python, cwd=self.runtime_root)
            if (
                identity.get("version") != self.request.version
                or identity.get("distribution_version") != self.request.version
                or not str(identity.get("module", "")).startswith(str(self.slot.resolve()) + os.sep)
                or Path(str(identity.get("prefix"))).resolve() != self.slot.resolve()
            ):
                raise InstalledForgeUpdateError("candidate slot identity is inconsistent")
            _atomic_json(self.slot_receipt, {
                "contract_version": CONTRACT_VERSION, "request_digest": self.request.digest,
                "wheel_sha256": self.request.wheel_sha256, "product_source": self.request.product_source,
                "version": self.request.version, "identity": identity,
                "wheel_manifest_digest": qualification["wheel_manifest_digest"],
                "installed_files": file_evidence, "staged_at": _now(),
            })
            if self.slot_claim.is_file():
                self.slot_claim.unlink()
        file_evidence = _verify_candidate_files(self.slot, manifest)
        identity = installed_identity(self.slot / "bin" / "python", cwd=self.runtime_root)
        if identity.get("version") != self.request.version or not str(identity.get("module", "")).startswith(str(self.slot.resolve()) + os.sep):
            raise InstalledForgeUpdateError("staged candidate readback changed")
        return self._advance(state, "STAGED", artifact_qualification=qualification, candidate=identity,
                             candidate_slot=str(self.slot), installed_files=file_evidence)

    def _managed_resolver_source(self, resolver: Path, state: Mapping[str, Any]) -> Path | None:
        if not resolver.is_symlink():
            return None
        _assert_no_symlink_components(resolver.parent)
        if os.readlink(resolver) != str(self.stable_resolver):
            raise InstalledForgeUpdateError("external Forge resolver has an unrecognized managed target")
        if not self.stable_resolver.is_symlink() or os.readlink(self.stable_resolver) != "../current":
            raise InstalledForgeUpdateError("stable Forge resolver changed")
        if not self.current.is_symlink():
            raise InstalledForgeUpdateError("managed Forge current resolver changed")
        existing_entrypoint = Path(self.request.existing_interpreter).parent / "forge"
        current_target = self.current.resolve(strict=True)
        allowed_targets = {existing_entrypoint.resolve(strict=True)}
        if (
            state.get("phase") == "STAGED"
            and state.get("safety_disposition") == "UNVERIFIED_OR_MIGRATED_RUNTIME_FENCED"
            and state.get("last_error") in {
                f"path contains a symbolic-link component: {self.request.resolver}",
                "external Forge resolver has an unrecognized managed target",
            }
        ):
            allowed_targets.add(self.fenced_resolver.resolve(strict=True))
        if current_target not in allowed_targets:
            raise InstalledForgeUpdateError("managed Forge current resolver has an unrecognized target")
        return existing_entrypoint

    def _adopt_resolver(self, state: dict[str, Any]) -> dict[str, Any]:
        resolver = Path(self.request.resolver)
        _safe_directory(self.runtime_root / "legacy", create=True)
        _safe_directory(self.runtime_root / "bin", create=True)
        _safe_directory(self.runtime_root / "fenced", create=True)
        if not self.legacy_entrypoint.exists():
            managed_source = self._managed_resolver_source(resolver, state)
            legacy_bytes = _read_regular_bytes(managed_source or resolver)
            if _digest_bytes(legacy_bytes) != self.request.resolver_sha256:
                raise InstalledForgeUpdateError("legacy command resolver changed before adoption")
            identity = installed_identity(Path(self.request.existing_interpreter), cwd=self.runtime_root)
            if identity.get("version") != self.request.existing_version:
                raise InstalledForgeUpdateError("legacy interpreter no longer provides the selected Forge version")
            descriptor = os.open(
                self.legacy_entrypoint,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o700,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(legacy_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            if file_digest(self.legacy_entrypoint) != self.request.resolver_sha256:
                raise InstalledForgeUpdateError("retained legacy entrypoint does not match the pinned resolver bytes")
        elif file_digest(self.legacy_entrypoint) != self.request.resolver_sha256:
            raise InstalledForgeUpdateError("retained legacy entrypoint changed")
        # The fence is shared by every update operation. Its bytes therefore
        # must be operation-independent. Releases before 2.7.24 embedded the
        # first operation id and made every later update fail closed while
        # trying to reuse the same managed launcher. Accept only that exact
        # legacy shape and atomically normalize it; arbitrary launcher changes
        # remain a hard failure.
        fence = b"#!/bin/sh\necho 'Forge installation maintenance is active' >&2\nexit 75\n"
        legacy_fence = re.compile(
            rb"\A#!/bin/sh\necho 'Forge installation maintenance is active: "
            rb"[A-Za-z0-9][A-Za-z0-9._-]{0,127}' >&2\nexit 75\n\Z"
        )
        if not self.fenced_resolver.exists():
            _atomic_regular_file(self.fenced_resolver, fence, mode=0o755)
        else:
            observed_fence = _read_regular_bytes(self.fenced_resolver)
            if observed_fence != fence:
                if legacy_fence.fullmatch(observed_fence) is None:
                    raise InstalledForgeUpdateError("maintenance fence launcher changed")
                _atomic_regular_file(self.fenced_resolver, fence, mode=0o755)
        if not self.current.exists() and not self.current.is_symlink():
            _replace_symlink(self.current, os.path.relpath(self.legacy_entrypoint, self.runtime_root))
        if not self.stable_resolver.exists() and not self.stable_resolver.is_symlink():
            _replace_symlink(self.stable_resolver, "../current")
        elif _resolved_link(self.stable_resolver) != _resolved_link(self.current):
            # The stable link follows current; compare its textual contract, not
            # a transient current target, when it already exists.
            if os.readlink(self.stable_resolver) != "../current":
                raise InstalledForgeUpdateError("stable Forge resolver changed")
        expected_external = self.stable_resolver.resolve(strict=True)
        if resolver.is_symlink():
            if resolver.resolve(strict=True) != expected_external:
                raise InstalledForgeUpdateError("external Forge resolver was retargeted")
        else:
            if file_digest(resolver) != self.request.resolver_sha256:
                raise InstalledForgeUpdateError("external Forge resolver changed")
            _replace_symlink(resolver, str(self.stable_resolver))
        return self._advance(state, "ADOPTED", resolver={
            "external": str(resolver), "stable": str(self.stable_resolver),
            "legacy": str(self.legacy_entrypoint), "legacy_sha256": self.request.resolver_sha256,
        })

    def _backup(self, state: dict[str, Any], before: Mapping[str, Any]) -> dict[str, Any]:
        schema_before, _schema_after = transition_schemas(self.request)
        existing = state.get("backup")
        if isinstance(existing, Mapping):
            if existing.get("path") != str(self.backup_path) or file_digest(self.backup_path) != existing.get("sha256"):
                raise InstalledForgeUpdateError("durable installation backup changed")
            backup = dict(existing)
            recovered = database_snapshot(self.backup_path)
            if recovered.get("content_digest") != before.get("content_digest"):
                raise InstalledForgeUpdateError("durable installation backup no longer matches the pre-migration snapshot")
        elif self.backup_path.exists() and not self.backup_path.is_symlink():
            recovered = database_snapshot(self.backup_path)
            if (
                recovered.get("user_version") != schema_before
                or recovered.get("integrity_check") != "ok"
                or recovered.get("foreign_key_check") != []
                or recovered.get("content_digest") != before.get("content_digest")
            ):
                raise InstalledForgeUpdateError("unreceipted installation backup cannot be safely adopted")
            backup = {
                "path": str(self.backup_path), "sha256": file_digest(self.backup_path),
                "size": self.backup_path.stat().st_size,
                "integrity_check": recovered["integrity_check"],
                "foreign_key_check": recovered["foreign_key_check"],
                "snapshot_digest": recovered["snapshot_digest"],
                "created_at": _now(), "recovered_after_atomic_backup_write": True,
                "source_wal_present": None, "source_shm_present": None,
            }
        else:
            backup = _copy_sqlite_backup(self.database, self.backup_path)
            backup["created_at"] = _now()
            backup["source_wal_present"] = self.database.with_name(self.database.name + "-wal").exists()
            backup["source_shm_present"] = self.database.with_name(self.database.name + "-shm").exists()
        return self._advance(state, "BACKED_UP", before=before, backup=backup)

    def _qualify_copy(self, state: dict[str, Any], before: Mapping[str, Any]) -> dict[str, Any]:
        existing = state.get("migration_qualification")
        if isinstance(existing, Mapping) and existing.get("status") == "PASS":
            database = self.operation_root / "qualification-copy" / "forge.db"
            qualified = database_snapshot(database)
            verify_preservation(before, qualified, self.request)
            if existing.get("after_snapshot_digest") != qualified.get("snapshot_digest"):
                raise InstalledForgeUpdateError("durable migration qualification copy changed")
            return state
        root = self.operation_root / "qualification-copy"
        _safe_directory(root, create=True)
        database = root / "forge.db"
        descriptor, name = tempfile.mkstemp(prefix=".forge.db.tmp-", dir=root)
        os.close(descriptor)
        temporary = Path(name)
        shutil.copyfile(self.backup_path, temporary)
        os.chmod(temporary, 0o600)
        os.replace(temporary, database)
        for suffix in ("-wal", "-shm"):
            sidecar = root / ("forge.db" + suffix)
            if sidecar.is_symlink():
                raise InstalledForgeUpdateError("qualification copy contains an unsafe SQLite sidecar")
            if sidecar.exists() and not sidecar.is_symlink():
                sidecar.unlink()
        instance = _safe_directory(root / "instance", create=True)
        marker = instance / "runtime-instance.json"
        marker_payload = (self.request.runtime_id + "\n").encode("utf-8")
        if marker.exists() or marker.is_symlink():
            if _read_regular_bytes(marker) != marker_payload:
                raise InstalledForgeUpdateError("qualification-copy runtime marker changed")
        else:
            descriptor = os.open(
                marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600,
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(marker_payload)
                handle.flush()
                os.fsync(handle.fileno())
        copy_before = database_snapshot(database)
        if copy_before.get("content_digest") != before.get("content_digest"):
            raise InstalledForgeUpdateError("isolated qualification copy does not match the consistent backup")
        _schema_before, schema_after = transition_schemas(self.request)
        candidate_output = _candidate_migrate(
            self.slot / "bin" / "forge", root, cwd=self.runtime_root,
            target_schema=schema_after,
        )
        copy_after = database_snapshot(database)
        qualification = verify_preservation(copy_before, copy_after, self.request)
        qualification.update({
            "qualified_at": _now(), "copy_root": str(root),
            "candidate_output": candidate_output,
            "before_snapshot_digest": copy_before["snapshot_digest"],
            "after_snapshot_digest": copy_after["snapshot_digest"],
        })
        return self._advance(state, "MIGRATION_QUALIFIED", migration_qualification=qualification)

    def _fence(self, state: dict[str, Any]) -> dict[str, Any]:
        _replace_symlink(self.current, os.path.relpath(self.fenced_resolver, self.runtime_root))
        if _resolved_link(Path(self.request.resolver)) != self.fenced_resolver.resolve():
            raise InstalledForgeUpdateError("external resolver did not enter the maintenance fence")
        return self._advance(state, "FENCED", safety_disposition="LEGACY_COMMAND_FENCED")

    def _restore_legacy_before_migration(self, state: dict[str, Any], error: Exception) -> None:
        _replace_symlink(self.current, os.path.relpath(self.legacy_entrypoint, self.runtime_root))
        self._advance(
            state, state.get("phase", "RECOVERY_PENDING"),
            safety_disposition="LEGACY_RESTORED_BEFORE_MIGRATION", last_error=str(error),
        )

    def _install_qualified_database(self, before: Mapping[str, Any]) -> dict[str, Any]:
        schema_before, _schema_after = transition_schemas(self.request)
        source = self.operation_root / "qualification-copy" / "forge.db"
        qualified = database_snapshot(source)
        verify_preservation(before, qualified, self.request)
        descriptor, name = tempfile.mkstemp(prefix=".forge.db.install-", dir=self.data_root)
        os.close(descriptor)
        temporary = Path(name)
        live_connection: sqlite3.Connection | None = None
        source_connection: sqlite3.Connection | None = None
        destination_connection: sqlite3.Connection | None = None
        try:
            live_connection = sqlite3.connect(self.database)
            live_connection.row_factory = sqlite3.Row
            live_connection.execute("PRAGMA busy_timeout=0")
            journal_mode = live_connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            if str(journal_mode).lower() != "delete":
                raise InstalledForgeUpdateError("live runtime journal could not enter crash-safe swap mode")
            live_connection.execute("BEGIN EXCLUSIVE")
            locked_live = database_snapshot(self.database, existing_connection=live_connection)
            if (
                locked_live.get("user_version") != schema_before
                or locked_live.get("content_digest") != before.get("content_digest")
            ):
                raise InstalledForgeUpdateError("live runtime changed after the qualified backup")
            source_connection = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
            destination_connection = sqlite3.connect(temporary)
            source_connection.backup(destination_connection)
            destination_connection.commit()
            destination_mode = destination_connection.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            if str(destination_mode).lower() != "delete":
                raise InstalledForgeUpdateError("migrated database copy has an unsafe journal mode")
            destination_connection.close()
            destination_connection = None
            source_connection.close()
            source_connection = None
            installed_copy = database_snapshot(temporary)
            verify_preservation(before, installed_copy, self.request)
            os.chmod(temporary, 0o400)
            for suffix in ("-wal", "-shm"):
                sidecar = self.database.with_name(self.database.name + suffix)
                if sidecar.is_symlink():
                    raise InstalledForgeUpdateError("live database has an unsafe SQLite sidecar")
                if sidecar.exists():
                    sidecar.unlink()
            self._interrupt("database_swap_prepared")
            os.replace(temporary, self.database)
            self._interrupt("database_swap")
            directory = os.open(self.data_root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except sqlite3.Error as error:
            raise InstalledForgeUpdateError("exclusive atomic installation of the migrated database failed") from error
        finally:
            for connection in (destination_connection, source_connection, live_connection):
                if connection is not None:
                    try:
                        connection.close()
                    except sqlite3.Error:
                        pass
            if temporary.exists() and not temporary.is_symlink():
                temporary.unlink()
        installed = database_snapshot(self.database)
        verify_preservation(before, installed, self.request)
        return installed

    def _migrate_live(self, state: dict[str, Any], before: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        schema_before, schema_after = transition_schemas(self.request)
        current = database_snapshot(self.database)
        if (self.request.existing_version, self.request.version) in SAME_SCHEMA_39_TRANSITIONS:
            qualified = database_snapshot(self.operation_root / "qualification-copy" / "forge.db")
            verify_preservation(before, qualified, self.request)
            # Candidate initialization may update the known volatile metadata in
            # its isolated copy. Preservation checks bind every historical table
            # and protected metadata key; only the live database must remain
            # byte-for-byte logically unchanged before activation.
            if (current.get("content_digest") != before.get("content_digest")
                    or qualified.get("schema_digest") != before.get("schema_digest")
                    or qualified.get("writer_state") != before.get("writer_state")
                    or set(qualified.get("metadata", {})) != set(before.get("metadata", {}))):
                raise InstalledForgeUpdateError("same-schema runtime changed outside the bounded operation")
            if state.get("phase") not in {"MIGRATED", "ACTIVATING", "ACTIVATED", "COMPLETE"}:
                state = self._fence(state)
                state = self._advance(
                    state, "MIGRATED", live_migration={
                        **verify_preservation(before, current, self.request),
                        "migrated_at": _now(), "application_mode": "UNCHANGED_DATABASE",
                        "before_snapshot_digest": before["snapshot_digest"],
                        "after_snapshot_digest": current["snapshot_digest"],
                    }, safety_disposition=f"CANDIDATE_REQUIRED_SCHEMA_{schema_after}",
                )
                self._interrupt("migration")
            return state, current
        if (
            current.get("user_version") == schema_before
            and (
                schema_before != schema_after
                or current.get("content_digest") == before.get("content_digest")
            )
        ):
            state = self._fence(state)
            self._interrupt("fence")
            after = self._install_qualified_database(before)
            preservation = verify_preservation(before, after, self.request)
            state = self._advance(
                state, "MIGRATED", live_migration={
                    **preservation, "migrated_at": _now(),
                    "application_mode": "ATOMIC_PRODUCT_MIGRATED_COPY",
                    "before_snapshot_digest": before["snapshot_digest"],
                    "after_snapshot_digest": after["snapshot_digest"],
                }, safety_disposition=f"CANDIDATE_REQUIRED_SCHEMA_{schema_after}",
            )
            self._interrupt("migration")
            return state, after
        if current.get("user_version") == schema_after:
            preservation = verify_preservation(before, current, self.request)
            os.chmod(self.database, 0o400)
            if state.get("phase") not in {"MIGRATED", "ACTIVATING", "ACTIVATED", "COMPLETE"}:
                state = self._advance(
                    state, "MIGRATED", live_migration={
                        **preservation, "reconciled_at": _now(),
                        "before_snapshot_digest": before["snapshot_digest"],
                        "after_snapshot_digest": current["snapshot_digest"],
                    }, safety_disposition=f"CANDIDATE_REQUIRED_SCHEMA_{schema_after}",
                )
            return state, current
        raise InstalledForgeUpdateError("live runtime schema changed outside the bounded operation")

    def _activate(self, state: dict[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
        _schema_before, schema_after = transition_schemas(self.request)
        state = self._advance(state, "ACTIVATING", safety_disposition="CANDIDATE_ACTIVATION_IN_PROGRESS")
        candidate = self.slot / "bin" / "forge"
        _replace_symlink(self.current, os.path.relpath(candidate, self.runtime_root))
        self._interrupt("activation")
        if _resolved_link(Path(self.request.resolver)) != candidate.resolve():
            raise InstalledForgeUpdateError("external command resolver did not activate the candidate")
        identity = installed_identity(self.slot / "bin" / "python", cwd=self.runtime_root)
        version = _run((self.request.resolver, "--version"), cwd=self.runtime_root).stdout.strip()
        status_result = _run(
            (self.request.resolver, "--data-root", self.request.data_root, "server", "status"),
            cwd=self.runtime_root,
        )
        try:
            status = json.loads(status_result.stdout)
        except json.JSONDecodeError as error:
            raise InstalledForgeUpdateError("activated CLI status readback is malformed") from error
        if (
            identity.get("version") != self.request.version
            or version != self.request.version
            or Path(str(identity.get("sys_executable", ""))).resolve() != (self.slot / "bin" / "python").resolve()
            or not str(identity.get("module", "")).startswith(str(self.slot.resolve()) + os.sep)
            or status.get("product_version") != self.request.version
            or Path(str(status.get("data_root", ""))).resolve() != self.data_root.resolve()
            or status.get("instance_id") != self.request.runtime_id
            or status.get("storage_schema") != str(schema_after)
        ):
            raise InstalledForgeUpdateError("activated Forge CLI readback does not match the selected installation")
        final_snapshot = database_snapshot(self.database)
        preservation = verify_preservation(state["before"], final_snapshot, self.request)
        return self._advance(
            state, "ACTIVATED", installed_readback={
                "identity": identity, "cli_version": version, "status": status,
                "database_snapshot_digest": final_snapshot["snapshot_digest"],
                "database_schema_digest": final_snapshot["schema_digest"],
                "preservation": preservation, "resolver": self.request.resolver,
                "resolved_executable": str(candidate.resolve()),
            }, safety_disposition="CANDIDATE_ACTIVE",
        )

    def _secure_failure(self, state: dict[str, Any], error: Exception) -> None:
        """Leave a pre-migration legacy route or a schema-38-safe candidate/fence."""
        try:
            state = self._state()
        except Exception:
            pass
        try:
            current = database_snapshot(self.database)
        except Exception:
            current = {}
        before = state.get("before")
        schema_before, _schema_after = transition_schemas(self.request)
        if (
            current.get("user_version") == schema_before
            and isinstance(before, Mapping)
            and current.get("content_digest") == before.get("content_digest")
            and self.legacy_entrypoint.exists()
            and ((self.request.existing_version, self.request.version) not in SAME_SCHEMA_39_TRANSITIONS
                 or state.get("phase") not in {"MIGRATED", "ACTIVATING", "ACTIVATED", "COMPLETE"})
        ):
            self._restore_legacy_before_migration(state, error)
            return
        _replace_symlink(self.current, os.path.relpath(self.fenced_resolver, self.runtime_root))
        self._advance(
            state, state.get("phase", "RECOVERY_PENDING"),
            safety_disposition="UNVERIFIED_OR_MIGRATED_RUNTIME_FENCED", last_error=str(error),
        )

    def _verify_complete(self, state: Mapping[str, Any], receipt: Mapping[str, Any]) -> None:
        _schema_before, schema_after = transition_schemas(self.request)
        if state.get("phase") != "COMPLETE" or state.get("request_digest") != self.request.digest:
            raise InstalledForgeUpdateError("completed operation state conflicts with this request")
        if state.get("receipt_sha256") != file_digest(self.receipt_path):
            raise InstalledForgeUpdateError("completed operation receipt changed")
        qualification, _, manifest = _qualified_artifact(self.request)
        if file_digest(Path(__file__)) != self.request.controller_sha256:
            raise InstalledForgeUpdateError("completed operation controller bytes changed")
        if receipt.get("request_digest") != self.request.digest or receipt.get("state") != "COMPLETE":
            raise InstalledForgeUpdateError("completed update receipt conflicts with this request")
        backup = receipt.get("backup")
        if (
            not isinstance(backup, Mapping)
            or backup.get("path") != str(self.backup_path)
            or backup.get("sha256") != file_digest(self.backup_path)
        ):
            raise InstalledForgeUpdateError("completed operation backup changed")
        slot_receipt = _read_json(self.slot_receipt)
        file_evidence = _verify_candidate_files(self.slot, manifest)
        if (
            slot_receipt.get("request_digest") != self.request.digest
            or slot_receipt.get("wheel_manifest_digest") != qualification["wheel_manifest_digest"]
            or slot_receipt.get("installed_files") != file_evidence
        ):
            raise InstalledForgeUpdateError("completed operation candidate slot changed")
        candidate = self.slot / "bin" / "forge"
        if _resolved_link(Path(self.request.resolver)) != candidate.resolve():
            raise InstalledForgeUpdateError("completed operation resolver no longer selects the candidate")
        identity = installed_identity(self.slot / "bin" / "python", cwd=self.runtime_root)
        version = _run((self.request.resolver, "--version"), cwd=self.runtime_root).stdout.strip()
        status_result = _run(
            (self.request.resolver, "--data-root", self.request.data_root, "server", "status"),
            cwd=self.runtime_root,
        )
        try:
            status = json.loads(status_result.stdout)
        except json.JSONDecodeError as error:
            raise InstalledForgeUpdateError("completed installed CLI readback is malformed") from error
        if (
            identity.get("version") != self.request.version
            or identity.get("distribution_version") != self.request.version
            or not str(identity.get("module", "")).startswith(str(self.slot.resolve()) + os.sep)
            or version != self.request.version
            or status.get("product_version") != self.request.version
            or status.get("instance_id") != self.request.runtime_id
            or status.get("storage_schema") != str(schema_after)
            or Path(str(status.get("data_root", ""))).resolve() != self.data_root.resolve()
        ):
            raise InstalledForgeUpdateError("completed installed CLI identity changed")
        final_snapshot = database_snapshot(self.database)
        assert_selected_installation(self.request, final_snapshot)
        if final_snapshot.get("integrity_check") != "ok" or final_snapshot.get("foreign_key_check") != []:
            raise InstalledForgeUpdateError("completed runtime database integrity changed")
        before = state.get("before")
        if not isinstance(before, Mapping):
            raise InstalledForgeUpdateError("completed operation lacks its pre-migration snapshot")
        backup_snapshot = database_snapshot(self.backup_path)
        if backup_snapshot.get("content_digest") != before.get("content_digest"):
            raise InstalledForgeUpdateError("completed operation backup no longer matches its source snapshot")
        for key in ("migration_qualification", "live_migration"):
            evidence = receipt.get(key)
            if not isinstance(evidence, Mapping) or evidence.get("status") != "PASS":
                raise InstalledForgeUpdateError("completed operation lacks successful migration evidence")
        installed_readback = receipt.get("installed_readback")
        if (
            not isinstance(installed_readback, Mapping)
            or not isinstance(installed_readback.get("preservation"), Mapping)
            or installed_readback["preservation"].get("status") != "PASS"
        ):
            raise InstalledForgeUpdateError("completed operation lacks successful installation readback")
        assert_completed_schema(final_snapshot, installed_readback, self.request)

    def _restore_database_writable(self) -> None:
        _assert_no_symlink_components(self.database)
        if not self.database.is_file():
            raise InstalledForgeUpdateError("installed database is unavailable after activation")
        os.chmod(self.database, 0o600)

    def run(self) -> dict[str, Any]:
        _safe_directory(self.data_root)
        _safe_directory(self.runtime_root)
        update_lock = self.runtime_root / "locks" / "installation-update.lock"
        controller_lock = self.data_root / "forge-mission-controller.lock"
        runtime_lock = self.data_root / "forge-runtime-mutation.lock"
        bootstrap_lock = self.data_root / "locks" / "runtime.lock"
        with exclusive_lock(update_lock), exclusive_lock(controller_lock):
            _safe_directory(self.operation_root, create=True)
            os.chmod(self.operation_root, 0o700)
            state = self._state(allow_request_mismatch=self.reconcile_staged_controller)
            if state.get("request") != asdict(self.request):
                with exclusive_lock(runtime_lock), exclusive_lock(bootstrap_lock):
                    self._assert_no_runtime_process()
                    live = database_snapshot(self.database)
                    state = self._reconcile_staged_controller(state, live)
            if state.get("phase") == "COMPLETE":
                receipt = _read_json(self.receipt_path)
                self._verify_complete(state, receipt)
                self._restore_database_writable()
                return receipt

            state = self._stage(state)
            self._interrupt("stage")
            with exclusive_lock(runtime_lock), exclusive_lock(bootstrap_lock):
                self._assert_no_runtime_process()
                live = database_snapshot(self.database)
                assert_selected_installation(self.request, live)
                live = reconcile_terminal_dispatcher_for_update(self.request, live, self.database)
                try:
                    schema_before, _schema_after = transition_schemas(self.request)
                    state = self._adopt_resolver(state)
                    self._interrupt("adoption")
                    before = state.get("before")
                    if not isinstance(before, Mapping):
                        if live.get("user_version") != schema_before:
                            raise InstalledForgeUpdateError(
                                "selected schema lacks this operation's pre-migration snapshot"
                            )
                        before = live
                    assert_selected_installation(self.request, before)
                    if before.get("user_version") != schema_before:
                        raise InstalledForgeUpdateError(
                            "durable pre-migration snapshot has the wrong source schema"
                        )
                    state = self._backup(state, before)
                    self._interrupt("backup")
                    state = self._qualify_copy(state, before)
                    self._interrupt("qualification")
                    state, after = self._migrate_live(state, before)
                    state = self._activate(state, after)
                    receipt = {
                        "contract_version": CONTRACT_VERSION,
                        "operation_id": self.request.operation_id,
                        "request_digest": self.request.digest,
                        "state": "COMPLETE",
                        "product": "forge",
                        "version": self.request.version,
                        "product_source": self.request.product_source,
                        "wheel_sha256": self.request.wheel_sha256,
                        "controller_source": self.request.controller_source,
                        "controller_sha256": self.request.controller_sha256,
                        "runtime_id": self.request.runtime_id,
                        "installation_id": self.request.installation_id,
                        "data_root": self.request.data_root,
                        "backup": state["backup"],
                        "migration_qualification": state["migration_qualification"],
                        "live_migration": state["live_migration"],
                        "installed_readback": state["installed_readback"],
                        "credential_disposition": "PRESERVED_UNCHANGED",
                        "service_disposition": "NOT_STARTED",
                        "mission_disposition": "NOT_STARTED_OR_RESUMED",
                        "reset_disposition": "NOT_EXECUTED",
                        "completed_at": _now(),
                    }
                    _atomic_json(self.receipt_path, receipt)
                    self._advance(state, "COMPLETE", receipt_sha256=file_digest(self.receipt_path),
                                  safety_disposition="CANDIDATE_ACTIVE")
                    self._restore_database_writable()
                    return receipt
                except Exception as error:
                    try:
                        self._secure_failure(state, error)
                    except Exception:
                        pass
                    raise


def _request_from_args(args: argparse.Namespace) -> UpdateRequest:
    return UpdateRequest(
        operation_id=args.operation_id, version=args.version, product_source=args.product_source,
        wheel=str(args.wheel), wheel_sha256=args.wheel_sha256,
        qualification_receipt=str(args.qualification_receipt),
        qualification_receipt_sha256=args.qualification_receipt_sha256,
        controller_source=args.controller_source, controller_sha256=args.controller_sha256,
        data_root=str(args.data_root), runtime_root=str(args.runtime_root),
        runtime_id=args.runtime_id, installation_id=args.installation_id,
        peer_configuration_digest=args.peer_configuration_digest,
        resolver=str(args.resolver), resolver_sha256=args.resolver_sha256,
        existing_interpreter=str(args.existing_interpreter), existing_version=args.existing_version,
        base_python=str(args.base_python),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely update one exact installed Forge runtime")
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--product-source", required=True)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--wheel-sha256", required=True)
    parser.add_argument("--qualification-receipt", required=True, type=Path)
    parser.add_argument("--qualification-receipt-sha256", required=True)
    parser.add_argument("--controller-source", required=True)
    parser.add_argument("--controller-sha256", required=True)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--runtime-id", required=True)
    parser.add_argument("--installation-id", required=True)
    parser.add_argument("--peer-configuration-digest", required=True)
    parser.add_argument("--resolver", required=True, type=Path)
    parser.add_argument("--resolver-sha256", required=True)
    parser.add_argument("--existing-interpreter", required=True, type=Path)
    parser.add_argument("--existing-version", required=True)
    parser.add_argument("--base-python", required=True, type=Path)
    parser.add_argument(
        "--reconcile-staged-controller", action="store_true",
        help="rebind a protected controller only after the recognized pre-adoption staged failure",
    )
    args = parser.parse_args(argv)
    try:
        receipt = InstalledForgeUpdateController(
            _request_from_args(args),
            reconcile_staged_controller=args.reconcile_staged_controller,
        ).run()
    except (InstalledForgeUpdateError, OSError, sqlite3.Error, ValueError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
