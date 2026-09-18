# Forge operational-history reset V1

**Status:** implemented product service and local administration CLI; source
qualification is recorded separately from protected delivery, release and
installed use. **Scope:** Forge-owned state only. This is neither a factory
reset nor a general SQL/database administration surface.

## Contract and boundary

The profile `forge-operational-history-v1` creates a new dataset generation
while retaining the Runtime Instance, project/EP binding, operator/security
authority, provider configuration, credential references, identifier
high-watermarks and anti-replay evidence. It never reads or writes Engineering
Platform CENTRAL and never invokes EP's CLI.

The same immutable operation identity binds:

- exact Runtime Instance ID, canonical database path/binding, marker and schema;
- plan, request, effect-set and meaningful-source-revision digests;
- real locally bound operator and current `SECURITY_APPROVAL` plus
  `OWNER_PROGRAMME_AUTHORIZATION` authority;
- installed implementation digest and Git source revision when genuinely
  available (`UNAVAILABLE_IN_INSTALLED_PACKAGE` is explicit otherwise);
- exact acknowledged referential findings wholly inside the purge set;
- one verified recovery backup and its manifest digest;
- dataset generation before/after, artifact steps and final verification.

There is no `--force`, arbitrary table list, peer SQL or automatic rollback.
The stable machine envelope is `contract_version=operational-reset-v1` and
contains no bearer values or raw credential verifiers.

The semantic plan contract is `forge-operational-reset-plan-1.1` under reset
policy version `2`. A general preview reports current availability separately
from the approved reset meaning. Consequently, the owning prepare transition
may add its exact maintenance operation, audit entries and verified backup
without changing the plan digest. A general preview still reports
`MAINTENANCE_ALREADY_ACTIVE` and cannot start or join an operation.

Only `revalidate` may inspect an already prepared operation. It requires the
exact operation, plan, request and backup digests and re-proves the current
operator/authority, physical database binding, schema, writer-fence owner,
source-row contents, preserved security/configuration, effect set, generation,
product/implementation provenance and verified backup. It creates a distinct
read-only revalidation digest; it neither rewrites the approved plan nor emits
a new backup or authority. Plan 1.0 operations are not reinterpreted under
these rules and must be cancelled before apply or handled by their original
installed implementation.

## Schema-owned data classification

Schema versions 38 and 39 share this complete table mapping. Version 39 adds a
completion-reader compatibility fence without adding application tables.
Criterion observations, `completion_history` and terminal continuation markers
inside `mission_state` remain `OPERATIONAL_HISTORY`; they introduce no separate
purge, schema migration reset or changes to preserved authority. Any additional application
table blocks reset until this contract is updated. SQLite indexes, triggers and
system objects are validated separately and are not purge candidates.

| Category | Tables | Reset treatment |
| --- | --- | --- |
| `INSTALLATION_AND_CONFIGURATION` | `runtime_metadata`, `execution_host_peer_configuration`, `planning_provider_security_config`, `planning_provider_external_session_config` | Preserve exactly. Credential references stay references; no Keychain read/dump/rotation. |
| `SECURITY_AND_AUTHORITY_LEDGER` | `installation_operator_binding`, `installation_operator_audit`, `governance_authority`, `governance_capability_grants`, `governance_decisions`, both provider-security/session audit tables, `planning_provider_generation_permits`, `mission_id_allocations` | Preserve. Pending/transport-committed provider permits become non-executable `INVALIDATED_BY_OPERATIONAL_RESET`; allocator history is unchanged. |
| `OPERATIONAL_HISTORY` | Mission state/lifecycle/recommendation/review/intake/amendment/evidence tables; Action derivation/result/reattempt/closure tables; execution context/receipt/integration/delegation/scheduler/correlation/exchange tables; token-preflight tables; bootstrap portfolio snapshot; Forge operational logs | Tombstone replay-sensitive identities, archive eligible external evidence, then delete in the schema-owned child-first transaction. |
| `DERIVED_CACHE_OR_PROJECTION` | `mission_runtime_projections`, `planning_state`, `dispatcher_state` | Delete from the active generation. |
| `MAINTENANCE_AUDIT` | `operational_reset_state`, `operational_reset_operations`, `operational_reset_audit`, `operational_reset_tombstones`, `operational_reset_artifact_steps` | Preserve; excluded from Mission/run/usage views. |
| `UNKNOWN_OR_UNSUPPORTED` | Anything else | Destructive progression blocked. |

