"""Immutable generated concepts on the existing durable finite turn engine."""
from .advisory_service import AdvisoryService
from .advisory_contract import digest, AdvisoryConflict
from .mission_concept_contract import CONTRACT, refine_request, proposed_definition
from .mission_concept_provider import MissionConceptProvider
from urllib.parse import urlsplit, parse_qs
from .mission_concept_setup import MissionConceptSetup
from .mission_concept_planning import derive_package
from .models.criterion_observation import canonical_digest



class MissionConceptService(AdvisoryService):
    contract = CONTRACT
    provider_type = MissionConceptProvider
    parse_request = staticmethod(refine_request)

    def _path(self, principal, conversation_id):
        # Distinct provenance contract, shared principal consumption ledger.
        old = super()._path(principal, conversation_id)
        return old.with_name('concept-' + old.name)

    def turn_context(self, principal, request):
        return self.context(principal, request['selected_sources'], request['conversation_id'])

    def context(self, principal, selections=None, conversation_id=None):
        value, _ = super().context(principal, selections)
        from .execution_host_configuration import read_peer_configuration
        binding = read_peer_configuration(self.root).configuration
        if binding is None or binding.ep_project_id != principal.project_id or binding.ep_repository_id != principal.repository_id:
            raise PermissionError('actual repository planning binding required')
        value['concept_repository_source'] = {'repository_id': principal.repository_id,
                                              'github_repository': binding.repository_identity}
        # No dependencies can be invented before an authorized catalog exists.
        dependencies = self._dependency_catalog(principal, conversation_id)
        value['concept_dependency_references'] = [r['candidate_id'] for r in dependencies]
        value['concept_dependency_catalog'] = dependencies
        # Historical own subjects remain integrity nodes, never selectable self-dependencies.
        value['concept_dependency_graph'] = {r['candidate_id']:r['dependencies']
            for r in self._dependency_catalog(principal,None)}
        records = MissionConceptSetup(self.root, principal.instance_id)._records()
        configured = next((r for r in records if r['grant_id'] == principal.grant_id
                           and r['principal_id'] == principal.principal_id
                           and r['scope'] == {k: getattr(principal, k) for k in
                               ('instance_id', 'project_id', 'repository_id')}), None)
        value['concept_work_profiles'] = configured['profiles'] if configured else {}
        value['concept_configuration_revision'] = configured['configuration_digest'] if configured else None
        return value, digest(value)

    def _dependency_catalog(self, principal, exclude_conversation):
        from .advisory_candidate_service import AdvisoryCandidateService
        from .lifecycle import RecommendationLifecycleStore
        from .mission_concept_registration import registration_receipt
        import json
        path = AdvisoryCandidateService(self.root, self.grant)._database_path()
        if not path.exists():
            return []
        with RecommendationLifecycleStore.read_only(path) as store:
            if store._connection.execute('SELECT 1 FROM sqlite_master WHERE name=?',
                    ('advisory_candidate_registrations',)).fetchone() is None:
                return []
            rows = store._connection.execute('SELECT document FROM advisory_candidate_registrations WHERE principal=?',
                                            (principal.reference,)).fetchall()
            result = []
            for row in rows:
                receipt = json.loads(row[0])
                if receipt.get('contract_version') != CONTRACT:
                    continue
                _, proposal = store.registered_candidate_source(receipt['candidate']['id'])
                if (proposal['conversation_id'] == exclude_conversation
                        or proposal['conversation_id'] not in principal.conversation_ids
                        or any(proposal[k] != getattr(principal,k) for k in ('instance_id','project_id','repository_id'))):
                    continue
                expected = registration_receipt(principal.reference, receipt['operation_id'],
                    receipt['registration_key'], proposal, receipt['registered_at'])
                if digest(expected) != digest(receipt):
                    raise RuntimeError('dependency source integrity differs')
                candidate = store.get_candidate(receipt['candidate']['id'])
                if canonical_digest(candidate.to_dict()) != proposal['package']['subject_revision']:
                    raise AdvisoryConflict('DEPENDENCY_SUBJECT_CHANGED')
                result.append({'candidate_id':candidate.id,'subject_revision':proposal['package']['subject_revision'],
                    'object_id':proposal['proposal_id'],'concept_revision':proposal['proposal_revision'],
                    'title':candidate.title,'dependencies':list(candidate.dependencies),
                    'recommendation_status':store.get_recommendation(candidate.recommendation_id).status.value})
            return sorted(result, key=lambda r:r['candidate_id'])

    @staticmethod
    def validate_result(document, admitted, references):
        definition = proposed_definition(
            document, admitted['request_digest'],
            admitted['context']['concept_dependency_references'],
            admitted['context'].get('concept_work_profiles'))
        return {'contract_version': CONTRACT,
                'request_digest': admitted['request_digest'],
                'definition': definition}

    def capability(self, authorization, selections=None):
        value = super().capability(authorization, selections)
        value['supported_operations'] = ['REFINE', 'READ', 'CANCEL_REQUEST']
        value['approval_supported'] = False
        value['readiness_qualified'] = False
        value['generated_content_origin'] = 'VALIDATED_MODEL_PROPOSAL'
        value['workspace_reference_resolution_supported'] = False
        try:
            _, configuration, allowance = MissionConceptSetup(self.root, self.grant.instance_id).current(authorization)
            value['approval_supported'] = True
            value['workspace_reference_resolution_supported'] = True
            value['supported_operations'].extend(['PREPARE', 'APPROVE', 'READ_OPERATION'])
            value['maximum_missions'] = allowance
            value['supported_work_kinds'] = sorted(configuration['profiles'])
        except PermissionError:
            value['maximum_missions'] = 0
            value['supported_work_kinds'] = []
        return value

    def prepare(self, authorization, conversation_id, revision=None):
        """Resolve trusted limits and freeze the same complete visible definition."""
        setup = MissionConceptSetup(self.root, self.grant.instance_id)
        principal, configuration, allowance = setup.current(authorization, conversation_id)
        context, context_revision = self.context(principal, conversation_id=conversation_id)
        history = self._read(self._path(principal, conversation_id), principal,
                             conversation_id, context)
        complete = [t for t in history['turns'] if t['status'] == 'COMPLETE']
        if revision is None:
            revision = len(complete)
        if type(revision) is not int or not 1 <= revision <= len(complete):
            raise FileNotFoundError('unknown concept revision')
        turn = complete[revision - 1]
        # Catalog growth is not a change to this exact subject. Recheck all
        # admitted owner/source bounds and only the actually referenced subjects.
        context, _ = self.context(principal, turn['request']['selected_sources'], conversation_id)
        catalogs = {'concept_dependency_references', 'concept_dependency_catalog', 'concept_dependency_graph'}
        admitted_base = {k:v for k,v in turn['context'].items() if k not in catalogs}
        current_base = {k:v for k,v in context.items() if k not in catalogs}
        actual_dependencies = {r['candidate_id']:r['subject_revision']
                               for r in context['concept_dependency_catalog']}
        old_dependencies = {r['candidate_id']:r['subject_revision']
                            for r in turn['context']['concept_dependency_catalog']}
        changed_dependency = any(actual_dependencies.get(ref) != old_dependencies.get(ref)
            for ref in turn['outcome']['output']['definition']['dependencies'])
        if (revision != len(complete) or admitted_base != current_base or changed_dependency
                or history['turns'][-1]['status'] in {'REASONING', 'REVIEW', 'CANCEL_REQUESTED'}):
            raise AdvisoryConflict('CONCEPT_OR_CONTEXT_CHANGED')
        from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
        from .advisory_provider import AdvisoryProvider
        from .planner.codex_cli_session import _policy_digest
        with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
            policy = AdvisoryProvider(runtime, self.provider_id).configuration.current_policy()
            if _policy_digest(policy) != turn['provider']['policy_digest']:
                raise AdvisoryConflict('CONCEPT_PROVIDER_POLICY_CHANGED')
        object_id = 'concept-' + digest([principal.reference,
                              history['scope'], conversation_id])[7:39]
        prepared = derive_package(turn['outcome']['output']['definition'],
            request_digest=turn['request_digest'], context=turn['context'],
            profiles=configuration['profiles'], object_id=object_id, revision=revision,
            provider_bounds=turn['provider'])
        if prepared['package'] is not None:
            prepared['package']['authority'] = {
                'principal_reference': principal.reference,
                'configuration_digest': configuration['configuration_digest'],
                'profile_id': configuration['profile_id'], 'signer': configuration['signer'],
                'maximum_missions': allowance}
            prepared['package']['source']['conversation_id'] = conversation_id
            # Bind the accepted turn's durable phase writes, not unrelated failed
            # attempts recorded later. Complete turns have these exact phases.
            prepared['package']['source']['conversation_revision'] = (
                turn['request']['expected_revision'] + sum(phase in
                    {'REASONING', 'REVIEW', 'COMPLETE'} for phase in turn['lifecycle']))
            prepared['package']['source'].update(
                turn_id=turn['request']['turn_id'], session_id=turn['session_id'],
                invocation_id=turn['invocation_id'], result_digest=turn['outcome']['result_digest'])
            prepared['package_digest'] = digest(prepared['package'])
        setup.current(authorization, conversation_id)
        prepared['read_only'] = True
        prepared['additional_model_calls'] = 0
        return prepared

    def catalog(self, authorization, *, cursor=0, limit=4, expected_snapshot=None):
        """Project only the caller's admitted canonical concept turns.

        Snapshot-bound pagination cannot silently join different revisions.
        This stage exposes unresolved owning conditions, never synthesized READY.
        """
        principal = self.grant.authorize(authorization)
        if type(cursor) is not int or cursor < 0 or type(limit) is not int or not 1 <= limit <= 4:
            raise ValueError('bounded catalog cursor required')
        items = []
        context, _ = self.context(principal)
        for conversation_id in sorted(principal.conversation_ids):
            path = self._path(principal, conversation_id)
            if not path.exists() and not path.is_symlink():
                continue
            history = self._read(path, principal, conversation_id, context)
            complete = [t for t in history['turns'] if t['status'] == 'COMPLETE']
            if not complete:
                continue
            turn = complete[-1]
            definition = turn['outcome']['output']['definition']
            item = {
                'object_id': 'concept-' + digest([principal.reference,
                              history['scope'], conversation_id])[7:39],
                'conversation_id': conversation_id,
                'revision': len(complete), 'conversation_revision': history['revision'],
                'definition_digest': digest(definition), 'definition': definition,
                'source_turn_id': turn['request']['turn_id'],
                'context_revision': turn['request']['context_revision'],
                'title': definition['title'], 'summary': definition['expected_result'],
                'state': 'CONCEPT', 'approval_supported': False,
                'blockers': ['TRUSTED_PLANNING_AND_APPROVAL_PACKAGE_REQUIRED'],
                'questions': definition['questions'],
                'parent_id': None, 'group_id': None,
                'labels': [{'INVESTIGATE':'Investigation','DESIGN':'Architecture',
                            'BUILD':'Implementation','DOCUMENT':'Documentation',
                            'UNDECIDED':'Needs clarification'}[definition['work_kind']]], 'edges': [],
                'candidate_id': None, 'mission_id': None, 'canonical_history': [],
            }
            dependencies = {r['candidate_id']:r for r in self._dependency_catalog(principal, conversation_id)}
            for dependency in definition['dependencies']:
                predecessor = dependencies.get(dependency)
                if predecessor is None:
                    raise AdvisoryConflict('DEPENDENCY_SUBJECT_CHANGED')
                item['edges'].append({'kind':'REQUIRES','source_object_id':predecessor['object_id'],
                    'target_object_id':item['object_id'],'candidate_id':dependency,
                    'subject_revision':predecessor['subject_revision'],
                    'source_definition_revision':predecessor['concept_revision'],
                    'reason':definition['dependency_reasons'][dependency],'state':'PROPOSED'})
            self._canonical_links(authorization, principal, item)
            items.append(item)
        snapshot = digest(items)
        if expected_snapshot is not None and expected_snapshot != snapshot:
            raise AdvisoryConflict('CATALOG_SNAPSHOT_CHANGED')
        if cursor > len(items):
            raise ValueError('catalog cursor outside scoped population')
        self.grant.authorize(authorization)
        selected = items[cursor:cursor + limit]
        return {'contract_version': CONTRACT,
                'scope': {k: getattr(principal, k) for k in
                          ('instance_id', 'project_id', 'repository_id')},
                'snapshot_revision': snapshot, 'items': selected,
                'next_cursor': cursor + len(selected) if cursor + len(selected) < len(items) else None,
                'population': 'AUTHORIZED_ADMITTED_CONCEPTS_ONLY',
                'complete_portfolio': False, 'read_only': True, 'additional_model_calls': 0}

    def _canonical_links(self, authorization, principal, item):
        """Promotion projects the same scoped concept, never a second card."""
        from .advisory_candidate_service import AdvisoryCandidateService
        from .lifecycle import RecommendationLifecycleStore
        from .mission_concept_registration import registration_receipt
        path = AdvisoryCandidateService(self.root, self.grant)._database_path()
        if not path.exists():
            return
        with RecommendationLifecycleStore.read_only(path) as store:
            table = store._connection.execute('SELECT 1 FROM sqlite_master WHERE name=?',
                                               ('advisory_candidate_registrations',)).fetchone()
            if table is None:
                return
            rows = store._connection.execute(
                'SELECT document FROM advisory_candidate_registrations WHERE principal=?',
                (principal.reference,)).fetchall()
            import json
            from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
            for row in rows:
                receipt = json.loads(row[0])
                if receipt.get('contract_version') != CONTRACT:
                    continue
                _, proposal = store.registered_candidate_source(receipt['candidate']['id'])
                if (proposal['proposal_id'] != item['object_id']
                        or proposal['conversation_id'] != item['conversation_id']
                        or any(proposal[k] != getattr(principal,k) for k in
                               ('instance_id','project_id','repository_id'))):
                    continue
                expected = registration_receipt(principal.reference,receipt['operation_id'],
                    receipt['registration_key'],proposal,receipt['registered_at'])
                if digest(expected) != digest(receipt):
                    raise RuntimeError('historical canonical registration differs')
                candidate = store.get_candidate(receipt['candidate']['id'])
                allocation = store.allocation_for_recommendation(candidate.recommendation_id)
                mission_status = None
                if allocation:
                    with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
                        present = runtime.database._connection.execute(
                            'SELECT 1 FROM mission_state WHERE mission_id=?',(allocation.mission_id,)).fetchone()
                        if present:
                            admitted = runtime.states.get(allocation.mission_id)
                            if (admitted.admission_contract or {}).get('subject_revision') != proposal['package']['subject_revision']:
                                raise RuntimeError('historical Mission subject differs')
                            mission_status = admitted.status.value
                item['canonical_history'].append({'definition_revision':proposal['proposal_revision'],
                    'candidate_id':candidate.id,'subject_revision':proposal['package']['subject_revision'],
                    'subject_current':canonical_digest(candidate.to_dict())==proposal['package']['subject_revision'],
                    'mission_id':allocation.mission_id if allocation else None,'mission_status':mission_status,
                    'operation_id':receipt['operation_id']})
            item['canonical_history'].sort(key=lambda entry:entry['definition_revision'])
            for row in rows:
                receipt = json.loads(row[0])
                if receipt.get('contract_version') != CONTRACT:
                    continue
                _, proposal = store.registered_candidate_source(receipt['candidate']['id'])
                if (proposal['proposal_id'] != item['object_id']
                        or proposal['proposal_revision'] != item['revision']
                        or proposal['conversation_id'] != item['conversation_id']
                        or any(proposal[k] != getattr(principal, k) for k in
                               ('instance_id', 'project_id', 'repository_id'))):
                    continue
                expected = registration_receipt(principal.reference, receipt['operation_id'],
                    receipt['registration_key'], proposal, receipt['registered_at'])
                if digest(expected) != digest(receipt):
                    raise RuntimeError('catalog canonical registration differs')
                candidate = store.get_candidate(receipt['candidate']['id'])
                if canonical_digest(candidate.to_dict()) != proposal['package']['subject_revision']:
                    item['blockers'] = ['CANONICAL_SUBJECT_CHANGED']
                    item['state'] = 'SUBJECT_STALE'
                    return
                rec = store.get_recommendation(candidate.recommendation_id)
                allocation = store.allocation_for_recommendation(rec.id)
                item['candidate_id'] = candidate.id
                item['mission_id'] = allocation.mission_id if allocation else None
                item['state'] = ('APPROVED_WAITING' if rec.status.value in
                    {'ARCHITECTURE_APPROVED', 'MISSION_ALLOCATED'} else rec.status.value)
                if item['state'] == 'APPROVED_WAITING':
                    for edge in item['edges']:
                        edge['state'] = 'APPROVED_DEFINITION'
                item['blockers'] = ['CANONICAL_APPROVAL_OR_INTAKE_PENDING']
                if allocation:
                    try:
                        prepared = self.prepare(authorization, item['conversation_id'], item['revision'])
                        if prepared.get('package_digest') != digest(proposal['package']):
                            raise AdvisoryConflict('APPROVAL_PACKAGE_CHANGED')
                    except AdvisoryConflict:
                        item['state'] = 'SUBJECT_STALE'
                        item['blockers'] = ['APPROVAL_PACKAGE_CHANGED']
                        return
                    from .runtime.dynamic_mission import InstalledDynamicMissionRuntime
                    from .mission_concept_readiness import current_readiness
                    with InstalledDynamicMissionRuntime.open_for_governance_read(str(self.root)) as runtime:
                        present = runtime.database._connection.execute(
                            'SELECT 1 FROM mission_state WHERE mission_id=?',(allocation.mission_id,)).fetchone()
                        if present:
                            current = current_readiness(runtime, store, proposal['package'],
                                runtime.states.get(allocation.mission_id), principal)
                            item['state'], item['blockers'] = current['state'], current['blockers']
                return

    def handle(self, method, target, authorization, body):
        parsed = urlsplit(target)
        prefix = '/v1/mission-concepts'
        if parsed.path != prefix and not parsed.path.startswith(prefix + '/'):
            return 404, {'contract_version': CONTRACT,
                         'error': {'code': 'CONCEPT_ROUTE_NOT_FOUND'}}
        parts = parsed.path.split('/')
        if method == 'GET' and len(parts) == 5 and parts[4] == 'context':
            try:
                if parsed.query:
                    raise ValueError('closed context route required')
                principal = self.grant.authorize(authorization, parts[3])
                context, revision = self.context(principal, conversation_id=parts[3])
                self.grant.authorize(authorization, parts[3])
                return 200, {'contract_version':CONTRACT,'conversation_id':parts[3],
                    'context':context,'context_revision':revision,'read_only':True,'additional_model_calls':0}
            except PermissionError:
                code,status='CONCEPT_SCOPE_DENIED',403
            except (ValueError,TypeError,KeyError):
                code,status='CONCEPT_REQUEST_INVALID',400
            except (OSError,RuntimeError):
                code,status='CONCEPT_SOURCE_UNAVAILABLE',503
            return status,{'contract_version':CONTRACT,'error':{'code':code}}
        if method == 'POST' and parsed.path == prefix + '/resolve' and not parsed.query:
            try:
                from .mission_concept_resolver import MissionConceptResolver
                return 200, MissionConceptResolver(self.root, self.grant.instance_id).resolve(authorization, body)
            except PermissionError:
                code, status = 'CONCEPT_SCOPE_DENIED', 403
            except AdvisoryConflict as error:
                code, status = error.code, 409
            except (ValueError, TypeError, KeyError):
                code, status = 'CONCEPT_REQUEST_INVALID', 400
            except (OSError, RuntimeError):
                code, status = 'CONCEPT_SOURCE_UNAVAILABLE', 503
            return status, {'contract_version': CONTRACT, 'error': {'code': code}}
        if method == 'GET' and len(parts) == 6 and parts[4] == 'operations' and not parsed.query:
            try:
                from .mission_concept_approval import MissionConceptApproval
                return 200, MissionConceptApproval(self).operation(authorization, parts[3], parts[5])
            except PermissionError:
                code, status = 'CONCEPT_SCOPE_DENIED', 403
            except FileNotFoundError:
                code, status = 'CONCEPT_NOT_FOUND', 404
            except (ValueError, TypeError, KeyError):
                code, status = 'CONCEPT_REQUEST_INVALID', 400
            except (OSError, RuntimeError):
                code, status = 'CONCEPT_SOURCE_UNAVAILABLE', 503
            return status, {'contract_version': CONTRACT, 'error': {'code': code}}
        if method == 'POST' and len(parts) == 5 and parts[4] == 'approve' and not parsed.query:
            try:
                from .mission_concept_approval import MissionConceptApproval
                return 200, MissionConceptApproval(self).approve(authorization, parts[3], body)
            except PermissionError:
                code, status = 'CONCEPT_SCOPE_DENIED', 403
            except AdvisoryConflict as error:
                code, status = error.code, 409
            except (ValueError, TypeError, KeyError):
                code, status = 'CONCEPT_APPROVAL_INPUT_OR_STATE_INVALID', 409
            except (OSError, RuntimeError):
                code, status = 'CONCEPT_APPROVAL_PENDING', 503
            return status, {'contract_version': CONTRACT, 'error': {'code': code}}
        if method == 'GET' and len(parts) == 5 and parts[4] == 'package':
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                if set(query) - {'revision'} or any(len(v) != 1 for v in query.values()):
                    raise ValueError('invalid package query')
                return 200, self.prepare(authorization, parts[3],
                    int(query['revision'][0]) if 'revision' in query else None)
            except PermissionError:
                code, status = 'CONCEPT_SCOPE_DENIED', 403
            except AdvisoryConflict as error:
                code, status = error.code, 409
            except FileNotFoundError:
                code, status = 'CONCEPT_NOT_FOUND', 404
            except (ValueError, TypeError, KeyError):
                code, status = 'CONCEPT_REQUEST_INVALID', 400
            except (OSError, RuntimeError):
                code, status = 'CONCEPT_SOURCE_UNAVAILABLE', 503
            return status, {'contract_version': CONTRACT, 'error': {'code': code}}
        if method == 'GET' and parsed.path == prefix + '/catalog':
            try:
                query = parse_qs(parsed.query, keep_blank_values=True)
                if set(query) - {'cursor', 'limit', 'snapshot_revision'} or any(len(v) != 1 for v in query.values()):
                    raise ValueError('invalid catalog query')
                return 200, self.catalog(authorization,
                    cursor=int(query.get('cursor', ['0'])[0]),
                    limit=int(query.get('limit', ['4'])[0]),
                    expected_snapshot=query.get('snapshot_revision', [None])[0])
            except PermissionError:
                code, status = 'CONCEPT_SCOPE_DENIED', 403
            except AdvisoryConflict as error:
                code, status = error.code, 409
            except (ValueError, TypeError):
                code, status = 'CONCEPT_REQUEST_INVALID', 400
            except (OSError, RuntimeError):
                code, status = 'CONCEPT_SOURCE_UNAVAILABLE', 503
            return status, {'contract_version': CONTRACT, 'error': {'code': code}}
        routed = '/v1/advisory' + parsed.path[len(prefix):]
        if parsed.query:
            routed += '?' + parsed.query
        return super().handle(method, routed, authorization, body)
