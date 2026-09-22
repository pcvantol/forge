# Forge installed update controller

Status: bounded product-owned maintenance provisioner for the selected Forge
2.7.21 to 2.7.22 schema-37-to-38 transition and the selected 2.7.22/2.7.23 to
2.7.23/2.7.24 same-schema corrective transitions, plus the selected 2.7.24 to
2.7.25 schema-38-to-39 completion correction and 2.7.25 to 2.7.26 schema-39-to-39
vertical-Mission delivery, and the selected 2.7.26 to 2.7.27 schema-39-to-39
baseline/rolling-planning correction, plus the selected 2.7.27 to 2.7.28
schema-39-to-39 Operations-read correction, the selected 2.7.28 to 2.7.29
schema-39-to-39 planner-contract correction, and the selected 2.7.29 to 2.7.30
planner-contract cardinality correction, plus the selected 2.7.30 to 2.7.31
planner governance-policy binding correction, the selected 2.7.31 to 2.7.32
authoritative installed-health and readiness delivery, and the selected 2.7.31/2.7.32
to 2.7.33 same-schema installer correction. Support for those routes is not a
claim that its release is published or an installation has been activated.

This controller closes one concrete product provisioning gap. It is not the
universal Forge Platform installer, an installer UI, a new service supervisor,
or a Forge Runtime self-updater. Forge Platform remains the owner of normal
cross-product installation and update composition. Forge retains the concrete
runtime selection, schema migration, recovery, verification, and cleanup
semantics that the platform must eventually invoke through a qualified adapter.

The external entry point is
[`scripts/update_installed_forge.py`](../../scripts/update_installed_forge.py).
It is deliberately excluded from the `forge-autonomy` wheel and therefore
cannot be called by the installed runtime as a second self-installer.

## Supported operation

The controller accepts only one explicitly bound existing installation and an
exact `forge-autonomy` wheel for one of those bounded transitions. Every invocation
binds:

- operation, runtime, installation, and peer-configuration identities;
- data root, runtime root, current command resolver, legacy interpreter, and
  candidate Python interpreter;
- product version and original product source;
- wheel and terminal release-qualification receipt, including their SHA-256
  digests;
- protected installation-controller source and file digest.

It rejects a changed target, artifact, receipt, resolver, peer binding, writer
state, or concurrent maintenance owner. Unknown historical installer
provenance remains unknown; adoption records only the observed entry point,
interpreter, version, and bytes.

## Safety sequence

1. Read the wheel once through a no-follow descriptor; validate its digest,
   canonical RECORD, purelib tag, package metadata, member allowlist, and the
   exact terminal release receipt without importing it. The historical
   2.7.22 reconciliation receipt retains its dedicated validation; 2.7.23 and
   2.7.24, 2.7.25, 2.7.26, 2.7.27, 2.7.28, 2.7.29, 2.7.30, 2.7.31, 2.7.32 and 2.7.33 must have the normal protected release-complete
   publication/readback/cleanup shape and cannot be presented to an
   unsupported transition.
2. Create an isolated versioned runtime slot outside the source checkout with
   the explicit Python interpreter. Extract only the already validated bytes
   into a pip-free virtual environment, then verify every installed file and
   the generated command wrapper. An interrupted unreceipted slot is
   quarantined and rebuilt, never trusted in place.
3. Read the candidate's version, distribution, module, prefix, and interpreter
   from an isolated process.
4. Acquire the installation-operation lock, canonical
   `forge-runtime-mutation.lock`, and bootstrap `locks/runtime.lock`; reject an
   active runtime process, dispatcher, non-terminal Mission or scheduler
   submission, active provider-generation permit, planning queue, reset, or
   conflicting operation.
   A dispatcher left `ACTIVE` by an older terminal `FAILED`/`BLOCKED` Mission
   can be reconciled only while all four locks are held, no Forge process is
   active, and every other writer-state check is quiescent. The installed
   Runtime Database writer records `IDLE` plus an operational audit event;
   Mission, Action, submission and evidence rows remain unchanged. Any
   non-terminal or mismatched dispatcher binding still blocks the update.
5. Adopt the selected legacy command entry point behind a stable product-owned
   resolver. Before migration it still resolves to the byte-equal retained
   legacy entry point.
6. Take a SQLite backup through the backup API while the writer fence is held.
   Verify `integrity_check`, foreign keys, digest, and the complete logical
   pre-migration snapshot.
