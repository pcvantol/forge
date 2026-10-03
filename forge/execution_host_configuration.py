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
from contextlib import contextmanager
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse

from .runtime.data_root import DataRootResolver
from .secure_store import MacOSKeychainSecureStoreAdapter, SecretReference, SecretState


PEER_CONFIGURATION_SCHEMA_VERSION = "1.1"
LEGACY_PEER_CONFIGURATION_SCHEMA_VERSION = "1.0"
PEER_PRODUCT = "engineering-platform"
PRODUCER_READBACK_CONTRACT = "1.2"
TERMINAL_EVIDENCE_CONTRACT = "1.4"
_REPLACEABLE_LEGACY_CONTRACT_PAIRS = frozenset({("1.2", "1.2"), ("1.2", "1.3")})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_GITHUB_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_FIELDS = frozenset((
    "schema_version", "binding_id", "configuration_revision", "configuration_digest",
    "owning_forge_runtime_id", "peer_product", "endpoint", "expected_ep_instance_id",
    "ep_consumer_id", "execution_host_id", "ep_project_id", "ep_repository_id", "repository_identity",
    "producer_readback_contract", "terminal_evidence_contract", "credential_reference",
    "allow_loopback_http", "timeout_seconds", "created_at", "created_by", "updated_at", "updated_by",
))
_LEGACY_FIELDS = _FIELDS - {"ep_consumer_id"}
_TABLE_SHAPE = (
    ("singleton", "INTEGER", 0, 1), ("binding_id", "TEXT", 1, 0),
    ("configuration_revision", "INTEGER", 1, 0),
    ("configuration_digest", "TEXT", 1, 0), ("document", "TEXT", 1, 0),
)


class PeerConfigurationError(RuntimeError):
    """A persisted peer cannot be read or used without weakening its binding."""


class PeerConfigurationConflict(PeerConfigurationError):
    """A configuration write did not match the currently persisted revision."""


