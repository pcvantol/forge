# Forge and four-repository consolidation / parking

Increment: `FOUR_REPO_CONSOLIDATION_PARKING_2026_09_10`. Reconciled
2026-09-10. Scoped under the
[canonical Forge roadmap](../../knowledge/bootstrap/10_ROADMAP.md).
[Documentary DAG](CONSOLIDATION_PARKING_2026_09_10_DAG.json).

## Decision and evidence boundary

Physical cleanup of all four local repositories is complete. This
documentation-only, `NO_BUMP` closure reconciles the existing consolidation
record and its documentary DAG with that evidence. It creates no product
implementation, test/workflow change, version, Mission, Action, runtime run,
review, qualification, installer, release, grant, credential or budget change.
`execution_authorized` remains `false`.

`USER_REPORTED` is the supplied physical cleanup and semantic-classification
evidence. `LOCAL_READBACK_VERIFIED` is direct Git checkout/worktree/branch
readback before each temporary documentation worktree was created.
`SOURCE_VERIFIED` is current GitHub main, ref and PR metadata. Each owner record
becomes canonical through its own protected documentation merge; transient
documentation branches are bookkeeping and are removed after merge.

## Forge physical closure

Pre-documentation Forge main was
`1ce16bf44585be7c8a84b8e3e54c9671ff83d0ab`, equal locally and on
`origin/main`. The baseline had one worktree, zero local feature branches and
zero unpreserved WIP.

| Node | Disposition | Closure / retained acceptance |
| --- | --- | --- |
| `F-LOCAL` | `RESOLVED` | One baseline worktree, zero local feature branches and zero unpreserved WIP |
| `F-PRODUCTIZATION` | `RESOLVED_SUPERSEDED_OR_PRESENT_ON_MAIN` | Every formerly preserved productization byte is present on main or superseded by a stronger main implementation; no unique residual remains |
| `F-ORCHESTRATOR` | `PARKED_REMOTE_UNREVIEWED_SOURCE` | Preserve `parking/2026-09-10/bootstrap-orchestrator-v0` at exact `40fa8b91bc7f0940dfa89ddbf43abb0adfd2e15e`; review scope/architecture before any future delivery |
| `F-RELEASE61` | `RESOLVED_NO_UNIQUE_RESIDUAL` | Closed-PR/local release evidence comparison left no unique residual |
| `F-CLEANUP` | `COMPLETE` | Authorized auxiliary worktree/branch cleanup completed; no active local feature lane remains |
| `F-LOCAL-MAIN` | `COMPLETE` | Baseline local main equals `origin/main`; final documentation delivery fast-forwards it again |
| `F-CONSUMER` | `PARKED` | Later prove the minimum compatible installed EP producer contract and exact durable evidence boundary |
| `F-DYNAMIC-SOURCE` | `SOURCE_DELIVERED_QUALIFIED` | Deterministic source qualification proves dynamic A, post-evidence B, restart preservation and evidence-derived per-criterion completion; no live EP or provider call |
| `F-E2E` | `PARKED_ORIGINAL_GOAL_NOT_EXECUTED` | Preserve the original first serial Mission loop below; configuration and governance remain open blockers |
| `F-LATER` | `PARKED` | Living Mission Graph, outer Mission loop, policy/progression, quality/knowledge learning, release management, Project Hygiene and optimization remain under their existing roadmaps |

The only remaining Forge cleanup-created product-source preservation is:

- ref: `parking/2026-09-10/bootstrap-orchestrator-v0`
- exact SHA: `40fa8b91bc7f0940dfa89ddbf43abb0adfd2e15e`
- disposition: `PARKED_REMOTE_UNREVIEWED_SOURCE`

Parking preserves bytes and provenance. It is not review, qualification,
delivery, product readiness or a dependency of the first Forge E2E.

The qualified `F-DYNAMIC-SOURCE` slice does not consume or qualify the parked
orchestrator source. It adds no endpoint, credential, Mission, grant, installed
runtime mutation, submission, provider generation, or canary execution.

## Original Forge E2E finish line retained exactly

```text
approved Mission
-> Forge derives Action A
-> EP executes A
-> Forge reconciles A
-> Forge restart/reopen from durable state
-> Forge derives successor B without owner relay
-> EP executes B
-> evidence-derived Mission COMPLETE
```

