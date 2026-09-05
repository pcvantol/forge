import tempfile,unittest
from pathlib import Path
from forge.runtime.database import RuntimeDatabase
from forge.operator_identity import InstallationOperatorService,MacOSGeneratedUIDIdentityAdapter,NamedOperatorIdentity
class T(unittest.TestCase):
 def test_trusted_binding_rejects_strings_wrong_and_revoked(self):
  with tempfile.TemporaryDirectory() as d:
   current=[NamedOperatorIdentity('generated-a',501)]; db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); svc=InstallationOperatorService(db,lambda:current[0]); ctx=svc.first_bind('t')
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
   db=RuntimeDatabase(root,path=path); context=InstallationOperatorService(db,lambda:identity).first_bind('t'); db.close()
   reopened=RuntimeDatabase(root,path=path); service=InstallationOperatorService(reopened,lambda:identity)
   self.assertTrue(service.authorize(context));self.assertFalse(service.authorize('generated-a'));reopened.close()
