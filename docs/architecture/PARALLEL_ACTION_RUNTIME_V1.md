# Parallel Actions inside one Mission — runtime design V1

**Increment:** `FORGE_EP_PARALLEL_ACTION_RUNTIME_V1`. **Owner:** Forge.
**Status:** target-design refinement; canonical after protected merge. All new implementation and qualification nodes remain **PLANNED**. **Version decision: NO_BUMP.**

This concretizes the existing [Living Mission Graph](LIVING_MISSION_GRAPH_AND_CROSS_REPOSITORY_ACTION_DAG.md) and its second cross-repository Runtime milestone. It is not a new planner, EP scheduler, Mission programme or replacement roadmap. See [owning delivery roadmap](../roadmap/PARALLEL_ACTION_RUNTIME_V1.md), [documentary DAG](../roadmap/parallel-action-runtime-v1.json) and [shared qualification cases](PARALLEL_ACTION_QUALIFICATION_V1.md). EP owns the companion `docs/engineering/FORGE_ACTION_DEPENDENCY_ADMISSION_BOUNDARY.md` and `docs/development/PARALLEL_ACTION_EXECUTION_V1_ROADMAP.md`.

## 1. Observed limitation and requested outcome

Source reviewed on 2026-09-17: Forge `03f9514e0f1e66a79ccb684c9fdbe51b28b88090`; EP `f45694d40b753d235feac8b803d364e1450cae26`. These identify inspected source, not a new audit of running services or the in-progress reset implementation.

At that Forge source, `forge/runtime/dynamic_mission.py` composes `_OneActionProvider`, requires exactly one derived Action per provider result and carries a single current Action/result correlation. `_loop()` binds the selected host configuration's project/repository at loop level. These are deliberate serial-canary limits, not permanent architecture invariants. Removing only the one-result check would leave persistence, target authorization, dispatch and reconciliation unsafe.

Required target: within one governed Mission, Forge derives multiple distinct, bounded Actions, proves their logical eligibility and durably submits a bounded eligible frontier. EP can actually execute independent repository Actions concurrently when its resource/capacity policy permits. A declaration that two nodes are eligible, two queued receipts, or two UI spinners is not proof of concurrent execution.

The current Mission-3 serial dynamic-replanning test and reset work remain unchanged. This design grants no permission to run a Mission, modify policy, install a release, rotate credentials or reset data. The first parallel delivery is two authorized repositories on one compatible EP host with separate workspaces. A distributed Agent fleet, Workspace UI, native nested-agent engine and the complete future Server/Console programme are not artificial predecessors; the exact installed runtime/transport/concurrency seams still require qualification.

## 2. Separate planning from execution and from subagents

Forge owns objective/criterion containment, graph reasoning, per-Action target/write scope, hard dependency evidence, planning policy and Mission reconciliation. EP owns accepted execution state, leases, physical placement, provider capacity, validation, assurance, delivery and terminal evidence. Communication uses the existing authenticated versioned HTTP boundary; neither product queries the other's database.

An Action is a bounded engineering delivery, not one AI worker. A provider may internally delegate work under its existing qualified scope; that does not create another Forge Action or permit writing another repository. Native subagents and parallel mandatory reviewers are separately governed capabilities, not prerequisites or proof for inter-Action concurrency. One Action retains its own candidate-bound assurance and delivery requirements regardless of the number of internal workers.

One Mission may cover several explicitly approved repository targets. A project label, same owner or filesystem adjacency is not authorization. One Action normally has one target repository. Per-Action routing resolves the exact EP instance/project/repository attachment and credential scope from an approved registry/binding, not a loop-global target or provider-supplied arbitrary URL. The current consumer for repository `forge` does not automatically authorize `engineering-platform`. Missing target grants are explicit blockers; no broad consumer, secret copying or repeated global peer reconfiguration to switch targets.

## 3. Model and immutable execution boundary

Extend the existing Mission state/store, planner, derivation journal and submission services; do not create a second graph database, scheduler or queue. Exact schema versions and migrations belong to implementation.

| Record | Required meaning |
| --- | --- |
| Mission graph revision | Stable Mission/revision, approved scope/policy references, current criteria and a revisioned set of nodes/edges |
| Planning snapshot | Per-repository Truth vector, accepted predecessor evidence set, unsatisfied criteria, unresolved findings, and reservations for materialized/in-flight contributions |
| Unmaterialized node | Proposed objective, target, criterion contribution, expected output/evidence, dependencies and independence/conflict analysis |
| Materialized Action | Immutable Action/revision, Mission/Intent provenance, target and write scope, actual target baseline, acceptance, dependency snapshot/evidence predicates, request digest and idempotency/correlation identity |
| Per-Action execution slot | Owning submission intent, selected binding revision, admission/readback identity, EP attempt lineage, observed lifecycle state and verified evidence references |
| Mission aggregation | Reconciled contributions, pending/blocked/uncertain work, graph revision and completion decision; never just the latest callback |

