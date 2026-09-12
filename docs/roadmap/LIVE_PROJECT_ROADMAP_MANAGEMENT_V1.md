# Live project roadmap management — Forge delivery DAG

**Increment:** `LIVE_PROJECT_ROADMAP_MANAGEMENT_V1`. **Status:** PLANNED.
Documentation/DAG refinement only, NO_BUMP; no live Mission, grant or execution.

[Forge contract](../architecture/LIVE_PROJECT_ROADMAP_MANAGEMENT_V1.md) and
[documentary DAG](live-project-roadmap-management-v1.json) refine existing F5
projection work and join the existing governance/progression/runtime services.
F5 is not a scheduler; its parent refinement is navigation, not a backward edge.

## Owned work and exact dependencies

| Node | Delivery | Local dependencies |
| --- | --- | --- |
| PRM-F-CONTRACT | Versioned project/readiness/change contracts and identity mapping | none |
| PRM-F-PROJECTION | Consistent project roadmap snapshot and HTTP read projection | PRM-F-CONTRACT |
| PRM-F-ELIGIBILITY | Current condition-vector and approved-pending interpretation | PRM-F-CONTRACT |
| PRM-F-ACTIVATION | Existing-runtime guarded intake/activation and recovery | PRM-F-ELIGIBILITY |
| PRM-F-CHANGES | Source-backed iteration deltas and advisory expectation refresh | PRM-F-PROJECTION |
| PRM-F-Q | Installed service, restart and outer-loop qualification | PRM-F-ACTIVATION, PRM-F-CHANGES |

All nodes remain PLANNED with empty qualification evidence. External evidence
is a real producer subset, not permission to allocate peer implementation.

PRM-F-PROJECTION consumes F2/FH operation/HTTP subsets. PRM-F-ELIGIBILITY and
PRM-F-ACTIVATION consume the relevant existing intake, approval, progression,
claim and recovery services. PRM-F-CHANGES reuses the existing context/observer
and Expected Mission semantics. Inspect and qualify missing seams rather than
create a second policy engine, allocator or Mission queue.

The original F1-F11 states/dependencies remain unchanged. F5 navigation links
this decomposition; no child depends on full F5/F9, avoiding a cycle. Read-only
projection may ship before activation. A qualified headless activation slice
may ship before Workspace management; PRM-F-Q is integrated full-family proof,
not a prerequisite for every independent bounded implementation.

## Shared mandatory future acceptance

PMT IDs are shared with the companion repository; keep IDs and meanings aligned.
They extend the relevant service/inner/outer/UI layers, not a second simulator.

