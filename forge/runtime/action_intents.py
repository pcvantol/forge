"""Durable, non-dispatchable execution intent for independent Mission Actions."""
from __future__ import annotations

from hashlib import sha256
import json
import re
import sqlite3
from typing import Any, Callable

from forge.models.criterion_assessment import ApprovedRepositoryEvidenceSource
from forge.execution_host_configuration import PeerConfigurationError, canonical_endpoint
from forge.parallel_action_contract import ParallelActionContractError, validate_peer_graph
from forge.runtime.action_authority import (
    RepositoryAuthorityError, RepositoryAuthorityScope, read_repository_authority,
    validate_authority_document,
)


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
CONTRACT_VERSION = "parallel-action-intent/v1"


class ActionIntentError(ValueError):
    """The pinned graph, Action identity or guarded revision is inconsistent."""


def _encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(encoded: str) -> str:
    return "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()


def _safe_view(document: dict[str, Any]) -> dict[str, Any]:
    """Expose durable state without a fingerprint of private request bytes."""
    return {key: value for key, value in document.items() if key != "request_digest"}


def _approved_state(connection: sqlite3.Connection, mission_id: str) -> tuple[dict[str, Any], list[str]]:
    state_row = connection.execute(
        "SELECT document FROM mission_state WHERE mission_id=?", (mission_id,)
    ).fetchone()
    if state_row is None:
        raise ActionIntentError("Action intents require an existing Mission")
    try:
        state = json.loads(state_row[0])
        if not isinstance(state, dict):
            raise TypeError("Mission source is not an object")
        revision = state["revision"]
        mission = state["mission"]
        state["actions"]
    except (TypeError, ValueError, KeyError) as error:
        raise ActionIntentError("Mission source is malformed") from error
    if (not isinstance(mission, dict) or state.get("mission_id") != mission_id
            or mission.get("id") != mission_id
            or mission.get("status") != "approved_for_engineering"
            or state.get("status") in {"COMPLETED", "ARCHIVED", "FAILED"}
            or type(revision) is not int or revision < 1):
        raise ActionIntentError("Action intents require the current approved Mission revision")
    if state.get("execution_correlation") is not None:
        raise ActionIntentError("legacy serial correlation cannot be replayed as multi-Action intent")
    scope = mission.get("scope")
    if (not isinstance(scope, list) or not scope
            or any(not isinstance(item, str) or not item for item in scope)
            or len(set(scope)) != len(scope)):
        raise ActionIntentError("approved Mission scope is invalid")
    return state, scope


def _pinned_graph(connection: sqlite3.Connection, mission_id: str,
                  state: dict[str, Any], scope: list[str]) -> tuple[dict[str, Any], str]:
    revision = state["revision"]
    row = connection.execute(
        "SELECT document_digest,document FROM mission_action_slot_snapshots "
        "WHERE mission_id=? AND mission_revision=?", (mission_id, revision)
    ).fetchone()
    if row is None or row[0] != _digest(row[1]):
        raise ActionIntentError("current planning snapshot is unavailable or corrupt")
    try:
        graph = json.loads(row[1])
        if not isinstance(graph, dict):
            raise TypeError("planning snapshot is not an object")
        normalized = validate_peer_graph({key: graph[key] for key in (
            "contract_version", "mission_id", "mission_revision", "actions",
        )})
    except (TypeError, ValueError, KeyError, ParallelActionContractError) as error:
        raise ActionIntentError("current planning snapshot is invalid") from error
    metadata = {"mission_source_digest", "action_set_digest", "repository_truth_digest"}
    present = metadata & set(graph)
    if present and present != metadata:
        raise ActionIntentError("current planning snapshot provenance is incomplete")
    if present:
        expected = {
            "mission_source_digest": _digest(_encode({
                "mission": state["mission"], "admission_contract": state.get("admission_contract"),
            })),
            "action_set_digest": _digest(_encode({
                "actions": state["actions"], "intents": state.get("intents"),
            })),
            "repository_truth_digest": _digest(_encode(state.get("repository_truth"))),
        }
        if any(graph[key] != value for key, value in expected.items()):
            raise ActionIntentError("current Mission, Action or Truth provenance has changed")
    if ({key: value for key, value in graph.items() if key not in metadata | {"approved_scope"}} != normalized
            or graph.get("mission_id") != mission_id or graph.get("mission_revision") != revision
            or graph.get("approved_scope") != sorted(scope)):
        raise ActionIntentError("planning snapshot has drifted from the Mission")
    if any(item["target"]["repository_id"] not in scope for item in normalized["actions"]):
        raise ActionIntentError("Action target is outside approved Mission scope")
    return normalized, row[0]


