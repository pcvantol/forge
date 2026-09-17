#!/usr/bin/env python3
"""Validate and resume one already-published Forge release without uploading it again."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from email.parser import Parser
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import tarfile
from typing import Mapping
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pypi_distribution_readback import distribution_filenames, expected_digests_from_sha256sums
from release_operation import ReleaseOperation, ReleaseOperationError, ReleaseOperationStore


RECONCILIATION_CONTRACT = "forge-existing-release-reconciliation/v1"
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_RUN_ID = re.compile(r"[1-9][0-9]*\Z")
_STATE_RANK = {
    "PREPARED": 0,
    "QUALIFIED": 1,
    "PUBLISHED": 2,
    "CLEANUP_PENDING": 3,
    "RELEASE_COMPLETE": 4,
}


class ExistingReleaseReconciliationError(RuntimeError):
    """The supplied historical release evidence cannot be reconciled safely."""


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ExistingReleaseReconciliationError(f"release evidence is unreadable: {path.name}") from error


def _digest(path: Path) -> str:
    supplied = Path(path)
    if supplied.is_symlink():
        raise ExistingReleaseReconciliationError(f"release artifact is unavailable or unsafe: {path.name}")
    candidate = supplied.resolve()
    if not candidate.is_file():
        raise ExistingReleaseReconciliationError(f"release artifact is unavailable or unsafe: {path.name}")
    value = sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return "sha256:" + value.hexdigest()


def _validate_original_run(document: object, *, run_id: str, source_revision: str) -> None:
    if not isinstance(document, Mapping):
        raise ExistingReleaseReconciliationError("original release run evidence is invalid")
    expected = {
        "databaseId": int(run_id),
        "status": "completed",
        "conclusion": "failure",
        "headSha": source_revision,
        "event": "workflow_dispatch",
        "workflowName": "Forge production release",
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise ExistingReleaseReconciliationError(f"original release run {key} does not match")
    jobs = document.get("jobs")
    if not isinstance(jobs, list) or any(not isinstance(item, Mapping) for item in jobs):
        raise ExistingReleaseReconciliationError("original release run jobs are invalid")
    conclusions = {str(item.get("name")): item.get("conclusion") for item in jobs}
    required = {
        "build-and-qualify": "success",
        "publish-pypi": "success",
        "registry-readback-and-published-evidence": "failure",
        "record-release-complete": "skipped",
    }
    if any(conclusions.get(name) != conclusion for name, conclusion in required.items()):
        raise ExistingReleaseReconciliationError("original release run did not fail at the expected post-publication boundary")


def _validate_package_metadata(wheel: Path, sdist: Path, *, version: str) -> None:
    try:
        with zipfile.ZipFile(wheel) as archive:
            metadata_names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metadata_names) != 1:
                raise ExistingReleaseReconciliationError("wheel metadata is missing or ambiguous")
            wheel_metadata = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
        with tarfile.open(sdist, "r:gz") as archive:
            metadata_members = [
                member for member in archive.getmembers()
                if member.name.endswith("/PKG-INFO") and member.name.count("/") == 1
            ]
            if len(metadata_members) != 1:
                raise ExistingReleaseReconciliationError("source-distribution metadata is missing or ambiguous")
            extracted = archive.extractfile(metadata_members[0])
            if extracted is None:
                raise ExistingReleaseReconciliationError("source-distribution metadata is unavailable")
            sdist_metadata = Parser().parsestr(extracted.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, tarfile.TarError) as error:
        raise ExistingReleaseReconciliationError("published distribution metadata is unreadable") from error
    for label, metadata in (("wheel", wheel_metadata), ("source distribution", sdist_metadata)):
        if metadata.get("Name") != "forge-autonomy" or metadata.get("Version") != version:
            raise ExistingReleaseReconciliationError(f"{label} package identity does not match")


def validate_reconciliation(
    *,
    run_document: object,
    qualified_action: bytes,
    qualified_release: bytes,
    hashes: Path,
    wheel: Path,
    sdist: Path,
    version: str,
    source_revision: str,
    original_run_id: str,
    controller_source: str,
    reconciliation_run_id: str,
    release_document: object,
) -> dict[str, object]:
    _validate_original_run(run_document, run_id=original_run_id, source_revision=source_revision)
    if qualified_action != qualified_release:
        raise ExistingReleaseReconciliationError("draft release qualified receipt differs from the original run")
    try:
        qualified = ReleaseOperation.parse(json.loads(qualified_action))
    except (json.JSONDecodeError, ReleaseOperationError) as error:
        raise ExistingReleaseReconciliationError("qualified release operation receipt is invalid") from error

    filenames = distribution_filenames(version)
    expected = expected_digests_from_sha256sums(hashes, filenames)
    observed = {
        filenames[0]: _digest(wheel),
        filenames[1]: _digest(sdist),
    }
    normalized_expected = {name: "sha256:" + digest for name, digest in expected.items()}
    if observed != normalized_expected:
        raise ExistingReleaseReconciliationError("fresh registry artifacts differ from the qualified hashes")
    requested = ReleaseOperation.create(
        operation_id=f"forge-release-{version}-{source_revision}",
        version=version,
        policy_revision="forge-bootstrap-release-cadence-v2",
        source_revision=source_revision,
        artifacts={"wheel": observed[filenames[0]], "sdist": observed[filenames[1]]},
    )
    if not qualified.same_identity(requested) or qualified.state != "QUALIFIED":
        raise ExistingReleaseReconciliationError("qualified release receipt does not bind the requested identity")
    qualification = dict(qualified.qualification or {})
    if qualification.get("exact_main_sha") != source_revision:
        raise ExistingReleaseReconciliationError("qualification does not bind the product source")
    if qualification.get("qualification") != "forge-production-distribution":
        raise ExistingReleaseReconciliationError("qualification kind is not the production distribution gate")
    if qualification.get("artifact_digests") != {
        f"dist/{filenames[0]}": observed[filenames[0]],
        f"dist/{filenames[1]}": observed[filenames[1]],
    }:
        raise ExistingReleaseReconciliationError("qualification does not bind the fresh registry artifacts")
    _validate_package_metadata(wheel, sdist, version=version)
    release_identity = validate_release_inventory(
        release_document, version=version, source_revision=source_revision,
    )["release"]
    return {
        "reconciliation_contract": RECONCILIATION_CONTRACT,
        "original_release_run_id": original_run_id,
        "original_release_run_conclusion": "failure",
        "reconciliation_run_id": reconciliation_run_id,
        "release_controller_source": controller_source,
        "product_source_revision": source_revision,
        "registry": "pypi",
        "readback": "PASS",
        "observed_artifact_digests": observed,
        "github_release": release_identity,
    }


def _release_asset_names(version: str, source_revision: str) -> dict[str, str]:
    stem = f"{version}-{source_revision}.json"
    return {
        "qualified": f"forge-release-qualified-{stem}",
        "published": f"forge-release-published-{stem}",
        "cleanup_pending": f"forge-cleanup-pending-{stem}",
        "complete": f"forge-release-complete-{stem}",
    }


def validate_release_inventory(
    document: object, *, version: str, source_revision: str,
) -> dict[str, object]:
    if not isinstance(document, Mapping):
        raise ExistingReleaseReconciliationError("GitHub release inventory is invalid")
    expected_release = {
        "tag": f"forge-v{version}",
        "target_commitish": source_revision,
    }
    if document.get("tagName") != expected_release["tag"]:
        raise ExistingReleaseReconciliationError("GitHub release tag name does not match")
    if document.get("targetCommitish") != source_revision:
        raise ExistingReleaseReconciliationError("GitHub release target does not match the product source")
    database_id, node_id, api_url = document.get("databaseId"), document.get("id"), document.get("apiUrl")
    if (
        not isinstance(database_id, int) or database_id <= 0
        or not isinstance(node_id, str) or not node_id
        or not isinstance(api_url, str) or not api_url.startswith("https://api.github.com/")
    ):
        raise ExistingReleaseReconciliationError("GitHub release identity is incomplete")
    if not isinstance(document.get("isDraft"), bool):
        raise ExistingReleaseReconciliationError("GitHub release draft state is invalid")
    if document.get("isPrerelease") is not False:
        raise ExistingReleaseReconciliationError("production GitHub release must not be a prerelease")
    if not isinstance(document.get("isImmutable"), bool):
        raise ExistingReleaseReconciliationError("GitHub release immutability state is invalid")
    assets = document.get("assets")
    if not isinstance(assets, list) or any(not isinstance(item, Mapping) for item in assets):
        raise ExistingReleaseReconciliationError("GitHub release asset inventory is invalid")
    allowed = set(_release_asset_names(version, source_revision).values())
    names = [item.get("name") for item in assets]
    if any(not isinstance(name, str) or name not in allowed for name in names):
        raise ExistingReleaseReconciliationError("GitHub release contains an unexpected asset")
    if len(names) != len(set(names)):
        raise ExistingReleaseReconciliationError("GitHub release contains duplicate asset names")
    if _release_asset_names(version, source_revision)["qualified"] not in names:
        raise ExistingReleaseReconciliationError("GitHub release lacks the qualified operation receipt")
    named = _release_asset_names(version, source_revision)
    if named["complete"] in names and named["published"] not in names:
        raise ExistingReleaseReconciliationError("GitHub release complete receipt lacks its published predecessor")
    if named["cleanup_pending"] in names and named["published"] not in names:
        raise ExistingReleaseReconciliationError("GitHub release cleanup-pending receipt lacks its published predecessor")
    for item in assets:
        if (
            item.get("state") != "uploaded"
            or not isinstance(item.get("size"), int) or item["size"] <= 0
            or not isinstance(item.get("digest"), str) or _SHA256.fullmatch(item["digest"]) is None
        ):
            raise ExistingReleaseReconciliationError("GitHub release asset evidence is incomplete")
    return {
        "release": {
            **expected_release,
            "database_id": database_id,
            "node_id": node_id,
            "api_url": api_url,
        },
        "is_draft": document["isDraft"],
        "is_immutable": document["isImmutable"],
        "assets": sorted(names),
    }


def validate_same_release(
    expected_document: object, current_document: object, *, version: str, source_revision: str,
) -> dict[str, object]:
    expected = validate_release_inventory(
        expected_document, version=version, source_revision=source_revision,
    )
    current = validate_release_inventory(
        current_document, version=version, source_revision=source_revision,
    )
    if expected["release"] != current["release"]:
        raise ExistingReleaseReconciliationError("GitHub release object identity changed during reconciliation")
    return current


def validate_release_assets(
    document: object, asset_root: Path, *, version: str, source_revision: str,
) -> dict[str, object]:
    result = validate_release_inventory(document, version=version, source_revision=source_revision)
    assets = document["assets"]  # type: ignore[index]
    expected_names = set(result["assets"])  # type: ignore[arg-type]
    root = Path(asset_root)
    if root.is_symlink() or not root.is_dir():
        raise ExistingReleaseReconciliationError("GitHub release asset directory is unavailable or unsafe")
    observed_names = {path.name for path in root.iterdir()}
    if observed_names != expected_names:
        raise ExistingReleaseReconciliationError("downloaded GitHub release assets do not match inventory")
    by_name = {str(item["name"]): item for item in assets}
    for name in expected_names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ExistingReleaseReconciliationError("downloaded GitHub release asset is unavailable or unsafe")
        if path.stat().st_size != by_name[name]["size"] or _digest(path) != by_name[name]["digest"]:
            raise ExistingReleaseReconciliationError("downloaded GitHub release asset differs from inventory")
    return result


def _validate_publication_evidence(
    operation: ReleaseOperation, *, original_run_id: str, release_identity: Mapping[str, object],
) -> None:
    expected_digests = {
        f"forge_autonomy-{operation.version}-py3-none-any.whl": operation.artifacts["wheel"],
        f"forge_autonomy-{operation.version}.tar.gz": operation.artifacts["sdist"],
    }
    evidence = operation.publication_receipt
    if not isinstance(evidence, Mapping) or set(evidence) != {
        "reconciliation_contract", "original_release_run_id", "original_release_run_conclusion",
        "reconciliation_run_id", "release_controller_source", "product_source_revision",
        "registry", "readback", "observed_artifact_digests", "github_release",
    }:
        raise ExistingReleaseReconciliationError("published receipt evidence shape is invalid")
    if (
        evidence["reconciliation_contract"] != RECONCILIATION_CONTRACT
        or evidence["original_release_run_id"] != original_run_id
        or evidence["original_release_run_conclusion"] != "failure"
        or evidence["product_source_revision"] != operation.source_revision
        or evidence["registry"] != "pypi"
        or evidence["readback"] != "PASS"
        or evidence["observed_artifact_digests"] != expected_digests
        or evidence["github_release"] != dict(release_identity)
        or not isinstance(evidence["reconciliation_run_id"], str)
        or _RUN_ID.fullmatch(evidence["reconciliation_run_id"]) is None
        or not isinstance(evidence["release_controller_source"], str)
        or _REVISION.fullmatch(evidence["release_controller_source"]) is None
    ):
        raise ExistingReleaseReconciliationError("published receipt evidence does not match the release identity")


def validate_new_publication_evidence(
    *, qualified_path: Path, publication_path: Path, original_run_id: str,
    release_identity: Mapping[str, object], controller_source: str, reconciliation_run_id: str,
) -> dict[str, object]:
    try:
        qualified = ReleaseOperation.parse(_load_json(qualified_path))
    except ReleaseOperationError as error:
        raise ExistingReleaseReconciliationError("qualified operation receipt is invalid") from error
    if qualified.state != "QUALIFIED":
        raise ExistingReleaseReconciliationError("new publication must start from the qualified operation")
    publication = _load_json(publication_path)
    if not isinstance(publication, Mapping):
        raise ExistingReleaseReconciliationError("new publication evidence is invalid")
    try:
        published = qualified.transition("PUBLISHED", evidence=publication)
    except ReleaseOperationError as error:
        raise ExistingReleaseReconciliationError("new publication evidence is invalid") from error
    _validate_publication_evidence(
        published, original_run_id=original_run_id, release_identity=release_identity,
    )
    if (
        publication.get("release_controller_source") != controller_source
        or publication.get("reconciliation_run_id") != reconciliation_run_id
    ):
        raise ExistingReleaseReconciliationError("new publication evidence is not bound to this controller run")
    return {
        "state": "QUALIFIED",
        "controller_runs": [{
            "phase": "publication", "run_id": reconciliation_run_id,
            "controller_source": controller_source,
        }],
    }


def validate_controller_run(
    document: object, *, run_id: str, controller_source: str,
) -> dict[str, object]:
    if not isinstance(document, Mapping):
        raise ExistingReleaseReconciliationError("release controller run evidence is invalid")
    expected = {
        "databaseId": int(run_id),
        "headSha": controller_source,
        "event": "workflow_dispatch",
        "workflowName": "Forge existing release reconciliation",
    }
    for key, value in expected.items():
        if document.get(key) != value:
            raise ExistingReleaseReconciliationError(f"release controller run {key} does not match")
    if document.get("status") not in {"queued", "in_progress", "completed"}:
        raise ExistingReleaseReconciliationError("release controller run status is invalid")
    return {"run_id": run_id, "controller_source": controller_source}


def validate_followup_receipts(
    *,
    published_path: Path,
    pending_path: Path | None,
    complete_path: Path | None,
    original_run_id: str,
    release_identity: Mapping[str, object],
) -> dict[str, object]:
    try:
        published = ReleaseOperation.parse(_load_json(published_path))
    except ReleaseOperationError as error:
        raise ExistingReleaseReconciliationError("published follow-up receipt is invalid") from error
    if published.state != "PUBLISHED":
        raise ExistingReleaseReconciliationError("published follow-up receipt has the wrong state")
    _validate_publication_evidence(
        published, original_run_id=original_run_id, release_identity=release_identity,
    )
    controller_runs = [{
        "phase": "publication",
        "run_id": published.publication_receipt["reconciliation_run_id"],  # type: ignore[index]
        "controller_source": published.publication_receipt["release_controller_source"],  # type: ignore[index]
    }]
    highest = published
    pending: ReleaseOperation | None = None
    if pending_path is not None:
        try:
            pending = ReleaseOperation.parse(_load_json(pending_path))
        except ReleaseOperationError as error:
            raise ExistingReleaseReconciliationError("cleanup-pending follow-up receipt is invalid") from error
        if (
            pending.state != "CLEANUP_PENDING"
            or not published.same_identity(pending)
            or pending.qualification != published.qualification
            or pending.publication_receipt != published.publication_receipt
            or not isinstance(pending.cleanup, Mapping)
            or set(pending.cleanup) != {
                "result", "reconciliation_contract", "original_release_run_id",
                "reconciliation_run_id", "release_controller_source", "github_release",
                "operation_local_cleanup", "failed_targets",
            }
            or pending.cleanup["result"] != "CLEANUP_PENDING"
            or pending.cleanup["reconciliation_contract"] != RECONCILIATION_CONTRACT
            or pending.cleanup["original_release_run_id"] != original_run_id
            or pending.cleanup["github_release"] != {
                **dict(release_identity), "draft": False, "tag_commit": published.source_revision,
            }
            or pending.cleanup["operation_local_cleanup"] != "PENDING"
            or not isinstance(pending.cleanup["failed_targets"], list)
            or not pending.cleanup["failed_targets"]
            or any(not isinstance(item, str) or not item for item in pending.cleanup["failed_targets"])
            or not isinstance(pending.cleanup["reconciliation_run_id"], str)
            or _RUN_ID.fullmatch(pending.cleanup["reconciliation_run_id"]) is None
            or not isinstance(pending.cleanup["release_controller_source"], str)
            or _REVISION.fullmatch(pending.cleanup["release_controller_source"]) is None
        ):
            raise ExistingReleaseReconciliationError("cleanup-pending follow-up receipt breaks release lineage")
        highest = pending
        controller_runs.append({
            "phase": "cleanup_pending",
            "run_id": pending.cleanup["reconciliation_run_id"],  # type: ignore[index]
            "controller_source": pending.cleanup["release_controller_source"],  # type: ignore[index]
        })
    if complete_path is not None:
        try:
            complete = ReleaseOperation.parse(_load_json(complete_path))
        except ReleaseOperationError as error:
            raise ExistingReleaseReconciliationError("complete follow-up receipt is invalid") from error
        cleanup = complete.cleanup
        if (
            complete.state != "RELEASE_COMPLETE"
            or not published.same_identity(complete)
            or complete.qualification != published.qualification
            or complete.publication_receipt != published.publication_receipt
            or not isinstance(cleanup, Mapping)
            or set(cleanup) != {
                "result", "reconciliation_contract", "original_release_run_id",
                "reconciliation_run_id", "release_controller_source", "github_release",
                "operation_local_cleanup",
            }
            or cleanup["result"] != "COMPLETE"
            or cleanup["reconciliation_contract"] != RECONCILIATION_CONTRACT
            or cleanup["original_release_run_id"] != original_run_id
            or cleanup["operation_local_cleanup"] != "COMPLETE"
            or cleanup["github_release"] != {
                **dict(release_identity), "draft": False, "tag_commit": published.source_revision,
            }
            or not isinstance(cleanup["reconciliation_run_id"], str)
            or _RUN_ID.fullmatch(cleanup["reconciliation_run_id"]) is None
            or not isinstance(cleanup["release_controller_source"], str)
            or _REVISION.fullmatch(cleanup["release_controller_source"]) is None
        ):
            raise ExistingReleaseReconciliationError("complete follow-up receipt breaks release lineage")
        if pending is not None and (
            not pending.same_identity(complete)
            or pending.qualification != complete.qualification
            or pending.publication_receipt != complete.publication_receipt
        ):
            raise ExistingReleaseReconciliationError("complete receipt does not preserve cleanup-pending lineage")
        highest = complete
        controller_runs.append({
            "phase": "completion",
            "run_id": complete.cleanup["reconciliation_run_id"],  # type: ignore[index]
            "controller_source": complete.cleanup["release_controller_source"],  # type: ignore[index]
        })
    return {
        "state": highest.state,
        "receipt": str(complete_path if complete_path is not None else pending_path or published_path),
        "controller_runs": controller_runs,
    }


def hydrate_followup_receipt(evidence_root: Path, operation_id: str, receipt_path: Path) -> ReleaseOperation:
    try:
        candidate = ReleaseOperation.parse(_load_json(receipt_path))
    except ReleaseOperationError as error:
        raise ExistingReleaseReconciliationError("follow-up release receipt is invalid") from error
    if candidate.operation_id != operation_id or candidate.state not in {
        "PUBLISHED", "CLEANUP_PENDING", "RELEASE_COMPLETE",
    }:
        raise ExistingReleaseReconciliationError("follow-up release receipt has an invalid operation or state")
    store = ReleaseOperationStore(evidence_root)
    store.acquire(operation_id)
    try:
        current = store.load(operation_id)
        if current is None or not current.same_identity(candidate):
            raise ExistingReleaseReconciliationError("follow-up release receipt changes immutable identity")
        if current.qualification != candidate.qualification:
            raise ExistingReleaseReconciliationError("follow-up release receipt changes qualification evidence")
        if _STATE_RANK[candidate.state] < _STATE_RANK[current.state]:
            raise ExistingReleaseReconciliationError("follow-up release receipt regresses release state")
        if current.publication_receipt is not None and current.publication_receipt != candidate.publication_receipt:
            raise ExistingReleaseReconciliationError("follow-up release receipt changes publication evidence")
        if current.cleanup is not None and current.cleanup != candidate.cleanup:
            raise ExistingReleaseReconciliationError("follow-up release receipt changes completion evidence")
        if current != candidate:
            current = store.replace(current, candidate)
        store.record_publication(current)
        return current
    finally:
        store.release(operation_id)


def completion_evidence(
    *, version: str, original_run_id: str, controller_source: str, reconciliation_run_id: str,
    source_revision: str, release_identity: Mapping[str, object],
) -> dict[str, object]:
    return {
        "result": "COMPLETE",
        "reconciliation_contract": RECONCILIATION_CONTRACT,
        "original_release_run_id": original_run_id,
        "reconciliation_run_id": reconciliation_run_id,
        "release_controller_source": controller_source,
        "github_release": {
            **dict(release_identity), "tag": f"forge-v{version}",
            "draft": False, "tag_commit": source_revision,
        },
        "operation_local_cleanup": "COMPLETE",
    }


def cleanup_pending_evidence(
    *, original_run_id: str, controller_source: str, reconciliation_run_id: str,
    source_revision: str, release_identity: Mapping[str, object], failed_targets: list[str],
) -> dict[str, object]:
    if not failed_targets or any(not isinstance(item, str) or not item for item in failed_targets):
        raise ExistingReleaseReconciliationError("cleanup-pending evidence requires failed targets")
    return {
        "result": "CLEANUP_PENDING",
        "reconciliation_contract": RECONCILIATION_CONTRACT,
        "original_release_run_id": original_run_id,
        "reconciliation_run_id": reconciliation_run_id,
        "release_controller_source": controller_source,
        "github_release": {
            **dict(release_identity), "draft": False, "tag_commit": source_revision,
        },
        "operation_local_cleanup": "PENDING",
        "failed_targets": failed_targets,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate")
    validate.add_argument("--run-json", type=Path, required=True)
    validate.add_argument("--qualified-action", type=Path, required=True)
    validate.add_argument("--qualified-release", type=Path, required=True)
    validate.add_argument("--hashes", type=Path, required=True)
    validate.add_argument("--wheel", type=Path, required=True)
    validate.add_argument("--sdist", type=Path, required=True)
    validate.add_argument("--version", required=True)
    validate.add_argument("--source-revision", required=True)
    validate.add_argument("--original-run-id", required=True)
    validate.add_argument("--controller-source", required=True)
    validate.add_argument("--reconciliation-run-id", required=True)
    validate.add_argument("--release-json", type=Path, required=True)
    inventory = subcommands.add_parser("inventory")
    inventory.add_argument("--release-json", type=Path, required=True)
    inventory.add_argument("--version", required=True)
    inventory.add_argument("--source-revision", required=True)
    assets = subcommands.add_parser("validate-assets")
    assets.add_argument("--release-json", type=Path, required=True)
    assets.add_argument("--asset-root", type=Path, required=True)
    assets.add_argument("--version", required=True)
    assets.add_argument("--source-revision", required=True)
    same = subcommands.add_parser("same-release")
    same.add_argument("--expected-release-json", type=Path, required=True)
    same.add_argument("--current-release-json", type=Path, required=True)
    same.add_argument("--version", required=True)
    same.add_argument("--source-revision", required=True)
    followup = subcommands.add_parser("validate-followup")
    followup.add_argument("--published", type=Path, required=True)
    followup.add_argument("--pending", type=Path)
    followup.add_argument("--complete", type=Path)
    followup.add_argument("--original-run-id", required=True)
    followup.add_argument("--release-json", type=Path, required=True)
    publication = subcommands.add_parser("validate-publication")
    publication.add_argument("--qualified", type=Path, required=True)
    publication.add_argument("--publication", type=Path, required=True)
    publication.add_argument("--original-run-id", required=True)
    publication.add_argument("--controller-source", required=True)
    publication.add_argument("--reconciliation-run-id", required=True)
    publication.add_argument("--release-json", type=Path, required=True)
    controller = subcommands.add_parser("validate-controller-run")
    controller.add_argument("--run-json", type=Path, required=True)
    controller.add_argument("--controller-source", required=True)
    controller.add_argument("--reconciliation-run-id", required=True)
    hydrate = subcommands.add_parser("hydrate")
    hydrate.add_argument("--evidence-root", type=Path, required=True)
    hydrate.add_argument("--operation-id", required=True)
    hydrate.add_argument("--receipt", type=Path, required=True)
    complete = subcommands.add_parser("completion-evidence")
    complete.add_argument("--version", required=True)
    complete.add_argument("--original-run-id", required=True)
    complete.add_argument("--controller-source", required=True)
    complete.add_argument("--reconciliation-run-id", required=True)
    complete.add_argument("--source-revision", required=True)
    complete.add_argument("--release-json", type=Path, required=True)
    pending = subcommands.add_parser("cleanup-pending-evidence")
    pending.add_argument("--original-run-id", required=True)
    pending.add_argument("--controller-source", required=True)
    pending.add_argument("--reconciliation-run-id", required=True)
    pending.add_argument("--version", required=True)
    pending.add_argument("--source-revision", required=True)
    pending.add_argument("--release-json", type=Path, required=True)
    pending.add_argument("--failed-target", action="append", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "validate":
        result = validate_reconciliation(
            run_document=_load_json(args.run_json),
            qualified_action=args.qualified_action.read_bytes(),
            qualified_release=args.qualified_release.read_bytes(),
            hashes=args.hashes,
            wheel=args.wheel,
            sdist=args.sdist,
            version=args.version,
            source_revision=args.source_revision,
            original_run_id=args.original_run_id,
            controller_source=args.controller_source,
            reconciliation_run_id=args.reconciliation_run_id,
            release_document=_load_json(args.release_json),
        )
    elif args.command == "inventory":
        result = validate_release_inventory(
            _load_json(args.release_json), version=args.version, source_revision=args.source_revision,
        )
    elif args.command == "validate-assets":
        result = validate_release_assets(
            _load_json(args.release_json), args.asset_root,
            version=args.version, source_revision=args.source_revision,
        )
    elif args.command == "same-release":
        result = validate_same_release(
            _load_json(args.expected_release_json), _load_json(args.current_release_json),
            version=args.version, source_revision=args.source_revision,
        )
    elif args.command == "validate-followup":
        try:
            published = ReleaseOperation.parse(_load_json(args.published))
        except ReleaseOperationError as error:
            raise ExistingReleaseReconciliationError("published follow-up receipt is invalid") from error
        release = validate_release_inventory(
            _load_json(args.release_json), version=published.version,
            source_revision=published.source_revision,
        )["release"]
        result = validate_followup_receipts(
            published_path=args.published, pending_path=args.pending, complete_path=args.complete,
            original_run_id=args.original_run_id, release_identity=release,  # type: ignore[arg-type]
        )
    elif args.command == "validate-publication":
        try:
            qualified = ReleaseOperation.parse(_load_json(args.qualified))
        except ReleaseOperationError as error:
            raise ExistingReleaseReconciliationError("qualified operation receipt is invalid") from error
        release = validate_release_inventory(
            _load_json(args.release_json), version=qualified.version,
            source_revision=qualified.source_revision,
        )["release"]
        result = validate_new_publication_evidence(
            qualified_path=args.qualified, publication_path=args.publication,
            original_run_id=args.original_run_id, release_identity=release,  # type: ignore[arg-type]
            controller_source=args.controller_source,
            reconciliation_run_id=args.reconciliation_run_id,
        )
    elif args.command == "validate-controller-run":
        result = validate_controller_run(
            _load_json(args.run_json), run_id=args.reconciliation_run_id,
            controller_source=args.controller_source,
        )
    elif args.command == "hydrate":
        result = asdict(hydrate_followup_receipt(args.evidence_root, args.operation_id, args.receipt))
    elif args.command == "completion-evidence":
        result = completion_evidence(
            version=args.version,
            original_run_id=args.original_run_id,
            controller_source=args.controller_source,
            reconciliation_run_id=args.reconciliation_run_id,
            source_revision=args.source_revision,
            release_identity=validate_release_inventory(
                _load_json(args.release_json), version=args.version,
                source_revision=args.source_revision,
            )["release"],  # type: ignore[arg-type]
        )
    else:
        result = cleanup_pending_evidence(
            original_run_id=args.original_run_id,
            controller_source=args.controller_source,
            reconciliation_run_id=args.reconciliation_run_id,
            source_revision=args.source_revision,
            release_identity=validate_release_inventory(
                _load_json(args.release_json), version=args.version,
                source_revision=args.source_revision,
            )["release"],  # type: ignore[arg-type]
            failed_targets=args.failed_target,
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExistingReleaseReconciliationError as error:
        raise SystemExit(f"EXISTING_RELEASE_RECONCILIATION_ERROR: {error}") from error
