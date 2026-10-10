"""Own-installation peer detach: atomic receipts, no credential or project access."""
from hashlib import sha256
import json
import re
import sqlite3
from types import SimpleNamespace

from .installation_pairing import InstallationPairingError

CONTRACT = 'forge-installation-peer-detach/v1'
_FIELDS = {'operation_id', 'expected_binding_id', 'expected_configuration_revision'}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return 'sha256:' + sha256(_canonical(value).encode()).hexdigest()


def _identifier(value):
    if not isinstance(value, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value) is None:
        raise InstallationPairingError('INSTALLATION_OPERATION_INVALID')
    return value


def _request(value):
    if set(value) != _FIELDS:
        raise InstallationPairingError('INSTALLATION_DETACH_REQUEST_INVALID')
    _identifier(value['operation_id'])
    binding = value['expected_binding_id']
    revision = value['expected_configuration_revision']
    if not isinstance(binding, str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', binding) is None or type(revision) is not int or revision < 1:
        raise InstallationPairingError('INSTALLATION_DETACH_PRECONDITION_INVALID')
    return dict(value)


def _context(connection, runtime_id):
    from .operator_identity import InstallationOperatorService, MacOSGeneratedUIDIdentityAdapter
    metadata = dict(connection.execute('SELECT key,value FROM runtime_metadata'))
    if not metadata.get('installation_id') or metadata.get('runtime_id') != runtime_id:
        raise InstallationPairingError('INSTALLATION_DETACH_CONTEXT_INVALID')
    database = SimpleNamespace(_connection=connection, metadata=metadata)
    operator = InstallationOperatorService(database, MacOSGeneratedUIDIdentityAdapter().resolve)
    context = operator.context()
    if not operator.authorize(context):
        raise InstallationPairingError('INSTALLATION_OPERATOR_REQUIRED')
    return dict(runtime_id=runtime_id, installation_id=context.installation_id,
                operator_binding_version=context.binding_version,
                operator_reference=sha256(context.generated_uid.encode()).hexdigest()[:16])


def _receipt(request, context, configuration_digest):
    value = dict(contract=CONTRACT, phase='COMPLETE', **context,
                 operation_id=request['operation_id'], binding_id=request['expected_binding_id'],
                 previous_configuration_revision=request['expected_configuration_revision'],
                 configuration_revision=request['expected_configuration_revision'] + 1,
                 previous_configuration_digest=configuration_digest,
                 request_digest=_digest(dict(request=request, context=context)), execution_ready=False)
    return dict(value, receipt_digest=_digest(value))


def _verified(row, request, context):
    from .installation_pairing import InstallationPeer
    try:
        saved_request = _request(json.loads(row[0]))
        saved, basis = json.loads(row[1]), json.loads(row[2])
        if _canonical(saved_request) != _canonical(request) or _canonical(saved_request) != row[0]:
            raise InstallationPairingError('INSTALLATION_OPERATION_CONFLICT')
        if set(basis) != {'configuration', 'configuration_revision'} or _canonical(basis) != row[2]:
            raise ValueError('invalid basis')
        configuration = basis['configuration']
        peer = InstallationPeer(**{key:configuration[key] for key in InstallationPeer.__dataclass_fields__})
        if (set(configuration) != set(InstallationPeer.__dataclass_fields__) | {'operation_id', 'installation_id', 'operator_binding_version'} or
            configuration['operation_id'] == request['operation_id'] or
            peer.binding_id != request['expected_binding_id'] or peer.forge_instance_id != context['runtime_id'] or
            configuration['installation_id'] != context['installation_id'] or
            type(configuration['operator_binding_version']) is not int or
            configuration['operator_binding_version'] != context['operator_binding_version'] or
            type(basis['configuration_revision']) is not int or
            basis['configuration_revision'] != request['expected_configuration_revision']):
            raise ValueError('basis context mismatch')
        expected = _receipt(request, context, _digest(configuration))
        if _canonical(saved) != _canonical(expected) or _canonical(expected) != row[1]:
            raise ValueError('invalid receipt')
        return expected
    except (KeyError, TypeError, ValueError):
        raise InstallationPairingError('INSTALLATION_DETACH_RECEIPT_INVALID') from None


def detach(service, document):
    from .execution_host_configuration import EngineeringPlatformPeerConfigurationService
    from .runtime.service import RuntimeServiceLock
    request = _request(document)
    with RuntimeServiceLock(service.root/'forge.db').acquire():
        database = EngineeringPlatformPeerConfigurationService(service.root)._open_for_configuration()
        try:
            connection = database._connection
            with connection:
                # One database transaction binds the preconditions, transition,
                # durable receipt and audit. No intermediate operation survives.
                connection.execute('BEGIN IMMEDIATE')
                context = _context(connection, database.runtime_identity.runtime_id)
                row = connection.execute('SELECT request,receipt,basis FROM installation_peer_detach_operations WHERE operation_id=?', (request['operation_id'],)).fetchone()
                if row is not None:
                    return _verified(row, request, context)
                current = service.show()
                configuration = current.get('configuration', {})
                if (current['status'] != 'CONFIGURED' or
                    configuration.get('binding_id') != request['expected_binding_id'] or
                    current['configuration_revision'] != request['expected_configuration_revision'] or
                    configuration.get('installation_id') != context['installation_id'] or
                    configuration.get('operator_binding_version') != context['operator_binding_version']):
                    raise InstallationPairingError('INSTALLATION_DETACH_PRECONDITION_MISMATCH')
                if configuration.get('operation_id') == request['operation_id']:
                    raise InstallationPairingError('INSTALLATION_OPERATION_CONFLICT')
                receipt = _receipt(request, context, current['configuration_digest'])
                connection.execute('DELETE FROM installation_peer_configuration WHERE singleton=1')
                connection.execute('UPDATE installation_peer_generation SET revision=revision+1 WHERE singleton=1')
                connection.execute('INSERT INTO installation_peer_detach_operations VALUES (?,?,?,?)',
                                   (request['operation_id'], _canonical(request), _canonical(receipt),
                                    _canonical(dict(configuration=configuration, configuration_revision=current['configuration_revision']))))
                database._append_operational_event(component='forge_execution_host', level='INFO',
                    event='installation_pairing_detached', operator_reference=context['operator_reference'],
                    details=dict(operation='detach_installation', outcome='accepted', new_state='NOT_CONFIGURED',
                                 binding_id=request['expected_binding_id'], configuration_digest=current['configuration_digest'],
                                 reason_code='INSTALLATION_BINDING_DETACHED', peer_product='engineering-platform'))
                return receipt
        finally:
            database.close()


def detach_status(service, operation_id):
    from .execution_host_configuration import read_peer_configuration
    from .runtime.database import RUNTIME_SCHEMA_VERSION
    _identifier(operation_id)
    readback = read_peer_configuration(service.root)
    if readback.storage_schema != RUNTIME_SCHEMA_VERSION:
        raise InstallationPairingError('INSTALLATION_SCHEMA_UPDATE_REQUIRED')
    connection = sqlite3.connect((service.root/'forge.db').as_uri()+'?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        context = _context(connection, readback.runtime_id)
        row = connection.execute('SELECT request,receipt,basis FROM installation_peer_detach_operations WHERE operation_id=?', (operation_id,)).fetchone()
        if row is None:
            raise InstallationPairingError('INSTALLATION_DETACH_OPERATION_ABSENT')
        try:
            request = _request(json.loads(row[0]))
        except (ValueError, TypeError):
            raise InstallationPairingError('INSTALLATION_DETACH_RECEIPT_INVALID') from None
        if request['operation_id'] != operation_id:
            raise InstallationPairingError('INSTALLATION_DETACH_RECEIPT_INVALID')
        return _verified(row, request, context)
    finally:
        connection.close()
