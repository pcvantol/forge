"""Offline planning guards; these are not native/runtime qualification."""
from collections import Counter
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'docs/roadmap/four-lane-development-v1.json'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


class FourLanePlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = read_json(PLAN)
        cls.legacy = read_json(ROOT / cls.plan['family_allocation']['inherit_file'])
        cls.inventory = read_json(ROOT / cls.plan['historical_inventory'])

    def test_four_disjoint_product_owners(self):
        self.assertEqual(self.plan['default_repository_holders'], {
            'forge-platform': 'LANE_1', 'engineering-platform': 'LANE_2',
            'forge': 'LANE_3', 'workspace': 'LANE_4'})
        self.assertEqual(self.plan['max_concurrent_repository_writers'], 4)
        self.assertEqual(self.plan['max_mutating_assignments_per_repository'], 1)
        self.assertEqual(self.plan['max_active_assignments_per_lane'], 1)

    def test_four_distinct_live_registers(self):
        registers = self.plan['lane_registers']
        self.assertEqual(set(registers), {'LANE_1','LANE_2','LANE_3','LANE_4'})
        self.assertEqual(len(set(registers.values())), 4)
        self.assertTrue(registers['LANE_1'].endswith('/141'))
        self.assertTrue(registers['LANE_2'].endswith('/142'))

    def test_lossless_historical_allocation(self):
        families = self.legacy['families']
        owners = self.plan['default_repository_holders']
        self.assertEqual(len(families), 34)
        nodes = [n for family in families for n in family['nodes']]
        self.assertEqual(len(nodes), 158)
        self.assertEqual(len(set(nodes)), 158)
        self.assertEqual(Counter(owners[f['repository']] for f in families),
                         {'LANE_1':4,'LANE_2':9,'LANE_3':12,'LANE_4':9})
        by_lane = Counter()
        for family in families:
            by_lane[owners[family['repository']]] += len(family['nodes'])
        self.assertEqual(by_lane, {'LANE_1':16,'LANE_2':40,'LANE_3':66,'LANE_4':36})
        shared = {n['id'] for n in self.legacy['shared_nodes']}
        self.assertEqual(shared, {'GP-DC','GP-Q','GP-X','POL-B','POL-Q','VR-Q','HY-Q'})
        self.assertFalse(set(nodes) & shared)
        self.assertEqual(len(nodes) + len(shared), 165)

    def test_priority_overrides_do_not_invent_families(self):
        known = {(f['repository'], f['family']) for f in self.legacy['families']}
        for value in self.plan['family_allocation']['rank_overrides']:
            self.assertIn((value['repository'], value['family']), known)
            self.assertGreaterEqual(value['rank'], 0)
        self.assertFalse(self.plan['graph_resolution']['rank_is_hard_edge'])

    def test_all_inventory_source_owners_resolve(self):
        aliases = self.plan['graph_resolution']['repository_aliases']
        sources = self.inventory['sources']
        self.assertEqual(len(sources), 31)
        for source in sources.values():
            repo = aliases.get(source['repository'], source['repository'])
            self.assertIn(repo.rsplit('/',1)[1], self.plan['default_repository_holders'])
            self.assertTrue(source['path'])
        self.assertFalse(self.plan['graph_resolution']['product_dependency_edges_changed'])
        self.assertTrue(self.plan['graph_resolution']['include_all_current_nodes_from_owning_sources'])
        self.assertTrue(self.plan['graph_resolution']['historical_rollups_do_not_hide_subnodes'])

    def test_running_work_is_not_reissued(self):
        keep = self.plan['migration']['preserve_assignments']
        self.assertEqual(keep['LANE_1'], 'L1-FORGE-PLATFORM-MANAGED-INSTALLER-V1-20260923')
        self.assertEqual(keep['LANE_2'], 'L2-FORGE-KEYCHAIN-CONSUMER-CONFORMANCE-V1-20261001')
        self.assertTrue(self.plan['migration']['waiting_is_not_idle'])
        self.assertFalse(self.plan['migration']['active_host_holds_transfer'])
        self.assertTrue(self.plan['migration']['no_automatic_second_assignment'])

    def test_dependency_example_is_acyclic_and_only_known_nodes(self):
        known = {f"{f['repository']}:{n}" for f in self.legacy['families'] for n in f['nodes']}
        graph = {}
        for predecessor, successor in self.plan['illustrative_dependency_edges']:
            self.assertIn(predecessor, known)
            self.assertIn(successor, known)
            graph.setdefault(predecessor, set()).add(successor)
        active, complete = set(), set()

        def visit(node):
            self.assertNotIn(node, active, 'cycle in illustrative dependency subset')
            if node in complete:
                return
            active.add(node)
            for successor in graph.get(node, ()):
                visit(successor)
            active.remove(node)
            complete.add(node)

        for node in graph:
            visit(node)

    def test_workspace_does_not_gate_current_installer(self):
        join = next(j for j in self.plan['cross_lane_joins'] if j['id']=='WORKSPACE_DISTRIBUTION')
        self.assertFalse(join['blocks_current_installer'])
        first = next(w for w in self.plan['initial_work'] if w['lane']=='LANE_4')
        self.assertFalse(first['full_parent_completion_claimed'])
        self.assertEqual(first['assignment'], 'L4-WORKSPACE-SERVER-READONLY-V1-20261001')
        self.assertNotIn('WH-Q', first['source_nodes'])
        self.assertNotIn('WPK-PUBLISH', first['source_nodes'])

    def test_no_credential_qualification_release_cycle(self):
        join = next(j for j in self.plan['cross_lane_joins'] if j['id']=='EXISTING_R30')
        self.assertFalse(join['hold_until_full_installer_release'])
        self.assertEqual(join['epoch'], 1)

    def test_shared_resources_are_not_four_host_mutators(self):
        resources = self.plan['resources']
        self.assertEqual(resources['privileged_host_mutation_slots_per_host'], 1)
        self.assertEqual(resources['signer_slots_per_identity'], 1)
        self.assertFalse(resources['worktrees_are_host_isolation'])
        self.assertFalse(resources['resource_tuning_changes_privileges'])

    def test_no_runtime_authority_or_fake_measurement(self):
        for field in ['executable','execution_authority','automatic_dispatch','runtime_scheduler_implemented']:
            self.assertFalse(self.plan[field])
        self.assertFalse(self.plan['selection_policy']['confidence_or_deadline_from_pr_counts'])
        self.assertFalse(self.plan['acceptance_and_reporting']['lane_count_is_speedup'])
        self.assertFalse(self.plan['invariants']['work_sessions_started_by_plan'])
        self.assertEqual(self.plan['invariants']['coverage_operator'], '>')
        self.assertEqual(self.plan['invariants']['strict_changed_production_line_coverage_percent'],80.2)

    def test_entry_documents_exist(self):
        for field in ['protocol','delivery_contract']:
            self.assertTrue((ROOT/self.plan[field]).is_file())
        for n in [3,4]:
            self.assertTrue((ROOT/f'docs/roadmap/lanes/LANE_{n}.md').is_file())


if __name__ == '__main__':
    unittest.main()
