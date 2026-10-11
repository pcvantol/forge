"""Producer byte vectors preserve the existing ASCII and UTF8 contract split."""
import json
import unittest
from forge.advisory_contract import digest
from forge.governance_authority import _digest as governance_digest
from forge.models.criterion_observation import canonical_digest


class WorksetOrderVectorTests(unittest.TestCase):
    def test_numeric_looking_candidate_keys_and_insertion_order_keep_exact_existing_bytes(self):
        keys = ['candidate-2', 'candidate-10', 'candidate-02', 'candidate-a', 'candidate-A',
                'candidate-1', 'candidate-1a', 'candidate-1A']
        value = {'concept_dependency_graph': {key: [] for key in keys}}
        expected = ('{"concept_dependency_graph":{"candidate-02":[],"candidate-1":[],"candidate-10":[],"candidate-1A":[],'
                    '"candidate-1a":[],"candidate-2":[],"candidate-A":[],"candidate-a":[]}}')
        self.assertEqual(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode(), expected.encode())
        self.assertEqual(len(expected.encode()), 170)
        for function in (digest, governance_digest, canonical_digest):
            self.assertEqual(function(value), 'sha256:26634c17166e00ecc46a5b9fd1a2cbd77209c3914cbf86950400e28e5accdc90')
            self.assertEqual(function(value), function({'concept_dependency_graph': {key: [] for key in reversed(keys)}}))
            self.assertNotEqual(function(['A', 'C', 'B']), function(['A', 'B', 'C']))

    def test_unicode_escape_nested_values_and_types_preserve_each_owning_digest(self):
        value = {'z': [True, False, None, 0, 2, 10, -1, {'b': 'caf\u00e9/\U0001f600',
                 'a': 'e\u0301\n\t\r\b\f\\"\u007f\u2028\u2029'}],
                 'a': {'candidate-2': None, 'candidate-10': True}}
        self.assertEqual(digest(value), 'sha256:2330a1b24137b9a2d0b2bd08e30f82314231f16658180fbda47bd50f5d74b7f3')
        self.assertEqual(governance_digest(value), digest(value))
        self.assertEqual(canonical_digest(value), 'sha256:eb28eb361d8e61272fe301947dd94e1283aa8f444a37a3628ffabbd40451d893')
        self.assertEqual(len(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()), 155)
        self.assertEqual(len(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()), 128)
        for function in (digest, governance_digest, canonical_digest):
            self.assertNotEqual(function({'v': True}), function({'v': 1}))
            self.assertNotEqual(function({'v': False}), function({'v': 0}))
            self.assertNotEqual(function({'v': '\u00e9'}), function({'v': 'e\u0301'}))
