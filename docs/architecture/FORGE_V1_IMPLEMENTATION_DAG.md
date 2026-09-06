# Forge V1 Implementation DAG

**AUTHORITY = DERIVED.** Source authority is the Product Model, Productization Reconciliation, V1 Decision Contract, canonical Forge roadmap and product-owned cross-product producer contracts. This document never allocates EP or Workspace work.

## Current bootstrap reconciliation — 2026-09-06

The shortest safe route to Forge autonomy is now explicit:

```text
Forge Action-Derivation foundation (qualified)
  -> EP P-NEUTRAL closure
  -> EP minimal installed execution-path qualification using existing runtime
  -> EP::STANDALONE_EP_VERIFIED
  -> Forge F3/F4 binding to canonical EP HTTP submission + status/evidence contracts
  -> first Forge -> EP -> Forge governed execution canary
  -> autonomous next-Mission loop
```

Important consequences:

- P-TRANSPORT is merged/closed and already provides three canonical submission transports: HTTP, installed CLI and Server-owned File Inbox. Forge should reuse the canonical HTTP submission ingress rather than wait for or invent a second mutation transport.
- The older Phase-1 Local Consumer API read-only qualification and the later P-TRANSPORT HTTP submission ingress are distinct contracts. Describing all installed EP HTTP integration as read-only is stale.
- Workspace is not a runtime prerequisite for the first Forge autonomy canary. Workspace remains the human/project control plane and later consumer of qualified Forge/EP projections.
- B8R supersedes the older assumption that Workspace manufactures EP logical project identity. Durable project/repository identity is declared by the Canonical Project Authority Repository in `.engineering-platform/repository.json`; Workspace may project it and own human-facing state.
- Broader Project-Agent separation, generalized Agent dispatch, multi-host scheduling and multi-repository parallelism are not prerequisites for the first `EP::STANDALONE_EP_VERIFIED` canary when the existing installed EP execution path can prove one governed execution. They remain follow-on EP productization.
- Do not make full P-QUEUE/generalized dispatch or the whole B8E product programme artificial prerequisites for the first standalone canary. Only concrete capabilities required to execute, finalize, retain evidence and observe one governed run are on the bootstrap critical path. Any remaining B8E/queue/Agent gaps stay explicit follow-on nodes unless a qualification failure proves them necessary.

`P_TRANSPORT_STATUS = MERGED_CLOSED`

`WORKSPACE_ON_FIRST_FORGE_AUTONOMY_CRITICAL_PATH = FALSE`

`GENERAL_AGENT_SEPARATION_ON_STANDALONE_CRITICAL_PATH = FALSE`

`P_TRANSPORT_HTTP_SUBMISSION_REUSED_BY_FORGE = TRUE`

## Capability inventory and dispositions

| Capability | Current evidence classification | V1 disposition |
| --- | --- | --- |
| Governance, Mission Intake/amendments, Action-Derivation evidence/provider boundary | QUALIFIED bootstrap foundation | KEEP; do not reopen except regression. |
| Action-Derivation canary closure | QUALIFIED / PR #40 merged | KEEP; administrative qualification authority only. |
| Product Vision, Portfolio, Roadmap DAG, Forecast | CONTRACT_ONLY / PARTIAL | F2/F5. |
| Mission Candidates/Recommendations, Business/Architecture refinement | PARTIALLY_IMPLEMENTED | KEEP/HARDEN; F2/F6. |
| AI Mission Planner, Living Mission Graph, Mission State/Scheduler | PARTIALLY_IMPLEMENTED / proven local segments | KEEP/HARDEN; F4. |
| Action materialization + execution admission | FORGE_GAP | First executable F4 slice. |
| EP submission transport | EXTERNAL PRODUCER AVAILABLE at P-TRANSPORT transport layer | Reuse canonical HTTP ingress; do not duplicate. |
| EP installed one-run execution/finalization/evidence | EXTERNAL QUALIFICATION GAP | EP critical path to `STANDALONE_EP_VERIFIED`. |
| Forge EP result observation/reconciliation | FORGE_GAP | F4 immediately after installed EP producer is usable. |
| Broader Agent separation/general dispatch/multi-host | EP FOLLOW_ON | Not a first-canary blocker unless evidence proves otherwise. |
| Workspace control plane | WORKSPACE-OWNED FUTURE | Not a first autonomy-canary blocker. |
| Quality Observer/Learning | CONTRACT_ONLY | F7 optional V1. |
| Knowledge Observer/Learning | EXTERNAL / POST_V1 | F8 post-V1. |

## Critical DAG

```text
F1/F2 Forge service + contracts
        |
        +------------------------------+
        |                              |
        v                              v
Forge planning/derivation        EP standalone bootstrap
(already strongly proven)        P-NEUTRAL
        |                              |
        |                              v
        |                       minimal installed execution
        |                       submission -> run -> finalization
        |                       -> receipt/result
        |                              |
        |                              v
        |                    EP::STANDALONE_EP_VERIFIED
        |                              |
        +---------------+--------------+
                        v
              Forge F3/F4 executable slice
              materialize -> admit
              -> HTTP submit -> observe
              -> reconcile
                        |
                        v
              first Forge -> EP -> Forge canary
                        |
                        v
              autonomous next-Mission loop
```

