# Forge Productization Reconciliation

**Status:** Canonical target architecture and reconciliation record.  
**Scope:** productization direction only; it authorizes no Mission, lifecycle
transition, implementation work, approval, or execution.

## Authority and evidence classification

This record is the target authority for productization terminology and
relationships. Existing models and contracts remain authoritative within their
stated boundaries: [Product Model](product-model.md), [Producer Contract](producer-contract.md),
[Execution Host Contract](execution-host-contract.md), [dual learning system](dual-engineering-learning-system.md),
and [roadmap](../../knowledge/bootstrap/10_ROADMAP.md).

| Evidence | Classification | Disposition |
| --- | --- | --- |
| Product lifecycle and separate Business/Architecture approvals | CURRENT_CANONICAL | Preserved exactly. |
| Producer and Execution Host contracts | CURRENT_CANONICAL | Forge plans/interprets; EP executes and owns operations/evidence. |
| Runtime DB, planner, scheduler, recommendation implementation | CURRENT_BUT_NEEDS_CLARIFICATION | Bootstrap limits are not permanent product limits. |
| Forge Studio as primary UI owning workspaces | SUPERSEDED | Separate Workspace owns interaction/control surfaces. |
| CLI owning runtime business logic | SUPERSEDED | CLI is deterministic adapter/reference over application services. |
| Bootstrap Workspace-as-sole-product-boundary language | HISTORICAL | Foundation provenance; live authority is divided below. |
| Cross-product dependency view/capability matrix | DERIVED_ONLY | Indexes evidence; allocates no work. |
| Recommendation lifecycle placing Candidate after approvals | CONFLICTING_AUTHORITY | Superseded by lifecycle below; compatibility read path only. |
| Versioned application-service/API and MCP transport schemas | UNDEFINED_GAP | Target boundary defined here; delivery remains V1 work. |

No classification silently changes implementation or persisted records.

## Product lifecycle, Vision, Portfolio and Forecast

```text
Product Vision -> Portfolio -> Mission Candidate -> Business Review
-> Approved for Architecture -> Architecture Review -> Approved for Engineering
-> Mission -> Engineering -> Execution -> Evidence -> Architecture Review
-> Mission Recommendation -> Portfolio
```

`MISSION_CANDIDATE_IS_NOT_EXECUTABLE = TRUE`  
`MISSION_RECOMMENDATION_IS_ADVISORY = TRUE`  
`BUSINESS_APPROVAL_REMAINS_EXPLICIT = TRUE`  
`ARCHITECTURE_APPROVAL_REMAINS_EXPLICIT = TRUE`  
`FORGE_AUTONOMY_BEGINS_ONLY_INSIDE_APPROVED_MISSION = TRUE`

Product Vision is a durable Forge ProductVision aggregate: the strategic
outcome, priorities, assumptions, constraints and success framing needed by
Portfolio, candidates, recommendations, refinement, roadmap/forecast and
learning interpretation. A Markdown record is versioned repository
representation/evidence, not the sole live authority. Workspace presents it
and sends governed intents.

Portfolio is governed product opportunity state. Its **Roadmap DAG** is a
derived Mission/product dependency, capability-ordering, readiness and unlock
projection. **Forecast** is another derived, freshness-labelled projection
from Vision, Portfolio, candidates, recommendations, roadmap, dependencies,
maturity, confidence, estimates, runtime state, throughput, blockers and
learning. Forecast can explain likely next work, unlocks, risk and uncertainty;
it is neither a lifecycle stage, scheduler nor authority.

`FORECAST_IS_DERIVED_PROJECTION = TRUE`  
`FORECAST_APPROVAL_AUTHORITY = FALSE`  
`FORECAST_EXECUTION_AUTHORITY = FALSE`

## Refinement, conversations and approval

Business refinement is a persistent Forge capability over Vision, Portfolio,
candidates, value, prioritisation, dependencies, assumptions, outcomes, risks
and alignment. **Business Advisor** remains the advisory capability. A future
“Business Architect Session” is only a Workspace session/presentation that
composes it; it does not rename it. AI/conversation output becomes a structured
proposal, then changes authoritative state only via a governed intent and
explicit Business decision.

Architecture refinement is a persistent Forge capability over scope,
feasibility, constraints, acceptance criteria, assumptions, dependencies,
capabilities, disciplines and risks. **Architecture Advisor** and **AI
Architect Session** are advisory capability/session records. Platform Architect
is the human approval authority. Session output becomes durable refinement only
through governed Architecture intent and decision.

`BUSINESS_CONVERSATION_IS_ADVISORY = TRUE`  
`BUSINESS_MUTATION_REQUIRES_GOVERNED_INTENT = TRUE`  
`ARCHITECTURE_CONVERSATION_IS_ADVISORY = TRUE`  
`PLATFORM_ARCHITECT_RETAINS_APPROVAL_AUTHORITY = TRUE`  
`AI_ARCHITECT_CANNOT_APPROVE_MISSION = TRUE`

