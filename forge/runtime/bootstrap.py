"""Persistent Runtime Instance resolution, bootstrap, and recovery.

The Runtime Database is storage owned by a Runtime Instance; it is never the
identity of that instance. Resolution uses the product-owned data root and
validates every persisted boundary before SQLite is opened.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from .data_root import DataRootResolver, RUNTIME_DIRECTORIES

try:
    import fcntl
except ImportError:  # pragma: no cover - supported Forge hosts are POSIX.
    fcntl = None


RUNTIME_INSTANCE_VERSION = "1"
RUNTIME_INITIALIZATION_VERSION = "1"


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
    initialization_version: str
    repository_uuid: str | None
    created_at: str
    database_location: str
    last_access_at: str
    status: str

    @classmethod
    def from_metadata(cls, metadata: dict[str, str]) -> "RuntimeIdentity":
        required = ("runtime_id", "repository_identity", "repository_root", "created_at", "initialization_version")
        if any(not metadata.get(key) for key in required):
            raise RuntimeResolutionError("runtime identity metadata is incomplete")
        return cls(metadata["runtime_id"], metadata["repository_identity"], metadata["repository_root"],
                   metadata.get("instance_version", RUNTIME_INSTANCE_VERSION), metadata["initialization_version"],
                   metadata.get("repository_uuid") or None, metadata["created_at"],
                   metadata.get("database_location", ""), metadata.get("last_access_at", ""), metadata.get("status", ""))

    @property
    def repository_id(self) -> str:
        return self.repository_identity

    @property
    def database_version(self) -> str:
        return self.instance_version

    def to_dict(self) -> dict[str, str]:
        result = {"runtime_id": self.runtime_id, "repository_identity": self.repository_identity,
                "repository_id": self.repository_identity, "repository_root": self.repository_root,
                "instance_version": self.instance_version, "database_version": self.instance_version,
                "initialization_version": self.initialization_version,
                "created_at": self.created_at, "database_location": self.database_location,
                "last_access_at": self.last_access_at, "status": self.status}
        if self.repository_uuid is not None:
            result["repository_uuid"] = self.repository_uuid
        return result


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


def repository_uuid(repository_root: Path | str) -> str | None:
    """Return an explicitly configured repository UUID when the host provides one."""
    try:
        value = subprocess.check_output(
            ("git", "-C", str(canonical_repository_root(repository_root)), "config", "--get", "forge.repositoryUUID"),
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return value or None


class RuntimeResolver:
    """Resolve one installed Forge instance beneath the product-owned data root.

    ``repository_root`` remains an API-compatibility argument only.  It is not
    consulted for location, identity, discovery, or writes.
    """

    def __init__(self, repository_root: Path | str = ".", *, configured_location: Path | str | None = None,
                 configured_runtime_root: Path | str | None = None, data_root: Path | str | None = None,
                 environment: dict[str, str] | None = None) -> None:
        self.repository_root = Path(repository_root).resolve()
        if configured_location is not None and (configured_runtime_root is not None or data_root is not None):
            raise RuntimeResolutionError("choose a data root or an explicit database location, not both")
        explicit_root = data_root if data_root is not None else configured_runtime_root
        # Supplying a path to the long-standing library API is an explicit
        # test/embedder root, never an inferred checkout location. Installed
        # entrypoints use ``data_root`` (or the resolver default) instead.
        self.compatibility_workspace = explicit_root is None and configured_location is None and repository_root != "."
        self.data_root = (Path(repository_root).expanduser().resolve() if self.compatibility_workspace
                          else Path(configured_location).expanduser().resolve().parent if configured_location is not None
                          else DataRootResolver(cli_data_root=explicit_root, environment=environment).resolve())
        self.configured_location = None if configured_location is None else Path(configured_location).expanduser().resolve()

    @property
    def default_location(self) -> Path:
        return self.data_root / "forge.db"

    @property
    def instance_marker_path(self) -> Path:
        return self.data_root / "instance" / "runtime-instance.json"

    @property
    def initialization_lock_path(self) -> Path:
        return self.data_root / "locks" / "runtime.lock"

    def resolve(self) -> RuntimeLocation:
        path = self.configured_location or self.default_location
        if path.is_file():
            return RuntimeLocation(path.resolve(), "configured" if self.configured_location else "data_root", False)
        if self.configured_location is None and self.instance_marker_path.exists():
            raise RuntimeResolutionError("initialized Forge data root is missing forge.db")
        return RuntimeLocation(path, "configured" if self.configured_location else "data_root", True)


class RuntimeBootstrap:
    """Discover an existing Runtime Instance or create exactly one new instance."""

    def __init__(self, repository_root: Path | str = ".", *, configured_location: Path | str | None = None,
                 configured_runtime_root: Path | str | None = None, data_root: Path | str | None = None,
                 environment: dict[str, str] | None = None, forge_version: str = "0.0") -> None:
        self.resolver = RuntimeResolver(repository_root, configured_location=configured_location,
                                        configured_runtime_root=configured_runtime_root, data_root=data_root, environment=environment)
        self.forge_version = forge_version

    def open(self):
        from .database import RuntimeDatabase
        if fcntl is None:
            raise RuntimeResolutionError("Runtime Instance initialization lock is unavailable")
        self._create_root_layout()
        with self.resolver.initialization_lock_path.open("a+", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeResolutionError("another mutating Forge runtime owns this data root") from error
            try:
                location = self.resolver.resolve()
                database = RuntimeDatabase(self.resolver.repository_root, path=location.path, forge_version=self.forge_version,
                                          installation_scoped=not self.resolver.compatibility_workspace)
                try:
                    marker = self.resolver.instance_marker_path
                    temporary = marker.with_suffix(".tmp")
                    temporary.write_text(database.runtime_identity.runtime_id + "\n", encoding="utf-8")
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, marker)
                except Exception:
                    database.close()
                    raise
                return database
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _create_root_layout(self) -> None:
        root = self.resolver.data_root
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        for name in RUNTIME_DIRECTORIES:
            directory = root / name
            directory.mkdir(exist_ok=True)
            os.chmod(directory, 0o700)


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
