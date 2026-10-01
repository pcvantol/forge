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
future PA-F1 migration must still prove lossless persistence and
reconciliation of actual serial execution state before claiming full
multi-slot support.
