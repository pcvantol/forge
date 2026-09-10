# Forge and four-repository consolidation / parking

Increment: `FOUR_REPO_CONSOLIDATION_PARKING_2026_09_10`. Recorded 2026-09-10.
Scoped record under the [canonical Forge roadmap](../../knowledge/bootstrap/10_ROADMAP.md).
[Documentary DAG](CONSOLIDATION_PARKING_2026_09_10_DAG.json).

## Decision, not a new engineering programme

The owner requested that the four repositories be inventoried, unfinished work
preserved and parked, and open items retained in documentation/roadmap DAGs.
Only documentation consolidation is active. No product implementation, runtime
run, review-provider dispatch, release, installation, cleanup or new Mission is
authorized here. NO_BUMP. Documentary authority begins at the owning protected
merge; peer documents remain pending until their own delivery is verified.

PARKED is a planning disposition, not cancellation, runtime failure/dismissal,
lease release or proof that an agent has stopped. Old handoff instructions to
continue installer or quality improvements are not current pickup instructions.
Do not automatically resume the earlier isolated EP qualification attempt.
Later resumption requires an explicitly selected bounded task and applicable
current authority. Missing prerequisites are recorded, not automatically built.

The existing strategic goal remains the first real serial Forge Mission loop:
approved Mission -> Forge-derived A -> real EP execution -> verified immutable
EP evidence -> durable Forge reconciliation -> Forge restart/reopen -> newly
derived non-preconfigured B without owner relay -> evidence-proven completion.
No Workspace UI, universal installer completion, all-branch cleanup, general
Project Hygiene implementation or broad subagent optimization is a new gate.
Necessary installed capability and mandatory assurance are not waived.

Forge owns planning and this cross-product index. Each peer owns its actual
status, contracts and evidence. This is a documentary graph, not an executable
programme, shared database, runtime authority or replacement for existing DAGs.
No peer SQL. Repo cleanup is reconciliation work, not a hidden Forge Mission.

## Evidence and snapshot

SOURCE_VERIFIED below means GitHub readback on 2026-09-10. USER_REPORTED means
the owner's architecture reports supplied in this task, not direct access to
Mac worktrees. Exact local paths/SHAs, stashes, ignored files, active processes
and leases were not independently inspected. Missing details remain open.

| Product | Pinned remote main | Remote work at the pre-documentation snapshot |
| --- | --- | --- |
| Forge | `847b552c1c9d4824a2b57bca96a28d4bc851cc09` | main and release-2.3.1; no open PR |
| EP | `d329852b06f71a10e13b91dd1d1f87982ef6b90d` | Draft #175 plus retained operational-record/version-operation and release refs |
| Workspace | `bad3dd7d7dafd6c907af440a10f9da0ed7261714` | No open product PR; documentation #26 was opened by this consolidation task |
| Forge Platform | `0bb24eb1094d7912de4e624b3ecd97fe73159ce9` | main only; parking PR #61 merged |

