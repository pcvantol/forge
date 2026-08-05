# Forge Runtime Database

## Boundary

`.forge/runtime.db` is Forge's repository-default local SQLite runtime database.
The canonical location is resolved before opening through [Runtime Bootstrap,
Location Resolution and Evidence Recovery](runtime-bootstrap.md); it may be a
configured or explicitly relocated local location. It is not committed.
Repository Truth remains the architectural source of truth, and the Engineering
Platform Execution Host retains its own independent Execution Database.

Forge owns Mission State, Architecture Reviews, Mission Recommendations,
Decision Evidence, Integration Evidence, Execution Receipts, and Planning State. It records only
execution receipt identity: Execution Host, run ID, Engineering Report ID,
correlation identity, timestamp, and outcome. It never copies Execution
Evidence, reports, telemetry, logs, or host credentials.

## Schema and migration

`forge.runtime.RuntimeDatabase` creates and opens the database at the fixed
workspace location. It enables SQLite foreign keys, WAL, and full synchronous
commits. Schema version and migration version are recorded in both SQLite's
user version and `runtime_metadata`. Startup is fail-closed for an unsupported
future version, incomplete migration, malformed required metadata, failed
SQLite integrity check, or invalid foreign reference.

The initial extensible schema contains exactly the runtime foundations:
`mission_state`, `architecture_reviews`, `mission_recommendations`,
`decision_evidence`, `integration_evidence`, `execution_receipts`, `planning_state`, and
`runtime_metadata`. The version 4 migration replaces legacy execution
references with immutable Execution Receipts and preserves their identifiers.

Architecture Reviews, Mission Recommendations, Decision Evidence, and
Execution Receipts are immutable. Mission State is the durable restart point and records lifecycle,
current Engineering Intent and Action, progress, resume point, execution
policy, and current status.

## Relationships

```text
Repository Truth ── architectural evidence ──> Forge Runtime Database
Execution Host ── immutable execution receipts only ──> Forge Runtime Database
Forge Runtime Database ── Mission / Planning / Review / Recommendation / Decision state
```

Decision Evidence links the Mission, Architecture Review, alternatives,
reasoning, confidence, and execution receipts without taking ownership of
either Repository Truth or Execution Evidence.

Planning State is a singleton mutable planner snapshot with planner version,
current queue, pending and blocked Engineering Actions, execution policy, and
planner runtime metadata. It is not dispatcher state. Bootstrap Qualification
consumes this database boundary, while the Business Workspace, Architecture
Workspace, Mission Planner, and Repository Truth retain their existing
separate responsibilities.

## Generation 1 qualification

`forge.qualification.qualify_generation_one_bootstrap` is the read-only
Generation 1 qualification entry point. Its caller supplies an existing,
already-resolved Runtime Database; the entry point never creates a database,
loads `missions/`, constructs a portfolio, initializes a dispatcher, resumes a
Mission, or contacts an Execution Host. Integrity is checked without recording
a new status update, then the result is projected exclusively from Runtime
Database tables.

The projection includes every canonical Mission's ID, terminal Mission State,
immutable Decision Evidence, Architecture Review, Mission Recommendation,
Execution Receipt identity, Execution Host, Execution Run ID, lifecycle
lineage, completion timestamp, and outcome. It also proves the terminal IDLE
Dispatcher and empty approved queue. Qualification fails closed with exact
missing Runtime Database evidence. A successful projection recommends
**Portfolio Intelligence Foundation**; a failed projection recommends nothing.
