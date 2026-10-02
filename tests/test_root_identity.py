from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.root_identity import RootIdentity


class RootIdentityTests(unittest.TestCase):
    def test_existing_root_allows_child_changes_but_rejects_replacement(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            root.mkdir()
            identity = RootIdentity(root)
            (root / "child").write_text("data")
            self.assertFalse(identity.drifted())
            root.rename(Path(temporary) / "parked")
            self.assertTrue(identity.drifted())
            root.mkdir()
            self.assertTrue(identity.drifted())

    def test_symlink_replacement_and_later_creation_are_drift(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "root"
            absent = RootIdentity(root)
            self.assertFalse(absent.drifted())
            root.mkdir()
            self.assertTrue(absent.drifted())
            selected = RootIdentity(root)
            other = Path(temporary) / "other"
            other.mkdir()
            root.rename(Path(temporary) / "parked")
            root.symlink_to(other, target_is_directory=True)
            self.assertTrue(selected.drifted())
            root.unlink()
            root.write_text("not a directory")
            self.assertTrue(selected.drifted())
