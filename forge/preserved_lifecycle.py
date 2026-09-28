"""Product-owned preserve/purge/restore semantics for Forge Server Runtime.

This contract extends, but never changes, the destructive
``forge-server-runtime-lifecycle/v1`` uninstall boundary. Deployment-owned
service definitions and immutable runtime slots remain outside Forge's mutable
instance-data ownership.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import os
from pathlib import Path
import stat
from typing import Any, Callable, Mapping

from .installed_lifecycle import (
    CONTROL_DIRECTORY,
    InstalledLifecycleError,
    InstalledUninstallDispatcher,
    UninstallRequest,
    _assert_identity,
    _assert_no_symlink_components,
    _assert_quiescent,
    _atomic_json,
    _digest_bytes,
    _exclusive_locks,
    _json_bytes,
    _read_json,
    _read_regular_bytes,
    _runtime_snapshot,
    _validate_identifier,
    _DIGEST,
    _SOURCE,
)


INSTANCE_LIFECYCLE_CONTRACT = "forge-server-instance-lifecycle/v1"
LIFECYCLE_DIRECTORY = "instance-lifecycle-v1"
PROVIDER_AUTH_PRESERVED = "PRESERVED_REQUIRES_REVERIFICATION"


def _content_tree_digest(root: Path) -> str:
    """Bind every regular byte in one exact, link-free instance tree."""
    _assert_no_symlink_components(root)
    entries: list[dict[str, object]] = []
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        parent = Path(directory)
        for name in sorted(names):
            path = parent / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise InstalledLifecycleError(f"instance tree contains an unsafe directory entry: {path}")
            entries.append({
                "path": str(path.relative_to(root)),
                "kind": "DIRECTORY",
                "mode": stat.S_IMODE(info.st_mode),
            })
        for name in sorted(files):
            path = parent / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise InstalledLifecycleError(f"instance tree contains an unsafe file entry: {path}")
            payload = _read_regular_bytes(path)
            entries.append({
                "path": str(path.relative_to(root)),
                "kind": "FILE",
                "mode": stat.S_IMODE(info.st_mode),
                "size": len(payload),
                "digest": _digest_bytes(payload),
            })
    return _digest_bytes(_json_bytes(entries))


@dataclass(frozen=True)
class InstanceLifecycleRequest:
    operation_id: str
    instance_id: str
    runtime_id: str
    installation_id: str
    installed_version: str
    installed_source: str
    installed_artifact_digest: str
    data_root: str
    instances_root: str

    def validate(self) -> None:
        for label, value in (
            ("operation identity", self.operation_id),
            ("instance identity", self.instance_id),
            ("runtime identity", self.runtime_id),
            ("installation identity", self.installation_id),
        ):
            _validate_identifier(label, value)
        if self.instance_id != self.runtime_id:
            raise InstalledLifecycleError("deployment instance does not bind the selected Forge runtime")
        if _SOURCE.fullmatch(self.installed_source) is None or _DIGEST.fullmatch(self.installed_artifact_digest) is None:
            raise InstalledLifecycleError("installed Forge artifact identity is invalid")
        if not isinstance(self.installed_version, str) or not self.installed_version:
            raise InstalledLifecycleError("installed Forge version is invalid")
        data_root, instances_root = Path(self.data_root), Path(self.instances_root)
        if not data_root.is_absolute() or not instances_root.is_absolute():
            raise InstalledLifecycleError("lifecycle paths must be absolute")
        _assert_no_symlink_components(instances_root)
        _assert_no_symlink_components(data_root, allow_missing=True)
        if data_root.parent != instances_root or data_root.name == CONTROL_DIRECTORY:
            raise InstalledLifecycleError("data root is not one direct managed instance root")

    @property
    def digest(self) -> str:
        return _digest_bytes(_json_bytes(asdict(self)))


@dataclass(frozen=True)
class RestoreRequest(InstanceLifecycleRequest):
    preserve_operation_id: str

    def validate(self) -> None:
        super().validate()
        _validate_identifier("preserve operation identity", self.preserve_operation_id)


class _LifecycleOperation:
    operation: str

    def __init__(
        self,
        request: InstanceLifecycleRequest,
        *,
        interrupt_after: str | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        request.validate()
        self.request = request
        self.data_root = Path(request.data_root)
        self.instances_root = Path(request.instances_root)
        identity = sha256(request.instance_id.encode()).hexdigest()
        self.control_root = self.instances_root / CONTROL_DIRECTORY / identity
        self.lifecycle_root = self.control_root / LIFECYCLE_DIRECTORY
        self.operation_root = self.lifecycle_root / "operations" / request.operation_id
        self.state_path = self.operation_root / "state.json"
        self.receipt_path = self.operation_root / "receipt.json"
        self.purge_tombstone = self.lifecycle_root / "purged.json"
        self.lifecycle_lock = self.control_root / "lifecycle.lock"
        self.interrupt_after = interrupt_after
        if clock is None:
            from .installed_lifecycle import _now
            clock = _now
        self.clock = clock

    def _interrupt(self, phase: str) -> None:
        if self.interrupt_after == phase:
            raise InterruptedError(f"interrupted after {phase}")

    def _state(self) -> dict[str, Any]:
        if self.state_path.exists():
            state = _read_json(self.state_path)
            if (
                state.get("contract") != INSTANCE_LIFECYCLE_CONTRACT
                or state.get("operation") != self.operation
                or state.get("request") != asdict(self.request)
                or state.get("request_digest") != self.request.digest
            ):
                raise InstalledLifecycleError("operation identity already belongs to another lifecycle request")
            return state
        state = {
            "contract": INSTANCE_LIFECYCLE_CONTRACT,
            "operation": self.operation,
            "request": asdict(self.request),
            "request_digest": self.request.digest,
            "phase": "PREPARED",
            "prepared_at": self.clock(),
        }
        _atomic_json(self.state_path, state)
        return state

    def _save(self, state: Mapping[str, Any], phase: str, **evidence: object) -> dict[str, Any]:
        updated = {**state, **evidence, "phase": phase, "updated_at": self.clock()}
        _atomic_json(self.state_path, updated)
        return updated

    def _write_receipt(self, state: Mapping[str, Any], payload: Mapping[str, object]) -> dict[str, Any]:
        receipt = {
            "contract": INSTANCE_LIFECYCLE_CONTRACT,
            "operation": self.operation,
            "operation_id": self.request.operation_id,
            "instance_id": self.request.instance_id,
            "runtime_id": self.request.runtime_id,
            "installation_id": self.request.installation_id,
            "request_digest": self.request.digest,
            "selected_artifact": {
                "version": self.request.installed_version,
                "source_revision": self.request.installed_source,
                "artifact_digest": self.request.installed_artifact_digest,
            },
            "state": "COMPLETE",
            **payload,
            "completed_at": self.clock(),
        }
        receipt["receipt_digest"] = _digest_bytes(_json_bytes(receipt))
        if self.receipt_path.exists():
            existing = _read_json(self.receipt_path)
            unsigned = {key: value for key, value in existing.items() if key != "receipt_digest"}
            if (
                existing.get("contract") != INSTANCE_LIFECYCLE_CONTRACT
                or existing.get("operation") != self.operation
                or existing.get("request_digest") != self.request.digest
                or existing.get("receipt_digest") != _digest_bytes(_json_bytes(unsigned))
            ):
                raise InstalledLifecycleError("terminal lifecycle receipt conflicts with existing evidence")
            receipt = existing
        else:
            _atomic_json(self.receipt_path, receipt)
        self._save(state, "COMPLETE", receipt_digest=receipt["receipt_digest"])
        return receipt

    def _terminal_receipt(self, state: Mapping[str, Any]) -> dict[str, Any]:
        receipt = _read_json(self.receipt_path)
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        if (
            receipt.get("contract") != INSTANCE_LIFECYCLE_CONTRACT
            or receipt.get("operation") != self.operation
            or receipt.get("request_digest") != self.request.digest
            or receipt.get("selected_artifact") != {
                "version": self.request.installed_version,
                "source_revision": self.request.installed_source,
                "artifact_digest": self.request.installed_artifact_digest,
            }
            or receipt.get("state") != "COMPLETE"
            or receipt.get("receipt_digest") != _digest_bytes(_json_bytes(unsigned))
            or state.get("receipt_digest") != receipt.get("receipt_digest")
        ):
            raise InstalledLifecycleError("terminal lifecycle receipt is inconsistent")
        return receipt

    def _runtime_locks(self) -> tuple[Path, ...]:
        return (
            self.data_root / "locks" / "forge-server-runtime.lock",
            self.data_root / "forge-mission-controller.lock",
            self.data_root / "forge-runtime-mutation.lock",
            self.data_root / "locks" / "runtime.lock",
        )

    def _verified_snapshot(self) -> tuple[dict[str, Any], str]:
        if not self.data_root.is_dir():
            raise InstalledLifecycleError("selected preserved instance data is unavailable")
        with _exclusive_locks(self._runtime_locks()):
            snapshot = _runtime_snapshot(self.data_root)
            _assert_identity(
                snapshot,
                runtime_id=self.request.runtime_id,
                installation_id=self.request.installation_id,
                installed_version=self.request.installed_version,
            )
            _assert_quiescent(snapshot)
            tree_digest = _content_tree_digest(self.data_root)
        return snapshot, tree_digest


class InstalledPreserveDispatcher(_LifecycleOperation):
    """Durably attest one quiescent instance as data-preserved."""

    operation = "PRESERVE"

    def run(self) -> dict[str, Any]:
        self.lifecycle_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.lifecycle_root, 0o700)
        with _exclusive_locks((self.lifecycle_lock,)):
            if self.purge_tombstone.exists():
                raise InstalledLifecycleError("instance identity was permanently purged")
            state = self._state()
            if state.get("phase") == "COMPLETE":
                receipt = self._terminal_receipt(state)
                _snapshot, current = self._verified_snapshot()
                if current != receipt.get("mutable_instance_data_digest"):
                    raise InstalledLifecycleError("preserved instance data changed after terminal preserve")
                return receipt
            snapshot, tree_digest = self._verified_snapshot()
            state = self._save(
                state,
                "VERIFIED",
                runtime_snapshot_digest=snapshot["digest"],
                mutable_instance_data_digest=tree_digest,
            )
            self._interrupt("verified")
            return self._write_receipt(state, {
                "lifecycle_state": "UNINSTALLED_DATA_PRESERVED",
                "instance_identity": "PRESERVED",
                "mutable_instance_data": "PRESERVED",
                "mutable_instance_data_digest": tree_digest,
                "restorable": True,
                "service_state": "REMOVED_OR_INACTIVE",
                "service_definition": "DEPLOYMENT_OWNER",
                "immutable_runtime_slots": "PRESERVED",
                "provider_auth_state": PROVIDER_AUTH_PRESERVED,
            })


class InstalledRestoreDispatcher(_LifecycleOperation):
    """Validate preserved Forge data for same-identity deployment-owner restore."""

    operation = "RESTORE"

    @property
    def restore_request(self) -> RestoreRequest:
        if not isinstance(self.request, RestoreRequest):
            raise InstalledLifecycleError("restore request type is invalid")
        return self.request

    def _preserve_receipt(self) -> dict[str, Any]:
        preserve_root = self.lifecycle_root / "operations" / self.restore_request.preserve_operation_id
        receipt = _read_json(preserve_root / "receipt.json")
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        if (
            receipt.get("contract") != INSTANCE_LIFECYCLE_CONTRACT
            or receipt.get("operation") != "PRESERVE"
            or receipt.get("instance_id") != self.request.instance_id
            or receipt.get("runtime_id") != self.request.runtime_id
            or receipt.get("installation_id") != self.request.installation_id
            or receipt.get("selected_artifact") != {
                "version": self.request.installed_version,
                "source_revision": self.request.installed_source,
                "artifact_digest": self.request.installed_artifact_digest,
            }
            or receipt.get("lifecycle_state") != "UNINSTALLED_DATA_PRESERVED"
            or receipt.get("restorable") is not True
            or receipt.get("receipt_digest") != _digest_bytes(_json_bytes(unsigned))
        ):
            raise InstalledLifecycleError("preserve evidence does not authorize same-identity restore")
        return receipt

    def run(self) -> dict[str, Any]:
        self.lifecycle_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.lifecycle_root, 0o700)
        with _exclusive_locks((self.lifecycle_lock,)):
            if self.purge_tombstone.exists():
                raise InstalledLifecycleError("purged instance identity cannot be restored")
            state = self._state()
            if state.get("phase") == "COMPLETE":
                return self._terminal_receipt(state)
            preserve = self._preserve_receipt()
            snapshot, tree_digest = self._verified_snapshot()
            if tree_digest != preserve.get("mutable_instance_data_digest"):
                raise InstalledLifecycleError("preserved instance data no longer matches restore evidence")
            state = self._save(
                state,
                "VERIFIED",
                runtime_snapshot_digest=snapshot["digest"],
                preserve_operation_id=self.restore_request.preserve_operation_id,
                preserve_receipt_digest=preserve["receipt_digest"],
                mutable_instance_data_digest=tree_digest,
            )
            self._interrupt("verified")
            return self._write_receipt(state, {
                "lifecycle_state": "RESTORE_VALIDATED",
                "instance_identity": "PRESERVED",
                "mutable_instance_data": "PRESERVED",
                "mutable_instance_data_digest": tree_digest,
                "restored_from_preserve_operation": self.restore_request.preserve_operation_id,
                "restored": True,
                "service_state": "DEPLOYMENT_OWNER_REINSTALL_REQUIRED",
                "service_definition": "DEPLOYMENT_OWNER",
                "immutable_runtime_slots": "PRESERVED",
                "provider_auth_state": PROVIDER_AUTH_PRESERVED,
                "ready": False,
            })


class InstalledPurgeDispatcher(_LifecycleOperation):
    """Explicit permanent purge projection over the legacy destructive uninstall."""

    operation = "PURGE"

    def run(self) -> dict[str, Any]:
        self.lifecycle_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.lifecycle_root, 0o700)
        with _exclusive_locks((self.lifecycle_lock,)):
            state = self._state()
            if state.get("phase") == "COMPLETE":
                receipt = self._terminal_receipt(state)
                if self.data_root.exists() or self.data_root.is_symlink():
                    raise InstalledLifecycleError("purged instance target was recreated")
                return receipt

        uninstall = InstalledUninstallDispatcher(UninstallRequest(
            operation_id=self.request.operation_id,
            instance_id=self.request.instance_id,
            runtime_id=self.request.runtime_id,
            installation_id=self.request.installation_id,
            data_root=self.request.data_root,
            instances_root=self.request.instances_root,
        )).run()
        self._interrupt("uninstalled")

        with _exclusive_locks((self.lifecycle_lock,)):
            state = self._state()
            if self.data_root.exists() or self.data_root.is_symlink():
                raise InstalledLifecycleError("destructive uninstall did not remove selected instance data")
            tombstone = {
                "contract": INSTANCE_LIFECYCLE_CONTRACT,
                "instance_id": self.request.instance_id,
                "lifecycle_state": "PURGED",
                "restorable": False,
                "purge_operation_id": self.request.operation_id,
                "uninstall_receipt_digest": uninstall["receipt_digest"],
            }
            tombstone["tombstone_digest"] = _digest_bytes(_json_bytes(tombstone))
            if self.purge_tombstone.exists():
                if _read_json(self.purge_tombstone) != tombstone:
                    raise InstalledLifecycleError("instance purge tombstone conflicts with prior evidence")
            else:
                _atomic_json(self.purge_tombstone, tombstone)
            return self._write_receipt(state, {
                "lifecycle_state": "PURGED",
                "instance_identity": "RETIRED",
                "mutable_instance_data": "REMOVED",
                "restorable": False,
                "service_state": "DEPLOYMENT_OWNER_REMOVAL_REQUIRED_OR_COMPLETE",
                "service_definition": "DEPLOYMENT_OWNER",
                "immutable_runtime_slots": "PRESERVED",
                "provider_auth_state": "REMOVED_WITH_INSTANCE_DATA",
                "legacy_uninstall_receipt_digest": uninstall["receipt_digest"],
                "purge_tombstone_digest": tombstone["tombstone_digest"],
            })


def lifecycle_status(instances_root: str, instance_id: str, operation_id: str) -> dict[str, Any]:
    """Read one exact product-owned preserve/purge/restore operation."""
    _validate_identifier("instance identity", instance_id)
    _validate_identifier("operation identity", operation_id)
    root = Path(instances_root)
    if not root.is_absolute():
        raise InstalledLifecycleError("instances root must be absolute")
    _assert_no_symlink_components(root)
    identity = sha256(instance_id.encode()).hexdigest()
    operation_root = root / CONTROL_DIRECTORY / identity / LIFECYCLE_DIRECTORY / "operations" / operation_id
    state = _read_json(operation_root / "state.json")
    result = {
        "contract": state.get("contract"),
        "operation": state.get("operation"),
        "operation_id": operation_id,
        "instance_id": instance_id,
        "phase": state.get("phase"),
        "request_digest": state.get("request_digest"),
        "state": "IN_PROGRESS",
    }
    if state.get("phase") == "COMPLETE":
        receipt = _read_json(operation_root / "receipt.json")
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        if receipt.get("receipt_digest") != _digest_bytes(_json_bytes(unsigned)):
            raise InstalledLifecycleError("terminal lifecycle receipt is inconsistent")
        result.update({
            "state": "COMPLETE",
            "lifecycle_state": receipt.get("lifecycle_state"),
            "receipt_digest": receipt.get("receipt_digest"),
            "restorable": receipt.get("restorable"),
        })
    return result
