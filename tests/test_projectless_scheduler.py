"""Installation idle is proven from canonical storage, never an EP-error fallback."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sqlite3
import unittest
from unittest.mock import patch

from forge.runtime import RuntimeBootstrap
from forge.server_runtime import ForgeServerRuntime
from forge.execution_host_configuration import PeerConfigurationError


class ProjectlessSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'instance'
        RuntimeBootstrap(data_root=self.root, forge_version='test').open().close()
        credential=self.root/'server-credential';credential.write_text('synthetic-server-token\n');credential.chmod(0o600)
        self.server=ForgeServerRuntime(data_root=self.root,credential_file=credential,host='127.0.0.1',port=0)
        self.addCleanup(self.server.server.server_close)
        self.provider=patch.object(self.server.services,'provider_readiness',return_value={'ready':True})
        self.provider.start();self.addCleanup(self.provider.stop)

    def test_empty_projectless_instance_does_not_compose_execution_runtime(self):
        with patch('forge.server_runtime.InstalledDynamicMissionRuntime.open',side_effect=AssertionError('project composition before work')) as opened:
            self.server._tick()
        opened.assert_not_called()
        self.assertEqual(self.server.state.document()['scheduler']['state'],'IDLE')
        readiness=self.server.services.installation_readiness()
        self.assertTrue(readiness['service_ready'])
        self.assertFalse(readiness['execution_ready'])
        self.assertFalse(readiness['project_authorized'])

    def test_unavailable_provider_remains_blocking_even_when_empty(self):
        self.provider.stop()
        with patch.object(self.server.services,'provider_readiness',return_value={'ready':False}):
            with self.assertRaisesRegex(RuntimeError,'provider is not ready'):self.server._tick()

    def test_nonempty_uncertain_work_evidence_cannot_take_empty_shortcut(self):
        # An allocation with no admitted state is intentionally uncertain.
        with sqlite3.connect(self.root/'forge.db') as db:
            db.execute("INSERT INTO mission_id_allocations VALUES('synthetic-mission','2026-10-17','synthetic-only')")
        with patch('forge.server_runtime.InstalledDynamicMissionRuntime.open',side_effect=PeerConfigurationError('project required')):
            with self.assertRaises(PeerConfigurationError):self.server._tick()

    def test_corrupt_or_missing_canonical_storage_never_becomes_idle(self):
        original=(self.root/'forge.db').read_bytes()
        for fault in ('missing','corrupt'):
            with self.subTest(fault=fault):
                path=self.root/'forge.db';saved=self.root/'saved.db';path.rename(saved)
                if fault=='corrupt':path.write_bytes(b'not sqlite')
                try:
                    with self.assertRaises(Exception):self.server._tick()
                    self.assertNotEqual(self.server.state.document()['scheduler']['state'],'IDLE')
                finally:
                    if path.exists():path.unlink()
                    saved.rename(path)
        self.assertEqual((self.root/'forge.db').read_bytes(),original)

    def test_persisted_resumable_mission_retains_project_requirement(self):
        from forge.state import MissionStateStore
        db=RuntimeBootstrap(data_root=self.root,forge_version='test').open()
        try:
            state=MissionStateStore(db,data_root=str(self.root)).create(
                {'id':'synthetic-resume'},[{'id':'intent'}],[{'id':'action'}],occurred_at='2026-10-17T00:00:00Z')
        finally:db.close()
        self.assertEqual(state.status.value,'CREATED')
        with patch('forge.server_runtime.InstalledDynamicMissionRuntime.open',side_effect=PeerConfigurationError('project required')) as opened:
            with self.assertRaises(PeerConfigurationError):self.server._tick()
        opened.assert_called_once_with(str(self.root.resolve()),provider_id=self.server.provider_id)

    def test_workset_without_admission_cannot_appear_idle(self):
        with sqlite3.connect(self.root/'forge.db') as db:
            db.execute("INSERT INTO approved_worksets VALUES('synthetic-workset',1,'not-json')")
        with patch('forge.server_runtime.InstalledDynamicMissionRuntime.open',side_effect=PeerConfigurationError('project required')):
            with self.assertRaises(PeerConfigurationError):self.server._tick()

    def test_empty_probe_is_read_only_and_does_not_migrate(self):
        from hashlib import sha256
        before=sha256((self.root/'forge.db').read_bytes()).hexdigest()
        self.server._tick();self.server._tick()
        self.assertEqual(sha256((self.root/'forge.db').read_bytes()).hexdigest(),before)

    def test_mutation_lease_contention_is_not_idle(self):
        from forge.runtime.service import RuntimeServiceLock, RuntimeServiceBusy
        with RuntimeServiceLock(self.root/'forge.db').acquire():
            with self.assertRaises(RuntimeServiceBusy):self.server._tick()
        self.assertNotEqual(self.server.state.document()['scheduler']['state'],'IDLE')

    def test_nonempty_runtime_keeps_original_service_tick(self):
        from contextlib import contextmanager
        from forge.runtime.service import RuntimeServiceTick
        with sqlite3.connect(self.root/'forge.db') as db:
            db.execute("INSERT INTO mission_id_allocations VALUES('synthetic-mission','2026-10-17','synthetic-only')")
        @contextmanager
        def opened(*args,**kwargs):yield SimpleNamespace(states=object(),database=object())
        with patch('forge.server_runtime.InstalledDynamicMissionRuntime.open',side_effect=opened), patch('forge.server_runtime.ForgeRuntimeService') as service:
            service.return_value.tick.return_value=RuntimeServiceTick(('synthetic-mission',),None,True)
            self.server._tick()
            service.return_value.tick.assert_called_once_with()
        self.assertEqual(self.server.state.document()['scheduler']['state'],'READY')

    def test_orphan_dispatcher_evidence_cannot_take_idle_shortcut(self):
        db=RuntimeBootstrap(data_root=self.root,forge_version='test').open()
        try:db.save_dispatcher_state(status='ACTIVE',mission_sequence=('synthetic-mission',),active_mission_id='synthetic-mission')
        finally:db.close()
        with patch('forge.server_runtime.InstalledDynamicMissionRuntime.open',side_effect=PeerConfigurationError('project required')):
            with self.assertRaises(PeerConfigurationError):self.server._tick()

    def test_unbound_execution_host_evidence_cannot_take_idle_shortcut(self):
        with sqlite3.connect(self.root/'forge.db') as db:
            db.execute("INSERT INTO execution_host_bindings VALUES('uncertain','not-json')")
        with patch('forge.server_runtime.InstalledDynamicMissionRuntime.open',side_effect=PeerConfigurationError('project required')):
            with self.assertRaises(PeerConfigurationError):self.server._tick()

    def test_unbound_durable_submission_audit_cannot_take_idle_shortcut(self):
        db=RuntimeBootstrap(data_root=self.root,forge_version='test').open()
        try:db.record_execution_host_exchange_audit('synthetic-uncertain',direction='FORGE_TO_EP',event_kind='FORGE_SUBMISSION_SENT',document={'status':'sent'})
        finally:db.close()
        with patch('forge.server_runtime.InstalledDynamicMissionRuntime.open',side_effect=PeerConfigurationError('project required')):
            with self.assertRaises(PeerConfigurationError):self.server._tick()
