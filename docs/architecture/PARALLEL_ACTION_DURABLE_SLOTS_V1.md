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

One immutable normalized document is stored per Mission revision in the
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