def _check_action_set(actions: object, graph: dict[str, Any]) -> None:
    if not isinstance(actions, list) or len(actions) != len(graph["actions"]):
        raise ActionIntentError("planning snapshot has drifted from the Mission")
    by_id = {action["action_id"]: action for action in graph["actions"]}
    if (len(by_id) != len(actions)
            or any(not isinstance(action, dict) or not isinstance(action.get("id"), str)
                   or action["id"] not in by_id for action in actions)
            or len({action["id"] for action in actions}) != len(actions)):
        raise ActionIntentError("planning snapshot Action identities have drifted")
    for action in actions:
        dependencies = action.get("dependencies")
        if (not isinstance(dependencies, list)
                or any(not isinstance(item, str) for item in dependencies)
                or len(dependencies) != len(set(dependencies))
                or set(dependencies) != {edge["predecessor_action_id"]
                                         for edge in by_id[action["id"]]["dependencies"]}):
            raise ActionIntentError("planning snapshot Action dependencies have drifted")


def _source(connection: sqlite3.Connection, mission_id: str) -> tuple[dict[str, Any], str]:
    state, scope = _approved_state(connection, mission_id)
    graph, digest = _pinned_graph(connection, mission_id, state, scope)
    _check_action_set(state["actions"], graph)
    return graph, digest


def _approved_sources(state: dict[str, Any], scope: list[str]) -> dict[str, ApprovedRepositoryEvidenceSource]:
    mission = state["mission"]
    declared = mission.get("repository_evidence_sources")
    if declared is None and len(scope) == 1:
        declared = [mission.get("repository_evidence_source")]
    try:
        sources = [ApprovedRepositoryEvidenceSource.from_dict(item) for item in declared]
    except (TypeError, ValueError) as error:
        raise ActionIntentError("approved per-target repository source is invalid") from error
    by_id = {source.repository_id: source for source in sources}
    if len(by_id) != len(sources) or set(by_id) != set(scope):
        raise ActionIntentError("approved per-target repository sources are incomplete")
    return by_id


def _row_document(row: sqlite3.Row) -> dict[str, Any]:
    if row["document_digest"] != _digest(row["document"]):
        raise ActionIntentError("Action intent digest is invalid")
    try:
        document = json.loads(row["document"])
    except (TypeError, ValueError) as error:
        raise ActionIntentError("Action intent document is invalid") from error
    if _encode(document) != row["document"]:
        raise ActionIntentError("Action intent document bytes are noncanonical")
    _check_row_identity(row, document)
    _check_binding(row, document)
    return document


def _check_row_identity(row: sqlite3.Row, document: object) -> None:
    core = {
            "contract_version", "mission_id", "action_id", "slot_revision",
            "source_revision", "source_digest", "target", "correlation_status",
            "correlation_id", "request_digest", "target_verification", "dispatch_authorized",
        }
    if (not isinstance(document, dict)
            or set(document) != (core | {"authority", "baseline", "peer"}
                                 if row["slot_revision"] == 3 else core)
            or document.get("contract_version") != CONTRACT_VERSION
            or document.get("mission_id") != row["mission_id"]
            or document.get("action_id") != row["action_id"]
            or document.get("slot_revision") != row["slot_revision"]
            or document.get("source_revision") != row["source_revision"]
            or document.get("source_digest") != row["source_digest"]
            or _DIGEST.fullmatch(row["source_digest"]) is None
            or document.get("target_verification") != (
                "VERIFIED" if row["slot_revision"] == 3 else "UNVERIFIED")
            or document.get("dispatch_authorized") is not False):
        raise ActionIntentError("Action intent identity is inconsistent")
    target = document["target"]
    if (not isinstance(target, dict) or set(target) != {
            "ep_instance_id", "project_id", "repository_id", "baseline_revision",
        } or any(not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None
                 for value in target.values())):
        raise ActionIntentError("Action intent target is invalid")
    if row["slot_revision"] == 3:
        _check_verified_evidence(document)


