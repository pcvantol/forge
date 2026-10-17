"""Deterministic regression for the actual TDE empty crash-boundary PID race."""
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest
from unittest.mock import patch


def driver():
    source = Path(__file__).resolve().parents[1]
    spec = spec_from_file_location('candidate_boundary_probe', source / 'scripts/qualification/qualify_installed_candidate_decisions.py')
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CandidateBoundaryPublicationTests(unittest.TestCase):
    def test_ready_path_is_not_visible_while_pid_write_is_incomplete(self):
        module = driver()
        opened, release = Event(), Event()
        original = Path.open
        failures = []
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            ready = root / 'decision-boundary.ready.private'

            @contextmanager
            def delayed_open(path, mode='r', *args, **kwargs):
                with original(path, mode, *args, **kwargs) as handle:
                    if path.parent == root and ('w' in mode or 'x' in mode):
                        opened.set()
                        if not release.wait(3):
                            raise AssertionError('test writer was not released')
                    yield handle

            def publish():
                try:
                    module._publish_boundary_pid(root)
                except BaseException as error:
                    failures.append(error)

            with patch.object(Path, 'open', delayed_open):
                worker = Thread(target=publish)
                worker.start()
                try:
                    self.assertTrue(opened.wait(3))
                    self.assertFalse(ready.exists(), 'partial PID file is visible to the crash controller')
                finally:
                    release.set()
                    worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(failures, [])
            self.assertEqual(ready.read_text(), str(os.getpid()))
            self.assertEqual(ready.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(root.iterdir()), [ready])

    def test_failed_publication_does_not_advertise_a_boundary(self):
        module = driver()
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(module.os, 'replace', side_effect=OSError('synthetic publication failure')):
                with self.assertRaises(OSError):
                    module._publish_boundary_pid(root)
            self.assertEqual(list(root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
