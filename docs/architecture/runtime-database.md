# Forge Runtime Database

## Boundary

The Runtime Database is the SQLite storage implementation of one persistent
[Runtime Instance](runtime-bootstrap.md). Its default is Git-common metadata
at `.git/forge-runtime/runtime.db`, outside repository cleanup paths; a
configured Runtime Root or explicit relocation may locate it elsewhere. The
canonical location is resolved and claimed before opening and is not committed.
Repository Truth remains the architectural source of truth, and the Engineering
Platform Execution Host retains its own independent Execution Database.

Forge Runtime owns allocated Mission State, Decision Evidence references, Integration Evidence, Execution Receipts, and Planning State. New Generation 2 Mission Recommendations and unallocated Mission Candidates belong to the separate [Mission Recommendation Lifecycle](mission-recommendation-lifecycle.md) governance store. Legacy recommendation records remain readable only for historical compatibility. Runtime records only
execution receipt identity: Execution Host, run ID, Engineering Report ID,
correlation identity, timestamp, and outcome. It never copies Execution
Evidence, reports, telemetry, logs, or host credentials.

## Execution Context projection

Execution Context is the compact, read-only, operator-facing projection of an
active Mission Runtime. The projection chain is `Mission Runtime -> Living
Mission Graph -> Execution Context -> clients`. It is a Runtime Instance
record, not a prompt, an Engineering Platform report, or a source-derived
view. Every successful Runtime reconciliation appends one immutable,
versioned snapshot to `execution_context_snapshots`; the prior snapshots stay
available as historical runtime evidence.

The context carries mission identity/title/lifecycle, concise Business and
Engineering summaries, active Intent and Action (or their explicit empty
messages), deterministic Execution Phase, Planning Confidence, iteration,
completed/ready/blocked/discovered/discarded Intent projections, remaining
Actions, last receipt identity, last Runtime update, timestamp and version.
It never carries Runtime Prompt text or internals, decision reasoning, hidden
reasoning, Execution Host reports, telemetry, logs, or credentials.

The canonical API is read-only through `RuntimeEvidence.execution_context_api`.
Engineering Platform, Apple, Windows, CLI, API and future clients consume the
same snapshot; none mutates it. Deterministic phase mapping supports
Preparing, Planning, Engineering, Validation, Waiting For Receipt, Waiting For
Governance, Paused, Mission Complete and Execution Complete. Planning
Confidence describes only plan confidence and is never Mission completion.

## Schema and migration

`forge.runtime.RuntimeDatabase` opens storage only after Runtime Instance
resolution. It enables SQLite foreign keys, WAL, and full synchronous
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
Repository Truth ── architectural evidence ──> Runtime Instance ──> Runtime Database
Execution Host ── immutable receipt identities ──> Runtime Instance ──> Runtime Database
Runtime Instance ── Mission / Planning / Review / Recommendation / Decision state
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
already-resolved Runtime Instance Database and a read-only Engineering Platform
receipt resolver; the entry point never creates a database,
loads `missions/`, constructs a portfolio, initializes a dispatcher, or resumes a
Mission. It invokes only the supplied read-only receipt resolver. Integrity is
checked without recording a new status update, then the runtime projection is
produced exclusively from Runtime
Database tables.

The projection includes every canonical Mission's ID, terminal Mission State,
immutable Decision Evidence, Architecture Review, Mission Recommendation,
Execution Receipt identity, Execution Host, Execution Run ID, lifecycle
lineage, completion timestamp, and outcome. It also proves the terminal IDLE
Dispatcher and empty approved queue. Each stored receipt identity must also
resolve through the supplied Engineering Platform resolver. The resolver
returns only reference validity and never copies host reports, telemetry, or
other Execution Evidence into Forge. Qualification fails closed with exact
missing runtime evidence. A successful projection recommends the
required **Generation 1 Completion Record**; a failed projection recommends
nothing. The portfolio and lifecycle ordering are read from the persistent
Runtime Instance, never imported from dispatcher or repository mission
definitions during qualification.
