"""One frozen user intent composed through the existing canonical services."""
from datetime import UTC, datetime
from .advisory_contract import digest, AdvisoryConflict
from .advisory_service import conversation_lock
from .advisory_context import AdvisoryContext
from .approved_worklist import candidate_source, identifier
from .mission_concept_contract import CONTRACT
from .mission_concept_setup import MissionConceptSetup
from .mission_concept_registration import candidate_objects, registration_receipt
from .advisory_candidate_contract import hash_reference
from .candidate_decision_contract import CONTRACT as DECISIONS, architecture_inputs
from .candidate_decision_service import decision_receipt, CandidateDecisionService
from .advisory_candidate_service import AdvisoryCandidateService
from .governed_candidate_intake import GovernedCandidateIntake
from .governance import resolve_governance_profile
from .lifecycle import RecommendationLifecycleStore
from .runtime.service import RuntimeServiceLock
from .workspace_review_grant import _locked
from .worklist_control import control_runtime
from .mission_concept_readiness import current_readiness
from .runtime.dynamic_mission import InstalledDynamicMissionRuntime


class MissionConceptApproval:
    def __init__(self, service):
        self.service = service
        self.root = service.root
        self.setup = MissionConceptSetup(self.root, service.grant.instance_id)

    def operation(self, authorization, conversation_id, operation_id):
        """Read actual partial/complete lineage without completing an effect."""
        identifier(operation_id)
        principal, configuration, _ = self.setup.current(authorization, conversation_id)
        from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
        with RecommendationLifecycleStore.read_only(candidate_source(self.root)) as store, \
                InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
            intent = store.candidate_registration_intent(operation_id, principal.reference)
            if intent is None:
                raise FileNotFoundError('unknown scoped composite operation')
            proposal = intent['proposal']
            if (proposal.get('contract_version') != CONTRACT
                    or proposal.get('conversation_id') != conversation_id
                    or proposal.get('principal_reference') != principal.reference):
                raise PermissionError('foreign compound operation')
            package = proposal['package']
            key = digest([principal.reference, principal.project_id, principal.repository_id,
                          conversation_id, proposal['proposal_id'], proposal['proposal_revision']])
            _, candidate = candidate_objects(proposal, key, intent['registered_at'])
            receipt = store.candidate_registration(key, principal.reference)
            if receipt is not None:
                expected = registration_receipt(principal.reference, receipt['operation_id'],
                    key, proposal, receipt['registered_at'])
                if digest(expected) != digest(receipt):
                    raise RuntimeError('compound registration receipt differs')
            decisions = {}
            for kind in ('BUSINESS', 'ARCHITECTURE'):
                decision_id = GovernedCandidateIntake._decision_id(kind.lower(), candidate.id,
                                                                   package['subject_revision'])
                decisions[kind] = CandidateDecisionService.checked_receipt(store, runtime, decision_id)
            allocation = store.allocation_for_recommendation(candidate.recommendation_id)
            present = (runtime.database._connection.execute(
                'SELECT 1 FROM mission_state WHERE mission_id=?',(allocation.mission_id,)).fetchone()
                if allocation else None)
            state = runtime.states.get(allocation.mission_id) if present else None
            if state is not None and (state.admission_contract or {}).get('subject_revision') != package['subject_revision']:
                raise RuntimeError('compound admitted subject differs')
            try:
                fresh = self.service.prepare(authorization, conversation_id,
                    proposal['proposal_revision']).get('package_digest') == digest(package)
            except AdvisoryConflict:
                fresh = False
            complete = receipt is not None and all(decisions.values()) and state is not None
            self.setup.current(authorization, conversation_id)
            return {'contract_version': CONTRACT, 'operation_id': operation_id,
                'state': 'COMPLETE' if complete else 'PENDING',
                'original_registration': receipt, 'package_digest': digest(package),
                'frozen_package': package,
                'business_decision': decisions['BUSINESS'], 'architecture_decision': decisions['ARCHITECTURE'],
                'candidate_id': candidate.id, 'mission_id': allocation.mission_id if allocation else None,
                'source_fresh': fresh, 'mission_status': state.status.value if state else None,
                'current_readiness': current_readiness(runtime, store, package, state, principal) if complete and fresh else None,
                'current_definition_state': 'APPROVED_WAITING' if complete and fresh else 'SUPERSEDED' if not fresh else 'PENDING',
                'execution_started': bool(state and state.actions), 'read_only': True,
                'additional_model_calls': 0}

    def approve(self, authorization, conversation_id, body):
        fields = {'contract_version', 'operation_id', 'revision', 'package_digest', 'confirm'}
        if (not isinstance(body, dict) or set(body) != fields
                or body['contract_version'] != CONTRACT or body['confirm'] is not True
                or type(body['revision']) is not int or body['revision'] < 1):
            raise ValueError('exact frozen approval intent required')
        identifier(body['operation_id']); hash_reference(body['package_digest'])
        principal, configuration, allowance = self.setup.current(authorization, conversation_id)
        with conversation_lock(self.service._path(principal, conversation_id)), \
                _locked(self.service.grant.path), _locked(self.setup.path), \
                _locked(AdvisoryContext(self.root, principal.instance_id).path), \
                RuntimeServiceLock(self.root / 'forge.db').acquire():
            prepared = self.service.prepare(authorization, conversation_id, body['revision'])
            if prepared['package'] is None or prepared['package_digest'] != body['package_digest']:
                raise AdvisoryConflict('APPROVAL_PACKAGE_CHANGED')
            package = prepared['package']
            principal, configuration, allowance = self.setup.current(authorization, conversation_id)
            if package['authority']['configuration_digest'] != configuration['configuration_digest']:
                # Replacement access can replay an exact COMPLETE operation only.
                # Never enter the mutation/recovery path or persist a new alias.
                current = self.operation(authorization, conversation_id, body['operation_id'])
                if (current['state'] != 'COMPLETE' or not current['source_fresh']
                        or current['package_digest'] != body['package_digest']):
                    raise PermissionError('complete original operation required')
                with RecommendationLifecycleStore.read_only(candidate_source(self.root)) as store, \
                        InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
                    bridge = GovernedCandidateIntake(store, runtime, resolve_governance_profile(configuration['profile_id']))
                    preview, planning = architecture_inputs(package['mission_preview'], package['planning'])
                    envelope = bridge.approved_envelope(current['candidate_id'], preview, planning)
                return {'contract_version': CONTRACT, 'operation_id': body['operation_id'],
                    'original_registration': current['original_registration'],
                    'package_digest': current['package_digest'], 'candidate_id': current['candidate_id'],
                    'mission_id': current['mission_id'], 'business_decision': current['business_decision'],
                    'architecture_decision': current['architecture_decision'],
                    'envelope_digest': envelope.digest, 'intake_subject_revision': package['subject_revision'],
                    'execution_started': current['execution_started'], 'additional_model_calls': 0,
                    'current': current['current_readiness']}
            candidate_guard_id = None

            def guard():
                actual = self.service.prepare(authorization, conversation_id, body['revision'])
                if actual.get('package_digest') != body['package_digest']:
                    raise PermissionError('frozen approval authority or source drifted')
                if candidate_guard_id is not None:
                    from .models.criterion_observation import canonical_digest
                    if canonical_digest(store.get_candidate(candidate_guard_id).to_dict()) != package['subject_revision']:
                        raise PermissionError('frozen Candidate subject drifted')

            source = package['source']
            proposal = {'contract_version': CONTRACT, 'principal_reference': principal.reference,
                **{k: getattr(principal, k) for k in ('instance_id', 'project_id', 'repository_id')},
                'conversation_id': conversation_id, 'proposal_id': source['object_id'],
                'proposal_revision': body['revision'], 'source': source, 'package': package,
                'field_origins': {'definition': 'VALIDATED_MODEL_PROPOSAL',
                                 'planning': 'TRUSTED_OWNER_CONFIGURATION'}}
            proposal['proposal_digest'] = digest(proposal)
            key = digest([principal.reference, principal.project_id, principal.repository_id,
                          conversation_id, proposal['proposal_id'], body['revision']])
            request = {'contract_version': CONTRACT, 'operation_id': body['operation_id'],
                **{k: proposal[k] for k in ('instance_id', 'project_id', 'repository_id',
                    'conversation_id', 'proposal_id', 'proposal_revision', 'proposal_digest')},
                'expected_conversation_revision': source['conversation_revision'],
                'context_revision': source['context_revision'], 'confirm': True}
            database_path = AdvisoryCandidateService(self.root, self.service.grant)._database_path(True)
            with control_runtime(self.root) as runtime, RecommendationLifecycleStore(database_path) as store:
                old = store.candidate_registration_intent(body['operation_id'], principal.reference)
                registered = store.candidate_registration(key, principal.reference)
                occurred_at = (old['registered_at'] if old else registered['registered_at'] if registered
                               else datetime.now(UTC).isoformat())
                intent = {'request': request, 'proposal': proposal, 'registered_at': occurred_at}
                # This immutable intent binds the complete compound effect package
                # before the first actual Candidate/governance/Intake store write.
                store.begin_candidate_registration(body['operation_id'], principal.reference, key, intent, allowance)
                guard()
                rec, candidate = candidate_objects(proposal, key, occurred_at)
                registered, _ = store.finish_candidate_registration(body['operation_id'], principal.reference,
                    key, rec, candidate, registration_receipt(principal.reference,
                    body['operation_id'], key, proposal, occurred_at))
                candidate_guard_id = candidate.id
                guard()
                bridge = GovernedCandidateIntake(store, runtime, resolve_governance_profile(configuration['profile_id']))
                preview, planning = architecture_inputs(package['mission_preview'], package['planning'])
                revision, business_id, architecture_id = bridge.decision_ids(candidate.id)
                if revision != package['subject_revision']:
                    raise AdvisoryConflict('APPROVAL_SUBJECT_CHANGED')
                for kind, decision_id in (('BUSINESS', business_id), ('ARCHITECTURE', architecture_id)):
                    guard()
                    decision_request = {'contract_version': DECISIONS,
                        'operation_id': 'concept-' + kind.lower() + '-' + key[7:39],
                        **{k: getattr(principal, k) for k in ('instance_id', 'project_id', 'repository_id')},
                        'candidate_id': candidate.id, 'subject_revision': revision, 'kind': kind,
                        'rationale': 'Explicit approval of the exact frozen Mission definition.', 'confirm': True}
                    if kind == 'BUSINESS':
                        decision_request['human_gates'] = list(planning.human_gates)
                    else:
                        business = runtime.repository.decision(business_id)
                        if CandidateDecisionService.checked_receipt(store, runtime, business_id) is None:
                            raise AdvisoryConflict('BUSINESS_PUBLICATION_REQUIRED')
                        decision_request.update(business_decision_id=business_id,
                            business_decision_digest=digest(business),
                            mission_preview=preview.to_dict(), planning=planning.to_dict())
                    binding = configuration['signer']
                    decision_intent = {'request': decision_request, 'request_digest': digest(decision_request),
                        'candidate': candidate.to_dict(), 'decision_id': decision_id,
                        'principal_reference': principal.reference, 'profile_id': configuration['profile_id'],
                        **binding, 'source_digest': digest(source), 'admitted_at': occurred_at}
                    store.begin_decision_operation(principal.reference, decision_request['operation_id'],
                        decision_id, decision_intent, min(8, allowance * 2))
                    if CandidateDecisionService.checked_receipt(store, runtime, decision_id) is None:
                        with store.atomic():
                            guard()
                            if kind == 'BUSINESS':
                                bridge.approve_business(candidate.id, actor='primary_operator',
                                    occurred_at=occurred_at, rationale=decision_request['rationale'],
                                    human_gates=planning.human_gates, effect_guard=guard)
                            else:
                                bridge.approve_architecture(candidate.id, preview, planning,
                                    actor='primary_operator', occurred_at=occurred_at,
                                    rationale=decision_request['rationale'], effect_guard=guard)
                            guard()
                            decision = runtime.repository.decision(decision_id)
                            evidence = next(e for e in store.history(rec.id)
                                            if e.kind == kind.lower() + '_decision')
                            store.finish_decision_operation(principal.reference,
                                decision_request['operation_id'], decision_id,
                                decision_receipt(decision_intent, decision, evidence))
                guard()
                envelope = bridge.approved_envelope(candidate.id, preview, planning)
                state = bridge.admit(candidate.id, preview, planning, occurred_at=occurred_at,
                                     effect_guard=guard)
                guard()
                return {'contract_version': CONTRACT, 'operation_id': body['operation_id'],
                    'original_registration': registered, 'package_digest': body['package_digest'],
                    'candidate_id': candidate.id, 'mission_id': state.mission_id,
                    'business_decision': CandidateDecisionService.checked_receipt(store, runtime, business_id),
                    'architecture_decision': CandidateDecisionService.checked_receipt(store, runtime, architecture_id),
                    'envelope_digest': envelope.digest, 'intake_subject_revision': revision,
                    'execution_started': False, 'additional_model_calls': 0,
                    'current': current_readiness(runtime, store, package, state, principal)}
