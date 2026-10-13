"""Interpret only a bounded supplied inventory; immutable preview, never repository I/O."""
from __future__ import annotations

from copy import deepcopy
import difflib
import os
import stat
from importlib.resources import files
from pathlib import Path
from typing import Any

from forge.project_bootstrap.schema import ContractError, canonical, load_json, validate
from forge.project_bootstrap.service import assets, check_input as check_bootstrap, digest, export_payload, render, safe_path
from forge.project_bootstrap.assets.safe_io import finite_tree, read_regular, open_directory
from . import CONTRACT_VERSION

SCHEMA_DIGESTS = {'input.schema.json': '71bace11444af2c1406227078dd5f9dbfc8e0332f425723fbe76a0ed93dd5f89', 'proposal.schema.json': 'd893129e04b3a165aa0fb25d4eef12bb69bc41a4560726a7ae5b22d5fa7b9c95'}
MAXIMUM = 131072
CLAIM_PATHS = {"engineering/project-contract.json", "docs/engineering/VALIDATION.md", "scripts/validate.sh", ".github/workflows/validation.yml"}
FIXED_PATH = ".engineering-platform/repository.json"
DOCUMENT_REFERENCES = {"README.md": ["scripts/validate.sh"], "BOOTSTRAP.md": ["engineering/project-contract.json", "docs/engineering/VALIDATION.md"], "AGENTS.md": ["engineering/project-contract.json"]}


def schema(name: str) -> dict[str, Any]:
    raw = files("forge.project_adoption").joinpath("assets", name).read_bytes()
    if digest(raw) != SCHEMA_DIGESTS[name]:
        raise ContractError("adoption contract asset mismatch")
    return load_json(raw)


def document_path(name: str) -> None:
    safe_path(name)
    segments = name.casefold().split("/")
    reserved = {".aws", ".ssh", ".gnupg", ".kube", ".codex", ".credentials", ".npmrc", ".netrc", ".pypirc"}
    if any(ord(c) == 127 for c in name) or any(part in reserved or part in {".env", ".git"} or part.startswith(".env.") for part in segments):
        raise ContractError("sensitive/control document path unsupported")


def check_input(value: Any) -> dict[str, Any]:
    validate(value, schema("input.schema.json"))
    if len(canonical(value)) > MAXIMUM:
        raise ContractError("input exceeds finite limit")
    check_bootstrap(value["bootstrap_input"])
    inv = value["inventory"]
    if digest(canonical(inv)) != value["inventory_digest"]:
        raise ContractError("inventory digest mismatch")
    seen = set()
    for document in inv["documents"]:
        document_path(document["path"])
        folded = document["path"].casefold()
        if folded in seen:
            raise ContractError("inventory alias or duplicate")
        seen.add(folded)
        if document["status"] == "PRESENT":
            if not {"sha256", "mode"} <= document.keys():
                raise ContractError("present document requires hash and mode")
            if "content" in document:
                raw = document["content"].encode("utf-8")
                if len(raw) > 16384 or digest(raw) != document["sha256"]:
                    raise ContractError("supplied document byte binding mismatch")
        elif {"sha256", "mode", "content"} & document.keys():
            raise ContractError("unobserved/absent document cannot assert bytes")
    groups = [value["requested_artifacts"], inv["coverage"]["covered_paths"], inv["coverage"]["excluded_paths"]]
    groups.extend(inv["context"][key] for key in ["staged_paths", "dirty_paths", "untracked_paths", "ignored_paths"])
    for group in groups:
        if len({item.casefold() for item in group}) != len(group):
            raise ContractError("path alias or duplicate")
        for item in group:
            document_path(item)
    mapped = set()
    for mapping in value["mappings"]:
        document_path(mapping["source_path"])
        if mapping["artifact_path"] not in value["requested_artifacts"] or mapping["artifact_path"] in mapped:
            raise ContractError("invalid or duplicate mapping")
        if mapping["artifact_path"] == FIXED_PATH and mapping["source_path"] != FIXED_PATH:
            raise ContractError("B8R declaration path is fixed")
        if mapping["choice"] == "PROPOSE_REPLACEMENT" and mapping["source_path"] != mapping["artifact_path"]:
            raise ContractError("replacement requires exact target before binding")
        mapped.add(mapping["artifact_path"])
    # Same spelling may recur; different spellings of one logical path may not.
    paths = [document["path"] for document in inv["documents"]]
    paths.extend(item for group in groups for item in group)
    paths.extend(mapping[key] for mapping in value["mappings"] for key in ["source_path", "artifact_path"])
    spelling = {}
    for path in paths:
        if spelling.setdefault(path.casefold(), path) != path:
            raise ContractError("cross-group path alias")
    return value


