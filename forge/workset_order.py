"""One effective selector over immutable original members and audited amendments."""
from .approved_worklist import timestamp
from .advisory_contract import digest
from .governance_authority import _digest as governance_digest
from .models.criterion_observation import canonical_digest
from .workset_order_contract import (CONTRACT, PACKAGE_FIELDS, OrderConflict, exact_order, permutation,
                                     validate_package, confirm_request)


def validate_order_intent(intent, operation_id):
    fields = {'request', 'request_digest', 'principal_reference', 'grant_id', 'operator_id',
              'installation_id', 'created_at', 'phase_revision', 'state', 'decisions', 'receipt'}
    if (type(intent) is not dict or set(intent) != fields
            or confirm_request(intent['request']) != intent['request']
            or intent['request']['operation_id'] != operation_id
            or digest(intent['request']) != intent['request_digest']
            or digest(intent['request']['package']) != intent['request']['package_digest']
            or type(intent['phase_revision']) is not int or intent['phase_revision'] < 1
            or intent['state'] not in ('PENDING', 'APPLIED')
            or type(intent['decisions']) is not dict
            or not set(intent['decisions']).issubset({'business', 'architecture'})
            or (intent['state'] == 'APPLIED') != (intent['receipt'] is not None)):
        raise OrderConflict('ORIGINAL_ORDER_INTENT_INVALID')


def canonical_intent_effects(db, intent):
    """Read original authority from canonical evidence, including a partial commit."""
    import json
    request = intent['request']; package = request['package']; found = {}
    for role, capability in (('business', 'BUSINESS_APPROVAL'), ('architecture', 'ARCHITECTURE_APPROVAL')):
        decision_id = 'order:' + digest([intent['principal_reference'], request['workset_id'], request['package_digest'], role])[7:]
        row = db.execute('SELECT document,digest FROM governance_decisions WHERE decision_id=?', (decision_id,)).fetchone()
        if row is None:
            if role in intent['decisions']:
                raise ValueError('published order decision absent from canonical store')
            continue
        decision = json.loads(row[0])
        expected = {'decision_id': decision_id, 'subject_id': 'workset-order:' + request['workset_id'],
            'subject_revision': request['package_digest'], 'capability': capability, 'decision': 'approved',
            'scope': sorted(package['current_order']), 'gates': ['EXACT_REMAINING_ORDER', 'UNCHANGED_CLAIMED_PREFIX'],
            'predecessor_digest': None, 'operator_id': intent['operator_id'], 'installation_id': intent['installation_id'],
            'evidence': {'actor': 'primary_operator', 'grant_id': intent['grant_id'],
                'principal_reference': intent['principal_reference'], 'package_digest': request['package_digest'],
                'order_revision': package['order_revision'] + 1, 'request_digest': intent['request_digest'],
                'original_operation_id': request['operation_id']}}
        if (set(decision) != set(expected) | {'occurred_at'} or governance_digest(decision) != row[1]
                or type((decision.get('evidence') or {}).get('order_revision')) is not int
                or any(decision[k] != v for k, v in expected.items())
                or role in intent['decisions'] and intent['decisions'][role] != decision_id):
            raise ValueError('canonical order intent evidence changed')
        found[role] = decision_id
    return found


def original_order(value):
    members = value['definition']['members']
    if type(members) is not list:
        raise ValueError('original membership must be a list')
    return exact_order([m['candidate_id'] for m in members]) if members else []


def fixed_prefix(value, states):
    """Canonical intake alone does not consume a position in the serial selector."""
    members = value['definition']['members']
    claims = value['claims']
    if (type(claims) is not dict or not set(claims).issubset(m['candidate_id'] for m in members)
            or type(value['consumed_activations']) is not int
            or value['consumed_activations'] != len(claims)):
        raise OrderConflict('CLAIM_CONSUMPTION_AMBIGUOUS')
    locked = 0
    free = False
    for candidate in states:
        state = states[candidate]
        claimed = candidate in claims
        if state is not None and state['status'] != 'APPROVED_PLANNABLE' and not claimed:
            raise OrderConflict('UNCLAIMED_STARTED_MEMBER')
        if claimed:
            if free:
                raise OrderConflict('NON_SERIAL_CLAIM_PREFIX')
            locked += 1
        else:
            free = True
    if set(states) != set(m['candidate_id'] for m in members):
        raise OrderConflict('MEMBER_STATE_INCOMPLETE')
    return locked


