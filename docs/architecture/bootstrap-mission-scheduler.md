# Bootstrap Mission Scheduler 2.0

## Purpose

The Bootstrap Mission Scheduler deterministically plans, sequences, monitors, and advances Engineering Actions within an approved Mission. It does not plan with AI and does not perform engineering. Engineering Platform 1.5 remains the temporary external Execution Host during bootstrap.

```text
Mission → Engineering Intent → Engineering Action → Runtime Prompt
  → Engineering Platform Inbox → Engineering Platform Report
  → Repository Evidence → Mission Scheduler
```

Mission owns its objective, boundaries, progress, dynamic Intent provenance, and completion state. An Intent owns tactical rationale and one or more Actions. An Action is the executable planning unit: each released Action produces exactly one Runtime Prompt. The Scheduler never releases an Intent.

## Deterministic scheduling

Actions have a stable, consecutive `order`, stable identity, parent Intent revision, bounded objective, declared dependencies, and expected evidence. Selection considers Actions by ascending order. The first `READY` Action whose declared predecessors are all `COMPLETE` is the only selectable Action. Unknown dependencies, duplicate identities, non-consecutive order, and a second `ACTIVE` or `WAITING_FOR_RESULT` Action are invalid Mission state.

The Scheduler state is the declared Actions plus an evidence-derived progress snapshot: current Intent, current Action, execution state, repository evidence, and completed-action count. It does not infer progress from an Intent status or from an assumed successful execution.

| State | Permitted next state | Meaning |
| --- | --- | --- |
| `READY` | `ACTIVE` | Deterministically selected after dependencies complete. |
| `ACTIVE` | `WAITING_FOR_RESULT` | Its single Runtime Prompt was delivered. |
| `WAITING_FOR_RESULT` | `COMPLETE` | Matching Engineering Platform report and repository evidence confirm it. |
| `WAITING_FOR_RESULT` | `BLOCKED`, `FAILED` | Terminal external result stops the Mission. |
| `COMPLETE` | — | A dependent Action may now be selected. |
| `BLOCKED`, `FAILED` | — | No implicit retry, skip, or successor release. |

Repository evidence must name the completed Action and the Engineering Platform report that asserted its successful outcome. A successful report without matching repository evidence cannot advance the Mission.

## Bootstrap Adapter

The adapter has two injected interfaces only: an Engineering Platform Inbox for submitting a Runtime Prompt, and an Engineering Platform Report supplied back to Forge. It translates neither prompt content nor reports and makes no network call, queue, repository mutation, provider invocation, or background service. It moves the one active Action to `WAITING_FOR_RESULT` only after delivery, and reconciles `COMPLETE`, `BLOCKED`, or `FAILED` only through the Scheduler.

Future Forge Execution Hosts may implement the same narrow inbox/report boundary. They do not become the Mission Planner and cannot change Mission, Intent, Action, or evidence semantics.

## Non-goals

This increment implements no AI Mission Planning, autonomous engineering, Forge Runtime, Execution Host, queue daemon, background service, provider, Studio, repository operation, or Engineering Platform modification.