def _check_verified_evidence(document: dict[str, Any]) -> None:
    authority = document["authority"]
    baseline = document["baseline"]
    peer = document["peer"]
    target = document["target"]
    try:
        validate_authority_document(
            authority, instance_id=target["ep_instance_id"],
            project_id=target["project_id"], consumer_id=authority["consumer_id"],
            repository_id=target["repository_id"],
            github_repository=baseline["github_repository"],
        )
    except (KeyError, TypeError, RepositoryAuthorityError) as error:
        raise ActionIntentError("verified Action authority is inconsistent") from error
    _check_peer_evidence(peer)
    _check_baseline_evidence(baseline, target, authority)


def _check_peer_evidence(peer: object) -> None:
    if not isinstance(peer, dict) or not isinstance(peer.get("ep_origin"), str):
        raise ActionIntentError("verified Action peer binding is inconsistent")
    try:
        if canonical_endpoint(peer["ep_origin"], allow_loopback_http=True) != peer["ep_origin"]:
            raise ActionIntentError("verified Action peer origin is noncanonical")
    except PeerConfigurationError as error:
        raise ActionIntentError("verified Action peer origin is invalid") from error
    if (set(peer) != {"ep_origin", "binding_id", "configuration_revision",
                             "configuration_digest"}
            or not isinstance(peer["binding_id"], str) or not peer["binding_id"]
            or type(peer["configuration_revision"]) is not int
            or peer["configuration_revision"] < 1
            or not isinstance(peer["configuration_digest"], str)
            or _DIGEST.fullmatch(peer["configuration_digest"]) is None):
        raise ActionIntentError("verified Action peer binding is inconsistent")


def _check_baseline_evidence(baseline: object, target: dict[str, str],
                             authority: dict[str, Any]) -> None:
    if (not isinstance(baseline, dict)
            or set(baseline) != {"source", "repository_id", "github_repository", "branch",
                                 "revision", "observed_at", "observation_digest", "approved_source_digest"}
            or baseline.get("source") != "GITHUB_DEFAULT_HEAD"
            or baseline.get("repository_id") != target["repository_id"]
            or baseline.get("github_repository") != authority.get("github_repository")
            or baseline.get("branch") != "main"
            or baseline.get("revision") != target["baseline_revision"]
            or not isinstance(baseline.get("observed_at"), str)
            or not baseline["observed_at"]
            or not isinstance(baseline.get("observation_digest"), str)
            or _DIGEST.fullmatch(baseline["observation_digest"]) is None
            or baseline["observation_digest"] != _digest(_encode({
                "repository": baseline["github_repository"],
                "branch": baseline["branch"], "revision": baseline["revision"],
            }))
            or not isinstance(baseline.get("approved_source_digest"), str)
            or _DIGEST.fullmatch(baseline["approved_source_digest"]) is None
            or baseline["approved_source_digest"] != _digest(_encode({
                "repository_id": baseline["repository_id"],
                "github_repository": baseline["github_repository"],
            }))):
        raise ActionIntentError("verified Action baseline is inconsistent")


def _check_binding(row: sqlite3.Row, document: dict[str, Any]) -> None:
    if document["correlation_status"] == "UNBOUND":
        if (row["slot_revision"] != 1 or document["correlation_id"] is not None
                or document["request_digest"] is not None):
            raise ActionIntentError("unbound Action intent is inconsistent")
    elif document["correlation_status"] == "BOUND":
        if (row["slot_revision"] not in {2, 3} or not isinstance(document["correlation_id"], str)
                or _IDENTIFIER.fullmatch(document["correlation_id"]) is None
                or not isinstance(document["request_digest"], str)
                or _DIGEST.fullmatch(document["request_digest"]) is None):
            raise ActionIntentError("bound Action intent is inconsistent")
    else:
        raise ActionIntentError("Action intent binding state is invalid")


def _current_baseline(source: ApprovedRepositoryEvidenceSource, target: dict[str, str]) -> dict[str, str]:
    from datetime import UTC, datetime
    from forge.mission_cli import _github_default_head

    branch, revision = _github_default_head(source.github_repository)
    if branch != "main" or revision != target["baseline_revision"]:
        raise ActionIntentError("Action target baseline differs from the current approved repository head")
    observed = {"repository": source.github_repository, "branch": branch, "revision": revision}
    return {
        "source": "GITHUB_DEFAULT_HEAD", "repository_id": source.repository_id,
        "github_repository": source.github_repository, "branch": branch, "revision": revision,
        "observed_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "observation_digest": _digest(_encode(observed)), "approved_source_digest": source.digest,
    }


