# r29 producer pairing lifecycle evidence

**Assignment:** `L2-PRODUCER-STANDALONE-AND-PAIRING-LIFECYCLE-V1-20260930`  
**Status:** qualified producer subset on exact published bytes. Full installer
acceptance remains with LANE_1.

## Exact starting baselines

| Product | Published version | Release source | Wheel SHA-256 |
| --- | --- | --- | --- |
| Forge | 2.7.38 | `0a3d6e35b01da93bb5a674ae7795558655c16c7d` | `e9a5609969b8e49476f44e99a6cf72b8edf60280a77e010effe55a3bc1b33af8` |
| Engineering Platform | 2.3.106 | `7b99b578153ae5d72372a09db194306b49ec9f9c` | `9d25a53d75b61d43d665d9f8290a968dc3e63d12d2037eae8ef31ee810eb6694` |

The frozen Forge wheel's authenticated `GET /v1/readiness` returns HTTP 503
for a not-configured EP peer. Its provider also needs its own qualification;
that baseline readback alone does not prove provider health. The new route is
explicit and leaves the old peer-required endpoint strict.

## Candidate evidence and limits

The isolated Forge source suite includes exact detach request/generation
guards, `PREPARED` recovery, a real disposable child-process SIGKILL after
the durable `PREPARED` commit, completed receipt replay, stale operation and
wrong-instance rejection, malformed/symlink receipt and marker rejection,
active or blocked-work refusal, sibling isolation, schema-39-to-40 peer and
identity preservation, legacy status retention, runtime/HTTP contract tests,
and existing preserve/purge/restore/update/security regressions.

The reusable `scripts/qualification/qualify_pairing_published_wheels.py`
requires a fresh venv installed from two exact SHA-bound wheels. It verifies
each distribution's installed `direct_url.json` origin and runs two disposable
product roots with a real EP Server loopback HTTP boundary and Forge's
packaged CLI/API/library. It covers initially unpaired standalone readiness,
real paired preflight, OLD revocation and rejection, valid wrong-consumer
rejection, paired PRESERVE→RESTORE, exact detach, guarded NEW configuration,
lost configure-response replay, new authenticated preflight and strict paired
readiness. A second Forge instance's database remains byte-identical. The
separate EP 2.3.106 conformance test covers same-project registration replay
and lost credential-issue response recovery without retaining a second active
grant.

The only HTTP test adapter supplies the ephemeral EP bearer at Forge's secure
store boundary in memory. EP verification, topology, consumer scope and HTTP
transport are real. Provider readiness and scheduler state are synthetic in
the focused pairing HTTP matrix; it makes no live provider login, Keychain,
LaunchDaemon, signer, host reboot, service-account or complete installer claim.
The controlled detach interruption includes one real SIGKILL after `PREPARED`;
other interruption edges are fault injection and replay tests. No physical
power-loss test was run.

## Protected delivery and published artifacts

Forge [PR #205](https://github.com/pcvantol/forge/pull/205) merged at
`ebc43dc12da27353f85c991a26da9852aa790f05`, after source validation,
CodeQL and TDE observation passed. EP conformance [PR #328](https://github.com/pcvantol/engineering-platform/pull/328)
merged at `1f1fe0799eec1525ba113657e4c0bdc82b573e29`; no EP runtime change or
EP release was needed. The normal Forge production [release run 36767110542](https://github.com/pcvantol/forge/actions/runs/36767110542)
completed every job, including registry readback and `record-release-complete`.
The public [forge-v2.7.39 release](https://github.com/pcvantol/forge/releases/tag/forge-v2.7.39)
is non-draft and targets that exact protected Forge commit.

| Published item | Independently downloaded SHA-256 |
| --- | --- |
| PyPI `forge_autonomy-2.7.39-py3-none-any.whl` | `b62bf5f7a1d937f5224ef941a3dea3e961d28b67d9206fd89b644153aea502f1` |
| PyPI `forge_autonomy-2.7.39.tar.gz` | `562b0007388acd221bc486b5d111b0a5682e0af8d96719e20074f3f1ab7343d7` |
| GitHub `forge-release-complete-2.7.39-ebc43dc12da27353f85c991a26da9852aa790f05.json` | `078a9f09f048cbd1fd36c4d5f83a5739dfeb3c3a546ba94bb1148596135ba15f` |

The independently downloaded receipt states `RELEASE_COMPLETE`, exact source
`ebc43dc12da27353f85c991a26da9852aa790f05`, both matching PyPI artifact
digests, publication readback `PASS` and cleanup `COMPLETE`. The installed
wheel's direct URL and digest were verified in a fresh Python 3.14 venv.

## Published-byte product and update readback

`scripts/qualification/qualify_pairing_published_wheels.py` on that exact
Forge wheel and the published EP 2.3.106 wheel passed standalone→pair→old
revoke→detach→replacement, authenticated exact-new-consumer HTTP readiness,
old and valid-foreign credential rejection, lost configure-response replay,
paired PRESERVE→RESTORE, both product-instance identities and byte-identical
sibling Forge database. The installed Server Runtime qualification on the
same published Forge wheel passed its lifecycle, multi-instance, HTTP
simulator, filesystem-security and clean-SIGTERM cells without contacting a
production EP or provider.

The external owning updater is separately bound to protected source
`ebc43dc12da27353f85c991a26da9852aa790f05`, file
`scripts/update_installed_forge.py` SHA-256
`84bac133849c539a2bfae662234be93c3cd6583e841cae34eb27f3b21728fb87`.
The repeatable `scripts/qualification/qualify_2738_to_2739_published_update.py`
used that exact controller, both published Forge wheels and the terminal
receipt. Its two disposable cells, paired and never-paired 2.7.38 instances,
each passed read-only `UPDATE_AVAILABLE` assessment, product-owned mutation to
schema 40, `COMPLETE` terminal replay, unchanged runtime/installation/peer
identity and unchanged sibling tree, plus database integrity and foreign-key
checks. The paired cell first completed the published 2.7.38 product's own
PRESERVE→RESTORE and verified its original receipt stayed byte-identical after
the update. The 2.7.38 source remains
`0a3d6e35b01da93bb5a674ae7795558655c16c7d` and its wheel digest is the
baseline above. No schema-39 database was silently opened by a 2.7.39 peer
command before the installed update.

Historical 2.7.38 PRESERVE receipts retain their identity and are consumed
first by the exact 2.7.38 RESTORE route, then by the declared installed update.
They are never rewritten as 2.7.39 evidence. The published-wheel pairing
matrix separately exercised paired PRESERVE→RESTORE on 2.7.39 before replacing
the revoked consumer.

The [owning contract](../architecture/FORGE_EP_STANDALONE_AND_PAIRING_LIFECYCLE_V1.md)
defines the consumer commands, states and recovery order. EP's existing-route
conformance is delivered in
[EP PR #328](https://github.com/pcvantol/engineering-platform/pull/328); no EP
runtime release is required for that demonstrated route.
