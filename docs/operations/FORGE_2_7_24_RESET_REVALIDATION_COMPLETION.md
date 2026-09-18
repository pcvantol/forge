# Forge 2.7.24 reset-revalidation remediation completion

Status: complete on 2026-09-18. This is a sanitized public projection of the
locally retained qualification, release, installation and read-only production
evidence. It does not authorize a production reset, a clean-baseline attempt or
Mission 3. Exact local identities, paths, operation identifiers, configuration
and evidence digests, credential references, backup locations and raw readbacks
remain outside Git.

## Root cause and corrected boundary

The failure was reproduced with the former installed Forge and Engineering
Platform CLIs, the real EP-owned coordinator and isolated synthetic databases.
After both owning `prepare` operations, a general Forge preview correctly
reported `MAINTENANCE_ALREADY_ACTIVE`; however, the coordinator used that
general preview as revalidation of the already-authorized operation. The old
semantic plan also included transient maintenance/audit observations produced
by the operation's own prepare step. The resulting plan change was classified
as `REVALIDATION_CHANGED`, even though the purge/preserve source revision had
not changed.

Forge and EP now distinguish a general availability preview from an explicit,
read-only revalidation of the same durable operation. The semantic plan binds
the approved reset meaning without transient maintenance availability. The
operation-bound route verifies the owning operation, actor and current
authority, physical database/instance and schema, lifecycle phase, writer
fence, original request/plan/effect, source and preserved state, generation,
verified backup and compatible implementation/contract provenance. Apply
repeats the critical checks inside its owning mutation transaction. The
coordinator requires these owning revalidation routes and rejects the older
contract rather than emulating them or reading peer databases.

General preview behavior is unchanged: a new reset remains blocked while a
writer or maintenance operation is active. A supplied operation identifier is
not sufficient to join, resume or authorize an existing operation.

## Protected delivery and releases

### Forge remediation

