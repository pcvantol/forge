import json
import tempfile
import unittest
from pathlib import Path

from forge.core import JsonStore
from forge.models import (
    Capability,
    EngineeringMode,
    GovernanceProfile,
    KnowledgeSource,
    Repository,
    RepositoryCatalog,
    RepositoryRole,
    Workspace,
)


class FoundationModelTests(unittest.TestCase):
    def test_repository_is_an_identity_without_catalog_role(self) -> None:
        repository = Repository("forge-repo", "Forge", "git", "example/forge", "/work/forge")
        self.assertEqual(repository.to_dict()["repository"], "example/forge")
        self.assertNotIn("role", repository.to_dict())

    def test_repository_catalog_requires_exactly_one_canonical_repository(self) -> None:
        catalog = RepositoryCatalog(
            "forge-catalog",
            {RepositoryRole.CANONICAL: ("forge-repo",), RepositoryRole.DOCUMENTATION: ("forge-docs",)},
        )
        self.assertEqual(catalog.to_dict()["entries"]["canonical"], ["forge-repo"])
        with self.assertRaises(ValueError):
            RepositoryCatalog("empty-catalog", {RepositoryRole.SUPPORTING: ("supporting-repo",)})
        with self.assertRaises(ValueError):
            RepositoryCatalog("duplicate-catalog", {RepositoryRole.CANONICAL: ("forge-repo",), RepositoryRole.SUPPORTING: ("forge-repo",)})

    def test_knowledge_sources_are_read_only(self) -> None:
        source = KnowledgeSource("platform-kb", "Platform KB", "knowledge_base", "local://platform-kb")
        self.assertTrue(source.to_dict()["read_only"])
        with self.assertRaises(ValueError):
            KnowledgeSource("mutable-source", "Mutable", "service", "local://mutable", read_only=False)

    def test_capabilities_are_declarations_only(self) -> None:
        capability = Capability("workspace-management", "Workspace Management", "Declare workspace contracts.")
        self.assertEqual(capability.to_dict()["status"], "declared")
        with self.assertRaises(ValueError):
            Capability("runtime", "Runtime", "Not in bootstrap.", status="active")

    def test_mode_and_governance_catalogs_preserve_all_declared_values(self) -> None:
        self.assertEqual([mode.value for mode in EngineeringMode], ["prototype", "managed", "production", "enterprise"])
        self.assertEqual([profile.value for profile in GovernanceProfile], ["solo", "two_person", "team", "enterprise"])

    def test_workspace_references_separate_catalog_and_profiles(self) -> None:
        workspace = Workspace(
            "forge-workspace",
            "Forge",
            "forge-catalog",
            EngineeringMode.PROTOTYPE,
            GovernanceProfile.SOLO,
        )
        self.assertEqual(workspace.to_dict()["repository_catalog_id"], "forge-catalog")

    def test_json_store_is_deterministic_and_human_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = JsonStore(Path(temporary_directory) / "foundation.json")
            store.save({"z": "last", "a": "first"})
            self.assertEqual(store.load(), {"a": "first", "z": "last"})
            self.assertEqual(json.loads(store.path.read_text()), {"a": "first", "z": "last"})
            self.assertTrue(store.path.read_text().startswith("{\n  \"a\""))


if __name__ == "__main__":
    unittest.main()
