"""Real A→B package denies missing/order/held/budget/stale scope changes."""
from datetime import UTC,datetime,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,unittest
from test_workset_release_chain import chain
from forge.server_runtime import existing_instance
from forge.workset_release_grant import WorksetReleaseGrant
from forge.workset_release_service import WorksetReleaseService
from forge.approved_worklist import ApprovedWorklistService,candidate_source
from forge.worklist_control import control_runtime
from forge.lifecycle import RecommendationLifecycleStore
from forge.models.criterion_observation import canonical_digest


class ApprovedReleaseSelectionTests(unittest.TestCase):
    def test_real_bound_predecessor_order_and_budget_denials_without_side_effects(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'selection'
            chain.chat_setup(root,'http://127.0.0.1:9','effect-read-only',release=False)
            with patch.object(chain.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=chain.utils.fixture.IDENTITY):
                instance=existing_instance(root/'runtime');grant=WorksetReleaseGrant(root/'runtime',instance.instance_id)
                service=WorksetReleaseService(root/'runtime',grant);token='Bearer '+(root/'release.private').read_text().strip()
                prepared=json.loads((root/'prepared.private.json').read_text());selection=prepared['package']['selection']
                child_only={**selection,'subjects':selection['subjects'][1:],'maximum_activations':1}
                missing=service.prepare(token,child_only)
                self.assertFalse(missing['release_supported']);self.assertEqual(missing['gaps'][0]['code'],'PREDECESSOR_NOT_SELECTED')
                reverse=service.prepare(token,{**selection,'subjects':list(reversed(selection['subjects']))})
                self.assertFalse(reverse['release_supported']);self.assertEqual(reverse['gaps'][0]['code'],'DEPENDENCY_ORDER_CONFLICT')
                body={'contract_version':'forge-approved-workset-release/v1','operation_id':'one-release','intent':'release',
                    'selection':selection,'package_digest':prepared['package_digest'],'confirm':True,'expected_revision':None}
                result=service.execute(token,body)
                self.assertEqual(result['state'],'COMPLETE')
                altered={**selection,'expires_at':(datetime.now(UTC)+timedelta(minutes=30)).isoformat()}
                conflict=service.prepare(token,altered)
                self.assertFalse(conflict['release_supported']);self.assertIn('ANOTHER_WORKSET_ARMED',[g['code'] for g in conflict['gaps']])
                service.execute(token,{**body,'operation_id':'withdraw','intent':'disarm','expected_revision':result['current']['workset_revision']})
                new=service.prepare(token,altered)
                with self.assertRaisesRegex(ValueError,'allowance exhausted'):
                    service.execute(token,{**body,'operation_id':'budget-cannot-reset','selection':altered,'package_digest':new['package_digest']})
                with control_runtime(root/'runtime') as runtime,RecommendationLifecycleStore(candidate_source(root/'runtime')) as store:
                    selected=ApprovedWorklistService(runtime,store)
                    value=selected._get(result['workset_id'])
                    with self.assertRaisesRegex(ValueError,'withdrawn'):
                        selected.control(result['workset_id'],expected_revision=value['revision'],operation='arm')
                    self.assertEqual(runtime.database._connection.execute('SELECT count(*) FROM approved_worksets').fetchone()[0],1)
                    self.assertEqual(runtime.database._connection.execute('SELECT count(*) FROM governance_decisions').fetchone()[0],6)
                    self.assertEqual(runtime.database._connection.execute('SELECT count(*) FROM mission_id_allocations').fetchone()[0],2)
                    # The genuine owner lifecycle rejects a cyclic update to an
                    # allocated subject; do not bypass it by inserting SQL bytes.
                    candidate=store.get_candidate(selection['subjects'][0]['candidate_id'])
                    with self.assertRaisesRegex(ValueError,'immutable'):
                        store.update_candidate(candidate.id,dependencies=(selection['subjects'][1]['candidate_id'],))
                    self.assertEqual(canonical_digest(store.get_candidate(candidate.id).to_dict()),selection['subjects'][0]['subject_revision'])
                stale={**selection,'subjects':[{**selection['subjects'][0],'subject_revision':'sha256:'+'0'*64},selection['subjects'][1]]}
                with self.assertRaises(PermissionError):service.prepare(token,stale)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),3)

    def test_held_partial_workset_cannot_gain_remaining_decision_or_release(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'held'
            # Terminated real command records Business only; recover uses the same
            # existing service after an actual canonical owner hold wins.
            simulator=chain.utils.EpSimulatorState(project_id=chain.utils.PROJECT,repository_id=chain.utils.fixture.SOURCE.repository_id,
                repository_identity=chain.utils.fixture.SOURCE.github_repository,consumer_id=chain.utils.CONSUMER,
                instance_id=chain.utils.INSTANCE,bearer_token=chain.utils.TOKEN,
                scenario=chain.utils.EpSimulatorScenario(name='held-partial',effect_declaration_supported=True))
            import subprocess,time
            with chain.utils.EpSimulatorServer(simulator) as server:
                chain.chat_setup(root,server.base_url,'effect-read-only',release=False)
                process=subprocess.Popen(chain.phase_command(root,'effect-read-only','crash-after-business',server.base_url),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    end=time.monotonic()+20
                    while not (root/'boundary.ready.private').exists() and process.poll() is None and time.monotonic()<end:time.sleep(.02)
                    self.assertTrue((root/'boundary.ready.private').exists());process.kill();process.communicate(timeout=5)
                finally:
                    if process.poll() is None:process.kill();process.communicate(timeout=5)
                with patch.object(chain.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=chain.utils.fixture.IDENTITY):
                    data=chain.utils.fixture._read(root/'release-case.private.json')
                    with control_runtime(root/'runtime') as runtime,RecommendationLifecycleStore(candidate_source(root/'runtime')) as store:
                        service=ApprovedWorklistService(runtime,store);value=service._get(data['workset_id'])
                        held=service.control(data['workset_id'],expected_revision=value['revision'],operation='hold')
                        self.assertTrue(held['held'])
                    instance=existing_instance(root/'runtime');release=WorksetReleaseService(root/'runtime',WorksetReleaseGrant(root/'runtime',instance.instance_id))
                    token='Bearer '+(root/'release.private').read_text().strip();package=json.loads((root/'prepared.private.json').read_text())
                    with self.assertRaisesRegex(ValueError,'held'):
                        release.execute(token,{'contract_version':'forge-approved-workset-release/v1','operation_id':'release-a-b','intent':'release',
                            'selection':package['package']['selection'],'package_digest':package['package_digest'],'confirm':True,'expected_revision':None})
                    current=release.operation(token,'release-a-b')
                    self.assertEqual(current['state'],'PENDING');self.assertIn('WORKSET_HELD',current['current']['items'][0]['blocking_reasons'])
                    self.assertFalse(simulator.submission_ids())

    def test_hold_blocks_pre_admitted_members_without_real_activation_claim(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'pre-admitted-hold'
            simulator=chain.utils.EpSimulatorState(project_id=chain.utils.PROJECT,repository_id=chain.utils.fixture.SOURCE.repository_id,
                repository_identity=chain.utils.fixture.SOURCE.github_repository,consumer_id=chain.utils.CONSUMER,
                instance_id=chain.utils.INSTANCE,bearer_token=chain.utils.TOKEN,
                scenario=chain.utils.EpSimulatorScenario(name='pre-admitted-hold',effect_declaration_supported=True))
            with chain.utils.EpSimulatorServer(simulator) as server:
                chain.chat_setup(root,server.base_url,'effect-read-only',release=True)
                with patch.object(chain.utils.composition.MacOSGeneratedUIDIdentityAdapter,'resolve',return_value=chain.utils.fixture.IDENTITY):
                    data=chain.utils.fixture._read(root/'release-case.private.json')
                    with control_runtime(root/'runtime') as runtime,RecommendationLifecycleStore(candidate_source(root/'runtime')) as store:
                        service=ApprovedWorklistService(runtime,store);value=service._get(data['workset_id'])
                        self.assertFalse(value['claims'])
                        service.control(data['workset_id'],expected_revision=value['revision'],operation='hold')
                result=chain.process_phase(root,'effect-read-only','tick',server.base_url)
                self.assertEqual(result['allocations'],2);self.assertEqual(result['provider_invocations'],0)
                self.assertEqual(result['workset']['consumed_activations'],0)
                self.assertTrue(all(s['status']=='APPROVED_PLANNABLE' for s in result['states']))
                self.assertIn('WORKSET_HELD',result['read']['items'][0]['blocking_reasons'])
                self.assertFalse(simulator.submission_ids())
