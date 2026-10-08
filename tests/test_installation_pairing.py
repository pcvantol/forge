"""Installation storage and authority tests; no real credentials or providers."""
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from forge.installation_pairing import InstallationPeer, InstallationPairingError, InstallationPairingService
from forge.operator_identity import InstallationOperatorService, MacOSGeneratedUIDIdentityAdapter
from forge.runtime.bootstrap import RuntimeBootstrap


class InstallationPeerBoundaryTest(unittest.TestCase):
    def test_project_fields_are_not_configuration_or_dispatch_authority(self):
        self.assertNotIn('project_id',InstallationPeer.__dataclass_fields__)
        self.assertNotIn('repository_id',InstallationPeer.__dataclass_fields__)
        self.assertFalse(hasattr(InstallationPairingService,'dispatch'))
        with self.assertRaises(TypeError):
            InstallationPeer('binding','https://example.com','ep','forge','consumer','keychain://service/item',project_id='project')

    def test_non_loopback_cleartext_and_credential_in_url_are_rejected(self):
        for endpoint in ('http://example.com','https://user:password@example.com'):
            with self.assertRaises(InstallationPairingError):
                InstallationPeer('binding',endpoint,'ep','forge','consumer','keychain://service/item',True)


@unittest.skipUnless(sys.platform=='darwin','Requires actual macOS named operator identity')
class InstallationPeerStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'installation'
        database=RuntimeBootstrap(data_root=self.root,forge_version='test').open()
        self.runtime=database.runtime_identity.runtime_id
        self.operator=InstallationOperatorService(database,MacOSGeneratedUIDIdentityAdapter().resolve)
        self.operator.first_bind()
        database.close()
        self.service=InstallationPairingService(self.root)
        self.values=dict(operation_id='configure-one',binding_id='binding',endpoint='https://example.com',
                         ep_instance_id='ep-instance',consumer_id='forge',credential_reference='keychain://service/item')

    def tearDown(self): self.temp.cleanup()

    def test_exact_replay_has_one_durable_event_and_no_project_peer(self):
        result=self.service.configure(**self.values)
        self.assertEqual(self.service.configure(**self.values),result)
        self.assertEqual(self.service.show(),result)
        self.assertFalse(result['execution_ready'])
        self.assertEqual(result['configuration']['forge_instance_id'],self.runtime)
        with sqlite3.connect(self.root/'forge.db') as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM execution_host_peer_configuration').fetchone()[0],0)
            self.assertEqual(connection.execute("SELECT count(*) FROM forge_operational_logs WHERE event='installation_pairing_configured'").fetchone()[0],1)

    def test_changed_replay_is_rejected(self):
        self.service.configure(**self.values)
        for key,value in (('ep_instance_id','foreign'),('operation_id','other'),('credential_reference','keychain://service/other')):
            with self.assertRaisesRegex(InstallationPairingError,'REPLACEMENT_REQUIRES_SEPARATE_REVIEW'):
                self.service.configure(**dict(self.values,**{key:value}))
        self.assertEqual(self.service.show()['configuration']['ep_instance_id'],'ep-instance')

    def test_corrupt_configuration_cannot_preflight(self):
        self.service.configure(**self.values)
        with sqlite3.connect(self.root/'forge.db') as connection:
            connection.execute("UPDATE installation_peer_configuration SET document_digest='corrupt'")
        with self.assertRaisesRegex(InstallationPairingError,'CORRUPT'):
            self.service.show()

if __name__=='__main__':unittest.main()
