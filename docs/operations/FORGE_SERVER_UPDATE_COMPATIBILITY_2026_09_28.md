# Forge Server update compatibility completion — 2026-09-28

## Authority and boundary

This is the terminal Forge-owned evidence for assignment
`L2-FORGE-SERVER-UPDATE-COMPATIBILITY-V1-20260928`, registration revision 25,
plan revision 1. It qualifies the existing `forge-installed-update/v1` and
`forge-installed-update-assessment/v1` contracts. It does not qualify Forge
Platform installer composition, signing, service-account or LaunchDaemon
choreography, a production instance, physical reboot, production Engineering
Platform, provider credentials or Project Agents.

The canonical backlog binding is the existing
`FSH-SERVICES/server-only installed lifecycle` subset. That subset is
`QUALIFIED`; parent `FSH-SERVICES` remains `PLANNED`.

## Exact target and controller

The product artifact and the external update controller are independently
bound:

| Item | Exact identity |
| --- | --- |
| Target release | `forge-v2.7.38`, `RELEASE_COMPLETE` |
| Target source | `0a3d6e35b01da93bb5a674ae7795558655c16c7d` |
| Target wheel | `forge_autonomy-2.7.38-py3-none-any.whl` |
| Target wheel SHA-256 | `e9a5609969b8e49476f44e99a6cf72b8edf60280a77e010effe55a3bc1b33af8` |
| Target sdist SHA-256 | `e720edd0c3ce77af4cb6526be9c40e4832ee4977b99def08ad648d8de89f08e0` |
| Release-complete receipt SHA-256 | `7f8f4646a369ea565e52f8420df665acb64d032e5004e1b45ef7dc8427548c49` |
| Release workflow | run `36467852418`, success |
| Final controller source | `bf7ae99c67e32fd2047965f19ece30a35071e868` |
| Final controller SHA-256 | `9c43e1c3dcb411fb5f81a6a70d99b0c28b6bb2c79117f70703a50037e2e78183` |

The normal product release remains the immutable 2.7.38 release. Later
controller corrections did not modify, relabel or republish its wheel.

## Supported published-wheel matrix

Every row used a new disposable Python 3.14 environment and data/runtime root,
the exact public old and target wheels, the exact public release-complete
receipt, and the final controller fetched from its protected merge. No source
checkout import, `PYTHONPATH` fallback, old-wheel edit or version rewrite was
used.

| Old release/source/wheel SHA-256 | Assessment | Actual update | Exact current |
| --- | --- | --- | --- |
| 2.7.35 / `ff4c0d45f51161376104250cd6efcfb6f045b8ac` / `79e7d7ef36da7c73c31981c39f4a1d90b0204965438779014fc129b79a2da2d0` | `UPDATE_AVAILABLE`; digest `sha256:6770a9868d3bee18ba0b1e74a87ae28d9f39597eb239714aa82132bea631fe87`; full selected tree byte-identical | `COMPLETE`; request `sha256:36771ef8917e6592cbee5f205fe3c20d9ef725a2099c922c14105678ef797b06` | `UP_TO_DATE`; non-mutating; full selected tree byte-identical |
| 2.7.36 / `ed1e623ef3cedd8c4f720510e0052409b2d5ab1f` / `c10e9584649538f2f1547bb09fd3982cc3495dcf34ef807d66463661fdd5cd68` | `UPDATE_AVAILABLE`; digest `sha256:36edbe6fe6f0fc70bfc6d76bafcbc14665841dc98c20a735e5166188d5069bcb`; full selected tree byte-identical | `COMPLETE`; request `sha256:9c3b87afbf42705d3e938d9e457b7c27185dd86e47fc1c85fbdf34169e00bb1f` | `UP_TO_DATE`; non-mutating; full selected tree byte-identical |
| 2.7.37 / `a78523603d6ea081d07875ea6b557e73b5d4fe63` / `b8165e59935a1edf22590cf6378fab3c5b1014aded88eec1e1a294bfa1b94938` | `UPDATE_AVAILABLE`; digest `sha256:0b5aad2f01fdde152cc061ea3beb78669ccb9439167d118a8bb1225e61b153ea`; full selected tree byte-identical | `COMPLETE`; request `sha256:84bb46fcb8e7ad5fdce00e0322e1c272f44bf2a7a714971a0835362094e9452c` | `UP_TO_DATE`; non-mutating; full selected tree byte-identical |

