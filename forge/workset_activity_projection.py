"""Bounded read projection of original records, never a historical backfill."""
from datetime import datetime, UTC
from hashlib import sha256
import json
import re
from pathlib import Path

from .advisory_contract import digest as ascii_digest
from .approved_worklist import candidate_source, identifier
from .governance_authority import _digest as governance_digest
from .models.criterion_observation import canonical_digest
from .operations_read_api import InstalledOperationsReadService, _parse_time, _safe_text, _redact
from .state.mission_state import MissionExecutionStatus
from .workset_order import effective_order, canonical_intent_effects
from .workset_activity_cursor import canonical, MAX_EVENTS
from .worklist_conditions import completion_facts

MAX_DOCUMENT_BYTES = 262144
MAX_SCAN_BYTES = 2097152
SOURCE_TYPES = ['WORKSET_DECISION', 'RELEASE_RECEIPT', 'CONTROL_INTENT', 'CONTROL_RECEIPT',
                'ORDER_INTENT', 'ORDER_DECISION', 'ORDER_RECEIPT', 'ACTIVATION_CLAIM',
                'MISSION_TRANSITION', 'EXECUTION_EXCHANGE', 'EXECUTION_RECEIPT', 'FINAL_ACCEPTANCE_DECISION']


def public_label(value):
    text = _safe_text(_redact(value))
    return re.sub(r'(?:file://|/Users/|/Volumes/|/private/|/tmp/|/home/|/var/|~/|[A-Za-z]:[\\/])[^\s,;]*',
                  '[PRIVATE_PATH_REDACTED]', text)


class ActivityUnavailable(ValueError):
    pass


class Sources:
    def __init__(self, db):
        self.db = db; self.bytes = 0; self.watermarks = {}; self.cache = {}

    def document(self, table, column, key, *, required=True):
        cache_key = (table, key)
        if cache_key in self.cache:
            return self.cache[cache_key]
        row = self.db.execute(f'SELECT substr(document,1,?) FROM {table} WHERE {column}=?',
                              (MAX_DOCUMENT_BYTES + 1, key)).fetchone()
        if row is None:
            if required:
                raise ActivityUnavailable('HISTORY_SOURCE_UNAVAILABLE')
            return None
        raw = row[0].encode(); self.bytes += len(raw)
        if len(raw) > MAX_DOCUMENT_BYTES or self.bytes > MAX_SCAN_BYTES:
            raise ActivityUnavailable('HISTORY_PARTIAL_CAPACITY')
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ActivityUnavailable('HISTORY_SOURCE_INVALID') from None
        if type(value) is not dict:
            raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
        self.watermarks[table + ':' + str(key)] = sha256(raw).hexdigest()
        self.cache[cache_key] = value
        return value

    def decision(self, key):
        value = self.document('governance_decisions', 'decision_id', key)
        stored = self.db.execute('SELECT digest FROM governance_decisions WHERE decision_id=?', (key,)).fetchone()
        if governance_digest(value) != stored[0] or value['decision_id'] != key:
            raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
        return value


