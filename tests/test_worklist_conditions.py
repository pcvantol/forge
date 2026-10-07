"""Completion/selector facts deny fabricated completion and inconsistent snapshots."""
import sqlite3
import unittest
from copy import deepcopy
from forge.worklist_conditions import completion_facts,continuation,snapshot_revision,SNAPSHOT_FIELDS

class WorklistConditionTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE execution_receipts(receipt_id TEXT)')
        self.db.execute('CREATE TABLE governance_decisions(decision_id TEXT,document TEXT,digest TEXT)')

    def test_green_state_or_missing_receipt_never_proves_completion(self):
        for state in [None,{}, {'status':'COMPLETED'}, {'status':'COMPLETED','completion':{'all_required_criteria_proven':1}},
            {'completion':{'all_required_criteria_proven':True,'criteria':[{'status':'PROVEN','observations':['fixture']}]},
             'execution_evidence':{'outcome':'complete','receipt_id':'unknown'}}]:
            self.assertFalse(completion_facts(self.db,state)[0])

    def test_real_receipt_reference_still_requires_current_business_acceptance(self):
        self.db.execute("INSERT INTO execution_receipts VALUES ('receipt')")
        repository={'mission_id':'MISSION-1','action_id':'action','report_id':'report','content_digest':'sha256:'+'a'*64}
        from forge.models.criterion_observation import canonical_digest
        state={'mission_id':'MISSION-1','status':'AWAITING_APPROVAL',
            'completion':{'all_required_criteria_proven':True,'criteria':[{'status':'PROVEN','observations':['fixture'],'execution_evidence':[{'receipt_id':'receipt','action_id':'action','repository_evidence_digest':canonical_digest(repository)}]}]},
            'execution_evidence':{'outcome':'complete','receipt_id':'receipt','repository_evidence':repository},
            'pause_reason':{'schema_version':'forge-final-acceptance-requirement/v1'}}
        state['execution_history']=[deepcopy(state['execution_evidence'])]
        proven,final,refs=completion_facts(self.db,state)
        self.assertFalse(proven);self.assertEqual(final,'WAITING');self.assertEqual(refs[0]['kind'],'MISSION_COMPLETION')
        state['pause_reason']=None;state['status']='COMPLETED'
        self.assertFalse(completion_facts(self.db,state)[0])
        state['approval_record']={'approval_id':'missing'}
        self.assertFalse(completion_facts(self.db,state)[0])
        self.db.execute("INSERT INTO governance_decisions VALUES ('missing','{}','bad')")
        self.assertFalse(completion_facts(self.db,state)[0])

    def test_only_producer_committed_selector_declares_next_or_idle(self):
        self.assertEqual(continuation([])['state'],'IDLE')
        item={'candidate_id':'a','mission_id':None,'committed_order':0,'completed':False,'active':False,
              'blocking_reasons':['ACTIVATION_NOT_YET_QUALIFIED']}
        self.assertEqual(continuation([item])['state'],'UNKNOWN')
        item['blocking_reasons']=['DEPENDENCY_NOT_PROVEN'];self.assertEqual(continuation([item])['state'],'BLOCKED')
        item['blocking_reasons']=[];self.assertEqual(continuation([item])['state'],'READY')
        item['active']=True;self.assertIn('MISSION_ACTIVE',continuation([item])['reason_codes'])
        item['completed']=True;self.assertEqual(continuation([item])['state'],'IDLE')

    def test_snapshot_binds_revisions_actor_members_and_continuation_not_wallclock(self):
        doc={key:None for key in SNAPSHOT_FIELDS};doc.update({'observed_at':'now','freshness':'CURRENT_READBACK'})
        digest=snapshot_revision(doc)
        doc['observed_at']='later';self.assertEqual(digest,snapshot_revision(doc))
        for key in SNAPSHOT_FIELDS:
            changed=deepcopy(doc);changed[key]='changed';self.assertNotEqual(digest,snapshot_revision(changed))