The pre-change released matrix remains evidence: 2.7.35/2.7.36 to 2.7.37
were unsupported, exact-current 2.7.37 was `UP_TO_DATE`, and unsupported,
downgrade, schema-mismatch and foreign-artifact controls failed closed without
mutation.

## Preservation, recovery and security

All three completed updates used one atomic qualified same-schema copy and
ended with schema 39, `PRAGMA integrity_check=ok` and an empty foreign-key
check. Runtime ID, installation ID, runtime marker, terminal Mission sentinel,
allocation, peer configuration/digest and credential reference were preserved.
The credential reference remained unverified synthetic configuration; no auth
state was promoted and no credential material was read.

Same-operation lost-response replay returned exactly the same JSON, receipt
bytes and operation bytes with one backup and one candidate slot. Stale
assessment failed before operation state or staging. Holding the canonical
Server-writer lease rejected the controller before operation state or staging;
the controller shares the established ordered writer locks with
preserve/restore/purge. A separate sibling installation remained byte-identical.

Source and installed-artifact qualification cover unsupported/downgrade/schema
and foreign-artifact cases; changed request/source/target/controller/receipt;
hardlink, permissive root/file/directory, symlink, special entry, owner drift,
recreated/foreign root and tampering. Controlled phase interruption/resume is
qualified in source tests. Real terminal replay is qualified above. Abrupt
process kill and physical host reboot were not performed and are not claimed.

## Failure history and protected delivery

The audit first proved that released 2.7.35/2.7.36 could not reach 2.7.37.
Protected delivery then found and closed four further gaps through real
published-artifact execution: missing Server-writer lease, canonical empty
fresh-dispatcher handling, stale `forge_version` inventory after same-schema
activation, and SQLite SHM mutation during nominally read-only assessment.

| PR | Protected merge | Purpose |
| --- | --- | --- |
| #194 | `af323ce7be3e7bf8465887d9b17eec5de1ccb33d` | direct transitions, assessment/controller binding and base qualification |
| #195 | `0a3d6e35b01da93bb5a674ae7795558655c16c7d` | normal 2.7.38 version preparation and release source |
| #196 | `e0b9a6d9ab797e675d3acbd3fde8736d9d21ed97` | canonical Server-writer lease |
| #197 | `cd321c896ee51e9a53bbaf2e043c1fc5cb46a5cb` | fresh empty dispatcher as canonical not-started/IDLE |
| #198 | `b7a454a64a707eaa7ccb1dfdb1f418bdf9169a83` | atomic exact target inventory advance |
| #199 | `bf7ae99c67e32fd2047965f19ece30a35071e868` | byte-for-byte read-only assessment snapshot |

Every source PR passed canonical version validation, Forge CI, Python analysis,
CodeQL and TDE before merge. Final source validation ran 1003 tests with one
release-only skip; changed controller coverage was 1271/1578 executable lines,
80.545627%, strictly above 80.2%. Product version remained 2.7.38 after the
release; no additional artifact release was required for the separately bound
external controller.

## Consumer handoff

LANE_1 may select only one of the three old bindings above, final controller
source/digest, and the exact 2.7.38 release source/wheel/receipt. It must consume
the read-only assessment digest and pass the same digest into mutation. The
same operation ID may be replayed after an ambiguous response; a changed
request, stale assessment, changed tree or foreign artifact must stop.

This producer qualification does not claim installer composition, signing,
service stop/start, live production or fresh-Mac acceptance. Those remain
LANE_1-owned.
