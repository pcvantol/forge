#!/usr/bin/env python3
"""Qualify the r23 Workspace HTTP read contract from an installed wheel only."""
from __future__ import annotations

import hashlib
from importlib import resources
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator, FormatChecker

import forge
from forge.execution_host_configuration import (
    EngineeringPlatformPeerConfigurationService, read_peer_configuration,
)
from forge.runtime import RuntimeBootstrap
from forge.secure_store import SecretReference
from forge.server_runtime import ForgeServerRuntime, existing_instance


SOURCE = Path(__file__).resolve().parents[1]
INSTALLED_SCHEMA_BYTES = resources.files(forge).joinpath("api", "workspace-status-read-v1.json").read_bytes()
SCHEMA = json.loads(INSTALLED_SCHEMA_BYTES)


def _assert_installed() -> None:
    if Path(forge.__file__).resolve().is_relative_to(SOURCE / "forge"):
        raise AssertionError("Forge was imported from the source checkout")
    if INSTALLED_SCHEMA_BYTES != (SOURCE / "forge/api/workspace-status-read-v1.json").read_bytes():
        raise AssertionError("installed response contract differs from selected source")
    Draft202012Validator.check_schema(SCHEMA)


def _root(parent: Path, name: str, repository_id: str | None) -> Path:
    root = parent / name
    RuntimeBootstrap(data_root=root, forge_version="installed-r23-test").open().close()
    if repository_id is not None:
        EngineeringPlatformPeerConfigurationService(root).configure(
            binding_id="ep", endpoint="https://ep.test", expected_ep_instance_id="ep-instance",
            ep_consumer_id="consumer", execution_host_id="ep-host", ep_project_id="project",
            ep_repository_id=repository_id, repository_identity="source-repo",
            credential_reference=SecretReference.parse("keychain://forge.ep/consumer"),
            operator_id="operator",
        )
    credential = root / "admin-credential"
    credential.write_text("synthetic-admin-only\n", encoding="utf-8")
    credential.chmod(0o600)
    return root


