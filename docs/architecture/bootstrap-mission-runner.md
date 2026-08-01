# Bootstrap Mission Runner 3.0

## Purpose and boundary

The Bootstrap Mission Runner is Forge's deterministic orchestration loop. It
loads authoritative Mission State, invokes the Bootstrap Mission Scheduler,
derives one injected Runtime Prompt, dispatches through the canonical
Execution Host Contract, accepts only exact run-bound Execution Host Evidence,
and persists the resulting state transition. It performs no engineering,
architectural, governance, repository, or AI reasoning.

```text
Mission State → Scheduler → Engineering Action → Runtime Prompt
→ Execution Host Contract → Execution Host → Execution Evidence → Mission State
```

The Runner does not import or know the Bootstrap Adapter, Engineering Platform,
Inbox, iCloud, watcher, dashboard, launchd, operating-system services, or a
repository transport. Those are host-side concerns.

## Lifecycle

The persisted lifecycle is `CREATED → READY → ACTIVE →
WAITING_FOR_EXECUTION → WAITING_FOR_EVIDENCE`. Exact terminal host evidence
then produces `COMPLETED`, `BLOCKED`, or `FAILED`. A complete action returns to
`ACTIVE` only when another scheduler-eligible action exists. The State Store
records every transition and remains the only operational authority.

Bootstrap v1 permits exactly one non-terminal Mission and one active or
waiting Action. There is no parallelism, distributed execution, autonomous
Mission creation, planner, retry policy, daemon, network API, or background
service.

## Crash-safe dispatch and resume

Before calling a host, the Runner persists a complete dispatch envelope:
immutable Execution Request, rendered Runtime Prompt provenance, correlation
identity, and dispatch time. After a host acknowledgement it persists the host
run identifier before waiting for evidence. On restart it rebuilds a request
only from that envelope, never from reports or process memory.

The canonical Execution Host Contract requires correlation-idempotent dispatch
and `recover_dispatch`. A host must return the original acknowledgement for a
previously accepted correlation. The Bootstrap Adapter obtains this receipt
from its host-side Inbox boundary rather than an in-memory dispatch map. This
makes the recovery guarantee explicit without coupling Forge Runtime to any
particular host.

`BLOCKED`, `FAILED`, malformed evidence, and host failures persist a terminal
Mission result. The Runner performs no automatic retry. A future explicit
recovery decision is required before any new execution attempt.

## Evidence and completion

Only `ExecutionHostEvidence` with exact host, correlation, run, Mission,
Intent revision, Action, Runtime Prompt, repository, and retry provenance can
advance an Action. `COMPLETE` marks exactly the waiting Action complete;
Mission completion is permitted only once every Action is complete and terminal
evidence is persisted. `BLOCKED` and `FAILED` halt the Mission.

## Bootstrap limitations

This is an orchestration component only. It does not implement an Execution
Host, provider, AI planner, engineering intent generation, Mission planner,
repository operation, Studio, network interface, or operating-system runtime.
