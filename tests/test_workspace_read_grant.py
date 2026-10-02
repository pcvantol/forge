"""Security and lifecycle qualification for the installed Workspace read grant."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from forge.execution_host_configuration import EngineeringPlatformPeerConfigurationService
from forge.runtime import RuntimeBootstrap
from forge.secure_store import SecretReference
from forge.server_runtime import existing_instance
from forge.workspace_read_grant import WorkspaceReadGrant, main


class WorkspaceReadGrantTests(unittest.TestCase):
    def _instance(self, temporary: str, *, bind_repository: bool = True) -> tuple[Path, WorkspaceReadGrant]:
        root = Path(temporary) / "forge-instance"
        RuntimeBootstrap(data_root=root, forge_version="test").open().close()
        if bind_repository:
            EngineeringPlatformPeerConfigurationService(root).configure(
                binding_id="ep", endpoint="https://ep.test", expected_ep_instance_id="ep-instance",
                ep_consumer_id="consumer", execution_host_id="ep-host", ep_project_id="project",
                ep_repository_id="repo-1", repository_identity="source-repo",
                credential_reference=SecretReference.parse("keychain://forge.ep/consumer"),
                operator_id="operator",
            )
        grant = WorkspaceReadGrant(root, existing_instance(root).instance_id,
                                   root / "credentials" / "workspace-read-grant.json")
        return root, grant

    def test_binding_private_files_rotation_and_revoke(self) -> None:
        with TemporaryDirectory() as temporary:
            root, grant = self._instance(temporary)
            token_path = root / "token-1"
            self.assertEqual(grant.issue("repo-1", token_path), 1)
            token = token_path.read_text(encoding="utf-8").strip()
            self.assertEqual(grant.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(token, grant.path.read_text(encoding="utf-8"))
            self.assertTrue(grant.authenticate(f"Bearer {token}"))
            self.assertFalse(grant.authenticate("Bearer wrong"))
            self.assertFalse(grant.authenticate(None))
            self.assertEqual(grant.scope()["repository_id"], "repo-1")
            with self.assertRaisesRegex(ValueError, "already exists"):
                grant.issue("repo-1", root / "token-2")
            with self.assertRaisesRegex(ValueError, "already exists"):
                grant.issue("repo-1", token_path, rotate=True)
            token_2_path = root / "token-2"
            self.assertEqual(grant.issue("repo-1", token_2_path, rotate=True), 2)
            self.assertFalse(grant.authenticate(f"Bearer {token}"))
            token_2 = token_2_path.read_text(encoding="utf-8").strip()
            self.assertTrue(grant.authenticate(f"Bearer {token_2}"))
            self.assertEqual(grant.revoke(), 3)
            self.assertFalse(grant.authenticate(f"Bearer {token_2}"))
            with self.assertRaisesRegex(ValueError, "binding is unavailable"):
                grant.scope()

    def test_missing_foreign_and_unsafe_documents_fail_closed(self) -> None:
        with TemporaryDirectory() as temporary:
            root, grant = self._instance(temporary)
            token_path = root / "token"
            with self.assertRaisesRegex(ValueError, "does not exist"):
                grant.issue("repo-1", token_path, rotate=True)
            with self.assertRaisesRegex(ValueError, "does not match"):
                grant.issue("other-repository", token_path)
            grant.issue("repo-1", token_path)
            token = token_path.read_text(encoding="utf-8").strip()
            document = grant.path.read_bytes()
            other = WorkspaceReadGrant(root, "another-instance", grant.path)
            self.assertFalse(other.authenticate(f"Bearer {token}"))
            with self.assertRaisesRegex(ValueError, "binding does not match"):
                other.revoke()
            grant.path.chmod(0o644)
            self.assertFalse(grant.authenticate(f"Bearer {token}"))
            grant.path.chmod(0o600)
            grant.path.unlink()
            grant.path.symlink_to(token_path)
            self.assertFalse(grant.authenticate(f"Bearer {token}"))
            grant.path.unlink()
            grant.path.write_bytes(document)
            grant.path.chmod(0o600)
            grant.path.parent.rename(root / "credentials-real")
            grant.path.parent.symlink_to(root / "credentials-real", target_is_directory=True)
            self.assertFalse(grant.authenticate(f"Bearer {token}"))
            grant.path.parent.unlink()
            (root / "credentials-real").rename(grant.path.parent)
            malformed = json.loads(document)
            malformed["revision"] = True
            grant.path.write_text(json.dumps(malformed), encoding="utf-8")
            self.assertFalse(grant.authenticate(f"Bearer {token}"))

    def test_repository_binding_is_required_and_installed_command_fails_closed(self) -> None:
        with TemporaryDirectory() as temporary:
            root, grant = self._instance(temporary, bind_repository=False)
            token_path = root / "token"
            with self.assertRaisesRegex(ValueError, "repository binding is unavailable"):
                grant.issue("repo-1", token_path)
            self.assertFalse(token_path.exists())
            with patch("builtins.print") as output:
                self.assertEqual(main(["--data-root", str(root), "issue",
                                       "--repository-id", "repo-1", "--token-file", str(token_path)]), 1)
            self.assertEqual(json.loads(output.call_args.args[0])["status"], "ERROR")


if __name__ == "__main__":
    unittest.main()
