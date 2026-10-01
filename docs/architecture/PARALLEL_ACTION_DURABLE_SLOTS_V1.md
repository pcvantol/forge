# Durable parallel Action planning slots V1

This is a bounded `PA-F1` storage and readback subset. It preserves the
existing serial Mission execution path and does not qualify complete PA-F1,
fan-out, reservations, EP admission, host execution, or parallel dispatch.

`RuntimeDatabase.record_mission_action_slots` accepts the strict
`parallel-action-graph/v1` document. It requires an existing Architecture-
approved Mission at the exact current state revision, the exact stored Action
ID set, and every target repository inside the approved Mission scope. The
validator checks target and baseline shape, predecessor identity, repository-
bound evidence digests, and a cycle-free graph. Scope membership is only a
planning containment check; it is not an EP binding or execution grant.
The writer also checks that the current stored Mission graph has unique Action
IDs, unique valid predecessors, and a unique nonempty approved scope before
recording a snapshot. Malformed or contradictory current state cannot create
a slot record, even when a set comparison would otherwise hide duplicates.

One immutable normalized document, including the sorted approved Mission
scope at registration, is stored per Mission revision in the
canonical SQLite runtime. Identical replay returns the same digest; changed
bytes at that revision fail closed. A later Mission revision can record a new
document, while the earlier document remains available for audit. Schema 41
adds this table without changing legacy serial Mission records. Operational
reset maintenance fences its writes.

Authenticated `GET /v1/missions/{mission_id}` includes `planning_slots` from
the same read-only snapshot, or `null` when no document exists. It verifies
the stored digest and contract, reports the revision as `CURRENT` or `STALE`,
and always reports `target_verification: UNVERIFIED` and
`dispatch_authorized: false`. A slot never supplies correlation, admission,
or execution evidence. Installed artifact qualification and full PA-F1/F2/F3
remain separate roadmap work.

For a snapshot at the current Mission revision, the installed reader also
rechecks the actual approved Mission status, repository scope, Action ID set
and predecessor graph. A same-revision change to these records produces a
safe `MISSION_ACTION_SLOTS_DRIFT` conflict instead of a false `CURRENT`
claim. A later Mission revision still reports the older snapshot as `STALE`.
The read does not repair or rewrite either record.
Earlier snapshots without a pinned approved scope cannot prove exact scope
continuity and therefore cannot report `CURRENT` after this guard is installed.

## Legacy serial correlation compatibility

Authenticated Mission detail also reports `serial_correlation` with contract
version `serial-action-correlation-compat/v1`. It reads the existing durable
singleton correlation without rewriting it. A bound view requires one
unambiguous relevant stored Action and matching direct or request-nested
Mission/Action/correlation identity. Only the Action ID and status,
correlation ID and optional host run ID are projected; prompt and
credential-bearing request fields are omitted. Missing correlation is
`UNAVAILABLE`; malformed, contradictory or multi-active records are
`UNSUPPORTED` with a reason and no selected Action. The view never implies a
new per-Action slot, EP admission, target verification, or host effect. A
this compatibility view alone does not prove lossless persistence or
reconciliation of actual serial execution state for full multi-slot support.

## Explicit serial execution-slot migration subset

Schema 42 adds a separate immutable `mission_action_execution_slots` table.
`RuntimeDatabase.migrate_legacy_serial_execution_slot` copies the complete
stored legacy correlation into one Action-keyed record only when the current
Mission, Action and correlation identity are unambiguous. It pins the source
revision and canonical correlation digest; identical replay is idempotent and
changed source bytes or revision conflict. It neither changes the legacy
Mission state nor submits or replays an execution request. No installation is
automatically migrated.

Authenticated Mission detail exposes only `execution_slots` migration status,
Action/correlation/run identity and source revision. Digests derived from the
private request are kept inside the runtime. The stored request and
private prompt remain inside the Forge runtime; malformed snapshots conflict
without exposing them. Missing or ambiguous migration stays explicit. This
subset does not qualify full PA-F1, runtime use of multiple execution slots,
target grants, admission, or parallel dispatch.

## Selected binding readback subset

The authenticated installed Mission detail compares each current, validated
planning-slot target's EP instance, project and repository IDs with the one
selected Forge→EP configuration in the same read-only runtime snapshot. Each
Action reports `selected_binding_resolution` as `MATCHED_SELECTED_BINDING`,
`UNCONFIGURED` or `MISMATCH`; the aggregate is that common value or `MIXED`.
An older Mission revision reports `STALE` regardless of today's configuration.
The comparison never rewrites or retargets a slot. A broken selected
configuration makes readback unavailable instead of asserting a match.

This identity comparison is narrower than target authorization: the selected
binding may later change, the Action's baseline remains unverified, and EP
admission, credential validity, host capacity and grants are not checked.
`target_verification` therefore remains `UNVERIFIED` and
`dispatch_authorized` remains false. The stored Action frontier remains
non-dispatchable; full PA-F1/F2/F3 qualification remains open.
