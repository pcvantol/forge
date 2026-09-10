"""Typed, explicit-reference access to operator-owned secure storage.

Forge persists only :class:`SecretReference` values.  Secret material is
resolved at the transport boundary and is never represented by a durable
Forge record.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import re
import subprocess
from typing import Callable, Protocol
from urllib.parse import parse_qsl, urlencode, urlparse


class SecretState(str, Enum):
    RESOLVABLE = "RESOLVABLE"
    MISSING = "MISSING"
    REVOKED = "REVOKED"
    ROTATED_INVALID = "ROTATED_INVALID"
    STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
    INVALID_REFERENCE = "INVALID_REFERENCE"
    ACCESS_DENIED = "ACCESS_DENIED"


@dataclass(frozen=True)
class SecretReference:
    """One opaque, canonical reference; never a secret value."""

    scheme: str
    identifier: str

    def __post_init__(self) -> None:
        self.validate()
        object.__setattr__(self, "identifier", self._canonical_identifier())

    def validate(self) -> None:
        try:
            if (self.scheme != "keychain" or not isinstance(self.identifier, str)
                    or not self.identifier or len(self.identifier) > 512):
                raise ValueError
            if any(ord(char) < 32 for char in self.identifier) or "%" in self.identifier:
                raise ValueError
            parsed = urlparse(self.identifier)
            if (parsed.scheme or parsed.username or parsed.password or parsed.port
                    or parsed.fragment or not parsed.netloc):
                raise ValueError
            parts = parsed.path.split("/")
            if (len(parts) != 2 or not parts[1]
                    or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", parsed.netloc)
                    or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", parts[1])):
                raise ValueError
            query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
            if (len(query) != len({key for key, _ in query})
                    or any(key not in {"namespace", "version"}
                           or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value)
                           for key, value in query)):
                raise ValueError
        except (UnicodeError, ValueError):
            raise ValueError("invalid secret reference") from None

    def _canonical_identifier(self) -> str:
        parsed = urlparse(self.identifier)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True))
        suffix = urlencode([(key, query[key]) for key in ("namespace", "version") if key in query])
        return f"//{parsed.netloc}/{parsed.path[1:]}" + (f"?{suffix}" if suffix else "")

    @property
    def fingerprint(self) -> str:
        return "sha256:" + sha256(self.serialized.encode()).hexdigest()

    @property
    def serialized(self) -> str:
        return f"{self.scheme}:{self.identifier}"

    @classmethod
    def parse(cls, value: str) -> "SecretReference":
        try:
            scheme, identifier = value.split(":", 1)
        except (AttributeError, ValueError):
            raise ValueError("invalid secret reference") from None
        return cls(scheme, identifier)


class SecureStorePort(Protocol):
    def status(self, reference: SecretReference) -> SecretState: ...

    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]: ...


class MacOSKeychainSecureStoreAdapter:
    """Resolve one explicit generic-password item without enumerating Keychain."""

    executable = "/usr/bin/security"

    def __init__(self, runner: Callable[..., object] | None = None, timeout: float = 5.0) -> None:
        self._runner, self._timeout = runner or subprocess.run, timeout

    @staticmethod
    def _parts(reference: SecretReference) -> tuple[str, str]:
        reference.validate()
        if reference.scheme != "keychain":
            raise ValueError("unexpected secure-store scheme")
        parsed = urlparse(reference.identifier)
        if parsed.scheme or not parsed.netloc:
            raise ValueError("invalid keychain reference")
        path = [parsed.netloc, *[item for item in parsed.path.split("/") if item]]
        query = parse_qsl(parsed.query, keep_blank_values=True)
        if (len(path) != 2 or not all(path) or len(query) != len(set(query))
                or any(key not in {"namespace", "version"} or not value for key, value in query)):
            raise ValueError("invalid keychain reference")
        return path[0], path[1]

    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        try:
            service, account = self._parts(reference)
        except ValueError:
            return SecretState.INVALID_REFERENCE, None
        try:
            result = self._runner(
                [self.executable, "find-generic-password", "-s", service, "-a", account, "-w"],
                capture_output=True, text=True, timeout=self._timeout, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return SecretState.STORE_UNAVAILABLE, None
        if result.returncode == 0:
            material = result.stdout.rstrip("\n")
            return (SecretState.RESOLVABLE, material) if material else (SecretState.MISSING, None)
        error = (result.stderr or "").lower()
        if "could not be found" in error or "item not found" in error:
            return SecretState.MISSING, None
        if "not allowed" in error or "user interaction is not allowed" in error:
            return SecretState.ACCESS_DENIED, None
        return SecretState.STORE_UNAVAILABLE, None

    def status(self, reference: SecretReference) -> SecretState:
        return self.resolve(reference)[0]
