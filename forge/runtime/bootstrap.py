"""Deterministic Forge Runtime Database bootstrap and recovery.

This module deliberately discovers database *locations*, never operational
state.  Once a database is selected, every recovery projection comes from the
persisted Runtime Database and not from repository source or legacy stores.
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


class RuntimeResolutionError(RuntimeError):
    """A canonical Runtime Database location cannot be determined safely."""


@dataclass(frozen=True)
class RuntimeIdentity:
    """Persisted identity for one Forge runtime, independent of a worktree."""

    runtime_id: str
    repository_identity: str
    repository_root: str
    database_version: str
    database_location: str
    created_at: str
    last_access_at: str
    status: str

    @classmethod
    def from_metadata(cls, metadata: dict[str, str]) -> "RuntimeIdentity":
        return cls(**{field: metadata[field] for field in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}


@dataclass(frozen=True)
class RuntimeLocation:
    path: Path
    source: str
    bootstrap: bool


def canonical_repository_root(repository_root: Path | str) -> Path:
    """Return the shared repository root for a main checkout or worktree."""
    root = Path(repository_root)
    try:
        common_dir = subprocess.check_output(
            ("git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"),
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return root
    return Path(common_dir).resolve().parent


def repository_identity(repository_root: Path | str) -> str:
    root = canonical_repository_root(repository_root).resolve()
    return "forge-repository-" + hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:24]


class RuntimeResolver:
    """Resolve exactly one canonical Runtime Database, or fail closed."""

    def __init__(self, repository_root: Path | str, *, configured_location: Path | str | None = None) -> None:
        self.repository_root = Path(repository_root).resolve()
        self.canonical_root = canonical_repository_root(self.repository_root)
        self.configured_location = None if configured_location is None else Path(configured_location).expanduser().resolve()

    @property
    def default_location(self) -> Path:
        return self.canonical_root / ".forge" / "runtime.db"

    @property
    def registry_path(self) -> Path:
        # Git common metadata survives normal repository cleanup and is shared
        # by worktrees.  Non-Git test/workspace roots retain a local registry.
        git_dir = self.canonical_root / ".git"
        return (git_dir / "forge-runtime-location.json") if git_dir.exists() else (self.canonical_root / ".forge" / "runtime-location.json")

    def resolve(self) -> RuntimeLocation:
        candidates: dict[Path, str] = {}
        registered = self._registered_location()
        for path, source in ((self.configured_location, "configured"), (registered, "registered"), (self.default_location, "repository_default")):
            if path is not None and path.is_file():
                candidates[path.resolve()] = source
        forge_dir = self.canonical_root / ".forge"
        if forge_dir.is_dir():
            for candidate in forge_dir.rglob("runtime*.db"):
                if candidate.is_file():
                    candidates.setdefault(candidate.resolve(), "discovery")
        if len(candidates) > 1:
            raise RuntimeResolutionError("multiple Runtime Database candidates found; explicit relocation is required")
        if candidates:
            path, source = next(iter(candidates.items()))
            self._validate_candidate_identity(path)
            self._register(path)
            return RuntimeLocation(path, source, False)
        target = self.configured_location or registered or self.default_location
        return RuntimeLocation(target, "configured" if self.configured_location else "repository_default", True)

    def relocate(self, destination: Path | str) -> RuntimeLocation:
        """Atomically validate and activate a copy while preserving Runtime ID."""
        source = self.resolve()
        if source.bootstrap:
            raise RuntimeResolutionError("cannot relocate a Runtime Database that has not been bootstrapped")
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
            activated = RuntimeDatabase(self.repository_root, path=destination_path)
            try:
                activated.validate_integrity()
            finally:
                activated.close()
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

    def _registered_location(self) -> Path | None:
        if not self.registry_path.is_file():
            return None
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
            if payload.get("repository_identity") != repository_identity(self.repository_root):
                raise RuntimeResolutionError("runtime registry belongs to a different repository")
            location = payload.get("database_location")
            return Path(location).expanduser().resolve() if isinstance(location, str) else None
        except json.JSONDecodeError as error:
            raise RuntimeResolutionError("runtime registry is malformed") from error

    def _register(self, location: Path) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"repository_identity": repository_identity(self.repository_root), "database_location": str(location.resolve())}, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self.registry_path)

    def _validate_candidate_identity(self, path: Path) -> None:
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                rows = connection.execute("SELECT key, value FROM runtime_metadata").fetchall()
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise RuntimeResolutionError("runtime candidate is not a readable Forge Runtime Database") from error
        metadata = dict(rows)
        candidate_identity = metadata.get("repository_identity")
        if candidate_identity is not None and candidate_identity != repository_identity(self.repository_root):
            raise RuntimeResolutionError("runtime candidate belongs to a different repository")


class RuntimeBootstrap:
    """Open the resolved Runtime Database only after deterministic resolution."""

    def __init__(self, repository_root: Path | str, *, configured_location: Path | str | None = None,
                 forge_version: str = "0.0") -> None:
        self.resolver = RuntimeResolver(repository_root, configured_location=configured_location)
        self.forge_version = forge_version

    def open(self):
        from .database import RuntimeDatabase
        location = self.resolver.resolve()
        database = RuntimeDatabase(self.resolver.repository_root, path=location.path, forge_version=self.forge_version)
        self.resolver._register(database.path)
        return database


class RuntimeRecovery:
    """Runtime-only recovery projections; no source or legacy-store reconstruction."""

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
        return {"runtime_identity": self._database.runtime_identity.to_dict(), "mission_state": documents("mission_state"),
                "architecture_reviews": documents("architecture_reviews"), "mission_recommendations": documents("mission_recommendations"),
                "decision_evidence": documents("decision_evidence"), "execution_receipts": receipts,
                "planning_state": planning, "source": "runtime_database"}
