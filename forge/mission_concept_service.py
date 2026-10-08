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

    def context(self, principal, selections=None):
        value, _ = super().context(principal, selections)
        # No dependencies can be invented before an authorized catalog exists.
        value['concept_dependency_references'] = []
        records = MissionConceptSetup(self.root, principal.instance_id)._records()
        configured = next((r for r in records if r['grant_id'] == principal.grant_id
                           and r['principal_id'] == principal.principal_id
                           and r['scope'] == {k: getattr(principal, k) for k in
                               ('instance_id', 'project_id', 'repository_id')}), None)
        value['concept_work_profiles'] = configured['profiles'] if configured else {}
        value['concept_configuration_revision'] = configured['configuration_digest'] if configured else None
        return value, digest(value)

    @staticmethod
    def validate_result(document, admitted, references):
        definition = proposed_definition(
            document, admitted['request_digest'],
            admitted['context']['concept_dependency_references'])
        return {'contract_version': CONTRACT,
                'request_digest': admitted['request_digest'],
                'definition': definition}

    def capability(self, authorization, selections=None):
        value = super().capability(authorization, selections)
        value['supported_operations'] = ['REFINE', 'READ', 'CANCEL_REQUEST']
        value['approval_supported'] = False
        value['readiness_qualified'] = False
        value['generated_content_origin'] = 'VALIDATED_MODEL_PROPOSAL'
        try:
            _, configuration, allowance = MissionConceptSetup(self.root, self.grant.instance_id).current(authorization)
            value['approval_supported'] = True
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
        context, context_revision = self.context(principal)
        history = self._read(self._path(principal, conversation_id), principal,
                             conversation_id, context)
        complete = [t for t in history['turns'] if t['status'] == 'COMPLETE']
        if revision is None:
            revision = len(complete)
        if type(revision) is not int or not 1 <= revision <= len(complete):
            raise FileNotFoundError('unknown concept revision')
        turn = complete[revision - 1]
        if (revision != len(complete) or turn['request']['context_revision'] != context_revision
                or history['turns'][-1]['status'] != 'COMPLETE'):
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
            prepared['package']['source']['conversation_revision'] = history['revision']
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
                'parent_id': None, 'group_id': None, 'labels': [], 'edges': [],
                'candidate_id': None, 'mission_id': None,
            }
            self._canonical_links(principal, item)
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

    def _canonical_links(self, principal, item):
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
                item['blockers'] = ['EXPLICIT_WORKSET_RELEASE_REQUIRED'] if allocation else ['CANONICAL_APPROVAL_OR_INTAKE_PENDING']
                return

    def handle(self, method, target, authorization, body):
        parsed = urlsplit(target)
        prefix = '/v1/mission-concepts'
        if parsed.path != prefix and not parsed.path.startswith(prefix + '/'):
            return 404, {'contract_version': CONTRACT,
                         'error': {'code': 'CONCEPT_ROUTE_NOT_FOUND'}}
        parts = parsed.path.split('/')
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
