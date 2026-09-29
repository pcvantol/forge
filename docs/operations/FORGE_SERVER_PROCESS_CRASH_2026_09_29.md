# Forge Server installed process-crash qualification — 2026-09-29

## Scope and immutable inputs

This is the Forge-owned revision-26 process-crash subset of the existing
`FSH-SERVICES/server-only installed lifecycle` node. It extends the historical
[update compatibility completion](FORGE_SERVER_UPDATE_COMPATIBILITY_2026_09_28.md)
without changing that report or its revision-25 claims. The consuming boundary
is the exact protected controller plus the exact published Forge wheels and
release-complete receipt. Forge Platform installation, LaunchDaemon/account
changes, live credentials, physical reboot and power loss are outside this
qualification.

| Input | SHA-256 or source |
| --- | --- |
| Old 2.7.35 source / wheel | `ff4c0d45f51161376104250cd6efcfb6f045b8ac` / `79e7d7ef36da7c73c31981c39f4a1d90b0204965438779014fc129b79a2da2d0` |
| Old 2.7.36 source / wheel | `ed1e623ef3cedd8c4f720510e0052409b2d5ab1f` / `c10e9584649538f2f1547bb09fd3982cc3495dcf34ef807d66463661fdd5cd68` |
| Old 2.7.37 source / wheel | `a78523603d6ea081d07875ea6b557e73b5d4fe63` / `b8165e59935a1edf22590cf6378fab3c5b1014aded88eec1e1a294bfa1b94938` |
| Target 2.7.38 source / wheel | `0a3d6e35b01da93bb5a674ae7795558655c16c7d` / `e9a5609969b8e49476f44e99a6cf72b8edf60280a77e010effe55a3bc1b33af8` |
| Target release-complete receipt | `7f8f4646a369ea565e52f8420df665acb64d032e5004e1b45ef7dc8427548c49` |
| Original separately pinned controller | `bf7ae99c67e32fd2047965f19ece30a35071e868` / `9c43e1c3dcb411fb5f81a6a70d99b0c28b6bb2c79117f70703a50037e2e78183` |
| Corrected protected controller | `e4b99a249845a547fd6b8e7e11d22467b2d0886d` / `6a6bb4ade3db9d1e45ba64a0d928e91013109de3243e8e2dbccfaa04a7a455b4` |

The exact old/target packages were installed in isolated Python 3.14
installations without a checkout package import or `PYTHONPATH` fallback. The
controller was bound separately and rehashed. All provider references were
synthetic and non-secret.

## Phase-observed result

