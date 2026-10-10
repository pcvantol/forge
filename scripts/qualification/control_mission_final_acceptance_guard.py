"""Remove the actual production effect guard in an isolated qualification process."""
from pathlib import Path
import inspect
import sys
import textwrap
import unittest

SOURCE = Path(__file__).resolve().parents[2]
if '--source-development' in sys.argv:
    sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE / 'tests'))

from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from test_mission_final_acceptance_denials import MissionFinalAcceptanceDenialTests

original = InstalledDynamicMissionRuntime.accept_final_completion
code = textwrap.dedent(inspect.getsource(original))
needle = '            with effect_guard():\n                yield'
assert code.count(needle) == 1
broken = code.replace(needle, '            yield')
namespace = {}
exec(compile(broken, 'isolated-actual-final-acceptance-guard-removal', 'exec'), original.__globals__, namespace)
InstalledDynamicMissionRuntime.accept_final_completion = namespace['accept_final_completion']
try:
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        MissionFinalAcceptanceDenialTests('test_revoke_between_canonical_and_terminal_stops_remaining_mutations_and_alias_keys')]))
    # Success here would mean the linked negative test did not detect the defect.
    raise SystemExit(0 if result.wasSuccessful() else 1)
finally:
    InstalledDynamicMissionRuntime.accept_final_completion = original
