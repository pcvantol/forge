# Bootstrap Mission Scheduler 2.1

## Boundary

The Bootstrap Mission Scheduler depends only on the canonical Execution Host
Contract. It releases a single Engineering Action through an `ExecutionHost`,
then reconciles only terminal `ExecutionHostEvidence`. It has no dependency on
Engineering Platform, DJConnect, iCloud, local paths, transport, watcher,
dashboard, report, or status representation.

```text
Mission → Engineering Intent → Engineering Action → Runtime Prompt
  → Execution Host Contract → Bootstrap Execution Host Adapter
  → Engineering Platform 1.5 → run-bound Execution Evidence → Scheduler
```

Engineering Actions, never Engineering Intents, are the executable scheduling
unit. The first `READY` Action in ascending order whose Action dependencies are
`COMPLETE` is the only eligible Action. Bootstrap v1 permits exactly one
`ACTIVE` or `WAITING_FOR_RESULT` Action and has no parallel execution, AI
replanning, daemon, repository mutation, implicit skip, or automatic retry.

## Dispatch and evidence correlation

`ExecutionRequest` binds one host request to its Mission, Intent and revision,
Action, Runtime Prompt, workspace, repository, correlation identity, dispatch
time, and optional retry predecessor. A host returns `ExecutionDispatch`, which
binds that exact request to one host run identifier.

Terminal `ExecutionHostEvidence` and its repository observation must match the
dispatched host, correlation, host run, retry relationship, Mission, Intent
revision, Action, Runtime Prompt, and repository. A latest report, unrelated
commit, old retry, mismatched report, unknown outcome, or contradictory identity
is rejected. This is intentionally fail-closed.

## Terminal states

| Host terminal evidence | Scheduler result |
| --- | --- |
| `COMPLETE` with exact correlation | Complete exactly the waiting Action; its eligible successor may be selected. |
| `BLOCKED` | Block the waiting Action and halt the Mission; explicit recovery/retry is required. |
| `FAILED` | Fail the waiting Action and halt the Mission; explicit recovery/retry is required. |
| Unknown or malformed | Reject evidence and do not advance. |

Intent completion is derived only when all of that Intent's Actions are
complete. Mission completion is derived only when all Actions and therefore all
Intents are complete.

## Bootstrap adapter

`BootstrapExecutionHostAdapter` is the sole Engineering Platform 1.5 boundary.
It translates canonical requests into the Bootstrap Inbox payload, receives the
host run identifier, retrieves Bootstrap reports, and maps their terminal state
and repository observation back into canonical evidence. Inbox transport,
`Retry-Of`, prompt-file handling, run identifiers, report/status locations,
polling, and local configuration belong there, never in scheduler core.

Engineering Platform 1.5 remains a replaceable reference Execution Host. The
separate Bootstrap Mission Runner 3.0 coordinates this scheduler through the
canonical contract; scheduler core still implements no host daemon, execution,
or repository operation.
