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


class InstallationPeerPortableStorageTest(unittest.TestCase):
    """Portable unit tests of canonical storage; not native identity qualification."""
    def setUp(self):
        from forge.operator_identity import NamedOperatorIdentity
        from unittest.mock import patch
        import os,uuid
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'installation'
        self.identity=NamedOperatorIdentity(str(uuid.uuid4()),os.getuid())
        database=RuntimeBootstrap(data_root=self.root,forge_version='test').open()
        self.runtime=database.runtime_identity.runtime_id
        InstallationOperatorService(database,lambda:self.identity).first_bind();database.close()
        self.native=patch('forge.operator_identity.MacOSGeneratedUIDIdentityAdapter.resolve',return_value=self.identity)
        self.native.start();self.addCleanup(self.native.stop)
        self.service=InstallationPairingService(self.root)
        self.values=dict(operation_id='configure-one',binding_id='binding',endpoint='https://example.com',
                         ep_instance_id='ep-instance',consumer_id='forge',credential_reference='keychain://service/item')

    def tearDown(self):self.temp.cleanup()

    def test_exact_replay_and_changed_target_rejection(self):
        result=self.service.configure(**self.values)
        self.assertEqual(self.service.configure(**self.values),result)
        self.assertEqual(self.service.show(),result)
        with self.assertRaises(InstallationPairingError):
            self.service.configure(**dict(self.values,ep_instance_id='foreign'))
        with self.assertRaises(InstallationPairingError):
            self.service.configure(**dict(self.values,operation_id='invalid operation'))

    def test_missing_peer_cannot_preflight(self):
        self.assertEqual(self.service.show()['status'],'NOT_CONFIGURED')
        with self.assertRaises(InstallationPairingError):self.service.preflight()

    def test_corrupt_or_foreign_runtime_binding_cannot_preflight(self):
        from hashlib import sha256
        import json
        result=self.service.configure(**self.values)
        document=dict(result['configuration'],forge_instance_id='foreign')
        raw=json.dumps(document,sort_keys=True,separators=(',',':'))
        with sqlite3.connect(self.root/'forge.db') as connection:
            connection.execute('UPDATE installation_peer_configuration SET document=?,document_digest=?',(raw,'sha256:'+sha256(raw.encode()).hexdigest()))
        with self.assertRaises(InstallationPairingError):self.service.show()
        with sqlite3.connect(self.root/'forge.db') as connection:
            connection.execute("UPDATE installation_peer_configuration SET document_digest='corrupt'")
        with self.assertRaises(InstallationPairingError):self.service.show()

    def test_bound_operator_is_required(self):
        from unittest.mock import patch
        from forge.operator_identity import NamedOperatorIdentity
        with patch('forge.operator_identity.MacOSGeneratedUIDIdentityAdapter.resolve',return_value=NamedOperatorIdentity('other',self.identity.uid)):
            with self.assertRaises(PermissionError):self.service.configure(**self.values)
        with sqlite3.connect(self.root/'forge.db') as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM installation_peer_configuration').fetchone()[0],0)

    def test_preflight_returns_transport_readback_digest(self):
        from unittest.mock import patch
        self.service.configure(**self.values)
        with patch('forge.installation_pairing.check_installation_peer',return_value=dict(status='CONNECTED',execution_ready=False)):
            result=self.service.preflight()
        self.assertEqual(result['status'],'CONNECTED');self.assertFalse(result['execution_ready'])
        self.assertEqual(result['configuration_digest'],self.service.show()['configuration_digest'])


