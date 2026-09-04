# Forge V1 Bootstrap Orchestrator Readiness

**AUTHORITY = DERIVED.** This hardens interpretation of the canonical V1 DAG; it is not a second roadmap, Mission graph, Runtime Service, Execution Host, lease authority, or runner. It authorizes no Mission, worker, worktree, subprocess, PR, merge, or repository mutation.

## Baseline and conclusion

| Evidence | Revision |
| --- | --- |
| Forge `main` | `7de68b3b70ea834145a88746beb00e5461c40ea1` |
| V1 DAG | `forge-v1-implementation-dag.json`, schema 1 |
| EP continuity provenance | merged Forge PR #13 |

PRs #10–#13 are merged. `BASELINE_VALIDATION = PASS` only when `bash scripts/validate.sh` and the dedicated DAG validator pass.

The former DAG has semantic ordering, but alone is not scheduler-grade: lanes do not express write conflicts, DoR/DoD are prose, and PR/post-merge state is absent. Its machine-readable companion supplies scheduler facts keyed only by existing node IDs.

`BOOTSTRAP_DISPATCHABILITY_CONTRACT = DEFINED`:

```text
DISPATCHABLE = SEMANTIC_READY AND DEPENDENCY_SAFE AND REPOSITORY_SAFE
             AND APPROVED_MISSION_BOUND AND OPERATOR_BOOTSTRAP_AUTHORIZATION
```

`SEMANTIC_READY` means machine-decided DoR, complete predecessors, satisfied external gates, and available contracts. `DEPENDENCY_SAFE` means no unfinished predecessor, producer violation or invalid snapshot. `REPOSITORY_SAFE` means compatible declared scopes and isolated worktrees. The final two terms prevent governance bypass.

## Boundary and governance

Temporary local scheduling for this Forge bootstrap repository is `BOOTSTRAP_COORDINATION`, never an execution lease; EP remains the repository-write lease owner. `BOOTSTRAP_RUNNER_IS_LEASE_AUTHORITY = FALSE`; `BOOTSTRAP_PROMPT_IS_AUTHORITY = FALSE`; `CI_GREEN_UNLOCKS_DEPENDENTS = FALSE`; `POST_MERGE_DAG_REEVALUATION = TRUE`; `HUMAN_GATE_GLOBAL_STOP_BY_DEFAULT = FALSE`.

The canonical [V1 Bootstrap Governance Decision](FORGE_V1_BOOTSTRAP_GOVERNANCE_DECISION.md) selects a bounded hybrid programme authorization. `BOOTSTRAP_MISSION_AUTHORITY = BOUNDED_V1_BOOTSTRAP_PROGRAMME_AUTHORIZATION (MODEL_C)`: an explicit human authorization record admits only its immutable node set and authority envelope. It never omits the permanent Roadmap → Candidate → Business approval → Architecture approval → Mission → Action model; a new product, architecture, security, cross-product, repository, scope, or undefined-contract finding returns the node to full governance. `BOOTSTRAP_AUTO_MERGE_POLICY = DISABLED`; a human merge remains required.

## Scheduler-grade coverage

The companion contract maps every node to semantic `write_scopes`, `read_scopes`, `exclusive_scopes`, `integration_scopes`, machine criteria, PR evidence, merge gate, and post-merge evidence. These are semantic labels, not guessed filenames. Two nodes may run together only when no write/exclusive scope conflicts and neither integration scope requires the other's merge. `ARCHITECTURE_CONTRACT`, `API_SCHEMA`, `RUNTIME_SERVICE`, and `CROSS_PRODUCT_CONTRACT` are exclusive by default.

| Question | Before | Hardened answer |
| --- | --- | --- |
| semantic readiness / predecessors / producer gates | partial | machine criteria plus gate query |
| parallel/write safety | descriptive lane | compatible scopes |
| human pause and scope | partial | immutable execution package |
| PR/merge/post-merge completion | prose | separate evidence boundaries |
| stale work / review / CI repair | absent | bounded lifecycle and classification |

`V1_NODE_COUNT = 9`; `AMBIGUOUS_PARALLELISM_NODES = 0`; `V1_NODE_WITHOUT_WRITE_SAFETY_CLASSIFICATION = 0`; `AMBIGUOUS_MACHINE_DOR_CRITERIA = 0`; `AMBIGUOUS_MACHINE_DOD_CRITERIA = 0`; `QUALIFICATION_WITHOUT_EVIDENCE_SOURCE = 0`.

## Isolation, snapshot and staleness

Each future context has one node, immutable Mission/Action identity, unique branch/worktree, pinned main SHA and correlation ID, with no shared uncommitted state. It rejects duplicate active node/correlation and never reuses a terminal worktree.

`BOOTSTRAP_WORKTREE_ISOLATION_CONTRACT = DEFINED`:
`UNIQUE_BRANCH + UNIQUE_WORKTREE + PINNED_BASE_SHA + NODE_ID_CORRELATION + NO_SHARED_UNCOMMITTED_STATE`.

`BOOTSTRAP_DISPATCH_SNAPSHOT = DEFINED`: DAG schema/digest, node, main SHA, roadmap/productization digests, external-gate provenance and evaluated DoR evidence explain every future dispatch.

