"""Authoritative bounded read-only health snapshot for an installed Forge."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import time
from typing import Callable

from ._version import canonical_version
from .execution_host_configuration import (
    EngineeringPlatformPeerConfigurationStore,
    PeerConfigurationError,
)
from .runtime.component_registry import (
    CANONICAL_COMPONENT_REGISTRY,
    ComponentRegistry,
)
from .runtime.data_root import DataRootResolver
from .runtime.health import (
    HealthEvaluation,
    HealthIdentity,
    HealthObservation,
    HealthState,
    ObservationState,
    evaluate_health,
)


HEALTH_SNAPSHOT_API_VERSION = "1"
DEFAULT_HEALTH_DEADLINE_SECONDS = 2.0
DEFAULT_HEALTH_SQL_STEP_LIMIT = 250_000
HEALTH_CAPABILITY_SCOPE = ("dispatch", "local_work")
_METADATA_KEYS = (
    "installation_id",
    "migration_version",
    "runtime_id",
    "schema_version",
    "status",
)
_MAX_IDENTITY_TEXT = 256
_MAX_PEER_DOCUMENT_BYTES = 65_536


class InstalledHealthError(RuntimeError):
    """One safe, non-sensitive installed-health failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HealthSnapshot:
    evaluation: HealthEvaluation
    component_registry_revision: str
    component_ids: tuple[str, ...]
    deadline_seconds: float
    observation_limit: int
    integrity_observations: int

    def to_dict(self) -> dict[str, object]:
        document = self.evaluation.to_dict()
        document.update({
            "api_version": HEALTH_SNAPSHOT_API_VERSION,
            "availability": (
                "AVAILABLE"
                if self.evaluation.state in {HealthState.HEALTHY, HealthState.DEGRADED}
                else "UNAVAILABLE"
            ),
            "component_registry_revision": self.component_registry_revision,
            "component_ids": list(self.component_ids),
            "source_observed_at": document["evaluated_at"],
            "read_only": True,
            "bounds": {
                "deadline_seconds": self.deadline_seconds,
                "observation_limit": self.observation_limit,
                "integrity_observations": self.integrity_observations,
            },
        })
        return document


