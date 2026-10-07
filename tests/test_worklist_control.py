from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec=spec_from_file_location('control_qualification',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_installed_worklist_control.py')
qual=module_from_spec(spec);spec.loader.exec_module(qual)

class WorklistControlTests(unittest.TestCase):
    def test_real_scoped_http_hold_unhold_serial_and_receipt_replay(self):
        with TemporaryDirectory() as tmp:
            outcomes=qual.source_flow(Path(tmp)/'control')
            self.assertEqual(outcomes[-1]['allocations'],2)

    def test_positive_gate_detects_real_revocation(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(AssertionError,'positive control grant replay gate failed'):
                qual.source_flow(Path(tmp)/'control',failure_control=True)

    def test_current_auth_scope_malformed_owner_hold_provenance_cli_and_zero_effects(self):
        with TemporaryDirectory() as tmp:
            outcomes=qual.source_denials(Path(tmp)/'denials')
            self.assertEqual(outcomes[-1]['case'],'current-operator-revoked')