`F-E2E` depends locally only on `F-CONSUMER`; `F-CONSUMER` references only the
external EP capability node `E-PRODUCER`. The next readiness audit may determine
the actually required producer capability. This closure does **not** decide
that all of EP #175, all installer work or any broader EP roadmap is necessary.

In particular `F-E2E` has no dependency on `FP-INSTALLER`,
`W-CONTROL-PLANE`, `W-POLICY-HYGIENE`, `E-LATER`, subagent optimization, full
repository cleanup or bootstrap-orchestrator productization. No Workspace,
installer or subagent prerequisite is added.

## Owning peer records and remaining parked work

| Product | Owning documentation merge / physical closure | Remaining parked product points |
| --- | --- | --- |
| Forge Platform | `cb6a10a4ffca90e2b689af62349da2075fe47a77`; 1 worktree, 0 local feature branches, 0 unpreserved WIP; 37 delivered branches removed; 16 examined as 11 present on main, 5 superseded, 0 genuine residual, 0 unresolved | `FP-INSTALLER = PARKED_EXISTING_DAG_RETAINED`; `FP-LATER = PARKED`. [EP Server clean-install v1](https://github.com/pcvantol/forge-platform/blob/main/docs/roadmap/EP_SERVER_CLEAN_INSTALL_V1.md) remains the detailed installer DAG and is not copied or made an E2E predecessor |
| Workspace | `f220f61ce214416287d6c696d63642dbe0e7d2a7`; 1 worktree, 0 local feature branches, 0 unpreserved WIP; 8 auxiliary worktrees/branches removed | `W-CONTROL-PLANE`, `W-POLICY-HYGIENE` and `W-RELEASE` remain PARKED; Workspace is `NOT_ON_FIRST_FORGE_E2E_CRITICAL_PATH` |
| Engineering Platform | `264f2a2c12224c83b79919add782b93db74fcfac`; 1 worktree, 0 local feature branches, 0 stashes, 0 unpreserved WIP | #175 remains `OPEN / DRAFT / PARKED_NOT_QUALIFIED`; residual/source/provenance refs and all product decisions below remain parked |

Engineering Platform durable refs, fetched at full SHA:

| Ref | Exact SHA | Disposition |
| --- | --- | --- |
| `codex/ep-operational-installation-record-v1` | `4026ad1e671ad86d23dc9f8c56b7c4d5ddeb8819` | `PARKED_REMOTE` |
| `codex/ep-version-operation-reconciliation-v1` | `63bb8f14bbbd176109f4da1d20e2d96dc3081125` | `PARKED_REMOTE` |
| `parking/2026-09-10/ep-local-stash-residual` | `2982ff8ca42085e09eecf92de38e37bb71d64eec` | `PARKED_UNREVIEWED_SOURCE / NOT_QUALIFIED / NOT_DELIVERY` |
| `parking/2026-09-10/ep-release-2.3.1-prior-tip` | `3c934ee2b1c432463c140e7dc8cee007a8a46531` | `HISTORICAL_PROVENANCE_PRESERVED`; never an execution predecessor |
| `release-2.3.1` | `2ff4ee7441b8d8bade6c39e2c52dd62187af87ef` | `RELEASE_HISTORY` |

The owning [EP record](https://github.com/pcvantol/engineering-platform/blob/main/docs/development/CONSOLIDATION_PARKING_2026_09_10.md)
retains the exact acceptance criteria. It also preserves both mandatory
distinctions: #175 hosted/source tests are not durable current Managed lifecycle
qualification, and the existing draft is not proof that first draft creation
happened after assurance. No qualification or merge of #175 is authorized.

## Documentary DAG invariants

The four consolidation DAGs were validated together after the three peer
merges and against this Forge candidate:

- node IDs are unique in their intended `F-*`, `FP-*`, `W-*` and `E-*`
  namespaces;
- every local `depends_on` target resolves;
- every documented external owner/ref resolves;
- no dependency cycle is present;
- all four graphs retain `execution_authorized = false`; and
- the first Forge E2E predecessor exclusions above hold.

These graphs remain documentary overlays. They do not replace the existing
product DAGs, authorize execution, or turn priority/parking into dependency.

## Closure

The physical repository state and consolidation documentation now agree. All
known remaining source, product, installer, Workspace and optimization points
are explicitly parked or preserved. This is readiness to begin a separately
authorized Forge E2E capability-readiness audit only; the audit is not started
by this closure.