Remote sources: [Forge heads](https://api.github.com/repos/pcvantol/forge/git/matching-refs/heads/),
[EP heads](https://api.github.com/repos/pcvantol/engineering-platform/git/matching-refs/heads/),
[Workspace #26](https://github.com/pcvantol/workspace/pull/26),
[Forge Platform #61](https://github.com/pcvantol/forge-platform/pull/61).
These endpoint URLs are mutable; the table pins the observation. New documentary
branches/PRs created by this task are not newly discovered product work.

## Forge local inventory and per-item disposition

USER_REPORTED: 13 local branches (main plus 12 features), 12 worktrees, none on
main. Local main `03c7572` is 16 commits behind the reported remote baseline;
locally cached origin/main was itself one commit stale. Do not synchronize by
switching the dirty primary checkout. A future fast-forward needs current
ancestry, ownership and worktree checks; no force/reset is authorized here.

| Item / node | Reported state | Disposition and later acceptance |
| --- | --- | --- |
| F-PRODUCTIZATION: codex/forge-productization-reconciliation | Primary worktree; one changed architecture document and eight untracked items; some paths also exist on main but differ | PRESERVE_AND_ASSESS. Compare each actual file against pinned main; classify PRESENT_ON_MAIN, SUPERSEDED, GENUINE_RESIDUAL or UNRESOLVED. No merge/overwrite from filenames or stale architecture. Preserve .engineering and its target. |
| F-ORCHESTRATOR: codex/bootstrap-orchestrator-v0 | Branch history reported integrated; untracked .engineering, forge/bootstrap_orchestrator/__init__.py, core.py and tests/test_bootstrap_orchestrator_core.py | PARKED_UNREVIEWED_SOURCE. Retain all bytes. Review whether it preserves Forge planning vs EP execution and dynamic Mission semantics before considering delivery. File names do not establish approved scope, quality or usefulness. |
| F-RELEASE61: codex/forge-release-evidence-v1 | Clean; PR #61 closed without merge; unique commit identities | RETAIN_PENDING_SEMANTIC_RECONCILIATION. Compare the actual local tip and diff to later release implementation/tests. Supersession is suspected, not proven by PR closure or squash history. |
| F-CLEANUP | Nine reported clean worktrees below | CONDITIONAL_CLEANUP_CANDIDATES only; inspect exact local tips and all retained files plus PR-head/post-merge commits and active ownership before any separately authorized removal. |
| F-LOCAL | Exact paths, full local tip IDs, file-level residual classification, stash/ignored inventory and active run/lease evidence | OPEN_EVIDENCE_GAP. Aggregate reports are useful but not per-target deletion evidence. |
| F-LOCAL-MAIN | Main behind; no worktree currently on it | FAST_FORWARD_CANDIDATE after fresh checks; preserve dirty worktrees. Not executed here. |

The nine F-CLEANUP branches, retained by exact name:

- codex/forge-cleanup-pending-first-failure-v1
- codex/forge-cleanup-pending-resume-v1
- codex/forge-engineering-platform-repository-declaration
- codex/forge-ep-release-flow-parity-v1
- codex/forge-ep-release-parity-v2
- codex/forge-main-first-release-v1
- codex/forge-release-completion-evidence-v1
- codex/forge-release-evidence-projection-v1
- codex/forge-release-prepublication-operation-v1

[Forge #61](https://github.com/pcvantol/forge/pull/61) is SOURCE_VERIFIED closed,
merged=false, historical head `3bf66d2cebc94702d45a03e0a9173b6769d896d9`.
That is not proof of the current local tip. The release-2.3.1 ref at
`5ae52d084c1ff24d56a76adcd2732242cc16e799` is retained as release history;
ancestry containment is not authorization to delete a release ref.

## Cross-product assessment and retained open points

EP #175 stays DRAFT/PARKED/NOT_QUALIFIED. Its early parking publication cannot
prove first-create-after-assurance; later reviews/readback cannot rewrite that
event. Keep its head untouched. Do not close/recreate it or invent legacy run
lineage. The future qualification strategy, exact review authority, runtime
route and level-B merge decision remain explicit EP-owned open decisions.

Workspace: USER_REPORTED eight clean feature worktrees under /private/tmp,
associated with merged #18-#25; main nine commits behind. These are conditional
cleanup candidates, not proof of product feature completeness. Documentation
#26 belongs to this inventory task and must be reconciled separately.

Forge Platform: USER_REPORTED 54 local branches and 52 worktrees, all clean;
37 featurebranches associated with merged PRs, 16 without a direct PR link;
main 41 commits behind and no unique main commits. The unnamed 16 require
per-branch comparison. Do not delete all 51 auxiliary worktrees by inference.
The installer is already parked through #61; use that scope/DAG, not the older
universal-installer handoff. Source foundation does not prove installed product.

Owning records (verify their protected delivery before treating them canonical):
[EP](https://github.com/pcvantol/engineering-platform/blob/main/docs/development/CONSOLIDATION_PARKING_2026_09_10.md),
[Workspace](https://github.com/pcvantol/workspace/blob/main/docs/CONSOLIDATION_PARKING_2026_09_10.md),
[Forge Platform](https://github.com/pcvantol/forge-platform/blob/main/docs/roadmap/CONSOLIDATION_PARKING_2026_09_10.md).

## Parked Forge work families

| Node | Retained work | Later resumption evidence |
| --- | --- | --- |
| F-CONSUMER | Installed Forge identity/storage, explicit EP v1.2 compatibility, immutable exact-byte terminal evidence and full identity/provenance binding | Exact Forge artifact/runtime and actual compatible EP producer; mismatch yields WAITING_EXTERNAL_CAPABILITY with zero submissions. No silent v1.1 fallback. |
| F-E2E | Original single-Mission real A/restart/dynamic-B/completion proof | Current approved Mission and grants, qualified runtimes, exact receipts and durable restart evidence. Not a preconfigured A/B script. |
| F-LATER | Cross-repository Living Mission Graph/depends_on, outer Mission loop, Project Intelligence, Quality/Knowledge Learning, policy/progression, release management and Project Hygiene | Existing owning roadmap/DAG criteria remain; not deleted or automatically added as canary prerequisites. |

The documentary JSON contains only consolidation/evidence relationships and
these work-family references; it is not a full replacement implementation DAG.
Priority is not a hard dependency. In particular F-E2E does not depend on local
cleanup, FP clean-install-v1, Workspace UI or all SA-* optimization nodes.

## Physical consolidation protocol — deferred, not performed

A later host-local operation must capture current worktree paths/tips/locks,
stashes, tracked/untracked/ignored files and symlink metadata without traversing
runtime roots. Preserve unique content in an access-controlled recoverable
location, retain exact refs/provenance and verify the recovery material before
removal. A Git bundle alone does not retain uncommitted/untracked/ignored bytes.
Never publish secrets or bulk .engineering contents as a parking commit.

Clean status, a merged PR, branch age or semantic supersession is insufficient
alone. Check current tip versus merged PR head, later local commits, ownership,
active EP run/PR/lease, exact expected ref, retention and recovery. Apply only
an explicit per-target authorized cleanup; no force removal, global prune,
stash/reset or direct-main commit to manufacture a clean state.

The documentation is complete only as a record of the known remote snapshot,
owner-supplied local inventory and remaining gaps. Physical cleanup and bytewise
classification of unseen local files are NOT_COMPLETE. Finish this documentary
task and stop; later engineering starts only from a selected bounded item.
