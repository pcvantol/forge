"""Bounded read-only observations at an approved immutable repository revision.

Only structural facts explicitly approved by Architecture are assessed. This
does not execute repository code or interpret artifacts as behavioral test PASS.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, HTTPRedirectHandler, build_opener

from forge.models.criterion_observation import CriterionObservation, canonical_digest
from forge.models.mission_completion import mission_criterion_id


class RepositoryObservationUnavailable(ValueError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RepositoryObservationUnavailable('REPOSITORY_SOURCE_REDIRECT_REJECTED')


class GitHubRepositoryArtifactReader:
    """Public HTTPS source only; no local checkout, token discovery or arbitrary URL."""

    maximum_bytes = 1024 * 1024

    def read(self, repository: str, revision: str, path: str) -> bytes:
        from forge.models.criterion_assessment import ApprovedRepositoryEvidenceSource, CriterionEvidenceRequirement
        ApprovedRepositoryEvidenceSource('validation', repository)
        CriterionEvidenceRequirement('validation', kind='repository_json', artifact_path=path,
                                     expected_json='null')
        if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
            raise RepositoryObservationUnavailable('IMMUTABLE_REPOSITORY_REVISION_REQUIRED')
        url = 'https://raw.githubusercontent.com/' + repository + '/' + revision + '/' + quote(path, safe='/')
        request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'Forge-criterion-observer/1.0'})
        try:
            with build_opener(_NoRedirect()).open(request, timeout=15) as response:
                data = response.read(self.maximum_bytes + 1)
        except HTTPError as error:
            code = 'REPOSITORY_ARTIFACT_ABSENT' if error.code == 404 else 'REPOSITORY_SOURCE_UNAVAILABLE'
            raise RepositoryObservationUnavailable(code) from error
        except (URLError, TimeoutError, OSError) as error:
            raise RepositoryObservationUnavailable('REPOSITORY_SOURCE_UNAVAILABLE') from error
        if len(data) > self.maximum_bytes:
            raise RepositoryObservationUnavailable('REPOSITORY_ARTIFACT_SIZE_LIMIT')
        return data


def _json(data: bytes) -> Any:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def invalid_constant(_value):
        raise ValueError('non-finite JSON number')
    return json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_constant)


def _pointer(value: Any, pointer: str) -> Any:
    if pointer == '':
        return value
    for part in pointer[1:].split('/'):
        key = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not key.isascii() or not key.isdigit() or (key != '0' and key.startswith('0')):
                raise KeyError(key)
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise KeyError(key)
    return value


class RepositoryCriterionObserver:
    """Collect facts from the approved source for the exact accepted delivery."""

    def __init__(self, reader=None):
        self.reader = reader or GitHubRepositoryArtifactReader()

    def observe(self, mission, reference, repository_id: str) -> tuple[CriterionObservation, ...]:
        source = mission.repository_evidence_source
        if source is None:
            return ()
        if source.repository_id != repository_id:
            raise ValueError('approved Repository Evidence source differs from the installed repository')
        observations = []
        cache: dict[str, bytes | RepositoryObservationUnavailable] = {}
        for contract in mission.criterion_assessment_contracts:
            for requirement in contract.requirements:
                if requirement.kind != 'repository_json':
                    continue
                path = requirement.artifact_path
                if path not in cache:
                    try:
                        cache[path] = self.reader.read(source.github_repository, reference.repository_revision, path)
                    except RepositoryObservationUnavailable as error:
                        cache[path] = error
                data = cache[path]
                observed_json, content_digest = None, None
                if isinstance(data, RepositoryObservationUnavailable):
                    result, reason = 'UNAVAILABLE', str(data)
                else:
                    content_digest = 'sha256:' + sha256(data).hexdigest()
                    try:
                        value = _pointer(_json(data), requirement.json_pointer)
                        observed_json = json.dumps(value, sort_keys=True, separators=(',', ':'),
                                                   ensure_ascii=False, allow_nan=False)
                        result = 'PASS' if observed_json == requirement.expected_json else 'FAIL'
                        reason = 'APPROVED_JSON_ASSERTION_MATCHED' if result == 'PASS' else 'JSON_ASSERTION_MISMATCH'
                    except (KeyError, IndexError):
                        result, reason = 'FAIL', 'JSON_POINTER_ABSENT'
                    except (ValueError, UnicodeError, RecursionError):
                        result, reason = 'FAIL', 'INVALID_JSON_ARTIFACT'
                observations.append(CriterionObservation(
                    mission.id, canonical_digest(mission.to_dict()), mission_criterion_id(mission.id, contract.criterion),
                    contract.digest, requirement.requirement_id, reference.receipt_id, reference.action_id,
                    reference.report_id, reference.repository_revision, reference.repository_evidence_digest,
                    'repository_json', source.github_repository, path, content_digest, observed_json, result, reason,
                    requirement_digest=requirement.digest, json_pointer=requirement.json_pointer,
                    candidate_revision=reference.candidate_revision,
                ))
        return tuple(observations)
