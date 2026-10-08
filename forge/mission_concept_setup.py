"""Finite owner provisioning for the selected chat-to-ready composition.

Uses existing advisory credentials and the actual G001 signer; a chat lens or
an old advice token cannot acquire approval capability by calling this module.
"""
import json
from datetime import UTC, datetime
from pathlib import Path
from .advisory_contract import digest
from .advisory_grant import AdvisoryGrant, project_scope
from .approved_worklist import timestamp
from .candidate_decision_grant import signer
from .mission_concept_contract import CONTRACT
from .mission_concept_planning import planning_profiles
from .workspace_review_grant import _locked, _private_bytes, _write_private
from .approved_worklist import identifier


class MissionConceptSetup:
    def __init__(self, root, instance_id):
        self.root = Path(root)
        self.instance_id = instance_id
        self.grant = AdvisoryGrant(root, instance_id)
        self.path = self.root / 'credentials' / 'mission-concepts' / 'setup.json'

    def _records(self):
        if not self.path.exists() and not self.path.is_symlink():
            return []
        value = json.loads(_private_bytes(self.path))
        if (not isinstance(value, dict) or set(value) != {'contract_version', 'records'}
                or value['contract_version'] != CONTRACT
                or not isinstance(value['records'], list) or len(value['records']) > 64):
            raise ValueError('mission setup unavailable')
        seen = set()
        for record in value['records']:
            keys = {'grant_id', 'principal_id', 'scope', 'profile_id', 'signer',
                    'profiles', 'maximum_missions', 'configuration_digest'}
            if not isinstance(record, dict) or set(record) != keys:
                raise ValueError('closed mission setup required')
            if record['grant_id'] in seen or record['configuration_digest'] != digest(
                    {k: v for k, v in record.items() if k != 'configuration_digest'}):
                raise ValueError('mission setup correlation differs')
            planning_profiles(record['profiles'])
            if type(record['maximum_missions']) is not int or not 1 <= record['maximum_missions'] <= 4:
                raise ValueError('finite Mission allowance required')
            seen.add(record['grant_id'])
        return value['records']

    def configure(self, *, grant_id, profiles, maximum_missions, profile_id='solo'):
        """Owning settings operation; never an automatic generation side effect."""
        planning_profiles(profiles)
        identifier(grant_id)
        if type(maximum_missions) is not int or not 1 <= maximum_missions <= 4:
            raise ValueError('finite Mission allowance required')
        with _locked(self.grant.path), _locked(self.path):
            actual = next((r for r in self.grant._records() if r['grant_id'] == grant_id), None)
            if (actual is None or actual['state'] != 'ACTIVE'
                    or timestamp(actual['expires_at']) <= datetime.now(UTC)):
                raise PermissionError('actual scoped grant required')
            scope = project_scope(self.root, self.instance_id)
            if any(actual[k] != scope[k] for k in scope):
                raise PermissionError('foreign Mission setup scope')
            binding = signer(self.root, self.instance_id, profile_id,
                             ('BUSINESS', 'ARCHITECTURE'), actual['principal_id'])
            record = {'grant_id': grant_id, 'principal_id': actual['principal_id'],
                      'scope': scope, 'profile_id': profile_id, 'signer': binding,
                      'profiles': profiles, 'maximum_missions': maximum_missions}
            record['configuration_digest'] = digest(record)
            records = self._records()
            old = next((r for r in records if r['grant_id'] == grant_id), None)
            if old is not None:
                if old != record:
                    raise ValueError('existing setup cannot expand or reset its bounds')
                return old
            if len(records) >= 64:
                raise ValueError('Mission setup capacity exhausted')
            raw = json.dumps({'contract_version': CONTRACT,
                              'records': [*records, record]}, sort_keys=True).encode()
            if len(raw) > 65536:
                raise ValueError('Mission setup byte capacity exhausted')
            _write_private(self.path, raw)
            return record

    def current(self, authorization, conversation_id=None):
        principal = self.grant.authorize(authorization, conversation_id)
        records = self._records()
        record = next((r for r in records if r['grant_id'] == principal.grant_id), None)
        if record is None or record['principal_id'] != principal.principal_id:
            raise PermissionError('owner-provisioned Mission capability required')
        if record['scope'] != {k: getattr(principal, k) for k in
                               ('instance_id', 'project_id', 'repository_id')}:
            raise PermissionError('Mission setup scope differs')
        binding = signer(self.root, self.instance_id, record['profile_id'],
                         ('BUSINESS', 'ARCHITECTURE'), principal.principal_id)
        if binding != record['signer']:
            raise PermissionError('Mission setup signer drifted')
        # Alias grants never increase the earliest retained principal allowance.
        allowance = min(r['maximum_missions'] for r in records
                        if r['principal_id'] == principal.principal_id
                        and r['scope'] == record['scope'])
        return principal, record, allowance


def main(argv=None):
    """One owner setup per project; normal Mission use needs no CLI fields."""
    import argparse
    parser = argparse.ArgumentParser(prog='forge-mission-concept-setup')
    parser.add_argument('--data-root', required=True)
    parser.add_argument('--grant-id', required=True)
    parser.add_argument('--profiles-file', required=True)
    parser.add_argument('--maximum-missions', type=int, required=True)
    parser.add_argument('--profile-id', default='solo')
    args = parser.parse_args(argv)
    try:
        from .server_runtime import existing_instance
        instance = existing_instance(args.data_root)
        profiles = json.loads(_private_bytes(Path(args.profiles_file)))
        configured = MissionConceptSetup(instance.data_root, instance.instance_id).configure(
            grant_id=args.grant_id, profiles=profiles, maximum_missions=args.maximum_missions,
            profile_id=args.profile_id)
        print(json.dumps({'contract_version': CONTRACT,
                          'configuration_digest': configured['configuration_digest'],
                          'maximum_missions': configured['maximum_missions'],
                          'supported_work_kinds': sorted(configured['profiles'])}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, PermissionError, RuntimeError):
        print(json.dumps({'contract_version': CONTRACT,
                          'error': {'code': 'MISSION_OWNER_SETUP_UNAVAILABLE'}}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