The first Forge execution canary must use one repository, one bounded Action, one canonical submission identity and no automatic resubmission. Forge persists the intended immutable Action/submission key before the EP call; EP owns submission/admission/run/finalization evidence; Forge reconciles by canonical correlation/run identity.

## Cross-product authority boundaries

| Boundary | Owner | Bootstrap meaning |
| --- | --- | --- |
| Mission, Action intent, planning/governance | Forge | Forge decides why/what. |
| Project/repository declaration | Canonical Project Authority Repository, validated by EP | No path/name/Workspace-runtime-derived identity. |
| Submission/admission/run/finalization/receipt | EP | EP decides how execution proceeds. |
| HTTP submission transport | EP P-TRANSPORT | Existing canonical mutation ingress; Forge is a consumer. |
| Run/status/evidence projection | EP | Forge consumes, never reconstructs from logs/Console. |
| Human/project UX and cross-product projections | Workspace | Not execution authority and not required for first canary. |

## Readiness chains

| Readiness chain | Current edge sequence |
| --- | --- |
| Autonomous Mission execution | approved Mission -> Planner/Living Graph **PROVEN** -> Action materialization/admission **FORGE GAP** -> P-TRANSPORT HTTP submission **AVAILABLE TRANSPORT** -> installed EP execution/finalization/receipt **EP QUALIFICATION GAP** -> Forge observation/reconciliation **FORGE GAP** -> first canary -> next-Mission automation. |
| Portfolio intelligence | repository/completed Mission -> Review/Recommendation **PROVEN** -> F5 Roadmap/Forecast/ranking -> advisory candidate -> Business review. |
| Quality learning | Action/EP outcome -> F7 observer/proposal -> governed hardening. |
| Knowledge learning | evidence -> F8 observer/export -> KB certification -> read-only consumption; post-V1. |

## Build lanes and safe parallelism

| Lane | May proceed now | Must wait for |
| --- | --- | --- |
| Forge Action materialization/admission contract fixtures | Yes | Live integration completion waits for installed EP evidence. |
| EP P-NEUTRAL | Yes; current EP critical path | Its own exact-head/host qualification. |
| EP minimal installed execution canary | After required P-NEUTRAL closure | Only concrete execution prerequisites discovered by the canary. |
| Forge HTTP submission/status/result adapter | Contract-first against existing P-TRANSPORT/status evidence | Integration-complete claim waits for installed EP producer qualification. |
| Workspace onboarding/control plane | Fixture/design work only | Qualified producer contracts; not needed for first Forge autonomy canary. |
| Broader Agent separation/dispatch/multi-host | Follow-on | Not a bootstrap prerequisite by default. |
| Quality/Knowledge | Parallel/post-V1 as already classified | Their named predecessors. |

`UNSAFE_PARALLEL_LANES = 0`

## Installed execution and Forge F4 completion

`EP::STANDALONE_EP_VERIFIED` for this bootstrap means the installed EP instance has proven the minimum real execution chain needed by consumers: canonical submission, bounded admission, one governed execution through the current installed execution path, finalization, immutable receipt/result evidence and stable observation. It does not by itself require the future generalized Agent topology or multi-project scheduler.

After that gate, Forge F3/F4 should take the shortest integration route:

1. create/select one new low-risk executable Mission;
2. materialize one immutable Action snapshot;
3. persist one execution-admission/submission intent with idempotency/correlation;
4. POST through the existing canonical P-TRANSPORT HTTP submission ingress;
5. observe the canonical EP run/result projection without resubmitting;
6. reconcile the terminal evidence into Forge;
7. stop after the first canary;
8. only then activate automatic next-Mission selection in a separate final autonomy increment.

## Workspace position

Workspace V1 remains a consumer/control-plane programme. It may later present project topology, Forge planning, EP queue/run/result state and permitted lifecycle actions, but it is not needed to prove the first machine-to-machine Forge -> EP -> Forge execution loop. Its roadmap remains authoritative for Workspace-owned implementation.

## Roadmap-to-action readiness contract

The canonical Forge roadmap remains strategic authority. A derived node can become `READY_FOR_MISSION_CANDIDATE` only when its Forge predecessors and real external producer gates are satisfied. Derived documentation must not reintroduce stale producer assumptions, convert follow-on productization into artificial blockers, or silently promote a transport-level capability into execution qualification.

A passing DoR creates/refines an advisory Candidate; it does not self-approve execution. Owner/human gates apply at genuine authority expansion points, not every engineering repair/validation sub-step.

Regenerate/reconcile this DAG whenever the canonical Forge roadmap, EP roadmap/qualification state, Workspace roadmap or cross-product producer contracts change.
