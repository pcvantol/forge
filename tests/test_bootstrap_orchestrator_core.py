import json
import tempfile
import unittest
from pathlib import Path

from forge.bootstrap_orchestrator.core import BootstrapOrchestrator, DispatchStore, LifecycleEvent, ProgrammeAuthorization, PullRequestState, WorkerResult, load_dag, merge_ready, plan_worktree, reconcile_pr, reconcile_worker


class BootstrapCoreTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.dag = load_dag(self.root / 'docs/architecture/forge-v1-implementation-dag.json')
        self.contract = json.loads((self.root / 'docs/architecture/forge-v1-bootstrap-scheduler-contract.json').read_text())
        self.main = 'main-sha'
        self.core = BootstrapOrchestrator(self.dag, self.contract, repository_id='forge', main_sha=self.main)

    def authorization(self, **overrides):
        values = dict(authorization_id='auth-1', programme_id='v1', dag_digest=self.dag.digest, approved_main_sha=self.main,
                      approved_node_ids=('F1',), architecture_references=('architecture',), productization_references=('product',),
                      allowed_repositories=('forge',), allowed_write_scopes=('RUNTIME_SERVICE','OPERATIONAL_STORE'),
                      preserved_human_gates=('ARCHITECTURE_DECISION',), preserved_external_gates=(), approved_by='human', approved_at='now')
        values.update(overrides); return ProgrammeAuthorization(**values)

    def test_loader_rejects_opaque_external_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dag.json'; data = json.loads((self.root / 'docs/architecture/forge-v1-implementation-dag.json').read_text())
            data['external_gate_details'][0]['current_state'] = 'EP_READY'; path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'precise'): load_dag(path)

    def test_no_authorization_is_not_dispatchable(self):
        criteria = self.core.evaluate('F1', None, completed=set(), repository_clean=True)
        self.assertFalse(self.core.dispatchable(criteria))
        self.assertFalse(next(item for item in criteria if item.criterion == 'PROGRAMME_AUTHORIZED').result)

    def test_current_authorization_builds_immutable_snapshot_and_prompt(self):
        criteria = self.core.evaluate('F1', self.authorization(), completed=set(), repository_clean=True)
        self.assertTrue(self.core.dispatchable(criteria))
        snapshot = self.core.snapshot(dispatch_id='dispatch-1', node_id='F1', mission_id='mission', intent_id='intent', action_id='action', authorization=self.authorization(), criteria=criteria)
        package = self.core.package(snapshot, objective='bounded work', worktree='/safe/worktree', branch='bootstrap/F1/dispatch-1')
        self.assertEqual(package.prompt(), package.prompt())
        self.assertIn('presentation only', package.prompt())
        self.assertIn('sha256:', snapshot.digest)

    def test_stale_or_out_of_scope_authorization_fails_closed(self):
        stale = self.authorization(approved_main_sha='old')
        criteria = self.core.evaluate('F1', stale, completed=set(), repository_clean=True)
        self.assertFalse(self.core.dispatchable(criteria))
        denied = self.authorization(approved_node_ids=('F2',))
        criteria = self.core.evaluate('F1', denied, completed=set(), repository_clean=True)
        self.assertFalse(next(item for item in criteria if item.criterion == 'NODE_AUTHORIZED').result)

    def test_worktree_plan_and_events_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory) / 'repo'; repository.mkdir(); (repository / '.git').mkdir()
            plan = plan_worktree(dispatch_id='dispatch-1', node_id='F1', repository=repository, base_sha='a' * 40, root=Path(directory) / 'worktrees')
            self.assertEqual(plan.branch, 'bootstrap/F1/dispatch-1')
            event = LifecycleEvent('WORKTREE_PLANNED', 'dispatch-1', 'F1', 'now', 'PLANNED')
            self.assertTrue(event.event_id.startswith('event-'))
        with self.assertRaises(ValueError):
            plan_worktree(dispatch_id='../bad', node_id='F1', repository=Path('.'), base_sha='a' * 40, root=Path('/tmp'))

    def test_store_recovers_snapshot_without_duplicate_side_effect_state(self):
        criteria = self.core.evaluate('F1', self.authorization(), completed=set(), repository_clean=True)
        snapshot = self.core.snapshot(dispatch_id='dispatch-restart', node_id='F1', mission_id='m', intent_id='i', action_id='a', authorization=self.authorization(), criteria=criteria)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.sqlite'; store = DispatchStore(path); store.create(snapshot); store.close()
            store = DispatchStore(path); store.create(snapshot)
            store.transition('dispatch-restart', 'WORKTREE_PLANNED', LifecycleEvent('WORKTREE_PLANNED', 'dispatch-restart', 'F1', 'now', 'WORKTREE_PLANNED'), branch='bootstrap/F1/dispatch-restart', worktree='/tmp/worktree')
            self.assertEqual(store.state('dispatch-restart')['worktree'], '/tmp/worktree')
            self.assertEqual(len(store.events('dispatch-restart')), 1); store.close()

    def test_crash_windows_recover_before_worker_or_pr_retry(self):
        class Worker:
            def recover(self, dispatch): return WorkerResult('run-1', 0, 'out', 'err')
            def invoke_once(self, package): raise AssertionError('must recover')
        class PR:
            def recover(self, dispatch, branch): return PullRequestState('pr-1','head',False,True,True,'APPROVED',0)
            def create_once(self, package): raise AssertionError('must recover')
        criteria = self.core.evaluate('F1', self.authorization(), completed=set(), repository_clean=True)
        snapshot = self.core.snapshot(dispatch_id='dispatch-crash', node_id='F1', mission_id='m', intent_id='i', action_id='a', authorization=self.authorization(), criteria=criteria)
        package = self.core.package(snapshot, objective='x', worktree='/tmp/x', branch='bootstrap/F1/dispatch-crash')
        with tempfile.TemporaryDirectory() as directory:
            store = DispatchStore(Path(directory) / 'state.sqlite'); store.create(snapshot)
            self.assertEqual(reconcile_worker(store, 'dispatch-crash', Worker(), package).invocation_id, 'run-1')
            self.assertEqual(reconcile_pr(store, 'dispatch-crash', PR(), package).pr_id, 'pr-1')
            self.assertTrue(merge_ready(PullRequestState('p','h',False,True,True,'APPROVED',0), local_qualification=True, human_gates_satisfied=True, owner_authorized=True, security_reviewed=True, risk_class='HIGH'))
            self.assertFalse(merge_ready(PullRequestState('p','h',False,True,True,'APPROVED',0), local_qualification=True, human_gates_satisfied=True, owner_authorized=False, security_reviewed=True, risk_class='ELEVATED'))


if __name__ == '__main__': unittest.main()
