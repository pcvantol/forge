"""Remove the installed production prefix guard; real claimed-B preview must fail."""
from pathlib import Path
import inspect
import sys
import textwrap
import unittest

SOURCE = Path(__file__).resolve().parents[2]
if '--source-development' in sys.argv:
    sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE / 'tests'))
import forge.workset_order_contract as contract
import forge.workset_order_service as service
import forge.workset_order as order
from test_workset_order_process import WorksetOrderProcessTests

original = contract.permutation
text = textwrap.dedent(inspect.getsource(original))
needle = "    if old[:fixed_prefix] != new[:fixed_prefix]:\n        raise OrderConflict('CLAIMED_PREFIX_CHANGED')\n"
assert text.count(needle) == 1
namespace = {}
exec(compile(text.replace(needle, ''), 'isolated-actual-workset-prefix-guard-removal', 'exec'), original.__globals__, namespace)
contract.permutation = service.permutation = order.permutation = namespace['permutation']
try:
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([WorksetOrderProcessTests(
        'test_real_runtime_b_claim_and_order_confirmation_have_one_fixed_prefix')]))
    raise SystemExit(0 if result.wasSuccessful() else 1)
finally:
    contract.permutation = service.permutation = order.permutation = original
