# Forge 2.7.22 release and installed-update completion

Status: complete on 2026-09-18. This is a sanitized public projection of the
locally retained completion evidence. It closes only the Forge 2.7.22 release
reconciliation and the selected installed 2.7.21 to 2.7.22 update. It is not a
complete, independently reproducible live-installation audit and does not
replace the original completion record, receipts, backups or owning product
readbacks.

Aliases such as `<FORGE_DATA_ROOT>` and `<EP_INSTANCE_A>` deliberately stand
for stable local identities. The exact one-to-one alias mapping is retained
only with the protected local evidence.

## Public product and release identity

### Forge

- Product version: `2.7.22`; installed storage schema: `38`.
- Product source: `e167ddd9995ac5cd9e7765a1d338547d08df4755`.
- Published wheel:
  `forge_autonomy-2.7.22-py3-none-any.whl`,
  `sha256:c3bd47954cd74c4bf4b8273749b6d25e3eb157e5e20e20af78ea308d908b3830`.
- Published sdist: `forge_autonomy-2.7.22.tar.gz`,
  `sha256:8088139d556d651fd7caca457d1c2944970d4e5c6949ab57e8715260b511bd6f`.
- The original release workflow
  [run 35254063298](https://github.com/pcvantol/forge/actions/runs/35254063298)
  remains classified as failed. Its registry publication was not rerun,
  overwritten or reclassified.
- Existing-release reconciliation: PR
  [#138](https://github.com/pcvantol/forge/pull/138), candidate
  `3ceb6d2ad93b4353af631aba1ef94b557655de5b`, protected squash merge
  `7ee66b4b9246d33e1d36f5556752ba28e05f9107`, reconciliation
  [run 35278398853](https://github.com/pcvantol/forge/actions/runs/35278398853).
- Release-controller source:
  `7ee66b4b9246d33e1d36f5556752ba28e05f9107`. This is distinct from the
  unchanged product source above.
- Terminal public release receipt:
  `forge-release-complete-2.7.22-e167ddd9995ac5cd9e7765a1d338547d08df4755.json`,
  `sha256:54cc3857f301f4f34db684e07c6a754afdce9e5bde2a8db0c039cc9fdf0526d3`.
- Public release:
  [`forge-v2.7.22`](https://github.com/pcvantol/forge/releases/tag/forge-v2.7.22),
  targeting the product source above.
- Fresh production-registry downloads were byte-equal to the qualified wheel
  and sdist. The release operation reached `RELEASE_COMPLETE`; local release
  cleanup reached `COMPLETE`.

### Companion Engineering Platform installation

- Product and installed dashboard version: `2.3.82`; storage schema: `68`.
- Product/release source:
  `171e6361c4026ea5654d14c801b761ce760d17af`.
- Published wheel:
  `engineering_platform-2.3.82-py3-none-any.whl`,
  `sha256:f7711474843457e34643a0e00a20d8f7e94c9513f9e8894047511a26ccea4d80`.
- Published sdist: `engineering_platform-2.3.82.tar.gz`,
  `sha256:655cf1f23c8b0b39358252c53f59577314f4cc407f4e78289a7b92bf56e28274`.
- Terminal public release receipt:
  `engineering-platform-release-complete-2.3.82-171e6361c4026ea5654d14c801b761ce760d17af.json`,
  `sha256:ec8a49a9527d1cf5bd65429e83e3a08937c38e4680237c76d28357c7a54d218e`.
- Public release:
  [`engineering-platform-v2.3.82`](https://github.com/pcvantol/engineering-platform/releases/tag/engineering-platform-v2.3.82),
  targeting the product/release source above.
- Required reporting, telemetry and reset corrections were protected through
  EP PRs [#271](https://github.com/pcvantol/engineering-platform/pull/271)
  (`9302c4dab35dbf99ea47a2f02464bff490b2dd92`),
  [#272](https://github.com/pcvantol/engineering-platform/pull/272)
  (`f45694d40b753d235feac8b803d364e1450cae26`),
  [#275](https://github.com/pcvantol/engineering-platform/pull/275)
  (`ad3d34ed24aa42d8c785067426246bfe0500f515`) and
  [#276](https://github.com/pcvantol/engineering-platform/pull/276)
  (`171e6361c4026ea5654d14c801b761ce760d17af`). Release-helper PR
  [#277](https://github.com/pcvantol/engineering-platform/pull/277) merged as
  `aa73aa46322230aaf8afce4223fd497879d800d6` after the selected product
  source and did not retarget the release.

## Installation controller and qualification

The product-owned external Forge maintenance provisioner is documented in
[FORGE_INSTALLED_UPDATE_RUNBOOK.md](FORGE_INSTALLED_UPDATE_RUNBOOK.md). It is
not packaged in the Forge wheel and does not make Forge Runtime a
self-installer.

- Protected installation-controller delivery: PR
  [#139](https://github.com/pcvantol/forge/pull/139), final candidate
  `21ad57bca56734a8ab33fe24e14e855436e24e26`, protected squash merge
  `371a297d87d232f211487772d37892f5c5917c70`.
- Merged controller digest:
  `sha256:65f55b3b82a9a7357006d3c7f97e0079a8106100cea7d057925c55f1d06fbca0`.
- Independent quality/safety review: PASS on the exact final candidate.
- Independent security review: PASS on the exact final candidate.
- Protected version/source validation, test/static validation, CodeQL, Python
  analysis and non-blocking TDE observation passed.
- Full repository validation discovered 738 tests after the final regression
  addition; the opt-in exact-artifact test was excluded from the default run.
  Product-version and offline AI-development-projection checks passed. The
  focused suite passed 21/21.
- Opt-in end-to-end qualification used the exact published wheel and terminal
  release receipt. It passed installation, the real owning schema migration,
  atomic activation, idempotent replay and deliberate schema-rollback
  rejection.

## Sanitized installed-update result

The selected local operation is identified publicly as
`<FORGE_UPDATE_OPERATION_A>`. Its durable receipt and protected schema-37
backup are referenced as `<FORGE_INSTALLATION_RECEIPT_A>` and
`<FORGE_SCHEMA37_BACKUP_A>`. Their exact locations and local-only checksums
remain in the protected evidence set. The backup passed SQLite integrity and
foreign-key checks and was retained with owner-only permissions.

The same exact operation was replayed once. It revalidated the public release
receipt and controller plus the private backup, slot manifest, resolver,
installed identity, target, schema fingerprint and database integrity, then
returned the original completion receipt.

| Property | Before | After |
| --- | --- | --- |
| CLI version | `2.7.21` | `2.7.22` |
| Storage schema | `37` | `38` |
| Runtime identity | `<FORGE_RUNTIME_A>` | unchanged |
| Installation identity | `<FORGE_INSTALLATION_A>` | unchanged |
| Data root | `<FORGE_DATA_ROOT>` | unchanged |
| Peer configuration | `<LOCAL_PEER_CONFIGURATION_A>` | unchanged |
| Consumer | `<EP_CONSUMER_A>` | unchanged |
| Credential reference | `<EXISTING_SECURE_STORE_REFERENCE>` | unchanged |

The normal installed command `<FORGE_CLI>` resolves through its managed stable
resolver to `<FORGE_RUNTIME_SLOT_A>`. Its Python executable and import package
remain contained in that same versioned slot.

Forge's owning migrator ran first on an isolated copy. The controller then
installed the verified product-migrated database atomically under the
installation, runtime, bootstrap, resolver and SQLite writer fences. All 40
pre-existing domain tables and protected metadata were byte-logically
preserved. The only schema additions were the five expected operational-reset
tables, with one fresh idle control row. Integrity and foreign keys passed. No
historical Mission was resumed; no planner, provider, Action, submission,
permit or reset operation was started by the installed update.

## Installed readbacks

The installed Forge reset preview against `<FORGE_DATA_ROOT>` returned `READY`
and `allowed: true`, with schema 38, dataset generation 0, no blockers, no
unknown tables, no external files, `integrity_check: ok`, and no foreign-key
issues. The local plan digest is intentionally retained only in the private
evidence. This preview created no reset operation, backup, reset receipt or
data mutation.

The installed CLI also performed an authenticated, read-only Forge-to-EP HTTP
compatibility request. It returned PASS for:

- EP product/version `engineering-platform` `2.3.82` and instance
  `<EP_INSTANCE_A>`;
- consumer `<EP_CONSUMER_A>`, ACTIVE and submission-authorized;
- project/repository `forge`/`forge`, repository role `authority`;
- producer-readback contract `1.2` and terminal-evidence contract `1.4`.

The credential reference, peer configuration and bound identities remained
unchanged. No credential value was read into this record. The EP persistent
database and installation-control record retained modification times predating
the installed Forge update and compatibility readback; no EP product update,
configuration write or submission was caused by those checks.

## Later reset preflight and Mission status

A separately authorized joint reset preparation later used the installed
product-owned routes. Both products entered maintenance and produced verified
backups, but the mandatory pre-apply revalidation failed closed. Forge's second
preview reported `MAINTENANCE_ALREADY_ACTIVE`, its bound reset plan changed,
and the coordinator classified the result as `REVALIDATION_CHANGED`.

No reset `apply` milestone was admitted for either product. The Forge reset
operation was cancelled, the EP reset operation was aborted, both dataset
generations remained 0, existing operational data remained intact, and the
installed authenticated Forge-to-EP preflight passed again after EP service
recovery. The production reset was therefore **not performed**, a clean
baseline was not established, T0 was not recorded and Mission 3 was **not
started**. No replacement attempt was created.

The remaining step is to correct and qualify the owning cross-product
revalidation behavior before a separately authorized clean-baseline attempt.
This record does not grant that attempt, a new release, installation,
credential change, reset or Mission.

## Deliberate public omissions

The protected local evidence retains the exact values omitted from this public
projection. Omitted categories are:

- absolute user, installation, runtime, backup and receipt paths;
- hostnames, local endpoints and screenshots;
- concrete runtime, installation, EP-instance and consumer identities;
- secure-store references, credential material, verifiers and authorization
  payloads;
- installation-bound update/reset/coordinator operation IDs;
- hashes of local configuration, peer bindings, reset plans, databases,
  backups and non-public receipts;
- database copies, raw configuration dumps and raw operational readbacks.

Public source, release, PR, commit, package and registry-artifact identities
are intentionally retained above. The aliases do not merge distinct local
identities, and their exact mapping remains outside Git.

## Earlier branch exposure

An earlier unmerged public branch commit
`10dc261a2b3042143693d06784b767c2e2c8c370` contained the host-specific
operational metadata now omitted. A targeted review found operational and
identifying metadata but no usable token, bearer value, password, private key,
credential verifier or authorization payload. That earlier commit was not
included in this completion PR's ancestry.

Publishing this sanitized projection does not remove the earlier commit or its
metadata from GitHub history. No force-push, history rewrite, branch deletion,
credential rotation or repository-visibility change was performed or implied.
