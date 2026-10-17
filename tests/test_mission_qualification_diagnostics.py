"""Bounded qualification failure evidence keeps the original acceptance result."""
from importlib.util import module_from_spec, spec_from_file_location
from io import StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch


def driver():
    path = Path(__file__).resolve().parents[1] / 'scripts/qualification/qualify_installed_mission_concepts.py'
    spec = spec_from_file_location('mission_qualification_diagnostics', path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MissionQualificationDiagnosticTests(unittest.TestCase):
    def test_subtest_diagnostics_exclude_raw_messages_paths_and_parameters(self):
        module = driver()

        class Failure(unittest.TestCase):
            def runTest(self):
                with self.subTest(stage='crash-after-intake', secret='private-value'):
                    raise ValueError('/private/secret-token private-value')

        result = unittest.TextTestRunner(stream=StringIO(), resultclass=module.DiagnosticTestResult).run(Failure())
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.errors), 1)
        facts = result.failure_diagnostics[0]
        self.assertEqual(facts['error'], 'ValueError')
        self.assertEqual(facts['stage'], 'crash-after-intake')
        encoded = json.dumps(facts)
        for private in ['secret-token', 'private-value', '/private/']:
            self.assertNotIn(private, encoded)

    def test_secondary_diagnostic_failure_cannot_replace_original_error(self):
        module = driver()

        class Failure(unittest.TestCase):
            def runTest(self):
                raise ValueError('original-test-error')

        with patch.object(module, '_failure_facts', side_effect=OSError('diagnostic fault')):
            result = unittest.TextTestRunner(stream=StringIO(), resultclass=module.DiagnosticTestResult).run(Failure())
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(len(result.errors), 1)
        self.assertIn('original-test-error', result.errors[0][1])
        self.assertEqual(result.failure_diagnostics[0]['error'], 'DIAGNOSTIC_UNAVAILABLE')

    def test_test_failure_survives_secondary_log_write_failure(self):
        module = driver()
        for error in [OSError('log fault'), ValueError('closed log stream'),
                      UnicodeEncodeError('utf-8', chr(0xd800), 0, 1, 'secondary encoding fault')]:
            with self.subTest(error_type=type(error).__name__):
                with patch.object(Path, 'write_text', side_effect=error):
                    self.assertFalse(module._retain_test_log(Path('unused'), StringIO('original failure'), True))

    def test_log_failure_still_blocks_an_otherwise_successful_gate(self):
        module = driver()
        for error in [OSError('log fault'), ValueError('closed log stream'),
                      UnicodeEncodeError('utf-8', chr(0xd800), 0, 1, 'secondary encoding fault')]:
            with self.subTest(error_type=type(error).__name__):
                with patch.object(Path, 'write_text', side_effect=error):
                    with self.assertRaises(type(error)):
                        module._retain_test_log(Path('unused'), StringIO('test success'), False)


if __name__ == '__main__':
    unittest.main()
