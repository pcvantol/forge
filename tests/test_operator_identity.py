import os,shutil,sqlite3,tempfile,unittest
from pathlib import Path
from forge.runtime.database import RuntimeDatabase,RuntimeIntegrityError
from forge.operator_identity import InstallationOperatorService,MacOSGeneratedUIDIdentityAdapter,NamedOperatorIdentity
class T(unittest.TestCase):
 def test_trusted_binding_rejects_strings_wrong_and_revoked(self):
  with tempfile.TemporaryDirectory() as d:
   current=[NamedOperatorIdentity('generated-a',501)]; db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); svc=InstallationOperatorService(db,lambda:current[0],lambda:'2026-01-01T00:00:00Z'); ctx=svc.first_bind()
   self.assertTrue(svc.authorize(ctx));self.assertFalse(svc.authorize('generated-a'))
   current[0]=NamedOperatorIdentity('generated-b',502);self.assertFalse(svc.authorize(ctx));current[0]=NamedOperatorIdentity('generated-a',501);svc.revoke(ctx);self.assertFalse(svc.authorize(ctx))
 def test_macos_generated_uid_adapter_parses_dscl_label(self):
  class Result:
   returncode=0
   stdout='GeneratedUID: 123E4567-E89B-42D3-A456-426614174000'
  adapter=MacOSGeneratedUIDIdentityAdapter(runner=lambda *args,**kwargs:Result())
  from unittest.mock import patch
  with patch('forge.operator_identity.os.getuid',return_value=501),patch('forge.operator_identity.pwd.getpwuid',return_value=type('P',(),{'pw_name':'operator'})()):
   self.assertEqual(adapter.resolve(),NamedOperatorIdentity('123e4567-e89b-42d3-a456-426614174000',501))
 def test_restart_retains_binding_but_not_caller_string_authority(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); path=root/'runtime.db'; identity=NamedOperatorIdentity('generated-a',501)
   db=RuntimeDatabase(root,path=path); context=InstallationOperatorService(db,lambda:identity,lambda:'2026-01-01T00:00:00Z').first_bind(); db.close()
   reopened=RuntimeDatabase(root,path=path); service=InstallationOperatorService(reopened,lambda:identity)
   self.assertTrue(service.authorize(context));self.assertFalse(service.authorize('generated-a'));reopened.close()
 def test_clone_fails_closed_for_a_different_runtime_root(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); source=root/'source'; clone=root/'clone'; source.mkdir();clone.mkdir(); path=source/'runtime.db'
   db=RuntimeDatabase(source,path=path); InstallationOperatorService(db,lambda:NamedOperatorIdentity('generated-a',501),lambda:'2026-01-01T00:00:00Z').first_bind(); db.close()
   shutil.copy2(path,clone/'runtime.db')
   with self.assertRaises(RuntimeIntegrityError): RuntimeDatabase(clone,path=clone/'runtime.db')
 def test_environment_cannot_change_trusted_identity(self):
  class Result: returncode=0; stdout='GeneratedUID: 123E4567-E89B-42D3-A456-426614174000'
  adapter=MacOSGeneratedUIDIdentityAdapter(runner=lambda *args,**kwargs:Result())
  from unittest.mock import patch
  with patch('forge.operator_identity.os.getuid',return_value=501),patch('forge.operator_identity.pwd.getpwuid',return_value=type('P',(),{'pw_name':'operator'})()),patch.dict(os.environ,{'USER':'forged','LOGNAME':'forged','HOME':'/forged','PWD':'/forged'}):
   self.assertEqual(adapter.resolve().generated_uid,'123e4567-e89b-42d3-a456-426614174000')
 def test_audit_is_append_only_and_survives_restart(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); path=root/'runtime.db'; identity=NamedOperatorIdentity('generated-a',501); db=RuntimeDatabase(root,path=path); service=InstallationOperatorService(db,lambda:identity,lambda:'2026-01-01T00:00:00Z'); context=service.first_bind(); service.revoke(context)
   rows=db._connection.execute('SELECT * FROM installation_operator_audit ORDER BY operation').fetchall(); self.assertEqual([row['operation'] for row in rows],['FIRST_BIND','REVOKE']); self.assertTrue(rows[1]['occurred_at'].endswith('Z'))
   with self.assertRaises(sqlite3.DatabaseError): db._connection.execute("UPDATE installation_operator_audit SET result='FORGED'")
   with self.assertRaises(sqlite3.DatabaseError): db._connection.execute('DELETE FROM installation_operator_audit')
   db.close(); reopened=RuntimeDatabase(root,path=path); self.assertEqual(reopened._connection.execute('SELECT COUNT(*) FROM installation_operator_audit').fetchone()[0],2); reopened.close()
 def test_v16_audit_rows_are_preserved_when_immutability_migrates(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); path=root/'runtime.db'; db=RuntimeDatabase(root,path=path); db._connection.execute('DROP TRIGGER installation_operator_audit_immutable_update'); db._connection.execute('DROP TRIGGER installation_operator_audit_immutable_delete'); db._connection.execute("INSERT INTO installation_operator_audit VALUES ('legacy','installation','fingerprint','FIRST_BIND','2026-01-01T00:00:00Z','ALLOW')"); db._set_metadata({'schema_version':'16','migration_version':'16','last_migration':'16'}); db._connection.execute('PRAGMA user_version=16'); db._connection.commit(); db.close()
   reopened=RuntimeDatabase(root,path=path); self.assertEqual(reopened._connection.execute("SELECT operation FROM installation_operator_audit WHERE audit_id='legacy'").fetchone()[0],'FIRST_BIND');
   with self.assertRaises(sqlite3.DatabaseError): reopened._connection.execute("DELETE FROM installation_operator_audit WHERE audit_id='legacy'")
   reopened.close()
 def test_first_bind_uses_only_the_trusted_clock(self):
  with tempfile.TemporaryDirectory() as d:
   db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); service=InstallationOperatorService(db,lambda:NamedOperatorIdentity('generated-a',501),lambda:'2042-02-03T04:05:06Z')
   with self.assertRaises(TypeError): service.first_bind('1900-01-01T00:00:00Z')
   service.first_bind(); row=db._connection.execute("SELECT occurred_at FROM installation_operator_audit WHERE operation='FIRST_BIND'").fetchone(); self.assertEqual(row[0],'2042-02-03T04:05:06Z'); db.close()