A materialized Action remains immutable even if not yet dispatched. To withdraw it, use an explicit pre-dispatch cancellation disposition proving no accepted effect, or owning EP cancellation/readback when acceptance is possible. Do not recycle its identity for changed bytes. Future unmaterialized work may be revised, split or retired. Already running siblings and historical evidence are never rewritten by replanning.

Legacy singleton fields are compatible projections only when exactly one Action exists in flight. With multiple Actions they must expose an explicit collection/count or unsupported legacy view, not an arbitrary first/latest child. Migration maps an existing serial Action/correlation losslessly into one slot. Ambiguous legacy records fail closed; migration cannot replay submissions, invent graph edges or reset grants/usage.

## 4. Derive an eligible frontier, not a forced A→B chain

The planner may return one or several justified nodes from one immutable planning snapshot. Validate the complete proposed graph delta for scope, criterion causality, unique identities, valid targets, resolvable references and acyclicity before accepting/materializing it. An invalid delta does not silently materialize its convenient valid subset; use an explicitly versioned partial-result contract only if separately qualified.

Independence is reasoned from required inputs/outputs, approved artifact/interfaces and causal evidence, not merely absence of an edge in malformed data. Different repositories can depend on each other. Conversely membership of one Mission/project is not a hard dependency. Shared resource exclusion remains EP-owned and must not be encoded as a fake `depends_on` edge.

Reserve intended criterion contributions for materialized/in-flight Actions. Reservation is not success evidence, but prevents two planners from duplicating the same missing work while a sibling is progressing. Overlapping contributions are allowed only with an explicit reason, such as independent verification or distinct parts of one criterion. Do not split a coherent Action solely to increase agent count or create unnecessary review/publication transactions.

Compute the currently eligible frontier from the validated graph and verified evidence. Release a bounded subset according to the approved Mission policy, fair selection and negotiated peer limits; do not fan out the whole backlog. Remaining eligible nodes are visibly waiting for release/capacity policy, not given invented logical predecessors. A finite numeric limit, not the number three from an example, is resolved and recorded before execution. `SERIAL` remains compatible; `PARALLEL_ELIGIBLE` is a design profile whose activation requires real capability/authorization. Unknown capability cannot be reported as parallel success.

## 5. Dependencies and Truth are per Action

A hard edge names the predecessor Action/revision and the required canonical result/evidence. Predicates can require exact project/repository, source revision, immutable receipt, qualified artifact digest, publication provenance and contract version. A generic COMPLETE or source merge cannot satisfy a published-qualified-wheel requirement. Wrong attempt, different candidate or stale incompatible artifact cannot satisfy the edge.

Use a repository Truth vector, not one Mission-wide commit SHA. A change to repository A does not overwrite B's baseline or invalidate an unrelated B Action. Each admitted Action retains its own pinned target baseline and declared read/evidence dependencies. A newly derived successor pins the actual current baseline required by its inputs; it cannot retrofit a new allowed-baseline to an existing request.

If an in-flight consumer's declared inputs are materially invalidated, record the actual conflict and use guarded hold/cancellation/replanning. An unrelated sibling's successful commit is not automatically such a conflict. Qualification must distinguish causal input invalidation from harmless graph revision, unrelated repository progress, pending CI or read-only observations.

## 6. Bounded asynchronous dispatch and concurrency-safe persistence

Persist intended materialization/submission identities before HTTP effects. Use short owning database transactions plus graph/slot revision compare-and-swap. Do not hold a Mission/database mutation lock across provider reasoning, network waits or the whole EP execution. SQLite serializing brief writes does not justify serializing independent engineering work.

Planning uses a captured revision; publication of its result rechecks relevant Truth, accepted evidence, policy and in-flight reservations. A stale plan is recorded as stale, not applied over newer sibling results. Deduplicate/batch independent events where semantically safe to avoid redundant planning; completion/cancellation events still cannot be lost. Planner concurrency need not equal execution concurrency: a single short planning coordinator may manage several concurrent EP runs.

Submission outcomes are independent. Persist A's acceptance even if B's POST is rejected or times out. A lost acknowledgement triggers exact readback/reconciliation of B's existing identity and bytes, never a new Action/submission or a resend with a different key. On restart rebuild all slots and reconcile each accepted/uncertain request before retrying any effect. Product policy owns retry/recovery allowances; parallelism does not replenish them or convert same-Action attempts into new graph nodes.