def effective_order(value, db):
    """Never infer a fallback order from invalid or partially applied history."""
    order = original_order(value)
    amendments = value.get('order_amendments', [])
    if type(amendments) is not list or len(amendments) > 64:
        raise ValueError('finite order amendment history required')
    intents = value.get('order_intents', {})
    if type(intents) is not dict or len(intents) > 64:
        raise ValueError('finite order intent history required')
    for operation, intent in intents.items():
        validate_order_intent(intent, operation)
        package = intent['request']['package']
        if (package['workset_id'] != value['definition']['workset_id']
                or package['definition_digest'] != value['definition_digest']
                or package['authority_digest'] != value['authority_digest']
                or intent['installation_id'] != value['installation_id']
                or intent['phase_revision'] > value['revision']
                or intent['state'] == 'PENDING' and package['order_revision'] != len(amendments)):
            raise ValueError('original order intent lineage changed')
        if intent['state'] == 'APPLIED':
            matching = [a for a in amendments if a['receipt']['operation_id'] == operation]
            if (len(matching) != 1 or matching[0]['receipt'] != intent['receipt']
                    or matching[0]['package'] != package or matching[0]['grant_id'] != intent['grant_id']
                    or matching[0]['principal_reference'] != intent['principal_reference']):
                raise ValueError('applied original intent lacks its exact amendment')
        canonical_intent_effects(db, intent)
    # Missing partial intent data cannot silently restore the original selector.
    import json
    for row in db.execute('SELECT document FROM governance_decisions WHERE subject_id=?',
                          ('workset-order:' + value['definition']['workset_id'],)):
        decision = json.loads(row[0])
        if (decision.get('evidence') or {}).get('original_operation_id') not in intents:
            raise ValueError('orphan canonical order intent blocks selection')
    previous = canonical_digest(order)
    members = {m['candidate_id']: m for m in value['definition']['members']}
    for revision, amendment in enumerate(amendments, 1):
        fields = {'package', 'package_digest', 'grant_id', 'principal_reference', 'operator_id',
                  'installation_id', 'decisions', 'receipt', 'receipt_digest'}
        if type(amendment) is not dict or set(amendment) != fields:
            raise ValueError('order amendment shape changed')
        package = amendment['package']
        validate_package(package)
        if (type(package) is not dict or set(package) != PACKAGE_FIELDS
                or package['definition_digest'] != value['definition_digest']
                or package['authority_digest'] != value['authority_digest']
                or package['workset_id'] != value['definition']['workset_id']
                or type(package['order_revision']) is not int or package['order_revision'] != revision - 1
                or package['previous_order_digest'] != previous or package['current_order'] != order
                or digest(package) != amendment['package_digest']
                or package['expires_at'] != value['definition']['expires_at']
                or package['maximum_activations'] != value['definition']['maximum_activations']
                or type(package['consumed_activations']) is not int
                or package['consumed_activations'] > value['consumed_activations']
                or package['subjects'] != [{'candidate_id': c, 'subject_revision': members[c]['subject_revision']}
                                           for c in original_order(value)]):
            raise ValueError('original order amendment binding changed')
        new = permutation(order, package['proposed_order'], package['fixed_prefix'], members)
        if type(amendment['decisions']) is not dict or set(amendment['decisions']) != {'business', 'architecture'}:
            raise ValueError('two canonical order decisions required')
        for role, decision_id in amendment['decisions'].items():
            row = db.execute('SELECT document,digest FROM governance_decisions WHERE decision_id=?',
                             (decision_id,)).fetchone()
            if row is None:
                raise ValueError('order decision missing')
            import json
            decision = json.loads(row[0])
            if (governance_digest(decision) != row[1]
                    or decision['subject_id'] != 'workset-order:' + package['workset_id']
                    or decision['subject_revision'] != amendment['package_digest']
                    or decision['decision'] != 'approved'
                    or decision['capability'] != {'business': 'BUSINESS_APPROVAL',
                                                 'architecture': 'ARCHITECTURE_APPROVAL'}[role]
                    or decision['scope'] != sorted(order)
                    or decision['gates'] != ['EXACT_REMAINING_ORDER', 'UNCHANGED_CLAIMED_PREFIX']
                    or decision['installation_id'] != amendment['installation_id']
                    or decision['operator_id'] != amendment['operator_id']
                    or decision['evidence'] != {'actor': 'primary_operator',
                        'grant_id': amendment['grant_id'], 'principal_reference': amendment['principal_reference'],
                        'package_digest': amendment['package_digest'], 'order_revision': revision,
                        'request_digest': intents[amendment['receipt']['operation_id']]['request_digest'],
                        'original_operation_id': amendment['receipt']['operation_id']}):
                raise ValueError('canonical order decision differs')
        receipt = amendment['receipt']
        receipt_fields = {'contract_version', 'operation_id', 'workset_id', 'package_digest',
                          'order_revision', 'original_order', 'applied_order', 'fixed_prefix',
                          'decisions', 'consumed_activations', 'applied_at'}
        if (type(receipt) is not dict or set(receipt) != receipt_fields
                or receipt['contract_version'] != CONTRACT
                or type(receipt['order_revision']) is not int
                or type(receipt['consumed_activations']) is not int
                or type(receipt['fixed_prefix']) is not int
                or receipt['consumed_activations'] != package['consumed_activations']
                or receipt['fixed_prefix'] != package['fixed_prefix']
                or receipt['workset_id'] != package['workset_id']
                or receipt['operation_id'] not in intents or intents[receipt['operation_id']]['state'] != 'APPLIED'
                or amendment['installation_id'] != value['installation_id']
                or canonical_digest(receipt) != amendment['receipt_digest']
                or receipt['package_digest'] != amendment['package_digest']
                or receipt['original_order'] != order or receipt['applied_order'] != new
                or receipt['order_revision'] != revision
                or receipt['decisions'] != amendment['decisions']):
            raise ValueError('original order receipt changed')
        timestamp(receipt['applied_at'])
        order = new
        previous = canonical_digest(order)
    return order, len(amendments), previous
