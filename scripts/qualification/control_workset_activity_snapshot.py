"""Remove the actual snapshot guard only in this owned isolated defect process."""
from pathlib import Path
import inspect
import sys
import textwrap
import unittest

SOURCE = Path(__file__).resolve().parents[2]
if '--source-development' in sys.argv:
    sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE / 'tests'))


def main():
    import forge.workset_activity_service as product
    from test_workset_activity_edges import ActivityEdgesTests
    original = product.WorksetActivityService.read
    source = textwrap.dedent(inspect.getsource(original))
    guard = 'if context != final_context or stamp != final_stamp:'
    if guard not in source:
        raise ValueError('actual production snapshot guard absent')
    scope = dict(vars(product)); exec(compile(source.replace(guard, 'if False:'), '<owned-activity-snapshot-defect>', 'exec'), scope)
    try:
        product.WorksetActivityService.read = scope['read']
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
            ActivityEdgesTests('test_mid_read_real_order_effect_forces_resync')]))
        return 0 if result.wasSuccessful() else 1
    finally:
        product.WorksetActivityService.read = original


if __name__ == '__main__':
    raise SystemExit(main())