EP may accept several independently and report dependency/resource/capacity/authority waits separately. A blocked queue head must not prevent eligible unrelated work from being considered. Forge does not allocate CPU/provider slots or bypass EP admission. Bounded dispatch and backpressure prevent request storms; one unavailable target must not silently retarget to another host/project.

## 7. Incremental fan-in and replan without a global wave barrier

Process results by Action identity and immutable receipt, not arrival order. Verify and reconcile each result once; update only the owning slot and affected criterion/Truth references. Duplicate, late, reordered or contradictory events retain their own classification and cannot overwrite another Action's outcome or double-count usage.

If A completes while B is still running, Forge may immediately derive/release C when C depends only on verified A evidence and is otherwise eligible. Do not wait for all Actions launched in the same planning round merely because they share a wave label. D depending on both A and B waits for both required evidence sets. A coordinator preparing integration tests can work earlier, but cannot claim joint qualification before both artifacts exist.

Example, not an allocated programme or prescribed Action script:

```text
              approved shared contract / Mission criteria
                       /                         \
         A: Forge reset implementation      B: EP reset implementation
                 |                                  |
         C: A-only follow-up                 B still running
                 \                                  /
                  Q: combined qualification of exact required artifacts
```

A and B become independent only once their required shared interface inputs are sufficiently fixed. The planner chooses actual nodes/sizing; a named coordination agent is not automatically another mutating Action. Q may be a provider-free validation operation under the existing contract or a real separately scoped Action if it delivers independent engineering work. None of these examples authorizes the live reset or changes the current reset task.

## 8. Failure, cancellation, maintenance and Mission completion

Use causal impact and explicit policy. A failed required predecessor blocks its dependants; a proven success in another slot stays successful. Permitted independent siblings can finish, or be safely cancelled when the applicable Mission/authority policy requires it. Revoked authority, unknown scope impact or compromised shared resources stop affected new admission and require owning reconciliation. Do not globally mark every sibling failed, silently ignore a required failure, or automatically launch scope-expanding repair work.

Cancellation/pause is a per-Action protocol with an aggregate Mission disposition. A request is not proof execution stopped or a lease was released. Uncertain effects remain visible and block unsafe completion/reuse. Existing product maintenance/reset must enumerate all active/uncertain slots; this document neither implements that maintenance change nor permits a reset during execution.

Mission completion requires current evidence for all approved required criteria AND no unaccounted accepted/pending/uncertain effects or required unresolved work. If work becomes unnecessary, retire unmaterialized forecasts and explicitly settle any materialized/admitted cancellations. Do not declare the Mission complete while a sibling may still mutate a repository. A stale completion check must fail its revision guard when another result or authorized graph change intervenes.

Each Action retains its own independent Quality/Security, validation and protected delivery. Joint qualification binds the actual pair/set of source/artifact digests, not two unrelated green reports. No new human approval is introduced merely for each eligible Action inside already-approved scope; existing genuine gates and scope/publication authority remain mandatory. Starting the next Mission remains the separately governed project loop.

## 9. Readback and efficiency evidence

Expose one Mission graph with a set of active Actions, independent target/attempt/receipt identities, dependency reasons, all applicable wait reasons, policy limits and source/as-of revisions. Legacy single-current-Action views must not hide other work. Workspace/Console are consumers of these readmodels, not prerequisites or lifecycle authorities; UI implementation is out of scope here.

Use existing canonical telemetry/evidence stores. Separate Mission planning, Action attempts, provider invocations and any observable internal subagents. Sibling Actions are not an EP retry chain. Include all observed child usage once; unknown subagent accounting remains explicitly incomplete, not zero. Concurrent duration is not the sum of Action wall times; distinguish Mission elapsed time, busy interval union, overlapping work, provider totals and dependency/resource/capacity waits.

Qualify actual execution overlap on a common observable clock and correct result isolation. Compare parallel and serial execution on the same bounded workload, provider/policy/quality gates and resource limits. Report elapsed time, accepted outcome, required-review quality, total/cached/uncached usage with coverage and orchestration overhead. No universal speedup or token reduction is guaranteed; constrained capacity may legitimately serialize. The acceptance claim must distinguish eligible concurrency, observed parallel execution and measured efficiency.

## 10. Delivery boundary

The seven Forge nodes in the owning roadmap generalize the existing runtime rather than deleting its serial guard in isolation. EP's six-node counterpart supplies dependency admission, independent resource execution, isolation/recovery and multi-run evidence. Both source and installed qualification are required. The first serial canary, active reset work, policy defaults, existing credentials and historical telemetry outcomes are unchanged by this documentation merge.