After main moves: unchanged predecessors/scopes/contracts/DAG/gate provenance is `STILL_VALID`; compatible code movement is `REBASE_REQUIRED`; changed read contract is `STALE_CONTRACT`; predecessor/gate change is `BLOCKED_BY_NEW_PREDECESSOR`; changed scope/DAG/architecture is `REPLAN_REQUIRED`. Git mergeability is never sufficient. `ACTIVE_NODE_STALENESS_CONTRACT = DEFINED`.

## Lifecycle, qualification and human pause

```text
NOT_READY -> READY -> BOOTSTRAP_CLAIMED -> IMPLEMENTING -> PR_OPEN -> CI_RUNNING
  -> {REVIEW_REQUIRED | REPAIR_REQUIRED | MERGE_READY} -> {WAITING_HUMAN_GATE | MERGED}
  -> POST_MERGE_QUALIFICATION -> DONE
```

`BLOCKED`, `FAILED`, `STALE`, `SUPERSEDED`, and `REPLAN_REQUIRED` require explicit resolution. `BOOTSTRAP_NODE_LIFECYCLE = DEFINED`. `CODE_IMPLEMENTED`, `PR_OPEN`, `CI_GREEN`, `MERGE_READY`, `MERGED`, and `DONE` differ; only `DONE` satisfies a predecessor.

Every qualification names `LOCAL_TEST`, `HOSTED_CI`, `INSTALLED_PRODUCT_CANARY`, `SECURITY_GATE`, `BROWSER_GATE`, `CROSS_PRODUCT_GATE`, `HUMAN_REVIEW`, `OWNER_AUTHORIZATION`, or `POST_MERGE_GATE`, exact SHA, result and new-head invalidation.

Ordinary review is same-node `REPAIR_REQUIRED`; an architecture decision, dependency, new capability or scope expansion is `REPLAN_REQUIRED`. CI failures must first classify as `IMPLEMENTATION_DEFECT`, `TEST_DEFECT`, `FLAKY_INFRASTRUCTURE`, `STALE_BASE`, `DEPENDENCY_CHANGED`, `SECURITY_FAILURE`, `QUALIFICATION_GAP`, or `UNDEFINED_CONTRACT`. No canonical retry limit exists: automatic repair requires a future operator-set finite limit; otherwise it is disallowed. `UNBOUNDED_AUTONOMOUS_REPAIR = FALSE`.

Human UI review, owner authorization, business approval, architecture approval and security decision pause only their node; each needs named evidence and returns to re-evaluation. Other safe nodes continue. The canonical governance decision supplies Forge's consequence-based risk mapping: `NORMAL_LOW` needs no separate Owner Authorization, `ELEVATED` needs exact-head Owner Authorization, and `HIGH` needs exact-head Owner Authorization plus security review. A new commit invalidates the authorization. This is a Forge contract, not an inference from EP.

## External gates and parallel proof

EP uses PR #13's named producer state, never `EP_READY`; Workspace uses its named onboarding producer and prerequisite. `OPAQUE_EP_BOOTSTRAP_GATE = 0`; `OPAQUE_WORKSPACE_BOOTSTRAP_GATE = 0`.

| Pair | Semantic parallel | Dependency safe | Write-safe | Integration | Dispatch safe |
| --- | --- | --- | --- | --- | --- |
| F1/F2, F1/F5, F1/F6 | No | No | N/A | F2 predecessor/API | No |
| F2/F5, F2/F6 | No | No | N/A | F2 must be done | No |
| F5/F6 | Yes after F2 | Yes | Yes | versioned API read contract | Yes, after Mission approval and operator authorization |

`MAX_PARALLELISM = DYNAMIC`; ready nodes, scope compatibility, human gates, worktree/repository capacity and a future operator upper bound determine it. `STATIC_ASSUMED_PARALLELISM = FALSE`.

## Future Codex adapter

The future adapter consumes an immutable execution package: snapshot/node/Mission/Action identity, objective/scope, DoR/DoD evidence, architecture references, allowed/forbidden scopes, validation, gates, base SHA and worktree identity. It may report work/evidence; it cannot approve, expand scope, create a lease, edit DAG authority, merge, or bypass governance. A deterministic renderer presents that package as a transient Codex prompt. Official OpenAI documentation documents non-interactive and worktree integration surfaces; Forge's contract, not that prompt, remains authority.

`CODEX_BOOTSTRAP_ADAPTER_CONTRACT = DEFINED`; `BOOTSTRAP_PROMPT_IS_AUTHORITY = FALSE`.

After a human merge: refresh main, verify merge SHA, clean context, refresh Repository Truth, run post-merge qualification, refresh DAG/gate evidence, then re-evaluate readiness.

## Governance closure

The governance decision resolves the three prior blockers: `BOOTSTRAP_MISSION_AUTHORITY = RESOLVED`, `OWNER_AUTHORIZATION_SCHEDULER_CONTRACT = RESOLVED`, and `BOOTSTRAP_AUTO_MERGE_POLICY = DISABLED`. The future runner is therefore contract-ready for a separately approved implementation Mission; dispatch still requires an actual, non-stale programme authorization record and cannot use repair automation.

`FORGE_V1_BOOTSTRAP_ORCHESTRATOR_READY_FOR_IMPLEMENTATION = YES`.