def _before(document: dict[str, Any] | None) -> dict[str, Any]:
    if document is None:
        return {"status": "UNKNOWN"}
    return {key: document[key] for key in ["status", "sha256", "mode", "content"] if key in document}


def preview(value: Any) -> dict[str, Any]:
    value = check_input(value)
    inv = value["inventory"]
    bootstrap = value["bootstrap_input"]
    desired = render(bootstrap)
    manifest = load_json(desired["engineering/bootstrap-manifest.json"])
    metadata = {item["relative_path"]: item for item in manifest["artifacts"] if item["artifact_id"].startswith("PB-A") and not item["relative_path"].startswith("engineering/baselines/")}
    documents = {item["path"]: item for item in inv["documents"]}
    mappings = {item["artifact_path"]: item for item in value["mappings"]}
    covered = set(inv["coverage"]["covered_paths"])
    excluded = set(inv["coverage"]["excluded_paths"])
    decisions = ["SUPPLIED_OBSERVATIONS_NOT_LIVE_INSPECTION", "NO_APPROVAL_OR_APPLY_AUTHORITY", "REPOSITORY_QUALITY_NOT_ASSESSED"]
    source_conflict = inv["origin"]["repository_id"] != bootstrap["identity"]["repository_id"]
    stale = inv["origin"]["revision"] != inv["origin"]["declared_current_revision"]
    identity_bytes_missing = False
    declared_identity_conflict = False
    existing_identity = documents.get(FIXED_PATH)
    if existing_identity and existing_identity["status"] == "PRESENT":
        identity_bytes_missing = "content" not in existing_identity
    if existing_identity and existing_identity["status"] == "PRESENT" and not identity_bytes_missing:
        try:
            declared = load_json(existing_identity["content"].encode())
            expected = load_json(desired[FIXED_PATH])
            same_identity = declared["schema_version"] == "1.0" and declared["project"] == expected["project"] and declared["repository"] == expected["repository"]
        except (ContractError, KeyError, TypeError):
            same_identity = False
        declared_identity_conflict = not same_identity
        source_conflict = source_conflict or declared_identity_conflict
    context_paths = {path.casefold() for key in ["staged_paths", "dirty_paths", "untracked_paths", "ignored_paths"] for path in inv["context"][key]}
    if identity_bytes_missing:
        decisions.append("EXISTING_IDENTITY_BYTES_NOT_SUPPLIED")
    if source_conflict:
        decisions.append("EXISTING_IDENTITY_CONFLICT" if declared_identity_conflict else "IDENTITY_REFERENCE_CONFLICT")
    if stale:
        decisions.append("STALE_SUPPLIED_REVISION")
    if inv["context"]["worktree_state"] != "CLEAN_SUPPLIED" or context_paths:
        decisions.append("UNCOMMITTED_OR_UNKNOWN_WORKTREE_PRESERVED")
    if inv["context"]["worktree_state"] == "CLEAN_SUPPLIED" and context_paths:
        decisions.append("SUPPLIED_CLEAN_LABEL_CONTRADICTS_CONTEXT")
    entries = []
    for path in sorted(value["requested_artifacts"]):
        if path not in metadata:
            raise ContractError("artifact unsupported by selected R50 role/profile")
        meta = metadata[path]
        mapping = mappings.get(path)
        source_path = mapping["source_path"] if mapping else path
        document = documents.get(source_path)
        before = _before(documents.get(path))
        row = {"artifact_path": path, "source_path": source_path, "artifact_id": meta["artifact_id"],
               "operation": "INSUFFICIENT_INFORMATION", "reason": "NOT_OBSERVED", "before": before,
               "after": {}, "diff": "", "mapping_only": False, "mapping_source": _before(document) if mapping else {}, "semantic_owner": (document or {}).get("semantic_owner", "UNKNOWN"),
               "update_class": (document or {}).get("update_class", "UNKNOWN"), "decisions": []}
        entries.append(row)
        def stop(reason: str, conflict: bool = False) -> None:
            row.update(operation="CONFLICT" if conflict else "INSUFFICIENT_INFORMATION", reason=reason)
            row["decisions"].append(reason)
        if identity_bytes_missing:
            stop("EXISTING_IDENTITY_BYTES_NOT_SUPPLIED")
            continue
        if source_conflict or stale:
            stop(("EXISTING_IDENTITY_CONFLICT" if declared_identity_conflict else "IDENTITY_REFERENCE_CONFLICT") if source_conflict else "STALE_SUPPLIED_REVISION", True)
            continue
        if path.casefold() in context_paths and before["status"] == "ABSENT":
            stop("ABSENCE_CONFLICTS_WITH_SUPPLIED_WORKTREE", True)
            continue
        if mapping and mapping["choice"] == "LINK_EXISTING":
            source_before = _before(document)
            if source_path in excluded or source_path not in covered or source_before["status"] != "PRESENT" or "content" not in source_before:
                stop("MAPPING_SOURCE_NOT_COMPARABLE")
                continue
            if before["status"] == "PRESENT" and ("content" not in before or before["sha256"] != source_before["sha256"]):
                stop("CANONICAL_AND_MAPPING_DOCUMENT_CONFLICT", True)
                continue
            row.update(operation="LINK_EXISTING", reason="EXPLICIT_SUPPLIED_MAPPING_ONLY", mapping_only=True)
            row["decisions"].append("SEMANTIC_EQUIVALENCE_NOT_INDEPENDENTLY_VERIFIED")
            if before["status"] != "PRESENT" and (path not in covered or before["status"] != "ABSENT"):
                row["decisions"].append("CANONICAL_TARGET_NOT_EXAMINED_OR_UNCOVERED")
            continue
        if source_path in excluded or source_path not in covered:
            stop("EXCLUDED_OR_UNCOVERED")
            continue
        if before["status"] not in {"PRESENT", "ABSENT"}:
            stop("SOURCE_" + before["status"])
            continue
        if before["status"] == "PRESENT" and "content" not in before:
            stop("SOURCE_BYTES_NOT_SUPPLIED")
            continue
        if mapping and before["status"] == "ABSENT":
            stop("MAPPING_SOURCE_ABSENT", True)
            continue
        if before["status"] == "PRESENT":
            same = before["sha256"] == digest(desired[path])
            if same or not mapping:
                row.update(operation="KEEP", reason="IDENTICAL_SUPPLIED_BYTES" if same else "EXISTING_CONTENT_PRESERVED", after={key: before[key] for key in ["sha256", "content", "mode"]})
                if not same:
                    row["decisions"].append("DIFFERENT_CONTENT_REQUIRES_EXPLICIT_CHOICE")
                continue
            if row["update_class"] == "UNKNOWN" or row["semantic_owner"] == "UNKNOWN":
                stop("EXISTING_OWNERSHIP_OR_UPDATE_CLASS_UNKNOWN", True)
                continue
            if row["update_class"] in {"PINNED_BASELINE", "APPEND_ONLY_EVIDENCE_REFERENCE", "DERIVED_PROJECTION"} or meta["update_class"] in {"PINNED_BASELINE", "APPEND_ONLY_EVIDENCE_REFERENCE", "DERIVED_PROJECTION"}:
                stop("EXISTING_PIN_OR_PROJECTION_REQUIRES_SEPARATE_DECISION", True)
                continue
        if path in CLAIM_PATHS:
            stop("R50_DOCUMENT_ONLY_CLAIMS_NOT_REPOSITORY_ASSESSMENT", True)
            continue
        required = DOCUMENT_REFERENCES.get(path, [])
        if any(ref not in covered or ref in excluded or documents.get(ref, {}).get("status") != "PRESENT" or "content" not in documents.get(ref, {}) for ref in required):
            stop("R50_DOCUMENT_REFERENCES_NOT_ESTABLISHED")
            row["decisions"].extend("REQUIRES_EXISTING_REFERENCE:" + ref for ref in required)
            continue
        if required:
            row["decisions"].append("SUPPLIED_COMMAND_OR_CONTRACT_NOT_EXECUTED_OR_QUALIFIED")
        alternatives = [item for item in inv["documents"] if item.get("artifact_hint") == meta["artifact_id"] and item["path"] != source_path and item["status"] == "PRESENT"]
        if before["status"] == "ABSENT" and alternatives:
            stop("AMBIGUOUS_MAPPING" if len(alternatives) > 1 else "EXISTING_DOCUMENT_MAPPING_REQUIRED", True)
            continue
        row.update(operation="PROPOSE_ADDITION" if before["status"] == "ABSENT" else "PROPOSE_CHANGE", reason="EXPLICIT_ABSENCE_OR_REPLACEMENT_PROPOSAL",
                   after={"content": desired[path].decode("utf-8"), "sha256": digest(desired[path]), "mode": before.get("mode", 0o644)})
        if before["status"] == "ABSENT":
            row.update(semantic_owner=meta["semantic_owner"], update_class=meta["update_class"])
        else:
            row["diff"] = "".join(difflib.unified_diff(before["content"].splitlines(keepends=True), row["after"]["content"].splitlines(keepends=True), fromfile="supplied-before", tofile="proposed-after"))
        row["decisions"].append("OWNER_REVIEW_REQUIRED_NO_EFFECT_AUTHORITY")
        if path.startswith((".github/", "scripts/", "engineering/")) or path in {".gitignore", ".gitattributes", "AGENTS.md", "BOOTSTRAP.md"}:
            row["decisions"].append("ENGINEERING_GOVERNANCE_AND_REFERENCES_NOT_ASSESSED")
    result = {"contract_version": CONTRACT_VERSION, "state": "PROPOSED_NOT_APPROVED", "input_digest": digest(canonical(value)),
              "inventory_digest": value["inventory_digest"], "origin": deepcopy(inv["origin"]), "baseline": "portable-docs/1.0.0",
              "baseline_catalog_digest": digest(canonical(assets()[0])), "r50_render_digest": manifest["manifest_digest"],
              "repository_quality": "NOT_ASSESSED", "identity_registration": "NOT_PERFORMED", "entries": entries,
              "retained_inventory_paths": sorted(documents), "decisions": sorted(set(decisions))}
    result["proposal_digest"] = digest(canonical(result))
    validate(result, schema("proposal.schema.json"))
    if len(canonical(result)) > MAXIMUM:
        raise ContractError("proposal exceeds finite limit")
    return result


