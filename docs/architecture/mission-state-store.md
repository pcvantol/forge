# Mission State Store 2.2

## Purpose

The Mission State Store is Forge's canonical durable record of Mission
execution. It owns operational state; it does not plan a Mission, execute an
Action, retrieve host evidence, or infer completion from a report. It is
repository-independent and has no dependency on Engineering Platform.

The immutable `EngineeringMission` contract remains the governed statement of
Mission meaning. Its historical `MissionStatus` is not reused as execution
state. The separately versioned runtime lifecycle below records operational
progress without changing Mission governance.

## Stored snapshot

Each atomic state revision persists:

- the immutable Mission snapshot;
- pinned Engineering Intent and Engineering Action snapshots;
- current runtime status and derived Action progress;
- execution request/dispatch correlation (including host run identity);
- terminal Execution Host evidence references;
- a scheduler resume cursor; and
- an append-only transition history.

Snapshots retain value data and references only. The Store does not retain an
Execution Host object, Scheduler object, process memory, reports, logs, or
repository credentials.

## Execution lifecycle

```text
CREATED → READY → ACTIVE → WAITING_FOR_EXECUTION → WAITING_FOR_EVIDENCE
                                      │                    │
                                      └── BLOCKED ──→ READY ┘
                                      └── FAILED  ──→ READY

WAITING_FOR_EVIDENCE → ACTIVE | COMPLETED → ARCHIVED
```

`BLOCKED` and `FAILED` have explicit recovery transitions only; they never
silently retry. `COMPLETED` requires persisted terminal execution evidence and
all persisted Actions complete. `ARCHIVED` is terminal. Every creation and
transition appends one immutable, sequential history entry in the same
transaction as the new snapshot. The storage schema rejects history updates
and deletion as well as the public API exposing no history mutator.

## Persistence and recovery

The initial implementation uses a local SQLite database. SQLite transactions,
foreign keys, full synchronous commits, and write-ahead logging make the
snapshot and history commit together and permit reopening after process or host
restart. The database location is supplied by the caller; no workspace,
repository, network, or Engineering Platform location is assumed.

On restart, the canonical sequence is:

```text
Mission State Store
  ↓ load persisted non-terminal Mission state
Mission Scheduler
  ↓ select the persisted current Engineering Action and resume cursor
Current Engineering Action
  ↓ continue through the Execution Host Contract
```

No Mission is reconstructed from reports. Reports and host evidence remain
authoritative for evidence, but they become eligible to change Mission progress
only after their exact correlation is persisted by a caller using the State
Store. A future Mission Runner coordinates these existing boundaries; it must
not become an alternate state authority.

## Architecture relationship

```text
Mission
  ↓
Mission Scheduler
  ↓ plans and persists operational decisions
Mission State Store
  ↓ provides the correlated released Action
Execution Host Contract
  ↓
Execution Host
  ↓ returns execution evidence
Execution Evidence
  ↓ persisted atomically
Mission State Store
  ↓ informs subsequent scheduling
Mission Scheduler
```

The Mission Planner creates and reconciles Engineering Intents within a
Mission's boundaries. The Scheduler plans releases of Engineering Actions. The
State Store records their resulting execution state. The Execution Host owns
delivery, execution, retries, and evidence collection. These responsibilities
remain separate.

## API boundary

`forge.state.MissionStateStore` is local and deterministic. `create` stores a
new Mission snapshot, `transition` performs a closed, atomic lifecycle change,
`get` reads the canonical snapshot, `history` reads immutable history, and
`resumable` lists non-terminal persisted Missions. It accepts Forge values or
JSON-compatible mappings and persists deterministic JSON snapshots.

## Out of scope

This increment does not implement a Mission Runner, daemon, Execution Host,
queue, AI planning, Studio, transport, report retrieval, or repository
operation.
