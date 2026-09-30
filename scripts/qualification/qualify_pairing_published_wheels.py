"""Pairing lifecycle conformance on installed Forge and EP wheels only."""
import argparse
from hashlib import sha256
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import sqlite3
import socket
import subprocess
import sys
import tempfile
from threading import Thread
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from engineering_platform import local_repository_binding, project_topology, repository_attachment, server
from engineering_platform.storage import sqlite_connection
from forge.execution_host_configuration import EngineeringPlatformExecutionHostFactory, EngineeringPlatformPeerConfigurationService
from forge.secure_store import SecretState
from forge.server_runtime import ForgeServerRuntime

parser = argparse.ArgumentParser()
parser.add_argument('--forge-wheel', type=Path, required=True)
parser.add_argument('--forge-sha256', required=True)
parser.add_argument('--forge-source', required=True)
parser.add_argument('--ep-wheel', type=Path, required=True)
parser.add_argument('--ep-sha256', required=True)
arguments = parser.parse_args()
if sys.flags.optimize:
    raise RuntimeError('qualification requires Python assertions to remain enabled')
for wheel, digest in ((arguments.forge_wheel, arguments.forge_sha256),
                      (arguments.ep_wheel, arguments.ep_sha256)):
    if sha256(wheel.read_bytes()).hexdigest() != digest:
        raise RuntimeError('selected wheel digest mismatch')
for product, wheel, digest in (
    ('forge-autonomy', arguments.forge_wheel, arguments.forge_sha256),
    ('engineering-platform', arguments.ep_wheel, arguments.ep_sha256),
):
    origin = distribution(product).read_text('direct_url.json')
    try:
        direct = json.loads(origin) if origin is not None else None
    except json.JSONDecodeError:
        direct = None
    if (not isinstance(direct, dict) or direct.get('url') != wheel.resolve().as_uri()
            or direct.get('archive_info', {}).get('hashes', {}).get('sha256') != digest):
        raise RuntimeError('installed product is not the selected exact wheel')
if len(arguments.forge_source) != 40 or any(character not in '0123456789abcdef' for character in arguments.forge_source):
    raise RuntimeError('Forge source revision must be exact')
import engineering_platform
import forge
for module in (engineering_platform, forge):
    if 'site-packages' not in Path(module.__file__).resolve().parts:
        raise RuntimeError('qualification did not import an installed product')

def port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]

def cli(root, *args):
    result = subprocess.run([sys.executable, '-m', 'forge', '--data-root', str(root), *args],
                            cwd=tempfile.gettempdir(), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Forge CLI failed: ' + result.stderr[-1000:])
    return json.loads(result.stdout)

def epcli(root, action, *, consumer=None, project=None, credential=None, success=True):
    args = [sys.executable, '-m', 'engineering_platform.ep_consumer_credentials', action,
            '--repo', str(root)]
    if consumer: args += ['--consumer-id', consumer]
    if project: args += ['--project-id', project]
    if credential: args += ['--credential-id', credential]
    environment = os.environ.copy()
    environment['EP_CENTRAL_OPERATIONAL_DATABASE'] = str(root / server.SERVER_DATABASE_FILENAME)
    result = subprocess.run(args, cwd=tempfile.gettempdir(), env=environment,
                            capture_output=True, text=True)
    if (result.returncode == 0) != success:
        raise RuntimeError('EP CLI returned unexpected status for ' + action)
    return json.loads(result.stdout) if success else None

class Resolver:
    def __init__(self, value): self.value = value
    def resolve(self, _ref): return SecretState.RESOLVABLE, self.value

def forge_http(runtime, route):
    request = Request('http://127.0.0.1:' + str(runtime.server.server_port) + route,
                      headers={'Authorization': 'Bearer r29-test-server-token'})
    try:
        with urlopen(request, timeout=4) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())

