"""Distinguishing evidence-sink faults, preserving original HTTP outcome."""
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('proposal_http_qualifier',Path('scripts/qualification/qualify_installed_project_proposal_http.py'))
qualifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(qualifier)
class ProposalRetentionTests(unittest.TestCase):
    def test_secondary_receipt_failure_preserves_primary_and_private_fallback(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);primary=TimeoutError('original HTTP timeout');receipt={'result':'FAIL','failure':{'category':'TimeoutError'}}
            with patch.object(Path,'write_text',side_effect=OSError('sink unavailable')):
                qualifier.retain_receipt(root,receipt,primary)
            self.assertFalse(receipt['diagnostic_complete']);self.assertTrue((root/'installed-project-proposal-http.retention-failure.private.json').is_file())
            self.assertIsInstance(primary,TimeoutError);self.assertIn('incomplete',primary.__notes__[0])
    def test_both_sinks_failure_remains_original_with_explicit_diagnostic(self):
        primary=RuntimeError('original nonzero');receipt={'result':'FAIL'};err=io.StringIO()
        with patch.object(Path,'write_text',side_effect=OSError()),patch.object(qualifier.CAPTURE,'retain',side_effect=OSError()),patch('sys.stderr',err):
            qualifier.retain_receipt(Path('/synthetic'),receipt,primary)
        self.assertIn('RuntimeError',err.getvalue());self.assertFalse(receipt['diagnostic_complete'])
    def test_success_sink_failure_cannot_remain_green(self):
        with patch.object(Path,'write_text',side_effect=OSError()),patch.object(qualifier.CAPTURE,'retain'):
            with self.assertRaises(OSError):qualifier.retain_receipt(Path('/synthetic'),{'result':'PASS'},None)
