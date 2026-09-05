import tempfile
import unittest
from pathlib import Path
from forge.runtime.database import RuntimeDatabase
from forge.provider_security import PlanningProviderSecurityService, SecretReference, SecretState

class Store:
 def __init__(self, state=SecretState.RESOLVABLE): self.state=state
 def status(self, reference): return self.state

class ProviderSecurityTests(unittest.TestCase):
 def test_reference_only_and_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); store=Store(); svc=PlanningProviderSecurityService(db,store)
   result=svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('os-keychain','planning-key'),operator_id='operator',occurred_at='2026-09-05T00:00:00Z')
   self.assertTrue(result['ready']); self.assertEqual(result['secret_reference'],'[REDACTED]')
   store.state=SecretState.REVOKED; self.assertFalse(svc.inspect('planning')['ready'])
   self.assertRaises(ValueError, SecretReference,'os','sk-secret')
 def test_stale_write_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   db=RuntimeDatabase(Path(d),path=Path(d)/'runtime.db'); svc=PlanningProviderSecurityService(db,Store())
   svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('os','id'),operator_id='operator',occurred_at='x')
   with self.assertRaises(ValueError): svc.configure(configuration_id='cfg',provider_id='planning',reference=SecretReference('os','id2'),operator_id='operator',occurred_at='x')
