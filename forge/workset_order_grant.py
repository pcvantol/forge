"""Finite revocable order authority, distinct from release, hold and admin."""
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import secrets

from .advisory_grant import project_scope
from .approved_worklist import identifier, timestamp
from .candidate_decision_grant import signer
from .operations_read_api import InstalledOperationsReadService
from .models.criterion_observation import canonical_digest
from .workspace_worklist_control_grant import current_operator
from .workspace_review_grant import _locked, _private_bytes, _write_private, _new_token
from .workset_order_contract import CONTRACT, grant_bounds


@dataclass(frozen=True)
class OrderPrincipal:
    principal_id: str
    instance_id: str
    project_id: str
    repository_id: str
    grant_id: str
    profile_id: str
    permissions: tuple
    worksets: tuple
    maximum_amendments: int
    operator_id: str
    operator_binding_version: int
    installation_id: str
    expires_at: str

    @property
    def reference(self):
        return 'forge-workset-order-principal:v1:' + self.instance_id + ':' + self.principal_id


def authority_binding(root, instance_id, permissions, principal_id):
    current_operator(root, instance_id)
    needed = ('BUSINESS', 'ARCHITECTURE') if 'REORDER' in permissions else ('READ',)
    return signer(root, instance_id, 'solo', needed, principal_id)


def scoped_workset(root, scope, workset_id, definition_digest=None):
    """Bind actual canonical approved members to the existing project scope."""
    identifier(workset_id)
    with InstalledOperationsReadService(root)._runtime_snapshot() as (db, metadata):
        row = db.execute('SELECT document FROM approved_worksets WHERE workset_id=?', (workset_id,)).fetchone()
        if row is None or metadata['runtime_id'] != scope['instance_id']:
            raise PermissionError('order workset unavailable in this instance')
        value = json.loads(row[0])
        if (value['installation_id'] != metadata['installation_id']
                or value['definition']['profile_id'] != 'solo'
                or type(value['definition']['members']) is not list or not 1 <= len(value['definition']['members']) <= 64
                or canonical_digest(value['definition']) != value['definition_digest']
                or definition_digest is not None and definition_digest != value['definition_digest']):
            raise PermissionError('original order subject binding changed')
    from .workset_release_subjects import approved_subject
    for member in value['definition']['members']:
        actual = approved_subject(root, scope, member['candidate_id'], member['subject_revision'], profile_id='solo')
        if (member['mission'] != actual['mission'] or member['planning'] != actual['planning']
                or member['dependencies'] != [d['candidate_id'] for d in actual['dependency_bindings']]):
            raise PermissionError('original member planning or dependency binding changed')
    return value


