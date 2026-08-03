# Autonomous Mission Execution Loop 4.4

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

The loop executes exactly one Engineering Action at a time. The Planner owns
the tactical plan; the Renderer owns prompt presentation; the Host owns
operational execution and evidence return. The loop never alters Mission
objectives, approves work, schedules a Mission, implements a Host, or activates
the next Mission.

## Durable Mission State

`MissionStateStore` is the canonical restart-safe runtime record. In addition
to the Mission, generated Intents and Actions, it persists current Intent and
Action, completed and remaining Action progress, correlation, current and
cumulative Execution Evidence, waiting reason, Repository Truth, completion
assertions, authorised recovery, and append-only lifecycle history.

The read-only `ExecutionLoopObservability` projection exposes current Mission,
Intent, Action, progress, host/lifecycle state, waiting reason and completion
percentage. It has no mutation or scheduling authority.

## Deterministic lifecycle

1. The Dispatcher supplies the one persisted active Mission.
2. For a newly admitted Mission, the loop obtains a complete, digest-pinned
   Planner input, calls `MissionPlanner.replan`, and persists the generated
   Intents and Actions before execution.
3. The Bootstrap Mission Runner releases one evidence-eligible Action, renders
   it through the injected renderer, and persists its exact Host request before
   dispatch.
4. Exact, correlated Host Evidence changes that Action only. Completed evidence
   causes the next Planner/Action cycle; incomplete host evidence leaves the
   Mission waiting without guessing.
5. Completion requires every Action complete, terminal Execution Evidence, and
   a refreshed Repository Truth completion context. The Dispatcher then runs
   the Architecture Review and Mission Recommendation hooks. It alone may
   subsequently evaluate its queue.

For identical Mission, Mission State, approved scope map, Repository Truth,
Planning Evidence and Host Evidence, the Planner and loop choose the same
Action order and persist equivalent state. Timestamps and host correlations are
operational evidence, not planning inputs.

## Blocking and resume

`BLOCKED` and `FAILED` are deterministic pauses. The unresolved Action remains
in Mission State, the Dispatcher is placed on hold, and no later Action can be
released. A normal resume only continues non-terminal persisted work.

Resuming a blocked or failed Mission requires a `RecoveryAuthorization` naming
the exact unresolved Action. It records the authority in durable state and
returns only that unresolved Action to `READY`; completed Actions are never
rerun. The Dispatcher is reactivated only after durable recovery.

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
