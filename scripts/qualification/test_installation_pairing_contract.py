"""Real HTTP producer/consumer source tests; not installed qualification."""
from pathlib import Path
import http.server
import tempfile
import threading
import unittest

from engineering_platform import installation_pairing as ep_pairing, server, storage
from forge.installation_pairing import InstallationPeer, InstallationPairingError, _InstallationReadback


class InstallationPairingContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ep_id = server.initialize(self.root).instance_id
        with storage.sqlite_connection(self.root/server.SERVER_DATABASE_FILENAME) as connection:
            ep_pairing.register(connection,binding_id='binding-one',ep_instance_id=self.ep_id,
                                forge_instance_id='forge-instance',consumer_id='forge',operation_id='register-one')
            self.issued = ep_pairing.issue(connection,binding_id='binding-one',operation_id='issue-one')
        self.http = http.server.ThreadingHTTPServer(('127.0.0.1',0),server._HealthHandler)
        self.http.data_root=self.root
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.peer=InstallationPeer('binding-one','http://127.0.0.1:'+str(self.http.server_port),self.ep_id,
                                   'forge-instance','forge','keychain://installation-pairing/test',True)

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join();self.temp.cleanup()

    def test_real_project_free_http_does_not_claim_execution(self):
        result=_InstallationReadback(self.peer,self.issued.credential).check()
        self.assertEqual(result['status'],'CONNECTED')
        self.assertIs(result['project_authorized'],False)
        self.assertIs(result['execution_ready'],False)
        self.assertNotIn(self.issued.credential,repr(result))
        self.assertNotIn(self.issued.credential,repr(_InstallationReadback(self.peer,self.issued.credential)))
        self.assertFalse(hasattr(_InstallationReadback(self.peer,self.issued.credential),'dispatch'))

    def test_foreign_instance_is_rejected(self):
        from dataclasses import replace
        wrong=replace(self.peer,forge_instance_id='other')
        with self.assertRaisesRegex(InstallationPairingError,'403'):
            _InstallationReadback(wrong,self.issued.credential).check()

    def test_revoked_credential_is_rejected(self):
        with storage.sqlite_connection(self.root/server.SERVER_DATABASE_FILENAME) as connection:
            ep_pairing.revoke_credential(connection,binding_id='binding-one',credential_id=self.issued.credential_id,operation_id='revoke-one')
        with self.assertRaisesRegex(InstallationPairingError,'401'):
            _InstallationReadback(self.peer,self.issued.credential).check()

    def test_non_loopback_cleartext_transport_is_rejected(self):
        from dataclasses import replace
        with self.assertRaises(InstallationPairingError):
            replace(self.peer,endpoint='http://example.com')
        with self.assertRaises(InstallationPairingError):
            replace(self.peer,timeout_seconds=float('nan'))

if __name__=='__main__':unittest.main()
