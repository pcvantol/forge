# Generation 1 Architecture Reconciliation and Generation 2 Transition

Forge Generation 1 is historical bootstrap engineering. Its five Portfolio
Seed Missions established Forge's architectural foundation; they are not a
backfilled operational portfolio.

## Ownership and runtime boundary

```text
Repository Truth → historical architecture and bootstrap engineering
Engineering Platform → historical/future execution evidence, reports, receipts, telemetry
Forge Runtime Instance → future operational Mission state and planning state
```

The Runtime Instance begins with the first operational Mission. Immediately
after bootstrap completion it is operational, intentionally empty, with an
`IDLE` Dispatcher and an empty Approved Mission Queue. This is the expected
state, not missing bootstrap evidence.

`MISSION-0001` through `MISSION-0005` remain canonical Portfolio Seed
Missions in repository and execution-history documentation. No Runtime
materialisation of those historical Missions is permitted.

## Generation 2 entry

Generation 2 starts only when a Mission Candidate progresses through Business
Workspace and Business Approval, Architecture Workspace and Architecture
Approval, the Approved Mission Queue, Mission Dispatcher, Runtime Instance,
and Engineering Platform. The first such Mission is the first Runtime Mission.

See the [Generation 1 Completion Record](../../GENERATION_1_COMPLETION.md).
