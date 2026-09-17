# Living Mission Graph and cross-repository Engineering Action DAG

**Status:** canonical target architecture. The bounded serial dynamic-derivation
and evidence-derived completion slice is source-delivered and deterministically
qualified; live Forge→EP and cross-repository qualifications remain separately
governed and unexecuted.

## Parallel-runtime refinement — 2026-09-17

The [Parallel Action runtime V1 design](PARALLEL_ACTION_RUNTIME_V1.md),
[owning roadmap](../roadmap/PARALLEL_ACTION_RUNTIME_V1.md),
[documentary DAG](../roadmap/parallel-action-runtime-v1.json) and
[shared qualification catalogue](PARALLEL_ACTION_QUALIFICATION_V1.md)
make the existing second Runtime milestone implementable: bounded planner
fan-out, durable per-Action targets/state, asynchronous dispatch, incremental
fan-in and actual EP execution overlap. All added PA implementation nodes remain
PLANNED. This NO_BUMP design does not change the current serial Mission-3 proof,
reset-maintenance work, active policy, credentials or installed runtime.

## Purpose

An approved Mission is the stable human-governed boundary. Forge owns the dynamic engineering plan inside that boundary. It must be able to derive the first Engineering Action, reconcile real execution evidence, change the remaining plan, derive additional Actions, and stop only when Mission completion is proven by evidence.

The active plan is the **Living Mission Graph**: a mutable planning graph of current Intents and not-yet-completed Engineering Actions. It is not the Roadmap DAG and it is not an EP scheduling queue.

```text
approved Mission
    -> Forge plan / Living Mission Graph
    -> materialized Engineering Action
    -> EP execution
    -> terminal receipt / repository evidence / findings
    -> Forge reconcile + Project Context refresh
    -> Mission completion evaluation
       -> complete, or
       -> replan / add, split, supersede, reorder or retire remaining work
    -> next eligible Action(s)
```

`OWNER_DEFINES_MISSION_BOUNDARY = TRUE`
`FORGE_DEFINES_AND_REDEFINES_ACTION_PLAN = TRUE`
`EP_EXECUTES_ACTIONS = TRUE`
`EVIDENCE_DRIVES_REPLAN = TRUE`

## Dynamic inner Mission loop

Forge must not require the owner to predeclare Action A, B, C or relay execution results between them. A Mission can begin with only its objective, constraints and success criteria. Forge may forecast likely work, but forecast work is not immutable backlog.

After every material terminal result Forge:

1. verifies and reconciles the exact EP result;
2. refreshes repository/project truth and relevant quality findings;
3. evaluates the Mission success criteria and unresolved constraints;
4. revises the Living Mission Graph when evidence changes the required work;
5. materializes only bounded eligible Actions;
6. continues without another owner message while remaining inside the approved Mission boundary.

A result may therefore cause `A -> B -> B2 -> C`, even when `B2` was not known before B executed. A forecast successor may also disappear when the new evidence proves it unnecessary.

A change to the Mission objective, approved scope, constitutional constraints, destructive authority or security authority remains a governance change rather than ordinary replanning.

## Engineering Action target and immutability

The normal V1 planning unit is **one Engineering Action targeting one repository**. The Action snapshot carries the repository identity and bounded write scope required by EP admission. Cross-repository outcomes are normally decomposed into separate Actions connected by dependency edges rather than one opaque multi-repository prompt.

Conceptually an Action snapshot must be able to carry:

```text
EngineeringAction
  id / revision
  mission_id / mission_revision
  intent_id / intent_revision
  target_repository_id
  write_scope
  objective
  acceptance / expected evidence
  depends_on[]
  dependency evidence requirements
```

A planned node may change before materialization. Once an Action is materialized for submission, its execution identity, target, objective, dependency snapshot and expected evidence are immutable. New evidence creates a new/revised successor Action or graph edge; Forge never rewrites historical execution identity.

A newly derived successor is not Mission work merely because its repository,
scope or write scope is allowed. Before materialization it must bind to at
least one currently unsatisfied approved Mission criterion, or to a technical
blocker directly caused by current Mission Action history and supported by
current causal evidence. The append-only derivation record retains that exact
criterion/blocker, planning-snapshot, evidence and objective binding. Unknown,
already-proven, stale, optional or Mission-expanding work fails closed and is
not released as an executable node.

`UNMATERIALIZED_PLAN_MAY_CHANGE = TRUE`
`MATERIALIZED_ACTION_IS_IMMUTABLE = TRUE`

