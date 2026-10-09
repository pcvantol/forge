"""Actual scoped ID resolution, no per-Mission tokens or model invocations."""
from datetime import UTC,datetime,timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import json
from jsonschema import Draft202012Validator
from test_mission_concept_ready_http import configure,call,model_output
import test_mission_concept_contract as content
from test_mission_concept_planning import profiles
from test_advisory_http import qual
from forge.mission_concept_setup import MissionConceptSetup
from forge.mission_concept_resolver import MissionConceptResolver
from forge.mission_concept_contract import CONTRACT
from forge.server_runtime import existing_instance


class MissionConceptResolverTests(unittest.TestCase):
    def test_existing_unbound_transcript_is_preserved_and_never_adopted(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'occupied';grant=configure(root)
            with qual.http(root) as port:
                instance=existing_instance(root/'runtime')
                principal=sha256(qual.utils.fixture.IDENTITY.generated_uid.encode()).hexdigest()[:16]
                token_path=root/'owner.private'
                issued=grant.issue(principal_id=principal,project_id=qual.utils.PROJECT,
                    repository_id=qual.utils.fixture.SOURCE.repository_id,
                    conversation_ids=['occupied-slot','unused-slot'],
                    expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),maximum_turns=8,token_path=token_path)
                MissionConceptSetup(root/'runtime',instance.instance_id).configure(
                    grant_id=issued['grant_id'],profiles=profiles(),maximum_missions=2)
                _,cap=call(port,token_path,'GET','/v1/mission-concepts/capability')
                model_output(root,content.MissionConceptContractTests().output()['definition'])
                request={k:cap[k] for k in ('instance_id','project_id','repository_id','context_revision')}
                request.update(contract_version=CONTRACT,conversation_id='occupied-slot',turn_id='existing',
                    advisor_kind='BUSINESS',objective='Existing independent product discussion.',expected_revision=0,selected_sources=[])
                self.assertEqual(call(port,token_path,'POST','/v1/mission-concepts/occupied-slot/turns',request)[0],200)
                from forge.mission_concept_service import MissionConceptService
                p=grant.authorize('Bearer '+token_path.read_text().strip())
                path=MissionConceptService(root/'runtime',grant,qual.utils.fixture.PROVIDER)._path(p,'occupied-slot')
                before=path.read_bytes()
                body={'contract_version':CONTRACT,'operation_id':'resolve-new',
                      'workspace_conversation_id':'own-chat','workspace_draft_id':'new-draft'}
                status,resolved=call(port,token_path,'POST','/v1/mission-concepts/resolve',body)
                self.assertEqual(status,200,resolved)
                self.assertEqual(resolved['binding']['conversation_id'],'unused-slot')
                self.assertEqual(path.read_bytes(),before)
                self.assertEqual(call(port,token_path,'POST','/v1/mission-concepts/resolve',
                    {**body,'operation_id':'another','workspace_draft_id':'another-draft'})[0],409)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_workspace_references_replay_restart_alias_capacity_and_scope(self):
        schema=json.loads((Path(__file__).resolve().parents[1]/'forge/api/mission-concepts-v1.json').read_text())
        Draft202012Validator.check_schema(schema);validator=Draft202012Validator(schema)
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'resolver';grant=configure(root)
            with qual.http(root) as port:
                instance=existing_instance(root/'runtime')
                principal=sha256(qual.utils.fixture.IDENTITY.generated_uid.encode()).hexdigest()[:16]
                owner=root/'owner.private'
                issued=grant.issue(principal_id=principal,project_id=qual.utils.PROJECT,
                    repository_id=qual.utils.fixture.SOURCE.repository_id,
                    conversation_ids=['producer-slot-a','producer-slot-b'],
                    expires_at=(datetime.now(UTC)+timedelta(hours=1)).isoformat(),maximum_turns=8,token_path=owner)
                setup=MissionConceptSetup(root/'runtime',instance.instance_id)
                setup.configure(grant_id=issued['grant_id'],profiles=profiles(),maximum_missions=2)
                body={'contract_version':CONTRACT,'operation_id':'resolve-1',
                      'workspace_conversation_id':'workspace-chat','workspace_draft_id':'workspace-draft-1'}
                status,first=call(port,owner,'POST','/v1/mission-concepts/resolve',body)
                self.assertEqual(status,200,first)
                validator.validate(body);validator.validate(first)
                self.assertEqual(first['binding']['conversation_id'],'producer-slot-a')
                self.assertFalse(first['budget_reset']);self.assertFalse(first['grant_issued'])
                restarted=MissionConceptResolver(root/'runtime',instance.instance_id)
                token='Bearer '+owner.read_text().strip()
                self.assertEqual(restarted.resolve(token,body),first)
                alias=restarted.resolve(token,{**body,'operation_id':'alias'})
                self.assertEqual(alias['binding'],first['binding'])
                changed={**body,'workspace_draft_id':'workspace-draft-2'}
                self.assertEqual(call(port,owner,'POST','/v1/mission-concepts/resolve',changed)[0],409)
                status,second=call(port,owner,'POST','/v1/mission-concepts/resolve',
                    {**changed,'operation_id':'resolve-2'})
                self.assertEqual(status,200,second)
                self.assertEqual(second['binding']['conversation_id'],'producer-slot-b')
                self.assertEqual(call(port,owner,'POST','/v1/mission-concepts/resolve',
                    {**body,'operation_id':'resolve-3','workspace_draft_id':'workspace-draft-3'})[0],409)
                self.assertEqual(call(port,root/'bob.private','POST','/v1/mission-concepts/resolve',body)[0],403)
                self.assertEqual(call(port,owner,'POST','/v1/mission-concepts/resolve',
                    {**body,'principal_id':'other'})[0],400)
                self.assertFalse((root/'provider-requests.private.jsonl').exists())
                self.assertEqual(len(grant._records()),3)
                _,cap=call(port,owner,'GET','/v1/mission-concepts/capability')
                model_output(root,content.MissionConceptContractTests().output()['definition'])
                request={k:cap[k] for k in ('instance_id','project_id','repository_id','context_revision')}
                request.update(contract_version=CONTRACT,conversation_id=first['binding']['conversation_id'],
                    turn_id='first-natural-turn',advisor_kind='BUSINESS',
                    objective='Build a portal where clients can see their invoices.',
                    expected_revision=0,selected_sources=[])
                status,generated=call(port,owner,'POST','/v1/mission-concepts/'+
                    first['binding']['conversation_id']+'/turns',request)
                self.assertEqual(status,200,generated)
                self.assertEqual(generated['original_turn']['status'],'COMPLETE')
                self.assertEqual(restarted.resolve(token,body),first)
                self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)
                saved=restarted.path.read_bytes();restarted.path.write_text('{broken')
                self.assertEqual(call(port,owner,'POST','/v1/mission-concepts/resolve',body)[0],503)
                restarted.path.write_bytes(saved)
                grant.revoke(issued['grant_id'])
                self.assertEqual(call(port,owner,'POST','/v1/mission-concepts/resolve',body)[0],401)
