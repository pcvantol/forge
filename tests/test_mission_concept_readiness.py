"""Existing exact workset release reaches logical activation readiness, no start."""
from contextlib import closing
from datetime import UTC,datetime,timedelta
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from jsonschema import Draft202012Validator
from forge.advisory_context import AdvisoryContext
from forge.advisory_grant import AdvisoryGrant
from forge.approved_worklist import ApprovedWorklistService,CONTRACT
from forge.lifecycle import RecommendationLifecycleStore
from forge.repository_truth import RepositoryTruthEvidence,RepositoryTruthSnapshot
from forge.server_runtime import existing_instance
from forge.worklist_control import control_runtime

spec=spec_from_file_location('mission_readiness_recovery',Path(__file__).resolve().parents[1]/'scripts/qualification/qualify_mission_concept_recovery.py')
driver=module_from_spec(spec);spec.loader.exec_module(driver)


class MissionConceptReadinessTests(unittest.TestCase):
    def test_actual_explicit_workset_release_and_hold_before_activation_without_start(self):
        ready,_=driver.cases();q=ready.qual
        validator=Draft202012Validator(json.loads((Path(__file__).resolve().parents[1]/'forge/api/mission-concepts-v1.json').read_text()))
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'ready';body=driver.prepare_case(root,'approval')
            with q.http(root) as port:
                token=root/'owner.private';base='/v1/mission-concepts/recovery-chat'
                status,approved=ready.call(port,token,'POST',base+'/approve',body)
                self.assertEqual(status,200,approved)
                _,operation=ready.call(port,token,'GET',base+'/operations/approve-recovery')
                package=operation['frozen_package'];before=driver.counts(root)
                instance=existing_instance(root/'runtime')
                principal=AdvisoryGrant(root/'runtime',instance.instance_id).authorize('Bearer '+token.read_text().strip())
                source=AdvisoryContext(root/'runtime',instance.instance_id).available(principal)[0]
                self.assertEqual(package['mission_preview']['repository_evidence_source'],
                    {'repository_id':principal.repository_id,'github_repository':source['repository']})
                # Observe the genuine owner-published immutable repository snapshot.
                # Its GitHub bytes are the declared external transport fixture;
                # no successful runtime state or governance result is inserted.
                truth=RepositoryTruthSnapshot('published-context-'+source['source_id'],principal.repository_id,
                    source['revision'],datetime.now(UTC).isoformat(),
                    (RepositoryTruthEvidence(source['source_id'],'repository_document',source['revision'],
                        'https://github.com/'+source['repository']+'/blob/'+source['revision']+'/'+source['path'],
                        source['content_digest']),))
                member={'candidate_id':approved['candidate_id'],'subject_revision':package['subject_revision'],
                    'mission':package['mission_preview'],'planning':package['planning'],'dependencies':[],
                    'truth':truth.to_dict(),'progression_policy':{'profile_id':'solo','profile_revision':'1',
                        'policy_revision':'1','mode':'continuous','required_decision_role':'platform_architect',
                        'higher_scope_obligations':package['planning']['human_gates']}}
                with control_runtime(root/'runtime') as runtime, RecommendationLifecycleStore(root/'runtime'/'governance'/'candidates.sqlite') as store:
                    service=ApprovedWorklistService(runtime,store)
                    value=service.propose({'contract_version':CONTRACT,'workset_id':'exact-one-approved-subject',
                        'profile_id':'solo','expires_at':(datetime.now(UTC)+timedelta(hours=1)).isoformat(),
                        'maximum_activations':1,'members':[member]})
                    for role in ('business','architecture'):
                        value=service.decide('exact-one-approved-subject',expected_revision=value['revision'],
                                             role=role,actor='primary_operator')
                    value=service.control('exact-one-approved-subject',expected_revision=value['revision'],operation='arm')
                    status,current=ready.call(port,token,'GET',base+'/operations/approve-recovery')
                    self.assertEqual(status,200,current);validator.validate(current)
                    facts=current['current_readiness']
                    self.assertEqual(facts['state'],'READY_FOR_GOVERNED_ACTIVATION',facts)
                    self.assertEqual(facts['blockers'],[])
                    self.assertTrue(facts['workset_facts'][0]['eligible'])
                    self.assertTrue(facts['workset_facts'][0]['selected_next'])
                    self.assertEqual(facts['execution_resources'],'NOT_OBSERVED')
                    self.assertFalse(facts['execution_ready']);self.assertFalse(current['execution_started'])
                    status,catalog=ready.call(port,token,'GET','/v1/mission-concepts/catalog')
                    self.assertEqual(status,200,catalog);validator.validate(catalog)
                    self.assertEqual(catalog['items'][0]['state'],facts['state'])
                    self.assertEqual(catalog['items'][0]['blockers'],[])
                    value=service.control('exact-one-approved-subject',expected_revision=value['revision'],operation='hold')
                    _,held=ready.call(port,token,'GET',base+'/operations/approve-recovery')
                    self.assertEqual(held['current_readiness']['state'],'APPROVED_WAITING')
                    self.assertIn('WORKSET_HELD',held['current_readiness']['blockers'])
                    admitted=runtime.states.get(approved['mission_id'])
                    self.assertEqual(admitted.actions,());self.assertEqual(admitted.intents,())
                    active=runtime.database._connection.execute('SELECT active_mission_id FROM dispatcher_state WHERE singleton=1').fetchone()
                    self.assertTrue(active is None or active[0] is None)
                self.assertEqual(driver.counts(root),{**before,'governance_decisions':before['governance_decisions']+2})
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