## Runtime, graphs and autonomy

Forge Runtime Service is the always-on-capable composition host. It attaches
projects, coordinates Runtime Instances, observes Repository Truth, processes
recommendations, plans/reconciles Missions, schedules bounded work, reconciles
EP receipts, hands off completion, runs Quality/Knowledge Observers, produces
Roadmap/Forecast, persists governed proposals, and exposes APIs/events. It is
not an Execution Host or second engineering engine. CLI remains bootstrap,
qualification, scripting, admin, CI, recovery and headless adapter.

The **Living Mission Graph** is the active approved Mission's Intent/Action
dependency graph; evidence reconciliation may change its eligible work but not
the Mission objective, constraints, approval state or boundary. The Roadmap
DAG is not the Living Mission Graph.

`ROADMAP_DAG_IS_NOT_LIVING_MISSION_GRAPH = TRUE`  
`MISSION_GRAPH_CANNOT_CHANGE_APPROVED_MISSION_BOUNDARY = TRUE`

1. **Mission Execution:** approved Mission -> planning -> Action -> Producer
   submission -> EP evidence -> graph reconciliation -> replan -> completion.
2. **Portfolio Intelligence:** product/repository truth + completed evidence +
   Architecture Review -> recommendation -> Portfolio/Roadmap/Forecast ->
   Business refinement -> candidate -> explicit approvals -> Mission.
3. **Engineering Learning:** Action/Mission evidence feeds Quality and
   Knowledge learning; both propose only.

`MISSION_EXECUTION_AUTONOMY = BOUNDED_BY_APPROVED_MISSION`  
`PORTFOLIO_AUTONOMY = OBSERVE_ANALYZE_PROPOSE`  
`LEARNING_AUTONOMY = OBSERVE_ANALYZE_PROPOSE`

## Workspace, EP, CLI, API and MCP

Forge owns Vision/Portfolio semantics, candidates, Architecture refinement,
approved Missions, planning/runtime state, recommendations and learning
outputs. Workspace owns human interaction, conversations, visualizations,
approval UX, notifications and user-controlled proposal accept/reject. It
uses canonical API/contracts, does not shell out to CLI, and never owns Forge
planning. Historical Forge Studio is fully superseded as a product surface by
Workspace; its presentation-only constraints are compatible.

EP owns admission, readiness, submissions/runs, queue/scheduling, Agent
dispatch, liveness, retry/resume/repair, receipts and execution evidence.
Forge owns Mission semantics, Producer Submission construction, completion
reasoning and learning interpretation. Workspace may present both, owns neither.

```text
Forge application services
        ^
 CLI / API / Workspace / MCP / Runtime Service background workers
        ^
Forge Producer Submission -> EP admission, scheduling, execution and receipts
```

Application services are interface-neutral. Queries include Vision, Portfolio,
Roadmap DAG, Forecast, candidates, recommendations, approved Missions, Living
Mission Graph, runtime status, owned/consumed DoR/DoD/Gates, learning and
lineage. Governed intents include candidate/refinement proposals,
Business/Architecture decisions, learning disposition, Mission Intake request
and bounded controls. All mutations require actor, authorization/approval
context, idempotency, expected version, correlation and audit evidence.

MCP is an adapter with initial **READ, EXPLAIN, PROPOSE** profile; no direct
execution, approval bypass, DoR/DoD bypass, policy mutation or certification.

`FORGE_CAN_RUN_WITHOUT_WORKSPACE = TRUE`  
`FORGE_RUNTIME_SERVICE_IS_ALWAYS_ON_CAPABLE = TRUE`  
`FORGE_RUNTIME_SERVICE_IS_NOT_EXECUTION_HOST = TRUE`  
`CLI_IS_NOT_SECOND_AUTHORITY = TRUE`  
`WORKSPACE_DOES_NOT_SHELL_OUT_TO_FORGE_CLI = TRUE`  
`WORKSPACE_FORGE_INTERACTION = CANONICAL_API_OR_CONTRACT`  
`WORKSPACE_DOES_NOT_OWN_FORGE_PLANNING_AUTHORITY = TRUE`  
`FORGE_EXECUTION_AUTHORITY = 0`  
`EP_PRODUCT_PLANNING_AUTHORITY = 0`  
`FORGE_APPLICATION_SERVICES_INTERFACE_NEUTRAL = TRUE`  
`MCP_IS_ADAPTER_NOT_AUTHORITY = TRUE`  
`FORGE_DOES_NOT_CALL_ITSELF_THROUGH_MCP = TRUE`

## Repository, operational state, learning and clean installation