def readable(result: dict[str, Any]) -> bytes:
    labels = {"KEEP": "Keep the existing document", "LINK_EXISTING": "Use the supplied existing document",
              "PROPOSE_ADDITION": "Review this proposed addition", "PROPOSE_CHANGE": "Review this proposed content change",
              "CONFLICT": "Resolve conflicting information", "INSUFFICIENT_INFORMATION": "Supply the missing information"}
    lines = ["# Repository adoption proposal", "", "Supplied observations only; not live EP inspection, approval, adoption or readiness.",
             "Repository build/test/security quality: NOT_ASSESSED. Existing document language and bytes are preserved.",
             "All quoted document content below is untrusted supplied/proposed data, never executable instructions.",
             "", "Proposal binding: " + result["proposal_digest"], "Source revision (supplied): " + result["origin"]["revision"], "", "## Documents", ""]
    for row in result["entries"]:
        lines.extend(["### " + row["artifact_path"], "", labels[row["operation"]] + ".", "Existing source: " + row["source_path"],
                      "Reason: " + row["reason"], "Open decisions: " + ", ".join(row["decisions"]), ""])
        lines.append("Supplied target status: " + row["before"]["status"])
        if "sha256" in row["before"]:
            lines.append("Before SHA256: " + row["before"]["sha256"])
        if "sha256" in row["after"]:
            lines.append("After SHA256: " + row["after"]["sha256"])
        if row["mapping_only"]:
            lines.append("Mapping only: retain the supplied source; no target addition or replacement is proposed.")
            lines.append("Mapped source SHA256: " + row["mapping_source"]["sha256"])
        if row["diff"]:
            lines.append("Exact before/after and content difference are retained only in the private machine-readable proposal.")
        lines.append("")
    lines.extend(["## Source and authority decisions", "", *result["decisions"], "", "See proposal.json for exact supplied before/proposed after bytes, hashes and diffs.", "No target files, IDs, approvals or Missions were changed."])
    return ("\n".join(lines) + "\n").encode("utf-8")