with tempfile.TemporaryDirectory(prefix='r29-pairing-http-') as temporary:
    base = Path(temporary).resolve()
    ep_root, forge_root, checkout = base / 'ep', base / 'forge', base / 'checkout'
    sibling_root = base / 'forge-sibling'
    declaration = {
        'schema_version': '1.0',
        'project': {'id': 'forge', 'authority_repository_id': 'forge'},
        'repository': {'id': 'forge', 'role': 'authority'},
        'validation': {'kind': 'none', 'entrypoint': None, 'description': None},
        'requirements': {'host': {}, 'tools': {}}, 'integrations': {},
    }
    attachment_path = repository_attachment.config_path(checkout)
    attachment_path.parent.mkdir(parents=True)
    attachment_path.write_text(json.dumps(declaration), encoding='utf-8')
    ep_port = port()
    ep_identity = server.initialize(ep_root, bind_port=ep_port)
    with sqlite_connection(ep_root / server.SERVER_DATABASE_FILENAME) as connection:
        project_topology.register_server_local_topology(connection, declaration=declaration)
        local_repository_binding.bind_local_repository(
            connection, project_id='forge', repository_id='forge', local_root=checkout, data_root=ep_root)
    server.start(ep_root)
    try:
        old = 'r29-consumer-old'
        new = 'r29-consumer-new'
        epcli(ep_root, 'consumer-register', consumer=old, project='forge')
        old_issue = epcli(ep_root, 'credential-issue', consumer=old, project='forge')
        old_secret = old_issue.pop('credential')
        initialized = cli(forge_root, 'server', 'init')
        cli(sibling_root, 'server', 'init')
        sibling_database_before = (sibling_root / 'forge.db').read_bytes()
        instance_id = initialized.get('instance_id')
        if not instance_id:
            from forge.server_runtime import existing_instance
            instance_id = existing_instance(forge_root).instance_id
        token_file = base / 'server-token'
        token_file.write_text('r29-test-server-token\n', encoding='utf-8')
        token_file.chmod(0o600)
        runtime = ForgeServerRuntime(data_root=forge_root, credential_file=token_file,
                                     host='127.0.0.1', port=0)
        thread = Thread(target=runtime.server.serve_forever, daemon=True)
        thread.start()
        try:
            runtime.state.scheduler('READY')
            with patch.object(runtime.services, 'provider_readiness', return_value={'ready': True}):
                status, initial = forge_http(runtime, '/v1/readiness/standalone')
            assert status == 200 and initial['service_ready'] and not initial['execution_ready']
            common = [
                '--binding-id', 'ep-primary', '--endpoint', f'http://127.0.0.1:{ep_port}',
                '--expected-instance-id', ep_identity.instance_id,
                '--host-id', 'engineering-platform', '--project-id', 'forge',
                '--repository-id', 'forge', '--repository-identity', 'forge',
                '--credential-reference', 'keychain://forge.ep/consumer', '--operator-id', 'test-operator',
                '--allow-loopback-http',
            ]
            configured = cli(forge_root, 'execution-host', 'configure', *common,
                             '--consumer-id', old)
            old_config = configured['configuration']
            with patch('forge.secure_store.MacOSKeychainSecureStoreAdapter.resolve',
                       return_value=(SecretState.RESOLVABLE, old_secret)):
                preflight = EngineeringPlatformPeerConfigurationService(forge_root).preflight()
                assert preflight['authenticated_consumer_identity'] == old
                with patch.object(runtime.services, 'provider_readiness', return_value={'ready': True}):
                    status, ready = forge_http(runtime, '/v1/readiness')
                    assert status == 200 and ready['ready']
            runtime.server.shutdown()
            runtime.server.server_close()
            thread.join(timeout=2)
            with sqlite3.connect(f'file:{forge_root / "forge.db"}?mode=ro', uri=True) as database:
                installation_id = database.execute(
                    "SELECT value FROM runtime_metadata WHERE key='installation_id'"
                ).fetchone()[0]
            identity = [
                '--instances-root', str(base), '--instance-id', instance_id,
                '--runtime-id', instance_id, '--installation-id', installation_id,
                '--installed-version', '2.7.39', '--installed-source', arguments.forge_source,
                '--installed-artifact-digest', 'sha256:' + arguments.forge_sha256,
            ]
            preserved = cli(forge_root, 'server', 'preserve', '--operation-id', 'r29-preserve', *identity)
            assert preserved['lifecycle_state'] == 'UNINSTALLED_DATA_PRESERVED'
            restored = cli(forge_root, 'server', 'restore', '--operation-id', 'r29-restore',
                           '--preserve-operation-id', 'r29-preserve', *identity)
            assert restored['lifecycle_state'] == 'RESTORE_VALIDATED'
            runtime = ForgeServerRuntime(data_root=forge_root, credential_file=token_file,
                                         host='127.0.0.1', port=0)
            thread = Thread(target=runtime.server.serve_forever, daemon=True)
            thread.start()
            runtime.state.scheduler('READY')
            epcli(ep_root, 'consumer-revoke', consumer=old, project='forge')
            with patch('forge.secure_store.MacOSKeychainSecureStoreAdapter.resolve',
                       return_value=(SecretState.RESOLVABLE, old_secret)):
                with patch.object(runtime.services, 'provider_readiness', return_value={'ready': True}):
                    status, rejected = forge_http(runtime, '/v1/readiness')
                    assert status == 503 and not rejected['ready']
            epcli(ep_root, 'consumer-register', consumer=new, project='forge')
            new_issue = epcli(ep_root, 'credential-issue', consumer=new, project='forge')
            new_secret = new_issue.pop('credential')
            with patch('forge.secure_store.MacOSKeychainSecureStoreAdapter.resolve',
                       return_value=(SecretState.RESOLVABLE, new_secret)):
                with patch.object(runtime.services, 'provider_readiness', return_value={'ready': True}):
                    status, wrong_consumer = forge_http(runtime, '/v1/readiness')
                    assert status == 503 and not wrong_consumer['ready']
            detached = cli(forge_root, 'execution-host', 'detach', '--operation-id', 'r29-detach',
                           '--instance-id', instance_id, '--expected-binding-id', 'ep-primary',
                           '--expected-revision', str(old_config['configuration_revision']),
                           '--expected-digest', old_config['configuration_digest'],
                           '--operator-id', 'test-operator')
            assert detached['remote_consumer_revoke'] == 'NOT_ASSERTED'
            assert cli(forge_root, 'execution-host', 'detach-status', '--operation-id', 'r29-detach')['phase'] == 'COMPLETE'
            replacement = cli(forge_root, 'execution-host', 'configure', *common,
                              '--consumer-id', new, '--replace',
                              '--expected-revision', str(old_config['configuration_revision']),
                              '--expected-digest', detached['receipt_digest'])['configuration']
            replay = cli(forge_root, 'execution-host', 'configure', *common,
                         '--consumer-id', new, '--replace',
                         '--expected-revision', str(old_config['configuration_revision']),
                         '--expected-digest', detached['receipt_digest'])['configuration']
            assert replay == replacement
            assert replacement['configuration_revision'] == old_config['configuration_revision'] + 1
            assert replacement['owning_forge_runtime_id'] == instance_id
            assert replacement['expected_ep_instance_id'] == ep_identity.instance_id
            with patch('forge.secure_store.MacOSKeychainSecureStoreAdapter.resolve',
                       return_value=(SecretState.RESOLVABLE, old_secret)):
                with patch.object(runtime.services, 'provider_readiness', return_value={'ready': True}):
                    status, rejected = forge_http(runtime, '/v1/readiness')
                    assert status == 503 and not rejected['ready']
            with patch('forge.secure_store.MacOSKeychainSecureStoreAdapter.resolve',
                       return_value=(SecretState.RESOLVABLE, new_secret)):
                preflight = EngineeringPlatformPeerConfigurationService(forge_root).preflight()
                assert preflight['authenticated_consumer_identity'] == new
                with patch.object(runtime.services, 'provider_readiness', return_value={'ready': True}):
                    status, ready = forge_http(runtime, '/v1/readiness')
                    assert status == 200 and ready['ready']
                    status, no_standalone = forge_http(runtime, '/v1/readiness/standalone')
                    assert status == 503 and not no_standalone['service_ready']
            assert (sibling_root / 'forge.db').read_bytes() == sibling_database_before
            from forge.server_runtime import existing_instance
            assert existing_instance(sibling_root).instance_id != instance_id
            print(json.dumps({'forge_wheel_sha256': arguments.forge_sha256,
                              'ep_wheel_sha256': arguments.ep_sha256,
                              'old_credential_rejected':'PASS', 'new_exact_peer_http':'PASS',
                              'valid_foreign_consumer_rejected':'PASS',
                              'standalone_then_detach_then_repair':'PASS',
                              'lost_peer_configure_response_replay':'PASS',
                              'paired_preserve_restore':'PASS',
                              'forge_instance_preserved':'PASS', 'ep_instance_preserved':'PASS',
                              'sibling_instance_byte_unchanged':'PASS'}, sort_keys=True))
        finally:
            runtime.server.shutdown()
            runtime.server.server_close()
            thread.join(timeout=2)
    finally:
        server.stop(ep_root)