class WorksetOrderGrant:
    def __init__(self, root, instance_id):
        self.root, self.instance_id = Path(root), identifier(instance_id)
        self.path = self.root / 'credentials' / 'workset-order' / 'grants.json'

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():
            return []
        value = json.loads(_private_bytes(self.path))
        if (type(value) is not dict or set(value) != {'contract_version', 'instance_id', 'records'}
                or value['contract_version'] != CONTRACT or value['instance_id'] != self.instance_id
                or type(value['records']) is not list or len(value['records']) > 64):
            raise ValueError('order grant store invalid')
        ids, tokens = set(), set()
        for record in value['records']:
            if type(record) is not dict or set(record) != set(OrderPrincipal.__dataclass_fields__) | {'state', 'token_digest'}:
                raise ValueError('closed order grant record required')
            grant_bounds(record['permissions'], record['worksets'], record['maximum_amendments'])
            for key in ('principal_id', 'instance_id', 'project_id', 'repository_id', 'grant_id', 'operator_id', 'installation_id'):
                identifier(record[key])
            token = record['token_digest']
            if (record['instance_id'] != self.instance_id or record['profile_id'] != 'solo'
                    or type(record['operator_binding_version']) is not int or record['operator_binding_version'] < 1
                    or record['state'] not in ('ACTIVE', 'REVOKED') or record['grant_id'] in ids
                    or type(token) is not str or len(token) != 64
                    or any(c not in '0123456789abcdef' for c in token) or token in tokens):
                raise ValueError('order grant identity invalid')
            timestamp(record['expires_at'])
            ids.add(record['grant_id']); tokens.add(token)
        return value['records']

    def _save(self, records):
        raw = json.dumps({'contract_version': CONTRACT, 'instance_id': self.instance_id,
                          'records': records}, sort_keys=True).encode()
        if len(records) > 64 or len(raw) > 65536:
            raise ValueError('order private grant capacity exhausted')
        _write_private(self.path, raw)

    def issue(self, *, principal_id, project_id, repository_id, permissions, worksets,
              maximum_amendments, expires_at, token_path):
        identifier(principal_id)
        grant_bounds(permissions, worksets, maximum_amendments)
        if not datetime.now(UTC) < timestamp(expires_at) <= datetime.now(UTC) + timedelta(days=30):
            raise ValueError('finite future order expiry required')
        path = Path(token_path)
        if path.resolve() == self.path.resolve():
            raise ValueError('order token/store collision')
        with _locked(self.path):
            binding = authority_binding(self.root, self.instance_id, permissions, principal_id)
            scope = project_scope(self.root, self.instance_id)
            if (scope['project_id'], scope['repository_id']) != (project_id, repository_id):
                raise PermissionError('foreign order project scope')
            for subject in worksets:
                value = scoped_workset(self.root, scope, **subject)
                if timestamp(expires_at) > timestamp(value['definition']['expires_at']):
                    raise ValueError('order authority cannot extend original workset expiry')
            records = self._records(missing=True)
            if 'REORDER' in permissions and any(r['principal_id'] == principal_id and 'REORDER' in r['permissions']
                    and r['maximum_amendments'] != maximum_amendments for r in records):
                raise ValueError('replacement order grant cannot change the existing principal ceiling')
            token = secrets.token_urlsafe(48)
            record = {**scope, **binding, 'principal_id': principal_id, 'profile_id': 'solo',
                'grant_id': 'workset-order-' + secrets.token_hex(16), 'permissions': sorted(permissions),
                'worksets': json.loads(json.dumps(worksets)), 'maximum_amendments': maximum_amendments,
                'expires_at': expires_at, 'state': 'ACTIVE', 'token_digest': sha256(token.encode()).hexdigest()}
            _new_token(path, token)
            try:
                self._save([*records, record])
            except Exception:
                path.unlink(missing_ok=True)
                raise
            return {k: v for k, v in record.items() if k != 'token_digest'}

    def authenticate(self, authorization):
        if type(authorization) is not str or not authorization.startswith('Bearer '):
            return None
        token = authorization[7:]
        if not token or len(token) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            return None
        try:
            matches = [r for r in self._records() if secrets.compare_digest(r['token_digest'], sha256(token.encode()).hexdigest())]
            if len(matches) != 1:
                return None
            record = matches[0]
            if record['state'] != 'ACTIVE' or timestamp(record['expires_at']) <= datetime.now(UTC):
                return None
            return OrderPrincipal(**{k: tuple(record[k]) if k in ('permissions', 'worksets') else record[k]
                                     for k in OrderPrincipal.__dataclass_fields__})
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def authorize(self, authorization, workset_id=None, permission='READ'):
        principal = self.authenticate(authorization)
        if principal is None or permission not in principal.permissions:
            raise PermissionError('order capability unavailable')
        binding = authority_binding(self.root, self.instance_id, (permission,), principal.principal_id)
        scope = project_scope(self.root, self.instance_id)
        if (any(binding[k] != getattr(principal, k) for k in binding)
                or any(scope[k] != getattr(principal, k) for k in scope)):
            raise PermissionError('current order actor or project binding changed')
        if workset_id is not None:
            subject = next((s for s in principal.worksets if s['workset_id'] == workset_id), None)
            if subject is None:
                raise PermissionError('foreign order workset scope')
            scoped_workset(self.root, scope, **subject)
        return principal

    def revoke(self, grant_id):
        identifier(grant_id)
        with _locked(self.path):
            authority_binding(self.root, self.instance_id, ('READ',), None)
            records = self._records()
            record = next((r for r in records if r['grant_id'] == grant_id), None)
            if record is None:
                raise ValueError('unknown order grant')
            record['state'] = 'REVOKED'; self._save(records)
            return {'grant_id': grant_id, 'state': 'REVOKED'}


