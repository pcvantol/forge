"""Exercise the synthetic qualification against the current governed runtime."""
import tempfile
import unittest
from pathlib import Path

from forge.qualification import criterion_completion as qualification


class CriterionReleaseQualificationTests(unittest.TestCase):
    def test_governed_completion_and_negative_cases_survive_reopen(self):
        expected = {
            'partial': 'COMPLETED', 'single': 'COMPLETED', 'misleading': 'COMPLETED',
            'invalid': 'BLOCKED', 'missing': 'BLOCKED', 'no-progress': 'BLOCKED',
            'limit': 'BLOCKED', 'regression': 'BLOCKED',
        }
        with tempfile.TemporaryDirectory() as directory:
            for scenario, outcome in expected.items():
                with self.subTest(scenario=scenario):
                    root = Path(directory) / scenario
                    root.mkdir()
                    phases = ['prepare', 'after-a']
                    if scenario in {'partial', 'misleading', 'regression'}:
                        phases += ['replay-a', 'after-b']
                    phases += ['readback']
                    for phase in phases:
                        qualification._phase(root, scenario, phase)
                    summary = qualification._summary(root, scenario)
                    self.assertEqual(summary['status'], outcome)
                    self.assertEqual(summary['actions'], summary['submissions'])
