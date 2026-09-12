# Live project roadmap management V1 — Forge contract

**Increment:** `LIVE_PROJECT_ROADMAP_MANAGEMENT_V1`.
**Status:** PLANNED implementation; this is the owner-requested design iteration.
**Owner:** Forge for project semantics, projection and existing runtime services;
Workspace for the human interface. **Version decision:** NO_BUMP.

This refines F5 Roadmap/Forecast, not a new planner or execution queue. The
[scoped roadmap](../roadmap/LIVE_PROJECT_ROADMAP_MANAGEMENT_V1.md) and
[documentary DAG](../roadmap/live-project-roadmap-management-v1.json) join F5
projections to existing governance/progression and activation services.
The companion is `pcvantol/workspace:docs/LIVE_PROJECT_ROADMAP_MANAGEMENT_V1.md`.
All runtime nodes remain PLANNED; no live permission or Mission is created.

## Basis and terminology

Source observations: Forge `77374203ada9260a9152a8cbb1be841fd070d871` and
Workspace `664a3eb87b7b6523d0473dc8b696e94064908940`, reviewed 2026-09-12.
The existing [productization contract](FORGE_PRODUCTIZATION_RECONCILIATION.md),
[decision contract](FORGE_V1_PRODUCTIZATION_DECISION_CONTRACT.md),
[Living Mission Graph](LIVING_MISSION_GRAPH_AND_CROSS_REPOSITORY_ACTION_DAG.md)
and [progression contract](GOVERNED_PROGRESSION_AND_DELIVERY_AUTHORITY.md)
already distinguish product direction, recommendations, approvals and execution.
They are the foundation, not proof of a qualified pending-Mission release path.

The roadmap is broader than a Mission list: governed capabilities/milestones
can exist before any implementing Mission is known. Links from capabilities to
Missions/Candidates/Expected Missions are many-to-many with explicit contribution
and evidence. Do not create placeholder executable Missions just to draw a graph.
Distinguish the approved source direction from its derived live projection.
A textual repository roadmap supplies versioned evidence, not runtime authority.

Keep three layers distinct: project capability/Mission dependencies; the active
Mission's Living Mission Graph of Actions; EP admission, queue and execution.
No new scheduler in the F5 projector or Workspace. All labels/record names below
are target contract vocabulary to map to owning versioned schemas, not shipped
lifecycle enums or new database tables.

## One snapshot, five views of work

A project snapshot supports ACTIVE, APPROVED_PENDING, CANDIDATES, EXPECTED and
HISTORY views. These are presentation groups, not replacement lifecycle states.
ACTIVE includes authoritative active/waiting/recoverable Missions; HISTORY
retains finalized successes, failures, cancellations and superseded work distinctly.
A recoverable failure is not hidden merely because its process exited.
Attention-needed is a cross-cutting facet, not an exclusive sixth lifecycle.

Project a singular current Mission when exactly one is active, explicit idle
when none is active, and all actual active Missions when more than one is
supported and observed. This design does not enable concurrent Missions or
relax existing serial limits. An unsupported multiplicity is a visible conflict,
not permission to choose one and hide the others.

A snapshot carries project and producer-instance identities, roadmap/context/
policy revisions, source digests, as-of time, cursor/snapshot ID and per-source
freshness. Items retain stable typed IDs, lifecycle and projection group,
contribution links, immutable approved revision where applicable, actual evidence,
approval and release facts, and capability-dependent permitted operations.
Events/cursors are scoped to the same authorized snapshot. Reset a stale cursor
with an explicit snapshot resync; never combine pages from different revisions
into a purported single authoritative view. Missing/partial evidence is visible.

## Frozen, approved, released, eligible and active are separate

A frozen Mission fixes a revision of goal, scope, effects, constraints, success
criteria and dependency requirements. It does NOT freeze a prewritten Action
script. Retain immutable prior revisions and approval subjects. Candidate
maturity and Business/Architecture decisions are separate: one partial approval
is not approval for engineering, and refining a Candidate is not a Mission start.

