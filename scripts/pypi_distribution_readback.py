#!/usr/bin/env python3
"""Bounded, fail-closed PyPI readback for one Forge distribution release.

The classifier is pure.  Polling performs only cache-busted HTTP GET requests;
it cannot publish, replace, or delete a distribution.  A published filename
with an unexpected digest is an immediate identity conflict, while a missing
expected filename may be retried within the caller's explicit bound.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


_SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CACHE_TOKEN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class RegistryReadbackError(ValueError):
    """The registry readback input or response is not safely usable."""


class RegistryIdentityConflict(RegistryReadbackError):
    """A published filename is already bound to different bytes."""


class RegistryReadbackExhausted(RegistryReadbackError):
    """The bounded readback did not observe both expected artifacts."""


@dataclass(frozen=True)
class RegistryClassification:
    """Pure classification of one PyPI release-document snapshot."""

    state: str
    missing_filenames: tuple[str, ...]


@dataclass(frozen=True)
class RegistryReadbackResult:
    """Successful result for one bounded registry readback."""

    state: str
    attempts: int
    output: Path


def distribution_filenames(version: str) -> tuple[str, str]:
    """Return the exact two filenames owned by one Forge release."""
    if not isinstance(version, str) or _SEMVER.fullmatch(version) is None:
        raise RegistryReadbackError("Forge release version is invalid")
    return (
        f"forge_autonomy-{version}-py3-none-any.whl",
        f"forge_autonomy-{version}.tar.gz",
    )


def expected_digests_from_sha256sums(
    path: Path,
    expected_filenames: tuple[str, ...],
) -> dict[str, str]:
    """Load exact expected digests, normalizing qualified paths to basenames.

    ``sha256sum dist/file`` records ``dist/file``.  PyPI exposes only
    ``file``.  Normalization therefore belongs at this boundary, with duplicate
    basenames rejected so two qualified paths cannot ambiguously bind one
    published filename.
    """
    if not expected_filenames or len(set(expected_filenames)) != len(expected_filenames):
        raise RegistryReadbackError("expected distribution filenames are invalid")
    if any(not name or Path(name).name != name for name in expected_filenames):
        raise RegistryReadbackError("expected distribution filenames must be basenames")
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RegistryReadbackError("qualified SHA256SUMS is unavailable") from error

    wanted = set(expected_filenames)
    observed: dict[str, str] = {}
    for number, line in enumerate(lines, start=1):
        fields = line.split(maxsplit=1)
        if len(fields) != 2:
            raise RegistryReadbackError(f"qualified SHA256SUMS line {number} is invalid")
        digest, qualified_name = fields
        qualified_name = qualified_name.lstrip("*")
        if _SHA256.fullmatch(digest) is None or not qualified_name:
            raise RegistryReadbackError(f"qualified SHA256SUMS line {number} is invalid")
        basename = Path(qualified_name).name
        if basename not in wanted:
            continue
        if basename in observed:
            if observed[basename] != digest:
                raise RegistryIdentityConflict(
                    f"qualified SHA256SUMS contains conflicting paths for {basename}"
                )
            raise RegistryReadbackError(
                f"qualified SHA256SUMS contains a duplicate basename for {basename}"
            )
        observed[basename] = digest

    missing = sorted(wanted - set(observed))
    if missing:
        raise RegistryReadbackError(
            "qualified SHA256SUMS omits expected distribution filenames: "
            + ", ".join(missing)
        )
    return {name: observed[name] for name in expected_filenames}


def classify_pypi_document(
    document: object,
    expected_digests: Mapping[str, str],
) -> RegistryClassification:
    """Classify one response as READY or PENDING, or raise on conflict.

    PENDING is reserved for an otherwise valid release document that omits at
    least one expected filename.  A present filename with a different SHA-256
    is never retried because the immutable publication identity conflicts.
    """
    if not isinstance(expected_digests, Mapping) or not expected_digests:
        raise RegistryReadbackError("expected distribution digests are invalid")
    for filename, digest in expected_digests.items():
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or not isinstance(digest, str)
            or _SHA256.fullmatch(digest) is None
        ):
            raise RegistryReadbackError("expected distribution digests are invalid")
    if not isinstance(document, Mapping) or not isinstance(document.get("urls"), list):
        raise RegistryReadbackError("PyPI release document is invalid")

    observed: dict[str, str] = {}
    for item in document["urls"]:
        if not isinstance(item, Mapping):
            raise RegistryReadbackError("PyPI release document contains an invalid file entry")
        filename = item.get("filename")
        if filename not in expected_digests:
            continue
        if filename in observed:
            raise RegistryIdentityConflict(
                f"PyPI release document contains duplicate filename {filename}"
            )
        digests = item.get("digests")
        digest = digests.get("sha256") if isinstance(digests, Mapping) else None
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise RegistryReadbackError(
                f"PyPI release document omits a valid SHA-256 for {filename}"
            )
        if digest != expected_digests[filename]:
            raise RegistryIdentityConflict(
                f"PyPI publication identity conflicts for {filename}"
            )
        artifact_url = item.get("url")
        if not isinstance(artifact_url, str) or not artifact_url.startswith("https://"):
            raise RegistryReadbackError(
                f"PyPI release document omits a secure artifact URL for {filename}"
            )
        observed[filename] = digest

    missing = tuple(sorted(set(expected_digests) - set(observed)))
    return RegistryClassification("PENDING" if missing else "READY", missing)


def _registry_url(version: str, cache_token: str, attempt: int) -> str:
    base = f"https://pypi.org/pypi/forge-autonomy/{quote(version, safe='')}/json"
    return base + "?" + urlencode({"forge_readback": f"{cache_token}-{attempt}"})


def _fetch_document(
    version: str,
    cache_token: str,
    attempt: int,
    timeout_seconds: float,
    opener: Callable[..., object],
) -> object:
    request = Request(
        _registry_url(version, cache_token, attempt),
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    response = opener(request, timeout=timeout_seconds)
    with response:  # type: ignore[attr-defined]
        raw = response.read(_MAX_RESPONSE_BYTES + 1)  # type: ignore[attr-defined]
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise RegistryReadbackError("PyPI release document exceeds the readback limit")
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RegistryReadbackError("PyPI release document is not valid JSON") from error


def _atomic_json(path: Path, document: object) -> None:
    output = Path(path)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(document, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, output)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def poll_pypi_release(
    *,
    version: str,
    expected_digests: Mapping[str, str],
    output: Path,
    cache_token: str,
    attempts: int,
    interval_seconds: float,
    timeout_seconds: float,
    opener: Callable[..., object] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> RegistryReadbackResult:
    """Poll PyPI through bounded GET-only observations until READY."""
    distribution_filenames(version)
    if not isinstance(cache_token, str) or _CACHE_TOKEN.fullmatch(cache_token) is None:
        raise RegistryReadbackError("registry readback cache token is invalid")
    if not isinstance(attempts, int) or not 1 <= attempts <= 60:
        raise RegistryReadbackError("registry readback attempts must be between 1 and 60")
    if not isinstance(interval_seconds, (int, float)) or not 0 <= interval_seconds <= 60:
        raise RegistryReadbackError("registry readback interval must be between 0 and 60 seconds")
    if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 60:
        raise RegistryReadbackError("registry readback timeout must be between 0 and 60 seconds")

    last_state = "UNAVAILABLE"
    last_detail = "no registry response"
    for attempt in range(1, attempts + 1):
        try:
            document = _fetch_document(
                version, cache_token, attempt, float(timeout_seconds), opener,
            )
            classification = classify_pypi_document(document, expected_digests)
            last_state = classification.state
            last_detail = (
                "missing=" + ",".join(classification.missing_filenames)
                if classification.missing_filenames else "exact artifacts observed"
            )
            if classification.state == "READY":
                _atomic_json(output, document)
                return RegistryReadbackResult("READY", attempt, Path(output))
        except RegistryIdentityConflict:
            raise
        except (RegistryReadbackError, HTTPError, URLError, TimeoutError, OSError) as error:
            last_state = "UNAVAILABLE"
            last_detail = str(error)
        if attempt < attempts:
            sleeper(float(interval_seconds))

    raise RegistryReadbackExhausted(
        f"PyPI registry readback exhausted after {attempts} attempts "
        f"(last_state={last_state}; {last_detail})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read back one exact Forge PyPI release without publication authority."
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--hashes", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache-token", required=True)
    parser.add_argument("--attempts", type=int, default=24)
    parser.add_argument("--interval-seconds", type=float, default=15.0)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)

    try:
        filenames = distribution_filenames(args.version)
        expected = expected_digests_from_sha256sums(args.hashes, filenames)
        result = poll_pypi_release(
            version=args.version,
            expected_digests=expected,
            output=args.output,
            cache_token=args.cache_token,
            attempts=args.attempts,
            interval_seconds=args.interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    except RegistryIdentityConflict as error:
        parser.exit(2, f"PYPI_PUBLICATION_IDENTITY_CONFLICT: {error}\n")
    except RegistryReadbackExhausted as error:
        parser.exit(3, f"PYPI_REGISTRY_READBACK_EXHAUSTED: {error}\n")
    except RegistryReadbackError as error:
        parser.exit(4, f"PYPI_REGISTRY_READBACK_INVALID: {error}\n")
    print(json.dumps({"attempts": result.attempts, "state": result.state}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
