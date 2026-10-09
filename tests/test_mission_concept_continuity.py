"""Real HTTP/governance continuity; only external model/OS adapters are fixtures."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import time
import unittest
from unittest.mock import patch
import sqlite3
from contextlib import closing
from test_mission_concept_ready_http import configure, call, model_output
from test_mission_concept_planning import profiles
import test_mission_concept_contract as content
from test_mission_concept_recovery import driver
from test_advisory_http import qual
from forge.server_runtime import existing_instance
from forge.mission_concept_setup import MissionConceptSetup
from forge.mission_concept_contract import CONTRACT


class MissionConceptContinuityTests(unittest.TestCase):
    def provision(self, root, grant, *, seconds=3600, turns=1, missions=1,
                  conversations=None, principal=None, work_profiles=None):
        token = root / ('owner-' + str(len(grant._records())) + '.private')
        issued = grant.issue(
            principal_id=principal or sha256(qual.utils.fixture.IDENTITY.generated_uid.encode()).hexdigest()[:16],
            project_id=qual.utils.PROJECT, repository_id=qual.utils.fixture.SOURCE.repository_id,
            conversation_ids=conversations or ['mission-chat'], maximum_turns=turns,
            expires_at=(datetime.now(UTC)+timedelta(seconds=seconds)).isoformat(), token_path=token)
        instance = existing_instance(root/'runtime')
        setup = MissionConceptSetup(root/'runtime', instance.instance_id)
        setup.configure(grant_id=issued['grant_id'], profiles=work_profiles or profiles(), maximum_missions=missions)
        return token, issued

    def complete(self, root, port, token, stop=None):
        base = '/v1/mission-concepts/mission-chat'
        model_output(root, content.MissionConceptContractTests().output()['definition'])
        status, context = call(port, token, 'GET', base+'/context')
        self.assertEqual(status, 200, context)
        request = {'contract_version':CONTRACT,'turn_id':'continuity-turn',
                   'instance_id':context['context']['instance_id'],
                   'project_id':qual.utils.PROJECT,'repository_id':qual.utils.fixture.SOURCE.repository_id,
                   'conversation_id':'mission-chat','expected_revision':0,
                   'context_revision':context['context_revision'],'advisor_kind':'BUSINESS',
                   'objective':'Build a client portal showing invoice and payment status.',
                   'selected_sources':[]}
        status, generated = call(port, token, 'POST', base+'/turns', request)
        self.assertEqual(status, 200, generated)
        status, prepared = call(port, token, 'GET', base+'/package')
        self.assertEqual(status, 200, prepared)
        command = {'contract_version':CONTRACT,'operation_id':'original-approval',
                   'revision':1,'package_digest':prepared['package_digest'],'confirm':True}
        if stop is None:
            status, approved = call(port, token, 'POST', base+'/approve', command)
            self.assertEqual(status, 200, approved)
        else:
            def identity():
                if stop(driver.counts(root)):
                    raise PermissionError('isolated external operator interruption')
                return qual.utils.fixture.IDENTITY
            with patch.object(qual.utils.composition.MacOSGeneratedUIDIdentityAdapter,
                              'resolve', side_effect=identity):
                status, approved = call(port, token, 'POST', base+'/approve', command)
            self.assertNotEqual(status, 200, approved)
        return prepared, command, approved

    def test_natural_expiry_equal_replacement_exact_read_replay_catalog_restart_zero_effects(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)/'continuity'; grant = configure(root)
            with qual.http(root) as port:
                old_token, old = self.provision(root, grant, seconds=8)
                prepared, command, approved = self.complete(root, port, old_token)
                token, _ = self.provision(root, grant)
            remaining = (datetime.fromisoformat(old['expires_at'])-datetime.now(UTC)).total_seconds()
            if remaining > 0:
                time.sleep(remaining+0.02)
            baseline = driver.counts(root)
            transcript = {p:p.read_bytes() for p in (root/'runtime/advisory').rglob('*.json')}
            # Exercise the Linux order: non-transcript ledgers precede concepts.
            transcript = dict(sorted(transcript.items(),
                key=lambda item: item[0].name.startswith('concept-')))
            before_setup = (root/'runtime/credentials/mission-concepts/setup.json').read_bytes()
            for _ in range(2):
                with qual.http(root) as port:
                    base='/v1/mission-concepts/mission-chat'
                    self.assertEqual(call(port, old_token, 'GET', base+'/package')[0], 401)
                    status, actual = call(port, token, 'GET', base+'/package')
                    self.assertEqual(status,200,actual); self.assertEqual(actual,prepared)
                    status, replay = call(port, token, 'POST', base+'/approve',command)
                    self.assertEqual(status,200,replay); self.assertEqual(replay,approved)
                    status, operation=call(port,token,'GET',base+'/operations/original-approval')
                    self.assertEqual(status,200,operation); self.assertTrue(operation['source_fresh'])
                    self.assertEqual(operation['frozen_package'],prepared['package'])
                    _, catalog=call(port,token,'GET','/v1/mission-concepts/catalog')
                    self.assertEqual(catalog['items'][0]['state'],'APPROVED_WAITING')
                    self.assertEqual(catalog['items'][0]['mission_id'],approved['mission_id'])
                    self.assertNotEqual(call(port,token,'POST',base+'/approve',
                        {**command,'operation_id':'replacement-new-key'})[0],200)
                    _, current_context=call(port,token,'GET',base+'/context')
                    concept_paths=[p for p in transcript
                        if p.parent==root/'runtime/advisory/transcripts'
                        and p.name.startswith('concept-')]
                    self.assertEqual(len(concept_paths),1)
                    stored=json.loads(transcript[concept_paths[0]])
                    status,out=call(port,token,'POST',base+'/turns',
                        {**stored['turns'][0]['request'],'turn_id':'extra-turn',
                         'expected_revision':stored['revision'],
                         'context_revision':current_context['context_revision']})
                    self.assertEqual(status,409,out)
                    self.assertEqual(driver.counts(root),baseline)
            self.assertEqual({p:p.read_bytes() for p in transcript},transcript)
            self.assertEqual((root/'runtime/credentials/mission-concepts/setup.json').read_bytes(),before_setup)
            self.assertEqual(len((root/'provider-requests.private.jsonl').read_text().splitlines()),1)

    def test_changed_scope_bounds_profiles_and_original_revocation_deny_without_effects(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'denials';grant=configure(root)
            with qual.http(root) as port:
                original_token, old=self.provision(root,grant)
                _,command,_=self.complete(root,port,original_token)
                baseline=driver.counts(root)
                changed=profiles();changed['BUILD']['maximum_actions']+=1
                for changes in ({'turns':2},{'missions':2},
                                {'conversations':['mission-chat','extra']},
                                {'work_profiles':changed}):
                    with self.subTest(changes=changes):
                        token,_=self.provision(root,grant,**changes)
                        for route,method,body in (('/package','GET',None),
                            ('/approve','POST',command),('/operations/original-approval','GET',None)):
                            status,out=call(port,token,method,'/v1/mission-concepts/mission-chat'+route,body)
                            self.assertNotEqual(status,200,out)
                        self.assertEqual(driver.counts(root),baseline)
                token,_=self.provision(root,grant)
                grant.revoke(old['grant_id'])
                self.assertEqual(call(port,token,'GET','/v1/mission-concepts/mission-chat/package')[0],403)
                self.assertEqual(driver.counts(root),baseline)

    def test_replacement_cannot_complete_real_partial_effects(self):
        stages = (
            lambda c: c['advisory_candidate_intents'] == 1,
            lambda c: c['advisory_candidate_registrations'] == 1,
            lambda c: c['governance_decisions'] == 1 and c['candidate_decision_receipts'] == 0,
            lambda c: c['candidate_decision_receipts'] == 1,
            lambda c: c['candidate_decision_receipts'] == 2 and c['mission_state'] == 0)
        for stage, stop in enumerate(stages):
            with self.subTest(stage=stage), TemporaryDirectory() as tmp:
                root=Path(tmp)/'partial';grant=configure(root)
                with qual.http(root) as port:
                    original,_=self.provision(root,grant)
                    _,command,_=self.complete(root,port,original,stop=stop)
                    token,_=self.provision(root,grant)
                    baseline=driver.counts(root)
                    for method,route,body in (('GET','/package',None),('POST','/approve',command)):
                        status,out=call(port,token,method,'/v1/mission-concepts/mission-chat'+route,body)
                        self.assertNotEqual(status,200,out)
                    self.assertEqual(driver.counts(root),baseline)

    def test_missing_canonical_proof_and_current_revocation_deny(self):
        for table in ('candidate_decision_receipts','allocations','advisory_candidate_registrations',
                      'advisory_candidate_intents'):
            with self.subTest(table=table),TemporaryDirectory() as tmp:
                root=Path(tmp)/'missing';grant=configure(root)
                with qual.http(root) as port:
                    original,_=self.provision(root,grant)
                    _,command,_=self.complete(root,port,original)
                    token,new=self.provision(root,grant)
                    # Declared isolated storage fault after real canonical approval.
                    with closing(sqlite3.connect(root/'runtime/governance/candidates.sqlite')) as db:
                        # Corrupt disposable fixture storage below the real immutable
                        # API, never a supported product mutation or success fixture.
                        triggers=db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",(table,)).fetchall()
                        for name,_ in triggers:
                            db.execute('DROP TRIGGER "'+name.replace('"','""')+'"')
                        db.execute('DELETE FROM '+table)
                        for _,sql in triggers:db.execute(sql)
                        db.commit()
                    baseline=driver.counts(root)
                    self.assertNotEqual(call(port,token,'GET','/v1/mission-concepts/mission-chat/package')[0],200)
                    self.assertNotEqual(call(port,token,'POST','/v1/mission-concepts/mission-chat/approve',command)[0],200)
                    self.assertEqual(driver.counts(root),baseline)
                    grant.revoke(new['grant_id'])
                    self.assertEqual(call(port,token,'GET','/v1/mission-concepts/mission-chat/package')[0],401)

    def test_missing_original_grant_setup_or_corrupt_turn_deny(self):
        for fault in ('grant','setup','setup-digest','turn'):
            with self.subTest(fault=fault),TemporaryDirectory() as tmp:
                root=Path(tmp)/'provenance';grant=configure(root)
                with qual.http(root) as port:
                    original,old=self.provision(root,grant)
                    _,command,_=self.complete(root,port,original)
                    token,_=self.provision(root,grant)
                    if fault=='grant':
                        path=grant.path;value=json.loads(path.read_text())
                        value['records']=[r for r in value['records'] if r['grant_id']!=old['grant_id']]
                    elif fault.startswith('setup'):
                        path=root/'runtime/credentials/mission-concepts/setup.json'
                        value=json.loads(path.read_text())
                        if fault=='setup':
                            value['records']=[r for r in value['records'] if r['grant_id']!=old['grant_id']]
                        else:
                            next(r for r in value['records'] if r['grant_id']==old['grant_id'])['configuration_digest']='sha256:'+'0'*64
                    else:
                        path=next((root/'runtime/advisory/transcripts').glob('concept-*.json'))
                        value=json.loads(path.read_text());value['turns'][0]['outcome']['result_digest']='sha256:'+'0'*64
                    # Explicit isolated private-storage corruption; no success state seed.
                    path.write_text(json.dumps(value))
                    baseline=driver.counts(root)
                    self.assertNotEqual(call(port,token,'GET','/v1/mission-concepts/mission-chat/package')[0],200)
                    self.assertNotEqual(call(port,token,'POST','/v1/mission-concepts/mission-chat/approve',command)[0],200)
                    self.assertEqual(driver.counts(root),baseline)

    def test_exact_original_request_mission_admission_allocation_proof_required(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'exact-proof';grant=configure(root)
            with qual.http(root) as port:
                original,_=self.provision(root,grant)
                _,command,approved=self.complete(root,port,original)
                token,_=self.provision(root,grant)
                base='/v1/mission-concepts/mission-chat'
                status,out=call(port,token,'GET',base+'/package')
                self.assertEqual(status,200,out)
                faults=(('state','mission_id'),('mission','engineering_constraints'),
                    *(('admission',k) for k in ('envelope_digest','candidate_id','installation_id',
                        'business_decision_id','architecture_decision_id','planning','mission')),
                    *(('allocation',k) for k in ('candidate_id','installation_id','business_decision_evidence_id',
                        'architecture_decision_evidence_id')),
                    *(('request',k) for k in ('confirm','context_revision','proposal_digest',
                        'proposal_revision','expected_conversation_revision','extra_field')))
                for kind,key in faults:
                    with self.subTest(kind=kind,key=key):
                        database=root/'runtime'/('governance/candidates.sqlite' if kind in ('request','allocation') else 'forge.db')
                        table='advisory_candidate_intents' if kind=='request' else 'allocations' if kind=='allocation' else 'mission_state'
                        with closing(sqlite3.connect(database)) as db:
                            raw=db.execute('SELECT document FROM '+table).fetchone()[0]
                            value=json.loads(raw)
                            target=value['mission'] if kind=='mission' else value['admission_contract'] if kind=='admission' else value['request'] if kind=='request' else value
                            if key=='engineering_constraints':target[key].append('Unapproved expanded objective.')
                            elif key=='planning':target[key]['maximum_actions']+=1
                            elif key=='mission':target[key]['engineering_constraints'].append('Unapproved admission definition.')
                            elif key=='confirm':target[key]=False
                            elif key=='extra_field':target[key]='not admitted'
                            elif type(target[key]) is int:target[key]+=1
                            else:target[key]='sha256:'+'b'*64 if 'digest' in key or 'revision' in key else 'foreign-binding'
                            triggers=db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?",(table,)).fetchall()
                            for name,_ in triggers:
                                db.execute('DROP TRIGGER "'+name.replace('"','""')+'"')
                            db.execute('UPDATE '+table+' SET document=?',(json.dumps(value),))
                            for _,sql in triggers:db.execute(sql)
                            db.commit()
                        baseline=driver.counts(root)
                        try:
                            for method,route,body in (('GET',base+'/package',None),
                                ('POST',base+'/approve',command),
                                ('GET',base+'/operations/original-approval',None),
                                ('GET','/v1/mission-concepts/catalog',None)):
                                status,out=call(port,token,method,route,body)
                                self.assertNotEqual(status,200,out)
                            self.assertEqual(driver.counts(root),baseline)
                        finally:
                            with closing(sqlite3.connect(database)) as db:
                                for name,_ in triggers:
                                    db.execute('DROP TRIGGER "'+name.replace('"','""')+'"')
                                db.execute('UPDATE '+table+' SET document=?',(raw,))
                                for _,sql in triggers:db.execute(sql)
                                db.commit()
