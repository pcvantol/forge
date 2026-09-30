# r29 producer pairing lifecycle evidence

**Assignment:** `L2-PRODUCER-STANDALONE-AND-PAIRING-LIFECYCLE-V1-20260930`  
**Status:** source/candidate qualification in progress; Forge release and final
published-byte readback remain pending in this record.

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

## Release and consumer evidence to append

The protected Forge product source/merge SHA, separately protected updater
source SHA and SHA-256, `forge-v2.7.39` release run, published wheel/sdist and
`RELEASE_COMPLETE` receipt digests, independent download/readback, exact
2.7.38→2.7.39 controller assessment/mutation/replay/preservation, and final
published-wheel pairing rerun must be recorded here before this subset is
`QUALIFIED`. Historical 2.7.38 PRESERVE receipts retain their identity and
are consumed first by the exact 2.7.38 RESTORE route, then by the declared
installed update. They are never rewritten as 2.7.39 evidence.

The [owning contract](../architecture/FORGE_EP_STANDALONE_AND_PAIRING_LIFECYCLE_V1.md)
defines the consumer commands, states and recovery order. EP's existing-route
conformance is delivered in
[EP PR #328](https://github.com/pcvantol/engineering-platform/pull/328); no EP
runtime release is required for that demonstrated route.