For approved pending work preserve these orthogonal dimensions:

| Dimension | Meaning |
| --- | --- |
| Approved subject | Exact revision and separate applicable Business/Architecture decisions |
| Release policy | Explicit MANUAL_RELEASE or AUTO_WHEN_ELIGIBLE with valid owning execution authority |
| Dependency satisfaction | Required predecessor identity and evidence, not just a green status |
| Current validity | Scope/assumptions/policy/identity and relevant review requirements remain valid |
| Runtime disposition | Pending, held, blocked, eligible, activating or actual lifecycle state |
| Execution availability | EP-observed admission/resources/capacity, separate from logical readiness |

Support already approved definitions awaiting canonical intake and admitted
Missions awaiting activation without inventing a second allocator. Before intake
use the owning approved-subject ID; after intake link the real Mission ID. Never
allocate early merely to populate a card or lose lineage between those views.
An item must not appear twice as two independent executable units.

AUTO_WHEN_ELIGIBLE authorizes no new approval. It is an explicit bounded release
choice applied through existing governance/authority services, not an assumed
result of approval, a default taken from a display setting or a grant in this doc.
Once all currently applicable gates hold, the existing runtime may intake/start
that already-approved work without another owner message or an open Workspace.
Selecting MANUAL_RELEASE does not demand repeated Business/Architecture approval;
it adds only the specifically required release decision.

## Current eligibility and safe automatic activation

The existing runtime evaluates a structured condition vector, not one UI boolean:
exact approved subject; current release authority and remaining limits; valid
required dependency evidence; compatible current assumptions and read/write scope;
no applicable hold/review/emergency fence; qualified provider/peer/readiness;
and existing Mission-capacity policy. UNKNOWN is not satisfied. Expose all
blocking reasons and their owner, source, freshness and permitted next action.
EP still owns Action admission, leases and capacity. No reservation guessed from
an old EP observation guarantees an Action can run; distinguish logical eligibility
from waiting for EP capacity. An EP capacity wait is not a failed Mission.

Persist the eligibility decision with input revisions and expiry, then recheck
volatile grants/fences/dependency validity at the atomic activation boundary.
Use existing locks/CAS/operation identities and admission/claim journals. Two
starters, duplicate events or UI/CLI retries must activate/intake the same subject
at most once. After a crash, reconcile the same operation before retry; an
uncertain EP POST follows the existing ambiguity contract, never another submit.
No read-side projector performs admission as a side effect of being queried.

Routine predecessor code changes do not automatically invalidate a frozen Mission
or demand blanket reapproval. Revalidate its declared requirements, applicability
and assumptions. Material goal/scope/effects changes or invalidated approval
conditions require an owning amendment and relevant reapproval, with reasons.
New source evidence cannot rewrite the approved revision or broaden its rights.
Expiry while waiting blocks release; it does not refresh itself. A model switching
roles, a successor Mission or a reopened process cannot reset consumed allowances.
An unrelated failed Mission blocks only actual dependency/fence/resource scopes.

## Dependency and priority management

Hard edges bind typed producer/subject revisions and evidence requirements.
Qualified source, published artifact, human acceptance and deployment proof are
different unlocks. An Action marked COMPLETE does not automatically satisfy an
artifact or a Mission-end acceptance requirement. Missing, tampered, revoked or
incompatible evidence leaves the dependent work blocked with a precise reason.
Validate cycles and unresolved references in the scoped project graph; qualify
external project/repository references, not arbitrary URLs or cross-project leaks.

Priority and recommended sequence rank currently eligible work under an explicit
policy; they do not override edges, capacity, fairness constraints or fences.
Use deterministic tie-breaking and preserve the selected ordering rationale.
Reordering, adding/removing an edge, hold/disarm or changing release policy is a
versioned intent: actor/scope, expected revision, idempotency key, redacted impact,
required decision and authoritative readback. A readback, not optimistic UI order,
confirms the change. An illegal reorder yields a proposal/conflict, never an
implicit edge deletion. Do not automatically remove external approval gates.

