"""Actual chat generation and owner-scoped frozen canonical planning."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from jsonschema import Draft202012Validator
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from test_advisory_http import qual
import test_mission_concept_contract as content
from test_mission_concept_planning import profiles
from forge.mission_concept_contract import CONTRACT
from forge.mission_concept_setup import MissionConceptSetup
from forge.server_runtime import existing_instance


def call(port, token, method, route, body=None):
    request=Request('http://127.0.0.1:'+str(port)+route,method=method,
        headers={'Authorization':'Bearer '+token.read_text().strip(),'Content-Type':'application/json'},
        data=None if body is None else json.dumps(body).encode())
    try:
        with urlopen(request,timeout=15) as response:return response.status,json.load(response)
    except HTTPError as error:
        with error:return error.code,json.load(error)


def configure(root):
    grant=qual.configure(root)
    executable=root/'external-provider';raw=executable.read_text()
    raw=raw.replace("assert v['contract_version']=='forge-advisory-conversation/v1'",
                    "assert v['contract_version']=='forge-chat-first-mission/v1'")
    raw=raw.replace("assert schema['properties']['applied']=={'const':False}",
                    "assert schema['properties']['definition']['additionalProperties'] is False")
    start=raw.index("response={'contract_version'");end=raw.index("if fault=='inject'",start)
    raw=raw[:start]+('response={"contract_version":v["contract_version"],"request_digest":v["request_digest"],'
        '"definition":json.loads((ROOT/"model-output.private.json").read_text())}\n')+raw[end:]
    executable.write_text(raw)
    return grant


def model_output(root,definition):
    path=root/'model-output.private.json';path.write_text(json.dumps(definition));path.chmod(0o600)


class MissionConceptReadyHTTPTests(unittest.TestCase):
    def test_natural_turn_question_refinement_frozen_human_plan_and_owner_bounds(self):
        schema=json.loads((Path(__file__).resolve().parents[1]/'forge/api/mission-concepts-v1.json').read_text())
        Draft202012Validator.check_schema(schema);validator=Draft202012Validator(schema)
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'chat';grant=configure(root)
            with qual.http(root) as port:
                instance=existing_instance(root/'runtime')
                principal=sha256(qual.utils.fixture.IDENTITY.generated_uid.encode()).hexdigest()[:16]
                scope=qual.utils.PROJECT;repo=qual.utils.fixture.SOURCE.repository_id
                owner=root/'owner.private'
                issued=grant.issue(principal_id=principal,project_id=scope,repository_id=repo,
                    conversation_ids=['mission-chat'],expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),
                    maximum_turns=8,token_path=owner)
                setup=MissionConceptSetup(root/'runtime',instance.instance_id)
                configured=setup.configure(grant_id=issued['grant_id'],profiles=profiles(),maximum_missions=2)
                from contextlib import redirect_stdout
                from io import StringIO
                from forge.mission_concept_setup import main as setup_main
                inputs=root/'owner-inputs';inputs.mkdir(mode=0o700)
                config_file=inputs/'profiles.json';config_file.write_text(json.dumps(profiles()));config_file.chmod(0o600)
                arguments=['--data-root',str(root/'runtime'),'--grant-id',issued['grant_id'],
                           '--profiles-file',str(config_file),'--maximum-missions','2']
                with redirect_stdout(StringIO()) as output:
                    self.assertEqual(setup_main(arguments),0)
                    self.assertEqual(json.loads(output.getvalue())['configuration_digest'],configured['configuration_digest'])
                self.assertEqual(setup.configure(grant_id=issued['grant_id'],profiles=profiles(),maximum_missions=2),configured)
                with self.assertRaises(ValueError):
                    setup.configure(grant_id=issued['grant_id'],profiles=profiles(),maximum_missions=3)
                with self.assertRaises(PermissionError):
                    setup.configure(grant_id=grant._records()[0]['grant_id'],profiles=profiles(),maximum_missions=2)
                _,cap=call(port,owner,'GET','/v1/mission-concepts/capability')
                draft=content.MissionConceptContractTests().output()['definition']
                draft['questions']=['Only investigate the portal, or also implement it?']
                draft['work_kind']='UNDECIDED';draft['components']=[];model_output(root,draft)
                request={k:cap[k] for k in ('instance_id','project_id','repository_id','context_revision')}
                request.update(contract_version=CONTRACT,turn_id='first',conversation_id='mission-chat',
                    advisor_kind='BUSINESS',objective='I want clients to see their invoices and payments.',
                    expected_revision=0,selected_sources=[])
                status,first=call(port,owner,'POST','/v1/mission-concepts/mission-chat/turns',request)
                self.assertEqual(status,200,first)
                status,incomplete=call(port,owner,'GET','/v1/mission-concepts/mission-chat/package')
                self.assertEqual(status,200,incomplete);self.assertIsNone(incomplete['package'])
                self.assertFalse(incomplete['approval_supported'])
                validator.validate(incomplete)
                refined={**draft,'work_kind':'BUILD','questions':[],
                         'change_summary':'Build the portal; payment execution remains excluded.',
                         'components':['Invoice views','Payment views'],
                         'possible_subresults':[{'title':'Account isolation',
                             'expected_result':'The portal authenticates and isolates each account.',
                             'acceptance_criteria':['An account cannot see invoices belonging to another account.']},
                             {'title':'Invoice views','expected_result':'Clients see current invoice and payment status.',
                              'acceptance_criteria':['Clients see the invoice status belonging to their own account.']}]}
                model_output(root,refined)
                status,second=call(port,owner,'POST','/v1/mission-concepts/mission-chat/turns',
                    {**request,'turn_id':'second','objective':'Build it, split account isolation and invoice views, but do not execute payments.',
                     'expected_revision':first['current_revision'],'advisor_kind':'ARCHITECTURE'})
                self.assertEqual(status,200,second)
                status,prepared=call(port,owner,'GET','/v1/mission-concepts/mission-chat/package')
                self.assertEqual(status,200,prepared)
                package=prepared['package'];self.assertEqual(package['definition'],refined)
                validator.validate(prepared)
                self.assertEqual(package['planning']['maximum_actions'],4)
                self.assertEqual(package['authority']['maximum_missions'],2)
                self.assertEqual(package['consequences']['exclusions'],['Payment execution'])
                self.assertFalse(package['execution_started'])
                self.assertEqual(call(port,owner,'GET','/v1/mission-concepts/mission-chat/package?revision=1')[0],409)
                _,history=call(port,owner,'GET','/v1/mission-concepts/mission-chat')
                self.assertEqual(history['turns'][0]['outcome']['output']['definition'],draft)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),2)
                command={'contract_version':CONTRACT,'operation_id':'approve-exact-definition',
                         'revision':2,'package_digest':prepared['package_digest'],'confirm':True}
                status,approved=call(port,owner,'POST','/v1/mission-concepts/mission-chat/approve',command)
                self.assertEqual(status,200,approved)
                validator.validate(command);validator.validate(approved)
                self.assertEqual(approved['business_decision']['kind'],'BUSINESS')
                self.assertEqual(approved['architecture_decision']['kind'],'ARCHITECTURE')
                self.assertTrue(approved['mission_id'])
                self.assertFalse(approved['execution_started'])
                self.assertEqual(approved['current']['state'],'APPROVED_WAITING')
                status,replayed=call(port,owner,'POST','/v1/mission-concepts/mission-chat/approve',command)
                self.assertEqual(status,200,replayed)
                self.assertEqual(replayed,approved)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),2)
                from test_candidate_decisions_http import counts
                actual=counts(root)
                self.assertEqual(actual['governance_decisions'],2)
                self.assertEqual(actual['mission_id_allocations'],1)
                self.assertEqual(actual['mission_state'],1)
                self.assertEqual(actual['allocations'],1)
                self.assertEqual(actual['approved_worksets'],0)
                _,catalog=call(port,owner,'GET','/v1/mission-concepts/catalog')
                self.assertEqual(len(catalog['items']),1)
                self.assertEqual(catalog['items'][0]['object_id'],prepared['object_id'])
                self.assertEqual(catalog['items'][0]['candidate_id'],approved['candidate_id'])
                self.assertEqual(catalog['items'][0]['mission_id'],approved['mission_id'])
                self.assertEqual(catalog['items'][0]['state'],'APPROVED_WAITING')
                self.assertEqual(catalog['items'][0]['labels'],['Implementation'])
                self.assertEqual(len(catalog['items'][0]['definition']['possible_subresults']),2)
                # Suggestions remain content: no inferred child Mission or Action.
                self.assertIsNone(catalog['items'][0]['parent_id'])
                self.assertEqual(counts(root)['mission_state'],1)
                validator.validate(catalog)
                status,current=call(port,owner,'GET',
                    '/v1/mission-concepts/mission-chat/operations/approve-exact-definition')
                self.assertEqual(status,200,current)
                validator.validate(current)
                self.assertEqual(current['state'],'COMPLETE')
                self.assertEqual(current['mission_id'],approved['mission_id'])
                self.assertEqual(current['frozen_package'],prepared['package'])
                self.assertTrue(current['source_fresh'])
                status,alias=call(port,owner,'POST','/v1/mission-concepts/mission-chat/approve',
                    {**command,'operation_id':'alternate-confirmation-key'})
                self.assertEqual(status,200,alias)
                self.assertEqual(alias['mission_id'],approved['mission_id'])
                self.assertEqual(alias['original_registration'],approved['original_registration'])
                self.assertEqual(counts(root)['governance_decisions'],2)
                self.assertEqual(counts(root)['mission_id_allocations'],1)
                from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
                with InstalledDynamicMissionRuntime.open_for_governance_read(str(root/'runtime')) as runtime:
                    admitted=runtime.states.get(approved['mission_id'])
                    self.assertEqual(admitted.actions,())
                    self.assertEqual(admitted.intents,())
                    for phrase in refined['scope']:
                        self.assertIn('IN SCOPE: '+phrase,admitted.mission['engineering_constraints'])
                    self.assertIn('EXPECTED RESULT: '+refined['expected_result'],admitted.mission['engineering_constraints'])
                    self.assertEqual(admitted.mission['effect_policy']['write_paths'],
                        ['src/invoices/views.py','src/payments/views.py','tests/test_invoice_views.py','tests/test_payment_views.py'])
                    self.assertEqual(admitted.admission_contract['planning']['write_scopes'],
                                     admitted.mission['effect_policy']['write_paths'])
                    active=runtime.database._connection.execute('SELECT active_mission_id FROM dispatcher_state WHERE singleton=1').fetchone()
                    self.assertTrue(active is None or active[0] is None)
                before=counts(root)
                for change in ({'confirm':1}, {'actor':'business_owner'},
                               {'revision':0}, {'package_digest':'sha256:'+'b'*64}):
                    with self.subTest(change=change):
                        self.assertEqual(call(port,owner,'POST','/v1/mission-concepts/mission-chat/approve',
                            {**command,**change})[0],409)
                self.assertEqual(call(port,root/'bob.private','POST',
                    '/v1/mission-concepts/mission-chat/approve',command)[0],403)
                self.assertEqual(call(port,root/'admin.private','POST',
                    '/v1/mission-concepts/mission-chat/approve',command)[0],403)
                self.assertEqual(counts(root),before)
                successor={**refined,'scope':['Only invoice listing; do not implement payment views.'],
                    'components':['Invoice views'],'acceptance_criteria':[
                    *refined['acceptance_criteria'],'Show a recoverable error when invoice lookup is unavailable.'],
                    'change_summary':'Limit implementation to invoice listing and add visible error recovery.'}
                model_output(root,successor)
                _,fresh_context=call(port,owner,'GET','/v1/mission-concepts/mission-chat/context')
                status,third=call(port,owner,'POST','/v1/mission-concepts/mission-chat/turns',
                    {**request,'context_revision':fresh_context['context_revision'],'turn_id':'third','objective':'Only invoice listing, exclude payment views, and include recovery when invoice lookup fails.',
                     'expected_revision':second['current_revision'],'advisor_kind':'ARCHITECTURE'})
                self.assertEqual(status,200,third)
                _,old_operation=call(port,owner,'GET',
                    '/v1/mission-concepts/mission-chat/operations/approve-exact-definition')
                self.assertEqual(old_operation['state'],'COMPLETE')
                self.assertFalse(old_operation['source_fresh'])
                self.assertEqual(old_operation['current_definition_state'],'SUPERSEDED')
                self.assertEqual(old_operation['frozen_package'],prepared['package'])
                self.assertEqual(call(port,owner,'POST','/v1/mission-concepts/mission-chat/approve',command)[0],409)
                _,updated_catalog=call(port,owner,'GET','/v1/mission-concepts/catalog')
                self.assertEqual(len(updated_catalog['items']),1)
                self.assertEqual(updated_catalog['items'][0]['revision'],3)
                self.assertEqual(updated_catalog['items'][0]['state'],'CONCEPT')
                self.assertEqual(counts(root)['governance_decisions'],2)
                self.assertEqual(counts(root)['mission_id_allocations'],1)
                self.assertEqual(counts(root)['provider_calls'],3)
                # A second explicit confirmation approves the narrowed successor,
                # never mutating the earlier full-portal approvals or Mission.
                _,narrowed=call(port,owner,'GET','/v1/mission-concepts/mission-chat/package')
                second_command={**command,'operation_id':'approve-invoice-only','revision':3,
                                'package_digest':narrowed['package_digest']}
                status,second_approved=call(port,owner,'POST','/v1/mission-concepts/mission-chat/approve',second_command)
                self.assertEqual(status,200,second_approved)
                self.assertNotEqual(second_approved['candidate_id'],approved['candidate_id'])
                with InstalledDynamicMissionRuntime.open_for_governance_read(str(root/'runtime')) as runtime:
                    old=runtime.states.get(approved['mission_id']);new=runtime.states.get(second_approved['mission_id'])
                    self.assertEqual(old.mission['effect_policy'],package['candidate']['effect_policy'])
                    self.assertEqual(new.mission['effect_policy']['write_paths'],
                                     ['src/invoices/views.py','tests/test_invoice_views.py'])
                    self.assertIn('IN SCOPE: '+successor['scope'][0],new.mission['engineering_constraints'])
                    self.assertNotEqual(old.admission_contract['subject_revision'],new.admission_contract['subject_revision'])
                    self.assertEqual(new.actions,());self.assertEqual(old.actions,())
                self.assertEqual(counts(root)['governance_decisions'],4)
                self.assertEqual(counts(root)['mission_state'],2)
                self.assertEqual(counts(root)['provider_calls'],3)
                grant.revoke(issued['grant_id'])
                self.assertEqual(call(port,owner,'POST','/v1/mission-concepts/mission-chat/approve',command)[0],401)
