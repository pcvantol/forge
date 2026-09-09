# Forge Runtime Instance Persistence

## Canonical concept

The **Runtime Instance** is Forge's persistent operational identity. The
Runtime Database is its SQLite implementation detail, never its architectural
identity.

```text
Repository Identity
  -> Runtime Identity
    -> Runtime Instance
      -> Runtime Database
```

Runtime Identity is immutable: Runtime ID, repository identity, original
repository root, optional repository UUID, instance version, initialization
version, and creation timestamp. Runtime Instance metadata is mutable and
validated: current instance location, last-access timestamp, and active
status. A Runtime Instance owns Mission State, Decision
Evidence, Architecture Reviews, Mission Recommendations, Execution Receipts,
Planning State, and runtime metadata. It records receipt identities only;
Engineering Platform retains ownership of Execution Evidence and Repository
Truth remains the architectural authority.

## Resolution, persistence, and bootstrap

The installed Runtime Instance belongs to the product-owned
[canonical data root](canonical-data-root.md), not a repository. Its durable
marker, lock, and database are all below that root. Git metadata and the
historical `.git/forge-runtime` location are legacy bootstrap material only;
installed Forge never discovers or silently migrates them.

`RuntimeResolver` resolves exactly one candidate beneath the selected data
root. It validates the instance marker, immutable Runtime Identity,
instance version, schema/migration version, instance status, SQLite integrity,
Mission/Decision/Receipt references, and Planning State before startup.
An invalid instance marker, identity mismatch, invalid references, an unknown
newer schema, or a marked root with a missing database fails closed. A marked
root never permits bootstrap to silently fabricate a replacement instance.

`RuntimeBootstrap` acquires one data-root inter-process initialization lock
before resolving and creating. It creates an instance only when the selected
root has no instance marker. The marker claim is atomic, so competing mutating
processes cannot create two instances. It never overwrites an existing Runtime
Instance.

Initialization creates only the empty runtime infrastructure: Mission State,
Decision Evidence, Architecture Reviews, Mission Recommendations, Execution
Receipts, Planning State, Bootstrap Portfolio State, and metadata storage. It
does not infer, import, or mark any Mission complete. In particular, it does
not materialise historical bootstrap Portfolio Seed Missions.

## Recovery

Recovery is root-scoped. An operator takes a SQLite-consistent backup with its
instance marker and restores it only to an explicitly selected, stopped data
root. A workspace move, branch switch, worktree switch, host restart, Forge
restart, or repository cleanup has no effect on installed state.

`RuntimeRecovery` reads only the validated Runtime Instance projection. It
does not inspect repository source, old databases, caches, or Execution Host
records to reconstruct state. Interrupted Missions resume from persisted
Mission State; recovery never fabricates a mission, review, recommendation,
decision, receipt, or planning record.

## Generation 1 completion reconciliation

Generation 1 Bootstrap is historical. Its Portfolio Seed Missions are owned by
Repository Truth and Engineering Platform evidence, not by the Runtime
Instance. Generation 1 completion therefore verifies an integrity-valid,
operational, intentionally empty Runtime Instance with an `IDLE` Dispatcher
and empty Approved Mission Queue. It cannot reconstruct bootstrap state by
inspecting repository source or external evidence.

See [Runtime Database](runtime-database.md) for SQLite storage details and
[the Runtime Instance report](../reports/forge-runtime-instance-report-001.md)
for the operational conclusion.
