# Forge 2.7.22 release and installed-update completion

Status: complete on 2026-09-18. This record closes only the existing Forge
2.7.22 release reconciliation and the selected installed 2.7.21 to 2.7.22
update. It does not authorize or record a production operational reset, a
clean baseline, T0, or Mission 3.

## Product and release identity

- Product version: `2.7.22`.
- Product source: `e167ddd9995ac5cd9e7765a1d338547d08df4755`.
- Published wheel:
  `forge_autonomy-2.7.22-py3-none-any.whl`,
  `sha256:c3bd47954cd74c4bf4b8273749b6d25e3eb157e5e20e20af78ea308d908b3830`.
- Published sdist: `forge_autonomy-2.7.22.tar.gz`,
  `sha256:8088139d556d651fd7caca457d1c2944970d4e5c6949ab57e8715260b511bd6f`.
- Original release workflow run `35254063298` remains recorded as failed. Its
  registry publication was not rerun, overwritten, or reclassified.
- Existing-release reconciliation: PR
  [#138](https://github.com/pcvantol/forge/pull/138), candidate
  `3ceb6d2ad93b4353af631aba1ef94b557655de5b`, protected squash merge
  `7ee66b4b9246d33e1d36f5556752ba28e05f9107`, reconciliation run
  `35278398853`.
- Release-controller source:
  `7ee66b4b9246d33e1d36f5556752ba28e05f9107`.
- Terminal release receipt:
  `forge-release-complete-2.7.22-e167ddd9995ac5cd9e7765a1d338547d08df4755.json`,
  `sha256:54cc3857f301f4f34db684e07c6a754afdce9e5bde2a8db0c039cc9fdf0526d3`.
- GitHub release `forge-v2.7.22` is public, database ID `390928129`, node ID
  `RE_kwDOUKfYVs4XTRcB`, and targets the unchanged product source.
- Fresh production-registry downloads were byte-equal to the qualified wheel
  and sdist. The release operation is terminal `RELEASE_COMPLETE`, with local
  cleanup `COMPLETE`.

## Installation controller and qualification

The product-owned external maintenance provisioner is documented in
[FORGE_INSTALLED_UPDATE_RUNBOOK.md](FORGE_INSTALLED_UPDATE_RUNBOOK.md). It is
not packaged in the Forge wheel and does not make Forge Runtime a
self-installer.

- Protected delivery: PR
  [#139](https://github.com/pcvantol/forge/pull/139), final candidate
  `21ad57bca56734a8ab33fe24e14e855436e24e26`, protected squash merge
  `371a297d87d232f211487772d37892f5c5917c70`.
- Merged controller digest:
  `sha256:65f55b3b82a9a7357006d3c7f97e0079a8106100cea7d057925c55f1d06fbca0`.
- Independent quality/safety review: PASS on the exact final candidate.
- Independent security review: PASS on the exact final candidate.
- Protected checks: version/source validation, test and static validation,
  CodeQL, Python analysis, and non-blocking TDE observation all passed.
- Full repository validation: 738 tests discovered after the final regression
  addition, with the opt-in exact-artifact test excluded from the default run;
  product version and offline AI-development projection passed. The focused
  suite passed 21/21.
- The opt-in end-to-end qualification used the exact published wheel and
  terminal release receipt. It passed installation, real owning schema
  migration, atomic activation, idempotent replay, and deliberate
  schema-rollback rejection.

## Selected installed update

- Operation ID: `forge-update-2722-live-reset-readiness-20260918-001`.
- Durable receipt:
  `/Users/pcvantol/Library/Application Support/Forge Server/artifacts/installation/forge-update-2722-live-reset-readiness-20260918-001/receipt.json`,
  `sha256:306f6c71bc4899dcbb1d325d5c1b969036d8f64ce6a2691038e2b25969a36831`.
- Protected schema-37 backup:
  `/Users/pcvantol/Library/Application Support/Forge Server/backups/installation/forge-update-2722-live-reset-readiness-20260918-001/forge-schema37.sqlite3`,
  `sha256:de981a32f1fc2cd8f4c5f6fb90f45fae0461a5727b69019450cc582ec4f8f358`.
  SQLite integrity was `ok`, foreign-key issues were empty, and the backup is
  mode `0600`.
- The same exact operation was replayed once. It revalidated the release
  receipt, controller, backup, slot manifest, resolver, installed identity,
  target, schema fingerprint, and database integrity, then returned the
  original completion receipt.

Before and after identity:

| Property | Before | After |
| --- | --- | --- |
| CLI version | `2.7.21` | `2.7.22` |
| Storage schema | `37` | `38` |
| Runtime ID | `forge-runtime-735b0321-c4bf-41cd-81d3-9ee00249254b` | unchanged |
| Installation ID | `99ede979-e8b8-48ca-9174-3257778c680f` | unchanged |
| Data root | `/Users/pcvantol/Library/Application Support/Forge Server` | unchanged |
| Peer configuration digest | `sha256:c8188dd7185c0916f52aedd7261c415995d68ca76161ccdf510e5a46524e3693` | unchanged |
| Consumer | `forge-managed-e2e` | unchanged |
| Credential reference | `keychain://forge.ep/consumer` | unchanged |

The normal command remains
`/Users/pcvantol/.platformio/penv/bin/forge`. It resolves through the managed
stable resolver to
`/Users/pcvantol/Library/Application Support/Forge Server Runtime/slots/2.7.22-c3bd47954cd7/bin/forge`.
Its Python executable and import package are contained in that same slot.

Forge's owning migrator ran first on an isolated copy. The controller then
installed that fully verified product-migrated database atomically under the
installation, runtime, bootstrap, resolver, and SQLite writer fences. All 40
pre-existing domain tables and protected metadata were byte-logically
preserved. The only schema additions were the five expected operational-reset
tables, with one fresh idle control row. Integrity and foreign keys passed.
No historical Mission was resumed; no service, planner, provider, Action,
submission, permit, or reset operation was started.

## Installed readbacks

The actually installed command executed:

```text
forge --data-root "/Users/pcvantol/Library/Application Support/Forge Server" server reset preview
```

The result was `READY` and `allowed: true`, with schema 38, dataset generation
0, no blockers, no unknown tables or external files, `integrity_check: ok`, no
foreign-key issues, and plan digest
`sha256:20496257bf9505ad6df0d1f9755f0db3aec8999fd7480326845b2ab04cc07705`.
The preview classified the configured installation/security/authority records
for preservation and the current operational-history records for a future
purge. It did not create an operation ID, backup, reset receipt, or data
mutation. `operational_reset_operations` remains empty and reset state remains
`IDLE` at dataset generation 0.

The installed CLI then performed only the authenticated read-only Forge-to-EP
compatibility request. It returned PASS for:

- EP product/version `engineering-platform` `2.3.82`;
- EP instance `63bda874-6521-44c7-bd1d-78398cdeb6c0`;
- consumer `forge-managed-e2e`, ACTIVE and submission-authorized;
- project/repository `forge`/`forge`, repository role `authority`;
- producer readback contract `1.2` and terminal evidence contract `1.4`.

The credential reference and configuration revision 5 remained unchanged.
The EP persistent database and installation-control record retained modification
times predating this update and readback; no EP product update, configuration
write, submission, or unexpected persistent mutation was observed.

## Explicitly not performed and later sequence

- Production reset: not performed. No `prepare`, `apply`, `resume`, `verify`,
  or `finish` command was invoked.
- Clean baseline: not established.
- T0 and Mission 3: not started.
- Credentials, consumer, grants, allocations, Missions, Actions, runs, and chat
  history were not rotated, removed, archived, or recreated.

The later authorized operation must remain a separate decision and follow:

```text
fresh joint preview
→ explicit reset authorization and backup/receipt locations
→ both writer fences
→ coherent backups
→ owning resets
→ joint verification
→ clean baseline
→ T0
→ the single Mission-3 attempt
```

Before that future T0, explicitly reconcile the namespace relationship between
the historical repository document `missions/MISSION-0003.md` and the runtime
Mission allocator. This completion changed neither the document, allocator,
criteria, nor Mission state.
