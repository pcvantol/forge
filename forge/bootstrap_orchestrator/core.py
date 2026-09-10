"""Interface-neutral governed single-node bootstrap orchestration.

All effects are injected ports.  This module deliberately cannot approve,
merge, or retry a worker; it only constructs and evaluates bounded evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sqlite3
from typing import Any, Mapping, Protocol

SCHEMA_VERSION = "1"
MAX_ACTIVE_BOOTSTRAP_DISPATCHES = 1
RISK_OWNER_AUTHORIZATION = {"NORMAL_LOW": False, "ELEVATED": True, "HIGH": True}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_canonical(value).encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Criterion:
    criterion: str
    result: bool
    evidence: tuple[str, ...]
    source: str
    provenance: str
    evaluated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgrammeAuthorization:
    authorization_id: str
    programme_id: str
    dag_digest: str
    approved_main_sha: str
    approved_node_ids: tuple[str, ...]
    architecture_references: tuple[str, ...]
    productization_references: tuple[str, ...]
    allowed_repositories: tuple[str, ...]
    allowed_write_scopes: tuple[str, ...]
    preserved_human_gates: tuple[str, ...]
    preserved_external_gates: tuple[str, ...]
    approved_by: str
    approved_at: str
    programme_version: str = "1"
    revoked_at: str | None = None
    superseded_by: str | None = None

    def __post_init__(self) -> None:
        if not all((self.authorization_id, self.programme_id, self.dag_digest, self.approved_main_sha,
                    self.approved_node_ids, self.allowed_repositories, self.allowed_write_scopes,
                    self.approved_by, self.approved_at)):
            raise ValueError("programme authorization requires complete governed identity and scope")


@dataclass(frozen=True)
class Dag:
    source: str
    digest: str
    nodes: Mapping[str, Mapping[str, Any]]
    external_gates: Mapping[str, Mapping[str, Any]]


def load_dag(path: Path) -> Dag:
    """Load the canonical source of truth; reject malformed or opaque graph data."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or document.get("authority") != "DERIVED":
        raise ValueError("unsupported canonical V1 DAG")
    nodes = document.get("nodes")
    gates = document.get("external_gate_details")
    if not isinstance(nodes, list) or not isinstance(gates, list):
        raise ValueError("DAG requires nodes and explicit external gate details")
    indexed = {item.get("id"): item for item in nodes if isinstance(item, dict) and item.get("id")}
    if len(indexed) != len(nodes):
        raise ValueError("DAG node identifiers must be unique and non-empty")
    gate_map = {item.get("id"): item for item in gates if isinstance(item, dict) and item.get("id")}
    for node_id, node in indexed.items():
        required = ("predecessors", "external_gates", "dor", "dod", "human_gates", "parallelism", "v1_classification")
        if any(not node.get(key) and key not in {"predecessors", "external_gates"} for key in required):
            raise ValueError(f"DAG node {node_id} lacks scheduler provenance")
        if any(predecessor not in indexed for predecessor in node["predecessors"]):
            raise ValueError(f"DAG node {node_id} has an unknown predecessor")
        if any(gate not in gate_map for gate in node["external_gates"]):
            raise ValueError(f"DAG node {node_id} has an unknown external gate")
    if any(not item.get("current_state") or item.get("current_state") in {"EP_READY", "WORKSPACE_READY"} for item in gate_map.values()):
        raise ValueError("external gates must retain precise producer states")
    return Dag(str(path), _digest(document), indexed, gate_map)


@dataclass(frozen=True)
class DispatchSnapshot:
    dispatch_id: str
    node_id: str
    mission_id: str
    intent_id: str
    action_id: str
    dag_digest: str
    node_digest: str
    base_sha: str
    authorization_id: str
    criteria: tuple[Criterion, ...]
    write_scopes: tuple[str, ...]
    risk_class: str
    created_at: str

    @property
    def digest(self) -> str:
        return _digest(asdict(self))


@dataclass(frozen=True)
class ExecutionPackage:
    snapshot: DispatchSnapshot
    objective: str
    allowed_write_scopes: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    validation_commands: tuple[str, ...]
    human_gates: tuple[str, ...]
    worktree: str
    branch: str

    @property
    def digest(self) -> str:
        return _digest(asdict(self))

    def prompt(self) -> str:
        """Deterministic provider presentation; package/snapshot remain authority."""
        return "\n".join((
            "FORGE BOOTSTRAP V0 EXECUTION PACKAGE (presentation only)",
            f"dispatch: {self.snapshot.dispatch_id}", f"node: {self.snapshot.node_id}",
            f"objective: {self.objective}", f"allowed write scopes: {', '.join(self.allowed_write_scopes)}",
            f"base SHA: {self.snapshot.base_sha}", f"validation: {', '.join(self.validation_commands)}",
            "forbidden: " + "; ".join(self.forbidden_actions),
            "stop: do not approve, expand scope, merge, resolve human gates, or retry work.",
        ))


