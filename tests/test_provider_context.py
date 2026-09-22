from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.provider_context import ProviderExecutionContextError, ProviderExecutionContextService
from forge.runtime import RuntimeBootstrap


class ProviderExecutionContextTests(unittest.TestCase):
    def _root(self, temporary: str, name: str) -> Path:
        root = Path(temporary) / name
        database = RuntimeBootstrap(data_root=root, forge_version="test").open()
        database.close()
        return root

    def test_context_is_instance_bound_guarded_and_secret_free(self) -> None:
        with TemporaryDirectory() as temporary:
            root = self._root(temporary, "one")
            service = ProviderExecutionContextService(root)
            first = service.configure(
                provider_id="codex-chatgpt-session",
                provider_type="CODEX_CLI_CHATGPT_SESSION",
                executable_path="/opt/forge/codex/bin/codex",
                provider_home="/var/lib/forge/one/provider-home",
                provider_config_home="/var/lib/forge/one/codex-home",
                profile="forge-one",
            )
            self.assertEqual(first.configuration_revision, 1)
            self.assertEqual(first.instance_id, (root / "instance" / "runtime-instance.json").read_text().strip())
            rendered = json.dumps(first.to_safe_dict(), sort_keys=True)
            self.assertNotIn("token", rendered.lower())
            self.assertNotIn("secret", rendered.lower())

            with self.assertRaisesRegex(ProviderExecutionContextError, "current digest"):
                service.configure(
                    provider_id=first.provider_id, provider_type=first.provider_type,
                    executable_path=first.executable_path, provider_home=first.provider_home,
                    provider_config_home=first.provider_config_home, profile=first.profile,
                )
            second = service.configure(
                provider_id=first.provider_id, provider_type=first.provider_type,
                executable_path=first.executable_path,
                provider_home="/var/lib/forge/one/provider-home-v2",
                provider_config_home="/var/lib/forge/one/codex-home-v2",
                profile=first.profile, expected_digest=first.configuration_digest,
            )
            self.assertEqual(second.configuration_revision, 2)
            self.assertNotEqual(second.configuration_digest, first.configuration_digest)

    def test_context_cannot_cross_instance_boundary(self) -> None:
        with TemporaryDirectory() as temporary:
            first_root = self._root(temporary, "one")
            second_root = self._root(temporary, "two")
            first = ProviderExecutionContextService(first_root)
            first.configure(
                provider_id="codex-chatgpt-session",
                provider_type="CODEX_CLI_CHATGPT_SESSION",
                executable_path="/opt/forge/one/codex",
                provider_home="/var/lib/forge/one/home",
                provider_config_home="/var/lib/forge/one/config",
            )
            destination = second_root / "instance" / "provider-contexts"
            destination.mkdir(parents=True)
            (destination / "codex-chatgpt-session.json").write_bytes(
                (first_root / "instance" / "provider-contexts" / "codex-chatgpt-session.json").read_bytes()
            )
            with self.assertRaisesRegex(ProviderExecutionContextError, "does not belong"):
                ProviderExecutionContextService(second_root).read("codex-chatgpt-session")

    def test_missing_instance_or_relative_paths_fail_closed(self) -> None:
        with TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing"
            missing.mkdir()
            with self.assertRaises(ProviderExecutionContextError):
                ProviderExecutionContextService(missing).configure(
                    provider_id="codex-chatgpt-session",
                    provider_type="CODEX_CLI_CHATGPT_SESSION",
                    executable_path="codex",
                    provider_home="/tmp/home",
                    provider_config_home="/tmp/config",
                )
            root = self._root(temporary, "valid")
            with self.assertRaisesRegex(ProviderExecutionContextError, "absolute"):
                ProviderExecutionContextService(root).configure(
                    provider_id="codex-chatgpt-session",
                    provider_type="CODEX_CLI_CHATGPT_SESSION",
                    executable_path="codex",
                    provider_home="/tmp/home",
                    provider_config_home="/tmp/config",
                )


if __name__ == "__main__":
    unittest.main()
