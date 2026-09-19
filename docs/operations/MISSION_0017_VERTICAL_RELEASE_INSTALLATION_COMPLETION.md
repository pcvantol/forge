# MISSION-0017 vertical release and installed delivery

Status: released and installed by 2026-09-20. This public projection
does not replace the
protected local evidence, original run records, backups or registry receipts.

Local installation identities, roots, operational receipt paths and backup
digests are represented by stable aliases. Public PR, source, release and
distribution identities remain exact.

## Isolated live Mission qualification

`MISSION-0017` ran once in the isolated `pcvantol/forge-mission-qualification`
project. Forge completed the Mission after two separately persisted Actions;
the second planner invocation followed assessment of the first Action's
terminal delivery evidence. Both EP runs were `COMPLETE / QUALIFIED`, required
validation passed and neither reported a repair round. The terminal target
commit was `0c049b67aedb97497d4e9ae1a8dc0e1801acf32a`.

| Action evidence | EP run | Target PRs |
| --- | --- | --- |
| Select transformed names after an optional prefix | `inbox-6e5a40147c3e49b982377aa81e5ff664` | [#28](https://github.com/pcvantol/forge-mission-qualification/pull/28), [#29](https://github.com/pcvantol/forge-mission-qualification/pull/29), [#30](https://github.com/pcvantol/forge-mission-qualification/pull/30) |
| Limit selected records before grouping | `inbox-3fdf7edc094242d99dd613b41d52b33e` | [#31](https://github.com/pcvantol/forge-mission-qualification/pull/31), [#32](https://github.com/pcvantol/forge-mission-qualification/pull/32), [#33](https://github.com/pcvantol/forge-mission-qualification/pull/33) |

The qualification used Forge 2.7.26 from source
`7caa4fd60dacdd5df5736237c6d0475391b496bf`, storage schema 39, and EP
2.3.87 from source `09f13cbff33295bb29c0464435e9b01430643c59`, server
schema 70 and engineering-storage schema 45. The isolated target commit is a
fourth identity: it is neither product source nor product artifact. Earlier
qualification attempts retain their original outcomes; no attempt count is
inferred from the Mission number.

## Protected product delivery and exact distribution binding

Forge's implementation [PR #155](https://github.com/pcvantol/forge/pull/155)
merged as `d833b612c3d968b05a7747f91ae5ef893e4ecdd1`. The production
Forge 2.7.26 wheel built from that protected commit has a different archive
digest from the isolated qualification wheel, while all 170 installed product
members are byte-identical. The external update controller is not part of the
product wheel. Its corrections merged separately in
[#156](https://github.com/pcvantol/forge/pull/156) at
`9ede7bbc92b78bfbb9593e2513ca27ad93ee6b84` and
[#157](https://github.com/pcvantol/forge/pull/157) at
`fef565de08f28dcfd0241520f64d55d22ee70188`.

EP [PR #279](https://github.com/pcvantol/engineering-platform/pull/279)
merged at `6ceaf67b0113b237e8645422795ecf05741944dc`; the subsequent
protected EP deliveries through #286 produced the 2.3.87 source above. Its
qualified and published wheels have different archive digests but all 159
installed product members are byte-identical. The supplemental reset repair
[#287](https://github.com/pcvantol/engineering-platform/pull/287) merged
as `3785de7c10f4468624468f72081ff9f984291551` and introduced EP 2.3.88
with server schema 71. MISSION-0017 is **not** retroactively relabeled as a
2.3.88 live qualification. The 2.3.88 delta is the forward-only reset-fence
migration and canonical version projections; the Mission planning, evidence,
delegation and merge behavior used by MISSION-0017 is unchanged.

| Product distribution | Isolated qualification SHA-256 | Published SHA-256 | Published sdist SHA-256 |
| --- | --- | --- | --- |
| `forge_autonomy-2.7.26-py3-none-any.whl` | `1dc152a7f521281f64e474c1e6814d3436d66d8366b5572cc1bf0fd452d287f1` | `cf2057a1fa5b4687d4d41db10ca6e4b6755f68eafa8304296617f8d1a865e633` | `c66b11bbcec8894b229b6c586b95c049f0b42a2267299965eaeba0ecc55757bd` |
| `engineering_platform-2.3.87-py3-none-any.whl` | `257d95ddb8197d920e268e18a97916c6ceffb7cf3a79f8feaa3935ac44c555e0` | `9407a6f2a15a804183b1b9853d34db69e95fa30967636a5e3f1e6046627a79fc` | `0faf5763ed7963331949aa6356202dbf1e095465d179aa3ce36aee13c9c84c97` |
| `engineering_platform-2.3.88-py3-none-any.whl` | Not used in MISSION-0017 | `cf5e72a37f7acb5e7ba9473ef4f135a7ba95fa0f04ba8a3f1314e52c45edd68b` | `528cf11d7a404c218c49e699d120e94b79600e2b801254bd34d102cb0f79c5ea` |

The Forge [release operation](https://github.com/pcvantol/forge/actions/runs/35469882484)
and EP 2.3.87 [release operation](https://github.com/pcvantol/engineering-platform/actions/runs/35469879923)
both reached `RELEASE_COMPLETE`. Their original PyPI distributions were
downloaded and checked against those registry digests. The released tags are
[`forge-v2.7.26`](https://github.com/pcvantol/forge/releases/tag/forge-v2.7.26)
and [`engineering-platform-v2.3.87`](https://github.com/pcvantol/engineering-platform/releases/tag/engineering-platform-v2.3.87).
The supplemental EP 2.3.88
[release operation](https://github.com/pcvantol/engineering-platform/actions/runs/35472491395)
also reached `RELEASE_COMPLETE`, including PyPI download, checksum readback,
fresh-wheel qualification and cleanup. Its
[`engineering-platform-v2.3.88`](https://github.com/pcvantol/engineering-platform/releases/tag/engineering-platform-v2.3.88)
release targets exactly `3785de7c10f4468624468f72081ff9f984291551`.
The published EP 2.3.87 and 2.3.88 wheels have the same 159 product member
paths; only the canonical version/configuration projections,
`central_operational_reset.py` and `server.py` differ.

The terminal release-receipt digests are `sha256:9135d30bd3a66408946be85c99001ee996113a5ecff636daa32adc08e8292e7a`
for Forge 2.7.26,
`sha256:a0bebb7a923a1604031b31aff9db9037bb250a0a7279df16f83352282bd9871d`
for EP 2.3.87 and
`sha256:1ea027a90f6850adf00356d9aa5b69a1c3bdb1d7c02abd16da28842c9e63a7f1`
for EP 2.3.88. Each receipt binds its own protected product source, wheel,
sdist, registry readback and terminal cleanup state.

The protected PR gates passed on the final heads: Forge test/static validation,
CodeQL, Python analysis and version-source control; EP production validation,
coverage, dashboard/browser checks, CodeQL, dependency/static security,
trusted delivery and version-source control. The EP 2.3.88 source suite passed
2,009 tests with two skips. Its published wheel passed 167 installed server,
migration and operational-reset coordination regressions on isolated roots.
The latter cover revalidation, both apply orders, verification,
resume authorization, both finishes and interruption recovery. These are
automated quality and security controls; no separate human reviewer approval
is claimed.

## CENTRAL installation and reset boundary

The owning EP update operation `<EP_UPDATE_A>` installed 2.3.87 from the
published wheel: `COMPLETE`, with an operation-owned backup, schema 68→70,
active service readback, the unchanged `<EP_INSTALLATION_A>` identity and
preserved project, repository and credential bindings. A subsequent read-only
reset preview exposed three missing schema-70 writer fences on
`ep_installations`. The active-writer blocker was expected; the missing fences
were a separate defect. Protected PR #287 and the supplemental tests repair
that exact defect without executing a production reset.

The owning Forge update operation `<FORGE_UPDATE_A>` installed 2.7.26 from
the original published wheel and release receipt: `COMPLETE`, with a retained
backup, unchanged schema 39, unchanged `<FORGE_INSTALLATION_A>` and
`<FORGE_RUNTIME_A>` identities, preserved credentials and no Mission or
service start. Its first pre-adoption attempt safely fenced the runtime after
an internal resolver was selected. The same durable operation was reconciled
after protected PR #157; its terminal receipt retains both the failure and
recovery. No link or database was repaired by hand.

The subsequent owning EP update operation `<EP_UPDATE_B>` installed the
published 2.3.88 wheel: `COMPLETE`, with its own backup, schema 70→71,
the same `<EP_INSTALLATION_A>` identity, active server and healthy status.
Its read-only CENTRAL reset preview reports only `TARGET_WRITER_ACTIVE` while
the normal service is running. It no longer reports
`WRITER_FENCE_INCOMPLETE`. A separate installed-wheel regression used the
published artifact and isolated data roots; it did not touch CENTRAL.

A fresh installed Forge command reports 2.7.26 and schema 39. Authenticated
Forge→EP preflight reports `PASS` against installed EP 2.3.88, including
producer readback 1.2, terminal evidence 1.4, validation controls 1.0/1.1,
delivery-revision validation 1.0 and bounded merge delegation 1.0. The
installed Forge reset preview is read-only `READY`; neither reset protocol
was applied to CENTRAL.

## Next production Mission boundary

The installed command surface includes `forge mission inspect --input`,
`approve-business --input`, `approve-architecture --input`, `admit --input`,
`run --mission-id --repository-truth`, and read-only `status --mission-id`.
The input is the canonical candidate, Mission, planning and decision-reference
document; the runner obtains fresh default-branch Repository Truth and checks
the EP grant before new work. A concrete candidate objective for later Business
and Architecture refinement is a read-only installed Mission evidence ledger
that ties each Action to its EP run, accepted delivery revision, merged PR and
criterion-control result, including continuation after a partial first
Action. Its consumer is the operator checking the Mission result; acceptance
would require exact-revision positive and stale-evidence negative controls.
This is an input proposal, not an Action list or an approved Mission. Forge
must later derive its own Action sequence.

The successful autonomous assurance and merge authority were scoped to
`pcvantol/forge-mission-qualification`. CENTRAL currently has the Forge
repository registered, but no active merge delegation for it. Its protected
`main` requires a PR and current passing checks. Mission 3 therefore needs a
new owner-selected effective assurance profile and a bounded grant for its
actual target; the test-project profile cannot be carried over. The earlier
C01–C20 and Mission-3 preflight rejection are unchanged.

Before any later T0, the owner must separately coordinate clean-CENTRAL
read-only previews, quiescence, approved backups and both owning reset
protocols through final verification and resume authorization; then fresh
Repository Truth, Business and Architecture decisions, applicable controls,
target policy and EP authority must be checked. This record authorizes none
of those future production mutations.

`PRODUCTION_CENTRAL_RESET = NIET_UITGEVOERD`;
`PRODUCTION_MISSION_3 = NIET_GESTART`;
`HISTORICAL_MISSION_3_ACCEPTANCE = NIET_GEHAALD_ONGEWIJZIGD`.

## Scoped resource handoff

The Forge and EP source PRs, release operations and owning CENTRAL update
operations cited above are terminal. Their original receipts and the two
MISSION-0017 run records remain available to the owning Architecture lanes
#141 and #142 through the protected local evidence and the public source,
release and target PR references in this record. The qualification target,
earlier attempt history and original local checkouts remain intact. This
handoff does not claim machine-wide quiescence or close either Architecture
assignment hold on the architects' behalf. No additional Mission, release,
update or reset operation is reserved by this completion record.
