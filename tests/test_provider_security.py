import sqlite3,tempfile
import unittest
from pathlib import Path
from forge.runtime.database import RuntimeDatabase
from forge.provider_security import PlanningProviderSecurityService, SecretReference, SecretState, MacOSKeychainSecureStoreAdapter
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity

class Store:
 def __init__(self, state=SecretState.RESOLVABLE): self.state=state
 def status(self, reference): return self.state

class ProviderSecurityTests(unittest.TestCase):
 def _operator(self, db):
  service=InstallationOperatorService(db,lambda:NamedOperatorIdentity('generated-a',501)); return service,service.first_bind()
 def test_reference_only_and_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); store=Store(); operator,context=self._operator(db); svc=PlanningProviderSecurityService(db,store,operator)
   result=svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('keychain','//planning-key/account'),operator_context=context)
   self.assertTrue(result['ready']); self.assertEqual(result['secret_reference'],'[REDACTED]')
   store.state=SecretState.REVOKED; self.assertFalse(svc.inspect('planning')['ready'])
   self.assertRaises(ValueError, SecretReference,'os','sk-secret')
 def test_stale_write_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); operator,context=self._operator(db); svc=PlanningProviderSecurityService(db,Store(),operator)
   svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('keychain','//service/id'),operator_context=context)
   with self.assertRaises(ValueError): svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('keychain','//service/id2'),operator_context=context)
 def test_raw_operator_strings_and_revoked_context_are_denied(self):
  with tempfile.TemporaryDirectory() as d:
   db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); operator,context=self._operator(db); svc=PlanningProviderSecurityService(db,Store(),operator)
   with self.assertRaises(PermissionError): svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('keychain','//service/id'),operator_context='operator')
   operator.revoke(context)
   with self.assertRaises(PermissionError): svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('keychain','//service/id'),operator_context=context)
 def test_rotation_restart_redaction_and_audit_immutability(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); path=root/'runtime.db'; secret_a='G011_SYNTHETIC_A'; secret_b='G011_SYNTHETIC_B'; db=RuntimeDatabase(root,path=path); operator,context=self._operator(db); store=Store(); svc=PlanningProviderSecurityService(db,store,operator)
   first=svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('keychain','//service/account-a'),operator_context=context)
   second=svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('keychain','//service/account-b'),operator_context=context,expected_version=first['version'])
   self.assertEqual(second['version'],2)
   with self.assertRaises(ValueError): svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('keychain','//service/account-c'),operator_context=context,expected_version=1)
   evidence=' '.join(str(tuple(row)) for row in db._connection.execute('SELECT * FROM planning_provider_security_config')) + ' ' + ' '.join(str(tuple(row)) for row in db._connection.execute('SELECT * FROM planning_provider_security_audit'))
   self.assertNotIn(secret_a,evidence); self.assertNotIn(secret_b,evidence); self.assertNotIn('account-b',second['secret_reference'])
   with self.assertRaises(sqlite3.DatabaseError): db._connection.execute('DELETE FROM planning_provider_security_audit')
   db.close(); reopened=RuntimeDatabase(root,path=path); restart=PlanningProviderSecurityService(reopened,store,InstallationOperatorService(reopened,lambda:NamedOperatorIdentity('generated-a',501)))
   self.assertTrue(restart.inspect('planning')['ready']); store.state=SecretState.REVOKED; self.assertFalse(restart.inspect('planning')['ready']); reopened.close()
 def test_keychain_reference_matrix_fails_closed(self):
  adapter=MacOSKeychainSecureStoreAdapter(runner=lambda *args,**kwargs: (_ for _ in ()).throw(OSError()))
  self.assertEqual(adapter.status(SecretReference('keychain','//service/account')),SecretState.STORE_UNAVAILABLE)
  for scheme,identifier in (('keychain','//service/account?namespace=x&namespace=y'),('keychain','//service'),('other','//service/account')):
   with self.assertRaises(ValueError): SecretReference(scheme,identifier)
 def test_secret_bearing_or_unknown_references_are_rejected_before_persistence(self):
  rejected=('unknown://service/account','env://service/account','file://service/account','keychain://user@service/account','keychain://user:password@service/account','keychain://service:123/account','keychain://service/account/extra','keychain://service/account#G011_FRAGMENT_SECRET','keychain://service/account?namespace=x#G011_FRAGMENT_SECRET','keychain://service/account?password=G011_REJECTED_SECRET','keychain://service/account?token=G011_REJECTED_SECRET','keychain://service/account?api_key=G011_REJECTED_SECRET','keychain://service/account?secret=G011_REJECTED_SECRET','keychain://service/account?namespace=x&namespace=y','keychain://service/%2Faccount','keychain://service%40evil/account')
  with tempfile.TemporaryDirectory() as d:
   db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); operator,context=self._operator(db); svc=PlanningProviderSecurityService(db,Store(),operator)
   before_config=db._connection.execute('SELECT COUNT(*) FROM planning_provider_security_config').fetchone()[0]
   before_audit=db._connection.execute('SELECT COUNT(*) FROM planning_provider_security_audit').fetchone()[0]
   for value in rejected:
    scheme,identifier=value.split(':',1)
    with self.assertRaises(ValueError) as error: svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference(scheme,identifier),operator_context=context)
    self.assertNotIn('G011_REJECTED_SECRET',str(error.exception))
   forged=object.__new__(SecretReference)
   object.__setattr__(forged,'scheme','keychain')
   object.__setattr__(forged,'identifier','//service/account?secret=G011_REJECTED_SECRET')
   with self.assertRaises(ValueError): svc.configure(configuration_id='cfg',provider_id='planning',reference=forged,operator_context=context)
   self.assertEqual(before_config,db._connection.execute('SELECT COUNT(*) FROM planning_provider_security_config').fetchone()[0])
   self.assertEqual(before_audit,db._connection.execute('SELECT COUNT(*) FROM planning_provider_security_audit').fetchone()[0])
   evidence=' '.join(str(row) for row in db._connection.execute('SELECT * FROM planning_provider_security_audit'))
   self.assertNotIn('G011_REJECTED_SECRET',evidence)
   self.assertNotIn('G011_FRAGMENT_SECRET',evidence)
 def test_reference_serialization_is_canonical(self):
  reference=SecretReference('keychain','//service/account?version=v2&namespace=n1')
  self.assertEqual(reference.serialized,'keychain://service/account?namespace=n1&version=v2')
  self.assertEqual(reference.identifier,'//service/account?namespace=n1&version=v2')
 def test_keychain_adapter_uses_explicit_argv_and_redacts_failures(self):
  calls=[]
  class Result:
   def __init__(self, rc, out='', err=''): self.returncode,self.stdout,self.stderr=rc,out,err
  def runner(argv, **kwargs): calls.append((argv,kwargs)); return Result(0,'synthetic-secret\n')
  adapter=MacOSKeychainSecureStoreAdapter(runner)
  state, material=adapter.resolve(SecretReference('keychain','//forge.test/account?namespace=n1'))
  self.assertEqual(state,SecretState.RESOLVABLE); self.assertEqual(material,'synthetic-secret')
  self.assertEqual(calls[0][0],['/usr/bin/security','find-generic-password','-s','forge.test','-a','account','-w'])
  self.assertTrue(calls[0][1]['capture_output']); self.assertNotIn('synthetic-secret', repr(calls))
  self.assertEqual(adapter.status(SecretReference('keychain','//missing/account')),SecretState.RESOLVABLE)
  with self.assertRaises(ValueError): SecretReference('keychain','//bad')
