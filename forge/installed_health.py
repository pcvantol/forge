"""Bounded, read-only assessment of one installed Forge runtime.

The component inventory is a packaged, versioned registry. Runtime evidence is
collected only from the installation marker and a query-only SQLite snapshot;
the collector never initializes storage, invokes a provider, or reads Mission
or execution records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from importlib.resources import files
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from time import monotonic
from typing import Any, Callable, Mapping

from ._version import canonical_version
from .runtime.data_root import DataRootResolver
from .runtime.database import RUNTIME_SCHEMA_VERSION
from .runtime.health import (
    CheckApplicability,
    CheckPurpose,
    HealthCheckDefinition,
    HealthIdentity,
    HealthObservation,
    ObservationFreshness,
    ObservationState,
    evaluate_health,
)


HEALTH_REGISTRY_RESOURCE = "installed-health-component-registry-1.0.json"
HEALTH_REGISTRY_SCHEMA = "1.0"
HEALTH_PROFILE_REFERENCE = "validation-profile-registry:FULL@1.0"
HEALTH_CAPABILITY_SCOPE = ("installed_health",)
MAX_HEALTH_SNAPSHOT_BYTES = 128 * 1024 * 1024
MAX_HEALTH_REGISTRY_BYTES = 64 * 1024
MAX_RUNTIME_MARKER_BYTES = 1024
_REGISTRY_FIELDS = frozenset((
    "schema_version", "registry_id", "registry_version", "profile_reference", "checks",
))
_CHECK_FIELDS = frozenset((
    "component_id", "check_id", "purpose", "applicability", "freshness_timeout_seconds",
    "capabilities", "enabled", "observation_source",
))


class InstalledHealthError(RuntimeError):
    """Safe failure emitted by the installed-health boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class InstalledHealthRegistry:
    registry_id: str
    registry_version: str
    profile_reference: str
    definitions: tuple[HealthCheckDefinition, ...]
    observation_sources: Mapping[str, str]
    digest: str

    @classmethod
    def load(
        cls,
        document: Mapping[str, Any] | None = None,
        *,
        deadline: float | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> "InstalledHealthRegistry":
        if document is None:
            resource = files("forge").joinpath("api", HEALTH_REGISTRY_RESOURCE)
            try:
                if deadline is not None:
                    _require_before_deadline(deadline, monotonic_clock)
                with resource.open("rb") as reader:
                    encoded = reader.read(MAX_HEALTH_REGISTRY_BYTES + 1)
                if deadline is not None:
                    _require_before_deadline(deadline, monotonic_clock)
                if len(encoded) > MAX_HEALTH_REGISTRY_BYTES:
                    raise InstalledHealthError(
                        "HEALTH_REGISTRY_LIMIT", "Installed health registry exceeds the snapshot limit",
                    )
                document = json.loads(encoded.decode("utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise InstalledHealthError(
                    "HEALTH_REGISTRY_UNAVAILABLE", "Installed health registry is unavailable",
                ) from error
        if not isinstance(document, Mapping) or set(document) != _REGISTRY_FIELDS:
            raise InstalledHealthError("HEALTH_REGISTRY_INVALID", "Installed health registry is invalid")
        if document.get("schema_version") != HEALTH_REGISTRY_SCHEMA:
            raise InstalledHealthError(
                "HEALTH_REGISTRY_SCHEMA_UNSUPPORTED", "Installed health registry schema is unsupported",
            )
        if (
            document.get("registry_id") != "forge-installed-health"
            or document.get("registry_version") != "1.0"
            or document.get("profile_reference") != HEALTH_PROFILE_REFERENCE
        ):
            raise InstalledHealthError("HEALTH_REGISTRY_INVALID", "Installed health registry is invalid")
        checks = document.get("checks")
        if not isinstance(checks, list) or not checks:
            raise InstalledHealthError("HEALTH_REGISTRY_INVALID", "Installed health registry is invalid")
        definitions: list[HealthCheckDefinition] = []
        sources: dict[str, str] = {}
        try:
            for item in checks:
                if not isinstance(item, Mapping) or set(item) != _CHECK_FIELDS:
                    raise ValueError("invalid check shape")
                timeout = item["freshness_timeout_seconds"]
                if not isinstance(timeout, int) or isinstance(timeout, bool) or not 0 < timeout <= 300:
                    raise ValueError("invalid timeout")
                source = item["observation_source"]
                if source not in {
                    "installed_process", "runtime_metadata", "sqlite_integrity_check", "dispatcher_state",
                    "operational_reset_state",
                }:
                    raise ValueError("invalid source")
                definition = HealthCheckDefinition(
                    component_id=item["component_id"],
                    check_id=item["check_id"],
                    purpose=CheckPurpose(item["purpose"]),
                    applicability=CheckApplicability(item["applicability"]),
                    freshness_timeout=timedelta(seconds=timeout),
                    capabilities=tuple(item["capabilities"]),
                    enabled=item["enabled"],
                )
                definitions.append(definition)
                sources[definition.check_id] = source
        except (KeyError, TypeError, ValueError) as error:
            raise InstalledHealthError("HEALTH_REGISTRY_INVALID", "Installed health registry is invalid") from error
        canonical = json.dumps(dict(document), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return cls(
            str(document["registry_id"]),
            str(document["registry_version"]),
            str(document["profile_reference"]),
            tuple(definitions),
            sources,
            "sha256:" + sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def provenance(self) -> dict[str, str]:
        return {
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "schema_version": HEALTH_REGISTRY_SCHEMA,
            "profile_reference": self.profile_reference,
            "digest": self.digest,
        }


class InstalledHealthSnapshotService:
    """Collect one current-revision assessment without mutating the runtime."""

    def __init__(
        self,
        data_root: str | Path,
        *,
        registry: InstalledHealthRegistry | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        timeout_seconds: float = 2.0,
        statement_observer: Callable[[str], None] | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 0 < float(timeout_seconds) <= 5
        ):
            raise ValueError("health snapshot timeout must be greater than zero and at most five seconds")
        self.data_root = data_root
        self.supplied_registry = registry
        self.clock = clock
        self.timeout_seconds = float(timeout_seconds)
        self.statement_observer = statement_observer
        self.monotonic_clock = monotonic_clock

    def installed_health_snapshot(self) -> dict[str, Any]:
        deadline = self.monotonic_clock() + self.timeout_seconds
        root = DataRootResolver(cli_data_root=self.data_root).resolve()
        _require_before_deadline(deadline, self.monotonic_clock)
        registry = self.supplied_registry or InstalledHealthRegistry.load(
            deadline=deadline, monotonic_clock=self.monotonic_clock,
        )
        _require_before_deadline(deadline, self.monotonic_clock)
        evaluated_at = self.clock()
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("health snapshot clock must be timezone-aware")
        evaluated_at = evaluated_at.astimezone(UTC)
        _require_before_deadline(deadline, self.monotonic_clock)
        database = root / "forge.db"
        marker_path = root / "instance" / "runtime-instance.json"
        if not database.is_file() or not marker_path.is_file():
            raise InstalledHealthError("HEALTH_RUNTIME_MISSING", "Installed Forge runtime is unavailable")
        _require_before_deadline(deadline, self.monotonic_clock)

        connection: sqlite3.Connection | None = None
        snapshot_copy: TemporaryDirectory[str] | None = None
        integrity_observations = 0
        source_snapshot = "direct_immutable"
        try:
            sidecars = tuple(Path(str(database) + suffix) for suffix in ("-wal", "-shm"))
            before = _storage_fingerprint(database, sidecars, deadline, self.monotonic_clock)
            if any(path.exists() for path in sidecars):
                source_snapshot = "bounded_sidecar_copy"
                wal = Path(str(database) + "-wal")
                _require_before_deadline(deadline, self.monotonic_clock)
                source_bytes = database.stat().st_size + (wal.stat().st_size if wal.exists() else 0)
                _require_before_deadline(deadline, self.monotonic_clock)
                if source_bytes > MAX_HEALTH_SNAPSHOT_BYTES:
                    raise InstalledHealthError(
                        "HEALTH_SNAPSHOT_LIMIT", "Installed Forge storage exceeds the health snapshot limit",
                    )
                snapshot_copy = TemporaryDirectory(prefix="forge-installed-health-")
                copied_database = Path(snapshot_copy.name) / "forge.db"
                _bounded_copy(database, copied_database, deadline, self.monotonic_clock)
                if wal.exists():
                    _bounded_copy(wal, Path(str(copied_database) + "-wal"), deadline, self.monotonic_clock)
                if _storage_fingerprint(database, sidecars, deadline, self.monotonic_clock) != before:
                    raise InstalledHealthError(
                        "HEALTH_RUNTIME_CHANGED", "Installed Forge storage changed during assessment",
                    )
                uri = copied_database.resolve().as_uri() + "?mode=rw"
            else:
                uri = database.resolve().as_uri() + "?mode=ro&immutable=1"
            connection = sqlite3.connect(uri, uri=True, timeout=0)
            _require_before_deadline(deadline, self.monotonic_clock)
            if self.statement_observer is not None:
                connection.set_trace_callback(self.statement_observer)
            connection.set_progress_handler(lambda: int(monotonic() >= deadline), 1000)
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            metadata = dict(connection.execute("SELECT key, value FROM runtime_metadata"))
            dispatcher_row = connection.execute(
                "SELECT status FROM dispatcher_state WHERE singleton = 1"
            ).fetchone()
            dispatcher = "IDLE" if dispatcher_row is None else str(dispatcher_row[0])
            maintenance_row = connection.execute(
                "SELECT active_operation_id, state FROM operational_reset_state WHERE singleton = 1"
            ).fetchone()
            if maintenance_row is None:
                raise InstalledHealthError(
                    "HEALTH_MAINTENANCE_UNREADABLE", "Installed Forge maintenance state is unavailable",
                )
            maintenance_active = maintenance_row[0] is not None
            maintenance_state = str(maintenance_row[1])
            try:
                schema = int(metadata["schema_version"])
                migration = int(metadata["migration_version"])
                user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            except (KeyError, TypeError, ValueError, IndexError):
                raise InstalledHealthError(
                    "HEALTH_SCHEMA_UNREADABLE", "Installed Forge storage schema is unreadable",
                ) from None
            if schema > RUNTIME_SCHEMA_VERSION or migration > RUNTIME_SCHEMA_VERSION or user_version > RUNTIME_SCHEMA_VERSION:
                raise InstalledHealthError(
                    "HEALTH_SCHEMA_FORWARD", "Installed Forge storage schema is newer than this reader",
                )
            if not (schema == migration == user_version == RUNTIME_SCHEMA_VERSION):
                raise InstalledHealthError(
                    "HEALTH_SCHEMA_UNSUPPORTED", "Installed Forge storage schema is unsupported",
                )
            runtime_id = metadata.get("runtime_id", "")
            marker = _bounded_marker(marker_path, deadline, self.monotonic_clock)
            if not runtime_id or marker != runtime_id:
                raise InstalledHealthError(
                    "HEALTH_IDENTITY_INCONSISTENT", "Installed Forge runtime identity is inconsistent",
                )
            installation_id = metadata.get("installation_id")
            if not installation_id:
                raise InstalledHealthError(
                    "HEALTH_IDENTITY_INCOMPLETE", "Installed Forge installation identity is unavailable",
                )
            binding_ids = tuple(
                str(row[0]) for row in connection.execute(
                    "SELECT DISTINCT installation_id FROM installation_operator_binding "
                    "ORDER BY installation_id LIMIT 2"
                )
            )
            if len(binding_ids) > 1 or (binding_ids and binding_ids[0] != installation_id):
                raise InstalledHealthError(
                    "HEALTH_IDENTITY_INCONSISTENT", "Installed Forge installation identity is inconsistent",
                )
            identity = HealthIdentity(canonical_version(), runtime_id, installation_id)

            integrity_observations += 1
            try:
                integrity = connection.execute("PRAGMA integrity_check(1)").fetchone()
                integrity_state = (
                    ObservationState.PASS
                    if integrity is not None and integrity[0] == "ok"
                    else ObservationState.FAIL
                )
                integrity_reason = None if integrity_state is ObservationState.PASS else "SQLITE_INTEGRITY_FAILED"
            except sqlite3.OperationalError as error:
                if "interrupt" not in str(error).lower():
                    raise
                integrity_state = ObservationState.TIMED_OUT
                integrity_reason = "SQLITE_INTEGRITY_TIMED_OUT"
            finally:
                connection.set_progress_handler(None, 0)

            observations = self._observations(
                identity,
                metadata,
                dispatcher,
                maintenance_active,
                maintenance_state,
                evaluated_at,
                integrity_state,
                integrity_reason,
            )
            evaluation = evaluate_health(
                identity,
                registry.definitions,
                observations,
                capability_scope=HEALTH_CAPABILITY_SCOPE,
                evaluated_at=evaluated_at,
            )
            if _bounded_marker(marker_path, deadline, self.monotonic_clock) != runtime_id:
                raise InstalledHealthError(
                    "HEALTH_IDENTITY_CHANGED", "Installed Forge runtime identity changed during assessment",
                )
            if _storage_fingerprint(database, sidecars, deadline, self.monotonic_clock) != before:
                raise InstalledHealthError(
                    "HEALTH_RUNTIME_CHANGED", "Installed Forge storage changed during assessment",
                )
            _require_before_deadline(deadline, self.monotonic_clock)
        except InstalledHealthError:
            raise
        except (OSError, sqlite3.Error, ValueError) as error:
            raise InstalledHealthError(
                "HEALTH_SNAPSHOT_UNAVAILABLE", "Installed health snapshot is unavailable",
            ) from error
        finally:
            if connection is not None:
                connection.close()
            if snapshot_copy is not None:
                snapshot_copy.cleanup()

        result = evaluation.to_dict()
        result.update({
            "api_version": "1",
            "outcome": _outcome(evaluation.checks),
            "read_only": True,
            "registry": registry.provenance(),
            "observation_provenance": {
                "collector": "installed-runtime-read-only",
                "bounded": True,
                "integrity_observation_count": integrity_observations,
                "timeout_seconds": self.timeout_seconds,
                "registry_byte_limit": MAX_HEALTH_REGISTRY_BYTES,
                "snapshot_byte_limit": MAX_HEALTH_SNAPSHOT_BYTES,
                "runtime_marker_byte_limit": MAX_RUNTIME_MARKER_BYTES,
                "source_snapshot": source_snapshot,
                "sources": dict(sorted(registry.observation_sources.items())),
            },
        })
        return result

    def _observations(
        self,
        identity: HealthIdentity,
        metadata: Mapping[str, str],
        dispatcher: str | None,
        maintenance_active: bool,
        maintenance_state: str,
        evaluated_at: datetime,
        integrity_state: ObservationState,
        integrity_reason: str | None,
    ) -> tuple[HealthObservation, ...]:
        observations = [HealthObservation(
            identity,
            "forge_server",
            "installed_api",
            CheckPurpose.LIVENESS,
            (),
            ObservationState.PASS,
            evaluated_at,
        )]
        observed_at = _parse_observed_at(metadata.get("last_access_at"))
        if observed_at is not None:
            runtime_state = ObservationState.PASS if metadata.get("status") == "active" else ObservationState.FAIL
            observations.append(HealthObservation(
                identity,
                "forge_runtime",
                "runtime_state",
                CheckPurpose.READINESS,
                HEALTH_CAPABILITY_SCOPE,
                runtime_state,
                observed_at,
                reason_code=None if runtime_state is ObservationState.PASS else "RUNTIME_NOT_ACTIVE",
            ))
            dispatcher_state = ObservationState.PASS if dispatcher in {"IDLE", "ACTIVE"} else ObservationState.UNKNOWN
            observations.append(HealthObservation(
                identity,
                "forge_dispatcher",
                "dispatcher_state",
                CheckPurpose.READINESS,
                HEALTH_CAPABILITY_SCOPE,
                dispatcher_state,
                observed_at,
                reason_code=None if dispatcher_state is ObservationState.PASS else "DISPATCHER_STATE_UNKNOWN",
            ))
        observations.append(HealthObservation(
            identity,
            "forge_runtime",
            "operational_reset_maintenance",
            CheckPurpose.READINESS,
            HEALTH_CAPABILITY_SCOPE,
            ObservationState.FAIL if maintenance_active or maintenance_state != "IDLE" else ObservationState.PASS,
            evaluated_at,
            reason_code=(
                "OPERATIONAL_RESET_MAINTENANCE_ACTIVE"
                if maintenance_active or maintenance_state != "IDLE"
                else None
            ),
        ))
        observations.append(HealthObservation(
            identity,
            "forge_storage",
            "sqlite_integrity",
            CheckPurpose.READINESS,
            HEALTH_CAPABILITY_SCOPE,
            integrity_state,
            evaluated_at,
            reason_code=integrity_reason,
        ))
        return tuple(observations)


def _parse_observed_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _require_before_deadline(deadline: float, monotonic_clock: Callable[[], float]) -> None:
    if monotonic_clock() >= deadline:
        raise InstalledHealthError(
            "HEALTH_SNAPSHOT_TIMED_OUT", "Installed health snapshot timed out",
        )


def _bounded_marker(
    path: Path,
    deadline: float,
    monotonic_clock: Callable[[], float],
) -> str:
    _require_before_deadline(deadline, monotonic_clock)
    if path.stat().st_size > MAX_RUNTIME_MARKER_BYTES:
        raise InstalledHealthError(
            "HEALTH_IDENTITY_LIMIT", "Installed Forge runtime identity marker exceeds the health snapshot limit",
        )
    _require_before_deadline(deadline, monotonic_clock)
    with path.open("rb") as reader:
        _require_before_deadline(deadline, monotonic_clock)
        encoded = reader.read(MAX_RUNTIME_MARKER_BYTES + 1)
        _require_before_deadline(deadline, monotonic_clock)
    if len(encoded) > MAX_RUNTIME_MARKER_BYTES:
        raise InstalledHealthError(
            "HEALTH_IDENTITY_LIMIT", "Installed Forge runtime identity marker exceeds the health snapshot limit",
        )
    try:
        return encoded.decode("utf-8").strip()
    except UnicodeError as error:
        raise InstalledHealthError(
            "HEALTH_IDENTITY_INCONSISTENT", "Installed Forge runtime identity is inconsistent",
        ) from error


def _storage_fingerprint(
    database: Path,
    sidecars: tuple[Path, ...],
    deadline: float,
    monotonic_clock: Callable[[], float],
) -> tuple[tuple[str, int, int] | None, ...]:
    result: list[tuple[str, int, int] | None] = []
    for path in (database, *sidecars):
        _require_before_deadline(deadline, monotonic_clock)
        try:
            stat = path.stat()
        except FileNotFoundError:
            result.append(None)
        else:
            result.append((path.name, stat.st_size, stat.st_mtime_ns))
        _require_before_deadline(deadline, monotonic_clock)
    return tuple(result)


def _bounded_copy(
    source: Path,
    target: Path,
    deadline: float,
    monotonic_clock: Callable[[], float],
) -> None:
    _require_before_deadline(deadline, monotonic_clock)
    if source.stat().st_size > MAX_HEALTH_SNAPSHOT_BYTES:
        raise InstalledHealthError(
            "HEALTH_SNAPSHOT_LIMIT", "Installed Forge storage exceeds the health snapshot limit",
        )
    copied = 0
    with source.open("rb") as reader, target.open("xb") as writer:
        while True:
            _require_before_deadline(deadline, monotonic_clock)
            chunk = reader.read(1024 * 1024)
            _require_before_deadline(deadline, monotonic_clock)
            if not chunk:
                break
            copied += len(chunk)
            if copied > MAX_HEALTH_SNAPSHOT_BYTES:
                raise InstalledHealthError(
                    "HEALTH_SNAPSHOT_LIMIT", "Installed Forge storage exceeds the health snapshot limit",
                )
            writer.write(chunk)
            _require_before_deadline(deadline, monotonic_clock)


def _outcome(checks: tuple[Any, ...]) -> str:
    if any(item.state.value == "FAIL" for item in checks):
        return "FAILED"
    freshness = {item.freshness for item in checks}
    for value in (
        ObservationFreshness.TIMED_OUT,
        ObservationFreshness.EXPIRED,
        ObservationFreshness.STALE,
        ObservationFreshness.FUTURE,
        ObservationFreshness.MISSING,
    ):
        if value in freshness:
            return value.value
    if any(item.state.value == "UNKNOWN" for item in checks):
        return "UNKNOWN"
    if any(item.state.value != "PASS" for item in checks):
        return "UNKNOWN"
    return "HEALTHY"


def installed_health_snapshot(
    data_root: str | Path,
    *,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """Public one-shot installed-health entrypoint used by CLI and HTTP."""
    return InstalledHealthSnapshotService(
        data_root, timeout_seconds=timeout_seconds,
    ).installed_health_snapshot()