## Hard dependencies

`depends_on` means a **hard logical execution dependency**: the successor is not eligible for dispatch until the required predecessor completion evidence exists and satisfies the dependency requirement.

Hard dependencies are planned by Forge. EP may durably persist and enforce the supplied dependency snapshot, but EP must not invent product or engineering dependencies.

A hard edge may exist within one repository or across repositories. Cross-repository edges are first-class because product delivery often spans independently owned repositories.

Do not overload `depends_on` with scheduling preference, forecast likelihood, shared-repository exclusion or Agent capacity. Those are separate concerns.

## Logical dependency, resource exclusion and capacity are separate

Three independent mechanisms determine whether work can run now:

1. **Logical dependency — Forge-owned plan.** Example: final installer manifest depends on published qualified EP artifacts.
2. **Repository/resource exclusion — EP-owned execution safety.** Independent Actions may still serialize when they require the same exclusive repository lease or other execution resource.
3. **Agent/provider capacity — EP-owned admission/placement.** Independent, lock-compatible Actions may still wait when no qualified execution capacity is available.

Consequently two Actions in different repositories with no dependency should be eligible for parallel execution when EP has safe capacity. Different repositories do not imply independence, and the same project does not imply serialization.

## Evidence-gated cross-repository unlock

A dependency can require a concrete producer artifact rather than merely a predecessor status flag. The predecessor Action DoD defines the evidence required to unlock the successor.

Example Mission: **make Engineering Platform Execution Agents production-ready and installable through Forge Platform**.

```text
EP-A1 Agent contract
   |\
   | +--> EP-A2 Agent runtime -------------------+
   |                                            |
   +----> EP-A3 Server <-> Agent protocol ------+--> EP-A4 qualification/package
                                                     |
                                                     v
                                             EP-A5 publish qualified artifacts
                                             server wheel + agent wheel
                                             source revision + artifact SHA-256
                                                     |
                                                     +-------------------------+
                                                                               |
FP-A1 installer Agent role/model --> FP-A2 installer support -----------------+--> FP-A3 final component manifest
                                                                                     |
                                                                                     v
                                                                              FP-A4 installer qualification
```

`EP-A2/EP-A3` work and `FP-A1/FP-A2` work can advance in parallel when their own dependencies and EP execution resources permit. `FP-A3` has hard dependencies on both the installer implementation and `EP-A5`. It cannot finalize the component manifest until qualified artifacts actually exist.

The artifact-producing predecessor should expose at least the installable artifact identity, artifact digest, source revision and relevant qualification/provenance references. A source commit alone is not sufficient proof of the bytes the installer will install.

## Dispatch and EP enforcement boundary

Forge determines which Actions exist, their repository target and their `depends_on` graph. Forge should normally submit only currently eligible Actions. The immutable submission also carries enough predecessor identity/evidence requirements for EP to fail closed if an ineligible successor is presented.

EP owns admission, repository leases, execution capacity, run state, validation/review/repair and terminal evidence. A dependency check by EP enforces the producer-supplied plan; it does not transfer planning authority to EP.

```text
Forge Living Mission Graph
  -> eligible Action snapshot + dependency requirements
  -> EP admission
       hard predecessor evidence satisfied?
       repository/resource lease available?
       qualified Agent/provider capacity available?
  -> dispatch or durable wait
```

## Parallel release from one Mission

The target Runtime releases a **bounded eligible frontier** from the same Mission,
not an enforced singleton or the entire backlog. Approved release/concurrency
policy and peer capability limits constrain how many independent immutable Actions
are offered. EP separately decides actual resource/capacity admission. Waiting due
to a limit does not create a false logical dependency.

The current Bootstrap Mission Scheduler's single in-flight Action rule and
`_OneActionProvider` are bootstrap implementation limits, not target invariants.
The loop-wide repository binding must become a verified per-Action mapping before
cross-target release; two repositories require real scope, not a broader prompt.

The delivered serial source slice retains that bootstrap limit. For an approved
provider-derived scope with no Action definitions, it derives and validates an
initial Action, reconciles canonical terminal evidence, refreshes current
planning evidence, and may append a validated successor. Derivation lineage and
completed materialized Actions survive a normal durable runtime reopen.

