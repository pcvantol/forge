"""Read one current EP repository grant without granting Forge dispatch rights."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request

from forge.execution_host_configuration import canonical_endpoint
from forge.scheduler.ep_http_adapter import _open


CONTRACT_VERSION = "ep-repository-consumer-authority/v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}\Z")
_PEER_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_GITHUB_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_FIELDS = frozenset({
    "contract_version", "instance_id", "project_id", "project_status",
    "repository_id", "repository_role", "authority_repository_id",
    "github_repository", "local_repository_binding", "consumer_id",
    "consumer_status", "repository_grant", "submission_authorization",
    "dispatch_authorized", "binding_revision", "provenance", "authority_digest",
})


class RepositoryAuthorityError(ValueError):
    """The current, exact EP repository authority cannot be established."""


@dataclass(frozen=True)
class RepositoryAuthorityScope:
    base_url: str
    bearer_token: str = field(repr=False)
    instance_id: str
    project_id: str
    consumer_id: str
    peer_binding_id: str
    peer_configuration_revision: int
    peer_configuration_digest: str
    allow_loopback_http: bool = False
    timeout: float = 10.0

    def __post_init__(self) -> None:
        if canonical_endpoint(self.base_url, allow_loopback_http=self.allow_loopback_http) != self.base_url:
            raise RepositoryAuthorityError("EP authority origin is not canonical")
        if (not self.bearer_token or any(char in self.bearer_token for char in "\r\n")
                or not self.instance_id or not _IDENTIFIER.fullmatch(self.project_id)
                or not _IDENTIFIER.fullmatch(self.consumer_id)
                or not _PEER_ID.fullmatch(self.peer_binding_id)
                or type(self.peer_configuration_revision) is not int
                or self.peer_configuration_revision < 1
                or _DIGEST.fullmatch(self.peer_configuration_digest) is None
                or not 0 < self.timeout <= 60):
            raise RepositoryAuthorityError("EP authority scope is incomplete")


def validate_authority_document(document: object, *, instance_id: str, project_id: str,
                                consumer_id: str, repository_id: str,
                                github_repository: str) -> dict[str, Any]:
    """Check the exact public EP v1 schema and one requested identity tuple."""
    if not isinstance(document, dict) or set(document) != _FIELDS:
        raise RepositoryAuthorityError("EP authority response shape is invalid")
    expected = {"contract_version": CONTRACT_VERSION, "instance_id": instance_id,
                "project_id": project_id, "repository_id": repository_id,
                "github_repository": github_repository, "consumer_id": consumer_id}
    if any(document[key] != value for key, value in expected.items()):
        raise RepositoryAuthorityError("EP authority response differs from the requested scope")
    _check_authority_grant(document, repository_id)
    _check_authority_provenance(document)
    return document


def _check_authority_grant(document: dict[str, Any], repository_id: str) -> None:
    authority_repository_id = document["authority_repository_id"]
    if (document["project_status"] != "ACTIVE"
            or not isinstance(document["repository_role"], str)
            or document["repository_role"] not in {"authority", "child"}
            or not isinstance(authority_repository_id, str)
            or not _IDENTIFIER.fullmatch(authority_repository_id)
            or (document["repository_role"] == "authority"
                and authority_repository_id != repository_id)
            or document["local_repository_binding"] != "BOUND"
            or document["consumer_status"] != "ACTIVE"
            or document["repository_grant"] != "ACTIVE"
            or document["submission_authorization"] != "PARALLEL_ACTION_INTAKE"
            or document["dispatch_authorized"] is not False
            or not isinstance(document["binding_revision"], str)
            or not _DIGEST.fullmatch(document["binding_revision"])
            or not isinstance(document["authority_digest"], str)
            or not _DIGEST.fullmatch(document["authority_digest"])):
        raise RepositoryAuthorityError("EP authority response differs from the requested scope")


def _check_authority_provenance(document: dict[str, Any]) -> None:
    provenance = document["provenance"]
    if (not isinstance(provenance, dict)
            or set(provenance) != {"source", "attachment_schema_version", "attachment_digest"}
            or provenance["source"] != "EP_CENTRAL_AND_BOUND_ATTACHMENT"
            or provenance["attachment_schema_version"] != "1.0"
            or not isinstance(provenance["attachment_digest"], str)
            or not _DIGEST.fullmatch(provenance["attachment_digest"])):
        raise RepositoryAuthorityError("EP authority response differs from the requested scope")


def read_repository_authority(scope: RepositoryAuthorityScope, *, repository_id: str,
                              github_repository: str, binding_revision: str | None = None,
                              authority_digest: str | None = None) -> dict[str, Any]:
    """Use EP's scoped bearer route and optional current-authority pins."""
    if (not isinstance(repository_id, str) or not _IDENTIFIER.fullmatch(repository_id)
            or not isinstance(github_repository, str)
            or not _GITHUB_REPOSITORY.fullmatch(github_repository)
            or github_repository.split("/")[1] in {".", ".."}
            or any(value is not None and
                   (not isinstance(value, str) or _DIGEST.fullmatch(value) is None)
                   for value in (binding_revision, authority_digest))):
        raise RepositoryAuthorityError("EP repository authority request is invalid")
    headers = {
        "Authorization": "Bearer " + scope.bearer_token,
        "EP-Instance-ID": scope.instance_id,
        "EP-Consumer-ID": scope.consumer_id,
        "EP-GitHub-Repository": github_repository,
        "EP-Project-ID": scope.project_id,
        "EP-Repository-ID": repository_id,
    }
    if binding_revision is not None:
        headers["EP-Authority-Revision"] = binding_revision
    if authority_digest is not None:
        headers["EP-Authority-Digest"] = authority_digest
    path = "/v1/projects/" + quote(scope.project_id, safe="") + "/repositories/" \
        + quote(repository_id, safe="") + "/consumer-authority"
    request = Request(scope.base_url + path, headers=headers, method="GET")
    try:
        with _open(request, timeout=scope.timeout) as response:
            raw = response.read(1_048_577)
    except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as error:
        if isinstance(error, HTTPError):
            error.close()
        raise RepositoryAuthorityError("EP repository authority is unavailable") from error
    if len(raw) > 1_048_576:
        raise RepositoryAuthorityError("EP repository authority exceeds response limit")
    try:
        document = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise RepositoryAuthorityError("EP repository authority response is invalid JSON") from error
    verified = validate_authority_document(
        document, instance_id=scope.instance_id, project_id=scope.project_id,
        consumer_id=scope.consumer_id, repository_id=repository_id,
        github_repository=github_repository,
    )
    if (binding_revision is not None and verified["binding_revision"] != binding_revision
            or authority_digest is not None and verified["authority_digest"] != authority_digest):
        raise RepositoryAuthorityError("EP repository authority pins have changed")
    return verified
