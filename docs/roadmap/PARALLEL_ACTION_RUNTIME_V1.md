# Parallel Action runtime V1 — Forge owning roadmap

**Owner:** Forge. **All implementation/qualification nodes: PLANNED. NO_BUMP.**
This is the implementation decomposition of the existing second Runtime milestone in [the canonical roadmap](../../knowledge/bootstrap/10_ROADMAP.md) and [implementation DAG](../architecture/FORGE_V1_IMPLEMENTATION_DAG.md), not a competing programme. Read [the detailed design](../architecture/PARALLEL_ACTION_RUNTIME_V1.md) and [26 shared qualification families](../architecture/PARALLEL_ACTION_QUALIFICATION_V1.md). The [JSON](parallel-action-runtime-v1.json) is documentary, not scheduler input.

| Node | Dependencies | Bounded deliverable |
| --- | --- | --- |
| PA-F0 | none | Versioned graph/frontier/target/evidence contract and published peer compatibility fixtures |
| PA-F1 | PA-F0 | Multi-slot durable Mission state, serial migration, per-Action target/baseline/correlation and revision guards |
| PA-F2 | PA-F1 | Validated bounded planner fan-out, criterion reservations, DAG/containment validation and eligible frontier |
| PA-F3 | PA-F1; EP PA-E1/PA-E2/PA-E3 | Existing HTTP adapter's bounded asynchronous multi-submit/readback, backpressure and exact replay/restart |
| PA-F4 | PA-F2, PA-F3 | Per-result reconciliation, incremental successor derivation, multi-parent joins, failure/cancel and completion barrier |
| PA-F5 | PA-F4; EP PA-E4 | Multi-active readmodels, complete per-Action evidence and scope-correct telemetry/export projections |
| PA-FQ | PA-F5; EP PA-EQ | Installed one-host/two-repository dynamic fan-out/overlap/fan-in canary and serial/parallel efficiency evidence |

PA-F0 consumes the existing Living Mission Graph/Producer contract; no complete future policy/UI programme is required. PA-F1/F2 can progress using peer fixtures while EP qualifies execution. PA-F3 requires the exact used EP admission/resource/isolation slice, not merely a threadpool or two accepted rows. EP PA-EQ consumes PA-F0 contract fixtures, never PA-FQ, so there is no cross-product qualification cycle.

EP owns `docs/development/PARALLEL_ACTION_EXECUTION_V1_ROADMAP.md` and its JSON DAG. Same-Mission membership must not add an EP global mutex; real shared resources may legitimately serialize. First canary uses separate repositories/workspaces on one host, no full Agent fleet, Workspace or native subagent implementation dependency. Same-repository concurrent mutation remains separate stricter qualification.

The serial Mission-3 loop and current reset maintenance task are not expanded. Implementation can be prepared in parallel with other roadmap lanes in isolated work; acceptance of this capability is separate from serial autonomy, not inferred from it. Any later prioritization/actual Mission allocation follows existing governance. No new Mission IDs, live grants, policy activation, CI gate activation, installed change or release is made by this documentation.
