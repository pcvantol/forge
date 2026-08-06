# Runtime Evidence

Forge Runtime Database is the canonical operational authority for Mission
State, Architecture Reviews, Mission Recommendations, Decision Evidence,
Execution Receipts, and Planning State. `RuntimeEvidence` is the only query
and projection boundary for runtime qualification, governance reports, and the
Business and Architecture Workspace runtime views.

The evidence chain is `Mission → Mission State → Decision Evidence → Execution
Receipt → Execution Host Evidence → Execution Report`. Forge retains the
immutable execution receipt only: host identity, run identifier, Engineering
Report ID, timestamp, outcome, and correlation identity. Engineering Platform retains all Execution Host
Evidence, reports, and telemetry. Repository Truth retains architecture.

`RuntimeEvidence.decision_evidence_reference()` exposes the narrow connection
between the resolved Runtime Instance and one immutable Decision Evidence
record. The reference contains only runtime identity, repository identity, a
stable runtime locator, Decision Evidence identity and a SHA-256 digest of the
canonical stored record. It is not a second Decision Evidence store and cannot
contain host evidence, prompts, or decision reasoning.

`RuntimeEvidence.mission_runtime_projection()` is the canonical persisted
operational view for an active Mission. It reconciles the already-persisted
Mission State, Planning State, Dispatcher State, Decision Evidence references
and Execution Receipt references before it selects exactly one dependency-ready
Engineering Action and its one ready Runtime Prompt. The projection persists
Mission lifecycle and progress; current, completed, ready, blocked, discovered
and discarded Intents; completed and remaining Actions; planning confidence;
Decision Evidence and receipt references; Dispatcher State; and Approved Mission
Queue. It fails closed when those records cannot prove one executable Action;
it never plans, creates or completes work. A completed Mission instead proves
every Action complete with an IDLE Dispatcher and empty Approved Mission Queue,
then projects no next Action or Runtime Prompt.

Mission Qualification reads Runtime Database projections; it does not inspect
repository implementation files or rebuild execution history. Generation 1
completion instead verifies that the operational Runtime Instance is
intentionally empty after historical bootstrap. Architecture Review, Mission
Recommendation, and Decision Evidence reports use the same projections. This
preserves explicit ownership: Forge owns future runtime state, the Execution
Host owns execution evidence, and the repository owns historical architecture.
