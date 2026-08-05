"""Persistent Runtime Instance resolution, bootstrap, and recovery.

The Runtime Database is storage owned by a Runtime Instance; it is never the
identity of that instance.  Resolution uses a durable, repository-scoped
registry and validates every persisted boundary before SQLite is opened.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Any


RUNTIME_INSTANCE_VERSION = "1"
RUNTIME_REGISTRY_VERSION = "1"


class RuntimeResolutionError(RuntimeError):
    """A canonical Runtime Instance cannot be determined safely."""


@dataclass(frozen=True)
class RuntimeIdentity:
    """The immutable identity of a single Forge Runtime Instance.

    Compatibility properties retain the Runtime Database vocabulary used by
    earlier callers while the public architectural concept is Runtime Instance.
    """

    runtime_id: str
    repository_identity: str
    repository_root: str
    instance_version: str
    created_at: str
    database_location: str
    last_access_at: str
    status: str

    @classmethod
    def from_metadata(cls, metadata: dict[str, str]) -> "RuntimeIdentity":
        required = ("runtime_id", "repository_identity", "repository_root", "created_at")
        if any(not metadata.get(key) for key in required):
            raise RuntimeResolutionError("runtime identity metadata is incomplete")
        return cls(metadata["runtime_id"], metadata["repository_identity"], metadata["repository_root"],
                   metadata.get("instance_version", RUNTIME_INSTANCE_VERSION), metadata["created_at"],
                   metadata.get("database_location", ""), metadata.get("last_access_at", ""), metadata.get("status", ""))

    @property
    def repository_id(self) -> str:
        return self.repository_identity

    @property
    def database_version(self) -> str:
        return self.instance_version

    def to_dict(self) -> dict[str, str]:
        return {"runtime_id": self.runtime_id, "repository_identity": self.repository_identity,
                "repository_id": self.repository_identity, "repository_root": self.repository_root,
                "instance_version": self.instance_version, "database_version": self.instance_version,
                "created_at": self.created_at, "database_location": self.database_location,
                "last_access_at": self.last_access_at, "status": self.status}


@dataclass(frozen=True)
class RuntimeInstance:
    """Resolved Runtime Instance: immutable identity plus mutable placement."""

    identity: RuntimeIdentity
    location: Path
    last_access_at: str
    status: str

    def to_dict(self) -> dict[str, str]:
        result = self.identity.to_dict()
        result.update({"instance_location": str(self.location), "database_location": str(self.location),
                       "last_access_at": self.last_access_at, "status": self.status})
        return result


@dataclass(frozen=True)
class RuntimeLocation:
    path: Path
    source: str
    bootstrap: bool


def canonical_repository_root(repository_root: Path | str) -> Path:
    """Return the common Git checkout root for a main checkout or worktree."""
    root = Path(repository_root)
    try:
        common_dir = subprocess.check_output(
            ("git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"),
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return root.resolve()
    return Path(common_dir).resolve().parent


def repository_identity(repository_root: Path | str) -> str:
    """Derive a location-independent identity from the Git root commit.

    The root commit is shared by branches, worktrees, and filesystem moves.
    A non-Git workspace has no durable Git identity and therefore remains
    intentionally local to its canonical path.
    """
    root = canonical_repository_root(repository_root)
    try:
        initial_commit = subprocess.check_output(
            ("git", "-C", str(root), "rev-list", "--max-parents=0", "HEAD"),
            text=True, stderr=subprocess.DEVNULL,
        ).strip().splitlines()
    except (OSError, subprocess.CalledProcessError):
        initial_commit = []
    basis = initial_commit[0] if len(initial_commit) == 1 and initial_commit[0] else str(root.resolve())
    return "forge-repository-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


class RuntimeResolver:
    """Resolve exactly one registered Runtime Instance, or fail closed."""

    def __init__(self, repository_root: Path | str, *, configured_location: Path | str | None = None,
                 configured_runtime_root: Path | str | None = None) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.canonical_root = canonical_repository_root(self.repository_root)
        self.configured_location = None if configured_location is None else Path(configured_location).expanduser().resolve()
        self.configured_runtime_root = None if configured_runtime_root is None else Path(configured_runtime_root).expanduser().resolve()

    @property
    def default_location(self) -> Path:
        if self.configured_runtime_root is not None:
            return self.configured_runtime_root / repository_identity(self.repository_root) / "runtime.db"
        return self.canonical_root / ".forge" / "runtime.db"

    @property
    def registry_path(self) -> Path:
        """Registry is outside cleanup-prone ``.forge`` and shared by worktrees."""
        if self.configured_runtime_root is not None:
            return self.configured_runtime_root / repository_identity(self.repository_root) / "runtime-instance.json"
        git_dir = self.canonical_root / ".git"
        return (git_dir / "forge-runtime-instance.json") if git_dir.exists() else (self.canonical_root / ".forge-runtime-instance.json")

    def resolve(self) -> RuntimeLocation:
        registered = self._registered_location()
        candidates: dict[Path, str] = {}
        for path, source in ((self.configured_location, "configured"), (registered, "registered"),
                             (self.default_location, "repository_default")):
            if path is not None and path.is_file():
                candidates[path.resolve()] = source
        forge_dir = self.canonical_root / ".forge"
        if forge_dir.is_dir():
            for candidate in forge_dir.rglob("runtime*.db"):
                if candidate.is_file():
                    candidates.setdefault(candidate.resolve(), "discovery")
        if len(candidates) > 1:
            raise RuntimeResolutionError("multiple Runtime Instance candidates found")
        if candidates:
            path, source = next(iter(candidates.items()))
            self._validate_candidate_identity(path)
            if registered is None:
                self._register(path)
            return RuntimeLocation(path, source, False)
        if self._registry_exists():
            raise RuntimeResolutionError("registered Runtime Instance location is missing")
        target = self.configured_location or self.default_location
        return RuntimeLocation(target, "configured" if self.configured_location else "repository_default", True)

    def relocate(self, destination: Path | str) -> RuntimeLocation:
        """Migrate one validated instance atomically without changing identity."""
        source = self.resolve()
        if source.bootstrap:
            raise RuntimeResolutionError("cannot relocate a Runtime Instance that has not been bootstrapped")
        destination_path = Path(destination).expanduser().resolve()
        if destination_path == source.path:
            return source
        if destination_path.exists():
            raise RuntimeResolutionError("runtime relocation destination already exists")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination_path.with_suffix(destination_path.suffix + ".relocating")
        try:
            with sqlite3.connect(source.path) as source_connection, sqlite3.connect(temporary) as destination_connection:
                source_connection.backup(destination_connection)
            from .database import RuntimeDatabase
            checked = RuntimeDatabase(self.repository_root, path=temporary)
            try:
                checked.validate_integrity()
            finally:
                checked.close()
            temporary.replace(destination_path)
            opened = RuntimeDatabase(self.repository_root, path=destination_path)
            try:
                opened.validate_integrity()
            finally:
                opened.close()
            self._register(destination_path)
            source.path.unlink()
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(source.path) + suffix)
                if sidecar.exists():
                    sidecar.unlink()
            return RuntimeLocation(destination_path, "relocated", False)
        except Exception:
            if temporary.exists():
                temporary.unlink()
            raise

    def _registry_exists(self) -> bool:
        return self.registry_path.exists()

    def _registered_location(self) -> Path | None:
        if not self.registry_path.exists():
            return None
        if not self.registry_path.is_file():
            raise RuntimeResolutionError("Runtime Instance registry is not a file")
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeResolutionError("Runtime Instance registry is malformed") from error
        expected = {"registry_version", "runtime_id", "repository_identity", "instance_location", "created_at", "status"}
        if not isinstance(payload, dict) or not expected <= payload.keys() or payload["registry_version"] != RUNTIME_REGISTRY_VERSION:
            raise RuntimeResolutionError("Runtime Instance registry is incomplete or unsupported")
        if payload["repository_identity"] != repository_identity(self.repository_root):
            raise RuntimeResolutionError("Runtime Instance registry belongs to a different repository")
        if not all(isinstance(payload[key], str) and payload[key] for key in expected - {"registry_version"}):
            raise RuntimeResolutionError("Runtime Instance registry has invalid identity metadata")
        return Path(payload["instance_location"]).expanduser().resolve()

    def _register(self, location: Path, instance: RuntimeInstance | None = None) -> None:
        if instance is None:
            instance = self._instance_from_database(location)
        if instance.identity.repository_identity != repository_identity(self.repository_root):
            raise RuntimeResolutionError("Runtime Instance belongs to a different repository")
        payload = {"registry_version": RUNTIME_REGISTRY_VERSION, **instance.to_dict()}
        payload["instance_location"] = str(location.resolve())
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.registry_path)

    def _instance_from_database(self, path: Path) -> RuntimeInstance:
        metadata = self._read_metadata(path)
        identity = RuntimeIdentity.from_metadata(metadata)
        return RuntimeInstance(identity, path.resolve(), identity.last_access_at, identity.status)

    def _read_metadata(self, path: Path) -> dict[str, str]:
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                rows = connection.execute("SELECT key, value FROM runtime_metadata").fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise RuntimeResolutionError("runtime candidate is not a readable Forge Runtime Database") from error
        return dict(rows)

    def _validate_candidate_identity(self, path: Path) -> None:
        instance = self._instance_from_database(path)
        if instance.identity.repository_identity != repository_identity(self.repository_root):
            raise RuntimeResolutionError("Runtime Instance candidate belongs to a different repository")
        if instance.status != "active" or not instance.last_access_at:
            raise RuntimeResolutionError("Runtime Instance candidate metadata is inconsistent")
        if self._registry_exists():
            registered = json.loads(self.registry_path.read_text(encoding="utf-8"))
            if registered["runtime_id"] != instance.identity.runtime_id:
                raise RuntimeResolutionError("Runtime Instance registry identity does not match database")


class RuntimeBootstrap:
    """Discover an existing Runtime Instance or create exactly one new instance."""

    def __init__(self, repository_root: Path | str, *, configured_location: Path | str | None = None,
                 configured_runtime_root: Path | str | None = None, forge_version: str = "0.0") -> None:
        self.resolver = RuntimeResolver(repository_root, configured_location=configured_location,
                                        configured_runtime_root=configured_runtime_root)
        self.forge_version = forge_version

    def open(self):
        from .database import RuntimeDatabase
        location = self.resolver.resolve()
        database = RuntimeDatabase(self.resolver.repository_root, path=location.path, forge_version=self.forge_version)
        self.resolver._register(database.path)
        return database


class RuntimeRecovery:
    """Runtime-only recovery projections; no source or legacy-state reconstruction."""

    def __init__(self, database) -> None:
        self._database = database

    def recover(self) -> dict[str, Any]:
        self._database.validate_integrity()
        connection = self._database._connection
        documents = lambda table: tuple(json.loads(row[0]) for row in connection.execute(f"SELECT document FROM {table} ORDER BY 1"))
        receipts = tuple(dict(row) for row in connection.execute(
            "SELECT receipt_id, mission_id, execution_host, execution_run_id, engineering_report_id, correlation_identity, executed_at, outcome FROM execution_receipts ORDER BY receipt_id"
        ))
        planning = None
        row = connection.execute("SELECT document FROM planning_state WHERE singleton = 1").fetchone()
        if row is not None:
            planning = json.loads(row[0])
        instance = RuntimeInstance(self._database.runtime_identity, self._database.path.resolve(),
                                   self._database.metadata["last_access_at"], self._database.metadata["status"])
        return {"runtime_instance": instance.to_dict(), "runtime_identity": instance.identity.to_dict(),
                "mission_state": documents("mission_state"), "architecture_reviews": documents("architecture_reviews"),
                "mission_recommendations": documents("mission_recommendations"), "decision_evidence": documents("decision_evidence"),
                "execution_receipts": receipts, "planning_state": planning, "source": "runtime_instance"}