Repository Truth is durable product/engineering evidence and canonical
repository records. Forge Operational State is restart-safe coordination,
cursors, pending proposals, runtime/scheduler state and observer status; it
cannot override Repository Truth. EP Operational State is submissions, runs,
Agents, receipts and repair state. Git-backed does not mean Git-only runtime.

Quality Learning changes project engineering practice only after project
governance. Knowledge Learning exports reusable implications to the separately
governed KB; Certified Knowledge is read-only when consumed. Both observers are
background Runtime Service capabilities and do not block execution unless an
explicit current Action contract requires it.

An installed Forge, Workspace and EP must package schemas, baseline contracts,
migrations, renderers, qualification fixtures and capability definitions.
Project-specific Repository Truth is created/attached per project; runtime
cannot require pcvantol source checkouts or ai-development-contracts paths.

`PROJECT_POLICY_IS_NOT_CERTIFIED_KNOWLEDGE = TRUE`  
`CERTIFIED_KNOWLEDGE_IS_NOT_AUTOMATIC_PROJECT_POLICY = TRUE`  
`GIT_BACKED_DOES_NOT_MEAN_GIT_ONLY_RUNTIME = TRUE`  
`CLEAN_INSTALL_SELF_CONTAINED = TRUE`

One active Mission, one Action, and one local project are current bootstrap
qualification limits, not target invariants. Target service supports per-project
observation/scheduling; cross-project and later multi-Mission parallelism wait
for EP admission/lease/delivery contracts. Intra-Mission ordering remains graph
controlled.

## Target authority matrix

| Concept | Canonical owner | Readers | Mutators | Approver | Execution authority | Persistence | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Product Vision | Forge | Workspace, advisors | governed intent | Business | none | Forge + repository representation | live aggregate. |
| Portfolio | Forge Business domain | Workspace, advisors | governed intent | Business | none | Forge | opportunity state. |
| Forecast | Forge projector | all adapters | projector only | none | none | derived Forge store | labelled projection. |
| Mission Candidate | Forge Business domain | Workspace, Architecture | governed refinement | Business | none | Forge | never executable. |
| Business refinement | Forge Business capability | Workspace | governed intent | Business Owner on decision | none | Forge | conversation advisory. |
| Business approval | Forge decision evidence | all | named Business Owner | Business Owner | none | Forge | explicit. |
| Architecture refinement | Forge Architecture capability | Workspace | governed intent | Platform Architect on decision | none | Forge | session advisory. |
| Architecture approval | Forge decision evidence | all | named Platform Architect | Platform Architect | none | Forge | explicit. |
| Mission | Forge | planner, Workspace, EP ref | Intake after approvals | prior approvals | bounded planning | Forge | immutable boundary. |
| Mission Planner | Forge | Runtime Service | replan | none | no dispatch | Forge operational state | bounded. |
| Roadmap DAG | Forge projector | Workspace | projector | none | none | derived Forge store | Mission-level. |
| Living Mission Graph | Forge runtime | planner, Workspace | reconciler | none | eligible Action selection | Forge operational state | Action-level. |
| Engineering Action | Forge | EP, Workspace | planner | none | EP submission/run | Forge snapshot/EP envelope | immutable after submission. |
| Submission | EP | Forge, Workspace | EP ingress | EP admission policy | EP | EP | Forge constructs envelope. |
| Run | EP | Forge, Workspace | EP | EP operational policy | EP | EP | retry/repair EP-owned. |
| Execution Receipt | EP | Forge, Workspace | EP | none | none | EP | Forge stores reference/interprets. |
| Quality Learning | Forge | Workspace/EP evidence | observer + governance | project governance | none | Forge/project contract | no auto-policy. |
| Knowledge Learning | Forge + KB | Workspace | observer/KB lifecycle | KB certification | none | Forge proposal + KB certified state | read-only consumption. |
| Workspace presentation | Workspace | humans | UI/preferences | user as applicable | none | Workspace | no Forge-state authority. |
| CLI | Forge adapter | operators/CI | service calls only | service rules | none | no independent store | scripting/qualification/recovery. |
| MCP | Forge adapter | AI clients | allowed service calls | service rules | none | no independent store | read/explain/propose. |

`AUTHORITY_CONFLICT_COUNT = 0`

## State and projection matrix