@dataclass(frozen=True)
class LifecycleEvent:
    event_type: str
    dispatch_id: str
    node_id: str
    occurred_at: str
    lifecycle_state: str
    evidence_references: tuple[str, ...] = ()
    event_id: str = ""

    def __post_init__(self) -> None:
        if self.event_type not in {"READINESS_EVALUATED", "DISPATCH_BLOCKED", "DISPATCH_SNAPSHOT_CREATED", "WORKTREE_PLANNED", "WORKTREE_CREATED", "CODEX_EXECUTION_STARTED", "CODEX_EXECUTION_COMPLETED", "WRITE_SCOPE_VALIDATED", "LOCAL_QUALIFICATION_PASSED", "LOCAL_QUALIFICATION_FAILED", "HUMAN_GATE_ENTERED", "MERGE_READY", "DONE", "FAILED"}:
            raise ValueError("unsupported bounded lifecycle event")
        if not self.event_id:
            object.__setattr__(self, "event_id", "event-" + _digest(asdict(self))[-16:])


@dataclass(frozen=True)
class WorktreePlan:
    dispatch_id: str
    node_id: str
    repository: str
    base_sha: str
    branch: str
    path: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", self.branch) or ".." in self.branch or self.branch.startswith("/"):
            raise ValueError("unsafe bootstrap branch")
        target = Path(self.path)
        if not target.is_absolute() or ".." in target.parts:
            raise ValueError("worktree path must be absolute and normalized")


