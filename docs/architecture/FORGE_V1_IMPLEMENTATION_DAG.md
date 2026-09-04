# Forge V1 Implementation DAG

**AUTHORITY = DERIVED.** Source authority is the Product Model, Productization
Reconciliation, V1 Decision Contract, canonical roadmap and cross-product
producer contracts. The JSON sibling is the deterministic source for validation.

## Capability inventory and dispositions

Implemented/bootstrap capabilities retained and adapted: Mission Intake,
Planner, Mission State, Scheduler, Repository Truth, Business/Architecture
domains, Recommendation/Architecture Review engines and EP adapter. They are
not standalone V1 qualification evidence. Runtime Service, application API,
attachment, Forecast, Workspace/MCP adapters and observers are contract-only or
not implemented. No capability is unclassified.

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