| Concept | Authoritative state | Derived projection | Conversation context | Repository representation | Operational storage | Workspace projection |
| --- | --- | --- | --- | --- | --- | --- |
| Product Vision | Forge aggregate | alignment/Forecast inputs | advisor session | vision record | Forge service state | vision/decision view |
| Portfolio | Forge Business domain | Roadmap/Forecast | Business session | portfolio record | Forge store | portfolio board |
| Forecast | governed inputs | Forecast | explanation chat | optional snapshot | projection cache | forecast view |
| Mission Candidate | Forge candidate | maturity/readiness | Business session | candidate export | Forge store | candidate editor |
| Architecture Mission | Forge refinement/approval | engineering-ready view | Architecture session | mission record | Forge store | review surface |
| Mission Runtime | Forge Mission State | runtime status | none | evidence links | Runtime Instance | execution view |
| Roadmap DAG | governed relationships | ordering/unlocks | advisory explanation | export | projection store | roadmap view |
| Living Mission Graph | Forge runtime graph | active dependency view | planner context | evidence links | Runtime Instance | graph view |
| Quality Learning | Forge proposals/dispositions | trends | quality discussion | accepted project policy | observer store | quality review |
| Knowledge Learning | KB-certified/Forge proposal state | reuse/lineage | knowledge discussion | exports/links | observer + KB store | knowledge review |

`UNCLASSIFIED_FIRST_CLASS_STATE = 0`

## Supersession and compatibility register

| Old concept | Status | Successor | Migration/doc action |
| --- | --- | --- | --- |
| Forge Studio primary UI/owner | SUPERSEDED | Workspace control plane | retain presentation-only compatibility pointer. |
| CLI-first runtime owner wording | SUPERSEDED | adapters + application services + Runtime Service | incrementally move duplicate logic. |
| Business/Architecture Workspace as UI | SUPERSEDED | Forge domain capability + Workspace presentation | preserve governance semantics. |
| one active Mission / one Action | CURRENT_BUT_NEEDS_CLARIFICATION | qualification limits | never write as permanent target rule. |
| Portfolio-only presentation | SUPERSEDED | Portfolio + Roadmap DAG + Forecast | add projections, no authority. |
| EP 1.5 direct integration | SUPERSEDED | Producer/Execution Host contracts | adapter-local bootstrap compatibility only. |
| Forge-owned Execution Host | SUPERSEDED | EP installed Execution Host | remove ownership claims. |
| standalone Forge Workspace terms | HISTORICAL | separate Workspace product | label bootstrap use historical. |
| docs/roadmap/0.1.md | HISTORICAL | knowledge/bootstrap/10_ROADMAP.md | redirect only. |
| recommendation-before-candidate lifecycle | CONFLICTING_AUTHORITY | this lifecycle/Product Model | compatibility read path only. |

`UNCLASSIFIED_STALE_PRODUCTIZATION_CONCEPTS = 0`

## V1 implementation DAG and decisions

```text
P0 reconciliation -> P1 application services -> P2 canonical API -> P3 Runtime Service
P1 -> P4 Portfolio/Roadmap/Forecast; P1 -> P5 Business/Architecture sessions
P2 -> Workspace API and MCP READ/EXPLAIN/PROPOSE
P3 + EP qualified contract -> bounded autonomous Mission execution
P3 -> Portfolio Intelligence -> recommendations
L0/L1 -> Quality L2-L4; KB export -> Knowledge L5-L8
P2 + packaged artifacts + EP/Workspace gates -> standalone qualification
```

| Node | Dependencies | Parallel work | Blocked capability |
| --- | --- | --- | --- |
| P0 reconciliation | repository evidence | design | coherent target |
| P1 application services | P0 | API/projections | adapter de-duplication |
| P2 canonical API | P1 | Workspace/MCP fixtures | integrations |
| P3 Runtime Service | P1 + CLI qualification | projections/observers | always-on operation |
| P4 Forecast | P1 | sessions/runtime | Forecast |
| P5 sessions | P1 + Workspace API contract | Forecast | governed conversations |
| EP qualified L0/L1 | EP-owned proof | Forge fixtures | autonomous submission/execution |
| Quality L2-L4 | runtime/planning + L0/L1 | Knowledge | Quality Learning |
| Knowledge L5-L8 | KB export/consumption proof | Quality | Knowledge Learning |
| MCP | P2 | Workspace client | safe AI exposure |
| installed qualification | P2 + packaged artifacts + EP/Workspace gates | observers | clean standalone release |

The DAG is acyclic: `V1_IMPLEMENTATION_DEPENDENCY_CYCLES = 0`. Every edge has
a named owner/contract: `UNRESOLVED_V1_DEPENDENCIES = 0`. It is nevertheless
blocked pending governed decisions/qualification for `FWV1-G001`, `G003`,
`G005`, `G007`, `G008`, `G009`, `G010`, `G011`, and `G013`: installed
topology/identity/security, attachment/adoption, multi-repo lease/delivery,
history/retention, API schemas, and Workspace accessibility/control-plane.

Every supersession needs consumer migration, stale-doc update, runtime/API/
storage audit, compatibility period and separately governed retirement Action.
The linked canonical records are updated with this pointer.

`CONTRADICTORY_CANONICAL_PRODUCTIZATION_TEXT = 0`

`FORGE_PRODUCTIZATION_RECONCILIATION = BLOCKED` until the named human/product
decisions and producer qualification evidence are closed.
