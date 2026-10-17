"""Closed diagnostics never turn a duplicate-effect observation into acceptance."""
import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('r58_concurrency_qualifier',Path(__file__).parents[1]/'scripts/qualification/qualify_installed_http_successor.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ConcurrentDiagnosticsTests(unittest.TestCase):
    def test_late_transition_is_observed_without_changing_acceptance(self):
        value=module._concurrent_observation([{'result':'REJECTED','type':'MissionStateStoreError','reason':'mission state transition WAITING_FOR_EXECUTION -> CREATED is not permitted'},{'result':'STARTED'}],1,1)
        self.assertEqual(value['outcomes'][0]['reason_code'],'TRANSITION_WAITING_FOR_EXECUTION_TO_CREATED_DENIED')
        self.assertEqual((value['submission_count'],value['planner_invocation_count']),(1,1))

    def test_unknown_exception_text_and_identifiers_are_never_published(self):
        value=module._concurrent_observation([{'result':'private-token','type':'/private/secret-path','reason':'Bearer private-token','actor':'private-actor'}],2,3)
        raw=json.dumps(value)
        for secret in ('private-token','secret-path','Bearer','private-actor'):self.assertNotIn(secret,raw)
        self.assertEqual(value['outcomes'][0],{'result':'UNKNOWN','type':'OTHER','reason_code':'UNCLASSIFIED'})

    def test_busy_and_duplicate_effect_counts_remain_exact_observations(self):
        value=module._concurrent_observation([{'result':'REJECTED','type':'RuntimeServiceBusy','reason':'canonical runtime is busy'}],2,2)
        self.assertEqual(value['outcomes'][0]['reason_code'],'RUNTIME_BUSY')
        self.assertEqual((value['submission_count'],value['planner_invocation_count']),(2,2))
