# Forge V1 Implementation DAG

**AUTHORITY = DERIVED.** Source authority is the Product Model, Productization
Reconciliation, V1 Decision Contract, canonical roadmap and cross-product
producer contracts. The JSON sibling is the deterministic source for validation.

## Capability inventory and dispositions

| Capability | Evidence classification | V1 disposition |
| --- | --- | --- |
| Product Vision, Portfolio, Roadmap DAG, Forecast | CONTRACT_ONLY | F2/F5; Forecast materialized projection. |
| Mission Candidates/Recommendations, Business/Architecture refinement | PARTIALLY_IMPLEMENTED | KEEP/HARDEN; F2/F6. |
| Architecture Review, Repository Truth | IMPLEMENTED_NOT_QUALIFIED | KEEP/ADAPT_TO_RUNTIME_SERVICE. |
| AI Mission Planner, Living Mission Graph, Mission State/Scheduler | PARTIALLY_IMPLEMENTED | KEEP/HARDEN; F4. |
| Forge operational store | PARTIALLY_IMPLEMENTED | MIGRATE to installation/project-partitioned authority; F1. |
| Runtime Service, application services, versioned API | NOT_IMPLEMENTED | F1/F2. |
| project attachment, multi-repo/leases, EP submission/receipts | CONTRACT_ONLY / EXTERNAL_DEPENDENCY | F3/F4; EP producer gates. |
| Quality Observer/Learning | CONTRACT_ONLY | F7, optional V1. |
| Knowledge Observer/Learning | CONTRACT_ONLY / EXTERNAL_DEPENDENCY | F8, post-V1. |
| Workspace-facing contracts, CLI adapter, MCP adapter | PARTIALLY_IMPLEMENTED / CONTRACT_ONLY | F2/F9; MCP after API. |
| clean-install/install-product qualification | NOT_IMPLEMENTED | F9. |

`UNCLASSIFIED_V1_CAPABILITIES = 0`

`EXISTING_CAPABILITY_WITHOUT_V1_DISPOSITION = 0`

## DAG, lanes and critical path

`F1 Service foundation -> F2 API contracts -> F3 attachment + F4 runtime/EP
reconciliation -> F9 installed control plane` is the critical path. `F1` and
`F2` are high-leverage; after F2, F5 Forecast, F6 sessions and consumer fixtures
can proceed in parallel. F7 quality is optional V1; F8 Knowledge is post-V1 and
cannot block V1. External work remains EP/Workspace/KB owned.

Autonomous Mission execution path has proven local Planner/State/Scheduler
segments; F4 plus EP contract/admission/Agent/receipt qualification remain the
external path. Portfolio intelligence has Review/Recommendation implementation;
F5 materialization and background-worker qualification remain Forge gaps.

## First wave and Goldens

Ready now: F1 operational-store/service composition, F2 versioned contracts,
F5 Roadmap/Forecast projection and F6 shared session infrastructure. Their DoR
is the merged decision contract; DoD is the JSON node contract. Goldens A-C,
G-H and J are V1-required; D is required once Portfolio Intelligence is in V1;
E optional; F post-V1; I required for multi-project V1 only.

Roadmap node -> DoR -> advisory Mission Candidate -> explicit Business and
Architecture approvals -> Mission Intake. The DAG creates no executable Mission.

## Readiness chains and build lanes

| Readiness chain | Known edges |
| --- | --- |
| Autonomous Mission execution | approved Mission → Planner/Living Graph **ALREADY_PROVEN** → submission/EP admission/Agent/receipt **EP_DEPENDENCY** → F4 reconciliation **FORGE_GAP** → completion **QUALIFICATION_GAP**. |
| Portfolio intelligence | repository/completed Mission → Review/Recommendation **ALREADY_PROVEN** → F5 Roadmap/Forecast/ranking **FORGE_GAP** → advisory candidate **FORGE_GAP** → Business review; no approval automation. |
| Quality learning | Action/EP outcome **CONTRACT_GAP** → F7 observer/proposal **FORGE_GAP** → governed hardening → effectiveness evidence. |
| Knowledge learning | evidence → F8 observer/export **FORGE_GAP** → KB certification **EXTERNAL_DEPENDENCY** → read-only consumption. |

No chain has an unknown edge. `AUTONOMOUS_MISSION_EXECUTION_UNKNOWN_EDGE = 0`,
`AUTONOMOUS_PORTFOLIO_INTELLIGENCE_UNKNOWN_EDGE = 0`,
`QUALITY_LEARNING_UNKNOWN_EDGE = 0`, `KNOWLEDGE_LEARNING_UNKNOWN_EDGE = 0`.

| Lane | Start gate | Blockers | Integration point |
| --- | --- | --- | --- |
| A Service foundation | merged decisions | none | F1 store/identity composition. |
| B API contracts | F1 contract shape | F1 | F2 version/capability envelope. |
| C Forecast | F2 | none | F5 projection contract. |
| D Sessions | F2 | Workspace consumer later | F6 shared session/proposal contract. |
| E Mission runtime | F1/F2 | EP engineering/admission gates | F4 Producer/receipt boundary. |
| F Quality | F2/F4 | Action evidence | F7 proposals. |
| H Workspace | F2 | Workspace-owned producer work | F9 control-plane Goldens. |
| J MCP | F2 | API/security qualification | read/explain/propose adapter. |

`UNSAFE_PARALLEL_LANES = 0`; each lane merges only against its named shared
contract. Node DoR is its predecessor and external gate set; node DoD is its
JSON completion/qualification contract; its listed `human_gates` is exhaustive.

## Consumer gates, installation and advisory candidates

Workspace V1 requires F2 for Product Vision, Portfolio, Candidates,
Business/Architecture refinement, decisions/evidence and health; F5 for
Roadmap/Forecast; F4 for Mission/Living Graph/runtime status; and F9 for
attachment and EP views. Quality is optional and Knowledge is post-V1. Workspace
implementation remains Workspace-owned; these are consumer gates only.

Clean-install chain: embedded schemas/baselines/migrations -> F1 service ->
F2 discovery -> F3 EP attachment -> Workspace connection -> candidate and
approvals -> F4 Action/receipt -> Forge reconciliation -> F9 Golden. The V1
exit requires `SOURCE_REPOSITORY_RUNTIME_DEPENDENCIES = 0` and package,
restart, negative-security, version-negotiation and cross-product consumer
qualification.

The following are advisory implementation Mission Candidates, never approved
Missions: **Service Foundation** (F1; installation value; store/identity/restart
evidence); **Canonical Forge Contracts** (F2; adapter safety; version/conflict
evidence); **Project Attachment and Runtime Reconciliation** (F3/F4; bounded
execution value; EP-gate/receipt evidence); **Portfolio Projections and
Refinement Sessions** (F5/F6; governed planning value; provenance/audit
evidence); and **Installed Control Plane Qualification** (F9; product release
value; Golden evidence). Each requires its predecessor gate, has repository
impact limited to its named capability, and may proceed only in its lane.

`IMPLEMENTATION_CANDIDATES_ARE_ADVISORY = TRUE`