@dataclass(frozen=True)
class _StoredPeerConfiguration:
    """A structurally verified selected record, including a legacy contract.

    Runtime consumers never receive this type: they must construct the strict
    current-contract configuration below.  The explicit configuration command
    uses it only to perform an optimistic-locking replacement of a previously
    valid binding whose contract version has been retired.
    """

    document: dict[str, Any]

    @property
    def binding_id(self) -> str:
        return str(self.document["binding_id"])

    @property
    def revision(self) -> int:
        return int(self.document["configuration_revision"])

    @property
    def digest(self) -> str:
        return str(self.document["configuration_digest"])

    @property
    def current_contracts(self) -> bool:
        return (
            self.document["schema_version"] == PEER_CONFIGURATION_SCHEMA_VERSION
            and self.document["producer_readback_contract"] == PRODUCER_READBACK_CONTRACT
            and self.document["terminal_evidence_contract"] == TERMINAL_EVIDENCE_CONTRACT
        )


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _verified_detach_receipt(raw: str, *, operation_id: str, request_digest: str) -> dict[str, Any]:
    try:
        receipt = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise PeerConfigurationError("EP peer detach receipt is unreadable") from error
    if not isinstance(receipt, dict):
        raise PeerConfigurationError("EP peer detach receipt is malformed")
    digest = receipt.get("receipt_digest")
    basis = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    calculated = "sha256:" + sha256(json.dumps(
        basis, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    if (digest != calculated or receipt.get("operation_id") != operation_id
            or receipt.get("request_digest") != request_digest
            or receipt.get("contract") != "forge-ep-peer-detach/v1"
            or receipt.get("state") != "COMPLETE"
            or receipt.get("local_peer_state") != "DETACHED"
            or receipt.get("remote_consumer_revoke") != "NOT_ASSERTED"):
        raise PeerConfigurationError("EP peer detach receipt failed exact verification")
    return receipt


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise PeerConfigurationError(f"{label} is invalid")
    return value


def _repository_identity(value: object) -> str:
    """Accept the persisted legacy identity or one exact GitHub owner/repo."""
    if not isinstance(value, str) or (
        _IDENTIFIER.fullmatch(value) is None
        and (_GITHUB_REPOSITORY.fullmatch(value) is None or value.split("/")[1] in {".", ".."})
    ):
        raise PeerConfigurationError("Forge repository identity binding is invalid")
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


def _legacy_consumer_adoption_preserves_binding(
    predecessor: Mapping[str, Any], candidate: "EngineeringPlatformPeerConfiguration",
) -> bool:
    """Return true only when schema 1.0 is changed by adding consumer identity."""

    if predecessor.get("schema_version") != LEGACY_PEER_CONFIGURATION_SCHEMA_VERSION:
        return False
    current = candidate.configuration_basis()
    return all(
        key == "schema_version" or current.get(key) == value
        for key, value in predecessor.items()
        if key not in {
            "configuration_revision", "configuration_digest", "created_at", "created_by",
            "updated_at", "updated_by",
        }
    )


def _historical_target_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "binding_id", "owning_forge_runtime_id", "peer_product", "endpoint",
        "expected_ep_instance_id", "execution_host_id", "ep_project_id",
        "ep_repository_id", "repository_identity",
    )
    return {key: document.get(key) for key in keys}


@dataclass(frozen=True)
class EngineeringPlatformPeerConfiguration:
    """The sole selected EP peer binding, with no credential material."""

    binding_id: str
    configuration_revision: int
    configuration_digest: str
    owning_forge_runtime_id: str
    endpoint: str
    expected_ep_instance_id: str
    ep_consumer_id: str
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
            raise PeerConfigurationError("EP peer contracts must select the configured current versions")
        for value, label in (
            (self.binding_id, "binding identity"),
            (self.owning_forge_runtime_id, "owning Forge runtime identity"),
            (self.expected_ep_instance_id, "expected EP instance identity"),
            (self.ep_consumer_id, "expected EP consumer identity"),
            (self.execution_host_id, "Execution Host identity"),
            (self.ep_project_id, "EP project identity"),
            (self.ep_repository_id, "EP repository identity"),
            (self.created_by, "creation operator identity"),
            (self.updated_by, "modification operator identity"),
        ):
            _identifier(value, label)
        _repository_identity(self.repository_identity)
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
            "ep_consumer_id": self.ep_consumer_id,
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


def _stored_peer_identity(document: Mapping[str, Any]) -> str:
    schema_version = document.get("schema_version")
    expected_fields = (
        _FIELDS if schema_version == PEER_CONFIGURATION_SCHEMA_VERSION
        else _LEGACY_FIELDS if schema_version == LEGACY_PEER_CONFIGURATION_SCHEMA_VERSION
        else None
    )
    if expected_fields is None:
        raise PeerConfigurationError("EP peer configuration schema is unsupported")
    if set(document) != expected_fields:
        raise PeerConfigurationError("EP peer configuration record is incomplete or contains unknown fields")
    if document.get("peer_product") != PEER_PRODUCT:
        raise PeerConfigurationError("EP peer product is incompatible")
    for value, label in (
        (document.get("binding_id"), "binding identity"),
        (document.get("owning_forge_runtime_id"), "owning Forge runtime identity"),
        (document.get("expected_ep_instance_id"), "expected EP instance identity"),
        (document.get("execution_host_id"), "Execution Host identity"),
        (document.get("ep_project_id"), "EP project identity"),
        (document.get("ep_repository_id"), "EP repository identity"),
        (document.get("created_by"), "creation operator identity"),
        (document.get("updated_by"), "modification operator identity"),
    ):
        _identifier(value, label)
    _repository_identity(document.get("repository_identity"))
    if schema_version == PEER_CONFIGURATION_SCHEMA_VERSION:
        _identifier(document.get("ep_consumer_id"), "expected EP consumer identity")
    return schema_version


def _stored_peer_transport(document: Mapping[str, Any]) -> None:
    revision = document.get("configuration_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise PeerConfigurationError("EP peer configuration revision is invalid")
    loopback = document.get("allow_loopback_http")
    if not isinstance(loopback, bool):
        raise PeerConfigurationError("EP peer loopback transport setting is invalid")
    timeout = document.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < float(timeout) <= 60:
        raise PeerConfigurationError("EP peer timeout must be greater than zero and at most 60 seconds")
    endpoint = canonical_endpoint(document.get("endpoint"), allow_loopback_http=loopback)
    if endpoint != document.get("endpoint"):
        raise PeerConfigurationError("EP peer endpoint is not canonical")
    SecretReference.parse(document.get("credential_reference"))
    if _provenance_timestamp(document.get("updated_at")) < _provenance_timestamp(document.get("created_at")):
        raise PeerConfigurationError("EP peer configuration modification precedes its creation")


def _stored_peer_contract(document: Mapping[str, Any], schema_version: str) -> None:
    contracts = (document.get("producer_readback_contract"), document.get("terminal_evidence_contract"))
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+", value) for value in contracts):
        raise PeerConfigurationError("EP peer contract version is invalid")
    if contracts not in _REPLACEABLE_LEGACY_CONTRACT_PAIRS | {
        (PRODUCER_READBACK_CONTRACT, TERMINAL_EVIDENCE_CONTRACT),
    }:
        raise PeerConfigurationError("EP peer contract version is unsupported")
    basis_fields = [
        "schema_version", "binding_id", "owning_forge_runtime_id", "peer_product", "endpoint",
        "expected_ep_instance_id", "execution_host_id", "ep_project_id", "ep_repository_id",
        "repository_identity", "producer_readback_contract", "terminal_evidence_contract",
        "credential_reference", "allow_loopback_http", "timeout_seconds",
    ]
    if schema_version == PEER_CONFIGURATION_SCHEMA_VERSION:
        basis_fields.insert(6, "ep_consumer_id")
    basis = {key: document[key] for key in basis_fields}
    digest = document.get("configuration_digest")
    if (not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None
            or digest != EngineeringPlatformPeerConfiguration.digest_for(basis)):
        raise PeerConfigurationError("EP peer configuration digest is invalid")


def _validated_stored_peer(document: Mapping[str, Any], row: sqlite3.Row,
                           runtime_id: str) -> _StoredPeerConfiguration:
    normalized = dict(document)
    schema_version = _stored_peer_identity(normalized)
    _stored_peer_transport(normalized)
    _stored_peer_contract(normalized, schema_version)
    if (normalized["binding_id"] != row["binding_id"]
            or normalized["configuration_revision"] != row["configuration_revision"]
            or normalized["configuration_digest"] != row["configuration_digest"]):
        raise PeerConfigurationError("EP peer configuration storage columns do not match its record")
    if normalized["owning_forge_runtime_id"] != runtime_id:
        raise PeerConfigurationError("EP peer configuration belongs to a different Forge runtime")
    return _StoredPeerConfiguration(normalized)


class EngineeringPlatformPeerConfigurationStore:
    """The narrow Forge-owned SQL boundary for the singleton peer record."""

    def __init__(self, connection: sqlite3.Connection, runtime_id: str, *, writable: bool) -> None:
        self._connection = connection
        self.runtime_id = _identifier(runtime_id, "owning Forge runtime identity")
        self._writable = writable

    def _stored(self) -> _StoredPeerConfiguration | None:
        """Read one structurally sound selected record without promoting it.

        A retired peer-contract version must remain unusable for runtime reads.
        It can nevertheless be replaced by an explicit operator action that
        matches its immutable revision and digest.  This avoids trapping an
        installation on a stale terminal-evidence contract after Forge is
        upgraded to the v1.4 peer contract.
        """
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
        if not isinstance(document, Mapping):
            raise PeerConfigurationError("EP peer configuration record is incomplete or contains unknown fields")
        return _validated_stored_peer(document, row, self.runtime_id)

    def load(self) -> EngineeringPlatformPeerConfiguration | None:
        pending = self._connection.execute(
            "SELECT 1 FROM execution_host_peer_detach_operations WHERE phase='PREPARED' LIMIT 1"
        ).fetchone()
        if pending is not None:
            raise PeerConfigurationError("EP peer detach is unfinished")
        stored = self._stored()
        if stored is None:
            return None
        return EngineeringPlatformPeerConfiguration.from_dict(stored.document)

    def configure(
        self,
        *,
        binding_id: str,
        endpoint: str,
        expected_ep_instance_id: str,
        ep_consumer_id: str,
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
        operational_event_writer: Callable[[EngineeringPlatformPeerConfiguration, str], None] | None = None,
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
            "ep_consumer_id": ep_consumer_id,
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
            stored = self._stored()
            generation = self._connection.execute(
                "SELECT generation,last_digest FROM execution_host_peer_generation WHERE singleton=1"
            ).fetchone()
            if generation is None:
                raise PeerConfigurationError("EP peer generation state is missing")
            pending = self._connection.execute(
                "SELECT operation_id FROM execution_host_peer_detach_operations "
                "WHERE phase='PREPARED' LIMIT 1"
            ).fetchone()
            if pending is not None:
                raise PeerConfigurationConflict("EP peer detach is unfinished")
            current = (
                EngineeringPlatformPeerConfiguration.from_dict(stored.document)
                if stored is not None and stored.current_contracts else None
            )
            if current is not None and current.configuration_basis() == provisional.configuration_basis():
                self._connection.rollback()
                return current
            if stored is not None:
                if (not replace or expected_revision != stored.revision
                        or expected_digest != stored.digest):
                    raise PeerConfigurationConflict(
                        "conflicting EP peer configuration requires explicit replacement with the current revision and digest"
                    )
                revision = stored.revision + 1
                created_at, created_by = str(stored.document["created_at"]), str(stored.document["created_by"])
            else:
                if int(generation[0]) == 0:
                    if replace or expected_revision is not None or expected_digest is not None:
                        raise PeerConfigurationConflict("initial EP peer configuration cannot claim a replacement")
                elif (not replace or expected_revision != int(generation[0])
                      or expected_digest != generation[1]):
                    raise PeerConfigurationConflict(
                        "re-pair requires the exact detached peer generation and receipt digest"
                    )
                revision, created_at, created_by = int(generation[0]) + 1, now, operator_id
            configured = EngineeringPlatformPeerConfiguration(
                configuration_revision=revision,
                configuration_digest=EngineeringPlatformPeerConfiguration.digest_for(basis),
                created_at=created_at, created_by=created_by, updated_at=now, updated_by=operator_id,
                **basis,
            )
            if (
                stored is not None
                and stored.document.get("schema_version") == LEGACY_PEER_CONFIGURATION_SCHEMA_VERSION
                and not _legacy_consumer_adoption_preserves_binding(stored.document, configured)
            ):
                raise PeerConfigurationConflict(
                    "legacy consumer identity adoption may not retarget the existing EP peer binding"
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
            self._connection.execute(
                "UPDATE execution_host_peer_generation SET generation=?,last_digest=? WHERE singleton=1",
                (configured.configuration_revision, configured.configuration_digest),
            )
            if operational_event_writer is not None:
                operational_event_writer(configured, "created" if stored is None else "replaced")
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
    status: str
    stored_document: dict[str, Any] | None


def read_peer_configuration(
    data_root: Path | str | None, *, allow_legacy_contract_replacement: bool = False,
) -> ReadOnlyPeerConfiguration:
    """Read without creating, migrating, timestamping, or otherwise changing product state.

    Normal readback remains strict: a retired peer contract is not an eligible
    runtime binding.  The configuration route may opt into structural legacy
    validation solely to replace that exact record under optimistic locking.
    """
    from .runtime.database import RUNTIME_SCHEMA_VERSION

    root = DataRootResolver(cli_data_root=data_root).resolve()
    database = root / "forge.db"
    marker = root / "instance" / "runtime-instance.json"
    if marker.is_symlink() or database.is_symlink():
        raise PeerConfigurationError("Forge instance marker or database is an unsafe symbolic link")
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
            stored = None
            configuration = None
        else:
            store = EngineeringPlatformPeerConfigurationStore(connection, runtime_id, writable=False)
            stored = store._stored()
            configuration = (
                EngineeringPlatformPeerConfiguration.from_dict(stored.document)
                if stored is not None and stored.current_contracts else None
            )
            if (configuration is not None and schema < RUNTIME_SCHEMA_VERSION
                    and not (allow_legacy_contract_replacement and schema == 39)):
                raise PeerConfigurationError("EP peer configuration exists under an unqualified storage schema")
        detached = False
        pending_detach = False
        if schema == RUNTIME_SCHEMA_VERSION:
            pending_detach = connection.execute(
                "SELECT 1 FROM execution_host_peer_detach_operations WHERE phase='PREPARED' LIMIT 1"
            ).fetchone() is not None
            generation = connection.execute(
                "SELECT generation,last_digest FROM execution_host_peer_generation WHERE singleton=1"
            ).fetchone()
            if generation is None:
                raise PeerConfigurationError("EP peer generation state is missing")
            if stored is not None:
                if int(generation[0]) != stored.revision or generation[1] != stored.digest:
                    raise PeerConfigurationError("EP peer generation does not match selected binding")
            elif int(generation[0]) == 0:
                if generation[1] is not None:
                    raise PeerConfigurationError("initial EP peer generation is inconsistent")
            else:
                detached = True
                terminal = connection.execute(
                    "SELECT operation_id,request_digest,receipt FROM execution_host_peer_detach_operations "
                    "WHERE phase='COMPLETE' AND expected_revision=? "
                    "ORDER BY updated_at DESC LIMIT 1", (int(generation[0]),),
                ).fetchone()
                if terminal is None:
                    raise PeerConfigurationError("detached EP peer receipt is missing")
                receipt = _verified_detach_receipt(
                    terminal[2], operation_id=terminal[0], request_digest=terminal[1],
                )
                if receipt.get("receipt_digest") != generation[1]:
                    raise PeerConfigurationError("detached EP peer receipt does not match generation")
        if pending_detach:
            status, stored_document, configuration = "DETACH_PENDING", None, None
        elif stored is None:
            status, stored_document = ("DETACHED" if detached else "NOT_CONFIGURED"), None
        elif configuration is not None:
            status, stored_document = "CONFIGURED", configuration.to_dict()
        elif stored.document["schema_version"] == LEGACY_PEER_CONFIGURATION_SCHEMA_VERSION:
            status, stored_document = "CONSUMER_IDENTITY_REQUIRED", dict(stored.document)
        else:
            status, stored_document = "CONTRACT_UPGRADE_REQUIRED", dict(stored.document)
        return ReadOnlyPeerConfiguration(
            configuration, runtime_id, schema, status, stored_document,
        )
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
            expected_consumer_id=configuration.ep_consumer_id,
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
            raise PeerConfigurationError("EP peer is not runtime-ready: " + readback.status)
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
        # Installed lifecycle owns migration of preserved older schemas. A
        # peer command must never turn a 2.7.38 instance into a 2.7.39 one.
        readback = read_peer_configuration(self.data_root, allow_legacy_contract_replacement=True)
        from .runtime.database import RUNTIME_SCHEMA_VERSION
        if readback.storage_schema != RUNTIME_SCHEMA_VERSION:
            raise PeerConfigurationError("Forge instance requires its product-owned installed update first")
        database = RuntimeBootstrap(data_root=self.data_root, forge_version=canonical_version()).open()
        try:
            if marker.read_text(encoding="utf-8").strip() != database.runtime_identity.runtime_id:
                raise PeerConfigurationError("Forge runtime instance marker does not match storage")
        except Exception:
            database.close()
            raise
        return database

    def configure(self, **values: Any) -> EngineeringPlatformPeerConfiguration:
        from .runtime.service import RuntimeServiceLock
        with RuntimeServiceLock(self.data_root / "forge.db").acquire():
            return self._configure_locked(**values)

    def _configure_locked(self, **values: Any) -> EngineeringPlatformPeerConfiguration:
        database = self._open_for_configuration()
        try:
            store = EngineeringPlatformPeerConfigurationStore(
                database._connection, database.runtime_identity.runtime_id, writable=True,
            )
            stored = store._stored()
            previous = (
                EngineeringPlatformPeerConfiguration.from_dict(stored.document)
                if stored is not None and stored.current_contracts else None
            )
            predecessor = None if stored is None else dict(stored.document)
            operator_id = str(values.get("operator_id", ""))
            operator_reference = sha256(operator_id.encode("utf-8")).hexdigest()[:16]

            def record_change(configuration: EngineeringPlatformPeerConfiguration, operation: str) -> None:
                consumer_adoption = (
                    predecessor is not None
                    and _legacy_consumer_adoption_preserves_binding(predecessor, configuration)
                )
                stable_target = (
                    predecessor is not None
                    and _historical_target_identity(predecessor)
                    == _historical_target_identity(configuration.to_dict())
                )
                database._append_operational_event(
                    component="forge_execution_host", level="INFO",
                    event="execution_host_configuration_" + operation,
                    operator_reference=operator_reference,
                    details={
                        "operation": operation, "outcome": "accepted",
                        "binding_id": configuration.binding_id,
                        "configuration_revision": configuration.configuration_revision,
                        "configuration_digest": configuration.configuration_digest,
                        "peer_product": configuration.peer_product,
                        "ep_instance_id": configuration.expected_ep_instance_id,
                        "ep_consumer_id": configuration.ep_consumer_id,
                        "previous_state": (
                            "UNCONFIGURED" if predecessor is None else
                            "schema:" + str(predecessor["schema_version"])
                            + ";consumer-identity:"
                            + ("BOUND" if "ep_consumer_id" in predecessor else "UNBOUND")
                            + ";producer-readback:" + str(predecessor["producer_readback_contract"])
                            + ";terminal-evidence:" + str(predecessor["terminal_evidence_contract"])
                        ),
                        "request_digest": (
                            None if predecessor is None else predecessor["configuration_digest"]
                        ),
                        "previous_configuration_revision": (
                            None if predecessor is None else predecessor["configuration_revision"]
                        ),
                        "historical_readback_adoption": (
                            "LEGACY_CONSUMER_IDENTITY_ADOPTION_V1" if consumer_adoption else
                            "TARGET_IDENTITY_PRESERVED_V1" if stable_target else None
                        ),
                        "historical_target_identity_digest": (
                            None if not stable_target else EngineeringPlatformPeerConfiguration.digest_for(
                                _historical_target_identity(predecessor)
                            )
                        ),
                    },
                    occurred_at=configuration.updated_at,
                )

            configured = store.configure(**values, operational_event_writer=record_change)
            if previous == configured:
                database.record_operational_event(
                    component="forge_execution_host", level="INFO",
                    event="execution_host_configuration_unchanged",
                    operator_reference=operator_reference,
                    details={
                        "operation": "unchanged", "outcome": "accepted",
                        "binding_id": configured.binding_id,
                        "configuration_revision": configured.configuration_revision,
                        "configuration_digest": configured.configuration_digest,
                        "peer_product": configured.peer_product,
                        "ep_instance_id": configured.expected_ep_instance_id,
                        "ep_consumer_id": configured.ep_consumer_id,
                    },
                )
            return configured
        finally:
            database.close()

    @contextmanager
    def _detach_locks(self, instance_id: str):
        """Use the owning lifecycle, updater, controller and runtime exclusions."""
        from .installed_lifecycle import CONTROL_DIRECTORY, _assert_no_symlink_components, _exclusive_locks
        from .runtime.service import RuntimeServiceLock

        identity = sha256(instance_id.encode("ascii")).hexdigest()
        control = self.data_root.parent / CONTROL_DIRECTORY / identity
        _assert_no_symlink_components(control.parent, allow_missing=True)
        _assert_no_symlink_components(control, allow_missing=True)
        control.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _exclusive_locks((
            control / "lifecycle.lock",
            self.data_root / "forge-mission-controller.lock",
        )):
            with RuntimeServiceLock(self.data_root / "forge.db").acquire():
                yield

    @staticmethod
    def _require_detach_quiescence(connection: sqlite3.Connection) -> None:
        from .installed_lifecycle import TERMINAL_PERMIT_STATES

        # A blocked/failed Mission or submission can still have unresolved EP
        # authority. The broader preserve/update terminal set is insufficient
        # for deleting the local peer that would reconcile that authority.
        safe_missions = frozenset({"COMPLETED", "ARCHIVED", "INTEGRATION_COMPLETE"})
        safe_submissions = frozenset({"RECONCILED"})

        dispatcher = connection.execute(
            "SELECT status,active_mission_id FROM dispatcher_state WHERE singleton=1"
        ).fetchone()
        if dispatcher is not None and (dispatcher[0] != "IDLE" or dispatcher[1] is not None):
            raise PeerConfigurationConflict("Forge dispatcher is not idle")
        for table, column, allowed in (
            ("mission_state", "status", safe_missions),
            ("scheduler_submissions", "state", safe_submissions),
            ("planning_provider_generation_permits", "state", TERMINAL_PERMIT_STATES),
        ):
            if any(row[0] not in allowed for row in connection.execute(f"SELECT {column} FROM {table}")):
                raise PeerConfigurationConflict("Forge has active peer-dependent work")
        for row in connection.execute(
            "SELECT current_queue,pending_engineering_actions,blocked_engineering_actions FROM planning_state"
        ):
            if any(json.loads(str(value)) for value in row):
                raise PeerConfigurationConflict("Forge planning queue is not empty")
        reset = connection.execute(
            "SELECT active_operation_id,state FROM operational_reset_state WHERE singleton=1"
        ).fetchone()
        if reset is None or reset[0] is not None or reset[1] != "IDLE":
            raise PeerConfigurationConflict("Forge operational reset maintenance is active")

    def detach(
        self, *, operation_id: str, instance_id: str, expected_binding_id: str,
        expected_revision: int, expected_digest: str, operator_id: str,
        interrupt_after: str | None = None,
    ) -> dict[str, Any]:
        """Detach one exact quiescent peer; replay the same request after loss."""
        if not isinstance(operation_id, str) or _OPERATION_ID.fullmatch(operation_id) is None:
            raise PeerConfigurationError("detach operation identity is invalid")
        _identifier(instance_id, "Forge instance identity")
        _identifier(expected_binding_id, "expected EP binding identity")
        _identifier(operator_id, "operator identity")
        if (not isinstance(expected_revision, int) or isinstance(expected_revision, bool)
                or expected_revision < 1 or not isinstance(expected_digest, str)
                or _DIGEST.fullmatch(expected_digest) is None):
            raise PeerConfigurationError("expected EP peer generation is invalid")
        request = {
            "contract": "forge-ep-peer-detach/v1", "operation_id": operation_id,
            "instance_id": instance_id, "expected_binding_id": expected_binding_id,
            "expected_revision": expected_revision, "expected_digest": expected_digest,
            "operator_reference": sha256(operator_id.encode()).hexdigest()[:16],
        }
        request_digest = "sha256:" + sha256(json.dumps(
            request, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        with self._detach_locks(instance_id):
            selected = read_peer_configuration(self.data_root, allow_legacy_contract_replacement=True)
            if selected.runtime_id != instance_id:
                raise PeerConfigurationConflict("detach target is a different Forge instance")
            database = self._open_for_configuration()
            try:
                if database.runtime_identity.runtime_id != instance_id:
                    raise PeerConfigurationConflict("detach target is a different Forge instance")
                connection = database._connection
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT runtime_id,request_digest,phase,receipt FROM "
                    "execution_host_peer_detach_operations WHERE operation_id=?", (operation_id,),
                ).fetchone()
                if row is not None:
                    if row[0] != instance_id or row[1] != request_digest:
                        raise PeerConfigurationConflict("detach operation identity belongs to another request")
                    if row[2] == "COMPLETE":
                        receipt = _verified_detach_receipt(
                            row[3], operation_id=operation_id, request_digest=request_digest,
                        )
                        connection.rollback()
                        return receipt
                else:
                    other = connection.execute(
                        "SELECT operation_id FROM execution_host_peer_detach_operations "
                        "WHERE phase='PREPARED' LIMIT 1"
                    ).fetchone()
                    if other is not None:
                        raise PeerConfigurationConflict("another EP peer detach is unfinished")
                self._require_detach_quiescence(connection)
                store = EngineeringPlatformPeerConfigurationStore(
                    connection, instance_id, writable=True,
                )
                current = store._stored()
                if (current is None or current.binding_id != expected_binding_id
                        or current.revision != expected_revision or current.digest != expected_digest):
                    raise PeerConfigurationConflict("selected EP peer does not match the expected generation")
                if row is None:
                    now = _timestamp()
                    connection.execute(
                        "INSERT INTO execution_host_peer_detach_operations VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (operation_id, instance_id, request_digest, expected_binding_id,
                         expected_revision, expected_digest, "PREPARED", None, now, now),
                    )
                    connection.commit()
                    if interrupt_after == "PREPARED":
                        raise InterruptedError("detach interrupted after PREPARED")
                    connection.execute("BEGIN IMMEDIATE")
                    current = store._stored()
                    if (current is None or current.binding_id != expected_binding_id
                            or current.revision != expected_revision or current.digest != expected_digest):
                        raise PeerConfigurationConflict("selected EP peer changed during detach")
                    self._require_detach_quiescence(connection)
                now = _timestamp()
                receipt = {
                    **request, "request_digest": request_digest, "state": "COMPLETE",
                    "local_peer_state": "DETACHED", "remote_consumer_revoke": "NOT_ASSERTED",
                    "next_configuration_revision": expected_revision + 1,
                    "completed_at": now,
                }
                receipt["receipt_digest"] = "sha256:" + sha256(json.dumps(
                    receipt, sort_keys=True, separators=(",", ":"),
                ).encode()).hexdigest()
                deleted = connection.execute(
                    "DELETE FROM execution_host_peer_configuration WHERE singleton=1 "
                    "AND binding_id=? AND configuration_revision=? AND configuration_digest=?",
                    (expected_binding_id, expected_revision, expected_digest),
                )
                if deleted.rowcount != 1:
                    raise PeerConfigurationConflict("selected EP peer changed during detach")
                connection.execute(
                    "UPDATE execution_host_peer_generation SET generation=?,last_digest=? WHERE singleton=1",
                    (expected_revision, receipt["receipt_digest"]),
                )
                connection.execute(
                    "UPDATE execution_host_peer_detach_operations SET phase='COMPLETE',receipt=?,updated_at=? "
                    "WHERE operation_id=? AND phase='PREPARED'",
                    (json.dumps(receipt, sort_keys=True), now, operation_id),
                )
                connection.commit()
                return receipt
            except Exception:
                database._connection.rollback()
                raise
            finally:
                database.close()

    def detach_status(self, operation_id: str) -> dict[str, Any]:
        if not isinstance(operation_id, str) or _OPERATION_ID.fullmatch(operation_id) is None:
            raise PeerConfigurationError("detach operation identity is invalid")
        readback = read_peer_configuration(self.data_root)
        database_path = self.data_root / "forge.db"
        connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT runtime_id,request_digest,phase,receipt FROM "
                "execution_host_peer_detach_operations WHERE operation_id=?", (operation_id,),
            ).fetchone()
            if row is None or row[0] != readback.runtime_id:
                raise PeerConfigurationError("detach operation is absent")
            result = {
                "contract": "forge-ep-peer-detach/v1", "operation_id": operation_id,
                "instance_id": str(row[0]), "request_digest": str(row[1]),
                "phase": str(row[2]), "current_peer_status": readback.status,
            }
            if row[2] == "COMPLETE":
                result["receipt"] = _verified_detach_receipt(
                    row[3], operation_id=operation_id, request_digest=str(row[1]),
                )
            return result
        finally:
            connection.close()

    def show(self) -> EngineeringPlatformPeerConfiguration | None:
        readback = read_peer_configuration(self.data_root)
        if readback.configuration is None and readback.stored_document is not None:
            explanation = (
                "; peer contracts are not at the current versions"
                if readback.status == "CONTRACT_UPGRADE_REQUIRED"
                else ""
            )
            raise PeerConfigurationError(
                "EP peer is not runtime-ready: " + readback.status + explanation
            )
        return readback.configuration

    def readback(self) -> ReadOnlyPeerConfiguration:
        """Read current or guarded-upgrade state without resolving a credential."""
        return read_peer_configuration(self.data_root)

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
            "authenticated_consumer_identity": declaration["authentication"]["consumer_id"],
            "project_repository_scope": "PASS",
            "mutation_authority": "SUBMISSION_AUTHORIZED",
            "declaration": declaration,
        }