def _intent_histories(connection: sqlite3.Connection, mission_id: str) -> dict[str, list[dict[str, Any]]]:
    rows = connection.execute(
        "SELECT * FROM mission_action_intent_revisions WHERE mission_id=? "
        "ORDER BY action_id,slot_revision", (mission_id,),
    ).fetchall()
    histories: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        histories.setdefault(row["action_id"], []).append(_row_document(row))
    for history in histories.values():
        if ([item["slot_revision"] for item in history] not in ([1], [1, 2], [1, 2, 3])
                or any(item["source_revision"] != history[0]["source_revision"]
                       or item["source_digest"] != history[0]["source_digest"]
                       or item["target"] != history[0]["target"] for item in history)
                or (len(history) == 3 and
                    (history[2]["correlation_id"] != history[1]["correlation_id"]
                     or history[2]["request_digest"] != history[1]["request_digest"]))):
            raise ActionIntentError("Action intent history is inconsistent")
    return histories


def _check_current_intent_source(connection: sqlite3.Connection, mission_id: str,
                                 actions: list[dict[str, Any]], histories: dict[str, Any],
                                 source_digests: set[str]) -> None:
    graph, source_digest = _source(connection, mission_id)
    by_id = {item["action_id"]: item for item in graph["actions"]}
    if (source_digests != {source_digest} or set(histories) != set(by_id)
            or any(item["target"] != by_id[item["action_id"]]["target"] for item in actions)):
        raise ActionIntentError("Action intents conflict with current planning source")
    if not any("authority" in item for item in actions):
        return
    current_state, scope = _approved_state(connection, mission_id)
    sources = _approved_sources(current_state, scope)
    for item in actions:
        if "authority" not in item:
            continue
        source = sources[item["target"]["repository_id"]]
        if (item["baseline"]["approved_source_digest"] != source.digest
                or item["baseline"]["github_repository"] != source.github_repository):
            raise ActionIntentError("verified Action source no longer matches approved provenance")


