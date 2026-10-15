"""Qualified EP wire data remains historical, typed and source-bound."""
import unittest
from copy import deepcopy
from forge.ep_inspection_contract import observation, document_observations
from forge.project_bootstrap.schema import canonical, ContractError


def wire():
    return {'contract_version':'1.0','operation_id':'op-original','source_ref':'source-original',
            'instance_id':'ep-instance','host_id':'a'*64,'outcome':'COMPLETE','error':None,'http_status':200,
            'freshness':'AS_OF_OBSERVATION_NOT_CONTINUOUS','administrative_records':2,
            'target_write_operations':0,'b8r_write_operations':0,'producer_version':'2.3.121',
            'profile':'LOCAL_GENESIS_INSPECT_READ_V1',
            'limits':{'entries':2048,'documents':16,'document_bytes':65536,'all_document_bytes':262144,'hashed_worktree_bytes':4194304,'worker_seconds':15},
            'observation':{'state':'UNBORN_GIT','git':{'state':'UNBORN_GIT','head':None,'tree':None,
              'staged_count':0,'unstaged_count':0,'untracked_candidate_count':0,'unresolved_index_entries':0,
              'remote_present':False,'ignore_rules':'NOT_EVALUATED','git_execution':'NONE','hashed_worktree_bytes':0},
              'documents':[],'selection':[],'exclusions':['ALL_UNSELECTED_CONTENT','ASSESSMENT_AND_REPOSITORY_EXECUTION'],
              'assessments':'NOT_ASSESSED','completeness':'COMPLETE_WITHIN_SELECTION','observed_entries':0,
              'observed_at':'2026-10-15T17:13:58+00:00','canonical_declaration':{'state':'NOT_INSPECTED','identity':None},
              'source_fingerprint':'b'*64}}


def binding(value):
    return {**{k:value[k] for k in ('operation_id','source_ref','instance_id','host_id')},'paths':value['observation']['selection'],'content_paths':[]}


class EPContractTests(unittest.TestCase):
    def test_valid_historical_unborn_does_not_assert_current_revision(self):
        v=wire();self.assertEqual(observation(canonical(v),binding(v)),v)
        self.assertEqual(document_observations(v),[])

    def test_partial_unborn_head_tree_is_not_a_valid_observation(self):
        for key in ('head','tree'):
            v=wire();v['observation']['git'][key]='c'*40
            with self.subTest(key=key),self.assertRaises(ContractError):observation(canonical(v),binding(v))

    def test_closed_source_selection_and_null_semantics(self):
        for change in ('foreign','unknown','null'):
            v=wire();b=binding(v)
            if change=='foreign':v['source_ref']='other'
            elif change=='unknown':v['unexpected']=True
            else:v['observation']=None
            with self.subTest(change=change),self.assertRaises(ContractError):observation(canonical(v),b)

if __name__=='__main__':unittest.main()

class ObservedAdoptionTests(unittest.TestCase):
    def test_dutch_vision_link_real_absence_addition_and_unknown_roadmap(self):
        import json
        from pathlib import Path
        from hashlib import sha256
        from forge.ep_inspection_preview import result
        original=json.loads(Path('examples/project-adoption/adopt-existing-vision-input.json').read_text())
        value={k:original[k] for k in ('bootstrap_input','requested_artifacts','mappings')}
        value['requested_artifacts'].append('docs/roadmap/ROADMAP.md')
        vision=next(d for d in original['inventory']['documents'] if d['path']=='docs/RICHTING.md')
        v=wire();v['observation']['selection']=['docs/RICHTING.md','docs/architecture/ARCHITECTURE.md']
        v['observation']['documents']=[{'path':'docs/RICHTING.md','state':'PRESENT','content':vision['content'],'sha256':sha256(vision['content'].encode()).hexdigest()},
          {'path':'docs/architecture/ARCHITECTURE.md','state':'ABSENT','sha256':None,'content':None}]
        b={**binding(v),'content_paths':['docs/RICHTING.md'],'consumer_id':'synthetic-forge','principal':'synthetic-peer','audience':'synthetic-audience'}
        response=result(value,observation(canonical(v),b),b)
        proposal=json.loads(next(a['content'] for a in response['artifacts'] if a['path']=='proposal.json'))
        entries={x['artifact_path']:x for x in proposal['entries']}
        linked=entries['docs/product/VISION.md'];self.assertEqual(linked['operation'],'LINK_EXISTING')
        self.assertEqual(linked['mapping_source']['content'],vision['content']);self.assertIsNone(linked['mapping_source']['mode'])
        self.assertEqual(entries['docs/architecture/ARCHITECTURE.md']['operation'],'PROPOSE_ADDITION')
        self.assertEqual(entries['docs/roadmap/ROADMAP.md']['operation'],'INSUFFICIENT_INFORMATION')
        self.assertEqual(entries['docs/roadmap/ROADMAP.md']['before'],{'status':'UNKNOWN'})
        self.assertNotIn('SUPPLIED_OBSERVATIONS_NOT_LIVE_INSPECTION',proposal['decisions'])
