# Mission Recommendation Lifecycle

## Canonical lifecycle

Forge Generation 2 makes the following lifecycle canonical:

```text
Repository Analysis → Portfolio Intelligence → Mission Recommendation
→ Business Workspace → Business Decision → Architecture Workspace
→ Architecture Decision → Mission Candidate → Mission Allocation
→ Mission Runtime → Mission Completion → Historical Recommendation
```

Portfolio Intelligence creates immutable, advisory Mission Recommendations.
Business alone records Business approval or rejection; Architecture alone
records architectural approval or rejection. A recommendation has no execution
authority. Forge allocates a Mission ID only after both approvals are recorded
as immutable Decision Evidence.

## Governance aggregate

`forge.lifecycle.RecommendationLifecycleStore` is the canonical local store for
recommendations, unallocated candidates, lifecycle transitions, allocations,
and their Decision Evidence. It is separate from Runtime. The closed
recommendation status set is `PROPOSED`, `RECOMMENDED`, `BUSINESS_REJECTED`,
`BUSINESS_APPROVED`, `ARCHITECTURE_REJECTED`, `ARCHITECTURE_APPROVED`,
`MISSION_ALLOCATED`, `SUPERSEDED`, and `ARCHIVED`.

Recommendations are immutable. The current status is derived only from its
append-only transition log. Every creation and transition writes immutable
Decision Evidence with actor, time, rationale, and resolved references.
Candidate content is mutable only while unallocated. Allocation freezes the
candidate and creates an immutable record connecting the recommendation,
candidate, both approval records, Mission ID, and allocation evidence.

The allocation service accepts a Forge-owned Mission-ID allocator and validates
the resulting `MISSION-<number>` identity. Engineering Platform has no role in
allocation. Mission completion appends Decision Evidence against the allocated
identity; it never turns an advisory recommendation into Runtime state.

## Runtime and historical learning

Runtime stores only allocated Mission operational state, progress, Engineering
Intents, Engineering Actions, Execution Receipts, and references to immutable
Decision Evidence. It does not store advisory recommendations or unallocated
candidates. The legacy Runtime recommendation tables remain historical
compatibility records and are not a Generation 2 lifecycle write path.

Rejected, superseded, allocated/implemented, and archived recommendations
remain queryable in the governance aggregate. Portfolio Intelligence may use
that history as evidence for later advisory recommendations, but it may not
infer approval or allocation from it.

## Determinism and boundaries

The transition map is closed and rejects skipped approval paths. Evidence IDs
derive from canonical decision input, and SQLite append-only triggers prevent
rewriting recommendations, evidence, transitions, or allocations. This is a
governance store, not a Business UI, Architecture UI, planner, Runtime,
Execution Host, or repository-operation system.