The parallel refinement requires durable per-Action execution/correlation slots,
per-repository Truth, graph revision guards and in-flight contribution reservations.
Locks protect short state transitions, not full provider or HTTP waits. Process
each result independently: after A succeeds, C depending only on A may start while
B still runs. Only a real multi-parent dependency waits for both A and B. Do not
invent a global wave barrier. Materialized siblings remain immutable during replan;
duplicate/lost/late results cannot produce new submissions or overwrite another
slot. See [the detailed model and recovery contract](PARALLEL_ACTION_RUNTIME_V1.md).

An Engineering Action is not one subagent. Provider-internal delegation stays
under the owning Action's scope; it neither replaces cross-repository Action
admission nor requires a new full delivery cycle for every helper. Native nested
implementation agents and same-repository parallel writers remain separately
qualified, not implied by this target.

## Mission completion

Mission completion is not defined as “all Actions from the initial plan are COMPLETE”. The initial plan is provisional.

After reconciliation Forge must prove that the approved Mission success criteria are satisfied from current evidence and that no unresolved required work remains inside the Mission boundary. Only then may it mark the Mission complete.

A complete set of initially forecast Actions is insufficient if evidence exposes new required work. Conversely, Forge must not execute forecast work that is no longer necessary merely because it once existed in the graph.

`MISSION_COMPLETION_IS_EVIDENCE_DERIVED = TRUE`
`INITIAL_ACTION_LIST_IS_NOT_COMPLETION_AUTHORITY = TRUE`

The delivered evaluator identifies every approved criterion and binds it to an
exact current Repository Truth snapshot plus canonical correlated terminal Host
evidence. Unknown or absent evidence remains unsatisfied; neither provider prose
nor an Execution Host completion assertion has planning or completion authority.

For multi-in-flight operation, success evaluation also requires that all admitted
side effects are accounted for. No Mission COMPLETE while a sibling can still
write, cancellation is unacknowledged or an accepted request is uncertain.
A failed predecessor blocks its dependants without rewriting unrelated successes;
continuation/cancellation of independent siblings follows actual impact and policy.

## Qualification sequence

Two separate real-world qualifications are required.

### Dynamic inner-loop canary

The repository-level deterministic harness proves the Forge-owned source
semantics below with a fake derivation provider and fake Host. The real canary
is still unexecuted and may be claimed only after configuration, governance,
installed producer capability, and actual terminal evidence exist.

Input is one approved Mission, not a predeclared A/B script. Qualification proves:

```text
FORGE_DERIVES_ACTION_A = TRUE
ACTION_A_EXECUTED_BY_EP = TRUE
FORGE_RECONCILES_A_AND_REPLANS = TRUE
FORGE_DERIVES_SUCCESSOR_WITHOUT_OWNER_MESSAGE = TRUE
SUCCESSOR_MAY_DIFFER_FROM_INITIAL_FORECAST = TRUE
FORGE_CAN_INSERT_NEW_ACTION_AFTER_NEW_EVIDENCE = TRUE
MISSION_COMPLETION_DECIDED_FROM_EVIDENCE = TRUE
OWNER_IS_NOT_ACTION_MESSAGE_BUS = TRUE
```

### Cross-repository DAG canary

A later Mission spans at least two repositories and proves:

```text
FORGE_DERIVES_CROSS_REPO_DEPENDENCIES = TRUE
INDEPENDENT_REPOSITORIES_BECOME_CONCURRENTLY_ELIGIBLE = TRUE
INDEPENDENT_ACTION_EXECUTION_INTERVALS_OVERLAP = TRUE
PER_ACTION_TARGET_STATE_AND_EVIDENCE_ISOLATED = TRUE
DEPENDENT_ACTION_NEVER_EXECUTES_EARLY = TRUE
ARTIFACT_EVIDENCE_UNLOCKS_SUCCESSOR = TRUE
INCREMENTAL_REPLAN_WITHOUT_UNRELATED_SIBLING_BARRIER = TRUE
EP_RESOURCE_POLICY_REMAINS_SEPARATE_FROM_FORGE_PLAN = TRUE
MISSION_REPLANS_AFTER_PARALLEL_RESULTS = TRUE
```

The Execution Agent + Forge Platform installer role remains a suitable larger
dogfood Mission once its own prerequisites exist. The first bounded qualification
may instead use two already-authorized repositories on one host; no Agent-fleet
or UI dependency is added merely to prove concurrency. It must prove actual EP
execution overlap, independent per-Action recovery, incremental fan-in, complete
required assurance and honest time/usage accounting. See PA-01..PA-26 in the
[qualification catalogue](PARALLEL_ACTION_QUALIFICATION_V1.md). Eligibility alone
is no longer sufficient closure evidence for the parallel-runtime milestone.
