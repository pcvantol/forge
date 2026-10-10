"""Project-independent EP installation readback, without dispatch authority."""
from dataclasses import dataclass, field
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .execution_host_configuration import canonical_endpoint, PeerConfigurationError
from .secure_store import MacOSKeychainSecureStoreAdapter, SecretReference, SecretState


class InstallationPairingError(RuntimeError):
    """Nonsecret failure of installation-only connectivity."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


@dataclass(frozen=True)
class InstallationPeer:
    binding_id: str
    endpoint: str
    ep_instance_id: str
    forge_instance_id: str
    consumer_id: str
    credential_reference: str
    allow_loopback_http: bool = False
    timeout_seconds: float = 10.0

    def __post_init__(self):
        for value in (self.binding_id, self.ep_instance_id, self.forge_instance_id, self.consumer_id):
            if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value) is None:
                raise InstallationPairingError('INSTALLATION_ID_INVALID')
        if not isinstance(self.allow_loopback_http, bool):
            raise InstallationPairingError('INSTALLATION_TRANSPORT_INVALID')
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int,float)) or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 60:
            raise InstallationPairingError('INSTALLATION_TIMEOUT_INVALID')
        try:
            object.__setattr__(self, 'endpoint', canonical_endpoint(self.endpoint, allow_loopback_http=self.allow_loopback_http))
            object.__setattr__(self, 'credential_reference', SecretReference.parse(self.credential_reference).serialized)
        except (PeerConfigurationError, ValueError):
            raise InstallationPairingError('INSTALLATION_TRANSPORT_OR_REFERENCE_INVALID') from None


@dataclass(frozen=True)
class _InstallationReadback:
    peer: InstallationPeer
    bearer: str = field(repr=False)

    def check(self) -> dict[str, object]:
        request = Request(self.peer.endpoint + '/v1/installation-compatibility', headers={
            'Authorization': 'Bearer ' + self.bearer,
            'EP-Instance-ID': self.peer.ep_instance_id,
            'Forge-Instance-ID': self.peer.forge_instance_id,
        })
        try:
            with build_opener(_NoRedirect()).open(request, timeout=self.peer.timeout_seconds) as response:
                raw = response.read(32769)
                if response.status != 200 or len(raw) > 32768 or response.headers.get('EP-Server-Instance') != self.peer.ep_instance_id:
                    raise InstallationPairingError('INSTALLATION_RESPONSE_INVALID')
                value = json.loads(raw)
        except HTTPError as error:
            code = error.code; error.close()
            raise InstallationPairingError('INSTALLATION_HTTP_REJECTED_' + str(code)) from None
        except (URLError, OSError, ValueError):
            raise InstallationPairingError('INSTALLATION_READBACK_UNAVAILABLE') from None
        expected = dict(binding_id=self.peer.binding_id, ep_instance_id=self.peer.ep_instance_id,
                        forge_instance_id=self.peer.forge_instance_id, consumer_id=self.peer.consumer_id,
                        purpose='INSTALLATION_READBACK')
        if not isinstance(value, dict) or value.get('contract_version') != '1.0' or value.get('instance') != {'id':self.peer.ep_instance_id} or value.get('authentication') != expected or value.get('authority') != dict(installation_readback=True, project_access=False, submission=False, execution=False, governance=False):
            raise InstallationPairingError('INSTALLATION_AUTHORITY_MISMATCH')
        producer = value.get('producer')
        if not isinstance(producer, dict) or producer.get('id') != 'engineering-platform' or not isinstance(producer.get('version'), str):
            raise InstallationPairingError('INSTALLATION_PRODUCT_MISMATCH')
        return dict(status='CONNECTED', binding_id=self.peer.binding_id, ep_instance_id=self.peer.ep_instance_id,
                    forge_instance_id=self.peer.forge_instance_id, consumer_id=self.peer.consumer_id,
                    contract_version='1.0', purpose='INSTALLATION_READBACK', project_authorized=False, execution_ready=False)


def check_installation_peer(peer: InstallationPeer) -> dict[str, object]:
    """Use Forge's existing normal Keychain resolver; no credential argument."""
    if not isinstance(peer, InstallationPeer):
        raise InstallationPairingError('INSTALLATION_CONFIGURATION_REQUIRED')
    state, bearer = MacOSKeychainSecureStoreAdapter().resolve(SecretReference.parse(peer.credential_reference))
    if state is not SecretState.RESOLVABLE or not bearer:
        raise InstallationPairingError('INSTALLATION_CREDENTIAL_UNAVAILABLE')
    return _InstallationReadback(peer, bearer).check()


