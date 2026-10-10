"""Real canonical storage and public entrypoints for own-installation detach."""
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

from forge.installation_pairing import InstallationPairingService, InstallationPairingError
from forge.operator_identity import InstallationOperatorService, NamedOperatorIdentity
from forge.runtime.bootstrap import RuntimeBootstrap
from forge.runtime.service import RuntimeServiceLock, RuntimeServiceBusy


class InstallationDetachTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'installation'
        self.identity = NamedOperatorIdentity(str(uuid.uuid4()), os.getuid())
        db = RuntimeBootstrap(data_root=self.root, forge_version='test').open()
        self.runtime = db.runtime_identity.runtime_id
        self.context = InstallationOperatorService(db, lambda: self.identity).first_bind()
        db.close()
        from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter
        self.original_native_resolver = MacOSGeneratedUIDIdentityAdapter.resolve
        native = patch('forge.operator_identity.MacOSGeneratedUIDIdentityAdapter.resolve', return_value=self.identity)
        native.start(); self.addCleanup(native.stop)
        self.service = InstallationPairingService(self.root)
        self.configure = dict(operation_id='configure-one', binding_id='binding', endpoint='https://example.com',
                              ep_instance_id='ep', consumer_id='consumer', credential_reference='keychain://service/item')
        self.before = self.service.configure(**self.configure)
        self.request = dict(operation_id='detach-one', expected_binding_id='binding', expected_configuration_revision=1)

    def snapshot(self):
        with sqlite3.connect(self.root/'forge.db') as c:
            return '\n'.join(c.iterdump())

    def test_atomic_receipt_restart_exact_retry_and_read_only_status(self):
        with patch('forge.installation_pairing.MacOSKeychainSecureStoreAdapter', side_effect=AssertionError('must not resolve credentials')):
            receipt = self.service.detach(**self.request)
            restarted = InstallationPairingService(self.root)
            self.assertEqual(restarted.detach(**self.request), receipt)
            before_status = self.snapshot()
            self.assertEqual(restarted.detach_status('detach-one'), receipt)
            self.assertEqual(self.snapshot(), before_status)
        self.assertEqual(receipt['runtime_id'], self.runtime)
        self.assertEqual(receipt['installation_id'], self.context.installation_id)
        self.assertEqual(receipt['configuration_revision'], 2)
        self.assertEqual(receipt['previous_configuration_digest'], self.before['configuration_digest'])
        value = dict(receipt); digest = value.pop('receipt_digest')
        self.assertEqual(digest, 'sha256:'+sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest())
        self.assertNotIn('credential', json.dumps(receipt))
        self.assertEqual(self.service.show(), dict(status='NOT_CONFIGURED', configuration_revision=2, execution_ready=False))
        with sqlite3.connect(self.root/'forge.db') as c:
            self.assertEqual(c.execute("SELECT count(*) FROM forge_operational_logs WHERE event='installation_pairing_detached'").fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT count(*) FROM execution_host_peer_configuration').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM mission_state').fetchone()[0], 0)

    def test_stale_conflicting_missing_and_invalid_requests_preserve_binding(self):
        for change in ({'expected_binding_id':'foreign'}, {'expected_configuration_revision':2},
                       {'expected_configuration_revision':True}, {'expected_configuration_revision':0},
                       {'operation_id':'invalid/id'}, {'expected_binding_id':''}, {'operator_id':'fake'},
                       {'operation_id':'configure-one'}):
            with self.subTest(change=change):
                with self.assertRaises(InstallationPairingError): self.service.detach(**dict(self.request, **change))
                self.assertEqual(self.service.show(), self.before)
        with self.assertRaises(InstallationPairingError): self.service.detach_status('missing')
        with self.assertRaises(InstallationPairingError): self.service.detach_status('invalid/id')
        receipt = self.service.detach(**self.request)
        for change in ({'expected_binding_id':'foreign'}, {'expected_configuration_revision':2}):
            with self.assertRaises(InstallationPairingError): self.service.detach(**dict(self.request, **change))
        with self.assertRaises(InstallationPairingError): self.service.detach(**dict(self.request, operation_id='other'))
        self.assertEqual(self.service.detach_status('detach-one'), receipt)

    def test_reconfigure_advances_generation_and_old_receipt_never_detaches_new_binding(self):
        old = self.service.detach(**self.request)
        with self.assertRaises(InstallationPairingError): self.service.configure(**dict(self.configure, operation_id='detach-one'))
        new = self.service.configure(**dict(self.configure, operation_id='configure-two'))
        self.assertEqual(new['configuration_revision'], 3)
        self.assertEqual(self.service.detach(**self.request), old)
        self.assertEqual(self.service.detach_status('detach-one'), old)
        self.assertEqual(self.service.show(), new)
        with self.assertRaises(InstallationPairingError): self.service.detach(**dict(self.request, operation_id='detach-two'))
        second = self.service.detach(**dict(self.request, operation_id='detach-two', expected_configuration_revision=3))
        self.assertEqual(second['configuration_revision'], 4)

    def test_real_operator_foreign_or_revoked_fails_closed(self):
        for identity in (NamedOperatorIdentity(str(uuid.uuid4()), os.getuid()), NamedOperatorIdentity(self.identity.generated_uid, os.getuid()+1)):
            with patch('forge.operator_identity.MacOSGeneratedUIDIdentityAdapter.resolve', return_value=identity):
                with self.assertRaises(PermissionError): self.service.detach(**self.request)
        receipt = self.service.detach(**self.request)
        db = RuntimeBootstrap(data_root=self.root, forge_version='test').open()
        InstallationOperatorService(db, lambda: self.identity).revoke(self.context); db.close()
        with self.assertRaises(PermissionError): self.service.detach(**self.request)
        with self.assertRaises(PermissionError): self.service.detach_status(receipt['operation_id'])

    def test_busy_and_transaction_failure_leave_no_partial_transition(self):
        with RuntimeServiceLock(self.root/'forge.db').acquire():
            with self.assertRaises(RuntimeServiceBusy): self.service.detach(**self.request)
        with patch('forge.runtime.database.RuntimeDatabase._append_operational_event', side_effect=RuntimeError('injected audit failure')):
            with self.assertRaises(RuntimeError): self.service.detach(**self.request)
        self.assertEqual(self.service.show(), self.before)
        with self.assertRaises(InstallationPairingError): self.service.detach_status('detach-one')
        self.assertEqual(self.service.detach(**self.request)['phase'], 'COMPLETE')

    def test_http_admin_boundary_and_lost_reply_recovery(self):
        from forge.server_runtime import ForgeServerAPI, ForgeServerApplicationServices, ServerRuntimeState, existing_instance
        services = ForgeServerApplicationServices(self.root, ServerRuntimeState(existing_instance(self.root), 'test'), provider_id='test')
        api = ForgeServerAPI(services, 'server-test-credential')
        route = '/v1/installation-peer/detach'
        for auth in (None, 'Bearer wrong'):
            self.assertEqual(api.handle('POST', route, auth, self.request).status, 401)
        authorization = 'Bearer server-test-credential'
        response = api.handle('POST', route, authorization, self.request)
        self.assertEqual(response.status, 200, response.body)
        receipt = response.body
        recovered = api.handle('GET', route+'/detach-one', authorization)
        self.assertEqual(recovered.status, 200)
        self.assertEqual(recovered.body, receipt)
        self.assertEqual(api.handle('POST', route, authorization, self.request).body, receipt)
        for change in ({'project_id':'fake'}, {'expected_configuration_revision':True}, {'expected_binding_id':'other'}):
            self.assertEqual(api.handle('POST', route, authorization, dict(self.request, **change)).status, 409)

    def test_cli_uses_supported_detach_and_status(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from forge.__main__ import main
        common = ['--data-root', str(self.root), 'installation-peer']
        output = StringIO()
        with redirect_stdout(output):
            result = main(common+['detach', '--operation-id','detach-one','--expected-binding-id','binding','--expected-configuration-revision','1'])
        self.assertEqual(result, 0)
        receipt = json.loads(output.getvalue())
        output = StringIO()
        before = self.snapshot()
        with redirect_stdout(output): result = main(common+['detach-status','--operation-id','detach-one'])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue()), receipt)
        self.assertEqual(self.snapshot(), before)
        output = StringIO()
        with redirect_stdout(output): result = main(common+['detach-status','--operation-id','absent'])
        self.assertEqual(result, 1)
        self.assertNotIn('private', output.getvalue())

    def test_schema45_migration_preserves_binding_and_revision(self):
        # Separate pre-update runtime, never downgrade the current test database.
        root = Path(self.temp.name)/'old'
        with patch('forge.runtime.database.RUNTIME_SCHEMA_VERSION',45):
            db = RuntimeBootstrap(data_root=root, forge_version='old').open()
            InstallationOperatorService(db, lambda:self.identity).first_bind()
            doc = dict(self.before['configuration'], forge_instance_id=db.runtime_identity.runtime_id,
                       installation_id=db.metadata['installation_id'])
            encoded = json.dumps(doc, sort_keys=True, separators=(',',':'))
            digest = 'sha256:'+sha256(encoded.encode()).hexdigest()
            with db._connection: db._connection.execute('INSERT INTO installation_peer_configuration VALUES(1,?,?,?,?)',('binding','configure-one',digest,encoded))
            db.close()
        db = RuntimeBootstrap(data_root=root, forge_version='new').open(); db.close()
        service = InstallationPairingService(root)
        self.assertEqual(service.show()['configuration'], doc)
        self.assertEqual(service.show()['configuration_revision'], 1)
        self.assertEqual(service.detach(**self.request)['configuration_revision'], 2)

    def test_receipt_tampering_denied(self):
        receipt = self.service.detach(**self.request)
        with sqlite3.connect(self.root/'forge.db') as c:
            with self.assertRaises(sqlite3.IntegrityError): c.execute("DELETE FROM installation_peer_detach_operations")
            triggers = c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'installation_detach_receipt_immutable_%'").fetchall()
            for name, sql in triggers: c.execute(f'DROP TRIGGER {name}')
            corrupt = dict(receipt, binding_id='foreign')
            c.execute('UPDATE installation_peer_detach_operations SET receipt=?', (json.dumps(corrupt,sort_keys=True,separators=(',',':')),))
            for name, sql in triggers: c.execute(sql)
        with self.assertRaises(InstallationPairingError): self.service.detach_status('detach-one')
        with self.assertRaises(InstallationPairingError): self.service.detach(**self.request)

    def test_maintenance_blocks_detach_and_preserves_binding(self):
        with sqlite3.connect(self.root/'forge.db') as c:
            c.create_function('forge_maintenance_write_permitted', 0, lambda:1)
            c.execute("UPDATE operational_reset_state SET active_operation_id='test-maintenance' WHERE singleton=1")
        with self.assertRaises(RuntimeError): self.service.detach(**self.request)
        self.assertEqual(self.service.show(), self.before)

    def test_actual_http_transport_restart_and_cli_receipt_join(self):
        from threading import Thread
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from forge.server_runtime import ForgeServerRuntime
        credential = self.root/'isolated-server-credential'
        credential.write_text('isolated-detach-test-token\n'); credential.chmod(0o600)
        expected = None
        for iteration in range(2):
            server = ForgeServerRuntime(data_root=self.root, credential_file=credential, host='127.0.0.1', port=0)
            thread = Thread(target=server.server.serve_forever, daemon=True); thread.start()
            url = f'http://127.0.0.1:{server.server.server_port}/v1/installation-peer/detach'
            try:
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(url, data=json.dumps(self.request).encode(), method='POST'),timeout=2)
                self.assertEqual(caught.exception.code,401); caught.exception.close()
                headers = {'Authorization':'Bearer isolated-detach-test-token','Content-Type':'application/json'}
                if iteration == 0:
                    with urlopen(Request(url,data=json.dumps(self.request).encode(),method='POST',headers=headers),timeout=2) as response:
                        expected = json.load(response)
                with urlopen(Request(url+'/detach-one', headers=headers),timeout=2) as response:
                    self.assertEqual(json.load(response),expected)
                with urlopen(Request(url,data=json.dumps(self.request).encode(),method='POST',headers=headers),timeout=2) as response:
                    self.assertEqual(json.load(response),expected)
                with self.assertRaises(HTTPError) as caught:
                    urlopen(Request(url,data=json.dumps(dict(self.request,expected_configuration_revision=2)).encode(),method='POST',headers=headers),timeout=2)
                self.assertEqual(caught.exception.code,409); caught.exception.close()
            finally:
                server.server.shutdown(); server.server.server_close(); thread.join(timeout=2)
        self.assertEqual(self.service.detach_status('detach-one'),expected)

    @unittest.skipUnless(os.uname().sysname=='Darwin', 'native macOS identity qualification')
    def test_actual_native_operator_detach_without_secret_resolution(self):
        from forge.operator_identity import MacOSGeneratedUIDIdentityAdapter
        root = Path(self.temp.name)/'native'
        # Temporarily undo only this fixture's portable resolver; real directory
        # identity and real G001 binding are used for the native product proof.
        with patch('forge.operator_identity.MacOSGeneratedUIDIdentityAdapter.resolve', new=self.original_native_resolver):
            db = RuntimeBootstrap(data_root=root, forge_version='test').open()
            InstallationOperatorService(db, MacOSGeneratedUIDIdentityAdapter().resolve).first_bind(); db.close()
            service = InstallationPairingService(root)
            service.configure(**self.configure)
            with patch('forge.installation_pairing.MacOSKeychainSecureStoreAdapter', side_effect=AssertionError('secret access forbidden')):
                receipt = service.detach(**self.request)
                self.assertEqual(service.detach_status('detach-one'),receipt)
                self.assertEqual(service.detach(**self.request),receipt)

    def test_actual_binding_column_drift_cannot_detach(self):
        with sqlite3.connect(self.root/'forge.db') as c:
            c.execute("UPDATE installation_peer_configuration SET binding_id='foreign'")
        with self.assertRaises(InstallationPairingError): self.service.detach(**self.request)
        with self.assertRaises(InstallationPairingError): self.service.show()
        with sqlite3.connect(self.root/'forge.db') as c:
            self.assertEqual(c.execute('SELECT count(*) FROM installation_peer_configuration').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM installation_peer_detach_operations').fetchone()[0],0)

    def test_corrupt_stored_typed_request_and_coherent_receipt_rehash_both_deny(self):
        from forge.installation_peer_detach import _canonical, _digest
        receipt = self.service.detach(**self.request)
        with sqlite3.connect(self.root/'forge.db') as c:
            original = tuple(c.execute('SELECT request,receipt FROM installation_peer_detach_operations').fetchone())
            triggers = c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'installation_detach_receipt_immutable_%'").fetchall()
        variants = [(dict(self.request,expected_configuration_revision=True),receipt),
                    (dict(self.request,extra='invalid'),receipt),
                    ({key:value for key,value in self.request.items() if key!='expected_binding_id'},receipt)]
        changed = dict(receipt,previous_configuration_digest='sha256:'+'f'*64)
        changed.pop('receipt_digest'); changed['receipt_digest'] = _digest(changed)
        variants.append((self.request, changed))
        for request, saved in variants:
            with self.subTest(request=request, receipt=saved['previous_configuration_digest']):
                with sqlite3.connect(self.root/'forge.db') as c:
                    for name,sql in triggers: c.execute(f'DROP TRIGGER {name}')
                    c.execute('UPDATE installation_peer_detach_operations SET request=?,receipt=?', (_canonical(request),_canonical(saved)))
                    for name,sql in triggers: c.execute(sql)
                with self.assertRaises(InstallationPairingError): self.service.detach(**self.request)
                with self.assertRaises(InstallationPairingError): self.service.detach_status('detach-one')
        with sqlite3.connect(self.root/'forge.db') as c:
            for name,sql in triggers: c.execute(f'DROP TRIGGER {name}')
            c.execute('UPDATE installation_peer_detach_operations SET request=?,receipt=?',original)
            for name,sql in triggers: c.execute(sql)
        self.assertEqual(self.service.detach_status('detach-one'),receipt)

    def test_actual_canonical_revoke_before_effect_transaction_wins(self):
        from forge.execution_host_configuration import EngineeringPlatformPeerConfigurationService
        original = EngineeringPlatformPeerConfigurationService._open_for_configuration
        identity, context, root = self.identity, self.context, self.root
        class InterleavedConnection:
            def __init__(self, connection): self.connection = connection; self.fired = False
            def __getattr__(self, name): return getattr(self.connection,name)
            def __enter__(self): return self.connection.__enter__()
            def __exit__(self,*args): return self.connection.__exit__(*args)
            def execute(self, statement, *args):
                if statement == 'BEGIN IMMEDIATE' and not self.fired:
                    self.fired = True
                    other = RuntimeBootstrap(data_root=root, forge_version='test').open()
                    try: InstallationOperatorService(other,lambda:identity).revoke(context)
                    finally: other.close()
                return self.connection.execute(statement,*args)
        def scheduled_open(service):
            db = original(service)
            db._connection = InterleavedConnection(db._connection)
            return db
        with patch.object(EngineeringPlatformPeerConfigurationService, '_open_for_configuration',new=scheduled_open):
            with self.assertRaises(PermissionError): self.service.detach(**self.request)
        self.assertEqual(self.service.show(),self.before)
        with sqlite3.connect(self.root/'forge.db') as c:
            self.assertEqual(c.execute('SELECT count(*) FROM installation_peer_detach_operations').fetchone()[0],0)