def activation_authority(root, value):
    """Revocation stops future selection, never replaces the effective order."""
    amendments = value.get('order_amendments', [])
    if not amendments:
        return
    latest = amendments[-1]
    package = latest['package']
    grant = WorksetOrderGrant(root, package['instance_id'])
    record = next((r for r in grant._records() if r['grant_id'] == latest['grant_id']), None)
    if (record is None or record['state'] != 'ACTIVE' or 'REORDER' not in record['permissions']
            or timestamp(record['expires_at']) <= datetime.now(UTC)):
        raise PermissionError('ORDER_AUTHORITY_NOT_CURRENT')
    binding = authority_binding(root, package['instance_id'], ('REORDER',), record['principal_id'])
    scope = project_scope(root, package['instance_id'])
    if (any(record[k] != v for k, v in binding.items()) or any(record[k] != v for k, v in scope.items())
            or {'workset_id': package['workset_id'], 'definition_digest': value['definition_digest']} not in record['worksets']
            or latest['principal_reference'] != OrderPrincipal(**{k: tuple(record[k]) if k in ('permissions', 'worksets') else record[k]
                                                                for k in OrderPrincipal.__dataclass_fields__}).reference):
        raise PermissionError('ORDER_AUTHORITY_BINDING_CHANGED')


@contextmanager
def activation_order_lease(root, value):
    """Order revocation and a new runtime claim have one linearized boundary."""
    if not value.get('order_amendments'):
        yield
        return
    package = value['order_amendments'][-1]['package']
    grant = WorksetOrderGrant(root, package['instance_id'])
    with _locked(grant.path):
        activation_authority(root, value)
        yield


def main(argv=None):
    """Supported private owner setup derives the actual original workset digest."""
    import argparse
    parser = argparse.ArgumentParser(prog='forge-workset-order-grant')
    parser.add_argument('--data-root', required=True)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('identity')
    inspect = commands.add_parser('inspect'); inspect.add_argument('--workset-id', required=True)
    issue = commands.add_parser('issue')
    issue.add_argument('--workset-id', action='append', required=True)
    issue.add_argument('--principal-id')
    issue.add_argument('--permission', action='append', choices=['READ', 'REORDER'], required=True)
    issue.add_argument('--maximum-amendments', type=int, required=True)
    issue.add_argument('--expires-at', required=True); issue.add_argument('--token-file', required=True)
    revoke = commands.add_parser('revoke'); revoke.add_argument('--grant-id', required=True)
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        grant = WorksetOrderGrant(instance.data_root, instance.instance_id)
        scope = project_scope(grant.root, instance.instance_id)
        binding = authority_binding(grant.root, instance.instance_id, ('READ',), None)
        if args.action == 'revoke':
            result = grant.revoke(args.grant_id)
        elif args.action in ('identity', 'inspect'):
            result = {'contract_version': CONTRACT, **scope, **binding, 'read_only': True,
                      'supported_permissions': ['READ', 'REORDER'],
                      'required_roles': ['business_owner', 'platform_architect']}
            if args.action == 'inspect':
                value = scoped_workset(grant.root, scope, args.workset_id)
                result['workset'] = {'workset_id': args.workset_id, 'definition_digest': value['definition_digest'],
                                    'expires_at': value['definition']['expires_at']}
        else:
            subjects = [{'workset_id': key, 'definition_digest': scoped_workset(grant.root, scope, key)['definition_digest']}
                        for key in args.workset_id]
            result = grant.issue(principal_id=args.principal_id or binding['operator_id'],
                project_id=scope['project_id'], repository_id=scope['repository_id'], permissions=args.permission,
                worksets=subjects, maximum_amendments=args.maximum_amendments,
                expires_at=args.expires_at, token_path=args.token_file)
        print(json.dumps(result, sort_keys=True)); return 0
    except (OSError, ValueError, RuntimeError, PermissionError, KeyError, TypeError):
        print(json.dumps({'contract_version': CONTRACT, 'error': {'code': 'ORDER_SETUP_UNAVAILABLE'}})); return 1


if __name__ == '__main__':
    raise SystemExit(main())