class InstallationPairingService:
    """Canonical runtime storage and trusted operator boundary, no projects."""
    def __init__(self, data_root):
        from .runtime.data_root import DataRootResolver
        self.root = DataRootResolver(cli_data_root=data_root).resolve()

    def configure(self, *, operation_id: str, **values) -> dict[str, object]:
        from dataclasses import asdict
        from hashlib import sha256
        from .execution_host_configuration import EngineeringPlatformPeerConfigurationService
        from .operator_identity import InstallationOperatorService, MacOSGeneratedUIDIdentityAdapter
        from .runtime.service import RuntimeServiceLock
        if not isinstance(operation_id,str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',operation_id) is None:
            raise InstallationPairingError('INSTALLATION_OPERATION_INVALID')
        # Existing configuration composition verifies marker, schema and exact
        # RuntimeBootstrap provenance; it cannot install or migrate an old slot.
        with RuntimeServiceLock(self.root/'forge.db').acquire():
            database = EngineeringPlatformPeerConfigurationService(self.root)._open_for_configuration()
            try:
                peer = InstallationPeer(forge_instance_id=database.runtime_identity.runtime_id, **values)
                operator = InstallationOperatorService(database,MacOSGeneratedUIDIdentityAdapter().resolve)
                context = operator.context()
                if not operator.authorize(context):
                    raise InstallationPairingError('INSTALLATION_OPERATOR_REQUIRED')
                document = dict(asdict(peer), operation_id=operation_id,
                                installation_id=context.installation_id, operator_binding_version=context.binding_version)
                encoded = json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False)
                digest = 'sha256:' + sha256(encoded.encode()).hexdigest()
                with database._connection:
                    row = database._connection.execute('SELECT operation_id,document_digest,document FROM installation_peer_configuration WHERE singleton=1').fetchone()
                    if row is not None:
                        if tuple(row) != (operation_id,digest,encoded):
                            raise InstallationPairingError('INSTALLATION_BINDING_REPLACEMENT_REQUIRES_SEPARATE_REVIEW')
                    else:
                        if database._connection.execute("SELECT 1 FROM installation_peer_detach_operations WHERE operation_id=?", (operation_id,)).fetchone():
                            raise InstallationPairingError("INSTALLATION_OPERATION_CONFLICT")
                        database._connection.execute("UPDATE installation_peer_generation SET revision=revision+1 WHERE singleton=1")
                        database._connection.execute('INSERT INTO installation_peer_configuration VALUES(1,?,?,?,?)', (peer.binding_id,operation_id,digest,encoded))
                        database._append_operational_event(component='forge_execution_host',level='INFO',event='installation_pairing_configured',
                            operator_reference=sha256(context.generated_uid.encode()).hexdigest()[:16],
                            details=dict(binding_id=peer.binding_id,configuration_digest=digest,
                                         ep_instance_id=peer.ep_instance_id,ep_consumer_id=peer.consumer_id,
                                         operation='configure_installation',outcome='accepted',new_state='CONFIGURED',
                                         reason_code='INSTALLATION_READBACK_ONLY',peer_product='engineering-platform'))
                revision = database._connection.execute("SELECT revision FROM installation_peer_generation WHERE singleton=1").fetchone()[0]
                return dict(status='CONFIGURED',configuration=document,configuration_digest=digest,configuration_revision=revision,execution_ready=False)
            finally:
                database.close()

    def show(self) -> dict[str, object]:
        import sqlite3
        from hashlib import sha256
        from .execution_host_configuration import read_peer_configuration
        from .runtime.database import RUNTIME_SCHEMA_VERSION
        readback = read_peer_configuration(self.root)
        if readback.storage_schema != RUNTIME_SCHEMA_VERSION:
            raise InstallationPairingError('INSTALLATION_SCHEMA_UPDATE_REQUIRED')
        connection = sqlite3.connect((self.root/'forge.db').as_uri()+'?mode=ro',uri=True)
        try:
            revision = connection.execute("SELECT revision FROM installation_peer_generation WHERE singleton=1").fetchone()[0]
            row = connection.execute('SELECT operation_id,document_digest,document,binding_id FROM installation_peer_configuration WHERE singleton=1').fetchone()
        finally:
            connection.close()
        if row is None:
            return dict(status='NOT_CONFIGURED',configuration_revision=revision,execution_ready=False)
        operation,digest,encoded,binding_id = row
        if 'sha256:'+sha256(encoded.encode()).hexdigest() != digest:
            raise InstallationPairingError('INSTALLATION_BINDING_CORRUPT')
        document = json.loads(encoded)
        peer_values = {key:document[key] for key in InstallationPeer.__dataclass_fields__}
        peer = InstallationPeer(**peer_values)
        if set(document) != set(peer_values)|{'operation_id','installation_id','operator_binding_version'} or document['operation_id'] != operation or peer.forge_instance_id != readback.runtime_id or peer.binding_id != binding_id:
            raise InstallationPairingError('INSTALLATION_BINDING_INSTANCE_MISMATCH')
        return dict(status='CONFIGURED',configuration=document,configuration_digest=digest,configuration_revision=revision,execution_ready=False)

    def preflight(self) -> dict[str, object]:
        current = self.show()
        if current['status'] != 'CONFIGURED':
            raise InstallationPairingError('INSTALLATION_NOT_CONFIGURED')
        document = current['configuration']
        peer = InstallationPeer(**{key:document[key] for key in InstallationPeer.__dataclass_fields__})
        return dict(check_installation_peer(peer), configuration_digest=current['configuration_digest'])

    def detach(self, **request) -> dict[str, object]:
        from .installation_peer_detach import detach
        return detach(self, request)

    def detach_status(self, operation_id: str) -> dict[str, object]:
        from .installation_peer_detach import detach_status
        return detach_status(self, operation_id)
