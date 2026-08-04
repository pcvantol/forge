# Forge Runtime Database

## Boundary

`.forge/runtime.db` is Forge's canonical local SQLite runtime database. It is
not committed. Repository Truth remains the architectural source of truth, and
the Engineering Platform Execution Host retains its own independent Execution
Database.

Forge owns Mission State, Architecture Reviews, Mission Recommendations,
Decision Evidence, and planning runtime state. The database contains only
references to execution: Execution Host, run ID, correlation, timestamp, and
outcome. It never copies Execution Evidence, reports, telemetry, logs, or
host credentials.

## Schema and migration

`forge.runtime.RuntimeDatabase` creates and opens the database at the fixed
workspace location. It enables SQLite foreign keys, WAL, and full synchronous
commits. Schema version and migration version are recorded in both SQLite's
user version and `runtime_metadata`. Startup is fail-closed for an unsupported
future version, incomplete migration, malformed required metadata, failed
SQLite integrity check, or invalid foreign reference.

The initial extensible schema contains exactly the runtime foundations:
`mission_state`, `architecture_reviews`, `mission_recommendations`,
`decision_evidence`, `execution_references`, and `runtime_metadata`.

Architecture Reviews, Mission Recommendations, and Decision Evidence are
immutable. Mission State is the durable restart point and records lifecycle,
current Engineering Intent and Action, progress, resume point, execution
policy, and current status.

## Relationships

```text
Repository Truth ── architectural evidence ──> Forge Runtime Database
Execution Host ── execution references only ──> Forge Runtime Database
Forge Runtime Database ── Mission / Review / Recommendation / Decision state
```

Decision Evidence links the Mission, Architecture Review, alternatives,
reasoning, confidence, and execution references without taking ownership of
either Repository Truth or Execution Evidence.
