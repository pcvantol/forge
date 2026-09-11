"""Durable, secret-free configuration of the selected EP Execution Host peer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse

from .runtime.data_root import DataRootResolver
from .secure_store import MacOSKeychainSecureStoreAdapter, SecretReference, SecretState


PEER_CONFIGURATION_SCHEMA_VERSION = "1.0"
PEER_PRODUCT = "engineering-platform"
PRODUCER_READBACK_CONTRACT = "1.2"
TERMINAL_EVIDENCE_CONTRACT = "1.2"
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_FIELDS = frozenset((
    "schema_version", "binding_id", "configuration_revision", "configuration_digest",
    "owning_forge_runtime_id", "peer_product", "endpoint", "expected_ep_instance_id",
    "execution_host_id", "ep_project_id", "ep_repository_id", "repository_identity",
    "producer_readback_contract", "terminal_evidence_contract", "credential_reference",
    "allow_loopback_http", "timeout_seconds", "created_at", "created_by", "updated_at", "updated_by",
))
_TABLE_SHAPE = (
    ("singleton", "INTEGER", 0, 1), ("binding_id", "TEXT", 1, 0),
    ("configuration_revision", "INTEGER", 1, 0),
    ("configuration_digest", "TEXT", 1, 0), ("document", "TEXT", 1, 0),
)


class PeerConfigurationError(RuntimeError):
    """A persisted peer cannot be read or used without weakening its binding."""


class PeerConfigurationConflict(PeerConfigurationError):
    """A configuration write did not match the currently persisted revision."""


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise PeerConfigurationError(f"{label} is invalid")
    return value


def _provenance_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        raise PeerConfigurationError("EP peer configuration provenance timestamp is invalid")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PeerConfigurationError("EP peer configuration provenance timestamp is invalid") from None


def canonical_endpoint(value: object, *, allow_loopback_http: bool) -> str:
    """Validate one fixed origin; discovery, embedded credentials and URL state are forbidden."""
    if not isinstance(value, str) or not value:
        raise PeerConfigurationError("EP endpoint is required")
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        raise PeerConfigurationError("EP endpoint is invalid") from None
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.params
            or parsed.path not in {"", "/"}):
        raise PeerConfigurationError("EP endpoint must be a credential-free HTTP(S) origin")
    if parsed.scheme == "http":
        loopback = parsed.hostname.lower() == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            pass
        if not allow_loopback_http or not loopback:
            raise PeerConfigurationError("HTTP is allowed only for an explicitly enabled loopback endpoint")
    default_port = 443 if parsed.scheme == "https" else 80
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname.lower()
    authority = host if port in (None, default_port) else f"{host}:{port}"
    return f"{parsed.scheme}://{authority}"


@dataclass(frozen=True)
class EngineeringPlatformPeerConfiguration:
    """The sole selected EP peer binding, with no credential material."""

    binding_id: str
    configuration_revision: int
    configuration_digest: str
    owning_forge_runtime_id: str
    endpoint: str
    expected_ep_instance_id: str
    execution_host_id: str
    ep_project_id: str
    ep_repository_id: str
    repository_identity: str
    credential_reference: str
    allow_loopback_http: bool
    timeout_seconds: float
    created_at: str
    created_by: str
    updated_at: str
    updated_by: str
    schema_version: str = PEER_CONFIGURATION_SCHEMA_VERSION
    peer_product: str = PEER_PRODUCT
    producer_readback_contract: str = PRODUCER_READBACK_CONTRACT
    terminal_evidence_contract: str = TERMINAL_EVIDENCE_CONTRACT

    def __post_init__(self) -> None:
        if self.schema_version != PEER_CONFIGURATION_SCHEMA_VERSION:
            raise PeerConfigurationError("EP peer configuration schema is unsupported")
        if self.peer_product != PEER_PRODUCT:
            raise PeerConfigurationError("EP peer product is incompatible")
        if (self.producer_readback_contract != PRODUCER_READBACK_CONTRACT
                or self.terminal_evidence_contract != TERMINAL_EVIDENCE_CONTRACT):
            raise PeerConfigurationError("EP peer contracts must select version 1.2")
        for value, label in (
            (self.binding_id, "binding identity"),
            (self.owning_forge_runtime_id, "owning Forge runtime identity"),
            (self.expected_ep_instance_id, "expected EP instance identity"),
            (self.execution_host_id, "Execution Host identity"),
            (self.ep_project_id, "EP project identity"),
            (self.ep_repository_id, "EP repository identity"),
            (self.repository_identity, "Forge repository identity binding"),
            (self.created_by, "creation operator identity"),
            (self.updated_by, "modification operator identity"),
        ):
            _identifier(value, label)
        if (not isinstance(self.configuration_revision, int)
                or isinstance(self.configuration_revision, bool) or self.configuration_revision < 1):
            raise PeerConfigurationError("EP peer configuration revision is invalid")
        if not isinstance(self.allow_loopback_http, bool):
            raise PeerConfigurationError("EP peer loopback transport setting is invalid")
        if (not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool)
                or not 0 < float(self.timeout_seconds) <= 60):
            raise PeerConfigurationError("EP peer timeout must be greater than zero and at most 60 seconds")
        endpoint = canonical_endpoint(self.endpoint, allow_loopback_http=self.allow_loopback_http)
        reference = SecretReference.parse(self.credential_reference)
        if _provenance_timestamp(self.updated_at) < _provenance_timestamp(self.created_at):
            raise PeerConfigurationError("EP peer configuration modification precedes its creation")
        object.__setattr__(self, "endpoint", endpoint)
        object.__setattr__(self, "credential_reference", reference.serialized)
        object.__setattr__(self, "timeout_seconds", float(self.timeout_seconds))
        expected = self.digest_for(self.configuration_basis())
        if _DIGEST.fullmatch(self.configuration_digest) is None or self.configuration_digest != expected:
            raise PeerConfigurationError("EP peer configuration digest is invalid")

    def configuration_basis(self) -> dict[str, Any]:
        """Return the provenance-independent content used for idempotency and digesting."""
        return {
            "schema_version": self.schema_version,
            "binding_id": self.binding_id,
            "owning_forge_runtime_id": self.owning_forge_runtime_id,
            "peer_product": self.peer_product,
            "endpoint": self.endpoint,
            "expected_ep_instance_id": self.expected_ep_instance_id,
            "execution_host_id": self.execution_host_id,
            "ep_project_id": self.ep_project_id,
            "ep_repository_id": self.ep_repository_id,
            "repository_identity": self.repository_identity,
            "producer_readback_contract": self.producer_readback_contract,
            "terminal_evidence_contract": self.terminal_evidence_contract,
            "credential_reference": self.credential_reference,
            "allow_loopback_http": self.allow_loopback_http,
            "timeout_seconds": self.timeout_seconds,
        }

    @staticmethod
    def digest_for(basis: Mapping[str, Any]) -> str:
        encoded = json.dumps(dict(basis), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        return "sha256:" + sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.configuration_basis(),
            "configuration_revision": self.configuration_revision,
            "configuration_digest": self.configuration_digest,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EngineeringPlatformPeerConfiguration":
        if not isinstance(value, Mapping) or set(value) != _FIELDS:
            raise PeerConfigurationError("EP peer configuration record is incomplete or contains unknown fields")
        try:
            return cls(**dict(value))
        except TypeError as error:
            raise PeerConfigurationError("EP peer configuration record is malformed") from error


class EngineeringPlatformPeerConfigurationStore:
    """The narrow Forge-owned SQL boundary for the singleton peer record."""

    def __init__(self, connection: sqlite3.Connection, runtime_id: str, *, writable: bool) -> None:
        self._connection = connection
        self.runtime_id = _identifier(runtime_id, "owning Forge runtime identity")
        self._writable = writable

    def load(self) -> EngineeringPlatformPeerConfiguration | None:
        try:
            columns = tuple(
                (row["name"], row["type"].upper(), row["notnull"], row["pk"])
                for row in self._connection.execute("PRAGMA table_info(execution_host_peer_configuration)")
            )
            table = self._connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='execution_host_peer_configuration'"
            ).fetchone()
            sql = "" if table is None or table["sql"] is None else " ".join(table["sql"].lower().split())
            unique_indexes = {
                tuple(item["name"] for item in self._connection.execute(f"PRAGMA index_info('{row['name']}')"))
                for row in self._connection.execute("PRAGMA index_list(execution_host_peer_configuration)")
                if row["unique"]
            }
            if (columns != _TABLE_SHAPE or ("binding_id",) not in unique_indexes
                    or "check (singleton = 1)" not in sql
                    or "check (configuration_revision > 0)" not in sql):
                raise PeerConfigurationError("EP peer configuration storage structure is incompatible")
            rows = self._connection.execute(
                "SELECT binding_id, configuration_revision, configuration_digest, document "
                "FROM execution_host_peer_configuration ORDER BY singleton"
            ).fetchall()
        except sqlite3.Error as error:
            raise PeerConfigurationError("EP peer configuration storage is unavailable") from error
        if not rows:
            return None
        if len(rows) != 1:
            raise PeerConfigurationError("EP peer configuration storage contains multiple selected bindings")
        row = rows[0]
        try:
            document = json.loads(row["document"])
        except (TypeError, json.JSONDecodeError) as error:
            raise PeerConfigurationError("EP peer configuration record is unreadable") from error
        configuration = EngineeringPlatformPeerConfiguration.from_dict(document)
        if (configuration.binding_id != row["binding_id"]
                or configuration.configuration_revision != row["configuration_revision"]
                or configuration.configuration_digest != row["configuration_digest"]):
            raise PeerConfigurationError("EP peer configuration storage columns do not match its record")
        if configuration.owning_forge_runtime_id != self.runtime_id:
            raise PeerConfigurationError("EP peer configuration belongs to a different Forge runtime")
        return configuration

    def configure(
        self,
        *,
        binding_id: str,
        endpoint: str,
        expected_ep_instance_id: str,
        execution_host_id: str,
        ep_project_id: str,
        ep_repository_id: str,
        repository_identity: str,
        credential_reference: SecretReference,
        operator_id: str,
        allow_loopback_http: bool = False,
        timeout_seconds: float = 10.0,
        replace: bool = False,
        expected_revision: int | None = None,
        expected_digest: str | None = None,
        occurred_at: str | None = None,
    ) -> EngineeringPlatformPeerConfiguration:
        if not self._writable:
            raise PeerConfigurationError("read-only peer configuration storage cannot be changed")
        if not isinstance(credential_reference, SecretReference):
            raise PeerConfigurationError("a typed credential reference is required")
        now = occurred_at or _timestamp()
        basis = {
            "schema_version": PEER_CONFIGURATION_SCHEMA_VERSION,
            "binding_id": binding_id,
            "owning_forge_runtime_id": self.runtime_id,
            "peer_product": PEER_PRODUCT,
            "endpoint": canonical_endpoint(endpoint, allow_loopback_http=allow_loopback_http),
            "expected_ep_instance_id": expected_ep_instance_id,
            "execution_host_id": execution_host_id,
            "ep_project_id": ep_project_id,
            "ep_repository_id": ep_repository_id,
            "repository_identity": repository_identity,
            "producer_readback_contract": PRODUCER_READBACK_CONTRACT,
            "terminal_evidence_contract": TERMINAL_EVIDENCE_CONTRACT,
            "credential_reference": credential_reference.serialized,
            "allow_loopback_http": allow_loopback_http,
            "timeout_seconds": float(timeout_seconds),
        }
        # Construct a candidate once to apply every field validator before a transaction starts.
        provisional = EngineeringPlatformPeerConfiguration(
            configuration_revision=1,
            configuration_digest=EngineeringPlatformPeerConfiguration.digest_for(basis),
            created_at=now, created_by=operator_id, updated_at=now, updated_by=operator_id,
            **basis,
        )
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self.load()
            if current is not None and current.configuration_basis() == provisional.configuration_basis():
                self._connection.rollback()
                return current
            if current is not None:
                if (not replace or expected_revision != current.configuration_revision
                        or expected_digest != current.configuration_digest):
                    raise PeerConfigurationConflict(
                        "conflicting EP peer configuration requires explicit replacement with the current revision and digest"
                    )
                revision = current.configuration_revision + 1
                created_at, created_by = current.created_at, current.created_by
            else:
                if replace or expected_revision is not None or expected_digest is not None:
                    raise PeerConfigurationConflict("initial EP peer configuration cannot claim a replacement")
                revision, created_at, created_by = 1, now, operator_id
            configured = EngineeringPlatformPeerConfiguration(
                configuration_revision=revision,
                configuration_digest=EngineeringPlatformPeerConfiguration.digest_for(basis),
                created_at=created_at, created_by=created_by, updated_at=now, updated_by=operator_id,
                **basis,
            )
            document = json.dumps(configured.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            self._connection.execute(
                "INSERT INTO execution_host_peer_configuration "
                "(singleton, binding_id, configuration_revision, configuration_digest, document) VALUES (1,?,?,?,?) "
                "ON CONFLICT(singleton) DO UPDATE SET binding_id=excluded.binding_id, "
                "configuration_revision=excluded.configuration_revision, configuration_digest=excluded.configuration_digest, "
                "document=excluded.document",
                (configured.binding_id, configured.configuration_revision, configured.configuration_digest, document),
            )
            self._connection.commit()
            return configured
        except Exception:
            self._connection.rollback()
            raise


@dataclass(frozen=True)
class ReadOnlyPeerConfiguration:
    configuration: EngineeringPlatformPeerConfiguration | None
    runtime_id: str
    storage_schema: int


def read_peer_configuration(data_root: Path | str | None) -> ReadOnlyPeerConfiguration:
    """Read without creating, migrating, timestamping, or otherwise changing product state."""
    from .runtime.database import RUNTIME_SCHEMA_VERSION

    root = DataRootResolver(cli_data_root=data_root).resolve()
    database = root / "forge.db"
    marker = root / "instance" / "runtime-instance.json"
    if not marker.is_file() or not database.is_file():
        raise PeerConfigurationError("Forge data root is not initialized")
    try:
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise PeerConfigurationError("Forge runtime database integrity check failed")
        metadata = dict(connection.execute("SELECT key, value FROM runtime_metadata"))
        runtime_id = _identifier(metadata.get("runtime_id"), "owning Forge runtime identity")
        try:
            schema = int(metadata["schema_version"])
            migration = int(metadata["migration_version"])
        except (KeyError, TypeError, ValueError):
            raise PeerConfigurationError("Forge runtime storage schema is unreadable") from None
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if schema != migration or schema != user_version:
            raise PeerConfigurationError("Forge runtime storage schema versions are inconsistent")
        if schema > RUNTIME_SCHEMA_VERSION:
            raise PeerConfigurationError("Forge runtime storage schema is newer than this Forge version")
        if marker.read_text(encoding="utf-8").strip() != runtime_id:
            raise PeerConfigurationError("Forge runtime instance marker does not match storage")
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='execution_host_peer_configuration'"
        ).fetchone()
        if table is None:
            if schema == RUNTIME_SCHEMA_VERSION:
                raise PeerConfigurationError("EP peer configuration storage is missing")
            configuration = None
        else:
            configuration = EngineeringPlatformPeerConfigurationStore(connection, runtime_id, writable=False).load()
            if configuration is not None and schema < RUNTIME_SCHEMA_VERSION:
                raise PeerConfigurationError("EP peer configuration exists under an unqualified storage schema")
        return ReadOnlyPeerConfiguration(configuration, runtime_id, schema)
    except sqlite3.Error as error:
        raise PeerConfigurationError("Forge runtime storage is unavailable") from error
    except OSError as error:
        raise PeerConfigurationError("Forge runtime instance marker is unreadable") from error
    finally:
        if "connection" in locals():
            connection.close()


class CredentialResolver(Protocol):
    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]: ...


class _PreflightOnlyBindings:
    def execution_host_binding(self, correlation_id: str) -> dict[str, Any] | None:
        raise PeerConfigurationError("preflight-only adapter cannot read execution correlations")

    def save_execution_host_binding(self, correlation_id: str, document: Mapping[str, Any]) -> dict[str, Any]:
        raise PeerConfigurationError("preflight-only adapter cannot change execution correlations")


class EngineeringPlatformExecutionHostFactory:
    """Resolve persisted peer state and construct the existing strict HTTP adapter."""

    def __init__(self, credential_resolver: CredentialResolver | None = None) -> None:
        self._credential_resolver = credential_resolver or MacOSKeychainSecureStoreAdapter()

    def _build(self, configuration: EngineeringPlatformPeerConfiguration, bindings: object):
        from .scheduler.ep_http_adapter import EngineeringPlatformHttpConfiguration, EngineeringPlatformHttpExecutionHost

        reference = SecretReference.parse(configuration.credential_reference)
        state, bearer_token = self._credential_resolver.resolve(reference)
        if state is not SecretState.RESOLVABLE or not bearer_token:
            raise PeerConfigurationError(f"EP credential reference is not resolvable: {state.value}")
        transport = EngineeringPlatformHttpConfiguration(
            base_url=configuration.endpoint,
            project_id=configuration.ep_project_id,
            bearer_token=bearer_token,
            expected_instance_id=configuration.expected_ep_instance_id,
            repository_id=configuration.ep_repository_id,
            repository_identity=configuration.repository_identity,
            allow_loopback_http=configuration.allow_loopback_http,
            host_id=configuration.execution_host_id,
            timeout=configuration.timeout_seconds,
            peer_binding_id=configuration.binding_id,
            peer_configuration_revision=configuration.configuration_revision,
            peer_configuration_digest=configuration.configuration_digest,
            producer_readback_contract=configuration.producer_readback_contract,
            terminal_evidence_contract=configuration.terminal_evidence_contract,
        )
        return EngineeringPlatformHttpExecutionHost(transport, bindings)

    def from_database(self, database: object):
        """Runtime composition route using the already-open canonical Runtime Database."""
        store = EngineeringPlatformPeerConfigurationStore(
            database._connection, database.runtime_identity.runtime_id, writable=False,
        )
        configuration = store.load()
        if configuration is None:
            raise PeerConfigurationError("EP peer is not configured")
        return self._build(configuration, database)

    def from_data_root(self, data_root: Path | str | None):
        """Read-only CLI-preflight route; the returned host can perform only preflight."""
        readback = read_peer_configuration(data_root)
        if readback.configuration is None:
            raise PeerConfigurationError("EP peer is not configured")
        return self._build(readback.configuration, _PreflightOnlyBindings())


class EngineeringPlatformPeerConfigurationService:
    """Interface-neutral configure, readback and compatibility-preflight service."""

    def __init__(self, data_root: Path | str | None, *,
                 factory: EngineeringPlatformExecutionHostFactory | None = None) -> None:
        self.data_root = DataRootResolver(cli_data_root=data_root).resolve()
        self.factory = factory or EngineeringPlatformExecutionHostFactory()

    def _open_for_configuration(self):
        from ._version import canonical_version
        from .runtime.bootstrap import RuntimeBootstrap

        database_path = self.data_root / "forge.db"
        marker = self.data_root / "instance" / "runtime-instance.json"
        if not marker.is_file() or not database_path.is_file():
            raise PeerConfigurationError("Forge data root must be initialized before peer configuration")
        # Qualify marker/database identity on the read-only path before the
        # writable RuntimeDatabase is allowed to apply a schema migration.
        read_peer_configuration(self.data_root)
        database = RuntimeBootstrap(data_root=self.data_root, forge_version=canonical_version()).open()
        try:
            if marker.read_text(encoding="utf-8").strip() != database.runtime_identity.runtime_id:
                raise PeerConfigurationError("Forge runtime instance marker does not match storage")
        except Exception:
            database.close()
            raise
        return database

    def configure(self, **values: Any) -> EngineeringPlatformPeerConfiguration:
        database = self._open_for_configuration()
        try:
            store = EngineeringPlatformPeerConfigurationStore(
                database._connection, database.runtime_identity.runtime_id, writable=True,
            )
            return store.configure(**values)
        finally:
            database.close()

    def show(self) -> EngineeringPlatformPeerConfiguration | None:
        return read_peer_configuration(self.data_root).configuration

    def preflight(self) -> dict[str, Any]:
        host = self.factory.from_data_root(self.data_root)
        try:
            declaration = host.preflight()
        except (RuntimeError, ValueError) as error:
            raise PeerConfigurationError(str(error)) from error
        return {
            "status": "PASS",
            "configuration_status": "CONFIGURED",
            "peer_instance_consistency": "PASS",
            "cryptographic_peer_identity": "NOT_ASSERTED",
            "compatibility": "PASS",
            "project_repository_scope": "NOT_VERIFIED",
            "mutation_authority": "NOT_VERIFIED",
            "declaration": declaration,
        }