def collect(root, principal, workset_id):
    events = []; seen = set(); labels = {}; limits = {'NO_BACKFILL_OF_MUTABLE_SNAPSHOTS'}
    by_source = {kind: 0 for kind in SOURCE_TYPES}
    def event(source, subject_kind, subject, key, original, fact, *, sequence=None,
              occurred=None, algorithm='UTF8', causes=(), details=None):
        identity = sha256(canonical([principal.instance_id, workset_id, source, subject, str(key), fact])).hexdigest()
        if identity in seen or len(events) >= MAX_EVENTS:
            raise ActivityUnavailable('HISTORY_PARTIAL_CAPACITY')
        if sequence is not None and (type(sequence) is not int or sequence < 1):
            raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
        if occurred is not None and (type(occurred) is not str or len(occurred) > 1000 or _parse_time(occurred) is None):
            raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
        if occurred is None:
            limits.add('ORIGINAL_TIME_UNKNOWN:' + source)
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,511}', str(key))
                or _redact(str(key)) != str(key)):
            raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
        source_digest = (governance_digest if algorithm == 'GOVERNANCE_ASCII' else
                         ascii_digest if algorithm == 'ASCII' else canonical_digest)(original)
        value = {'event_id': identity, 'kind': 'INTENT' if source.endswith('INTENT') else
                 'DECISION' if 'DECISION' in source else 'FACT', 'fact': fact,
                 'subject': {'kind': subject_kind, 'id': identifier(subject), 'label': labels.get(subject, 'Werklijst')},
                 'source_revision': sequence if sequence is not None else source_digest,
                 'source_digest': source_digest, 'digest_contract': algorithm,
                 'source_reference': {'kind': source, 'record_id': str(key),
                     'url': '/v1/approved-workset-activity/' + workset_id + '/events/' + identity},
                 'occurred_at': occurred, 'time_status': 'RECORDED' if occurred else 'UNKNOWN',
                 'sequence': sequence, 'causes': list(causes), 'details': details or {}}
        summaries = {'RELEASE_APPLIED': 'Toekomstige uitvoering expliciet vrijgegeven',
            'DISARM_APPLIED': 'Toekomstige vrijgave ingetrokken', 'CONTROL_INTENT_RECORDED': 'Wachtstandintentie vastgelegd; geen effectclaim',
            'HOLD_APPLIED': 'Wachtstand toegepast op toekomstig werk', 'UNHOLD_APPLIED': 'Wachtstand expliciet opgeheven',
            'ORDER_INTENT_RECORDED': 'Volgordewijziging aangevraagd; geen effectclaim',
            'ORDER_APPLIED': 'Volgorde expliciet gewijzigd', 'ACTIVATION_CLAIMED': 'Activatie geclaimd; uitvoering hiermee niet bewezen',
            'FORGE_SUBMISSION_SENT': 'Forge heeft een uitvoeringsaanvraag verzonden',
            'EP_SUBMISSION_RECEIPT_RECEIVED': 'EP heeft de uitvoeringsaanvraag bevestigd; geen resultaat- of acceptatieclaim',
            'EP_EXECUTION_RESULT': 'EP-uitvoeringsresultaat vastgelegd; geen Forge- of acceptatieclaim',
            'FORGE_RECONCILIATION_COMPLETE': 'Forge heeft terminaal uitvoeringsbewijs verwerkt',
            'HUMAN_FINAL_ACCEPTANCE_RECORDED': 'Business-eindacceptatie vastgelegd',
            'MISSION_TRANSITION': 'Opgeslagen Forge-toestand: ' + str((details or {}).get('to_status', '')),
            'WORKSET_BUSINESS_APPROVED': 'Business heeft de exacte werklijst goedgekeurd',
            'WORKSET_ARCHITECTURE_APPROVED': 'Architectuur heeft de exacte werklijst goedgekeurd',
            'ORDER_BUSINESS_APPROVED': 'Business heeft de exacte volgorde goedgekeurd',
            'ORDER_ARCHITECTURE_APPROVED': 'Architectuur heeft de exacte volgorde goedgekeurd'}
        value['summary'] = (summaries[fact] + ' — ' + value['subject']['label'])[:1000]
        seen.add(identity); events.append(value); by_source[source] += 1
        return identity

    db_identity = (Path(root) / 'forge.db').stat()
    with InstalledOperationsReadService(root)._runtime_snapshot() as (db, metadata):
        sources = Sources(db)
        value = sources.document('approved_worksets', 'workset_id', workset_id)
        generation = db.execute('SELECT dataset_generation FROM operational_reset_state WHERE singleton=1').fetchone()[0]
        if (type(generation) is not int or type(value['runtime_generation']) is not int
                or type(value['revision']) is not int or value['revision'] < 1
                or value['runtime_generation'] != generation
                or metadata['runtime_id'] != principal.instance_id
                or value['installation_id'] != principal.installation_id
                or canonical_digest(value['definition']) != value['definition_digest']):
            raise ActivityUnavailable('RESYNC_REQUIRED')
        effective_order(value, db)
        members = value['definition']['members']
        if type(members) is not list or not 1 <= len(members) <= 64:
            raise ActivityUnavailable('HISTORY_PARTIAL_CAPACITY')
        labels.update({m['candidate_id']: public_label(m['mission']['title'])[:512] for m in members})
        decision_events = {}
        def decision_event(source, decision_id, subject_kind, subject, fact):
            if decision_id in decision_events:
                return decision_events[decision_id]
            decision = sources.decision(decision_id)
            if decision['installation_id'] != principal.installation_id:
                raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
            result = event(source, subject_kind, subject, decision_id, decision, fact,
                           occurred=decision['occurred_at'], algorithm='GOVERNANCE_ASCII')
            decision_events[decision_id] = result
            return result
        for role, decision_id in value['decisions'].items():
            decision_event('WORKSET_DECISION', decision_id, 'WORKSET', workset_id,
                           'WORKSET_' + role.upper() + '_APPROVED')
        for key, receipt in value.get('release_commands', {}).items():
            if (key != receipt['operation_id'] or receipt['workset_id'] != workset_id
                    or receipt['definition_digest'] != value['definition_digest']
                    or receipt['intent'] not in ('release', 'disarm')
                    or receipt['workset_decisions'] != value['decisions']):
                raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
            event('RELEASE_RECEIPT', 'WORKSET', workset_id, key, receipt,
                  'RELEASE_APPLIED' if receipt['intent'] == 'release' else 'DISARM_APPLIED',
                  sequence=receipt['applied_revision'], occurred=receipt.get('observed_at'),
                  causes=[decision_events[d] for d in receipt['workset_decisions'].values()])
        for key, intent in value.get('control_operations', {}).items():
            from .worklist_control import canonical_request
            request = canonical_request(intent['request'])
            if (request['operation_id'] != key or request['workset_id'] != workset_id
                    or request['instance_id'] != principal.instance_id
                    or request['definition_revision'] != value['definition_digest']
                    or canonical_digest(request) != intent['request_digest']
                    or intent['state'] not in ('PENDING', 'APPLIED')):
                raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
            original = {'request': request, 'request_digest': intent['request_digest'],
                        'intent_revision': intent['intent_revision']}
            original_id = event('CONTROL_INTENT', 'WORKSET', workset_id, key, original,
                'CONTROL_INTENT_RECORDED', sequence=intent['intent_revision'],
                details={'requested_effect': request['intent'], 'effect_not_implied': True})
            if intent['state'] == 'APPLIED':
                receipt = intent['receipt']
                if canonical_digest(receipt) != intent['receipt_digest'] or receipt['outcome'] != 'APPLIED':
                    raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
                from .workspace_worklist_control_grant import ControlPrincipal
                from .worklist_control import _operation
                original_principal = ControlPrincipal(identifier(receipt['principal_id']), principal.instance_id,
                                                     (workset_id,), identifier(receipt['grant_id']))
                bindings = []
                for ref in intent['admission_bindings']:
                    state_doc = sources.document('mission_state', 'mission_id', ref['mission_id'])
                    admitted = state_doc.get('admission_contract') or {}
                    bindings.append({'kind': 'CANONICAL_CANDIDATE_INTAKE',
                        'candidate_id': admitted['candidate_id'], 'subject_revision': admitted['subject_revision'],
                        'mission_id': state_doc['mission_id'], 'installation_id': admitted['installation_id'],
                        'envelope_digest': admitted['envelope_digest']})
                _operation(value, key, original_principal, bindings)
                event('CONTROL_RECEIPT', 'WORKSET', workset_id, key, receipt,
                      request['intent'].upper() + '_APPLIED', sequence=receipt['effect']['workset_revision'],
                      occurred=receipt['effect'].get('observed_at'), causes=[original_id])
        for key, intent in value.get('order_intents', {}).items():
            original = {k: intent[k] for k in ('request', 'request_digest', 'created_at')}
            origin = event('ORDER_INTENT', 'WORKSET', workset_id, key, original,
                           'ORDER_INTENT_RECORDED', occurred=intent['created_at'], algorithm='ASCII',
                           details={'effect_not_implied': True})
            applied = intent.get('receipt')
            decisions = []
            for role, decision_id in canonical_intent_effects(db, intent).items():
                decisions.append(decision_event('ORDER_DECISION', decision_id, 'WORKSET', workset_id,
                                                'ORDER_' + role.upper() + '_APPROVED'))
            if applied is not None:
                event('ORDER_RECEIPT', 'WORKSET', workset_id, key, applied, 'ORDER_APPLIED',
                      sequence=applied['order_revision'], occurred=applied['applied_at'],
                      causes=[origin] + decisions,
                      details={'original_order': applied['original_order'], 'applied_order': applied['applied_order']})
        db.execute('ATTACH DATABASE ? AS activity_candidates', (candidate_source(Path(root)).resolve().as_uri() + '?mode=ro',))
        for member in members:
            candidate = member['candidate_id']; claim = value['claims'].get(candidate)
            allocation = sources.document('activity_candidates.allocations', 'candidate_id', candidate, required=False)
            mission_id = (claim or {}).get('mission_id') or (allocation or {}).get('mission_id')
            if claim:
                if claim['subject_revision'] != member['subject_revision'] or claim['runtime_generation'] != generation:
                    raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
                event('ACTIVATION_CLAIM', 'CANDIDATE', candidate, claim['operation_id'], claim,
                      'ACTIVATION_CLAIMED', sequence=claim['release_revision'], occurred=claim.get('claimed_at'),
                      details={'execution_start_not_implied': True})
            if not mission_id:
                limits.add('MISSION_HISTORY_NOT_AVAILABLE'); continue
            labels[mission_id] = public_label(member['mission']['title'])[:512]
            state = sources.document('mission_state', 'mission_id', mission_id)
            admission = state.get('admission_contract') or {}
            if (admission.get('candidate_id') != candidate or admission.get('subject_revision') != member['subject_revision']
                    or admission.get('installation_id') != principal.installation_id or state['mission_id'] != mission_id
                    or type(state['revision']) is not int or state['revision'] < 1):
                raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
            previous = None; last_sequence = 0
            for entry in state.get('state_history', []):
                if type(entry.get('sequence')) is not int or entry['sequence'] <= last_sequence or entry['sequence'] > state['revision']:
                    raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
                statuses = {value.value for value in MissionExecutionStatus}
                if entry['to_status'] not in statuses or entry['from_status'] is not None and entry['from_status'] not in statuses:
                    raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
                last_sequence = entry['sequence']
                fact = 'FORGE_RECONCILIATION_COMPLETE' if entry.get('reason') == 'completed_terminal_evidence_reconciled' else 'MISSION_TRANSITION'
                previous = event('MISSION_TRANSITION', 'MISSION', mission_id, str(entry['sequence']), entry, fact,
                    sequence=entry['sequence'], occurred=entry.get('occurred_at'), causes=[previous] if previous else [],
                    details={'from_status': entry['from_status'], 'to_status': entry['to_status']})
            if not state.get('state_history'):
                limits.add('LEGACY_MISSION_TIMELINE_UNKNOWN')
            for entry in state.get('execution_history', []):
                repository = entry.get('repository_evidence') or {}
                if repository.get('mission_id') != mission_id or repository.get('repository_id') != principal.repository_id:
                    raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
                receipt_id = identifier(entry['receipt_id'])
                if entry['outcome'] not in ('complete', 'failed', 'incomplete', 'blocked', 'cancelled'):
                    raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
                event('EXECUTION_RECEIPT', 'MISSION', mission_id, receipt_id, entry, 'EP_EXECUTION_RESULT',
                      occurred=entry.get('execution_completed_at'), details={'outcome': entry['outcome']})
            correlations = set()
            request = (state.get('execution_correlation') or {}).get('request')
            if request is not None:
                if request.get('mission_id') != mission_id or request.get('repository_id') != principal.repository_id:
                    raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
                correlations.add(identifier(request['correlation_id']))
            for execution in state.get('execution_history', []):
                correlations.add(identifier(execution['correlation_id']))
            for correlation in sorted(correlations):
                rows = db.execute('SELECT audit_id,correlation_id,direction,event_kind,occurred_at,substr(document,1,4097) FROM execution_host_exchange_audit WHERE correlation_id=? ORDER BY occurred_at,audit_id LIMIT ?',
                                  (correlation, MAX_EVENTS + 1)).fetchall()
                if not rows:
                    limits.add('EXECUTION_EXCHANGE_NOT_RETAINED')
                if len(rows) > MAX_EVENTS:
                    raise ActivityUnavailable('HISTORY_PARTIAL_CAPACITY')
                for row in rows:
                    raw = row[5].encode(); sources.bytes += len(raw)
                    if len(raw) > 4096 or sources.bytes > MAX_SCAN_BYTES:
                        raise ActivityUnavailable('HISTORY_PARTIAL_CAPACITY')
                    document = json.loads(raw)
                    if (document.get('correlation_id') != correlation or document.get('ep_project_id') != principal.project_id
                            or document.get('ep_repository_id') != principal.repository_id
                            or row[3] not in ('FORGE_SUBMISSION_SENT', 'EP_SUBMISSION_RECEIPT_RECEIVED')
                            or row[2] != ('FORGE_TO_EP' if row[3] == 'FORGE_SUBMISSION_SENT' else 'EP_TO_FORGE')):
                        raise ActivityUnavailable('HISTORY_SOURCE_INVALID')
                    audit = {'audit_id': row[0], 'correlation_id': row[1], 'direction': row[2],
                             'event_kind': row[3], 'occurred_at': row[4], 'document': document}
                    sources.watermarks['exchange:' + row[0]] = sha256(canonical(audit)).hexdigest()
                    event('EXECUTION_EXCHANGE', 'MISSION', mission_id, row[0], audit, row[3], occurred=row[4])
            completed, final, _ = completion_facts(db, state)
            approval = state.get('approval_record') or {}
            if completed and final == 'ACCEPTED':
                decision_event('FINAL_ACCEPTANCE_DECISION', approval['approval_id'], 'MISSION', mission_id,
                               'HUMAN_FINAL_ACCEPTANCE_RECORDED')
            elif state['status'] == 'COMPLETED':
                limits.add('FINAL_ACCEPTANCE_HISTORY_UNKNOWN')
        context = {'instance_id': principal.instance_id, 'installation_id': principal.installation_id,
                   'generation': generation, 'workset_id': workset_id, 'definition_digest': value['definition_digest'],
                   'reader': sha256(canonical([principal.reference, principal.grant_id])).hexdigest(),
                   'dataset_identity': sha256(canonical([db_identity.st_dev, db_identity.st_ino])).hexdigest()}
        stamp = sha256(canonical(sources.watermarks)).hexdigest()
    if (Path(root) / 'forge.db').stat().st_ino != db_identity.st_ino:
        raise ActivityUnavailable('RESYNC_REQUIRED')
    events.sort(key=lambda e: (_parse_time(e['occurred_at']) or datetime.max.replace(tzinfo=UTC), e['event_id']))
    coverage = {'offered_records': 'PARTIAL' if 'EXECUTION_EXCHANGE_NOT_RETAINED' in limits else 'COMPLETE_FOR_RETAINED_SOURCES', 'historical_extent': 'PARTIAL',
                'limitations': sorted(limits), 'source_counts': by_source,
                'ordering': 'STABLE_PRESENTATION_NOT_CROSS_SOURCE_CAUSAL_PROOF'}
    return events, context, stamp, coverage