A hold prevents future activation/dispatch within its declared scope. It does not
undo accepted EP work. Cancelling existing execution remains a separately
supported owning operation. Preserve evidence of approved/disarmed/superseded
pending work rather than deleting it from history.

## Expected work, completion and change explanations

Only relevant verified evidence or explicit authorized reasoning requests refresh
Project Context and expectations; coalesce duplicate invalidations with bounded
work. Reading, polling, reconnecting and sorting the view cause ZERO generations.
Relevant Action results can refresh in-Mission planning; material Mission results
refresh broader expectations. Failed/ambiguous results may inform an explicitly
labelled risk assessment but are never treated as successful predecessor evidence.

Expected work is advisory: may appear, split, merge, change confidence or retire.
Maintain stable identity where justified and explicit supersession links otherwise;
record origin, old/new context, reason and uncertainty. Do not manufacture numeric
confidence. Candidate refinement remains versioned; automatic reasoning does not
silently overwrite human-edited/approved content. Approved pending or active
Missions are not auto-deleted when an expectation vanishes: expose applicability
review and use the owning governance path for amendment/retirement.

Persist a redacted, source-backed delta since a chosen snapshot or Mission
iteration: proven results, newly unlocked pending work, new/retired expectations,
changed dependencies, stale approvals and decisions now needed. Clearly distinguish
FACT, INFERENCE, FORECAST, RECOMMENDATION and DECISION. Summaries link to originals;
logs and model prose are not completion/approval evidence.

EP terminal success may precede Forge reconciliation or required human acceptance.
Display those separate facts. A completed capability needs its actual contribution
and acceptance evidence, not merely a count of finished Missions. Without credible
estimates show a blocking dependency chain, not a dated critical-path promise.
Forecast ranges/assumptions are separate from execution authority. No percentage
from a changing Mission denominator, and no dummy next Mission when no work remains.
Read-only/docs/design outcomes retain their effect and artifact semantics; a report
or approved design is not permission to implement the recommendation.

## Interfaces, rollout and evidence

Workspace Client -> Workspace Server -> Forge/EP and Forge -> EP remain authenticated,
versioned HTTP-only, even on one host. No peer CLI/import/SQL/Inbox/IPC fallback.
Workspace reads Forge-owned readiness/roadmap and EP-owned execution through the
correct owner. Forge is not a generic EP proxy. Own CLI is a thin adapter to the
same application rules; bootstrap/recovery exceptions never become peer shortcuts.
F2 supplies per-capability operation/error/event schemas and OpenAPI/Postman parity.
No invented route, mutable shared database or second Workspace roadmap authority.

Read-only project projection can ship before activation/edit controls. Qualify
activation headlessly through the existing runtime without requiring full UI,
chat or forecast completion. Server, grants and API readiness are exact subset
evidence, not demand to finish all Console/installer/policy productization first.
This refines the existing F5/GP/runtime boundaries, not current live-canary gates.

The shared PMT scenario registry in the documentary DAG is mandatory future proof.
Reuse the installed inner-loop harness and stateful EP HTTP simulator. For the
later outer-loop line, test BOTH new-Candidate-then-approval and previously approved
pending M2: create its real Candidate/decisions/release through public services
before M1 completion, never inject an already-approved database row. Completion
of M1 is evidence unlocking existing permission, not permission for M2. Retain
current FIE/FOE cases and qualified HTTP/CLI variants; no test-side orchestrator.
Workspace contributes API/browser/locale/security acceptance. Missing required
coverage or unavailable public seams are gaps, not a green expected failure.

No runtime implementation, active policy, pending queue, CI workflow, credential,
version allocation, Mission or peer state changes in this documentation increment.
