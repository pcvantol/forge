# Project Hygiene and Repository Reconciliation

## Decision, maturity and owning boundaries

Increment: `PROJECT_HYGIENE_AND_REPOSITORY_RECONCILIATION_V1`.
Native target capability: `FORGE::PROJECT_HYGIENE_AND_REPOSITORY_RECONCILIATION_V1`.
This is a documentation/roadmap decision: `PENDING_PR` until each owning merge,
then canonical target architecture. It does not implement a scanner, API,
maintenance executor, table, schedule or UI, and activates no cleanup permission.

This capability extends [Project Intelligence](PROJECT_INTELLIGENCE_AND_DYNAMIC_PLANNING.md),
not the Mission execution engine. It uses [effective policy](POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES.md)
and [governed progression](GOVERNED_PROGRESSION_AND_DELIVERY_AUTHORITY.md).
The [scoped roadmap](../roadmap/PROJECT_HYGIENE_V1.md) and
[documentary DAG](../roadmap/project-hygiene-v1.json) do not replace the
executable bootstrap programme or alter live grants.

| Responsibility | Authority |
| --- | --- |
| Actual remote refs, PRs, reviews and protected-ref settings | The declared repository provider/project authority |
| Host checkout/worktree facts, leases, run provenance, mutation and cleanup receipts | EP and its qualified host/provider boundary |
| Project-wide observations, anomaly classification, semantic reconciliation, residual routing and proposals | Forge |
| Human chat, Repository Health, evidence presentation and governed decisions | Workspace; actual decision authority remains with the declared owner |
| Installed artifact composition, update/uninstall/rollback and installation state | Forge Platform and product-owned installation contracts |

Forge may consume authorized read-only provider facts through declared adapters;
local host inspection and all target-repository/ref/worktree mutation remain
EP-owned. Forge still writes its own cases and projections in Forge-owned central
runtime storage; that is not permission to mutate a target repository. Neither
Forge nor Workspace reads EP CENTRAL, walks another product's data-root or uses
an LLM shell as a substitute adapter. Project identity comes from the canonical
repository declaration, never a branch prefix or incidental checkout path.

## Three kinds of work; no Mission for every maintenance question

**Run finalization cleanup** is an EP lifecycle responsibility. For its own
proven-delivered resources, EP reconciles delivery and conditionally cleans only
its owned branch/worktree while retaining the valid coordination lease until
safe finalization. No Forge Mission, project-wide scan or semantic model is needed.
A cleanup warning must not overwrite proven delivery or fabricate a failed run.

**Project hygiene** is a bounded Forge application operation/case. Requests such
as “what remains on this old branch?” or “inspect stale branches” resolve to
read-only observation and, only where useful, a reconciliation case. The case is
not a Mission Candidate, Mission, Engineering Action or EP execution run. It
has its own correlation, policy, evidence and finite analysis budget in existing
Forge-owned storage. An existing Action/run can be a provenance reference, not a
mandatory parent or an identity manufactured for the case.

**Genuine residual product work** is not executed by the hygiene case. Forge
may propose a successor under a still-applicable approved Mission, or a Mission
Candidate/amendment/other already-governed engineering intake when no such scope
exists. A completed Mission is not silently reopened. New architecture, security
or write scope follows its real gate. No direct cherry-pick, hidden maintenance
Mission or generic “hygiene” shell route bypasses normal product qualification.
Accepted salvage is a new bounded change against current main, never wholesale
replay of an old branch merely to make the ancestry graph look merged.

```text
EP run result / provider event / bounded schedule / Workspace request
  -> scoped observation -> Forge Project Context + provenance projection
  -> no anomaly: done
  -> ambiguous: RepositoryReconciliationCase
       -> retain / already delivered / accepted supersession
       -> genuine residual: governed engineering proposal
       -> permitted cleanup proposal: EP admission + current safety checks
  -> EP receipt/readback -> Forge case reconciliation -> Workspace projection
```

A cleanup request is a separate bounded EP maintenance command using existing
admission/provider/lease/evidence services, not a new execution mode or queue.
A Mission ID is optional provenance for this operation, not a required fiction.
Until that command seam is implemented and qualified, Forge can recommend or
retain, but cannot substitute an arbitrary Engineering Action or shell command.

## Observation schedule and completeness

After a terminal EA result (including failed/blocked results), delivery or
cleanup receipt, Forge requests a cheap **delta** refresh of the affected
repository and known branch/worktree identities. External Codex/developer PRs
and provider events are also inputs; they need not originate in Forge. Use
bounded periodic full inventory to recover missed events, plus on-demand and
release/canary preflight refreshes. Exact intervals are policy/configuration,
not hardcoded cron or a full model call after every Action.

Persist cursors, source event IDs and coalesced refresh jobs in the existing
Forge runtime. Duplicate/out-of-order events are deduplicated and reconciled
against provider revision/evidence, not local wall-clock ordering alone. An
unknown event gap, permission-limited page, offline Agent, shallow history or
rate-limited response makes the relevant snapshot `PARTIAL`/`STALE`/`UNAVAILABLE`.
It never means “zero branches” or “no active work”. A full rescan repairs a gap;
an event itself grants no mutation authority. Do not extend a run's lease or
hold its completion open merely to await project-wide analysis.