class InstalledHealthSnapshotService:
    """Collect one bounded observation set from one installed SQLite snapshot."""

    def __init__(
        self,
        data_root: str | Path,
        *,
        registry: ComponentRegistry = CANONICAL_COMPONENT_REGISTRY,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        deadline_seconds: float = DEFAULT_HEALTH_DEADLINE_SECONDS,
        sql_step_limit: int = DEFAULT_HEALTH_SQL_STEP_LIMIT,
    ) -> None:
        if not isinstance(registry, ComponentRegistry):
            raise ValueError("a typed component registry is required")
        if (
            not isinstance(deadline_seconds, (int, float))
            or isinstance(deadline_seconds, bool)
            or not 0 < float(deadline_seconds) <= 10
        ):
            raise ValueError("health deadline must be greater than zero and at most 10 seconds")
        if (
            not isinstance(sql_step_limit, int)
            or isinstance(sql_step_limit, bool)
            or not 1_000 <= sql_step_limit <= 1_000_000
        ):
            raise ValueError("health SQL step limit is invalid")
        self.root = DataRootResolver(cli_data_root=data_root).resolve()
        self.registry = registry
        self.clock = clock
        self.monotonic = monotonic
        self.deadline_seconds = float(deadline_seconds)
        self.sql_step_limit = sql_step_limit

    def snapshot(self) -> HealthSnapshot:
        observed_at = self.clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise InstalledHealthError("HEALTH_CLOCK_INVALID", "Installed health clock is unavailable")
        observed_at = observed_at.astimezone(UTC)
        started = self.monotonic()
        database = self.root / "forge.db"
        marker = self.root / "instance" / "runtime-instance.json"
        if not database.is_file() or not marker.is_file():
            raise InstalledHealthError(
                "INSTALLED_HEALTH_UNAVAILABLE",
                "Installed Forge health is unavailable",
            )

        connection: sqlite3.Connection | None = None
        integrity_observations = 0
        sql_steps = 0

        def bounded() -> int:
            nonlocal sql_steps
            sql_steps += 1_000
            if sql_steps > self.sql_step_limit:
                return 1
            return int(self.monotonic() - started >= self.deadline_seconds)

        try:
            connection = sqlite3.connect(
                database.resolve().as_uri() + "?mode=ro&immutable=1",
                uri=True,
                timeout=min(self.deadline_seconds, 1.0),
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            connection.set_progress_handler(bounded, 1_000)
            connection.execute("BEGIN")

            integrity_observations += 1
            integrity = connection.execute("PRAGMA quick_check(1)").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise InstalledHealthError(
                    "INSTALLED_HEALTH_UNAVAILABLE",
                    "Installed Forge health is unavailable",
                )

            placeholders = ",".join("?" for _ in _METADATA_KEYS)
            rows = connection.execute(
                f"SELECT key, value FROM runtime_metadata "
                f"WHERE key IN ({placeholders}) AND length(value) <= ? LIMIT ?",
                (*_METADATA_KEYS, _MAX_IDENTITY_TEXT, len(_METADATA_KEYS) + 1),
            ).fetchall()
            metadata = {str(row["key"]): str(row["value"]) for row in rows}
            if set(metadata) != set(_METADATA_KEYS):
                raise InstalledHealthError(
                    "INSTALLATION_IDENTITY_UNAVAILABLE",
                    "Installed Forge identity is unavailable",
                )
            try:
                schema = int(metadata["schema_version"])
                migration = int(metadata["migration_version"])
                user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            except (TypeError, ValueError):
                raise InstalledHealthError(
                    "INSTALLED_HEALTH_UNAVAILABLE",
                    "Installed Forge health is unavailable",
                ) from None
            runtime_id = metadata["runtime_id"]
            if schema != migration or schema != user_version or self._marker_identity(marker) != runtime_id:
                raise InstalledHealthError(
                    "INSTALLATION_IDENTITY_MISMATCH",
                    "Installed Forge identity is inconsistent",
                )

            identity = HealthIdentity(
                canonical_version(),
                runtime_id,
                metadata["installation_id"],
            )
            dispatcher_rows = connection.execute(
                "SELECT status FROM dispatcher_state WHERE singleton = 1 LIMIT 2"
            ).fetchall()
            dispatcher_status = "IDLE" if not dispatcher_rows else str(dispatcher_rows[0]["status"])
            dispatcher_valid = len(dispatcher_rows) <= 1 and dispatcher_status in {"IDLE", "ACTIVE"}

            peer_state = ObservationState.FAIL
            peer_reason = "PEER_NOT_CONFIGURED"
            try:
                peer_sizes = connection.execute(
                    "SELECT length(document) FROM execution_host_peer_configuration LIMIT 2"
                ).fetchall()
                if len(peer_sizes) > 1 or any(
                    row[0] is None or int(row[0]) > _MAX_PEER_DOCUMENT_BYTES
                    for row in peer_sizes
                ):
                    raise PeerConfigurationError("EP peer configuration exceeds the health read bound")
                peer = EngineeringPlatformPeerConfigurationStore(
                    connection, runtime_id, writable=False,
                ).load()
                if peer is not None:
                    peer_state = ObservationState.PASS
                    peer_reason = None
            except PeerConfigurationError:
                peer_reason = "PEER_CONFIGURATION_INVALID"

            observations = (
                HealthObservation(
                    identity, "forge_server", "server_process",
                    self._definition("server_process").purpose, (),
                    ObservationState.PASS, observed_at,
                ),
                HealthObservation(
                    identity, "platform_database", "runtime_storage",
                    self._definition("runtime_storage").purpose,
                    self._definition("runtime_storage").capabilities,
                    ObservationState.PASS if metadata["status"] == "active" else ObservationState.FAIL,
                    observed_at,
                    reason_code=None if metadata["status"] == "active" else "RUNTIME_NOT_ACTIVE",
                ),
                HealthObservation(
                    identity, "mission_dispatcher", "dispatcher_state",
                    self._definition("dispatcher_state").purpose,
                    self._definition("dispatcher_state").capabilities,
                    ObservationState.PASS if dispatcher_valid else ObservationState.FAIL,
                    observed_at,
                    reason_code=None if dispatcher_valid else "DISPATCHER_STATE_INVALID",
                ),
                HealthObservation(
                    identity, "ep_peer", "execution_peer_binding",
                    self._definition("execution_peer_binding").purpose,
                    self._definition("execution_peer_binding").capabilities,
                    peer_state, observed_at, reason_code=peer_reason,
                ),
            )
            if self.monotonic() - started >= self.deadline_seconds:
                raise InstalledHealthError(
                    "HEALTH_SNAPSHOT_TIMEOUT",
                    "Installed Forge health assessment timed out",
                )
            evaluation = evaluate_health(
                identity,
                self.registry.health_definitions,
                observations,
                capability_scope=HEALTH_CAPABILITY_SCOPE,
                evaluated_at=observed_at,
            )
            return HealthSnapshot(
                evaluation,
                self.registry.schema_revision,
                self.registry.component_ids,
                self.deadline_seconds,
                len(observations),
                integrity_observations,
            )
        except InstalledHealthError:
            raise
        except (OSError, RuntimeError, sqlite3.Error, ValueError):
            code = (
                "HEALTH_SNAPSHOT_TIMEOUT"
                if self.monotonic() - started >= self.deadline_seconds
                else "INSTALLED_HEALTH_UNAVAILABLE"
            )
            message = (
                "Installed Forge health assessment timed out"
                if code == "HEALTH_SNAPSHOT_TIMEOUT"
                else "Installed Forge health is unavailable"
            )
            raise InstalledHealthError(code, message) from None
        finally:
            if connection is not None:
                connection.set_progress_handler(None, 0)
                connection.close()

    def _definition(self, check_id: str):
        for definition in self.registry.health_definitions:
            if definition.check_id == check_id:
                return definition
        raise InstalledHealthError(
            "COMPONENT_REGISTRY_INVALID",
            "Installed Forge component registry is invalid",
        )

    @staticmethod
    def _marker_identity(marker: Path) -> str:
        if marker.stat().st_size > _MAX_IDENTITY_TEXT:
            raise InstalledHealthError(
                "INSTALLATION_IDENTITY_MISMATCH",
                "Installed Forge identity is inconsistent",
            )
        with marker.open("r", encoding="utf-8") as stream:
            value = stream.read(_MAX_IDENTITY_TEXT + 1)
        if len(value) > _MAX_IDENTITY_TEXT:
            raise InstalledHealthError(
                "INSTALLATION_IDENTITY_MISMATCH",
                "Installed Forge identity is inconsistent",
            )
        return value.strip()
