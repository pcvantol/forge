# Autonomous Mission Execution Loop

## Purpose

The Execution Loop is Forge's composition root for one active,
Architecture-approved Mission. It continuously advances the Mission from
Intake through completion while retaining Business and Architecture governance,
Repository Truth, and Execution Host independence.

```text
Approved Mission Dispatcher → Mission State → AI Mission Planner
→ Engineering Intent → Engineering Action → Runtime Prompt Renderer
→ Execution Host Adapter → Execution Host → Execution Evidence
→ Mission State → Mission Planner → next Engineering Action
```

When a required capability is unavailable internally, this path inserts the
[Capability Delegation Framework](capability-delegation-framework.md) before
host dispatch. Forge pauses the Mission and records a delegation rather than
delegating Mission ownership.

The loop executes exactly one Engineering Action at a time. The Planner owns
the tactical plan; the Renderer owns prompt presentation; the Host owns
operational execution and evidence return. The loop never alters Mission
objectives, approves work, schedules a Mission, implements a Host, or activates
the next Mission.

## Durable Mission State

`MissionStateStore` is the canonical restart-safe runtime record. In addition
to the Mission, generated Intents and Actions, it persists current Intent and
Action, completed and remaining Action progress, correlation, current and
cumulative Execution Evidence, waiting reason, Repository Truth, per-criterion
completion evaluation, authorised recovery, append-only derivation provenance,
and append-only lifecycle history. Completed materialized Actions cannot be
dropped or rewritten by later planning.

The read-only `ExecutionLoopObservability` projection exposes current Mission,
Intent, Action, progress, host/lifecycle state, waiting reason and completion
percentage. It has no mutation or scheduling authority.

## Deterministic lifecycle

1. The Dispatcher supplies the one persisted active Mission.
2. For a newly admitted Mission, the loop obtains a complete, digest-pinned
   Planner input. Static scopes use `MissionPlanner.replan`. A scope explicitly
   marked `allow_provider_derivation` must have no preconfigured Actions and
   uses the injected `AIMissionPlanner` composition: provider output remains
   untrusted until the existing deterministic derivation validator has accepted
   it. The validated plan and its provenance are persisted before execution.
3. The Bootstrap Mission Runner releases one evidence-eligible Action, renders
   it through the injected renderer, and persists its exact Host request before
   dispatch.
4. Exact, correlated Host Evidence changes that Action only. Completed evidence
   is persisted, Repository Truth is refreshed, and the current Mission criteria
   are evaluated. Static planning preserves its unresolved Action identities;
   provider-derived planning may validate and append a newly required successor
   that was absent before the evidence. Incomplete host evidence leaves the
   Mission waiting without guessing.
5. Completion requires every materialized Action complete and every approved
   Mission criterion individually proven against current Repository Truth and
   canonical terminal Host evidence. Missing, stale, prose-only, or otherwise
   non-canonical evidence is unsatisfied. Finishing the current Action set alone
   cannot complete the Mission. The Dispatcher then runs
   the Architecture Review and Mission Recommendation hooks. It alone may
   subsequently evaluate its queue.

For identical Mission, Mission State, approved scope map, Repository Truth,
Planning Evidence and Host Evidence, the Planner and loop choose the same
Action order and persist equivalent state. Timestamps and host correlations are
operational evidence, not planning inputs.

The deterministic source qualification covers dynamic initial derivation,
evidence-triggered successor derivation, immutable completed history, durable
restart before the successor, and evidence-derived completion. It makes no
claim that the live Forge→EP canary has run.

## Dynamic-successor Mission containment

A provider-derived successor is executable only when its immutable derivation
record binds the Action to current Mission necessity. `UNPROVEN_MISSION_CRITERION`
names at least one approved criterion whose current Forge evaluation is
`UNSATISFIED`. `MISSION_CAUSED_BLOCKER` instead names the already materialized
Mission Action that caused a technical blocker and current causal Repository
Truth or Execution Evidence. Both classifications bind the exact planning
snapshot, triggering evidence references and the proposed Action objective.

Forge rejects the successor before materialization when the criterion is
unknown or already `PROVEN`, the binding or causal evidence is absent/stale,
the objective does not match the declared gap, or the blocker does not trace to
current Mission Action history. Existing scope, write-scope, human-gate and risk
validation remains cumulative. Work that is attractive but not required by an
unmet criterion or Mission-caused blocker receives the non-executing
`FOLLOW_UP_NOT_CURRENT_MISSION` disposition. Being inside the repository or
write scope is never sufficient Mission membership.

The binding cannot add or alter the Mission objective, approved scope,
acceptance criteria, required capabilities, governance constraints or write
authority. A need outside that immutable envelope follows existing governance
refinement/waiting semantics and does not become an Action.

`SUCCESSOR_HAS_MISSION_GAP_BINDING = TRUE`

No Mission/action-count progression budget exists in the current Forge
planning policy. The repair budget and maximum-parallel-action constraint are
different controls and are not generalized here.

`AUTONOMOUS_PROGRESSION_BUDGET = SEPARATE_NON_CANARY_HARDENING`

## Blocking, governance pause, and resume

`BLOCKED` and `FAILED` are deterministic pauses. The unresolved Action remains
in Mission State, the Dispatcher is placed on hold, and no later Action can be
released. A normal resume only continues non-terminal persisted work.

Resuming a blocked or failed Mission requires a `RecoveryAuthorization` naming
the exact unresolved Action. It records the authority in durable state and
returns only that unresolved Action to `READY`; completed Actions are never
rerun. The Dispatcher is reactivated only after durable recovery.

Execution Policy adds a separate `AWAITING_APPROVAL` state after exact
successful evidence. It is neither a failure nor recovery. The resolved policy,
boundary, resume point, and approval provenance are durable; the Host is not
aware of them. See [Execution Policy](execution-policy.md).

Capability Delegation adds `WAITING_EXTERNAL_CAPABILITY`,
`WAITING_EXTERNAL_APPROVAL`, `WAITING_EXTERNAL_RESULT` and
`READY_TO_CONTINUE`. These durable states admit no later Action until the
delegated result has been verified and planning continuity is restored.

## Governance relationships

- Business Workspace approves the candidate and retains business authority.
- Architecture Workspace approves the Mission boundary and constraints.
- Mission Dispatcher admits and activates one approved Mission, handles holds,
  and receives completion notification; it does not plan or execute.
- AI Mission Planner produces only bounded Intents and Actions from approved,
  evidence-pinned inputs.
- Execution Host and its adapter remain replaceable operational boundaries.
- Architecture Review Engine and Mission Recommendation Engine run after
  completion through Dispatcher hooks. Recommendations remain advisory to the
  Business Workspace.

## Out of scope

Parallel Missions, parallel Engineering Actions, cloud execution, portfolio
optimisation, automatic approval, and Execution Host implementation remain out
of scope.