Record-level rules matter. `planning_provider_generation_permits` remain in the
security ledger but lose executable state. Mission-bound token and reattempt
records are removed only after their receipt/request/authorization identities
become durable reset tombstones. Old correlation, submission, Action and receipt
identities cannot be reintroduced through owning writers.

## External data classification

The database, WAL/SHM and owning lock are SQLite/runtime control, not domain
history. `instance/runtime-instance.json`, prior `backups/`, locks and strict
installation/qualification artifacts are preserved. In particular
`artifacts/controlled-installation-*` and entries under
`artifacts/{installation,qualification}/` retain installation/artifact/product
qualification provenance.

Only product-shaped operational paths are eligible:

- `artifacts/{operational,runtime,missions}/...`: archive in the operation's
  recovery backup, verify digest, then remove from active ingest;
- recognized `.json`, `.jsonl` and `.journal` entries under `journals/`, and
  `.log`/`.jsonl` entries under `logs/`: archive, verify and remove;
- regular files under `cache/`: remove as derived cache, without claiming them
  as recovery evidence.

Unknown artifacts, instance files, top-level files, special files, unreadable
entries and every symlink block. The service never follows a symlink and never
touches repositories, source, documents, other workspaces or other instances.

## State machine, fencing and crash recovery

```text
read-only PREVIEW
  -> PREPARED (durable writer fence + exact authority/request binding)
  -> BACKUP_VERIFIED
  -> read-only operation-bound REVALIDATE
  -> DATABASE_APPLIED (one domain transaction)
  -> APPLIED (every filesystem step reconciled)
  -> VERIFIED
  -> COMPLETED (writer fence released)
```

Normal owning `RuntimeDatabase` opens fail while maintenance is active. Every
already-open connection is fenced by schema triggers that directly consult the
durable state before a write, without requiring a connection-local UDF during
normal operation. The reset transaction temporarily removes only its exact
delete/update fence triggers under `BEGIN IMMEDIATE` and restores them before
commit. A process-local OS lock is therefore not the crash boundary. The
same-root mutation lock serializes runtime service ticks and maintenance
commands. A raw/peer SQL writer is unsupported and does not become a product
interface.

Successful revalidation is not a durable permission token. `apply` repeats
the operation, operator/authority, database identity, lifecycle, fence,
generation, meaningful-source and backup checks after entering its actual
`BEGIN IMMEDIATE` mutation boundary. Fence loss or drift after revalidation
therefore remains blocking.

`resume` rereads the same operation. A failure before the SQLite commit leaves
the whole operational population. A failure after commit continues forward.
Each external item has a durable step; if removal happened before its step write,
resume accepts absence only when the verified archive copy still matches.
Neither resume nor uncertainty creates another reset.

## Backup and recovery

Prepare uses SQLite's online backup API after the durable writer fence, then
converts the isolated image to a self-contained non-WAL snapshot. The private
`0700` operation directory contains a `0600` database, marker, archived external
artifacts and manifest. The manifest binds source instance/schema/version,
operation/plan/request, source counts, exact known FK findings, inclusions,
exclusions and per-file SHA-256. It excludes Keychain, provider login/session,
venv/tooling, cache, locks and earlier backups.

Verification copies the database into a temporary non-active root, performs
`quick_check`, reconstructs the meaningful source revision and compares external
digests. A known operational orphan remains honestly listed in the backup; the
backup is byte/semantic recovery evidence, not falsely labelled FK-clean.

Forward reconciliation is the normal recovery. Do not copy the old database
back over a running instance and do not use it to undo later revocations,
budgets or external effects. A physical restore requires a separately authorized
stopped-root recovery decision; it must first reconcile security/external state.

## Postconditions

Verify requires `integrity_check=ok`, `quick_check=ok`, zero foreign-key errors,
zero rows in every operational/projection table, no active pre-reset provider
permit, no active classified operational file, exact preserved-table digests,
same Runtime Instance/marker/peer binding, the expected dataset generation and
a still-verifiable recovery backup. Only its exact verification digest releases
maintenance. “Clean” therefore means no old active/executable operational
population; security tombstones, allocator history and maintenance audit remain.

Repository document `missions/MISSION-0003.md` is reported as a historical
repository-document namespace. It is not an active Runtime Mission. The reset
does not rename it, fabricate a Mission, reset the allocator or promise that the
next runtime identity will display `MISSION-0003`.
