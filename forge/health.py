"""Authoritative, bounded and read-only health of an installed Forge runtime."""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
import sqlite3
import time
from typing import Callable

from ._version import canonical_version
from .component_registry import canonical_component_registry, component_registry_projection
from .runtime.data_root import DataRootResolver
from .runtime.database import RUNTIME_SCHEMA_VERSION
from .runtime.health import (
    CheckApplicability,
    CheckPurpose,
    HealthCheckDefinition,
    HealthIdentity,
    HealthObservation,
    ObservationState,
    evaluate_health,
)


INSTALLED_HEALTH_SNAPSHOT_VERSION = "1.0"
INSTALLED_HEALTH_PROFILE = "FULL@1.0"
INSTALLED_HEALTH_CAPABILITY = "installed_health_snapshot"
INSTALLED_HEALTH_DEADLINE_SECONDS = 1.0
_SQLITE_PROGRESS_STEPS = 1_000


class InstalledHealthError(RuntimeError):
    """A bounded public failure that never includes paths or database details."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def installed_health_definitions() -> tuple[HealthCheckDefinition, ...]:
    """Project the health checks owned by the canonical component registry."""
    return tuple(
        HealthCheckDefinition(
            component.component_id,
            check.check_id,
            CheckPurpose(check.purpose),
            CheckApplicability(check.applicability),
            timedelta(seconds=check.freshness_timeout_seconds),
            check.capabilities,
        )
        for component in canonical_component_registry()
        for check in component.health_checks
    )


class InstalledHealthSnapshotService:
    """Observe one installed database through a single bounded read transaction.

    Exactly one SQLite integrity observation is made.  No bootstrap, migration,
    provider call, peer request, subprocess, or writable connection is used.
    """

    def __init__(
        self,
        data_root: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        maximum_seconds: float = INSTALLED_HEALTH_DEADLINE_SECONDS,
    ) -> None:
        if (
            isinstance(maximum_seconds, bool)
            or not isinstance(maximum_seconds, (int, float))
            or not math.isfinite(maximum_seconds)
            or maximum_seconds <= 0
            or maximum_seconds > INSTALLED_HEALTH_DEADLINE_SECONDS
        ):
            raise ValueError("installed health deadline is invalid")
        self.root = DataRootResolver(cli_data_root=data_root).resolve()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic_clock = monotonic_clock or time.monotonic
        self.maximum_seconds = float(maximum_seconds)

    def snapshot(self) -> dict[str, object]:
        evaluated_at = self.clock()
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError("installed health clock must be timezone-aware")
        evaluated_at = evaluated_at.astimezone(UTC)
        database = self.root / "forge.db"
        marker = self.root / "instance" / "runtime-instance.json"
        if not database.is_file() or not marker.is_file():
            raise InstalledHealthError("INSTALLATION_MISSING", "Forge installation is not initialized")

        deadline = self.monotonic_clock() + self.maximum_seconds
        try:
            uri = database.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=self.maximum_seconds)) as connection:
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA query_only=ON")
                connection.execute(f"PRAGMA busy_timeout={int(self.maximum_seconds * 1000)}")
                connection.execute("BEGIN")
                self._observe_integrity(connection, deadline)
                metadata = dict(connection.execute("SELECT key, value FROM runtime_metadata"))
                schema = self._validated_schema(connection, metadata)
                runtime_id = self._identifier(metadata.get("runtime_id"), "runtime identity")
                marker_runtime_id = marker.read_text(encoding="utf-8").strip()
                if marker_runtime_id != runtime_id:
                    raise InstalledHealthError(
                        "INSTALLATION_IDENTITY_MISMATCH", "Forge installation identity is inconsistent",
                    )
                installation_id = self._identifier(metadata.get("installation_id"), "installation identity")
                dispatcher = connection.execute(
                    "SELECT status FROM dispatcher_state WHERE singleton=1"
                ).fetchone()
                dispatcher_status = "IDLE" if dispatcher is None else dispatcher[0]
                dispatcher_state = (
                    ObservationState.PASS
                    if dispatcher_status in {"IDLE", "ACTIVE"}
                    else ObservationState.FAIL
                )
                observations = self._observations(
                    HealthIdentity(canonical_version(), runtime_id, installation_id),
                    evaluated_at,
                    dispatcher_state,
                )
                evaluation = evaluate_health(
                    observations[0].identity,
                    installed_health_definitions(),
                    observations,
                    capability_scope=(INSTALLED_HEALTH_CAPABILITY,),
                    evaluated_at=evaluated_at,
                )
                # Recheck the marker while the database read transaction is held.
                if marker.read_text(encoding="utf-8").strip() != runtime_id:
                    raise InstalledHealthError(
                        "INSTALLATION_IDENTITY_CHANGED", "Forge installation identity changed during observation",
                    )
                connection.rollback()
        except InstalledHealthError:
            raise
        except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
            raise InstalledHealthError(
                "HEALTH_OBSERVATION_UNAVAILABLE", "Installed Forge health is unavailable",
            ) from None

        sources = (
            ("installed_reader", "installed_http_or_cli_invocation", "forge_server"),
            ("database_integrity", "sqlite_integrity_check", "forge_runtime"),
            ("dispatcher_state", "dispatcher_state.singleton", "forge_runtime"),
        )
        return {
            "schema_version": INSTALLED_HEALTH_SNAPSHOT_VERSION,
            "assessment": "installed_health_snapshot",
            "profile": INSTALLED_HEALTH_PROFILE,
            "read_only": True,
            "bounded": True,
            "evaluated_at": evaluated_at.isoformat(),
            "identity": {
                "product": "forge",
                "product_version": evaluation.identity.product_version,
                "runtime_id": runtime_id,
                "installation_id": installation_id,
                "storage_schema": schema,
            },
            "registry": component_registry_projection(),
            "observation_policy": {
                "integrity_observations": 1,
                "provider_invocations": 0,
                "peer_invocations": 0,
                "mutations": 0,
            },
            "observation_provenance": [
                {"check_id": check_id, "source": source, "authority": authority}
                for check_id, source, authority in sources
            ],
            "evaluation": evaluation.to_dict(),
        }

    def _observe_integrity(self, connection: sqlite3.Connection, deadline: float) -> None:
        """Run the sole integrity observation with an interruptible wall-clock bound."""
        deadline_expired = False

        def interrupt_when_expired() -> int:
            nonlocal deadline_expired
            deadline_expired = self.monotonic_clock() >= deadline
            return int(deadline_expired)

        connection.set_progress_handler(interrupt_when_expired, _SQLITE_PROGRESS_STEPS)
        try:
            result = connection.execute("PRAGMA integrity_check(1)").fetchone()
            if self.monotonic_clock() >= deadline:
                raise InstalledHealthError(
                    "HEALTH_OBSERVATION_TIMED_OUT", "Installed Forge health observation timed out",
                )
        except sqlite3.OperationalError:
            if deadline_expired or self.monotonic_clock() >= deadline:
                raise InstalledHealthError(
                    "HEALTH_OBSERVATION_TIMED_OUT", "Installed Forge health observation timed out",
                ) from None
            raise
        finally:
            connection.set_progress_handler(None, 0)
        if result is None or result[0] != "ok":
            raise InstalledHealthError(
                "STORAGE_INTEGRITY_FAILED", "Forge runtime storage integrity is unavailable",
            )

    @staticmethod
    def _validated_schema(connection: sqlite3.Connection, metadata: dict[str, str]) -> int:
        try:
            schema = int(metadata["schema_version"])
            migration = int(metadata["migration_version"])
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        except (KeyError, TypeError, ValueError, sqlite3.Error):
            raise InstalledHealthError(
                "STORAGE_SCHEMA_INVALID", "Forge runtime storage schema is unreadable",
            ) from None
        if schema > RUNTIME_SCHEMA_VERSION:
            raise InstalledHealthError(
                "STORAGE_SCHEMA_NEWER", "Forge runtime storage schema is newer than this Forge version",
            )
        if schema != RUNTIME_SCHEMA_VERSION or migration != schema or user_version != schema:
            raise InstalledHealthError(
                "STORAGE_SCHEMA_UNSUPPORTED", "Forge runtime storage schema is not supported",
            )
        return schema

    @staticmethod
    def _identifier(value: object, label: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 128:
            raise InstalledHealthError("INSTALLATION_IDENTITY_INVALID", f"Forge {label} is invalid")
        if any(character.isspace() or ord(character) < 33 for character in value):
            raise InstalledHealthError("INSTALLATION_IDENTITY_INVALID", f"Forge {label} is invalid")
        return value

    @staticmethod
    def _observations(
        identity: HealthIdentity,
        observed_at: datetime,
        dispatcher_state: ObservationState,
    ) -> tuple[HealthObservation, ...]:
        capability = (INSTALLED_HEALTH_CAPABILITY,)
        return (
            HealthObservation(
                identity, "forge_server", "installed_reader", CheckPurpose.LIVENESS,
                (), ObservationState.PASS, observed_at,
            ),
            HealthObservation(
                identity, "platform_database", "database_integrity", CheckPurpose.READINESS,
                capability, ObservationState.PASS, observed_at,
            ),
            HealthObservation(
                identity, "mission_dispatcher", "dispatcher_state", CheckPurpose.READINESS,
                capability, dispatcher_state, observed_at,
                reason_code=None if dispatcher_state is ObservationState.PASS else "DISPATCHER_STATE_INVALID",
            ),
        )
