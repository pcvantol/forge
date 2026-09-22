"""Instance-owned execution context for external planning providers.

The context contains locations and identity only.  Provider credentials remain
owned by the provider CLI and are never parsed, copied, or persisted by Forge.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from .runtime.data_root import DataRootResolver


PROVIDER_CONTEXT_SCHEMA_VERSION = "1.0"
_PROVIDER_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_PROVIDER_TYPE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


class ProviderExecutionContextError(RuntimeError):
    """A provider context cannot be trusted for the selected Forge instance."""


@dataclass(frozen=True)
class ProviderExecutionContext:
    schema_version: str
    instance_id: str
    provider_id: str
    provider_type: str
    executable_path: str
    provider_home: str
    provider_config_home: str
    profile: str | None
    configuration_revision: int
    created_at: str
    updated_at: str
    configuration_digest: str

    def to_safe_dict(self) -> dict[str, Any]:
        """Return only non-secret deployment/readiness information."""
        return {
            "schema_version": self.schema_version,
            "instance_id": self.instance_id,
            "provider_id": self.provider_id,
            "provider_type": self.provider_type,
            "executable_path": self.executable_path,
            "provider_home": self.provider_home,
            "provider_config_home": self.provider_config_home,
            "profile": self.profile,
            "configuration_revision": self.configuration_revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "configuration_digest": self.configuration_digest,
        }


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_digest(document: dict[str, Any]) -> str:
    payload = {key: value for key, value in document.items() if key != "configuration_digest"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()


def _absolute(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ProviderExecutionContextError(label + " is invalid")
    path = Path(value)
    if not path.is_absolute():
        raise ProviderExecutionContextError(label + " must be an absolute path")
    return str(path)


class ProviderExecutionContextService:
    """Own one context document per provider below one explicit Forge data root."""

    def __init__(self, data_root: str | Path) -> None:
        self.root = DataRootResolver(cli_data_root=data_root).resolve()
        self.context_root = self.root / "instance" / "provider-contexts"
        self.marker = self.root / "instance" / "runtime-instance.json"

    def _instance_id(self) -> str:
        try:
            value = self.marker.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise ProviderExecutionContextError("Forge instance identity is unavailable") from error
        if not value:
            raise ProviderExecutionContextError("Forge instance identity is invalid")
        return value

    @staticmethod
    def _validate_provider_id(provider_id: str) -> str:
        if not isinstance(provider_id, str) or _PROVIDER_ID.fullmatch(provider_id) is None:
            raise ProviderExecutionContextError("provider id is invalid")
        return provider_id

    def _path(self, provider_id: str) -> Path:
        return self.context_root / (self._validate_provider_id(provider_id) + ".json")

    @staticmethod
    def _decode(document: object) -> ProviderExecutionContext:
        required = {
            "schema_version", "instance_id", "provider_id", "provider_type",
            "executable_path", "provider_home", "provider_config_home", "profile",
            "configuration_revision", "created_at", "updated_at", "configuration_digest",
        }
        if not isinstance(document, dict) or set(document) != required:
            raise ProviderExecutionContextError("provider context shape is invalid")
        if document["schema_version"] != PROVIDER_CONTEXT_SCHEMA_VERSION:
            raise ProviderExecutionContextError("provider context version is unsupported")
        if _PROVIDER_ID.fullmatch(str(document["provider_id"])) is None:
            raise ProviderExecutionContextError("provider context id is invalid")
        if _PROVIDER_TYPE.fullmatch(str(document["provider_type"])) is None:
            raise ProviderExecutionContextError("provider context type is invalid")
        if not isinstance(document["configuration_revision"], int) or document["configuration_revision"] < 1:
            raise ProviderExecutionContextError("provider context revision is invalid")
        if document["profile"] is not None and (
            not isinstance(document["profile"], str)
            or not document["profile"]
            or "\x00" in document["profile"]
        ):
            raise ProviderExecutionContextError("provider context profile is invalid")
        for field in ("instance_id", "created_at", "updated_at", "configuration_digest"):
            if not isinstance(document[field], str) or not document[field]:
                raise ProviderExecutionContextError("provider context " + field + " is invalid")
        _absolute(str(document["executable_path"]), "provider executable")
        _absolute(str(document["provider_home"]), "provider home")
        _absolute(str(document["provider_config_home"]), "provider config home")
        if document["configuration_digest"] != _canonical_digest(document):
            raise ProviderExecutionContextError("provider context digest is invalid")
        return ProviderExecutionContext(**document)

    def read(self, provider_id: str) -> ProviderExecutionContext:
        path = self._path(provider_id)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ProviderExecutionContextError("provider context is not configured") from error
        except (OSError, ValueError) as error:
            raise ProviderExecutionContextError("provider context is unreadable") from error
        context = self._decode(document)
        if context.provider_id != provider_id or context.instance_id != self._instance_id():
            raise ProviderExecutionContextError("provider context does not belong to this Forge instance")
        return context

    def configure(
        self,
        *,
        provider_id: str,
        provider_type: str,
        executable_path: str,
        provider_home: str,
        provider_config_home: str,
        profile: str | None = None,
        expected_digest: str | None = None,
    ) -> ProviderExecutionContext:
        """Create or guarded-replace one non-secret, instance-bound context."""
        provider_id = self._validate_provider_id(provider_id)
        if not isinstance(provider_type, str) or _PROVIDER_TYPE.fullmatch(provider_type) is None:
            raise ProviderExecutionContextError("provider type is invalid")
        executable_path = _absolute(executable_path, "provider executable")
        provider_home = _absolute(provider_home, "provider home")
        provider_config_home = _absolute(provider_config_home, "provider config home")
        if profile is not None and (not isinstance(profile, str) or not profile or "\x00" in profile):
            raise ProviderExecutionContextError("provider profile is invalid")

        path = self._path(provider_id)
        instance_id = self._instance_id()
        created_at = _timestamp()
        revision = 1
        if path.exists():
            existing = self.read(provider_id)
            if not expected_digest or expected_digest != existing.configuration_digest:
                raise ProviderExecutionContextError("provider context replacement requires the current digest")
            created_at = existing.created_at
            revision = existing.configuration_revision + 1
        elif expected_digest is not None:
            raise ProviderExecutionContextError("provider context does not exist for guarded replacement")

        updated_at = _timestamp()
        document: dict[str, Any] = {
            "schema_version": PROVIDER_CONTEXT_SCHEMA_VERSION,
            "instance_id": instance_id,
            "provider_id": provider_id,
            "provider_type": provider_type,
            "executable_path": executable_path,
            "provider_home": provider_home,
            "provider_config_home": provider_config_home,
            "profile": profile,
            "configuration_revision": revision,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        document["configuration_digest"] = _canonical_digest(document)
        self.context_root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.context_root, 0o700)
        temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory = os.open(
                self.context_root,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
            )
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return self.read(provider_id)