7. Re-open an isolated copy of that backup through the staged candidate's
   normal `forge ... server init` path. The 37-to-38 route requires exactly the
   reset-table additions and a fresh idle control row. The 38-to-38 route
   permits no table additions and requires the complete reset state and every
   domain/security/configuration row to remain byte-logically unchanged.
   The 38-to-39 route likewise permits no table additions or domain-row
   changes: it advances only the completion-reader compatibility metadata.
   The 39-to-39 routes qualify the candidate against an isolated copy and
   leave the live database bytes in place when the owning bootstrap makes no
   schema-object change. When the candidate strengthens schema objects without
   changing `user_version`, the controller installs that exact qualified copy
   atomically while preserving all historical tables and protected metadata.
   Historical terminal Missions are neither reopened nor reassessed.
8. Normalize the product-owned maintenance launcher to operation-independent
   canonical bytes, accepting only the exact older operation-labelled shape,
   then point the stable resolver at that fence. For routes through 2.7.25,
   take an exclusive SQLite writer boundary, prove the live database still
   matches the backup, and atomically install the Forge-migrated copy. That
   replacement remains read-only until activation and final receipt persistence.
   For schema-39-to-39 routes, verify the qualified copy and unchanged live
   snapshot under the fence. Retain the original database file when its schema
   fingerprint is unchanged; otherwise install the exact qualified copy under
   an exclusive atomic replacement boundary.
9. Atomically select the candidate slot and read back the exact installed CLI,
   module, interpreter, version, runtime identity, data root, schema, and peer
   binding. No service or historical Mission is started.
10. Persist one protected operation receipt below
    `artifacts/installation/<operation-id>` and retain the verified database
    backup below `backups/installation/<operation-id>`.
    The 2.7.24-to-2.7.25 route names its retained pre-migration backup
    `forge-schema38.sqlite3`; all schema-39-to-39 routes retain
    `forge-schema39.sqlite3`; older routes retain their prior backup name.

The controller never calls operational-reset prepare/apply/resume/finish,
Mission intake, Action derivation, a planner/provider, or an EP submission.
Credential material is neither read nor archived. A later installed CLI
preflight resolves the unchanged credential reference only for its separately
authorized read-only Forge-to-EP check.

## Interruption and resume

Re-run the same exact operation ID and arguments. A conflicting request is
rejected.

- Before atomic database replacement, failure restores the retained prior
  command route only when the complete live snapshot still equals `before`.
  A hard interruption may leave the explicit maintenance fence; resuming the
  same operation reconciles it from durable evidence.
- From the first target-schema readback or any ambiguous partial state onward, the
  old binary is never selected. Any caught activation/readback failure selects
  the maintenance fence; replay reconciles the exact protected candidate.
- A completed receipt is idempotently returned only after revalidating its
  bytes, backup, release receipt, controller, wheel manifest, slot, resolver,
  installed identity, target binding, schema, and database integrity. Later
  legitimate runtime history does not invalidate the historical update
  receipt.

The backup is recovery evidence, not permission for an automatic database
rollback. Restoring it after later security, budget, or external effects needs
separate authority and compatibility proof.

## Qualification boundary

`tests/test_installed_forge_update.py` covers exact release binding, target and
writer rejection, the bounded 37-to-38, 38-to-38, 38-to-39 and 39-to-39 transitions, preservation
of Missions, allocations, reviews, execution receipts, governance grants,
configuration and identity, concurrent-operation exclusion, resolver adoption,
prior-operation fence normalization and tamper rejection, canonical receipt
shape, path safety, exact slot contents, exclusive atomic
database replacement, late-writer rejection, and interruption before
migration, after migration, and during activation. An opt-in test runs the
entire route and replay against the exact published wheel and terminal release
receipt.
It also checks that the bounded stale-terminal dispatcher reconciliation leaves
the failed Mission history byte-for-byte intact, is idempotent, and refuses an
active or unrelated Mission. The installation controller's protected source
revision is reported separately from the released wheel's product source.

For 2.7.25 the only newly supported source version is 2.7.24; for 2.7.26 it
is 2.7.25; for 2.7.27 it is 2.7.26; for 2.7.28 it is 2.7.27; for 2.7.29 it is 2.7.28; for 2.7.30 it is 2.7.29; for 2.7.31 it is 2.7.30; for 2.7.32 it is 2.7.31; for 2.7.33 it is 2.7.31 or 2.7.32. Other version jumps are rejected. After schema 39 has been
observed during the 2.7.25 update, interruption recovery keeps the qualified
candidate or explicit maintenance fence selected; it never launches the retained
schema-38 binary against the migrated store. The 2.7.26 route does not swap an
unchanged schema-39 database. Once its candidate activation boundary is durable,
an interruption selects the candidate or maintenance fence until readback completes.
An atomic swap completed before its state write is adopted on resume after
preservation verification, without repeating the migration. Completion replay
also checks the exact target schema and schema fingerprint.

Production use additionally requires protected merge/check evidence for the
exact controller source, a terminal release-complete receipt, and live
post-activation installed CLI, reset-preview, and authenticated EP readback.