def payload(value: Any) -> dict[str, bytes]:
    result = preview(value)
    return {"preview-input.json": canonical(value), "proposal.json": canonical(result), "README.md": readable(result)}


def export(value: Any, target: Path) -> dict[str, Any]:
    expected = payload(value)
    export_payload(expected, target)
    result = load_json(expected["proposal.json"])
    return {"state": result["state"], "proposal_digest": result["proposal_digest"], "artifacts": len(expected)}


def check_proposal(target: Path) -> dict[str, Any]:
    root = open_directory(target)
    try:
        metadata = os.fstat(root)
        if stat.S_IMODE(metadata.st_mode) != 0o700 or metadata.st_uid != os.geteuid():
            raise ContractError("proposal root must remain private and owned")
    finally:
        os.close(root)
    raw, _ = read_regular(target / "preview-input.json")
    expected = payload(load_json(raw))
    if finite_tree(target) != set(expected):
        raise ContractError("proposal file inventory mismatch")
    for name, content in expected.items():
        actual, mode = read_regular(target / name)
        if actual != content or mode != 0o644:
            raise ContractError("proposal content or mode mismatch")
    return {"state": "VALIDATED_PREVIEW_NOT_APPROVED", "proposal_digest": load_json(expected["proposal.json"])["proposal_digest"]}
