"""Regression tests for bounded, identity-safe Forge PyPI readback."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


MODULE = Path(__file__).parents[1] / "scripts" / "pypi_distribution_readback.py"
SPEC = importlib.util.spec_from_file_location("forge_pypi_distribution_readback", MODULE)
assert SPEC and SPEC.loader
readback = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readback
SPEC.loader.exec_module(readback)


class _Response:
    def __init__(self, document: object) -> None:
        self._payload = json.dumps(document).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._payload[:limit]


class _Opener:
    def __init__(self, documents: list[object]) -> None:
        self._documents = iter(documents)
        self.requests: list[tuple[object, float]] = []

    def __call__(self, request: object, *, timeout: float) -> _Response:
        self.requests.append((request, timeout))
        return _Response(next(self._documents))


class PyPIDistributionReadbackTests(unittest.TestCase):
    version = "2.7.22"
    wheel, sdist = readback.distribution_filenames(version)
    wheel_digest = "1" * 64
    sdist_digest = "2" * 64
    expected = {wheel: wheel_digest, sdist: sdist_digest}

    @classmethod
    def document(cls, *, wheel: str | None = None, sdist: str | None = None) -> dict[str, object]:
        urls: list[dict[str, object]] = []
        if wheel is not None:
            urls.append({
                "filename": cls.wheel,
                "digests": {"sha256": wheel},
                "url": "https://files.pythonhosted.org/forge-wheel",
            })
        if sdist is not None:
            urls.append({
                "filename": cls.sdist,
                "digests": {"sha256": sdist},
                "url": "https://files.pythonhosted.org/forge-sdist",
            })
        return {"urls": urls}

    def test_sha256sums_normalizes_qualified_paths_to_pypi_basenames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sums = Path(directory) / "SHA256SUMS"
            sums.write_text(
                f"{self.wheel_digest}  dist/{self.wheel}\n"
                f"{self.sdist_digest}  dist/{self.sdist}\n",
                encoding="utf-8",
            )

            self.assertEqual(
                self.expected,
                readback.expected_digests_from_sha256sums(
                    sums, (self.wheel, self.sdist),
                ),
            )

    def test_sha256sums_rejects_conflicting_duplicate_basenames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sums = Path(directory) / "SHA256SUMS"
            sums.write_text(
                f"{self.wheel_digest}  dist/{self.wheel}\n"
                f"{'3' * 64}  rebuilt/{self.wheel}\n"
                f"{self.sdist_digest}  dist/{self.sdist}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                readback.RegistryIdentityConflict, "conflicting paths",
            ):
                readback.expected_digests_from_sha256sums(
                    sums, (self.wheel, self.sdist),
                )

    def test_missing_expected_filename_is_pending(self) -> None:
        classified = readback.classify_pypi_document(
            self.document(sdist=self.sdist_digest), self.expected,
        )

        self.assertEqual("PENDING", classified.state)
        self.assertEqual((self.wheel,), classified.missing_filenames)

    def test_present_filename_with_wrong_digest_is_immediate_conflict(self) -> None:
        with self.assertRaisesRegex(
            readback.RegistryIdentityConflict, self.wheel,
        ):
            readback.classify_pypi_document(
                self.document(wheel="f" * 64, sdist=self.sdist_digest),
                self.expected,
            )

    def test_ready_requires_both_exact_digests(self) -> None:
        classified = readback.classify_pypi_document(
            self.document(wheel=self.wheel_digest, sdist=self.sdist_digest),
            self.expected,
        )

        self.assertEqual("READY", classified.state)
        self.assertEqual((), classified.missing_filenames)

    def test_bounded_poll_uses_no_cache_gets_until_ready(self) -> None:
        opener = _Opener([
            self.document(sdist=self.sdist_digest),
            self.document(wheel=self.wheel_digest, sdist=self.sdist_digest),
        ])
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pypi.json"
            result = readback.poll_pypi_release(
                version=self.version,
                expected_digests=self.expected,
                output=output,
                cache_token="run-123-attempt-1",
                attempts=3,
                interval_seconds=0.25,
                timeout_seconds=4,
                opener=opener,
                sleeper=sleeps.append,
            )

            self.assertEqual(readback.RegistryReadbackResult("READY", 2, output), result)
            self.assertEqual([0.25], sleeps)
            self.assertEqual(2, len(opener.requests))
            first, second = (entry[0] for entry in opener.requests)
            self.assertEqual("GET", first.get_method())
            self.assertEqual("no-cache", first.get_header("Cache-control"))
            self.assertEqual("no-cache", first.get_header("Pragma"))
            self.assertIn("forge_readback=run-123-attempt-1-1", first.full_url)
            self.assertIn("forge_readback=run-123-attempt-1-2", second.full_url)
            self.assertEqual(
                self.document(wheel=self.wheel_digest, sdist=self.sdist_digest),
                json.loads(output.read_text(encoding="utf-8")),
            )

    def test_identity_conflict_stops_without_retry_or_output(self) -> None:
        opener = _Opener([
            self.document(wheel="f" * 64, sdist=self.sdist_digest),
            self.document(wheel=self.wheel_digest, sdist=self.sdist_digest),
        ])
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pypi.json"
            with self.assertRaises(readback.RegistryIdentityConflict):
                readback.poll_pypi_release(
                    version=self.version,
                    expected_digests=self.expected,
                    output=output,
                    cache_token="run-123-attempt-1",
                    attempts=3,
                    interval_seconds=0,
                    timeout_seconds=4,
                    opener=opener,
                    sleeper=sleeps.append,
                )

            self.assertEqual(1, len(opener.requests))
            self.assertEqual([], sleeps)
            self.assertFalse(output.exists())

    def test_exhaustion_is_bounded_and_writes_no_readback(self) -> None:
        opener = _Opener([
            self.document(sdist=self.sdist_digest),
            self.document(sdist=self.sdist_digest),
            self.document(sdist=self.sdist_digest),
        ])
        sleeps: list[float] = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "pypi.json"
            with self.assertRaisesRegex(
                readback.RegistryReadbackExhausted, "after 3 attempts",
            ):
                readback.poll_pypi_release(
                    version=self.version,
                    expected_digests=self.expected,
                    output=output,
                    cache_token="run-123-attempt-1",
                    attempts=3,
                    interval_seconds=0.5,
                    timeout_seconds=4,
                    opener=opener,
                    sleeper=sleeps.append,
                )

            self.assertEqual(3, len(opener.requests))
            self.assertEqual([0.5, 0.5], sleeps)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
