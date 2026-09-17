"""Forge-owned, fail-closed operational-history reset service.

The service owns one deliberately narrow profile.  It never accepts a caller
supplied table list and never reaches Engineering Platform storage.  Preview is
strictly read-only; every mutation after it is bound to the same target, plan,
operator authority, backup, and durable operation identity.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import uuid
from typing import Any, Callable, Iterator, Mapping, Sequence

from forge._version import canonical_version
from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter, NamedOperatorIdentity

from .data_root import DataRootResolver
from .database import RUNTIME_SCHEMA_VERSION
from .service import RuntimeServiceLock


RESET_PROFILE = "forge-operational-history-v1"
RESET_POLICY_VERSION = "1"
_OPERATION_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{7,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class OperationalResetError(RuntimeError):
    """The requested maintenance operation cannot preserve the reset contract."""


# Explicit schema-owned classification.  Adding a product table without adding
# it here makes preview fail closed as UNKNOWN_OR_UNSUPPORTED.
TABLE_CLASSIFICATION: Mapping[str, str] = {
    # A — durable installation, binding, and provider configuration.
    "runtime_metadata": "INSTALLATION_AND_CONFIGURATION",
    "execution_host_peer_configuration": "INSTALLATION_AND_CONFIGURATION",
    "planning_provider_security_config": "INSTALLATION_AND_CONFIGURATION",
    "planning_provider_external_session_config": "INSTALLATION_AND_CONFIGURATION",
    # B — authority, anti-replay, allocation, and consumed-budget lineage.
    "installation_operator_binding": "SECURITY_AND_AUTHORITY_LEDGER",
    "installation_operator_audit": "SECURITY_AND_AUTHORITY_LEDGER",
    "governance_authority": "SECURITY_AND_AUTHORITY_LEDGER",
    "governance_capability_grants": "SECURITY_AND_AUTHORITY_LEDGER",
    "governance_decisions": "SECURITY_AND_AUTHORITY_LEDGER",
    "planning_provider_security_audit": "SECURITY_AND_AUTHORITY_LEDGER",
    "planning_provider_external_session_audit": "SECURITY_AND_AUTHORITY_LEDGER",
    "planning_provider_generation_permits": "SECURITY_AND_AUTHORITY_LEDGER",
    "mission_id_allocations": "SECURITY_AND_AUTHORITY_LEDGER",
    # C — old planning/execution history removed from the active generation.
    "mission_state": "OPERATIONAL_HISTORY",
    "execution_context_snapshots": "OPERATIONAL_HISTORY",
    "architecture_reviews": "OPERATIONAL_HISTORY",
    "mission_recommendations": "OPERATIONAL_HISTORY",
    "decision_evidence": "OPERATIONAL_HISTORY",
    "execution_receipts": "OPERATIONAL_HISTORY",
    "bootstrap_portfolio_state": "OPERATIONAL_HISTORY",
    "mission_lifecycle_events": "OPERATIONAL_HISTORY",
    "delegation_requests": "OPERATIONAL_HISTORY",
    "integration_evidence": "OPERATIONAL_HISTORY",
    "mission_intake_evidence": "OPERATIONAL_HISTORY",
    "scheduler_submissions": "OPERATIONAL_HISTORY",
    "token_preflight_receipts": "OPERATIONAL_HISTORY",
    "token_preflight_receipt_consumptions": "OPERATIONAL_HISTORY",
    "token_preflight_failures": "OPERATIONAL_HISTORY",
    "action_derivations": "OPERATIONAL_HISTORY",
    "action_derivation_results": "OPERATIONAL_HISTORY",
    "action_derivation_reattempt_authorizations": "OPERATIONAL_HISTORY",
    "action_derivation_reattempt_consumptions": "OPERATIONAL_HISTORY",
    "action_derivation_evidence_sets": "OPERATIONAL_HISTORY",
    "action_derivation_canary_closures": "OPERATIONAL_HISTORY",
    "mission_amendments": "OPERATIONAL_HISTORY",
    "execution_host_bindings": "OPERATIONAL_HISTORY",
    "execution_host_exchange_audit": "OPERATIONAL_HISTORY",
    "forge_operational_logs": "OPERATIONAL_HISTORY",
    # D — mutable projections/queues, never durable authority.
    "mission_runtime_projections": "DERIVED_CACHE_OR_PROJECTION",
    "planning_state": "DERIVED_CACHE_OR_PROJECTION",
    "dispatcher_state": "DERIVED_CACHE_OR_PROJECTION",
    # E — the reset's own durable reconciliation and anti-replay evidence.
    "operational_reset_state": "MAINTENANCE_AUDIT",
    "operational_reset_operations": "MAINTENANCE_AUDIT",
    "operational_reset_audit": "MAINTENANCE_AUDIT",
    "operational_reset_tombstones": "MAINTENANCE_AUDIT",
    "operational_reset_artifact_steps": "MAINTENANCE_AUDIT",
}

PRESERVE_TABLES = tuple(
    table for table, category in TABLE_CLASSIFICATION.items()
    if category in {"INSTALLATION_AND_CONFIGURATION", "SECURITY_AND_AUTHORITY_LEDGER"}
)
PURGE_TABLES = tuple(
    table for table, category in TABLE_CLASSIFICATION.items()
    if category in {"OPERATIONAL_HISTORY", "DERIVED_CACHE_OR_PROJECTION"}
)
MAINTENANCE_TABLES = tuple(
    table for table, category in TABLE_CLASSIFICATION.items() if category == "MAINTENANCE_AUDIT"
)

# Child-first order is part of the product contract and mirrors schema FKs.
PURGE_ORDER = (
    "action_derivation_canary_closures",
    "action_derivation_results",
    "action_derivation_reattempt_consumptions",
    "action_derivation_reattempt_authorizations",
    "action_derivation_evidence_sets",
    "mission_amendments",
    "token_preflight_receipt_consumptions",
    "token_preflight_receipts",
    "token_preflight_failures",
    "decision_evidence",
    "integration_evidence",
    "mission_intake_evidence",
    "mission_runtime_projections",
    "execution_context_snapshots",
    "action_derivations",
    "scheduler_submissions",
    "delegation_requests",
    "execution_receipts",
    "mission_recommendations",
    "architecture_reviews",
    "mission_lifecycle_events",
    "execution_host_exchange_audit",
    "execution_host_bindings",
    "forge_operational_logs",
    "planning_state",
    "dispatcher_state",
    "bootstrap_portfolio_state",
    "mission_state",
)

EXTERNAL_CLASSIFICATION: Mapping[str, str] = {
    "instance": "INSTALLATION_AND_CONFIGURATION",
    "artifacts": "OPERATIONAL_HISTORY",
    "journals": "OPERATIONAL_HISTORY",
    "logs": "OPERATIONAL_HISTORY",
    "backups": "INSTALLATION_AND_CONFIGURATION",
    "cache": "DERIVED_CACHE_OR_PROJECTION",
    "locks": "SYSTEM_RUNTIME_CONTROL",
}

_IMMUTABLE_DELETE_TRIGGERS: Mapping[str, tuple[str, ...]] = {
    "execution_context_snapshots": ("execution_context_snapshots_immutable_delete",),
    "action_derivation_canary_closures": ("action_derivation_canary_closures_immutable_delete",),
    "action_derivation_results": ("action_derivation_results_immutable_delete",),
    "action_derivation_reattempt_authorizations": ("action_derivation_reattempt_authorizations_immutable_delete",),
    "action_derivation_reattempt_consumptions": ("action_derivation_reattempt_consumptions_immutable_delete",),
    "action_derivations": ("action_derivations_failed_immutable_delete",),
    "architecture_reviews": ("architecture_reviews_immutable_delete",),
    "decision_evidence": ("decision_evidence_immutable_delete",),
    "execution_host_exchange_audit": ("execution_host_exchange_audit_immutable_delete",),
    "execution_receipts": ("execution_receipts_immutable_delete",),
    "forge_operational_logs": ("forge_operational_logs_immutable_delete",),
    "integration_evidence": ("integration_evidence_immutable_delete",),
    "mission_intake_evidence": ("mission_intake_evidence_immutable_delete",),
    "mission_lifecycle_events": ("mission_lifecycle_events_immutable_delete",),
    "mission_recommendations": ("mission_recommendations_immutable_delete",),
    "token_preflight_failures": ("token_preflight_failures_immutable_delete",),
    "token_preflight_receipts": ("token_preflight_receipts_immutable_delete",),
    "token_preflight_receipt_consumptions": ("token_preflight_receipt_consumptions_immutable_delete",),
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    encoded = value if isinstance(value, bytes) else _json(value).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def _file_digest(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return "sha256:" + hasher.hexdigest()


def _safe_operation_id(value: str) -> str:
    if not isinstance(value, str) or _OPERATION_ID.fullmatch(value) is None:
        raise OperationalResetError("operation ID must be 8-128 safe identifier characters")
    return value


def _has_symlink_component(path: Path) -> bool:
    """Inspect the lexical path before ``resolve`` can hide a symlink.

    Missing components are safe to inspect and return ``False``.  Each
    existing parent is still checked, so ``alias/nonexistent-child`` cannot
    escape this guard merely because the leaf does not exist yet.
    """
    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for part in lexical.parts[1:]:
        current /= part
        if current.is_symlink():
            # macOS exposes root-owned compatibility aliases such as
            # /var -> /private/var.  They are immutable to an unprivileged
            # operator and precede the selected data hierarchy; accepting
            # them avoids rejecting the OS temporary-directory topology.
            if (
                current.parent == Path(current.anchor)
                and getattr(current.lstat(), "st_uid", -1) == 0
            ):
                continue
            return True
    return False


class ForgeOperationalResetService:
    """Application service for one local Forge operational-history reset."""

    def __init__(
        self,
        data_root: Path | str | None,
        *,
        identity_resolver: Callable[[], NamedOperatorIdentity] | None = None,
        disk_usage: Callable[[Path], Any] = shutil.disk_usage,
        fault_hook: Callable[[str, str | None], None] | None = None,
    ) -> None:
        self._requested_root = None if data_root is None else Path(data_root).expanduser()
        self._requested_root_is_symlink = bool(
            self._requested_root is not None and _has_symlink_component(self._requested_root)
        )
        candidate = DataRootResolver(cli_data_root=data_root).resolve()
        self.data_root = candidate
        self.database_path = candidate / "forge.db"
        self.marker_path = candidate / "instance" / "runtime-instance.json"
        self._identity_resolver = identity_resolver or MacOSGeneratedUIDIdentityAdapter().resolve
        self._disk_usage = disk_usage
        self._fault_hook = fault_hook or (lambda _event, _path=None: None)
        self._lock = RuntimeServiceLock(self.database_path)

    def _implementation_digest(self) -> str:
        service_bytes = Path(__file__).read_bytes()
        return _digest(service_bytes + canonical_version().encode("utf-8"))

    def _source_revision(self) -> str:
        """Return a real Git revision when this module is in tracked source.

        Installed wheels do not currently embed the protected-main SHA.  That
        absence is reported honestly; the independent implementation digest
        still binds the exact maintenance code used by this operation.
        """
        try:
            root = Path(subprocess.check_output(
                ("git", "-C", str(Path(__file__).parent), "rev-parse", "--show-toplevel"),
                text=True, stderr=subprocess.DEVNULL,
            ).strip()).resolve()
            relative = Path(__file__).resolve().relative_to(root).as_posix()
            subprocess.run(
                ("git", "-C", str(root), "ls-files", "--error-unmatch", relative),
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            revision = subprocess.check_output(
                ("git", "-C", str(root), "rev-parse", "HEAD"), text=True, stderr=subprocess.DEVNULL,
            ).strip()
            if re.fullmatch(r"[0-9a-f]{40}", revision):
                return revision
        except (OSError, ValueError, subprocess.CalledProcessError):
            pass
        return "UNAVAILABLE_IN_INSTALLED_PACKAGE"

    def _require_target_paths(self) -> None:
        if self._requested_root_is_symlink or not self.data_root.is_dir() or self.data_root.is_symlink():
            raise OperationalResetError("Forge data root must be a real directory, not a symlink")
        if not self.database_path.is_file() or self.database_path.is_symlink():
            raise OperationalResetError("Forge database must be a real file, not a symlink")
        if not self.marker_path.is_file() or self.marker_path.is_symlink():
            raise OperationalResetError("Forge runtime marker must be a real file, not a symlink")

    @contextmanager
    def _connect(self, *, read_only: bool) -> Iterator[sqlite3.Connection]:
        self._require_target_paths()
        if read_only:
            connection = sqlite3.connect(self.database_path.resolve().as_uri() + "?mode=ro", uri=True)
        else:
            connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        if read_only:
            connection.execute("PRAGMA query_only=ON")
        else:
            connection.execute("PRAGMA synchronous=FULL")
            connection.create_function("forge_maintenance_write_permitted", 0, lambda: 1)
            # Existing product triggers reference these owning writer functions.
            for name in (
                "forge_governance_write_permitted", "forge_token_preflight_write_permitted",
                "forge_action_derivation_write_permitted", "forge_action_derivation_reattempt_write_permitted",
                "forge_action_derivation_canary_closure_write_permitted",
            ):
                connection.create_function(name, 0, lambda: 0)
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _application_tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    @staticmethod
    def _row_digest(connection: sqlite3.Connection, table: str, *, post_reset: bool = False) -> str:
        columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]
        rows: list[list[Any]] = []
        for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
            values = [row[column] for column in columns]
            if post_reset and table == "planning_provider_generation_permits":
                state_index = columns.index("state")
                updated_index = columns.index("updated_at")
                if values[state_index] in {
                    "PENDING", "TRANSPORT_COMMITTED", "INVALIDATED_BY_OPERATIONAL_RESET",
                }:
                    values[state_index] = "INVALIDATED_BY_OPERATIONAL_RESET"
                    # The timestamp is intentionally normalized out of the
                    # preservation proof; it is separately bound in audit.
                    values[updated_index] = "<reset-time>"
            rows.append(values)
        return _digest({"columns": columns, "rows": rows})

    def _relevant_revision(self, connection: sqlite3.Connection) -> str:
        values: dict[str, str] = {}
        for table in sorted(set(TABLE_CLASSIFICATION) - set(MAINTENANCE_TABLES)):
            if table == "runtime_metadata":
                rows = [
                    [row[0], row[1]] for row in connection.execute(
                        "SELECT key,value FROM runtime_metadata "
                        "WHERE key NOT IN ('last_access_at','integrity_status') ORDER BY key"
                    )
                ]
                values[table] = _digest(rows)
            else:
                values[table] = self._row_digest(connection, table)
        return _digest(values)

    def _external_inventory(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        entries: list[dict[str, Any]] = []
        unknown: list[dict[str, Any]] = []
        recognized_root_files = {"forge.db", "forge.db-wal", "forge.db-shm"}
        recognized_root_controls = {"forge-runtime-mutation.lock"}
        for child in sorted(self.data_root.iterdir(), key=lambda item: item.name):
            relative = child.relative_to(self.data_root).as_posix()
            if child.is_symlink():
                unknown.append({"path": relative, "reason": "SYMLINK"})
                continue
            if child.is_file():
                if child.name in recognized_root_controls:
                    entries.append({
                        "path": relative, "category": "SYSTEM_RUNTIME_CONTROL",
                        "effect": "PRESERVE", "size_bytes": child.stat().st_size,
                    })
                elif child.name not in recognized_root_files:
                    unknown.append({"path": relative, "reason": "UNKNOWN_ROOT_FILE"})
                continue
            if not child.is_dir() or child.name not in EXTERNAL_CLASSIFICATION:
                unknown.append({"path": relative, "reason": "UNKNOWN_ROOT_ENTRY"})
                continue
            category = EXTERNAL_CLASSIFICATION[child.name]
            for current_root, directory_names, file_names in os.walk(child, followlinks=False):
                current = Path(current_root)
                for name in tuple(directory_names):
                    candidate = current / name
                    if candidate.is_symlink():
                        unknown.append({
                            "path": candidate.relative_to(self.data_root).as_posix(), "reason": "SYMLINK",
                        })
                        directory_names.remove(name)
                for name in sorted(file_names):
                    candidate = current / name
                    rel = candidate.relative_to(self.data_root).as_posix()
                    try:
                        mode = candidate.lstat().st_mode
                    except OSError as error:
                        unknown.append({"path": rel, "reason": "UNREADABLE", "error": type(error).__name__})
                        continue
                    if stat.S_ISLNK(mode):
                        unknown.append({"path": rel, "reason": "SYMLINK"})
                    elif not stat.S_ISREG(mode):
                        unknown.append({"path": rel, "reason": "SPECIAL_FILE"})
                    elif child.name == "instance" and rel != "instance/runtime-instance.json":
                        unknown.append({"path": rel, "reason": "UNKNOWN_INSTANCE_FILE"})
                    elif child.name in {"backups", "locks"}:
                        # Existing recovery material and lock files are outside
                        # the effect set but remain inventoried by count only.
                        entries.append({"path": rel, "category": category, "effect": "PRESERVE", "size_bytes": candidate.stat().st_size})
                    elif category == "INSTALLATION_AND_CONFIGURATION":
                        entries.append({
                            "path": rel, "category": category, "effect": "PRESERVE",
                            "size_bytes": candidate.stat().st_size, "digest": _file_digest(candidate),
                        })
                    elif child.name == "artifacts" and (
                        Path(rel).name.startswith("controlled-installation-")
                        or len(Path(rel).parts) > 1 and Path(rel).parts[1] in {"installation", "qualification"}
                    ):
                        entries.append({
                            "path": rel, "category": "INSTALLATION_AND_CONFIGURATION",
                            "effect": "PRESERVE", "size_bytes": candidate.stat().st_size,
                            "digest": _file_digest(candidate),
                        })
                    elif child.name == "artifacts" and not (
                        len(Path(rel).parts) > 1
                        and Path(rel).parts[1] in {"operational", "runtime", "missions"}
                    ):
                        unknown.append({"path": rel, "reason": "UNCLASSIFIED_ARTIFACT"})
                    elif child.name == "journals" and candidate.suffix not in {".json", ".jsonl", ".journal"}:
                        unknown.append({"path": rel, "reason": "UNCLASSIFIED_JOURNAL"})
                    elif child.name == "logs" and candidate.suffix not in {".log", ".jsonl"}:
                        unknown.append({"path": rel, "reason": "UNCLASSIFIED_LOG"})
                    else:
                        entries.append({
                            "path": rel,
                            "category": category,
                            "effect": "ARCHIVE_AND_REMOVE" if category == "OPERATIONAL_HISTORY" else "REMOVE_CACHE",
                            "size_bytes": candidate.stat().st_size,
                            "digest": _file_digest(candidate),
                        })
        return entries, unknown

    @staticmethod
    def _foreign_key_issues(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for row in connection.execute("PRAGMA foreign_key_check"):
            table, rowid, parent, fkid = str(row[0]), row[1], str(row[2]), int(row[3])
            if table in PURGE_TABLES and parent in PURGE_TABLES:
                scope = "OPERATIONAL_PURGE_SET"
            elif table in TABLE_CLASSIFICATION and parent in TABLE_CLASSIFICATION:
                scope = "PRESERVATION_SET"
            else:
                scope = "UNKNOWN_OR_UNSUPPORTED"
            issue = {"table": table, "rowid": rowid, "parent": parent, "foreign_key_id": fkid, "scope": scope}
            issue["issue_id"] = _digest(issue)
            issues.append(issue)
        return issues

    @staticmethod
    def _writer_fence_issues(connection: sqlite3.Connection) -> list[str]:
        issues: list[str] = []
        for table in sorted(TABLE_CLASSIFICATION):
            prefix = "operational_reset_authorize" if table in MAINTENANCE_TABLES else "operational_reset_block"
            for operation in ("insert", "update", "delete"):
                name = f"{prefix}_{table}_{operation}"
                row = connection.execute(
                    "SELECT tbl_name,sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)
                ).fetchone()
                sql = "" if row is None or row[1] is None else " ".join(str(row[1]).lower().split())
                guard = (
                    "forge_maintenance_write_permitted() != 1"
                    if table in MAINTENANCE_TABLES else
                    "active_operation_id from operational_reset_state"
                )
                if row is None or row[0] != table or f"before {operation}" not in sql or guard not in sql:
                    issues.append(name)
        return issues

    def _inventory(self, connection: sqlite3.Connection) -> dict[str, Any]:
        schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        tables = self._application_tables(connection)
        known_for_schema = set(TABLE_CLASSIFICATION)
        if schema == 37:
            known_for_schema -= set(MAINTENANCE_TABLES)
        unknown_tables = sorted(tables - known_for_schema)
        missing_tables = sorted(known_for_schema - tables)
        metadata = dict(connection.execute("SELECT key,value FROM runtime_metadata")) if "runtime_metadata" in tables else {}
        marker = self.marker_path.read_text(encoding="utf-8").strip()
        runtime_id = str(metadata.get("runtime_id", ""))
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign_keys = self._foreign_key_issues(connection)
        table_counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in sorted(tables & known_for_schema)
        }
        classifications = {
            category: [
                {"table": table, "rows": table_counts.get(table, 0)}
                for table, mapped in sorted(TABLE_CLASSIFICATION.items()) if mapped == category and table in tables
            ]
            for category in (
                "INSTALLATION_AND_CONFIGURATION", "SECURITY_AND_AUTHORITY_LEDGER", "OPERATIONAL_HISTORY",
                "DERIVED_CACHE_OR_PROJECTION", "MAINTENANCE_AUDIT",
            )
        }
        external, unknown_external = self._external_inventory()
        generation = 0
        active_operation = None
        if "operational_reset_state" in tables:
            state = connection.execute(
                "SELECT dataset_generation,active_operation_id,state FROM operational_reset_state WHERE singleton=1"
            ).fetchone()
            if state is not None:
                generation, active_operation = int(state[0]), state[1]
        target = {
            "product": "forge", "runtime_id": runtime_id,
            "data_root": str(self.data_root), "database": str(self.database_path),
            "database_binding_digest": _digest(str(self.database_path.resolve())),
            "marker_digest": _file_digest(self.marker_path), "schema_version": schema,
            "dataset_generation": generation,
        }
        blockers: list[dict[str, Any]] = []
        if schema != RUNTIME_SCHEMA_VERSION:
            blockers.append({"code": "SCHEMA_MIGRATION_REQUIRED", "found": schema, "required": RUNTIME_SCHEMA_VERSION})
        if marker != runtime_id or not runtime_id:
            blockers.append({"code": "TARGET_IDENTITY_MISMATCH"})
        if integrity != "ok" or quick != "ok":
            blockers.append({"code": "PHYSICAL_DATABASE_CORRUPTION", "integrity_check": integrity, "quick_check": quick})
        if unknown_tables or missing_tables:
            blockers.append({"code": "UNKNOWN_OR_INCOMPLETE_SCHEMA", "unknown_tables": unknown_tables, "missing_tables": missing_tables})
        fence_issues = self._writer_fence_issues(connection) if schema == RUNTIME_SCHEMA_VERSION else []
        if fence_issues:
            blockers.append({"code": "MAINTENANCE_FENCE_INCOMPLETE", "triggers": fence_issues})
        if unknown_external:
            blockers.append({"code": "UNKNOWN_OR_UNSAFE_EXTERNAL_DATA", "entries": unknown_external})
        non_operational_fk = [item for item in foreign_keys if item["scope"] != "OPERATIONAL_PURGE_SET"]
        if non_operational_fk:
            blockers.append({"code": "FOREIGN_KEY_DAMAGE_OUTSIDE_PURGE_SET", "issues": non_operational_fk})
        operational_fk = [item for item in foreign_keys if item["scope"] == "OPERATIONAL_PURGE_SET"]
        if active_operation:
            blockers.append({"code": "MAINTENANCE_ALREADY_ACTIVE", "operation_id": active_operation})
        relevant_revision = self._relevant_revision(connection) if not unknown_tables and not missing_tables and schema == RUNTIME_SCHEMA_VERSION else None
        preserved = {}
        if schema == RUNTIME_SCHEMA_VERSION and not unknown_tables and not missing_tables:
            preserved = {
                table: {
                    "rows": table_counts[table],
                    "current_digest": self._row_digest(connection, table),
                    "expected_post_reset_digest": self._row_digest(connection, table, post_reset=True),
                }
                for table in PRESERVE_TABLES
            }
        effect_entries = [item for item in external if item.get("effect") in {"ARCHIVE_AND_REMOVE", "REMOVE_CACHE"}]
        external_controls = [
            item for item in external
            if item.get("category") == "SYSTEM_RUNTIME_CONTROL"
            or str(item.get("path", "")).startswith(("locks/", "backups/"))
        ]
        meaningful_external = [item for item in external if item not in external_controls]
        preserved_external = [
            item for item in external
            if item.get("effect") == "PRESERVE"
            and item.get("category") == "INSTALLATION_AND_CONFIGURATION"
            and not str(item.get("path", "")).startswith("backups/")
        ]
        effect_set = {
            "purge_tables": [{"table": table, "rows": table_counts.get(table, 0)} for table in PURGE_TABLES if table in tables],
            "invalidate_active_generation_permits": table_counts.get("planning_provider_generation_permits", 0),
            "external": effect_entries,
        }
        active_permits = (
            int(connection.execute(
                "SELECT COUNT(*) FROM planning_provider_generation_permits "
                "WHERE state IN ('PENDING','TRANSPORT_COMMITTED')"
            ).fetchone()[0]) if "planning_provider_generation_permits" in tables else 0
        )
        effect_set["invalidate_active_generation_permits"] = active_permits
        no_op = (
            sum(item["rows"] for item in effect_set["purge_tables"]) == 0
            and not effect_entries
            and active_permits == 0
        )
        source_revision = self._source_revision()
        plan_core = {
            "contract": "forge-operational-reset-plan-1.0", "profile": RESET_PROFILE,
            "policy_version": RESET_POLICY_VERSION, "product_version": canonical_version(),
            "source_revision": source_revision,
            "source_revision_kind": (
                "GIT_HEAD" if source_revision != "UNAVAILABLE_IN_INSTALLED_PACKAGE"
                else "UNAVAILABLE_IN_INSTALLED_PACKAGE"
            ),
            "implementation_digest": self._implementation_digest(),
            "target": target,
            "relevant_revision": relevant_revision, "classifications": classifications,
            "preserved": preserved, "effect_set": effect_set,
            "effect_set_digest": _digest(effect_set), "foreign_key_issues": foreign_keys,
            "required_fk_acknowledgements": [item["issue_id"] for item in operational_fk],
            "integrity": {"integrity_check": integrity, "quick_check": quick},
            "external_inventory": meaningful_external,
            "external_inventory_digest": _digest(effect_entries),
            "preserved_external": preserved_external,
            "preserved_external_digest": _digest(preserved_external),
            "unknown_external": unknown_external,
            "unknown_tables": unknown_tables, "missing_tables": missing_tables,
            "blockers": blockers, "no_op": no_op,
            "namespace": {
                "repository_document": "missions/MISSION-0003.md",
                "repository_document_kind": "HISTORICAL_REPOSITORY_DOCUMENT",
                "runtime_identity_namespace": "FORGE_RUNTIME_MISSION",
                "allocator_is_reset": False,
            },
        }
        return {
            **plan_core, "plan_digest": _digest(plan_core),
            "external_control_entries": external_controls,
        }

    def preview(self) -> dict[str, Any]:
        """Inspect the exact target without schema migration or domain writes."""
        with self._connect(read_only=True) as connection:
            plan = self._inventory(connection)
        return {
            **plan,
            "status": "BLOCKED" if plan["blockers"] or plan["required_fk_acknowledgements"] else "READY",
            "execution_allowed": not plan["blockers"] and not plan["required_fk_acknowledgements"],
            "summary": "read-only operational reset preview; no Forge operational data changed",
        }

    def _operator_authority(self, connection: sqlite3.Connection) -> tuple[str, str]:
        identity = self._identity_resolver()
        if not isinstance(identity, NamedOperatorIdentity) or not identity.generated_uid:
            raise OperationalResetError("trusted local operator identity is unavailable")
        row = connection.execute(
            "SELECT installation_id,generated_uid,uid,version,status FROM installation_operator_binding"
        ).fetchone()
        if row is None or row[4] != "ACTIVE" or row[1] != identity.generated_uid or int(row[2]) != identity.uid:
            raise OperationalResetError("current operator is not the active installation operator")
        reference = sha256(identity.generated_uid.encode("utf-8")).hexdigest()[:16]
        capabilities = {
            str(item[0]) for item in connection.execute(
                "SELECT capability FROM governance_authority WHERE installation_id=? AND operator_id=?",
                (row[0], reference),
            )
        }
        required = {"SECURITY_APPROVAL", "OWNER_PROGRAMME_AUTHORIZATION"}
        if not required <= capabilities:
            raise OperationalResetError("operational reset requires current Security and programme authority")
        authority = {
            "installation_id": str(row[0]), "operator_reference": reference,
            "binding_version": int(row[3]), "capabilities": sorted(required),
        }
        return reference, _digest(authority)

    @staticmethod
    def _request_digest(operation_id: str, plan: Mapping[str, Any], acknowledgements: Sequence[str]) -> str:
        return _digest({
            "operation_id": operation_id, "profile": RESET_PROFILE,
            "runtime_id": plan["target"]["runtime_id"], "plan_digest": plan["plan_digest"],
            "effect_set_digest": plan["effect_set_digest"],
            "acknowledged_operational_fk_issues": sorted(acknowledgements),
        })

    def _audit(self, connection: sqlite3.Connection, operation_id: str, event: str, details: Mapping[str, Any]) -> None:
        occurred_at = _now()
        document = {"event": event, "operation_id": operation_id, "occurred_at": occurred_at, **details}
        connection.execute(
            "INSERT INTO operational_reset_audit VALUES (?,?,?,?,?)",
            ("forge-reset-audit-" + str(uuid.uuid4()), operation_id, event, occurred_at, _json(document)),
        )

    def prepare(
        self,
        *,
        operation_id: str,
        expected_plan_digest: str,
        acknowledge_operational_fk: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Authorize the exact plan, enter maintenance, and verify its backup."""
        operation_id = _safe_operation_id(operation_id)
        if _DIGEST.fullmatch(expected_plan_digest or "") is None:
            raise OperationalResetError("an exact preview plan digest is required")
        acknowledgements = tuple(sorted(set(acknowledge_operational_fk)))
        with self._lock.acquire():
            with self._connect(read_only=False) as connection:
                if int(connection.execute("PRAGMA user_version").fetchone()[0]) != RUNTIME_SCHEMA_VERSION:
                    raise OperationalResetError("installed schema migration 38 is required before prepare")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT * FROM operational_reset_operations WHERE operation_id=?", (operation_id,)
                    ).fetchone()
                    plan = self._inventory(connection)
                    # Ignore only this operation's durable maintenance-active
                    # blocker when an idempotent prepare is being resumed.
                    active = connection.execute(
                        "SELECT active_operation_id FROM operational_reset_state WHERE singleton=1"
                    ).fetchone()[0]
                    if existing is not None:
                        document = json.loads(existing["document"])
                        request_digest = self._request_digest(operation_id, document["plan"], acknowledgements)
                        if (
                            existing["plan_digest"] != expected_plan_digest
                            or existing["request_digest"] != request_digest
                        ):
                            raise OperationalResetError("operation ID is already bound to a different request")
                        connection.rollback()
                        existing_request = True
                    else:
                        existing_request = False
                    if existing_request:
                        pass
                    elif active is not None:
                        raise OperationalResetError("another operational reset already owns maintenance")
                    elif plan["plan_digest"] != expected_plan_digest:
                        raise OperationalResetError("preview plan changed before maintenance authorization")
                    elif plan["blockers"]:
                        raise OperationalResetError("preview contains blocking findings")
                    required = tuple(sorted(plan["required_fk_acknowledgements"]))
                    if not existing_request and acknowledgements != required:
                        raise OperationalResetError("exact operational foreign-key findings must be acknowledged")
                    if existing_request:
                        continue_prepare = False
                    else:
                        continue_prepare = True
                    if not continue_prepare:
                        # Leave both the SQLite transaction and process lock
                        # before the backup continuation reacquires them.
                        pass
                    else:
                        actor_reference, authority_digest = self._operator_authority(connection)
                        request_digest = self._request_digest(operation_id, plan, acknowledgements)
                        now = _now()
                        document = {
                            "operation_id": operation_id, "state": "PREPARED", "plan": plan,
                            "acknowledged_operational_fk_issues": list(acknowledgements),
                            "request_digest": request_digest, "actor_reference": actor_reference,
                            "authority_digest": authority_digest, "backup": None, "verification": None,
                        }
                        connection.execute(
                        "INSERT INTO operational_reset_operations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                operation_id, plan["target"]["runtime_id"], RESET_PROFILE, "PREPARED",
                                actor_reference, authority_digest, expected_plan_digest, request_digest,
                                None, None, plan["relevant_revision"], plan["source_revision"],
                                plan["implementation_digest"],
                                RUNTIME_SCHEMA_VERSION, RESET_POLICY_VERSION,
                                plan["target"]["dataset_generation"], None, now, now, _json(document),
                            ),
                        )
                        connection.execute(
                            "UPDATE operational_reset_state SET active_operation_id=?,state='PREPARED',updated_at=? WHERE singleton=1",
                            (operation_id, now),
                        )
                        for item in plan["effect_set"]["external"]:
                            connection.execute(
                                "INSERT INTO operational_reset_artifact_steps VALUES (?,?,?,?,?,?,?,?)",
                                (
                                    operation_id, item["path"], item["category"], item["digest"],
                                    int(item["size_bytes"]), "PENDING", None, now,
                                ),
                            )
                        self._audit(connection, operation_id, "PREPARED", {
                            "plan_digest": expected_plan_digest, "request_digest": request_digest,
                            "effect_set_digest": plan["effect_set_digest"], "actor_reference": actor_reference,
                        })
                        connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        self._fault_hook("after_prepare", None)
        return self._ensure_backup(operation_id)

    def _backup_directory(self, operation_id: str) -> Path:
        return self.data_root / "backups" / operation_id

    def _ensure_backup(self, operation_id: str) -> dict[str, Any]:
        with self._lock.acquire():
            with self._connect(read_only=False) as source:
                operation = source.execute(
                    "SELECT * FROM operational_reset_operations WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if operation is None:
                    raise OperationalResetError("unknown operational reset operation")
                if operation["backup_digest"]:
                    return self._operation_receipt(operation_id)
                state = source.execute(
                    "SELECT active_operation_id FROM operational_reset_state WHERE singleton=1"
                ).fetchone()[0]
                if state != operation_id:
                    raise OperationalResetError("operation does not own durable maintenance")
                document = json.loads(operation["document"])
                plan = document["plan"]
                backup = self._backup_directory(operation_id)
                backup_parent = backup.parent
                if backup_parent.is_symlink():
                    raise OperationalResetError("backup directory must not be a symlink")
                backup_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                estimated = self.database_path.stat().st_size + sum(
                    int(item["size_bytes"]) for item in plan["effect_set"]["external"]
                    if item["category"] == "OPERATIONAL_HISTORY"
                )
                if int(self._disk_usage(backup_parent).free) < estimated * 2 + 1024 * 1024:
                    raise OperationalResetError("insufficient free space for verified recovery backup")
                if backup.exists() and backup.is_symlink():
                    raise OperationalResetError("operation backup path must not be a symlink")
                backup.mkdir(mode=0o700, exist_ok=True)
                os.chmod(backup, 0o700)
                backup_db = backup / "forge.db"
                if _has_symlink_component(backup_db):
                    raise OperationalResetError("backup database path must not be a symlink")
                destination = sqlite3.connect(backup_db)
                try:
                    source.backup(destination)
                    destination.commit()
                    # Make the isolated recovery image self-contained.  The
                    # active source remains WAL-backed; the snapshot must not
                    # require a sibling WAL/SHM pair to verify or restore.
                    destination.execute("PRAGMA journal_mode=DELETE")
                finally:
                    destination.close()
                os.chmod(backup_db, 0o600)
                backup_marker = backup / "runtime-instance.json"
                if _has_symlink_component(backup_marker):
                    raise OperationalResetError("backup marker path must not be a symlink")
                shutil.copyfile(self.marker_path, backup_marker)
                os.chmod(backup_marker, 0o600)
                external_manifest: list[dict[str, Any]] = []
                for item in plan["effect_set"]["external"]:
                    if item["category"] != "OPERATIONAL_HISTORY":
                        continue
                    source_path = self.data_root / item["path"]
                    self._require_effect_path(source_path, item["path"], item["digest"])
                    destination_path = backup / "external" / item["path"]
                    if _has_symlink_component(destination_path):
                        raise OperationalResetError("backup external path contains a symlink")
                    destination_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    shutil.copyfile(source_path, destination_path)
                    os.chmod(destination_path, 0o600)
                    if _file_digest(destination_path) != item["digest"]:
                        raise OperationalResetError("external recovery copy failed digest verification")
                    external_manifest.append({
                        "path": item["path"], "digest": item["digest"], "size_bytes": item["size_bytes"],
                    })
                backup_manifest = {
                    "contract": "forge-operational-reset-backup-1.0", "operation_id": operation_id,
                    "runtime_id": operation["runtime_id"], "plan_digest": operation["plan_digest"],
                    "request_digest": operation["request_digest"], "source_revision": operation["source_revision"],
                    "source_revision_kind": plan["source_revision_kind"],
                    "implementation_digest": operation["implementation_digest"],
                    "product_version": canonical_version(), "schema_version": RUNTIME_SCHEMA_VERSION,
                    "snapshot_relevant_revision": operation["relevant_revision"],
                    "database": {"path": "forge.db", "digest": _file_digest(backup_db), "size_bytes": backup_db.stat().st_size},
                    "instance_marker": {"path": "runtime-instance.json", "digest": _file_digest(backup / "runtime-instance.json")},
                    "external": external_manifest,
                    "excluded": ["Keychain", "provider login", "venv", "cache", "locks", "prior backups"],
                    "source_counts": {
                        item["table"]: item["rows"] for item in plan["effect_set"]["purge_tables"]
                    },
                    "known_source_foreign_key_issues": plan["foreign_key_issues"],
                }
                backup_digest = _digest(backup_manifest)
                backup_manifest["backup_digest"] = backup_digest
                manifest_path = backup / "manifest.json"
                temporary = backup / "manifest.json.tmp"
                if _has_symlink_component(manifest_path) or _has_symlink_component(temporary):
                    raise OperationalResetError("backup manifest path must not be a symlink")
                temporary.write_text(_json(backup_manifest) + "\n", encoding="utf-8")
                os.chmod(temporary, 0o600)
                os.replace(temporary, manifest_path)
                self._verify_backup_files(backup, backup_manifest, expected_digest=backup_digest)
                now = _now()
                document["state"] = "BACKUP_VERIFIED"
                document["backup"] = {"reference": f"backups/{operation_id}", "digest": backup_digest}
                source.execute("BEGIN IMMEDIATE")
                try:
                    source.execute(
                        "UPDATE operational_reset_operations SET state='BACKUP_VERIFIED',backup_digest=?,backup_reference=?,updated_at=?,document=? WHERE operation_id=?",
                        (backup_digest, f"backups/{operation_id}", now, _json(document), operation_id),
                    )
                    source.execute(
                        "UPDATE operational_reset_state SET state='BACKUP_VERIFIED',updated_at=? WHERE singleton=1 AND active_operation_id=?",
                        (now, operation_id),
                    )
                    for item in external_manifest:
                        source.execute(
                            "UPDATE operational_reset_artifact_steps SET state='BACKED_UP',backup_relative_path=?,updated_at=? WHERE operation_id=? AND relative_path=?",
                            ("external/" + item["path"], now, operation_id, item["path"]),
                        )
                    self._audit(source, operation_id, "BACKUP_VERIFIED", {
                        "backup_reference": f"backups/{operation_id}", "backup_digest": backup_digest,
                    })
                    source.commit()
                except Exception:
                    source.rollback()
                    raise
        self._fault_hook("after_backup", None)
        return self._operation_receipt(operation_id)

    def _verify_backup_files(
        self, backup: Path, manifest: Mapping[str, Any], *, expected_digest: str | None = None,
    ) -> None:
        if _has_symlink_component(backup) or not backup.is_dir():
            raise OperationalResetError("recovery backup directory is invalid")
        manifest_core = dict(manifest)
        declared_digest = manifest_core.pop("backup_digest", None)
        if (
            not isinstance(declared_digest, str)
            or _digest(manifest_core) != declared_digest
            or expected_digest is not None and declared_digest != expected_digest
        ):
            raise OperationalResetError("recovery backup manifest binding is invalid")
        database = backup / str(manifest["database"]["path"])
        marker = backup / str(manifest["instance_marker"]["path"])
        if _has_symlink_component(database) or _has_symlink_component(marker):
            raise OperationalResetError("recovery backup contains an unsafe path")
        if _file_digest(database) != manifest["database"]["digest"] or _file_digest(marker) != manifest["instance_marker"]["digest"]:
            raise OperationalResetError("recovery backup digest verification failed")
        # Restore into an isolated, non-active root and read it there.  No
        # scheduler, provider, intake, or second RuntimeDatabase is started.
        with tempfile.TemporaryDirectory(prefix="forge-reset-restore-check-") as directory:
            restored = Path(directory) / "forge.db"
            shutil.copyfile(database, restored)
            check = sqlite3.connect(restored.resolve().as_uri() + "?mode=ro", uri=True)
            check.row_factory = sqlite3.Row
            try:
                if check.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise OperationalResetError("isolated recovery backup quick_check failed")
                if self._relevant_revision(check) != manifest["snapshot_relevant_revision"]:
                    raise OperationalResetError("isolated recovery backup does not match the approved source revision")
            finally:
                check.close()
        for item in manifest["external"]:
            archived = backup / "external" / str(item["path"])
            try:
                archived.resolve(strict=True).relative_to(backup.resolve(strict=True))
            except (OSError, ValueError) as error:
                raise OperationalResetError("isolated external recovery path is unsafe") from error
            if _has_symlink_component(archived) or not archived.is_file() or _file_digest(archived) != item["digest"]:
                raise OperationalResetError("isolated external recovery artifact verification failed")

    def _require_effect_path(self, path: Path, relative: str, expected_digest: str) -> None:
        try:
            resolved = path.resolve(strict=True)
        except OSError as error:
            raise OperationalResetError(f"planned external path is unavailable: {relative}") from error
        try:
            resolved.relative_to(self.data_root.resolve())
        except ValueError as error:
            raise OperationalResetError("external effect path escapes the Forge data root") from error
        if path.is_symlink() or not path.is_file() or _file_digest(path) != expected_digest:
            raise OperationalResetError(f"planned external artifact changed: {relative}")

    def _bound_operation(
        self, connection: sqlite3.Connection, operation_id: str, *,
        plan_digest: str, request_digest: str, backup_digest: str,
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM operational_reset_operations WHERE operation_id=?", (_safe_operation_id(operation_id),)
        ).fetchone()
        if row is None:
            raise OperationalResetError("unknown operational reset operation")
        if (
            row["plan_digest"] != plan_digest or row["request_digest"] != request_digest
            or row["backup_digest"] != backup_digest
        ):
            raise OperationalResetError("operation identity, plan, request, or backup binding differs")
        active = connection.execute(
            "SELECT active_operation_id FROM operational_reset_state WHERE singleton=1"
        ).fetchone()[0]
        if active != operation_id:
            raise OperationalResetError("operation does not own durable maintenance")
        if row["source_revision"] != self._source_revision():
            raise OperationalResetError("source revision changed after authorization")
        if row["implementation_digest"] != self._implementation_digest():
            raise OperationalResetError("maintenance service revision changed after authorization")
        return row

    @staticmethod
    def _tombstone_values(connection: sqlite3.Connection) -> list[tuple[str, str]]:
        queries: tuple[tuple[str, str], ...] = (
            ("mission_id", "SELECT mission_id FROM mission_state"),
            ("action_id", "SELECT action_id FROM scheduler_submissions"),
            ("submission_id", "SELECT submission_id FROM scheduler_submissions"),
            ("correlation_id", "SELECT correlation_id FROM execution_host_bindings"),
            ("correlation_id", "SELECT correlation_id FROM execution_host_exchange_audit"),
            ("execution_receipt_id", "SELECT receipt_id FROM execution_receipts"),
            ("action_derivation_id", "SELECT derivation_id FROM action_derivations"),
            ("generation_request_digest", "SELECT generation_request_digest FROM action_derivations WHERE generation_request_digest IS NOT NULL"),
            ("token_preflight_receipt_id", "SELECT receipt_id FROM token_preflight_receipts"),
            ("token_request_digest", "SELECT request_digest FROM token_preflight_receipts"),
            ("reattempt_authorization_id", "SELECT authorization_id FROM action_derivation_reattempt_authorizations"),
        )
        values: set[tuple[str, str]] = set()
        for kind, query in queries:
            for row in connection.execute(query):
                if row[0] is not None and str(row[0]):
                    values.add((kind, str(row[0])))
        return sorted(values)

    def _apply_database(self, row: sqlite3.Row) -> None:
        operation_id = str(row["operation_id"])
        document = json.loads(row["document"])
        plan = document["plan"]
        with self._connect(read_only=False) as connection:
            connection.execute("BEGIN IMMEDIATE")
            trigger_sql: list[str] = []
            try:
                current = self._relevant_revision(connection)
                if current != row["relevant_revision"]:
                    raise OperationalResetError("meaningful source data changed after the approved preview")
                external, unknown = self._external_inventory()
                effects = [item for item in external if item.get("effect") in {"ARCHIVE_AND_REMOVE", "REMOVE_CACHE"}]
                preserved_external = [
                    item for item in external
                    if item.get("effect") == "PRESERVE"
                    and item.get("category") == "INSTALLATION_AND_CONFIGURATION"
                    and not str(item.get("path", "")).startswith("backups/")
                ]
                if (
                    unknown or _digest(effects) != plan["external_inventory_digest"]
                    or _digest(preserved_external) != plan["preserved_external_digest"]
                ):
                    raise OperationalResetError("external operational data changed after the approved preview")
                if plan["source_revision"] != self._source_revision():
                    raise OperationalResetError("source revision changed after preview")
                if plan["implementation_digest"] != self._implementation_digest():
                    raise OperationalResetError("maintenance implementation changed after preview")
                maintenance_trigger_operations = {
                    **{table: "delete" for table in PURGE_ORDER},
                    "planning_provider_generation_permits": "update",
                }
                for table, operation in sorted(maintenance_trigger_operations.items()):
                    name = f"operational_reset_block_{table}_{operation}"
                    trigger = connection.execute(
                        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=? AND tbl_name=?",
                        (name, table),
                    ).fetchone()
                    if trigger is None or not trigger[0]:
                        raise OperationalResetError(f"required durable writer-fence trigger is missing: {name}")
                    trigger_sql.append(str(trigger[0]))
                    connection.execute(f'DROP TRIGGER "{name}"')
                for table, names in _IMMUTABLE_DELETE_TRIGGERS.items():
                    for name in names:
                        trigger = connection.execute(
                            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=? AND tbl_name=?",
                            (name, table),
                        ).fetchone()
                        if trigger is None or not trigger[0]:
                            raise OperationalResetError(f"required immutable trigger is missing: {name}")
                        trigger_sql.append(str(trigger[0]))
                        connection.execute(f'DROP TRIGGER "{name}"')
                retired_at = _now()
                retired_values = self._tombstone_values(connection)
                for kind, identifier in retired_values:
                    connection.execute(
                        "INSERT INTO operational_reset_tombstones VALUES (?,?,?,?,?) "
                        "ON CONFLICT(record_kind,record_id) DO NOTHING",
                        (kind, identifier, _digest({"kind": kind, "id": identifier}), operation_id, retired_at),
                    )
                connection.execute(
                    "UPDATE planning_provider_generation_permits "
                    "SET state='INVALIDATED_BY_OPERATIONAL_RESET',updated_at=? "
                    "WHERE state IN ('PENDING','TRANSPORT_COMMITTED')",
                    (retired_at,),
                )
                for table in PURGE_ORDER:
                    connection.execute(f'DELETE FROM "{table}"')
                for sql in trigger_sql:
                    connection.execute(sql)
                generation_before = int(row["generation_before"])
                generation_after = generation_before if plan["no_op"] else generation_before + 1
                document["state"] = "DATABASE_APPLIED"
                document["generation_after"] = generation_after
                connection.execute(
                    "UPDATE operational_reset_operations SET state='DATABASE_APPLIED',generation_after=?,updated_at=?,document=? WHERE operation_id=?",
                    (generation_after, retired_at, _json(document), operation_id),
                )
                connection.execute(
                    "UPDATE operational_reset_state SET dataset_generation=?,state='DATABASE_APPLIED',updated_at=? "
                    "WHERE singleton=1 AND active_operation_id=?",
                    (generation_after, retired_at, operation_id),
                )
                self._audit(connection, operation_id, "DATABASE_APPLIED", {
                    "generation_before": generation_before, "generation_after": generation_after,
                    "no_op": plan["no_op"], "tombstone_count": len(retired_values),
                })
                self._fault_hook("before_database_commit", None)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        self._fault_hook("after_database_commit", None)

    def _apply_artifacts(self, operation_id: str) -> None:
        with self._connect(read_only=False) as connection:
            steps = connection.execute(
                "SELECT * FROM operational_reset_artifact_steps WHERE operation_id=? ORDER BY relative_path",
                (operation_id,),
            ).fetchall()
        backup = self._backup_directory(operation_id)
        for step in steps:
            if step["state"] == "REMOVED":
                continue
            relative = str(step["relative_path"])
            source = self.data_root / relative
            expected = str(step["source_digest"])
            if source.exists():
                self._require_effect_path(source, relative, expected)
                if step["classification"] == "OPERATIONAL_HISTORY":
                    archived = backup / str(step["backup_relative_path"])
                    if not archived.is_file() or _file_digest(archived) != expected:
                        raise OperationalResetError("recovery artifact is unavailable before active removal")
                self._fault_hook("before_artifact_remove", relative)
                source.unlink()
                self._fault_hook("after_artifact_remove", relative)
            elif step["classification"] == "OPERATIONAL_HISTORY":
                archived = backup / str(step["backup_relative_path"])
                if not archived.is_file() or _file_digest(archived) != expected:
                    raise OperationalResetError("missing active artifact has no verified recovery copy")
            with self._connect(read_only=False) as connection:
                now = _now()
                with connection:
                    connection.execute(
                        "UPDATE operational_reset_artifact_steps SET state='REMOVED',updated_at=? WHERE operation_id=? AND relative_path=?",
                        (now, operation_id, relative),
                    )
                    self._audit(connection, operation_id, "ARTIFACT_REMOVED", {
                        "path_digest": _digest(relative), "classification": step["classification"],
                    })
        with self._connect(read_only=False) as connection:
            row = connection.execute(
                "SELECT document FROM operational_reset_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            document = json.loads(row[0])
            document["state"] = "APPLIED"
            now = _now()
            with connection:
                connection.execute(
                    "UPDATE operational_reset_operations SET state='APPLIED',updated_at=?,document=? WHERE operation_id=?",
                    (now, _json(document), operation_id),
                )
                connection.execute(
                    "UPDATE operational_reset_state SET state='APPLIED',updated_at=? WHERE singleton=1 AND active_operation_id=?",
                    (now, operation_id),
                )
                self._audit(connection, operation_id, "APPLIED", {"database_and_artifacts": "complete"})

    def apply(
        self, *, operation_id: str, plan_digest: str, request_digest: str, backup_digest: str,
    ) -> dict[str, Any]:
        """Apply or idempotently reconcile the already-authorized operation."""
        with self._lock.acquire():
            with self._connect(read_only=False) as connection:
                row = self._bound_operation(
                    connection, operation_id, plan_digest=plan_digest,
                    request_digest=request_digest, backup_digest=backup_digest,
                )
                state = str(row["state"])
                if state == "BACKUP_VERIFIED":
                    self._apply_database(row)
                    state = "DATABASE_APPLIED"
                if state in {"DATABASE_APPLIED", "APPLIED"}:
                    self._apply_artifacts(operation_id)
                elif state in {"VERIFIED", "COMPLETED"}:
                    return self._operation_receipt(operation_id)
                else:
                    raise OperationalResetError(f"operation is not ready to apply from state {state}")
        return self._operation_receipt(operation_id)

    def verify(
        self, *, operation_id: str, plan_digest: str, request_digest: str, backup_digest: str,
    ) -> dict[str, Any]:
        """Prove clean operational state and exact preserved bindings."""
        with self._lock.acquire():
            with self._connect(read_only=False) as connection:
                row = self._bound_operation(
                    connection, operation_id, plan_digest=plan_digest,
                    request_digest=request_digest, backup_digest=backup_digest,
                )
                if row["state"] == "VERIFIED":
                    return self._operation_receipt(operation_id)
                if row["state"] != "APPLIED":
                    raise OperationalResetError("verification requires a fully applied operation")
                document = json.loads(row["document"])
                plan = document["plan"]
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
                quick = connection.execute("PRAGMA quick_check").fetchone()[0]
                foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
                counts = {
                    table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
                    for table in PURGE_TABLES
                }
                if integrity != "ok" or quick != "ok" or foreign_keys:
                    raise OperationalResetError("post-reset SQLite integrity verification failed")
                if any(counts.values()):
                    raise OperationalResetError("post-reset operational tables are not empty")
                if connection.execute(
                    "SELECT 1 FROM planning_provider_generation_permits "
                    "WHERE state IN ('PENDING','TRANSPORT_COMMITTED') LIMIT 1"
                ).fetchone():
                    raise OperationalResetError("a pre-reset generation permit remains executable")
                preserved: dict[str, dict[str, Any]] = {}
                for table in PRESERVE_TABLES:
                    actual = self._row_digest(connection, table, post_reset=(table == "planning_provider_generation_permits"))
                    expected = plan["preserved"][table]["expected_post_reset_digest"]
                    if actual != expected:
                        raise OperationalResetError(f"preserved table changed unexpectedly: {table}")
                    preserved[table] = {
                        "rows": int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]),
                        "digest": actual,
                    }
                external, unknown = self._external_inventory()
                active_effects = [
                    item for item in external if item.get("effect") in {"ARCHIVE_AND_REMOVE", "REMOVE_CACHE"}
                ]
                if unknown or active_effects:
                    raise OperationalResetError("post-reset active external operational data is not empty")
                preserved_external = [
                    item for item in external
                    if item.get("effect") == "PRESERVE"
                    and item.get("category") == "INSTALLATION_AND_CONFIGURATION"
                    and not str(item.get("path", "")).startswith("backups/")
                ]
                if _digest(preserved_external) != plan["preserved_external_digest"]:
                    raise OperationalResetError("preserved external installation artifacts changed")
                manifest = json.loads((self._backup_directory(operation_id) / "manifest.json").read_text(encoding="utf-8"))
                self._verify_backup_files(
                    self._backup_directory(operation_id), manifest, expected_digest=backup_digest,
                )
                marker = self.marker_path.read_text(encoding="utf-8").strip()
                if marker != row["runtime_id"]:
                    raise OperationalResetError("runtime identity changed during reset")
                generation = int(connection.execute(
                    "SELECT dataset_generation FROM operational_reset_state WHERE singleton=1"
                ).fetchone()[0])
                if generation != int(row["generation_after"]):
                    raise OperationalResetError("dataset generation does not match the applied operation")
                verification = {
                    "integrity_check": "ok", "quick_check": "ok", "foreign_key_errors": 0,
                    "operational_rows": counts, "preserved": preserved,
                    "runtime_id": marker, "dataset_generation": generation,
                    "backup_digest": backup_digest, "active_external_effect_entries": 0,
                }
                verification_digest = _digest(verification)
                verification["verification_digest"] = verification_digest
                document["state"] = "VERIFIED"
                document["verification"] = verification
                now = _now()
                with connection:
                    connection.execute(
                        "UPDATE operational_reset_operations SET state='VERIFIED',updated_at=?,document=? WHERE operation_id=?",
                        (now, _json(document), operation_id),
                    )
                    connection.execute(
                        "UPDATE operational_reset_state SET state='VERIFIED',updated_at=? WHERE singleton=1 AND active_operation_id=?",
                        (now, operation_id),
                    )
                    self._audit(connection, operation_id, "VERIFIED", {
                        "verification_digest": verification_digest, "dataset_generation": generation,
                    })
        return self._operation_receipt(operation_id)

    def resume(
        self, *, operation_id: str, plan_digest: str, request_digest: str, backup_digest: str | None,
    ) -> dict[str, Any]:
        """Reconcile the same operation; never create a replacement reset."""
        status = self.status(operation_id=operation_id)
        state = status["state"]
        if state == "PREPARED":
            receipt = self._ensure_backup(operation_id)
            backup_digest = str(receipt["backup_digest"])
            state = str(receipt["state"])
        if not backup_digest:
            raise OperationalResetError("resume requires the operation's verified backup digest")
        if state in {"BACKUP_VERIFIED", "DATABASE_APPLIED", "APPLIED"}:
            receipt = self.apply(
                operation_id=operation_id, plan_digest=plan_digest,
                request_digest=request_digest, backup_digest=backup_digest,
            )
            state = str(receipt["state"])
        if state == "APPLIED":
            return self.verify(
                operation_id=operation_id, plan_digest=plan_digest,
                request_digest=request_digest, backup_digest=backup_digest,
            )
        if state in {"VERIFIED", "COMPLETED"}:
            return self._operation_receipt(operation_id)
        raise OperationalResetError(f"operation cannot be resumed from state {state}")

    def finish(
        self, *, operation_id: str, verification_digest: str | None = None,
        cancel_before_apply: bool = False,
    ) -> dict[str, Any]:
        """Leave maintenance only after proof, or cancel before any purge."""
        with self._lock.acquire():
            with self._connect(read_only=False) as connection:
                row = connection.execute(
                    "SELECT * FROM operational_reset_operations WHERE operation_id=?", (_safe_operation_id(operation_id),)
                ).fetchone()
                if row is None:
                    raise OperationalResetError("unknown operational reset operation")
                active = connection.execute(
                    "SELECT active_operation_id FROM operational_reset_state WHERE singleton=1"
                ).fetchone()[0]
                if active != operation_id:
                    if row["state"] in {"COMPLETED", "CANCELLED"}:
                        return self._operation_receipt(operation_id)
                    raise OperationalResetError("operation does not own durable maintenance")
                document = json.loads(row["document"])
                if cancel_before_apply:
                    if row["state"] not in {"PREPARED", "BACKUP_VERIFIED"}:
                        raise OperationalResetError("only an unapplied operation can be cancelled")
                    final_state = "CANCELLED"
                else:
                    if row["state"] != "VERIFIED":
                        raise OperationalResetError("maintenance can finish only after successful verification")
                    actual = document.get("verification", {}).get("verification_digest")
                    if not verification_digest or verification_digest != actual:
                        raise OperationalResetError("exact verification digest is required to finish")
                    final_state = "COMPLETED"
                document["state"] = final_state
                now = _now()
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "UPDATE operational_reset_operations SET state=?,updated_at=?,document=? WHERE operation_id=?",
                        (final_state, now, _json(document), operation_id),
                    )
                    self._audit(connection, operation_id, final_state, {
                        "verification_digest": verification_digest if final_state == "COMPLETED" else None,
                    })
                    connection.execute(
                        "UPDATE operational_reset_state SET active_operation_id=NULL,state='IDLE',updated_at=? "
                        "WHERE singleton=1 AND active_operation_id=?",
                        (now, operation_id),
                    )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        return self._operation_receipt(operation_id)

    def status(self, *, operation_id: str | None = None) -> dict[str, Any]:
        """Read durable maintenance state without opening a mutating runtime."""
        with self._connect(read_only=True) as connection:
            if int(connection.execute("PRAGMA user_version").fetchone()[0]) < 38:
                return {
                    "status": "UNAVAILABLE", "state": "SCHEMA_MIGRATION_REQUIRED",
                    "schema_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
                }
            if operation_id is None:
                state = connection.execute("SELECT * FROM operational_reset_state WHERE singleton=1").fetchone()
                metadata = dict(connection.execute(
                    "SELECT key,value FROM runtime_metadata WHERE key IN ('runtime_id','schema_version')"
                ))
                return {
                    "status": "OK", "state": str(state["state"]),
                    "active_operation_id": state["active_operation_id"],
                    "dataset_generation": int(state["dataset_generation"]),
                    "runtime_id": metadata.get("runtime_id"),
                    "database_identity": _digest(str(self.database_path.resolve())),
                    "schema_version": int(metadata.get("schema_version", RUNTIME_SCHEMA_VERSION)),
                }
        return self._operation_receipt(_safe_operation_id(operation_id))

    def _operation_receipt(self, operation_id: str) -> dict[str, Any]:
        with self._connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT * FROM operational_reset_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise OperationalResetError("unknown operational reset operation")
            document = json.loads(row["document"])
            audit_count = int(connection.execute(
                "SELECT COUNT(*) FROM operational_reset_audit WHERE operation_id=?", (operation_id,)
            ).fetchone()[0])
            pending_artifacts = int(connection.execute(
                "SELECT COUNT(*) FROM operational_reset_artifact_steps WHERE operation_id=? AND state!='REMOVED'",
                (operation_id,),
            ).fetchone()[0])
            return {
                "contract": "forge-operational-reset-receipt-1.0",
                "operation_id": operation_id, "state": str(row["state"]),
                "runtime_id": str(row["runtime_id"]), "profile": str(row["profile"]),
                "plan_digest": str(row["plan_digest"]), "request_digest": str(row["request_digest"]),
                "effect_set_digest": document["plan"]["effect_set_digest"],
                "backup_reference": row["backup_reference"], "backup_digest": row["backup_digest"],
                "source_revision": str(row["source_revision"]),
                "source_revision_kind": document["plan"]["source_revision_kind"],
                "implementation_digest": str(row["implementation_digest"]),
                "schema_version": int(row["schema_version"]),
                "policy_version": str(row["policy_version"]),
                "generation_before": int(row["generation_before"]), "generation_after": row["generation_after"],
                "verification_digest": (
                    None if document.get("verification") is None
                    else document["verification"].get("verification_digest")
                ),
                "audit_events": audit_count, "pending_artifacts": pending_artifacts,
                "summary": "secret-free Forge operational reset maintenance receipt",
            }

    def operator_envelope(self, command: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Project one stable, secret-free cross-product operator envelope."""
        plan: Mapping[str, Any] | None = payload if "target" in payload else None
        operation_id = payload.get("operation_id")
        if plan is None and isinstance(operation_id, str):
            with self._connect(read_only=True) as connection:
                if int(connection.execute("PRAGMA user_version").fetchone()[0]) >= 38:
                    row = connection.execute(
                        "SELECT document FROM operational_reset_operations WHERE operation_id=?", (operation_id,)
                    ).fetchone()
                    if row is not None:
                        plan = json.loads(row[0])["plan"]
        target = {} if plan is None else dict(plan["target"])
        counts = {} if plan is None else {
            item["table"]: item["rows"] for item in plan["effect_set"]["purge_tables"]
        }
        preserved = {} if plan is None else plan.get("preserved", {})
        state = str(payload.get("state") or payload.get("status") or "UNKNOWN")
        backup_digest = payload.get("backup_digest")
        backup_reference = payload.get("backup_reference")
        return {
            "contract_version": "operational-reset-v1",
            "product": "forge",
            "command": command,
            "operation_id": operation_id,
            "state": state,
            "allowed": bool(
                payload.get("execution_allowed", state not in {"BLOCKED", "ERROR", "UNAVAILABLE"})
            ),
            "target": {
                "instance_id": target.get("runtime_id") or payload.get("runtime_id"),
                "database_path": target.get("database", str(self.database_path)),
                "database_identity": target.get("database_binding_digest") or payload.get("database_identity"),
                "schema_version": target.get("schema_version", payload.get("schema_version")),
            },
            "profile": payload.get("profile", RESET_PROFILE),
            "dataset_generation": target.get(
                "dataset_generation", payload.get("generation_after", payload.get("dataset_generation"))
            ),
            "plan_digest": payload.get("plan_digest"),
            "relevant_revision_digest": (
                None if plan is None else plan.get("relevant_revision")
            ),
            "backup": (
                None if not backup_digest else {
                    "manifest": backup_reference, "digest": backup_digest,
                    "verified": state in {"BACKUP_VERIFIED", "DATABASE_APPLIED", "APPLIED", "VERIFIED", "COMPLETED"},
                }
            ),
            "counts": counts,
            "blockers": list(payload.get("blockers", ())),
            "integrity": {} if plan is None else dict(plan.get("integrity", {})),
            "preserved_bindings_digest": _digest({
                "tables": {
                    table: value.get("expected_post_reset_digest") for table, value in sorted(preserved.items())
                },
                "external": None if plan is None else plan.get("preserved_external_digest"),
            }) if preserved else None,
            "details": dict(payload),
        }