class ActionIntentLedger:
    """A short-transaction append-only ledger; no EP or provider effect occurs here."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def _latest(self, mission_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT r.* FROM mission_action_intent_revisions r JOIN ("
            "SELECT action_id,MAX(slot_revision) AS latest FROM mission_action_intent_revisions "
            "WHERE mission_id=? GROUP BY action_id) x "
            "ON r.mission_id=? AND r.action_id=x.action_id AND r.slot_revision=x.latest "
            "ORDER BY r.action_id", (mission_id, mission_id),
        ).fetchall()

    def materialize(self, mission_id: str) -> dict[str, Any]:
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            graph, source_digest = _source(self.connection, mission_id)
            if self.connection.execute(
                "SELECT 1 FROM mission_action_execution_slots WHERE mission_id=? LIMIT 1", (mission_id,)
            ).fetchone():
                raise ActionIntentError("legacy serial execution slots cannot be rematerialized")
            revision = graph["mission_revision"]
            for action in graph["actions"]:
                document = {
                    "contract_version": CONTRACT_VERSION, "mission_id": mission_id,
                    "action_id": action["action_id"], "slot_revision": 1,
                    "source_revision": revision, "source_digest": source_digest,
                    "target": action["target"], "correlation_status": "UNBOUND",
                    "correlation_id": None, "request_digest": None,
                    "target_verification": "UNVERIFIED", "dispatch_authorized": False,
                }
                encoded = _encode(document)
                prior = self.connection.execute(
                    "SELECT * FROM mission_action_intent_revisions "
                    "WHERE mission_id=? AND action_id=? AND slot_revision=1",
                    (mission_id, action["action_id"]),
                ).fetchone()
                if prior is None:
                    self.connection.execute(
                        "INSERT INTO mission_action_intent_revisions VALUES (?,?,?,?,?,?,?)",
                        (mission_id, action["action_id"], 1, revision, source_digest,
                         _digest(encoded), encoded),
                    )
                elif _row_document(prior) != document or prior["document"] != encoded:
                    raise ActionIntentError("Action intent conflicts with the pinned source")
            existing = self._latest(mission_id)
            if {row["action_id"] for row in existing} != {item["action_id"] for item in graph["actions"]}:
                raise ActionIntentError("Action intent set conflicts with the pinned source")
            return self.read(mission_id)

    def bind(self, mission_id: str, action_id: str, *, expected_slot_revision: int,
             correlation_id: str, request_digest: str) -> dict[str, Any]:
        if (not isinstance(correlation_id, str) or _IDENTIFIER.fullmatch(correlation_id) is None
                or not isinstance(request_digest, str) or _DIGEST.fullmatch(request_digest) is None
                or type(expected_slot_revision) is not int or expected_slot_revision < 1):
            raise ActionIntentError("Action correlation binding is invalid")
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            graph, source_digest = _source(self.connection, mission_id)
            self._read_snapshot(mission_id)
            if action_id not in {item["action_id"] for item in graph["actions"]}:
                raise ActionIntentError("Action is absent from the current planning snapshot")
            row = self.connection.execute(
                "SELECT * FROM mission_action_intent_revisions WHERE mission_id=? AND action_id=? "
                "ORDER BY slot_revision DESC LIMIT 1", (mission_id, action_id),
            ).fetchone()
            if row is None:
                raise ActionIntentError("Action intent has not been materialized")
            document = _row_document(row)
            if row["source_digest"] != source_digest or row["source_revision"] != graph["mission_revision"]:
                raise ActionIntentError("Action intent source is stale")
            if document["correlation_status"] == "BOUND":
                if (document["correlation_id"] == correlation_id
                        and document["request_digest"] == request_digest
                        and expected_slot_revision == row["slot_revision"] - 1):
                    view = _safe_view(document)
                    if row["slot_revision"] == 3:
                        view["target_verification"] = "PINNED_CURRENT_UNCHECKED"
                    return view
                raise ActionIntentError("Action correlation binding conflicts")
            if row["slot_revision"] != expected_slot_revision or document["correlation_status"] != "UNBOUND":
                raise ActionIntentError("Action intent revision conflicts")
            for other in self._latest(mission_id):
                if other["action_id"] != action_id and _row_document(other)["correlation_id"] == correlation_id:
                    raise ActionIntentError("Action correlation identity is already bound")
            bound = {**document, "slot_revision": expected_slot_revision + 1,
                     "correlation_status": "BOUND", "correlation_id": correlation_id,
                     "request_digest": request_digest}
            encoded = _encode(bound)
            self.connection.execute(
                "INSERT INTO mission_action_intent_revisions VALUES (?,?,?,?,?,?,?)",
                (mission_id, action_id, bound["slot_revision"], graph["mission_revision"],
                 source_digest, _digest(encoded), encoded),
            )
        return _safe_view(bound)

    def verify(self, mission_id: str, action_id: str, scope: RepositoryAuthorityScope,
               *, assert_selected_peer: Callable[[], None]) -> dict[str, Any]:
        """Pin current EP authority and current approved repository head to one bound Action."""
        graph, source_digest, target, current, source = self._verification_inputs(
            mission_id, action_id, scope,
        )
        prior = current if "authority" in current else None
        peer = {"ep_origin": scope.base_url, "binding_id": scope.peer_binding_id,
                "configuration_revision": scope.peer_configuration_revision,
                "configuration_digest": scope.peer_configuration_digest}
        if prior is not None and prior["peer"] != peer:
            raise ActionIntentError("selected EP peer binding differs from the pinned Action")
        authority = read_repository_authority(
            scope, repository_id=target["repository_id"], github_repository=source.github_repository,
            binding_revision=None if prior is None else prior["authority"]["binding_revision"],
            authority_digest=None if prior is None else prior["authority"]["authority_digest"],
        )
        baseline = _current_baseline(source, target)
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            assert_selected_peer()
            return self._commit_verification(
                mission_id, action_id, graph, source_digest, target, current,
                authority, baseline, peer,
            )

    def _verification_inputs(self, mission_id: str, action_id: str,
                             scope: RepositoryAuthorityScope) -> tuple[
                                 dict[str, Any], str, dict[str, str], dict[str, Any],
                                 ApprovedRepositoryEvidenceSource]:
        snapshot = self.read(mission_id)
        if snapshot["source_freshness"] != "CURRENT":
            raise ActionIntentError("Action intent source is stale")
        graph, source_digest = _source(self.connection, mission_id)
        target = next((item["target"] for item in graph["actions"]
                       if item["action_id"] == action_id), None)
        current = next((item for item in snapshot["actions"] if item["action_id"] == action_id), None)
        if (target is None or current is None or current["correlation_status"] != "BOUND"
                or target["ep_instance_id"] != scope.instance_id
                or target["project_id"] != scope.project_id
                or re.fullmatch(r"[0-9a-f]{40}", target["baseline_revision"]) is None):
            raise ActionIntentError("Action target is not ready for current authority verification")
        state, approved_scope = _approved_state(self.connection, mission_id)
        source = _approved_sources(state, approved_scope)[target["repository_id"]]
        return graph, source_digest, target, current, source

    def _commit_verification(self, mission_id: str, action_id: str, graph: dict[str, Any],
                             source_digest: str, target: dict[str, str], current: dict[str, Any],
                             authority: dict[str, Any], baseline: dict[str, str],
                             peer: dict[str, Any]) -> dict[str, Any]:
        latest_graph, latest_digest = _source(self.connection, mission_id)
        row = next((item for item in self._latest(mission_id) if item["action_id"] == action_id), None)
        if (row is None or latest_digest != source_digest or latest_graph != graph
                or row["source_digest"] != source_digest):
            raise ActionIntentError("Action source changed during authority verification")
        document = _row_document(row)
        if document["correlation_id"] != current["correlation_id"] or document["target"] != target:
            raise ActionIntentError("Action identity changed during authority verification")
        if row["slot_revision"] == 3:
            stable_baseline = {key: value for key, value in baseline.items() if key != "observed_at"}
            pinned_baseline = {key: value for key, value in document["baseline"].items()
                               if key != "observed_at"}
            if document["authority"] != authority or document["peer"] != peer or pinned_baseline != stable_baseline:
                raise ActionIntentError("pinned Action authority or baseline changed")
            return _safe_view(document)
        if row["slot_revision"] != 2:
            raise ActionIntentError("Action correlation is not bound")
        verified = {**document, "slot_revision": 3, "target_verification": "VERIFIED",
                    "authority": authority, "baseline": baseline, "peer": peer}
        encoded = _encode(verified)
        self.connection.execute(
            "INSERT INTO mission_action_intent_revisions VALUES (?,?,?,?,?,?,?)",
            (mission_id, action_id, 3, graph["mission_revision"], source_digest, _digest(encoded), encoded),
        )
        return _safe_view(verified)

    def read(self, mission_id: str) -> dict[str, Any]:
        if self.connection.in_transaction:
            return self._read_snapshot(mission_id)
        with self.connection:
            self.connection.execute("BEGIN")
            return self._read_snapshot(mission_id)

    def _read_snapshot(self, mission_id: str) -> dict[str, Any]:
        histories = _intent_histories(self.connection, mission_id)
        actions = [history[-1] for history in histories.values()]
        source_revisions = {item["source_revision"] for item in actions}
        source_digests = {item["source_digest"] for item in actions}
        if len(source_revisions) > 1 or len(source_digests) > 1:
            raise ActionIntentError("Action intents have inconsistent sources")
        state_row = self.connection.execute(
            "SELECT document FROM mission_state WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if state_row is None:
            raise ActionIntentError("Action intent Mission is unavailable")
        try:
            state = json.loads(state_row[0])
            current_revision = state["revision"]
        except (TypeError, ValueError, KeyError) as error:
            raise ActionIntentError("Action intent Mission is malformed") from error
        freshness = "UNAVAILABLE" if not actions else (
            "CURRENT" if current_revision in source_revisions else "STALE"
        )
        if freshness == "CURRENT":
            _check_current_intent_source(self.connection, mission_id, actions, histories, source_digests)
        return {"contract_version": CONTRACT_VERSION, "mission_id": mission_id,
                "source_freshness": freshness, "read_only": True,
                "dispatch_authorized": False,
                "actions": [{**_safe_view(action),
                             "target_verification": "PINNED_CURRENT_UNCHECKED"
                             if action["target_verification"] == "VERIFIED"
                             else action["target_verification"]} for action in actions]}
