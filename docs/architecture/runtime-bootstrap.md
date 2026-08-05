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

Repository Identity is derived from the Git repository's initial commit, not
an absolute filesystem path. It is therefore stable across branch and
worktree transitions and repository relocation. Where a host supplies an
explicit Git `forge.repositoryUUID`, Forge persists it as immutable supporting
identity metadata. The durable registry and default database live in Git-common
metadata, outside cleanup-prone `.forge`, and are shared by all worktrees. A
configured Runtime Root may place the database outside the repository; the
single canonical registry remains in Git-common metadata so future executions
discover the same instance without relying on caller configuration.

`RuntimeResolver` resolves exactly one candidate from configured location,
registered instance location, repository default, and local discovery. It
validates the registry, immutable Runtime Identity, repository identity,
instance version, schema/migration version, instance status, SQLite integrity,
Mission/Decision/Receipt references, and Planning State before startup.
Ambiguity, a corrupt registry, identity mismatch, invalid references, or a
missing registered location fails closed. A prior registration never permits
bootstrap to silently fabricate a replacement instance.

`RuntimeBootstrap` acquires one repository-wide inter-process initialization
lock before resolving, creating, and registering. It first discovers a valid
instance, or creates a new instance only when no registry exists and no
candidate exists. The registry claim is atomic, so competing configured
locations cannot produce multiple instances. It never overwrites an existing
Runtime Instance; explicit relocation is the sole controlled registry update.

Initialization creates only the empty runtime infrastructure: Mission State,
Decision Evidence, Architecture Reviews, Mission Recommendations, Execution
Receipts, Planning State, Bootstrap Portfolio State, and metadata storage. It
does not infer, import, or mark any Mission complete. In particular, it does
not materialise historical bootstrap Portfolio Seed Missions.

## Relocation and recovery

Explicit relocation copies SQLite through its backup API, validates the
destination, activates its registry entry atomically, then removes the old
database. The Runtime ID and Repository Identity are preserved. This is the
only migration path; a workspace move, branch switch, worktree switch, host
restart, Forge restart, or repository cleanup merely resolves the same
registered instance.

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
