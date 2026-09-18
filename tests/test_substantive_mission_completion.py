"""Approved repository assertions, observations, and substantive completion."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from forge.completion import MissionCompletionEvaluationError, MissionCompletionEvaluator
from forge.completion.repository_observer import (
    GitHubRepositoryArtifactReader, RepositoryCriterionObserver, RepositoryObservationUnavailable,
)
from forge.models.architecture_mission import ArchitectureMission, ArchitectureMissionStatus
from forge.models.criterion_assessment import (
    ApprovedRepositoryEvidenceSource, CriterionAssessmentContract, CriterionEvidenceRequirement,
)
from forge.models.criterion_observation import canonical_digest
from forge.models.mission_completion import (
    CanonicalExecutionEvidenceReference, MissionCompletionEvidence, MissionCriterionEvidenceBinding,
    MissionCriterionEvaluationStatus, RepositoryTruthReference, mission_criterion_id,
)
from forge.models.mission_recommendation import RequiredDiscipline


K1 = 'The export contract declares the report_data field.'
K2 = 'The published policy declares authorization_required=true.'
PATH = 'contracts/export.json'
SOURCE = ApprovedRepositoryEvidenceSource('repository', 'synthetic-owner/synthetic-repository')


def requirement(identifier, pointer, expected='true'):
    return CriterionEvidenceRequirement(identifier, kind='repository_json', artifact_path=PATH,
                                        json_pointer=pointer, expected_json=expected)


def mission(*, contracts=None):
    contracts = contracts if contracts is not None else (
        CriterionAssessmentContract(K1, (requirement('report-field', '/report/fields', '["report_data"]'),)),
        CriterionAssessmentContract(K2, (requirement('authorization-policy', '/policy/authorization_required'),)),
    )
    criteria = tuple(item.criterion for item in contracts) if contracts else (K1, K2)
    return ArchitectureMission('synthetic-mission', 'synthetic-candidate', 'Export contract', 'Publish explicit JSON.',
        'Provide an inspectable export contract.', 'Inspectability.', 'architecture', 'recommendation',
        ('contract',), ('bounded',), criteria, ('public immutable repository',), ('none',), ('contract',),
        (RequiredDiscipline.PLATFORM_ARCHITECTURE,), ('scope-drift',),
        ArchitectureMissionStatus.APPROVED_FOR_ENGINEERING,
        criterion_assessment_contracts=contracts, maximum_actions=4 if contracts else None,
        maximum_consecutive_no_progress_actions=1 if contracts else None,
        repository_evidence_source=SOURCE if contracts else None)


def reference(label='a', revision=None):
    return CanonicalExecutionEvidenceReference('receipt-' + label, 'action-' + label,
        'report-' + label, revision or label * 40, canonical_digest('host-' + label))


def truth(ref):
    return RepositoryTruthReference('truth-' + ref.receipt_id, ref.repository_revision,
        'repository://repository/' + ref.repository_revision, canonical_digest('truth-' + ref.receipt_id))


def host(ref, mission_id='synthetic-mission'):
    return {'receipt_id': ref.receipt_id, 'report_id': ref.report_id, 'outcome': 'complete',
            'correlation_id': 'correlation-' + ref.action_id, 'host_run_id': 'run-' + ref.action_id,
            'repository_evidence': {'mission_id': mission_id, 'action_id': ref.action_id,
                'report_id': ref.report_id, 'correlation_id': 'correlation-' + ref.action_id,
                'host_run_id': 'run-' + ref.action_id, 'repository_revision': ref.repository_revision,
                'content_digest': ref.repository_evidence_digest}}


def artifact(k1=True, k2=True):
    return json.dumps({'report': {'fields': ['report_data'] if k1 else []},
                       'policy': {'authorization_required': k2}}).encode()


class Reader:
    def __init__(self, value):
        self.value, self.calls = value, []

    def read(self, repository, revision, path):
        self.calls.append((repository, revision, path))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def observed(approved, ref, content):
    return RepositoryCriterionObserver(Reader(content)).observe(approved, ref, SOURCE.repository_id)


def contract_evidence(approved, refs, observations, assessed_truth=None):
    target = assessed_truth or truth(refs[-1])
    bindings = tuple(MissionCriterionEvidenceBinding(
        mission_criterion_id(approved.id, contract.criterion), tuple(refs), target,
        tuple(item for item in observations if item.criterion_id == mission_criterion_id(approved.id, contract.criterion)),
        contract.digest,
    ) for contract in approved.criterion_assessment_contracts)
    return MissionCompletionEvidence(approved.id, canonical_digest(approved.to_dict()), bindings)


def evaluate(approved, refs, observations, **kwargs):
    evidence = contract_evidence(approved, refs, observations, **kwargs)
    return MissionCompletionEvaluator().evaluate(approved, truth(refs[-1]).to_dict(),
        tuple(host(item, approved.id) for item in refs), evidence)


class SubstantiveMissionCompletionTests(unittest.TestCase):
    def test_partial_delivery_proves_only_the_matching_criterion(self):
        approved, ref = mission(), reference()
        result = evaluate(approved, (ref,), observed(approved, ref, artifact(k2=False)))
        by_text = {item.criterion: item for item in result.criteria}
        self.assertEqual(by_text[K1].status, MissionCriterionEvaluationStatus.PROVEN)
        self.assertEqual(by_text[K2].status, MissionCriterionEvaluationStatus.UNSATISFIED)
        self.assertFalse(result.all_required_criteria_proven)
        self.assertEqual(by_text[K2].requirement_results[0]['reason'], 'JSON_ASSERTION_MISMATCH')

    def test_one_receipt_can_support_both_independently_matching_criteria(self):
        approved, ref = mission(), reference()
        result = evaluate(approved, (ref,), observed(approved, ref, artifact()))
        self.assertTrue(result.all_required_criteria_proven)
        self.assertTrue(all(item.execution_evidence == (ref,) for item in result.criteria))
        self.assertEqual(len({item.observations[0].id for item in result.criteria}), 2)

    def test_canonical_complete_and_planner_intent_or_pass_prose_are_not_observations(self):
        approved, ref = mission(), reference()
        document = host(ref)
        document.update({'expected_evidence': [K1, K2], 'provider_claim': 'PASS; everything complete',
                         'validation_references': ['all criteria PASS']})
        result = MissionCompletionEvaluator().evaluate(approved, truth(ref).to_dict(), (document,),
            contract_evidence(approved, (ref,), ()))
        self.assertFalse(result.all_required_criteria_proven)
        self.assertTrue(all(item.status is MissionCriterionEvaluationStatus.UNSATISFIED for item in result.criteria))

    def test_legacy_associations_do_not_acquire_substantive_meaning(self):
        approved, ref = mission(), reference()
        v2 = contract_evidence(approved, (ref,), observed(approved, ref, artifact()))
        v1 = replace(v2, schema_version='1.0')
        result = MissionCompletionEvaluator().evaluate(approved, truth(ref).to_dict(), (host(ref),), v1)
        self.assertFalse(result.all_required_criteria_proven)
        self.assertTrue(all(item.reason == 'LEGACY_ASSOCIATIONS_ARE_NOT_SUBSTANTIVE_EVIDENCE'
                            for item in result.criteria))
        legacy = mission(contracts=())
        missing = MissionCompletionEvaluator().evaluate(legacy, truth(ref).to_dict(), (host(ref),), None)
        self.assertTrue(all(item.reason == 'APPROVED_ASSESSMENT_CONTRACT_MISSING' for item in missing.criteria))

    def test_completion_evidence_roundtrips_all_original_observations(self):
        approved, ref = mission(), reference()
        original = contract_evidence(approved, (ref,), observed(approved, ref, artifact(k2=False)))
        restored = MissionCompletionEvidence.from_dict(json.loads(json.dumps(original.to_dict())))
        self.assertEqual(restored, original)
        self.assertEqual(restored.digest, original.digest)

    def test_wrong_observation_provenance_never_proves_criterion(self):
        approved, ref = mission(), reference()
        observations = observed(approved, ref, artifact())
        original = observations[0]
        changes = {'mission_id': 'other-mission', 'mission_digest': canonical_digest('other-mission'),
                   'criterion_id': 'other-criterion', 'contract_digest': canonical_digest('other-contract'),
                   'receipt_id': 'other-receipt', 'action_id': 'other-action', 'report_id': 'other-report',
                   'repository_revision': 'f' * 40, 'candidate_revision': 'f' * 40,
                   'repository_evidence_digest': canonical_digest('other-host')}
        for field, value in changes.items():
            with self.subTest(field=field):
                evidence = contract_evidence(approved, (ref,), observations)
                affected = next(item for item in evidence.bindings if item.criterion_id == original.criterion_id)
                bad = replace(affected, observations=(replace(original, **{field: value}),))
                evidence = replace(evidence, bindings=tuple(bad if item is affected else item for item in evidence.bindings))
                result = MissionCompletionEvaluator().evaluate(approved, truth(ref).to_dict(), (host(ref),), evidence)
                finding = next(item for item in result.criteria if item.criterion_id == original.criterion_id)
                self.assertEqual(finding.reason, 'OBSERVATION_PROVENANCE_MISMATCH')
                self.assertFalse(result.all_required_criteria_proven)

    def test_valid_provenance_with_irrelevant_repository_source_or_path_is_unproven(self):
        approved, ref = mission(), reference()
        observations = observed(approved, ref, artifact())
        for field, value in (('source_identity', 'other-owner/other-repository'), ('artifact_path', 'other.json'),
                             ('json_pointer', '/irrelevant'), ('requirement_digest', canonical_digest('other-requirement'))):
            with self.subTest(field=field):
                changed = (replace(observations[0], **{field: value}), *observations[1:])
                result = evaluate(approved, (ref,), changed)
                finding = next(item for item in result.criteria if item.criterion_id == observations[0].criterion_id)
                self.assertEqual(finding.requirement_results[0]['reason'], 'OBSERVATION_SOURCE_MISMATCH')
                self.assertFalse(result.all_required_criteria_proven)

    def test_legacy_host_control_claim_without_authoritative_observation_is_explicitly_unsupported(self):
        contract = CriterionAssessmentContract('Host validation ran.',
            (CriterionEvidenceRequirement('control', 'host-control', 'run-check'),))
        approved, ref = mission(contracts=(contract,)), reference()
        result = evaluate(approved, (ref,), ())
        self.assertEqual(result.criteria[0].requirement_results[0]['reason'], 'UNSUPPORTED_AUTHORITATIVE_EVIDENCE_SOURCE')

    def test_missing_evidence_and_wrong_contract_digest_remain_unproven(self):
        approved, ref = mission(), reference()
        result = MissionCompletionEvaluator().evaluate(approved, truth(ref).to_dict(), (host(ref),), None)
        self.assertFalse(result.all_required_criteria_proven)
        evidence = contract_evidence(approved, (ref,), observed(approved, ref, artifact()))
        changed = replace(evidence.bindings[0], contract_digest=canonical_digest('wrong-contract'))
        result = MissionCompletionEvaluator().evaluate(approved, truth(ref).to_dict(), (host(ref),),
            replace(evidence, bindings=(changed, *evidence.bindings[1:])))
        self.assertEqual(result.criteria[0].reason, 'ASSESSMENT_CONTRACT_MISMATCH')

    def test_unknown_criterion_requirement_or_conflicting_observations_are_rejected(self):
        approved, ref = mission(), reference()
        observations = observed(approved, ref, artifact())
        evidence = contract_evidence(approved, (ref,), observations)
        with self.assertRaisesRegex(MissionCompletionEvaluationError, 'unknown Mission criterion'):
            unknown = replace(evidence.bindings[0], criterion_id='unknown-criterion')
            MissionCompletionEvaluator().evaluate(approved, truth(ref).to_dict(), (host(ref),),
                replace(evidence, bindings=(unknown, *evidence.bindings[1:])))
        with self.assertRaisesRegex(MissionCompletionEvaluationError, 'unknown criterion requirement'):
            evaluate(approved, (ref,), (replace(observations[0], requirement_id='unknown-requirement'), *observations[1:]))
        conflict = replace(observations[0], result='FAIL', reason='JSON_ASSERTION_MISMATCH', observed_json='false')
        with self.assertRaisesRegex(MissionCompletionEvaluationError, 'conflicting immutable'):
            evaluate(approved, (ref,), (*observations, conflict))

    def test_unknown_mission_envelope_and_noncanonical_receipt_are_rejected(self):
        approved, ref = mission(), reference()
        evidence = contract_evidence(approved, (ref,), observed(approved, ref, artifact()))
        for changes in ({'mission_id': 'other'}, {'mission_digest': canonical_digest('other')}):
            with self.subTest(changes=changes), self.assertRaisesRegex(MissionCompletionEvaluationError, 'approved Mission'):
                MissionCompletionEvaluator().evaluate(approved, truth(ref).to_dict(), (host(ref),), replace(evidence, **changes))
        wrong = host(ref, mission_id='other')
        result = MissionCompletionEvaluator().evaluate(approved, truth(ref).to_dict(), (wrong,), evidence)
        self.assertTrue(all(item.reason == 'NON_CANONICAL_EXECUTION_EVIDENCE' for item in result.criteria))

    def test_new_revision_requires_new_current_property_observation_without_relabeling_old_fact(self):
        approved, a, b = mission(), reference('a'), reference('b')
        original = observed(approved, a, artifact())
        original_documents = [item.to_dict() for item in original]
        stale = evaluate(approved, (a, b), original)
        self.assertFalse(stale.all_required_criteria_proven)
        self.assertTrue(all(item.requirement_results[0]['reason'] == 'CURRENT_OBSERVATION_MISSING'
                            for item in stale.criteria))
        broken = observed(approved, b, artifact(k1=False))
        result = evaluate(approved, (a, b), (*original, *broken))
        self.assertEqual(next(item for item in result.criteria if item.criterion == K1).status,
                         MissionCriterionEvaluationStatus.UNSATISFIED)
        self.assertEqual([item.to_dict() for item in original], original_documents)
        confirmed = observed(approved, b, artifact())
        passing = evaluate(approved, (a, b), (*original, *confirmed))
        self.assertTrue(passing.all_required_criteria_proven)
        self.assertTrue(all(item.repository_revision == a.repository_revision for item in original))
        self.assertTrue(all(item.repository_revision == b.repository_revision for item in confirmed))

    def test_one_historical_criterion_accumulates_two_distinct_action_contributions(self):
        contract = CriterionAssessmentContract('Both declared publication milestones have been observed.',
            (requirement('first-milestone', '/first'), requirement('second-milestone', '/second')),
            validity_policy='historical_delivery')
        approved, a, b = mission(contracts=(contract,)), reference('a'), reference('b')
        first = observed(approved, a, b'{"first":true,"second":false}')
        second = observed(approved, b, b'{"first":false,"second":true}')
        self.assertFalse(evaluate(approved, (a,), first).all_required_criteria_proven)
        result = evaluate(approved, (a, b), (*first, *second))
        self.assertTrue(result.all_required_criteria_proven)
        required_ids = {identifier for req in result.criteria[0].requirement_results for identifier in req['observation_ids']}
        selected = [item for item in (*first, *second) if item.id in required_ids]
        self.assertEqual({item.action_id for item in selected}, {'action-a', 'action-b'})

    def test_conflicting_current_facts_cannot_be_hidden_by_observation_order(self):
        approved, a = mission(), reference('a')
        b = reference('b', revision=a.repository_revision)
        passing = observed(approved, a, artifact())
        contradicting = observed(approved, b, artifact(k2=False))
        for observations in ((*passing, *contradicting), (*contradicting, *passing)):
            with self.subTest(order=[item.receipt_id for item in observations]):
                try:
                    result = evaluate(approved, (a, b), observations)
                except MissionCompletionEvaluationError:
                    continue  # A conflict may reject the entire immutable evidence set.
                self.assertFalse(result.all_required_criteria_proven,
                                 'Conflicting observations for one immutable current artifact cannot be selected by order')


class RepositoryCriterionObserverTests(unittest.TestCase):
    def test_observes_bytes_once_per_artifact_and_binds_exact_original_delivery(self):
        approved, ref, content = mission(), reference(), artifact()
        reader = Reader(content)
        observations = RepositoryCriterionObserver(reader).observe(approved, ref, SOURCE.repository_id)
        self.assertEqual(reader.calls, [(SOURCE.github_repository, ref.repository_revision, PATH)])
        self.assertTrue(all(item.content_digest == 'sha256:' + sha256(content).hexdigest() for item in observations))
        self.assertTrue(all(item.receipt_id == ref.receipt_id and item.repository_revision == ref.repository_revision
                            for item in observations))

    def test_missing_empty_invalid_duplicate_and_free_text_artifacts_never_pass(self):
        values = (RepositoryObservationUnavailable('REPOSITORY_ARTIFACT_ABSENT'), b'', b'PASS everything complete',
                  b'{"report":{},"report":{"fields":["report_data"]}}', b'{"value":NaN}', b'\xff')
        for content in values:
            with self.subTest(content=repr(content)):
                observations = observed(mission(), reference(), content)
                self.assertTrue(all(item.result in {'FAIL', 'UNAVAILABLE'} for item in observations))
                self.assertFalse(evaluate(mission(), (reference(),), observations).all_required_criteria_proven)

    def test_json_pointer_escaping_array_index_and_exact_types(self):
        contracts = (CriterionAssessmentContract('The exact nested artifact value is declared.',
            (requirement('escaped-pointer', '/a~1b/~0name/0', 'true'),)),)
        approved = mission(contracts=contracts)
        observations = observed(approved, reference(), b'{"a/b":{"~name":[true]}}')
        self.assertEqual(observations[0].result, 'PASS')
        numerical = observed(approved, reference(), b'{"a/b":{"~name":[1]}}')
        self.assertEqual(numerical[0].result, 'FAIL')

    def test_repository_scope_mismatch_is_rejected_before_any_read(self):
        reader = Reader(artifact())
        with self.assertRaisesRegex(ValueError, 'installed repository'):
            RepositoryCriterionObserver(reader).observe(mission(), reference(), 'other-repository')
        self.assertEqual(reader.calls, [])

    def test_array_pointer_accepts_ascii_indices_only_but_preserves_unicode_object_keys(self):
        approved = mission(contracts=(CriterionAssessmentContract('Exact pointer property',
            (requirement('index', '/١', 'true'),)),))
        invalid_index = observed(approved, reference(), b'[false,true]')
        self.assertEqual(invalid_index[0].reason, 'JSON_POINTER_ABSENT')
        self.assertFalse(evaluate(approved, (reference(),), invalid_index).all_required_criteria_proven)
        object_key = observed(approved, reference(), '{"١":true}'.encode())
        self.assertTrue(evaluate(approved, (reference(),), object_key).all_required_criteria_proven)

    def test_reader_uses_fixed_origin_full_revision_and_bounded_bytes(self):
        requests = []
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, maximum):
                requests.append(maximum)
                return b'{}'
        class Opener:
            def open(self, request, *, timeout):
                requests.append((request.full_url, timeout))
                return Response()
        with patch('forge.completion.repository_observer.build_opener', return_value=Opener()):
            self.assertEqual(GitHubRepositoryArtifactReader().read(SOURCE.github_repository, 'a' * 40, PATH), b'{}')
            with self.assertRaisesRegex(RepositoryObservationUnavailable, 'IMMUTABLE_REPOSITORY_REVISION_REQUIRED'):
                GitHubRepositoryArtifactReader().read(SOURCE.github_repository, 'main', PATH)
        self.assertEqual(requests[0], ('https://raw.githubusercontent.com/' + SOURCE.github_repository + '/' + 'a' * 40 + '/' + PATH, 15))
        self.assertEqual(requests[1], GitHubRepositoryArtifactReader.maximum_bytes + 1)


if __name__ == '__main__':
    unittest.main()
