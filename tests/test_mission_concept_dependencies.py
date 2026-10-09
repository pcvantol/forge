"""Two actual governed subjects, directed reasoned edges and context stability."""
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json,unittest
from jsonschema import Draft202012Validator
from test_advisory_http import qual
from test_mission_concept_ready_http import configure,call,model_output
from test_mission_concept_planning import profiles
import test_mission_concept_contract as content
from forge.mission_concept_contract import CONTRACT
from forge.mission_concept_setup import MissionConceptSetup
from forge.server_runtime import existing_instance


class MissionConceptDependencyTests(unittest.TestCase):
    def test_real_parent_child_subjects_scoped_context_and_approved_definition_edges(self):
        schema=json.loads((Path(__file__).resolve().parents[1]/'forge/api/mission-concepts-v1.json').read_text())
        validator=Draft202012Validator(schema)
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'dependencies';grant=configure(root)
            with qual.http(root) as port:
                instance=existing_instance(root/'runtime')
                principal=sha256(qual.utils.fixture.IDENTITY.generated_uid.encode()).hexdigest()[:16]
                token=root/'owner.private'
                issued=grant.issue(principal_id=principal,project_id=qual.utils.PROJECT,
                    repository_id=qual.utils.fixture.SOURCE.repository_id,
                    conversation_ids=['foundation','portal'],maximum_turns=8,
                    expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),token_path=token)
                MissionConceptSetup(root/'runtime',instance.instance_id).configure(
                    grant_id=issued['grant_id'],profiles=profiles(),maximum_missions=2)
                def create(conversation,definition):
                    model_output(root,definition)
                    status,current=call(port,token,'GET','/v1/mission-concepts/'+conversation+'/context')
                    self.assertEqual(status,200,current);validator.validate(current)
                    request={k:current['context'][k] for k in ('instance_id','project_id','repository_id')}
                    request.update(contract_version=CONTRACT,conversation_id=conversation,turn_id='initial',
                        expected_revision=0,context_revision=current['context_revision'],selected_sources=[],
                        advisor_kind='ARCHITECTURE',objective=definition['objective'])
                    status,generated=call(port,token,'POST','/v1/mission-concepts/'+conversation+'/turns',request)
                    self.assertEqual(status,200,generated)
                    status,prepared=call(port,token,'GET','/v1/mission-concepts/'+conversation+'/package')
                    self.assertEqual(status,200,prepared);validator.validate(prepared)
                    return prepared
                def approve(conversation,prepared):
                    body={'contract_version':CONTRACT,'operation_id':'approve-'+conversation,'revision':1,
                          'package_digest':prepared['package_digest'],'confirm':True}
                    status,result=call(port,token,'POST','/v1/mission-concepts/'+conversation+'/approve',body)
                    self.assertEqual(status,200,result);validator.validate(result)
                    return result
                foundation={**content.MissionConceptContractTests().output()['definition'],
                            'title':'Account foundation','objective':'Build isolated account access for the client portal.'}
                parent_package=create('foundation',foundation);parent=approve('foundation',parent_package)
                reason='The portal requires the independently governed account isolation foundation.'
                child_definition={**content.MissionConceptContractTests().output()['definition'],
                    'dependencies':[parent['candidate_id']],'dependency_reasons':{parent['candidate_id']:reason}}
                child_package=create('portal',child_definition)
                binding=child_package['package']['dependency_bindings'][0]
                self.assertEqual(binding['subject_revision'],parent['intake_subject_revision'])
                self.assertEqual(binding['reason'],reason)
                child=approve('portal',child_package)
                self.assertIn('DEPENDENCY_NOT_PROVEN',child['current']['blockers'])
                self.assertFalse(child['current']['dependency_facts'][0]['proven'])
                self.assertFalse(child['current']['execution_ready'])
                self.assertEqual(child['current']['execution_resources'],'NOT_OBSERVED')
                self.assertNotEqual(parent['mission_id'],child['mission_id'])
                _,parent_operation=call(port,token,'GET','/v1/mission-concepts/foundation/operations/approve-foundation')
                self.assertTrue(parent_operation['source_fresh'])
                self.assertEqual(parent_operation['frozen_package'],parent_package['package'])
                status,catalog=call(port,token,'GET','/v1/mission-concepts/catalog')
                self.assertEqual(status,200,catalog);validator.validate(catalog)
                self.assertEqual(len(catalog['items']),2)
                item=next(i for i in catalog['items'] if i['candidate_id']==child['candidate_id'])
                edge=item['edges'][0]
                self.assertEqual(edge['state'],'APPROVED_DEFINITION')
                self.assertEqual(edge['kind'],'REQUIRES');self.assertEqual(edge['reason'],reason)
                self.assertEqual(edge['target_object_id'],item['object_id'])
                self.assertEqual(edge['source_object_id'],parent_package['object_id'])
                self.assertEqual(call(port,root/'bob.private','GET','/v1/mission-concepts/portal/context')[0],403)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),2)
                from forge.worklist_control import control_runtime
                from forge.lifecycle import RecommendationLifecycleStore
                from forge.approved_worklist import ApprovedWorklistService,CONTRACT as WORKLIST
                from forge.mission_concept_readiness import current_readiness
                from forge.advisory_grant import AdvisoryGrant
                with control_runtime(root/'runtime') as runtime, RecommendationLifecycleStore(root/'runtime'/'governance'/'candidates.sqlite') as store:
                    service=ApprovedWorklistService(runtime,store)
                    members=[]
                    for package in (parent_package['package'],child_package['package']):
                        members.append({'candidate_id':package['candidate']['id'],
                            'subject_revision':package['subject_revision'],'mission':package['mission_preview'],
                            'planning':package['planning'],'dependencies':package['candidate']['dependencies'],
                            'truth':{},'progression_policy':{}})
                    # Deliberately absent activation inputs: genuine approved subjects
                    # never become READY from an invalid release/activation document.
                    definition={'contract_version':WORKLIST,'workset_id':'exact-two-subjects','profile_id':'solo',
                        'expires_at':(datetime.now(UTC)+timedelta(hours=1)).isoformat(),
                        'maximum_activations':2,'members':members}
                    workset=service.propose(definition)
                    for role in ('business','architecture'):
                        workset=service.decide('exact-two-subjects',expected_revision=workset['revision'],role=role,actor='primary_operator')
                    principal_scope=AdvisoryGrant(root/'runtime',instance.instance_id).authorize('Bearer '+token.read_text().strip())
                    readiness=current_readiness(runtime,store,child_package['package'],runtime.states.get(child['mission_id']),principal_scope)
                    self.assertIn('NOT_RELEASED',readiness['blockers'])
                    self.assertIn('ACTIVATION_INPUTS_UNAVAILABLE',readiness['blockers'])
                    workset=service.control('exact-two-subjects',expected_revision=workset['revision'],operation='hold')
                    held=current_readiness(runtime,store,parent_package['package'],runtime.states.get(parent['mission_id']),principal_scope)
                    self.assertIn('WORKSET_HELD',held['blockers'])
                    self.assertFalse(held['execution_ready'])

                status,held_catalog=call(port,token,'GET','/v1/mission-concepts/catalog')
                self.assertEqual(status,200,held_catalog);validator.validate(held_catalog)
                by_id={i['candidate_id']:i for i in held_catalog['items']}
                self.assertIn('WORKSET_HELD',by_id[parent['candidate_id']]['blockers'])
                self.assertIn('DEPENDENCY_NOT_PROVEN',by_id[child['candidate_id']]['blockers'])
                self.assertEqual(by_id[parent['candidate_id']]['state'],'APPROVED_WAITING')
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),2)
