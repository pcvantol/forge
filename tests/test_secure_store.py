"""Deterministic qualification of bounded Keychain credential reads."""
from __future__ import annotations

import errno
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from forge.__main__ import main
from forge.secure_store import (
    CredentialAccessSetupService,
    CredentialAccessStatus,
    INTERACTIVE_CREDENTIAL_ACCESS_TIMEOUT_SECONDS,
    MacOSKeychainSecureStoreAdapter,
    SecretReference,
    SecretState,
    SecureStoreDiagnostic,
    SecureStoreResolution,
)


SYNTHETIC_SECRET = "KEYCHAIN_QUALIFICATION_SECRET_MUST_NOT_ESCAPE"
REFERENCE = SecretReference.parse("keychain://forge.test/consumer")


class _Reader:
    executable = "/usr/bin/security"

    def __init__(self, resolution: SecureStoreResolution) -> None:
        self.resolution = resolution
        self.references: list[str] = []

    def resolve_with_diagnostic(self, reference: SecretReference) -> SecureStoreResolution:
        self.references.append(reference.serialized)
        return self.resolution


class SecureStoreDiagnosticsTests(unittest.TestCase):
    def test_normal_read_keeps_the_short_default_timeout_and_never_enters_setup(self) -> None:
        observed: list[object] = []
        result = subprocess.CompletedProcess([], 0, stdout=SYNTHETIC_SECRET + "\n", stderr="")
        adapter = MacOSKeychainSecureStoreAdapter(
            runner=lambda argv, **kwargs: observed.append((argv, kwargs["timeout"])) or result,
        )

        state, material = adapter.resolve(REFERENCE)

        self.assertEqual((state, material), (SecretState.RESOLVABLE, SYNTHETIC_SECRET))
        self.assertEqual(observed, [([
            "/usr/bin/security", "find-generic-password", "-s", "forge.test", "-a", "consumer", "-w",
        ], 5.0)])

    def test_timeout_is_specific_and_its_captured_secret_never_enters_the_diagnostic(self) -> None:
        def timeout(*_args: object, **_kwargs: object):
            raise subprocess.TimeoutExpired("/usr/bin/security", 5.0, output=SYNTHETIC_SECRET)

        resolution = MacOSKeychainSecureStoreAdapter(runner=timeout).resolve_with_diagnostic(REFERENCE)
        diagnostic = resolution.diagnostic

        self.assertEqual(resolution.state, SecretState.TIMEOUT)
        self.assertEqual(diagnostic.code if diagnostic else None, "KEYCHAIN_SUBPROCESS_TIMEOUT")
        self.assertEqual(diagnostic.timeout_seconds if diagnostic else None, 5.0)
        self.assertNotIn(SYNTHETIC_SECRET, json.dumps(diagnostic.to_safe_dict() if diagnostic else {}))
        self.assertNotIn(SYNTHETIC_SECRET, repr(diagnostic))

    def test_process_start_failure_is_distinct_from_timeout(self) -> None:
        def start_failure(*_args: object, **_kwargs: object):
            raise OSError(errno.ENOENT, "missing security executable")

        resolution = MacOSKeychainSecureStoreAdapter(runner=start_failure).resolve_with_diagnostic(REFERENCE)

        self.assertEqual(resolution.state, SecretState.PROCESS_START_FAILED)
        self.assertEqual(resolution.diagnostic.code if resolution.diagnostic else None, "KEYCHAIN_PROCESS_START_FAILED")
        self.assertEqual(resolution.diagnostic.errno if resolution.diagnostic else None, errno.ENOENT)

    def test_missing_denied_and_other_command_errors_remain_fail_closed_and_distinct(self) -> None:
        cases = (
            ("The specified item could not be found in the keychain.", SecretState.MISSING, "KEYCHAIN_ITEM_NOT_FOUND"),
            ("User interaction is not allowed.", SecretState.ACCESS_DENIED, "KEYCHAIN_ACCESS_DENIED"),
            ("unrecognized failure", SecretState.COMMAND_FAILED, "KEYCHAIN_COMMAND_FAILED"),
        )
        for stderr, expected_state, expected_code in cases:
            with self.subTest(stderr=stderr):
                resolution = MacOSKeychainSecureStoreAdapter(
                    runner=lambda *_args, stderr=stderr, **_kwargs: subprocess.CompletedProcess(
                        [], 44, stdout="", stderr=stderr,
                    )
                ).resolve_with_diagnostic(REFERENCE)
                self.assertEqual(resolution.state, expected_state)
                self.assertEqual(resolution.diagnostic.code if resolution.diagnostic else None, expected_code)
                self.assertIsNone(resolution.material)

    def test_interactive_setup_requires_opt_in_then_uses_one_longer_bounded_read_without_a_peer(self) -> None:
        reader = _Reader(SecureStoreResolution(SecretState.RESOLVABLE, SYNTHETIC_SECRET))
        factory_timeouts: list[float] = []
        service = CredentialAccessSetupService(
            reader_factory=lambda timeout: factory_timeouts.append(timeout) or reader,
        )

        not_requested = service.read(REFERENCE, interactive=False)
        self.assertEqual(not_requested.status, CredentialAccessStatus.INTERACTIVE_OPT_IN_REQUIRED)
        self.assertEqual(factory_timeouts, [])
        self.assertEqual(reader.references, [])

        setup = service.read(REFERENCE, interactive=True)
        encoded = json.dumps(setup.to_safe_dict(), sort_keys=True)
        self.assertTrue(setup.succeeded)
        self.assertEqual(setup.status, CredentialAccessStatus.INTERACTIVE_CREDENTIAL_READ_SUCCEEDED)
        self.assertEqual(factory_timeouts, [INTERACTIVE_CREDENTIAL_ACCESS_TIMEOUT_SECONDS])
        self.assertEqual(reader.references, [REFERENCE.serialized])
        self.assertEqual(setup.access_requesting_executable, "/usr/bin/security")
        self.assertNotIn(SYNTHETIC_SECRET, encoded)

    def test_interactive_setup_rejects_overlong_timeout_and_does_not_retry(self) -> None:
        with self.assertRaisesRegex(ValueError, "at most 120"):
            CredentialAccessSetupService(timeout_seconds=120.1)

        reader = _Reader(SecureStoreResolution(
            SecretState.TIMEOUT,
            None,
            SecureStoreDiagnostic("KEYCHAIN_SUBPROCESS_TIMEOUT", "KEYCHAIN_CREDENTIAL_READ", timeout_seconds=120.0),
        ))
        service = CredentialAccessSetupService(reader_factory=lambda _timeout: reader)
        result = service.read(REFERENCE, interactive=True)
        self.assertFalse(result.succeeded)
        self.assertEqual(result.status, CredentialAccessStatus.INTERACTIVE_CREDENTIAL_READ_FAILED)
        self.assertEqual(result.credential_state, SecretState.TIMEOUT)
        self.assertEqual(reader.references, [REFERENCE.serialized])

    def test_interface_reader_diagnostic_and_executable_are_redacted_before_any_result_is_rendered(self) -> None:
        reader = _Reader(SecureStoreResolution(
            SecretState.TIMEOUT,
            None,
            SecureStoreDiagnostic(
                SYNTHETIC_SECRET, SYNTHETIC_SECRET, context=SYNTHETIC_SECRET,
            ),
        ))
        reader.executable = "/tmp/" + SYNTHETIC_SECRET
        result = CredentialAccessSetupService(reader_factory=lambda _timeout: reader).read(REFERENCE, interactive=True)
        rendered = json.dumps(result.to_safe_dict(), sort_keys=True) + repr(result)

        self.assertEqual(result.diagnostic.code, "SECURE_STORE_DIAGNOSTIC_REDACTED")
        self.assertIsNone(result.access_requesting_executable)
        self.assertNotIn(SYNTHETIC_SECRET, rendered)

    def test_cli_management_route_needs_no_peer_binding_or_initialized_data_root_and_never_prints_secret(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "not-initialized"
            output, errors = StringIO(), StringIO()
            keychain_result = subprocess.CompletedProcess([], 0, stdout=SYNTHETIC_SECRET + "\n", stderr="")
            with (patch("forge.secure_store.subprocess.run", return_value=keychain_result),
                  redirect_stdout(output), redirect_stderr(errors)):
                code = main([
                    "--data-root", str(root), "execution-host", "credential-access",
                    "--interactive", "--credential-reference", REFERENCE.serialized,
                ])

            report = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "INTERACTIVE_CREDENTIAL_READ_SUCCEEDED")
            self.assertEqual(report["credential_state"], "RESOLVABLE")
            self.assertFalse(root.exists())
            self.assertIn("macOS may ask", errors.getvalue())
            self.assertIn("/usr/bin/security", errors.getvalue())
            self.assertNotIn(SYNTHETIC_SECRET, output.getvalue() + errors.getvalue())

    def test_cli_management_route_without_opt_in_does_not_call_keychain(self) -> None:
        output = StringIO()
        with (patch("forge.secure_store.subprocess.run") as runner,
              redirect_stdout(output)):
            code = main([
                "execution-host", "credential-access", "--credential-reference", REFERENCE.serialized,
            ])

        report = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "INTERACTIVE_OPT_IN_REQUIRED")
        runner.assert_not_called()

    def test_cli_management_route_rejects_multiple_references_before_keychain(self) -> None:
        output = StringIO()
        with (patch("forge.secure_store.subprocess.run") as runner,
              redirect_stdout(output)):
            code = main([
                "execution-host", "credential-access", "--interactive",
                "--credential-reference", REFERENCE.serialized,
                "--credential-reference", "keychain://forge.test/other",
            ])

        report = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "ERROR")
        self.assertIn("exactly one credential reference", report["error"])
        runner.assert_not_called()