| ID | Requirement | Layer |
| --- | --- | --- |
| PMT-01 | Typed capability/Mission/Candidate/Expected/history groups, actual zero/one/multiple active work and no phantom Mission allocation | SERVICE_UI |
| PMT-02 | Frozen revision, distinct approvals, manual/automatic release, eligibility and active lifecycle remain orthogonal | SERVICE_UI |
| PMT-03 | M2 genuinely approved/released through real services before M1; current dependency evidence unlocks M2 once without owner relay | OUTER_LOOP |
| PMT-04 | Expected or partially/unapproved Candidate never auto-starts; new Candidate still follows explicit real approvals | OUTER_LOOP |
| PMT-05 | Predecessor COMPLETE without required artifact/review/deployment evidence does not unlock dependent work | SERVICE_INNER |
| PMT-06 | Expiry, revocation, hold or policy change between eligibility and claim denies activation at the actual boundary | SERVICE_OUTER |
| PMT-07 | Routine source change revalidates assumptions without blanket reapproval; material scope change cannot reuse stale approvals | SERVICE_OUTER |
| PMT-08 | Priority and hard/speculative edges remain distinct; conflicting/cyclic/unresolved edge edits rejected; stable eligible tie-break | SERVICE_UI |
| PMT-09 | Duplicate/out-of-order completion and event delivery produce one reconciliation/context application and correct delta | SERVICE_OUTER |
| PMT-10 | Concurrent starters and lost acknowledgement preserve one activation/intake identity; uncertain EP POST is not resubmitted | SERVICE_OUTER |
| PMT-11 | Fresh process reopens pending, claimed, admitted and reconciled boundaries with same instance, authority and consumption | SERVICE_OUTER |
| PMT-12 | Cursor resync, mixed revisions, pagination, offline and source outage remain visibly stale/partial; stale command rejected | SERVICE_UI |
| PMT-13 | EP completion, Forge reconciliation and required human acceptance are independently represented | SERVICE_UI |
| PMT-14 | Expected added/split/merged/retired changes retain reasons and provenance; no silent overwrite of human/frozen work | SERVICE_OUTER |
| PMT-15 | Wrong project/actor/instance, confused-deputy requests, malicious content and secret-bearing links are denied/redacted | SERVICE_UI |
| PMT-16 | Read-only report and docs/design-only scope survive projection, successor and release; no automatic implementation expansion | INNER_OUTER_UI |
| PMT-17 | Supported serial/concurrent limits preserved; unsupported multiplicity visible, no newly enabled parallel execution | SERVICE_UI |
| PMT-18 | Unknown estimates/usage/confidence remain unknown; no progress from changing Mission counts or invented deadline | SERVICE_UI |
| PMT-19 | Five locales, both themes, desktop/phone, keyboard/touch, stable detail links, selection and clipboard failures | UI |
| PMT-20 | Refresh/sort/open/reconnect issues zero planning, intake or EP mutation requests; closing Workspace does not stop Forge | SERVICE_UI |
| PMT-21 | Versioned hold/disarm/reorder/release commands show preview and actual readback; paused Forge does not cancel admitted EP work | SERVICE_UI |
| PMT-22 | Failed/ambiguous predecessor never grants new authority or fresh repair budget under a replacement Mission | SERVICE_OUTER |
| PMT-23 | Missing API/capability or peer outage has no CLI/import/SQL/Inbox/IPC fallback; read-only rollout labels unsupported controls | SERVICE_UI |
| PMT-24 | No remaining project gap yields bounded idle and no fabricated Expected/Candidate/Mission or extra provider call | OUTER_LOOP |

The later outer-loop cases add a second positive path: create pending M2's
Candidate, real separate approvals and bounded automatic release through public
services BEFORE predecessor completion. M1 unlocks evidence, not authority. This
is not the forbidden test-driver injection of an already-approved M2. Retain the
new-Candidate path and all existing FOE cases. Inner-loop read-only/docs/design
cases retain their explicit effects; completed design cannot authorize new code.

Full qualification uses installed artifacts/new processes, real owning services,
stateful EP HTTP mocks and controlled external provider/OS fixtures; no live
credentials or paid probes in deterministic CI. Once qualified server entrypoints
exist, test the same cases through HTTP and supported own-CLI variants. Missing,
skipped, setup-failed or unsupported required cases cannot be counted PASS.

Preserve current Python/HTTP/OpenAPI/Postman, security and coverage requirements;
production coverage must be above 80% and cannot replace scenario completion.
Workspace UI requires en/nl/de/fr/es, two themes, desktop/phone and accessible
Playwright cases. Tests of documentary JSON are not those runtime/browser tests.
Mock-CI success is distinct from real EP/provider and installed-service evidence.

## Ordering, authority and resume

This is future productization; the current live canary, its approved scope and
budget are unchanged. No universal-installer, full outer-loop or graphical editor
prerequisite is introduced for basic read-only delivery. Full preapproved-Mission
progression is qualified through the later outer-loop lane, after its inner-loop
foundation. Workspace is not required to remain open.

At pickup refresh both owners' relevant source/contracts, current runtime limits
and unresolved public seams. Keep implementation, qualification and activated
policy separate. Shared source pins are historical observations, not current
service status. Use normal protected source delivery; separately authorize live
activation/configuration. Never reset a failed lineage or move parked unrelated
work into this design's scope.
