"""Typed, explicit-reference access to operator-owned secure storage.

Forge persists only :class:`SecretReference` values.  Secret material is
resolved at the transport boundary and is never represented by a durable
Forge record.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from math import isfinite
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
    TIMEOUT = "TIMEOUT"
    PROCESS_START_FAILED = "PROCESS_START_FAILED"
    COMMAND_FAILED = "COMMAND_FAILED"


@dataclass(frozen=True)
class SecureStoreDiagnostic:
    """Redacted, stable detail for one secure-store operation failure.

    In particular, this deliberately does not retain process output.  A
    ``security -w`` invocation can place credential material in stdout, and
    ``TimeoutExpired`` can carry captured process output on its exception.
    """

    code: str
    operation: str
    timeout_seconds: float | None = None
    returncode: int | None = None
    errno: int | None = None
    context: str | None = None

    def to_safe_dict(self) -> dict[str, object]:
        """Return only bounded metadata that is safe for an operator report.

        Reader implementations are interface-neutral and therefore cannot be
        trusted to supply printable diagnostics.  Code, operation and context
        are selected from this module's closed table rather than copied from a
        reader-provided object.
        """
        safe = _SAFE_DIAGNOSTIC_DETAILS.get(self.code) if isinstance(self.code, str) else None
        if safe is None:
            code, operation, context = (
                "SECURE_STORE_DIAGNOSTIC_REDACTED",
                "KEYCHAIN_CREDENTIAL_READ",
                "an unrecognized secure-store diagnostic was redacted",
            )
        else:
            code, operation, context = self.code, safe[0], safe[1]
        result: dict[str, object] = {"code": code, "operation": operation, "context": context}
        if (isinstance(self.timeout_seconds, (int, float)) and not isinstance(self.timeout_seconds, bool)
                and isfinite(float(self.timeout_seconds)) and 0 < float(self.timeout_seconds) <= 120):
            result["timeout_seconds"] = float(self.timeout_seconds)
        if (isinstance(self.returncode, int) and not isinstance(self.returncode, bool)
                and -255 <= self.returncode <= 255):
            result["returncode"] = self.returncode
        if isinstance(self.errno, int) and not isinstance(self.errno, bool) and 0 <= self.errno <= 4095:
            result["errno"] = self.errno
        return result

    def redacted(self) -> "SecureStoreDiagnostic":
        """Return a copy that remains safe even if later rendered with ``repr``."""
        safe = self.to_safe_dict()
        return SecureStoreDiagnostic(
            code=str(safe["code"]),
            operation=str(safe["operation"]),
            timeout_seconds=safe.get("timeout_seconds") if isinstance(safe.get("timeout_seconds"), float) else None,
            returncode=safe.get("returncode") if isinstance(safe.get("returncode"), int) else None,
            errno=safe.get("errno") if isinstance(safe.get("errno"), int) else None,
            context=str(safe["context"]),
        )


_SAFE_DIAGNOSTIC_DETAILS: dict[str, tuple[str, str]] = {
    "EXPLICIT_INTERACTIVE_OPT_IN_REQUIRED": (
        "INTERACTIVE_CREDENTIAL_READ", "pass --interactive to request one local Keychain credential read",
    ),
    "INVALID_CREDENTIAL_REFERENCE": (
        "KEYCHAIN_CREDENTIAL_READ", "the credential reference is invalid",
    ),
    "KEYCHAIN_CREDENTIAL_READ_SUCCEEDED": (
        "INTERACTIVE_CREDENTIAL_READ", "one explicit credential read completed",
    ),
    "KEYCHAIN_SUBPROCESS_TIMEOUT": (
        "KEYCHAIN_CREDENTIAL_READ",
        "access to Keychain took too long; complete explicit credential-access setup and retry normal preflight",
    ),
    "KEYCHAIN_PROCESS_START_FAILED": (
        "KEYCHAIN_CREDENTIAL_READ", "the Keychain reader process could not be started",
    ),
    "KEYCHAIN_EMPTY_MATERIAL": (
        "KEYCHAIN_CREDENTIAL_READ", "the Keychain item returned no credential material",
    ),
    "KEYCHAIN_ITEM_NOT_FOUND": (
        "KEYCHAIN_CREDENTIAL_READ", "the explicit Keychain item was not found",
    ),
    "KEYCHAIN_ACCESS_DENIED": (
        "KEYCHAIN_CREDENTIAL_READ", "macOS denied access to the explicit Keychain item",
    ),
    "KEYCHAIN_COMMAND_FAILED": (
        "KEYCHAIN_CREDENTIAL_READ", "the Keychain reader command failed without a recognized access result",
    ),
}


@dataclass(frozen=True)
class SecureStoreResolution:
    """One in-memory secure-store read and its redacted diagnostic, if any."""

    state: SecretState
    material: str | None
    diagnostic: SecureStoreDiagnostic | None = None


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


class CredentialAccessReader(Protocol):
    """The narrow reader capability used by explicit local access setup."""

    def resolve_with_diagnostic(self, reference: SecretReference) -> SecureStoreResolution: ...


INTERACTIVE_CREDENTIAL_ACCESS_TIMEOUT_SECONDS = 120.0
_INTERACTIVE_CREDENTIAL_ACCESS_OPERATION = "INTERACTIVE_CREDENTIAL_READ"


class CredentialAccessStatus(str, Enum):
    INTERACTIVE_CREDENTIAL_READ_SUCCEEDED = "INTERACTIVE_CREDENTIAL_READ_SUCCEEDED"
    INTERACTIVE_CREDENTIAL_READ_FAILED = "INTERACTIVE_CREDENTIAL_READ_FAILED"
    INTERACTIVE_OPT_IN_REQUIRED = "INTERACTIVE_OPT_IN_REQUIRED"


@dataclass(frozen=True)
class CredentialAccessSetupResult:
    """Secret-free result for an explicit local credential-access request."""

    status: CredentialAccessStatus
    credential_state: SecretState | None
    diagnostic: SecureStoreDiagnostic
    access_requesting_executable: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is CredentialAccessStatus.INTERACTIVE_CREDENTIAL_READ_SUCCEEDED

    def to_safe_dict(self) -> dict[str, object]:
        diagnostic = self.diagnostic.to_safe_dict()
        if self.access_requesting_executable is not None:
            diagnostic["access_requesting_executable"] = self.access_requesting_executable
        result: dict[str, object] = {
            "status": self.status.value,
            "operation": _INTERACTIVE_CREDENTIAL_ACCESS_OPERATION,
            "diagnostic": diagnostic,
        }
        if self.credential_state is not None:
            result["credential_state"] = self.credential_state.value
        return result


class CredentialAccessSetupService:
    """Run exactly one opt-in, bounded credential read before peer binding.

    This service owns neither a peer configuration nor a Keychain policy.  It
    simply gives the local user an explicit opportunity to complete the native
    Keychain decision that the existing reader asks macOS to make.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = INTERACTIVE_CREDENTIAL_ACCESS_TIMEOUT_SECONDS,
        reader_factory: Callable[[float], CredentialAccessReader] | None = None,
    ) -> None:
        if (not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool)
                or not 0 < float(timeout_seconds) <= INTERACTIVE_CREDENTIAL_ACCESS_TIMEOUT_SECONDS):
            raise ValueError("interactive credential-access timeout must be greater than zero and at most 120 seconds")
        self._timeout_seconds = float(timeout_seconds)
        self._reader_factory = reader_factory or (lambda timeout: MacOSKeychainSecureStoreAdapter(timeout=timeout))

    def read(self, reference: SecretReference, *, interactive: bool) -> CredentialAccessSetupResult:
        """Read one validated reference once, only after explicit opt-in."""
        if not interactive:
            return CredentialAccessSetupResult(
                CredentialAccessStatus.INTERACTIVE_OPT_IN_REQUIRED,
                None,
                SecureStoreDiagnostic(
                    "EXPLICIT_INTERACTIVE_OPT_IN_REQUIRED",
                    _INTERACTIVE_CREDENTIAL_ACCESS_OPERATION,
                    timeout_seconds=self._timeout_seconds,
                    context="pass --interactive to request one local Keychain credential read",
                ),
            )
        if not isinstance(reference, SecretReference):
            return CredentialAccessSetupResult(
                CredentialAccessStatus.INTERACTIVE_CREDENTIAL_READ_FAILED,
                SecretState.INVALID_REFERENCE,
                SecureStoreDiagnostic(
                    "INVALID_CREDENTIAL_REFERENCE",
                    _INTERACTIVE_CREDENTIAL_ACCESS_OPERATION,
                    timeout_seconds=self._timeout_seconds,
                    context="the credential reference is invalid",
                ),
            )
        try:
            reference.validate()
        except ValueError:
            return CredentialAccessSetupResult(
                CredentialAccessStatus.INTERACTIVE_CREDENTIAL_READ_FAILED,
                SecretState.INVALID_REFERENCE,
                SecureStoreDiagnostic(
                    "INVALID_CREDENTIAL_REFERENCE",
                    _INTERACTIVE_CREDENTIAL_ACCESS_OPERATION,
                    timeout_seconds=self._timeout_seconds,
                    context="the credential reference is invalid",
                ),
            )
        reader = self._reader_factory(self._timeout_seconds)
        resolution = reader.resolve_with_diagnostic(reference)
        executable = getattr(reader, "executable", None)
        requesting_executable = executable if executable == MacOSKeychainSecureStoreAdapter.executable else None
        diagnostic = (resolution.diagnostic.redacted() if resolution.diagnostic is not None else SecureStoreDiagnostic(
            "KEYCHAIN_CREDENTIAL_READ_SUCCEEDED",
            _INTERACTIVE_CREDENTIAL_ACCESS_OPERATION,
            timeout_seconds=self._timeout_seconds,
            context="one explicit credential read completed",
        ))
        return CredentialAccessSetupResult(
            (CredentialAccessStatus.INTERACTIVE_CREDENTIAL_READ_SUCCEEDED
             if resolution.state is SecretState.RESOLVABLE and resolution.material else
             CredentialAccessStatus.INTERACTIVE_CREDENTIAL_READ_FAILED),
            resolution.state,
            diagnostic,
            requesting_executable,
        )


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

    def resolve_with_diagnostic(self, reference: SecretReference) -> SecureStoreResolution:
        """Resolve one item and retain only redacted failure classification.

        The normal runtime calls :meth:`resolve`, which deliberately preserves
        its tuple contract and its short default timeout.  The richer result is
        used only by the explicit local credential-access management path.
        """
        try:
            service, account = self._parts(reference)
        except ValueError:
            return SecureStoreResolution(
                SecretState.INVALID_REFERENCE,
                None,
                SecureStoreDiagnostic(
                    "INVALID_CREDENTIAL_REFERENCE", "KEYCHAIN_CREDENTIAL_READ",
                    context="the credential reference is invalid",
                ),
            )
        try:
            result = self._runner(
                [self.executable, "find-generic-password", "-s", service, "-a", account, "-w"],
                capture_output=True, text=True, timeout=self._timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            # Do not inspect this exception: captured stdout could be secret material.
            return SecureStoreResolution(
                SecretState.TIMEOUT,
                None,
                SecureStoreDiagnostic(
                    "KEYCHAIN_SUBPROCESS_TIMEOUT", "KEYCHAIN_CREDENTIAL_READ",
                    timeout_seconds=float(self._timeout),
                    context="access to Keychain took too long; complete explicit credential-access setup and retry normal preflight",
                ),
            )
        except OSError as error:
            return SecureStoreResolution(
                SecretState.PROCESS_START_FAILED,
                None,
                SecureStoreDiagnostic(
                    "KEYCHAIN_PROCESS_START_FAILED", "KEYCHAIN_CREDENTIAL_READ",
                    errno=error.errno if isinstance(error.errno, int) else None,
                    context="the Keychain reader process could not be started",
                ),
            )
        returncode = result.returncode if isinstance(getattr(result, "returncode", None), int) else None
        if returncode == 0:
            output = result.stdout if isinstance(getattr(result, "stdout", None), str) else ""
            material = output.rstrip("\n")
            if material:
                return SecureStoreResolution(SecretState.RESOLVABLE, material)
            return SecureStoreResolution(
                SecretState.MISSING,
                None,
                SecureStoreDiagnostic(
                    "KEYCHAIN_EMPTY_MATERIAL", "KEYCHAIN_CREDENTIAL_READ",
                    returncode=returncode,
                    context="the Keychain item returned no credential material",
                ),
            )
        error = (getattr(result, "stderr", "") or "").lower()
        if "could not be found" in error or "item not found" in error:
            return SecureStoreResolution(
                SecretState.MISSING,
                None,
                SecureStoreDiagnostic(
                    "KEYCHAIN_ITEM_NOT_FOUND", "KEYCHAIN_CREDENTIAL_READ", returncode=returncode,
                    context="the explicit Keychain item was not found",
                ),
            )
        if any(marker in error for marker in (
            "not allowed", "errsecauthfailed", "authorization denied", "access denied",
        )):
            return SecureStoreResolution(
                SecretState.ACCESS_DENIED,
                None,
                SecureStoreDiagnostic(
                    "KEYCHAIN_ACCESS_DENIED", "KEYCHAIN_CREDENTIAL_READ", returncode=returncode,
                    context="macOS denied access to the explicit Keychain item",
                ),
            )
        return SecureStoreResolution(
            SecretState.COMMAND_FAILED,
            None,
            SecureStoreDiagnostic(
                "KEYCHAIN_COMMAND_FAILED", "KEYCHAIN_CREDENTIAL_READ", returncode=returncode,
                context="the Keychain reader command failed without a recognized access result",
            ),
        )

    def resolve(self, reference: SecretReference) -> tuple[SecretState, str | None]:
        resolution = self.resolve_with_diagnostic(reference)
        return resolution.state, resolution.material

    def status(self, reference: SecretReference) -> SecretState:
        return self.resolve(reference)[0]
