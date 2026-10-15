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

class FixedDeclarationMappingTests(unittest.TestCase):
    def test_observed_entrance_keeps_legacy_fixed_b8r_path_rule(self):
        import json
        from pathlib import Path
        from forge.ep_inspection_preview import check_input
        original=json.loads(Path('examples/project-adoption/adopt-existing-vision-input.json').read_text())
        value={k:original[k] for k in ('bootstrap_input','requested_artifacts','mappings')}
        fixed='.engineering-platform/repository.json'
        value['requested_artifacts']=[fixed]
        value['mappings']=[{'artifact_path':fixed,'source_path':'docs/RICHTING.md','choice':'LINK_EXISTING'}]
        with self.assertRaisesRegex(ContractError,'B8R declaration path is fixed'):check_input(value)
        value['mappings'][0]['source_path']=fixed
        self.assertEqual(check_input(value),value)

class ObservationUncertaintyTests(unittest.TestCase):
    """Modeled producer-wire cases; actual installed transport is qualified separately."""
    def sample(self):
        import json
        from pathlib import Path
        original=json.loads(Path('examples/project-adoption/adopt-existing-vision-input.json').read_text())
        value={k:original[k] for k in ('bootstrap_input','requested_artifacts','mappings')}
        v=wire();v['observation']['selection']=['docs/RICHTING.md','docs/architecture/ARCHITECTURE.md']
        content='Nederlandstalige bestaande visie'
        from hashlib import sha256
        v['observation']['documents']=[{'path':'docs/RICHTING.md','state':'PRESENT','content':content,'sha256':sha256(content.encode()).hexdigest()}, {'path':'docs/architecture/ARCHITECTURE.md','state':'ABSENT','content':None,'sha256':None}]
        b={**binding(v),'consumer_id':'synthetic-forge','principal':'synthetic-peer','audience':'synthetic-audience','content_paths':['docs/RICHTING.md']}
        return value,v,b

    def proposal(self,value,v,b):
        import json
        from forge.ep_inspection_preview import result
        response=result(value,observation(canonical(v),b),b)
        return json.loads(next(a['content'] for a in response['artifacts'] if a['path']=='proposal.json'))

    def test_metadata_only_oversized_and_missing_selected_document_are_not_absent(self):
        from hashlib import sha256
        for kind in ('metadata','oversized','missing'):
            value,v,b=self.sample()
            doc=v['observation']['documents'][0]
            if kind=='metadata':doc['content']=None;b['content_paths']=[]
            elif kind=='oversized':doc['content']='x'*8193;doc['sha256']=sha256(doc['content'].encode()).hexdigest()
            else:v['observation']['documents']=v['observation']['documents'][1:]
            proposal=self.proposal(value,v,b)
            entry=next(e for e in proposal['entries'] if e['artifact_path']=='docs/product/VISION.md')
            self.assertEqual(entry['operation'],'INSUFFICIENT_INFORMATION')
            if kind=='oversized':self.assertEqual(entry['reason'],'R51_DOCUMENT_CONTENT_LIMIT_EXCEEDED')
            self.assertNotEqual(entry['operation'],'PROPOSE_ADDITION')

    def test_conflicting_declaration_blocks_all_rows_dirty_context_remains_visible(self):
        value,v,b=self.sample()
        v['observation']['git']['unstaged_count']=2
        proposal=self.proposal(value,v,b)
        self.assertIn('OBSERVED_DIRTY_OR_UNRESOLVED_CONTEXT_PRESERVED',proposal['decisions'])
        v['observation']['canonical_declaration']={'state':'INVALID_OR_CONFLICTING','identity':None}
        self.assertTrue(all(e['operation']=='CONFLICT' for e in self.proposal(value,v,b)['entries']))
        v['observation']['canonical_declaration']={'state':'OBSERVED_DECLARATION_ONLY','identity':{**{k:value['bootstrap_input']['identity'][k] for k in ('project_id','repository_id','authority_repository_id')},'project_id':'foreign','role':'authority'}}
        self.assertTrue(all(e['operation']=='CONFLICT' for e in self.proposal(value,v,b)['entries']))

    def test_original_subject_content_consent_selection_and_null_combinations_refused(self):
        for kind in ('instance_id','source_ref','operation_id','host_id','hash','consent','absent-bytes','present-nohash','declaration','git-presence','selection','duplicate','exclusions','timezone'):
            _,v,b=self.sample()
            if kind in ('instance_id','source_ref','operation_id','host_id'):v[kind]='foreign'
            elif kind=='hash':v['observation']['documents'][0]['sha256']='f'*64
            elif kind=='consent':b['content_paths']=[]
            elif kind=='absent-bytes':v['observation']['documents'][1]['content']='not absent'
            elif kind=='present-nohash':v['observation']['documents'][0]['sha256']=None
            elif kind=='declaration':v['observation']['canonical_declaration']['state']='OBSERVED_DECLARATION_ONLY'
            elif kind=='git-presence':v['observation']['git']=None
            elif kind=='selection':v['observation']['selection']=[]
            elif kind=='duplicate':v['observation']['documents'].append(deepcopy(v['observation']['documents'][0]))
            elif kind=='exclusions':v['observation']['exclusions']=[]
            else:v['observation']['observed_at']='2026-10-15T17:13:58'
            with self.subTest(kind=kind),self.assertRaises((ContractError,ValueError)):observation(canonical(v),b)