- PR [#144](https://github.com/pcvantol/forge/pull/144) delivered the owning
  reset contract/service/CLI remediation. Candidate
  `e5fed4b91fdd3f51800c0a2fef7f099b1a9d0dfe` was protected-merged as
  `9dd834350fdd9a4b89a9f6043433164ee5cf07ea`.
- Release [`forge-v2.7.23`](https://github.com/pcvantol/forge/releases/tag/forge-v2.7.23)
  completed through workflow
  [35317485194](https://github.com/pcvantol/forge/actions/runs/35317485194).
- The first exact installed-update attempt exposed a separate new defect: the
  shared external update fence still contained the previous update operation
  label. The controller failed closed before product mutation. No manual fence
  edit or runtime bypass was used.
- PR [#146](https://github.com/pcvantol/forge/pull/146) made that shared fence
  operation-independent and only normalizes the exact recognized legacy shape.
  Candidate `1fe8958ba70d662f9b102b112aa58bbf7c4dde42` was protected-merged as
  `d5461a345222c3e9c45661fbab0668760264ff0c`.
- Release [`forge-v2.7.24`](https://github.com/pcvantol/forge/releases/tag/forge-v2.7.24)
  completed through workflow
  [35319869648](https://github.com/pcvantol/forge/actions/runs/35319869648).
  Its qualified wheel has SHA-256
  `203382514160616d6236bea6f177655e316d4318fe14b9c6871406466f7fcabd`;
  its sdist has SHA-256
  `7427c1d0e2705f967cc9f1acca232ad4f2ff48739077516b26547fb1eec5117d`.

All required protected version/source validation, tests, security analysis,
CodeQL and trusted-delivery observation passed on the exact candidates. Forge's
final local repository validation discovered 746 passing tests; one opt-in
published-artifact test remained deliberately outside the default run.

### Engineering Platform and coordinator remediation

- EP PR [#278](https://github.com/pcvantol/engineering-platform/pull/278)
  delivered the owning EP reset correction and the real coordinator update.
  Candidate `75ef07b5eb5d193b490b246881d27c15f10c90ca` was protected-merged as
  `13691e4502c239e03558a9c79538ae9b7387938f`.
- Release
  [`engineering-platform-v2.3.83`](https://github.com/pcvantol/engineering-platform/releases/tag/engineering-platform-v2.3.83)
  completed through workflow
  [35318078132](https://github.com/pcvantol/engineering-platform/actions/runs/35318078132).
  Its qualified wheel has SHA-256
  `006b47b8a864502a4b4596ba17e2724fe6ddba1e932615e183841cfc913e5021`.
- Protected hosted validation, security analysis, CodeQL, version checks,
  trusted delivery and release readback all passed.

## Installed synthetic qualification

The full destructive qualification used fresh isolated synthetic Forge and EP
roots and the exact installed product CLIs plus the released coordinator. The
sequence was:

1. general preview for both products;
2. owning prepare and verified backup for both products;
3. general preview again, proving that a *new* reset remained blocked by the
   expected `MAINTENANCE_ALREADY_ACTIVE` condition while the semantic plan and
   relevant/preserved source bindings stayed stable;
4. operation-bound coordinator revalidation for both products;
5. separate-process restart/readback;
6. owning Forge apply, then owning EP apply;
7. owning verification for both products;
8. joint resume authorization and separate owning finish operations.

The final coordinator state was `COMPLETE`. Forge advanced its synthetic
dataset generation from 0 to 1 and purged 28 classified history tables. EP
advanced from 0 to 1 and purged 57 classified history tables. Preserved
configuration/security data, integrity and foreign keys passed.

Negative and recovery qualification covered a foreign operation, changed
authority, changed writer fence, wrong or changed backup, relevant row-content
drift with unchanged row counts, preserved-state drift, generation drift and a
change between revalidate and apply. It also covered one-product apply failure,
crashes after prepare/revalidate/apply, an uncertain response and restart from
durable coordinator state. Unsafe or uncertain cases remained visible and
blocked; neither product was silently resumed.

## Exact installed activation and production readback

The exact Forge `2.7.24` release artifact was installed through the protected
external updater. Storage schema remained 38. The updater retained its verified
SQLite backup; all 45 pre-existing tables, peer configuration and credential
binding were preserved. The final installed reset state was idle with dataset
generation 0. Read-only reset preview returned ready, with database integrity,
foreign keys, classification and unknown-table checks passing.

The exact EP `2.3.83` release artifact was installed through its official
updater. Its first post-activation health check found an older detached local
listener still occupying the service endpoint. The owning candidate CLI stopped
that listener and the same durable update operation resumed to `COMPLETE`.
Storage schema remained 68 and critical services were healthy. This recovery is
part of the partial-failure/restart evidence; no product database was edited
manually.

Final authenticated, read-only cross-product preflight passed for the installed
Forge `2.7.24` and EP `2.3.83` artifacts, active consumer and compatible
producer-readback and terminal-evidence contracts. EP's read-only reset preview
continued to block on its active target writer, as required. No production
prepare, backup, revalidate, apply, verify, resume or finish operation was
created by these checks.

## Future preflight boundary

A future reset requires new, explicit authorization and fresh owning evidence.
Before any destructive step, operators must re-establish the exact installed
release/receipt identities, both product health readbacks, idle reset state and
writer conditions, authenticated cross-product compatibility, current actor
authority and policy, physical targets, source/preserve bindings, generation,
and newly verified operation-bound backups. Earlier plans, requests, backups or
operation identifiers grant no authority.

This remediation therefore leaves production operational data unchanged. A
clean baseline has not been established, T0 has not been recorded and Mission 3
has not started.

## Deliberate public omissions

The protected local evidence retains the exact values omitted from this public
projection, including absolute installation/runtime/data/backup paths, host and
endpoint details, local product/instance/consumer identities, secure-store and
credential material, authorization payloads, reset/update/coordinator operation
identifiers, private receipts, raw databases/readbacks and hashes of local
configuration, plans, databases and backups. Public PR, commit, release,
workflow and published-package identities are intentionally retained.
