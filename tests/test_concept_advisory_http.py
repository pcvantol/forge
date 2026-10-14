import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from contextlib import contextmanager
from importlib.util import spec_from_file_location,module_from_spec
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from forge.server_runtime import ForgeServerRuntime
from forge.concept_advisory_contract import digest
from tests.test_concept_advisory_contract import example
spec=spec_from_file_location('concept_fixture',Path(__file__).resolve().parents[1]/'scripts/qualification/concept_advisory_fixture.py')
fixture=module_from_spec(spec);spec.loader.exec_module(fixture)

@contextmanager
def http(root):
    runtime=ForgeServerRuntime(data_root=root/'runtime',credential_file=root/'admin.private',host='127.0.0.1',port=0,provider_id='concept-fixture')
    thread=Thread(target=runtime.server.serve_forever,daemon=True);thread.start()
    try:yield runtime.server.server_address[1]
    finally:runtime.server.shutdown();thread.join(3);runtime.server.server_close()

def call(port,token,method,path,body=None,audience='synthetic-workspace'):
    r=Request('http://127.0.0.1:'+str(port)+path,method=method,data=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token.read_text().strip(),'X-Forge-Concept-Audience':audience,'Content-Type':'application/json'})
    try:
        with urlopen(r,timeout=15) as response:return response.status,json.loads(response.read())
    except HTTPError as error:
        try:return error.code,json.loads(error.read())
        finally:error.close()

class ConceptHttpTest(unittest.TestCase):
    def test_business_updated_briefing_architecture_exact_replay_and_restart(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'synthetic';fixture.configure(root)
            with http(root) as port:
                alice=root/'alice.private';status,cap=call(port,alice,'GET','/v1/concept-advisory/capability');self.assertEqual(status,200,cap)
                r=example();r.update(instance_id=cap['instance_id'],dossier_id='dossier-alice',conversation_id='conversation-alice',transfer_policy_digest=cap['provider']['transfer_policy_digest'])
                status,out=call(port,alice,'POST','/v1/concept-advisory/turns',r);self.assertEqual(status,200,out);self.assertEqual(out['original_turn']['status'],'COMPLETE',out)
                self.assertEqual(call(port,alice,'POST','/v1/concept-advisory/turns',r)[1]['original_turn'],out['original_turn'])
                revised=json.loads(json.dumps(r));revised.update(operation_id='second',turn_id='second',advisor_kind='ARCHITECTURE',expected_revision=1)
                revised['briefing']['revision']=2;revised['briefing']['fields']['users']='Explicitly accepted local volunteers';revised['briefing_digest']=digest(revised['briefing'])
                status,arch=call(port,alice,'POST','/v1/concept-advisory/turns',revised);self.assertEqual(status,200,arch);self.assertEqual(arch['original_turn']['status'],'COMPLETE',arch)
                self.assertEqual(call(port,root/'bob.private','GET','/v1/concept-advisory/history?dossier_id=dossier-alice&conversation_id=conversation-alice')[0],403)
                self.assertEqual(call(port,root/'admin.private','GET','/v1/concept-advisory/capability')[0],403)
                self.assertEqual(call(port,alice,'GET','/v1/onboarding/capability')[0],403)
                self.assertEqual(call(port,alice,'GET','/v1/concept-advisory/capability',audience='foreign')[0],403)
            with http(root) as port:
                recovered=call(port,alice,'GET','/v1/concept-advisory/intents/operation-one?dossier_id=dossier-alice&conversation_id=conversation-alice')
                self.assertEqual(recovered[0],200,recovered);self.assertEqual(recovered[1]['original_turn'],out['original_turn'])
            calls=[json.loads(line) for line in (root/'provider-requests.private.jsonl').read_text().splitlines()]
            self.assertEqual(len(calls),2);self.assertEqual(calls[1]['prior_turns'][0]['request'],r)
            self.assertEqual(calls[1]['request']['briefing']['revision'],2)
