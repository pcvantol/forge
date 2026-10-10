"""Finite owner-issued Mission-result access, separate from prior approvals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import secrets

from .advisory_grant import project_scope
from .approved_worklist import identifier, timestamp
from .candidate_decision_grant import signer
from .governed_continuation import _mission_subject_revision
from .mission_final_acceptance_contract import CONTRACT, grant_bounds
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
from .workspace_worklist_control_grant import current_operator
from .workspace_review_grant import _locked, _private_bytes, _write_private, _new_token


@dataclass(frozen=True)
class FinalAcceptancePrincipal:
    principal_id: str
    instance_id: str
    project_id: str
    repository_id: str
    grant_id: str
    profile_id: str
    permissions: tuple
    missions: tuple
    maximum_acceptances: int
    operator_id: str
    operator_binding_version: int
    installation_id: str
    expires_at: str

    @property
    def reference(self) -> str:
        return 'forge-mission-final-acceptance-principal:v1:' + self.instance_id + ':' + self.principal_id


def authority_binding(root, instance_id, profile_id, permissions, principal_id):
    if profile_id != 'solo':
        raise PermissionError('existing Solo Business acceptance policy required')
    current_operator(root, instance_id)
    mapped = tuple('BUSINESS' if p == 'ACCEPT' else p for p in permissions)
    binding = signer(root, instance_id, profile_id, mapped, principal_id)
    if type(binding['operator_binding_version']) is not int or binding['operator_binding_version'] < 1:
        raise PermissionError('typed current operator binding required')
    return binding


class MissionFinalAcceptanceGrant:
    def __init__(self, root, instance_id):
        self.root = Path(root)
        self.instance_id = identifier(instance_id)
        self.path = self.root / 'credentials' / 'mission-final-acceptance' / 'grants.json'

    def _records(self, missing=False):
        if missing and not self.path.exists() and not self.path.is_symlink():
            return []
        document = json.loads(_private_bytes(self.path))
        if (not isinstance(document, dict)
                or set(document) != {'contract_version', 'instance_id', 'records'}
                or document['contract_version'] != CONTRACT
                or document['instance_id'] != self.instance_id
                or not isinstance(document['records'], list) or len(document['records']) > 64):
            raise ValueError('final-acceptance private grant store unavailable')
        ids, tokens = set(), set()
        for record in document['records']:
            if (not isinstance(record, dict)
                    or set(record) != set(FinalAcceptancePrincipal.__dataclass_fields__) | {'token_digest', 'state'}):
                raise ValueError('final-acceptance grant shape invalid')
            grant_bounds(record['permissions'], record['missions'], record['maximum_acceptances'])
            for key in ('principal_id', 'instance_id', 'project_id', 'repository_id',
                        'grant_id', 'installation_id', 'operator_id'):
                identifier(record[key])
            if (record['instance_id'] != self.instance_id or record['profile_id'] != 'solo'
                    or type(record['operator_binding_version']) is not int
                    or record['operator_binding_version'] < 1
                    or record['state'] not in ('ACTIVE', 'REVOKED')
                    or not isinstance(record['token_digest'], str)
                    or len(record['token_digest']) != 64
                    or any(c not in '0123456789abcdef' for c in record['token_digest'])
                    or record['grant_id'] in ids or record['token_digest'] in tokens):
                raise ValueError('final-acceptance grant binding invalid')
            timestamp(record['expires_at'])
            ids.add(record['grant_id'])
            tokens.add(record['token_digest'])
        return document['records']

    def _save(self, records):
        raw = json.dumps({'contract_version': CONTRACT, 'instance_id': self.instance_id,
                          'records': records}, sort_keys=True).encode()
        if len(records) > 64 or len(raw) > 65536:
            raise ValueError('final-acceptance private grant capacity exhausted')
        _write_private(self.path, raw)

    def issue(self, *, principal_id, project_id, repository_id, profile_id, permissions,
              missions, maximum_acceptances, expires_at, token_path):
        identifier(principal_id)
        grant_bounds(permissions, missions, maximum_acceptances)
        now = datetime.now(UTC)
        if not now < timestamp(expires_at) <= now + timedelta(days=30):
            raise ValueError('finite future final-acceptance expiry required')
        token_path = Path(token_path)
        if token_path.resolve() == self.path.resolve():
            raise ValueError('final-acceptance token/store collision')
        with _locked(self.path):
            binding = authority_binding(self.root, self.instance_id, profile_id, permissions, principal_id)
            scope = project_scope(self.root, self.instance_id)
            if (scope['project_id'], scope['repository_id']) != (project_id, repository_id):
                raise PermissionError('foreign final-acceptance project/repository')
            with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
                for mission in missions:
                    state = runtime.states.get(mission['mission_id'])
                    if _mission_subject_revision(state) != mission['subject_revision']:
                        raise PermissionError('final-acceptance Mission subject changed')
            records = self._records(missing=True)
            if len(records) >= 64:
                raise ValueError('final-acceptance private grant capacity exhausted')
            token = secrets.token_urlsafe(48)
            record = {**scope, **binding, 'principal_id': principal_id,
                      'grant_id': 'final-acceptance-' + secrets.token_hex(16),
                      'profile_id': profile_id, 'permissions': sorted(permissions),
                      'missions': json.loads(json.dumps(missions)),
                      'maximum_acceptances': maximum_acceptances,
                      'expires_at': expires_at, 'state': 'ACTIVE',
                      'token_digest': sha256(token.encode()).hexdigest()}
            _new_token(token_path, token)
            try:
                self._save([*records, record])
            except Exception:
                token_path.unlink(missing_ok=True)
                raise
            return {key: value for key, value in record.items() if key != 'token_digest'}

    def revoke(self, grant_id):
        identifier(grant_id)
        with _locked(self.path):
            authority_binding(self.root, self.instance_id, 'solo', ('READ',), None)
            records = self._records()
            record = next((r for r in records if r['grant_id'] == grant_id), None)
            if record is None:
                raise ValueError('unknown final-acceptance grant')
            record['state'] = 'REVOKED'
            self._save(records)
            return {'grant_id': grant_id, 'state': 'REVOKED'}

    def authenticate(self, authorization):
        if not isinstance(authorization, str) or not authorization.startswith('Bearer '):
            return None
        token = authorization[7:]
        if not token or len(token) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in token):
            return None
        try:
            records = self._records()
            matches = [r for r in records if secrets.compare_digest(
                r['token_digest'], sha256(token.encode()).hexdigest())]
            if len(matches) != 1:
                return None
            record = matches[0]
            if record['state'] != 'ACTIVE' or timestamp(record['expires_at']) <= datetime.now(UTC):
                return None
            return FinalAcceptancePrincipal(**{
                key: tuple(record[key]) if key in ('permissions', 'missions') else record[key]
                for key in FinalAcceptancePrincipal.__dataclass_fields__})
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def authorize(self, authorization, mission_id=None, permission='READ'):
        principal = self.authenticate(authorization)
        if principal is None or permission not in principal.permissions:
            raise PermissionError('final-acceptance capability unavailable')
        binding = authority_binding(self.root, self.instance_id, principal.profile_id,
                                    (permission,), principal.principal_id)
        scope = project_scope(self.root, self.instance_id)
        if (any(binding[key] != getattr(principal, key) for key in binding)
                or any(scope[key] != getattr(principal, key) for key in scope)):
            raise PermissionError('current final-acceptance actor/project binding changed')
        if mission_id is not None:
            subject = next((m for m in principal.missions if m['mission_id'] == mission_id), None)
            if subject is None:
                raise PermissionError('foreign final-acceptance Mission scope')
            with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
                if _mission_subject_revision(runtime.states.get(mission_id)) != subject['subject_revision']:
                    raise PermissionError('current final-acceptance Mission subject changed')
        return principal


def main(argv=None):
    """Supported owner setup derives instance/project/Mission revisions locally."""
    import argparse
    parser = argparse.ArgumentParser(prog='forge-mission-final-acceptance-grant')
    parser.add_argument('--data-root', required=True)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('identity')
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--mission-id', required=True)
    issue = commands.add_parser('issue')
    issue.add_argument('--principal-id')
    issue.add_argument('--mission-id', action='append', required=True)
    issue.add_argument('--permission', action='append', choices=['READ', 'ACCEPT'], required=True)
    issue.add_argument('--maximum-acceptances', type=int, required=True)
    issue.add_argument('--expires-at', required=True)
    issue.add_argument('--token-file', required=True)
    revoke = commands.add_parser('revoke')
    revoke.add_argument('--grant-id', required=True)
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        grant = MissionFinalAcceptanceGrant(instance.data_root, instance.instance_id)
        binding = authority_binding(grant.root, instance.instance_id, 'solo', ('READ',), None)
        scope = project_scope(grant.root, instance.instance_id)
        if args.action == 'revoke':
            result = grant.revoke(args.grant_id)
        elif args.action in ('identity', 'inspect'):
            result = {'contract_version': CONTRACT, **scope, **binding, 'read_only': True,
                      'supported_permissions': ['READ', 'ACCEPT'], 'required_role': 'business_owner'}
            if args.action == 'inspect':
                identifier(args.mission_id)
                with InstalledDynamicMissionRuntime.open_for_governance_read(str(grant.root)) as runtime:
                    state = runtime.states.get(args.mission_id)
                    result['mission'] = {'mission_id': state.mission_id,
                                         'subject_revision': _mission_subject_revision(state)}
        else:
            with InstalledDynamicMissionRuntime.open_for_governance_read(str(grant.root)) as runtime:
                missions = []
                for mission_id in args.mission_id:
                    identifier(mission_id)
                    state = runtime.states.get(mission_id)
                    missions.append({'mission_id': mission_id, 'subject_revision': _mission_subject_revision(state)})
            result = grant.issue(principal_id=args.principal_id or binding['operator_id'],
                project_id=scope['project_id'], repository_id=scope['repository_id'], profile_id='solo',
                permissions=args.permission, missions=missions, maximum_acceptances=args.maximum_acceptances,
                expires_at=args.expires_at, token_path=args.token_file)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, PermissionError, KeyError, TypeError):
        print(json.dumps({'contract_version': CONTRACT, 'error': {'code': 'FINAL_ACCEPTANCE_SETUP_UNAVAILABLE'}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
