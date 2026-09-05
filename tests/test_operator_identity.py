import tempfile,unittest
from pathlib import Path
from forge.runtime.database import RuntimeDatabase
from forge.operator_identity import InstallationOperatorService,NamedOperatorIdentity
class T(unittest.TestCase):
 def test_trusted_binding_rejects_strings_wrong_and_revoked(self):
  with tempfile.TemporaryDirectory() as d:
   current=[NamedOperatorIdentity('generated-a',501)]; db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); svc=InstallationOperatorService(db,lambda:current[0]); ctx=svc.first_bind('t')
   self.assertTrue(svc.authorize(ctx));self.assertFalse(svc.authorize('generated-a'))
   current[0]=NamedOperatorIdentity('generated-b',502);self.assertFalse(svc.authorize(ctx));current[0]=NamedOperatorIdentity('generated-a',501);svc.revoke(ctx);self.assertFalse(svc.authorize(ctx))