Every snapshot records project/repository/provider identity, observation ID,
source revisions/cursors, observed ref-to-object mapping, relevant main/base
revision, PR/delivery references, host/worktree coverage, freshness and limits.
Bound API calls, bytes/diff size, analysis time/tokens/cost, concurrent cases,
retention and retries. Pause/cancel and exhausted budgets retain evidence and
produce a resumable case or recommendation, not a new case to reset allowance.
Read-only observation uses least-privilege access; no untrusted repository hooks,
builds or tests execute as a side effect of scanning. Qualified tests, if needed
for reconciliation, run through EP under a separately authorized bounded request.

## Branch Provenance Ledger is a projection, not another Git authority

Use a logical ledger within existing Forge Project Context/storage. It indexes
facts and their sources; it does not replace Git, PR history, EP leases or
execution receipts. Rebuildable views and immutable analysis/decision records
are distinguished. No second database service is introduced.

A branch record binds repository ID, provider/remote identity, full ref, observed
object ID, ref-generation/provider event revision where available, base/main
snapshot, nullable creation provenance, known Action/run/increment/PR links,
delivery evidence, worktree observations, retention/legal hold, case references,
last observation and explicit coverage/freshness. Host paths are scoped operational
references, not portable domain identities. Names reused for another branch
instance invalidate previous proposals; unknown generation/provenance remains
unknown. A branch name, author string, ahead/behind count or age is not ownership.

Do not compress all meanings into one mutable “safe” flag. Keep separate axes:

- activity: active Action/PR/lease, no known activity, unknown coverage;
- delivery: merged/reconciled, superseded candidate, residual, conflicting evidence;
- case: open/investigating/waiting/concluded, with immutable conclusion revisions;
- cleanup: not requested, retained, proposal, eligible-at-observation, admitted,
  partial/completed/denied/stale, with EP receipt references.

`SAFE_DELETE` may be shown only as a qualified shorthand for a scoped policy
eligibility observation. It is not an enduring permission or a delete receipt.
A `SUPERSEDED_RECONCILED` case can legitimately end with `RETAINED` cleanup.
Remote branch deletion says nothing about a local branch or worktree deletion.

## Reconciliation and strength of evidence

Start deterministically: exact delivery receipt/head, PR merge facts, ancestry,
changed-path and tree comparisons, then patch equivalence as a diagnostic aid.
Git reachability and content/intent equivalence are different questions. Squash
or cherry-pick can preserve work without preserving the original commit IDs;
even a merged PR does not cover commits later appended to its head branch.

Escalate to bounded semantic analysis only for unresolved cases. Bind it to the
exact source head, comparison main, commit range, relevant contracts and test
identities/results, analyzer/model/tool revision and analysis policy. Repository
content, commit messages and PR comments are untrusted evidence, not instructions
or grants. Preserve FACT / INFERENCE / RECOMMENDATION / DECISION distinctions.
Do not export proprietary source to an unapproved model/provider.

For each commit intent or independently meaningful residual, record:
`PRESENT_ON_MAIN`, `SUPERSEDED_BY_STRONGER_MAIN_IMPLEMENTATION`,
`GENUINE_RESIDUAL` or `UNRESOLVED`, with exact code/test/evidence references,
uncertainty, contradictory evidence and reviewer/decision provenance where
required. “Stronger” requires a compatibility/behavior explanation; a newer
version number, similarly named test, green unrelated suite or model confidence
is not proof. Testing observed behavior does not prove universal equivalence.

All mapped intents can support a proposed no-residual conclusion. Semantic
analysis alone never authorizes destructive cleanup. For semantically superseded
history, the target requires an accepted bounded disposition under the effective
policy and a verified retained recovery object/bundle before destructive cleanup.
No automatic semantic-delete path is enabled by this document. An unresolved or
residual case remains retained and may become governed product work.

## Safe cleanup is a separate operation

