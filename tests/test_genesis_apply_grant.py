"""Actual owning runtime grants; no transport or EP effect claims."""
import unittest
from datetime import UTC, datetime, timedelta
import tests.test_genesis_bootstrap_http as bootstrap_tests
BASE = bootstrap_tests.BASE
from forge.genesis_apply_grant import GenesisApplyGrant
from forge.genesis_bootstrap_grant import GenesisBootstrapGrant


class GenesisApplyGrantTests(unittest.TestCase):
    def setUp(self):
        self.owner = bootstrap_tests.GenesisBootstrapHttpTest(); self.addCleanup(self.owner.doCleanups); self.owner.setUp()
        self.owner.approve_content(); _, self.view = self.owner.prepare()
        self.owner.effect_grant(self.view)
        status, self.view = self.owner.call('POST', BASE+'/decisions', self.owner.effect(self.view), token='effect')
        self.assertEqual(status, 200, self.view)
        self.grant = GenesisApplyGrant(self.owner.root/'runtime', self.owner.setup['instance_id'])
        self.grant.initialize()

    def issue(self, **updates):
        return self.grant.issue(**dict(principal_id=self.owner.setup['human_principal_id'], audience='synthetic-workspace',
            proposal_principal_id='synthetic-service', dossier_ids=['synthetic-dossier'], source_plan_ids=[self.owner.source['plan_id']],
            permissions=['READ', 'REQUEST_APPLY', 'RESUME'],
            exact_plans=[{'plan_id': self.view['plan']['plan_id'], 'plan_digest': self.view['plan']['plan_digest']}],
            expires_at=self.owner.expiry, token_path=self.owner.root/'apply.private', **updates))

    def test_separate_purpose_exact_current_owner_plan_and_revoke(self):
        issued = self.issue()
        auth = 'Bearer '+(self.owner.root/'apply.private').read_text().strip()
        principal = self.grant.authorize(auth, audience='synthetic-workspace', dossier_id='synthetic-dossier', permission='REQUEST_APPLY', plan=self.view['plan'])
        self.assertEqual(principal.grant_id, issued['grant_id'])
        self.assertEqual(principal.purpose, 'GENESIS_APPLY_ONLY/1.0')
        with self.assertRaises(PermissionError): self.grant.authorize(auth, permission='REQUEST_APPLY', plan={**self.view['plan'], 'plan_digest':'f'*64})
        with self.assertRaises(PermissionError): GenesisBootstrapGrant(self.grant.root,self.grant.instance_id).authorize(auth)
        old = 'Bearer '+(self.owner.root/'effect.private').read_text().strip()
        with self.assertRaises(PermissionError): self.grant.authorize(old)
        self.grant.revoke(issued['grant_id'])
        with self.assertRaises(PermissionError): self.grant.authorize(auth)

    def test_rejects_foreign_sources_unfrozen_plan_permissions_and_credential_destination(self):
        base = dict(principal_id=self.owner.setup['human_principal_id'], audience='synthetic-workspace', proposal_principal_id='synthetic-service',
                    dossier_ids=['synthetic-dossier'], source_plan_ids=[self.owner.source['plan_id']], permissions=['READ','REQUEST_APPLY'],
                    exact_plans=[{'plan_id': self.view['plan']['plan_id'], 'plan_digest': self.view['plan']['plan_digest']}],
                    expires_at=self.owner.expiry, token_path=self.owner.root/'apply.private')
        for updates in ({'source_plan_ids':['foreign']}, {'exact_plans':[{'plan_id':'foreign','plan_digest':'f'*64}]},
                        {'permissions':['READ','DECIDE_EFFECT']}, {'permissions':['READ','REQUEST_APPLY'],'exact_plans':[]},
                        {'principal_id':'synthetic-service'}, {'token_path':self.grant.root/'overwrite'},
                        {'expires_at':(datetime.now(UTC)-timedelta(seconds=1)).isoformat()}):
            with self.subTest(updates=updates),self.assertRaises((ValueError,PermissionError)):
                self.grant.issue(**{**base,**updates})
        self.assertFalse((self.owner.root/'apply.private').exists())
