# Engineering Intent Repository Layout

This directory reserves the canonical future layout documented in
[Engineering Intent Lifecycle 1.2](../../docs/architecture/engineering-intent-lifecycle.md).
Future records are dynamic planning artifacts created by the Mission Planner
from repository evidence and must first satisfy the repository-grounded
[Engineering Intent Authoring 1.4](../../docs/architecture/engineering-intent-authoring.md)
context:

```text
active/
completed/
superseded/
templates/
```

No Intent artifact is created or migrated by this increment. Historical Intent
records remain immutable even when later planning supersedes, merges, splits,
or removes an active planning artifact.

The canonical future layout is reconciled by
[Engineering Action Architecture 1.11](../../docs/architecture/engineering-action.md):
each Intent contains one or more Engineering Actions, while this directory
remains reserved only for Intent records. No Action storage is created here.