The preregistered matrix is in [Forge #142 revision 26](https://github.com/pcvantol/forge/issues/142#issuecomment-5884518247).
`qualify_installed_update_sigkill.py` creates a two-instance disposable
installation, obtains the exact read-only assessment, then observes the
controller's durable journal and independent slot, backup, resolver, inventory
and receipt effects. `qualify_installed_lifecycle_sigkill.py` enters the
published Forge 2.7.38 CLI. Both supervisors signal only their own verified
child process group, verify SIGKILL exit and that no owned mutator survives,
and retry the unchanged request from a new process. A missed boundary is
`NOT_HIT` or `UNPROVEN`.

The original separately pinned controller was hit at all ten durable update
phases for each old baseline: `PREPARED`, `STAGED`, `ADOPTED`, `BACKED_UP`,
`MIGRATION_QUALIFIED`, `FENCED`, `MIGRATED`, `ACTIVATING`, `ACTIVATED` and
`COMPLETE`. The phase hits recovered to one terminal receipt, one receipted
candidate slot and one backup, with unchanged sibling bytes, selected data
sentinel, runtime/installation identity, schema-39 SQLite integrity, and exact
terminal replay. The first exploratory `PREPARED` case lacked a sibling;
subsequent cases included it. Short-window misses were retained as misses
before observed hits, not promoted by elapsed time.

| Forge 2.7.38 lifecycle operation | Observed boundaries on published wheel |
| --- | --- |
| PRESERVE | `PREPARED`, `VERIFIED`, receipt before `COMPLETE`, `COMPLETE` |
| RESTORE | `PREPARED`, `VERIFIED`, receipt before `COMPLETE`, `COMPLETE` |
| PURGE | lifecycle `PREPARED`; uninstall `PREPARED`, `VERIFIED`, `DETACHED`, partial physical quarantine deletion, `REMOVED`, receipt before uninstall `COMPLETE`, uninstall `COMPLETE`; lifecycle tombstone before receipt, lifecycle receipt before `COMPLETE`, `COMPLETE` |

These lifecycle phase hits resumed with the same request/operation, preserved
sibling bytes and terminal replay, and retained the expected provider state.
Restore remained product admission only and `ready=false`; terminal purge
continued to reject restore. The latest reusable harnesses also exercise live
lock exclusion, changed request, foreign operation/instance status and lock
reacquisition after process death.

## Reproduced original-controller defect and bounded correction

The original controller has a separate `GAP_PROVEN` at the unreceipted
candidate-slot boundary, recorded before product editing in
[Forge #142](https://github.com/pcvantol/forge/issues/142#issuecomment-5885713217).
SIGKILL can leave the matching external claim and a partially written
`.forge-installation-staging.json.tmp-*` file under a slot whose final owner
and receipt are absent. The original controller rejects unchanged same-ID
recovery. The bounded controller correction recognizes only one private,
regular, exclusively linked temporary staging-owner file under the exact
matching claim. It quarantines that slot without reading/executing its
contents, then rebuilds from the unchanged pinned wheel. Foreign contents,
foreign claims, changed requests and unsafe links still fail closed. The
published Forge 2.7.38 wheel is unchanged. The correction was merged through
[PR #201](https://github.com/pcvantol/forge/pull/201) at the protected source
above. The final controller file was read back from that exact main commit and
hashed independently before the post-merge matrix.

The corrected protected controller passed **all 57 tracked update cells**:
the ten durable phases and nine physical side-effect boundaries (including
the focused temporary staging-owner boundary of the reproduced defect) for
each of the three old wheels. Every passing cell records exact controller
`SIGKILL` exit, no surviving owned descendant, observed durable phase/effect,
unchanged same-operation recovery to `COMPLETE`, identical terminal replay,
one receipted candidate slot and backup, selected data/config identity,
SQLite integrity and unchanged sibling bytes. The temporary staging-owner
boundary was actually hit and recovered on all three old baselines. The
post-merge runs retained nine `NOT_HIT` and three `UNPROVEN` attempts as
non-passing observations before successful hits; they are not counted as
coverage. The first post-merge `ADOPTED` sweep produced four further
`UNPROVEN` records because the harness expected the candidate resolver too
early. [PR #202](https://github.com/pcvantol/forge/pull/202) corrected that
readback to the actual legacy managed resolver at `ADOPTED`, and fresh
confirmed SIGKILL runs passed. The original 2.7.36 candidate-slot harness
error and database-swap miss remain historical non-passing attempts; subsequent
observed runs passed.

The Forge-owned process-crash subset is qualified against the corrected
protected controller and unchanged published wheels. It does not qualify the
broader host installer or the separate EP release, which the same revision-26
assignment delivers independently.

## Reproduction entrypoints

- `scripts/qualification/qualify_installed_update_sigkill.py` accepts an unused
  disposable root, published artifact directory, Python 3.14, old baseline,
  boundary and optional separately bound controller source/digest.
- `scripts/qualification/qualify_installed_lifecycle_sigkill.py` accepts an
  unused disposable root, exact published target wheel, Python 3.14,
  lifecycle operation and boundary. `UNINSTALL_PARTIAL_DELETE` requires enough
  disposable sentinel files to observe real partial deletion.

Evidence JSON is local and may contain implementation-level phase state.
Private host paths, PIDs, runtime identifiers and local digests are not
published in this canonical report. A process-crash PASS never implies
`POWER_LOSS_QUALIFIED`, `PHYSICAL_REBOOT_QUALIFIED` or
`INSTALLER_LIVE_QUALIFIED`.