EP owns the actual decision at the side-effect boundary. Its
[owning contract](https://github.com/pcvantol/engineering-platform/blob/main/docs/engineering/REPOSITORY_HYGIENE_AND_SAFE_CLEANUP.md)
requires all applicable gates together: authenticated scoped actor/delegation,
permitted operation, current expected ref/worktree state, verified ownership or
explicit approved adoption, no conflicting active owner/PR/run/lease, protected-ref
policy, retention checks, current repository facts and retained recovery evidence
where required. Analysis authority, scan permission and provider push access are
not delete authority. The finalizer's own valid coordination lease is not a
conflicting owner; retain it during cleanup of its proven-delivered resources.
A separate maintenance command cannot borrow another run's finalizer authority.

Separate local ref deletion, remote ref deletion and owned worktree removal.
A request freezes the exact set and expected object IDs plus proposal/evidence/
policy revisions. No recursive path, wildcard branch, age-only or prefix-only
cleanup. Main/default/release/protected refs, tags, unknown ownership, active
work, dirty/untracked/ignored user files and runtime directories are retained.
Git-clean does not mean a worktree contains no valuable ignored data.

Immediately recheck state under EP's resource exclusion and use a provider's
atomic expected-ref mutation where available. An EP lease does not lock out
external Git users. If the provider cannot enforce the needed conditional
mutation, unattended cleanup is unsupported: retain or use a separately
qualified controlled operation, not check-then-blind-delete.

No distributed transaction is claimed for remote ref, local ref and worktree.
Persist operation intent before effects and individual outcome receipts after
each stage; timeout/lost acknowledgement reconciles the same operation. Partial
cleanup is visible. Never recreate a branch as “rollback” if doing so would
clobber somebody else's new ref. “Already absent” is an observation, not invented
proof that this operation deleted it. Recovery bundles/archives must be protected,
verifiable and governed by retention; creating an archive is not permission to
publish source or create release-triggering refs.

## Policy and Workspace interaction

Reuse the product-owned policy definition/assignment/effective-evaluation
contracts and their qualified services as available; this design does not claim
that the full policy management implementation already exists. A project profile
controls observation triggers, analysis escalation/budgets, protected/retained
refs, evidence freshness, adoption and retention rules, and which bounded cleanup
classes may use existing delegation. Mandatory controls combine; allowed scopes
intersect; budgets use remaining ceilings. A Mission assignment can narrow
relevant scope, not grant deletion of unrelated branches. Risk/semantic ambiguity
may require a gate; deterministic own-run cleanup within an existing grant must
not demand a new human click every time.

Workspace chat and Repository Health share the same typed request/decision
boundary. “Explain this branch” is read-only. “Reconcile it” permits analysis,
not deletion. “Clean everything safe” resolves an explicit project-scoped set
and policy proposal; new branches are not added after confirmation. The owner
service binds any decision to that set, its revisions, actual actor and expiry.
A chat transcript, LLM response or UI selection is not approval by itself.

The [Workspace design](https://github.com/pcvantol/workspace/blob/main/docs/REPOSITORY_HEALTH_AND_RECONCILIATION.md)
shows evidence, exclusions, uncertainty, external gate owners and per-target
outcomes. It cannot hold provider-admin credentials, invent Missions or use a
local client filesystem as authoritative evidence for unseen hosts. Routine
delegated work may run without UI; unsupported operations remain read-only.

## Release, canary and installation boundaries

A release/canary hygiene assessment binds the selected repository, exact source,
artifact operation and execution scope. Relevant conflicting owners, unexplained
changes to that candidate or missing required evidence can block that operation.
An unrelated retained branch or an unavailable optional scan does not create a
global release ban. Coverage must be explicit: one closed case does not prove
`UNEXPLAINED_REPOSITORY_BRANCHES = 0` for the whole project.

The full scanner, semantic reconciliation and Workspace surface are **not new
prerequisites** to the first serial autonomy canary. A small read-only hygiene
slice may be selected as canary product work without implying the whole family
is implemented. Existing minimum EP preflight/lease/cleanup safety still applies.

Forge Platform consumes an applicable assessment as source/operation evidence;
artifact digests, supply-chain qualification, publication, install readiness and
external CD approvals remain separate gates. Installing, upgrading or uninstalling
a product must not prune project refs, erase Forge cases/EP receipts or reset
budgets. See its [owning boundary](https://github.com/pcvantol/forge-platform/blob/main/docs/architecture/REPOSITORY_HYGIENE_RELEASE_BOUNDARY.md).

## Reference case and qualification targets

The user-supplied `codex/ep-producer-completion` case is a historical example:
head `c68ab079825aa58370b341f3b5087c147b7633ff`, compared with EP main
`f7c08872a2d334cff097ea5f28822836e59f78c3`, six ancestry-unique commits, zero
reported residuals, local/remote branch removed and `.engineering` retained.
Its manual reconciliation is not native scanner/executor qualification, not a
current inventory, and not new permission to delete anything.

Required future tests include: exact merge versus squash-equivalent history;
post-merge appended commits; partial residual; renamed/reused refs; offline or
permission-incomplete inventory; duplicate/out-of-order events; provider throttling;
active PR/run/lease; dirty and ignored files; protected/release refs; malicious
repository instructions; stale proposal/actor/grant; concurrent external push;
unsupported atomic delete; archive failure; lost acknowledgement/partial cleanup;
restart without duplicate command; no Mission for inspection; residual requiring
real governance; valid own-finalizer lease versus conflicting owner; no evidence
downgrade of successful delivery; and scope-correct release preflight. Shared
versioned fixtures must qualify both producer facts and consumer meaning before
activation. New protocol routes/tables are future owning implementation work,
not invented here.

## Source baseline for this documentation decision

Original source reading on 2026-09-08: Forge
`d88180d2ad934cfd8ff2cc7209cf49de8c2baa88`, EP
`d1ac70e76d00fd9cb838ca12625830967402e45f`, Workspace
`4277d5c179972f22da5c6304aa068752ea8ed19d`, Forge Platform
`863d543d470c653d4360c206692c432d514160a9`. These are historical document/source
pins, not installed-product or current-host observations. Final reviewed heads,
base compatibility and merge evidence are recorded in the coordinated PR closure.