class InstallationReadbackUnitTest(unittest.TestCase):
    """Negative transport/schema vectors; separate real producer test remains required."""
    def setUp(self):
        self.peer=InstallationPeer('binding','https://example.com','ep','forge','consumer','keychain://service/item')
        self.document=dict(contract_version='1.0',producer=dict(id='engineering-platform',version='candidate'),
            instance=dict(id='ep'),authentication=dict(binding_id='binding',ep_instance_id='ep',forge_instance_id='forge',consumer_id='consumer',purpose='INSTALLATION_READBACK'),
            authority=dict(installation_readback=True,project_access=False,submission=False,execution=False,governance=False))

    def check(self,document=None,*,raw=None,status=200,instance='ep',error=None):
        import json
        from unittest.mock import MagicMock,patch
        from forge.installation_pairing import _InstallationReadback
        response=MagicMock();response.status=status;response.headers={'EP-Server-Instance':instance}
        response.read.return_value=raw if raw is not None else json.dumps(document if document is not None else self.document).encode()
        opener=MagicMock()
        if error:opener.open.side_effect=error
        else:opener.open.return_value.__enter__.return_value=response
        with patch('forge.installation_pairing.build_opener',return_value=opener):
            result=_InstallationReadback(self.peer,'unit-test-only').check()
        request=opener.open.call_args.args[0]
        self.assertIsNone(request.get_header('Ep-project-id'))
        self.assertEqual(request.full_url,'https://example.com/v1/installation-compatibility')
        return result

    def test_connected_readback_never_authorizes_execution(self):
        result=self.check();self.assertFalse(result['execution_ready']);self.assertFalse(result['project_authorized'])

    def test_transport_and_bounds_fail_closed(self):
        from urllib.error import HTTPError,URLError
        import io
        for kwargs in (dict(status=503),dict(instance='foreign'),dict(raw=b'x'*32769),dict(raw=b'{broken'),
                       dict(error=URLError('unavailable')),dict(error=HTTPError('https://example.com',401,'unauthorized',{},io.BytesIO(b'')))):
            with self.subTest(kwargs=tuple(kwargs)),self.assertRaises(InstallationPairingError):self.check(**kwargs)

    def test_unsupported_or_excess_authority_is_rejected(self):
        for update in (dict(contract_version='other'),dict(instance={'id':'foreign'}),dict(authentication={}),
                       dict(authority=dict(self.document['authority'],execution=True)),dict(producer={'id':'foreign','version':'candidate'})):
            with self.assertRaises(InstallationPairingError):self.check(dict(self.document,**update))

    def test_normal_secure_store_boundary_is_required(self):
        from unittest.mock import patch
        from forge.installation_pairing import check_installation_peer,_NoRedirect
        from forge.secure_store import SecretState
        with self.assertRaises(InstallationPairingError):check_installation_peer(None)
        with patch('forge.installation_pairing.MacOSKeychainSecureStoreAdapter') as adapter:
            adapter.return_value.resolve.return_value=(SecretState.MISSING,None)
            with self.assertRaises(InstallationPairingError):check_installation_peer(self.peer)
            adapter.return_value.resolve.return_value=(SecretState.RESOLVABLE,'unit-test-only')
            with patch('forge.installation_pairing._InstallationReadback.check',return_value={'status':'CONNECTED'}):
                self.assertEqual(check_installation_peer(self.peer)['status'],'CONNECTED')
        self.assertIsNone(_NoRedirect().redirect_request(None,None,302,'redirect',{},'https://foreign.example'))

    def test_invalid_identity_and_transport_types_are_rejected(self):
        for changes in (dict(binding_id=''),dict(allow_loopback_http='yes'),dict(timeout_seconds=float('nan'))):
            with self.assertRaises(InstallationPairingError):replace(self.peer,**changes)


class InstallationCLIUnitTest(unittest.TestCase):
    def test_cli_routes_and_safe_failure(self):
        import io,json
        from contextlib import redirect_stdout,redirect_stderr
        from unittest.mock import patch
        from forge.__main__ import main
        commands=[['show'],['preflight'],['configure','--operation-id','configure','--binding-id','binding',
           '--endpoint','https://example.com','--expected-instance-id','ep','--consumer-id','forge','--credential-reference','keychain://service/item']]
        for command in commands:
            with patch('forge.installation_pairing.InstallationPairingService') as service:
                for method in ('show','preflight','configure'):getattr(service.return_value,method).return_value={'status':'UNIT_SOURCE_ONLY'}
                with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):main(['installation-peer',*command])
                getattr(service.return_value,command[0]).assert_called_once()
        with patch('forge.installation_pairing.InstallationPairingService') as service:
            service.return_value.show.side_effect=InstallationPairingError('private detail')
            stdout,stderr=io.StringIO(),io.StringIO()
            with redirect_stdout(stdout),redirect_stderr(stderr):code=main(['installation-peer','show'])
            self.assertEqual(code,1);self.assertNotIn('private detail',stdout.getvalue()+stderr.getvalue())