def _grant(root: Path, action: str, *, token_path: Path | None = None) -> None:
    command = [str(Path(sys.executable).parent / "forge-workspace-read-grant"),
               "--data-root", str(root), action]
    if token_path is not None:
        command += ["--repository-id", "repo-1", "--token-file", str(token_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode or json.loads(result.stdout).get("status") not in {"ACTIVE", "REVOKED"}:
        raise AssertionError(f"installed read-grant command failed: {result.stdout}")


def _replace_repository(root: Path, repository_id: str) -> None:
    current = read_peer_configuration(root).configuration
    assert current is not None
    EngineeringPlatformPeerConfigurationService(root).configure(
        binding_id="ep", endpoint="https://ep.test", expected_ep_instance_id="ep-instance",
        ep_consumer_id="consumer", execution_host_id="ep-host", ep_project_id="project",
        ep_repository_id=repository_id, repository_identity="source-repo",
        credential_reference=SecretReference.parse("keychain://forge.ep/consumer"),
        operator_id="operator", replace=True,
        expected_revision=current.configuration_revision, expected_digest=current.configuration_digest,
    )


def _request(port: int, path: str, token: str | None, *, method: str = "GET") -> tuple[int, dict]:
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    request = Request(f"http://127.0.0.1:{port}{path}", headers=headers, method=method)
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        with error:
            return error.code, json.load(error)


def _server(root: Path) -> tuple[ForgeServerRuntime, Thread]:
    runtime = ForgeServerRuntime(data_root=root, credential_file=root / "admin-credential",
                                 host="127.0.0.1", port=0)
    thread = Thread(target=runtime.server.serve_forever, daemon=True)
    thread.start()
    return runtime, thread


def _close(runtime: ForgeServerRuntime, thread: Thread) -> None:
    runtime.server.shutdown()
    runtime.server.server_close()
    thread.join(timeout=3)


def main() -> int:
    _assert_installed()
    with TemporaryDirectory(prefix="forge-r23-installed-") as temporary:
        parent = Path(temporary)
        primary = _root(parent, "primary", "repo-1")
        token_path = primary / "workspace-token"
        _grant(primary, "issue", token_path=token_path)
        token = token_path.read_text(encoding="utf-8").strip()
        grant_path = primary / "credentials/workspace-read-grant.json"
        grant = json.loads(grant_path.read_text(encoding="utf-8"))
        if token in grant_path.read_text(encoding="utf-8"):
            raise AssertionError("grant stored a plaintext token")
        runtime, thread = _server(primary)
        try:
            port = runtime.server.server_port
            before = hashlib.sha256((primary / "forge.db").read_bytes()).hexdigest()
            for path, kind in (("/v1/instance", "instance"), ("/v1/status", "status")):
                status, body = _request(port, path, token)
                assert status == 200, (path, status, body)
                Draft202012Validator(SCHEMA | {"$ref": f"#/$defs/{kind}"},
                                     format_checker=FormatChecker()).validate(body)
                assert body["workspace_read_scope"] == {
                    "contract_version": "forge-workspace-status-read/v1",
                    "instance_id": existing_instance(primary).instance_id,
                    "repository_id": "repo-1",
                }
            assert _request(port, "/v1/instance", None)[0] == 401
            assert _request(port, "/v1/instance", "wrong")[0] == 401
            assert _request(port, "/v1/version", token)[0] == 403
            assert _request(port, "/v1/provider-context", token, method="POST")[0] == 403
            assert _request(port, "/v1/instance", "synthetic-admin-only")[0] == 200
            assert hashlib.sha256((primary / "forge.db").read_bytes()).hexdigest() == before
            _replace_repository(primary, "repo-2")
            changed_binding = hashlib.sha256((primary / "forge.db").read_bytes()).hexdigest()
            assert _request(port, "/v1/instance", token)[0] == 401
            assert hashlib.sha256((primary / "forge.db").read_bytes()).hexdigest() == changed_binding
            _replace_repository(primary, "repo-1")
            restored_binding = hashlib.sha256((primary / "forge.db").read_bytes()).hexdigest()
            assert _request(port, "/v1/instance", token)[0] == 200
            assert hashlib.sha256((primary / "forge.db").read_bytes()).hexdigest() == restored_binding
            next_token_path = primary / "workspace-token-next"
            _grant(primary, "rotate", token_path=next_token_path)
            next_token = next_token_path.read_text(encoding="utf-8").strip()
            assert _request(port, "/v1/instance", token)[0] == 401
            assert _request(port, "/v1/instance", next_token)[0] == 200
            _grant(primary, "revoke")
            assert _request(port, "/v1/instance", next_token)[0] == 401
            assert hashlib.sha256((primary / "forge.db").read_bytes()).hexdigest() == restored_binding
        finally:
            _close(runtime, thread)

        for name, repository_id, expected_id in (
            ("foreign-instance", "repo-1", False),
            ("missing-repository", None, True),
            ("foreign-repository", "repo-2", True),
        ):
            root = _root(parent, name, repository_id)
            copied = dict(grant)
            if expected_id:
                copied["instance_id"] = existing_instance(root).instance_id
            target = root / "credentials/workspace-read-grant.json"
            target.parent.mkdir()
            target.write_text(json.dumps(copied), encoding="utf-8")
            target.chmod(0o600)
            other, thread = _server(root)
            try:
                assert _request(other.server.server_port, "/v1/instance", token)[0] == 401, name
            finally:
                _close(other, thread)

    print(json.dumps({"status": "PASS", "installed_forge": str(Path(forge.__file__).resolve()),
                      "contract_sha256": hashlib.sha256(INSTALLED_SCHEMA_BYTES).hexdigest(),
                      "routes": ["GET /v1/instance", "GET /v1/status"],
                      "negatives": ["missing/wrong/revoked token", "write/other route", "foreign instance",
                                    "missing/foreign/changed repository"],
                      "primary_http_requests_mutated_forge_db": False,
                      "fixture_peer_configuration_replaced": True}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
