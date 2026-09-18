# Forge operational reset operator runbook

This runbook uses only the installed Forge-owned CLI. Replace the placeholders
with values returned by the immediately preceding JSON receipt. Keep the Forge
data root explicit for every command. Exit code `0` means the command produced
its declared readback; exit code `1` means no success may be inferred.

> **Production safety:** in the current preparation assignment run `preview`
> only against the selected live root. Every command from `prepare` through
> `finish` changes maintenance/backup/reset state and is destructive or enables
> destructive continuation. Use those commands only during the later explicitly
> authorized clean-CENTRAL preflight.

## 1. Read-only preview

```text
forge --data-root "/absolute/Forge Server" server reset preview
```

Record `target.instance_id`, `target.database_identity`, `schema_version`,
`dataset_generation`, `plan_digest`, `relevant_revision_digest`, counts,
blockers, exact `required_fk_acknowledgements` (under `details`) and the
preserved-bindings digest. A schema-37 installation may be inventoried, but
reports `SCHEMA_MIGRATION_REQUIRED`; preview never migrates it.

## 2. Enter maintenance and create/verify backup — MUTATING

```text
forge --data-root "/absolute/Forge Server" server reset prepare \
  --operation-id "forge-reset-<approved-reference>" \
  --plan-digest "sha256:<preview-plan>"
```

For a specifically reviewed operational-only FK finding, repeat its exact ID:

```text
  --acknowledge-operational-fk "sha256:<exact-issue-id>"
```

There is no broad ignore option. Findings reaching preserved or unknown data
block. Prepare authenticates the installed local operator and current Security/
programme capabilities, activates the durable writer fence, produces the
consistent backup and returns `request_digest` plus verified `backup.digest`.
If backup creation fails, leave the instance in maintenance and use `status`;
do not start another operation.

## 3. Revalidate this prepared operation — READ-ONLY

Do not repeat the general preview as the same-operation gate. It correctly
blocks any new reset while maintenance is active. Instead, bind the exact
prepared receipt:

```text
forge --data-root "/absolute/Forge Server" server reset revalidate \
  --operation-id "forge-reset-<approved-reference>" \
  --plan-digest "sha256:<preview-plan>" \
  --request-digest "sha256:<prepared-request>" \
  --backup-digest "sha256:<verified-backup>"
```

Require `allowed=true`, no blockers, the unchanged plan/relevant-source and
preserved-bindings digests, the exact fence owner and a revalidation digest.
This command must not change owning status, data, authority or backup bytes.

## 4. Apply the reset — DESTRUCTIVE

```text
forge --data-root "/absolute/Forge Server" server reset apply \
  --operation-id "forge-reset-<approved-reference>" \
  --plan-digest "sha256:<preview-plan>" \
  --request-digest "sha256:<prepared-request>" \
  --backup-digest "sha256:<verified-backup>"
```

## 5. Verify — MAINTENANCE REMAINS ACTIVE

```text
forge --data-root "/absolute/Forge Server" server reset verify \
  --operation-id "forge-reset-<approved-reference>" \
  --plan-digest "sha256:<preview-plan>" \
  --request-digest "sha256:<prepared-request>" \
  --backup-digest "sha256:<verified-backup>"
```

Require `state=VERIFIED`, all operational counts zero, all integrity checks
green, unchanged target/bindings and a non-empty `verification_digest`.

## 6. Interrupted operation

```text
forge --data-root "/absolute/Forge Server" server reset status \
  --operation-id "forge-reset-<approved-reference>"

forge --data-root "/absolute/Forge Server" server reset resume \
  --operation-id "forge-reset-<approved-reference>" \
  --plan-digest "sha256:<preview-plan>" \
  --request-digest "sha256:<prepared-request>" \
  --backup-digest "sha256:<verified-backup>"
```

Resume reconciles the same operation through verification. If failure happened
before a backup digest exists, omit `--backup-digest`; the same PREPARED operation
finishes its backup first. Do not automatically restore or create a replacement
operation.

## 7. Release maintenance — MUTATING

```text
forge --data-root "/absolute/Forge Server" server reset finish \
  --operation-id "forge-reset-<approved-reference>" \
  --verification-digest "sha256:<verified-result>"
```

An unapplied PREPARED/BACKUP_VERIFIED operation may instead be safely cancelled:

```text
forge --data-root "/absolute/Forge Server" server reset finish \
  --operation-id "forge-reset-<approved-reference>" \
  --cancel-before-apply
```

Cancellation is forbidden after database apply. After successful coordinated
Forge and EP verification, perform the separately authorized read-only local
HTTP authentication/preflight; it must not create a Mission or submission.

## Coordinated later clean-CENTRAL preflight

1. Run installed read-only preview for Forge and EP; bind both target and plan
   digests to one external maintenance reference.
2. Resolve the historical document/runtime Mission namespace decision before T0
   if the normal allocator cannot produce the desired display label.
3. Prepare both owning operations; confirm both durable maintenance states and
   both verified backups.
4. Invoke both owning operation-bound `revalidate` commands under their writer
   fences. Do not substitute general preview.
5. Apply each owning reset sequentially. If either fails, keep both products in
   maintenance and resume the same owning operation; never auto-resume the first.
6. Verify both empty operational generations, preserved identities/peer binding,
   security/allocator state and backups.
7. Finish both only after the joint coordinator has recorded both verification
   digests. Then run the non-generating HTTP authentication check.

This recipe is intentionally not executed by the current implementation task.