def plan_worktree(*, dispatch_id: str, node_id: str, repository: Path, base_sha: str, root: Path) -> WorktreePlan:
    """Create no worktree; return a bounded plan suitable for a Git adapter."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", dispatch_id) or not re.fullmatch(r"F[1-9]", node_id):
        raise ValueError("unsafe dispatch or node identity")
    if not re.fullmatch(r"[0-9a-f]{7,64}", base_sha): raise ValueError("base SHA is invalid")
    resolved_repository, resolved_root = repository.resolve(), root.resolve()
    if not (resolved_repository / ".git").exists() or resolved_root == resolved_repository:
        raise ValueError("repository/worktree root is unsafe")
    return WorktreePlan(dispatch_id, node_id, str(resolved_repository), base_sha,
                        f"bootstrap/{node_id}/{dispatch_id}", str((resolved_root / f"{node_id}-{dispatch_id}").resolve()))


def changed_paths(repository: Path) -> tuple[str, ...]:
    output = subprocess.check_output(("git", "-C", str(repository), "diff", "--name-only"), text=True)
    paths = tuple(sorted(line for line in output.splitlines() if line))
    if any(Path(path).is_absolute() or ".." in Path(path).parts for path in paths):
        raise ValueError("unsafe changed path")
    return paths


class DispatchStore:
    """Durable, idempotent operational state; snapshots are never overwritten."""
    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path); self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS bootstrap_dispatch (dispatch_id TEXT PRIMARY KEY, state TEXT NOT NULL, snapshot TEXT NOT NULL, branch TEXT, worktree TEXT, worker_started INTEGER NOT NULL DEFAULT 0, pr_id TEXT);
        CREATE TABLE IF NOT EXISTS bootstrap_event (dispatch_id TEXT NOT NULL, sequence INTEGER NOT NULL, document TEXT NOT NULL, PRIMARY KEY(dispatch_id, sequence));
        CREATE TRIGGER IF NOT EXISTS bootstrap_event_immutable_update BEFORE UPDATE ON bootstrap_event BEGIN SELECT RAISE(ABORT, 'events immutable'); END;
        CREATE TRIGGER IF NOT EXISTS bootstrap_event_immutable_delete BEFORE DELETE ON bootstrap_event BEGIN SELECT RAISE(ABORT, 'events immutable'); END;
        """); self.connection.commit()
    def close(self) -> None: self.connection.close()
    def create(self, snapshot: DispatchSnapshot) -> None:
        document = _canonical(asdict(snapshot))
        row = self.connection.execute("SELECT snapshot FROM bootstrap_dispatch WHERE dispatch_id=?", (snapshot.dispatch_id,)).fetchone()
        if row and row["snapshot"] != document: raise ValueError("dispatch identity conflicts with immutable snapshot")
        if not row:
            with self.connection: self.connection.execute("INSERT INTO bootstrap_dispatch(dispatch_id,state,snapshot) VALUES(?,?,?)", (snapshot.dispatch_id, "SNAPSHOT_CREATED", document))
    def state(self, dispatch_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM bootstrap_dispatch WHERE dispatch_id=?", (dispatch_id,)).fetchone()
        if not row: raise ValueError("unknown dispatch")
        return dict(row)
    def transition(self, dispatch_id: str, state: str, event: LifecycleEvent, *, branch: str | None = None, worktree: str | None = None) -> None:
        current = self.state(dispatch_id)
        if current["state"] in {"DONE", "FAILED"}: raise ValueError("terminal dispatch cannot advance")
        event_doc = _canonical(asdict(event)); sequence = self.connection.execute("SELECT COUNT(*) FROM bootstrap_event WHERE dispatch_id=?", (dispatch_id,)).fetchone()[0] + 1
        with self.connection:
            self.connection.execute("UPDATE bootstrap_dispatch SET state=?, branch=COALESCE(?,branch), worktree=COALESCE(?,worktree) WHERE dispatch_id=?", (state, branch, worktree, dispatch_id))
            self.connection.execute("INSERT INTO bootstrap_event VALUES(?,?,?)", (dispatch_id, sequence, event_doc))
    def events(self, dispatch_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(row["document"]) for row in self.connection.execute("SELECT document FROM bootstrap_event WHERE dispatch_id=? ORDER BY sequence", (dispatch_id,)))


class GitWorktreePort:
    """Only accepts a prior plan; never runs commands supplied by runtime text."""
    def create_or_reconcile(self, plan: WorktreePlan) -> WorktreePlan:
        target = Path(plan.path)
        if target.exists():
            branch = subprocess.check_output(("git", "-C", str(target), "branch", "--show-current"), text=True).strip()
            if branch != plan.branch: raise ValueError("existing worktree belongs to another branch")
            return plan
        repository = Path(plan.repository)
        subprocess.run(("git", "-C", str(repository), "cat-file", "-e", f"{plan.base_sha}^{{commit}}"), check=True, capture_output=True, text=True)
        subprocess.run(("git", "-C", str(repository), "show-ref", "--verify", "--quiet", f"refs/heads/{plan.branch}"), check=False, capture_output=True)
        subprocess.run(("git", "-C", str(repository), "worktree", "add", "-b", plan.branch, str(target), plan.base_sha), check=True, capture_output=True, text=True)
        return plan


@dataclass(frozen=True)
class WorkerResult:
    invocation_id: str; exit_code: int; stdout_reference: str; stderr_reference: str

class WorkerPort(Protocol):
    def recover(self, dispatch_id: str) -> WorkerResult | None: ...
    def invoke_once(self, package: ExecutionPackage) -> WorkerResult: ...

class QualificationPort(Protocol):
    def qualify(self, package: ExecutionPackage) -> tuple[bool, tuple[str, ...]]: ...

@dataclass(frozen=True)
class PullRequestState:
    pr_id: str; head_sha: str; merged: bool; mergeable: bool; checks_passed: bool; review_state: str; unresolved_threads: int

class PullRequestPort(Protocol):
    def recover(self, dispatch_id: str, branch: str) -> PullRequestState | None: ...
    def create_once(self, package: ExecutionPackage) -> PullRequestState: ...


def reconcile_worker(store: DispatchStore, dispatch_id: str, worker: WorkerPort, package: ExecutionPackage) -> WorkerResult | None:
    """Exactly once: recover external acknowledgement before any invocation."""
    state = store.state(dispatch_id)
    recovered = worker.recover(dispatch_id)
    if recovered is not None: return recovered
    if state["worker_started"]:
        raise ValueError("worker outcome is unknown; fail closed without retry")
    with store.connection:
        store.connection.execute("UPDATE bootstrap_dispatch SET worker_started=1 WHERE dispatch_id=?", (dispatch_id,))
    return worker.invoke_once(package)


def reconcile_pr(store: DispatchStore, dispatch_id: str, port: PullRequestPort, package: ExecutionPackage) -> PullRequestState:
    state = store.state(dispatch_id)
    found = port.recover(dispatch_id, package.branch)
    if found is not None: return found
    if state["pr_id"]: raise ValueError("PR outcome is unknown; fail closed without duplicate creation")
    result = port.create_once(package)
    with store.connection: store.connection.execute("UPDATE bootstrap_dispatch SET pr_id=? WHERE dispatch_id=?", (result.pr_id, dispatch_id))
    return result


def merge_ready(pr: PullRequestState, *, local_qualification: bool, human_gates_satisfied: bool,
                owner_authorized: bool, security_reviewed: bool, risk_class: str) -> bool:
    if risk_class not in RISK_OWNER_AUTHORIZATION: raise ValueError("unknown risk class")
    return bool(local_qualification and pr.mergeable and pr.checks_passed and pr.review_state == "APPROVED" and not pr.unresolved_threads and human_gates_satisfied and (not RISK_OWNER_AUTHORIZATION[risk_class] or owner_authorized) and (risk_class != "HIGH" or security_reviewed))


class BootstrapOrchestrator:
    """Pure evaluator and evidence builder; transport adapters live outside this core."""
    def __init__(self, dag: Dag, scheduler_contract: Mapping[str, Any], *, repository_id: str, main_sha: str) -> None:
        self.dag, self.scheduler_contract = dag, scheduler_contract
        self.repository_id, self.main_sha = repository_id, main_sha

    def evaluate(self, node_id: str, authorization: ProgrammeAuthorization | None, *, completed: set[str],
                 repository_clean: bool, unresolved_human_gates: set[str] = frozenset()) -> tuple[Criterion, ...]:
        if node_id not in self.dag.nodes:
            raise ValueError("unknown canonical DAG node")
        node = self.dag.nodes[node_id]; contract = self.scheduler_contract["node_contracts"].get(node_id)
        if not contract: raise ValueError("scheduler contract lacks node")
        now = _now()
        def item(name: str, result: bool, evidence: tuple[str, ...], source: str) -> Criterion:
            return Criterion(name, result, evidence, source, self.dag.digest, now)
        valid_auth = authorization is not None and not authorization.revoked_at and not authorization.superseded_by
        criteria = [
            item("PROGRAMME_AUTHORIZED", valid_auth, () if authorization is None else (authorization.authorization_id,), "programme authorization"),
            item("NODE_AUTHORIZED", bool(valid_auth and node_id in authorization.approved_node_ids), (node_id,), "programme authorization"),
            item("AUTHORIZATION_NOT_STALE", bool(valid_auth and authorization.dag_digest == self.dag.digest and authorization.approved_main_sha == self.main_sha), (self.dag.digest, self.main_sha), "DAG/main provenance"),
            item("REPOSITORY_SAFE", bool(valid_auth and repository_clean and self.repository_id in authorization.allowed_repositories), (self.repository_id,), "repository preflight"),
            item("WRITE_SCOPE_SAFE", bool(valid_auth and set(contract["write_scopes"]) <= set(authorization.allowed_write_scopes)), tuple(contract["write_scopes"]), "scheduler contract"),
            item("PREDECESSORS_DONE", set(node["predecessors"]) <= completed, tuple(node["predecessors"]), "DAG predecessors"),
            item("EXTERNAL_GATES_PASS", all(self.dag.external_gates[g]["current_state"] == "EP_PRODUCER_AVAILABLE" for g in node["external_gates"]), tuple(node["external_gates"]), "producer metadata"),
            item("NODE_DOR_PASS", not any(str(value).startswith("PREDECESSOR_DONE:") and str(value).split(":", 1)[1] not in completed for value in contract["dor"]), tuple(contract["dor"]), "scheduler contract"),
            item("NO_UNRESOLVED_HUMAN_GATE", not (set(node["human_gates"]) - {"NO_HUMAN_GATE"}) & unresolved_human_gates, tuple(node["human_gates"]), "human gates"),
        ]
        return tuple(criteria)

    def dispatchable(self, criteria: tuple[Criterion, ...]) -> bool:
        return all(item.result for item in criteria)

    def snapshot(self, *, dispatch_id: str, node_id: str, mission_id: str, intent_id: str, action_id: str,
                 authorization: ProgrammeAuthorization, criteria: tuple[Criterion, ...]) -> DispatchSnapshot:
        if not self.dispatchable(criteria): raise ValueError("dispatch snapshot requires passing structured readiness")
        contract = self.scheduler_contract["node_contracts"][node_id]
        return DispatchSnapshot(dispatch_id, node_id, mission_id, intent_id, action_id, self.dag.digest,
                                _digest(self.dag.nodes[node_id]), self.main_sha, authorization.authorization_id,
                                criteria, tuple(contract["write_scopes"]), contract["risk_class"], _now())

    def package(self, snapshot: DispatchSnapshot, *, objective: str, worktree: str, branch: str) -> ExecutionPackage:
        return ExecutionPackage(snapshot, objective, snapshot.write_scopes,
            ("approve Mission or programme authorization", "expand scope", "merge or enable auto-merge", "autonomous repair", "modify another repository"),
            ("bash scripts/validate.sh",), tuple(self.dag.nodes[snapshot.node_id]["human_gates"]), worktree, branch)
