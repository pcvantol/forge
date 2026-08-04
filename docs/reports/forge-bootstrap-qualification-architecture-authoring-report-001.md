# Forge Bootstrap Qualification Architecture Authoring Report 001

## Decision

Forge Runtime Database is the canonical operational authority for Generation 1
Bootstrap qualification. Repository Truth remains the canonical architectural
authority. Engineering Platform remains the canonical Execution Host and
Execution Evidence authority. These ownership boundaries do not overlap.

## Authoring outcome

`.forge/runtime.db` now records immutable Mission lifecycle events, the
dispatcher portfolio and terminal state, Mission State, Architecture Reviews,
Mission Recommendations, Decision Evidence and execution-reference identities.
Qualification reads this database only. It cannot read mission definitions,
reconstruct runtime state, or return a cached JSON result.

Each bootstrap Mission requires a completed outcome, activation and completion
timestamps, exactly one successful correlated Execution Reference, an
Architecture Review, a Mission Recommendation and immutable Decision Evidence.
The stored dispatcher sequence must be FIFO and end `IDLE`.

Business Workspace and Architecture Workspace consume Forge projections. The
Execution Host retains receipts, reports, telemetry and evidence. Forge stores
only the immutable reference identity required to correlate that host evidence.
