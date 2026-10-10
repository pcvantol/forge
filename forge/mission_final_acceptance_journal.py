"""Bounded private original intents; canonical governance remains the authority."""
from __future__ import annotations

import json

from .advisory_contract import digest
from .mission_final_acceptance_contract import CONTRACT, acceptance_request
from .workset_release_journal import private_packet
from .workspace_review_grant import _write_private


class FinalAcceptanceJournal:
    def __init__(self, root, principal_reference):
        self.reference = principal_reference
        self.path = root / 'governance' / 'mission-final-acceptance' / (digest(principal_reference)[7:] + '.json')

    def read(self):
        if not self.path.exists() and not self.path.is_symlink():
            return {'contract_version': CONTRACT, 'principal_reference': self.reference,
                    'intents': {}, 'operations': {}}
        value = json.loads(private_packet(self.path))
        if (not isinstance(value, dict)
                or set(value) != {'contract_version', 'principal_reference', 'intents', 'operations'}
                or value['contract_version'] != CONTRACT or value['principal_reference'] != self.reference
                or not isinstance(value['intents'], dict) or len(value['intents']) > 16
                or not isinstance(value['operations'], dict) or len(value['operations']) > 128):
            raise ValueError('final-acceptance original intent store unavailable')
        for key, intent in value['intents'].items():
            if (not isinstance(intent, dict) or set(intent) != {
                    'original_request', 'request_digest', 'package', 'package_digest',
                    'grant_id', 'decision_id', 'created_at', 'receipt', 'receipt_digest'}
                    or acceptance_request(intent['original_request']) != intent['original_request']
                    or digest(intent['original_request']) != intent['request_digest']
                    or digest(intent['package']) != intent['package_digest']
                    or intent['original_request']['package_digest'] != intent['package_digest']
                    or key != intent['original_request']['mission_id']
                    or intent['package']['principal_reference'] != self.reference
                    or intent['package']['mission_id'] != key
                    or (intent['receipt'] is None) != (intent['receipt_digest'] is None)
                    or (intent['receipt'] is not None and digest(intent['receipt']) != intent['receipt_digest'])):
                raise ValueError('final-acceptance original intent integrity failed')
        for operation, record in value['operations'].items():
            if (not isinstance(record, dict) or set(record) != {'request', 'request_digest', 'mission_id'}
                    or acceptance_request(record['request']) != record['request']
                    or record['request']['operation_id'] != operation
                    or record['request']['mission_id'] != record['mission_id']
                    or record['mission_id'] not in value['intents']
                    or digest(record['request']) != record['request_digest']):
                raise ValueError('final-acceptance operation integrity failed')
        return value

    def save(self, value):
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        if len(value['intents']) > 16 or len(value['operations']) > 128 or len(raw) > 524288:
            raise ValueError('final-acceptance original intent capacity exhausted')
        _write_private(self.path, raw)
