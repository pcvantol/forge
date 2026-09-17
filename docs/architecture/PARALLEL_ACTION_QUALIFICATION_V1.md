# Parallel Action runtime — shared qualification cases

**Status:** PLANNED tests, not executed qualification. **Increment:** `FORGE_EP_PARALLEL_ACTION_RUNTIME_V1`. **NO_BUMP.**
The [Forge runtime design](PARALLEL_ACTION_RUNTIME_V1.md) owns graph semantics; EP's owning dependency/admission design owns execution proof. Implement tests against actual product services and isolated stores. Name exact source/artifact, policy, target and invocation scope in every receipt.

| ID | Case | Required proof |
| --- | --- | --- |
| PA-01 | Serial compatibility and migration | Existing singleton Action maps losslessly to one slot; no replay or authority/usage reset |
| PA-02 | Actual planner fan-out | One approved Mission produces distinct justified per-target Actions without owner Action script |
| PA-03 | Invalid graph delta | Cycles, missing targets/edges, duplicate identity and out-of-scope nodes rejected before partial materialization |
| PA-04 | Independent targets execute concurrently | Two real EP execution intervals overlap with independent resources; queue/eligible flags alone insufficient |
| PA-05 | True cross-repository dependency | Free resources/capacity never allow execution before required predecessor evidence |
| PA-06 | Evidence predicate integrity | Wrong run, target, candidate, revision or artifact rejected; source merge does not prove published qualified bytes |
| PA-07 | Incremental fan-in | A completes while B runs; C needing only A can advance without waiting for B |
| PA-08 | Multi-parent join | Q requiring A and B remains blocked until both exact result/artifact predicates hold |
| PA-09 | Per-repository Truth | A progress does not overwrite B baseline; real shared-input invalidation handled explicitly |
| PA-10 | Concurrent result updates | Out-of-order/duplicate callbacks reconcile correct slots once; no lost graph updates or double usage |
| PA-11 | Stale planner/completion CAS | Old snapshot cannot overwrite new evidence/reservations or claim premature completion |
| PA-12 | Partial submission and lost acknowledgement | A accepted/B uncertain remain distinct; exact B readback, no duplicate Action/request |
| PA-13 | Runtime restart | All pending/running/uncertain slots reopen; no second writer or silent singleton truncation |
| PA-14 | Same-repository contention | Logical independence preserved, first profile serializes shared mutable target; no fake dependency edge |
| PA-15 | Cross-repo shared test resources | Shared ports, data-root, signing/build/release resources still exclude correctly |
| PA-16 | Capacity and fairness | Bounded global/provider/per-target limits, no multiplication by subagents, no head-of-line starvation |
| PA-17 | Scope and peer routing | A grant cannot authorize B target; no global rebind, new broad credential or arbitrary endpoint |
| PA-18 | Child failure and cancellation | Unaffected success retained; dependants blocked; no unacknowledged cancellation or hidden running work |
| PA-19 | Required reviews and delivery | Independent candidate-bound assurance for each Action; joint proof binds exact combination |
| PA-20 | Completion with pending effects | Mission cannot COMPLETE while required work, accepted writes or uncertain cancellations remain |
| PA-21 | No authority or budget laundering | Materialized identities immutable; retries don't become new Actions or reset allowance; no next Mission |
| PA-22 | Readmodel/MD/JSON parity | All active Actions and wait causes represented in one scoped snapshot, no singleton/last-result disguise |
| PA-23 | Usage/time accounting | Siblings not retry lineage; all child usage once, unknown explicit; union/elapsed versus sums labelled |
| PA-24 | Controlled efficiency comparison | Same work and quality gates; actual overlap and measured elapsed/usage, no invented speedup |
| PA-25 | Unsupported/disabled capability | Explicit serial-only disposition or blocker; never claim parallel qualification from fallback |
| PA-26 | Installed real boundary | Qualified artifacts outside source checkout, real Forge→HTTP→EP and returned per-Action evidence |

Qualification levels remain separate: documentary JSON/DAG checks; deterministic graph/store/HTTP fixtures; real local concurrent EP execution with a controlled provider; explicitly authorized live provider/cross-repository dogfood. A controlled provider test proves scheduling/identity, not actual model reasoning or provider efficiency. The final live canary must prove Forge-generated fan-out and incremental successor derivation as well as overlapping execution. No production CENTRAL reset, credential change or paid canary follows from this document.

Prototype the scenario with two authorized repositories on one host. Distributed fleet and Workspace UI are not required. Same-repository parallel writers and native nested-agent implementation are not implied. Existing serial Mission-3 criteria remain unchanged.
