# Role-aware conversations V1 — Forge delivery plan

Increment `ROLE_AWARE_CONVERSATIONS_V1` refines existing F6 session
productization; it is not a replacement Mission engine or a new first-canary
prerequisite. See the [service design](../architecture/ROLE_AWARE_CONVERSATIONS_V1.md),
[documentary graph](role-aware-conversations-v1.json) and the
[owning Workspace plan](https://github.com/pcvantol/workspace/blob/main/docs/ROLE_AWARE_CONVERSATIONS_V1_ROADMAP.md).

The design is delivered only by protected owning merge. Every runtime node below
remains PLANNED; existing F1-F11 states/dependencies and bootstrap authorities are
unchanged. F6's existing Business/Architecture foundation is not retroactively
blocked by the complete three-lens UI or UX extension. The umbrella is a navigation
relationship, not an edge from F6 to its own children or from Workspace to F10.

## Bounded implementation sequence

| Node | Depends on | Delivery and qualification |
| --- | --- | --- |
| RC-FC | No runtime prerequisite for contract-first definition | Versioned turn/session/context/proposal/artifact and capability contracts; advisor-kind versus actor-role separation; shared fixtures and state mapping. |
| RC-FS | RC-FC + required F2 API/application-service subset | Durable admitted sessions, permission-filtered context, history/reopen, idempotent requests, cursor/readback and explicit retention. |
| RC-FA | RC-FS | Business/Architecture/UX advice adapters and request/result qualification using Forge-local provider policy; bounded calls, no implicit fan-out or ambiguous retry. |
| RC-FP | RC-FA | Version-bound proposals, decision routing/apply receipts and Candidate/design-only handoffs through existing governance; no direct Git writer or automatic Mission. |
| RC-FQ | RC-FP | Deterministic integrated service qualification for RC-T01..RC-T17 and RC-T20; real persistence/governance; external providers and EP mocked. |

RC-FC can be specified alongside Workspace RC-WC without requiring UI, server
fleet, installer, full policy programme, model-routing optimization or full F9.
RC-FS needs only the qualified authentication/project/version/idempotency/API
subset of F2. Do not mark all F2 complete based on that subset.

Business/Architecture advice can ship first with honest capability discovery;
UX enables only after its own request/result/preview checks. Partial delivery
never claims the full three-mode service. A selected runtime provider must
support the advice contracts; an Action-Derivation smoke is not sufficient proof.

## Cross-product joins and qualification

Workspace owns RC-WC -> RC-WS -> RC-WP -> RC-WQ. RC-WC consumes RC-FC; RC-WS
consumes RC-FS; RC-WP consumes RC-FP; RC-WQ consumes RC-FQ. There is deliberately
no reverse implementation edge from RC-FQ to RC-WQ. Workspace owns browser,
accessibility and five-language acceptance, including RC-T19; Forge owns service
correctness. Neither product claims qualification of its peer from its own tests.

RC-T17 reuses the qualified [inner-loop CI architecture](../architecture/FORGE_INNER_LOOP_CI_INTEGRATION_V1.md)
for Candidate -> separate approvals -> intake -> dynamic execution with mocked
EP. The full inner-loop suite is not made dependent on chat UI. RC-T18 belongs
to the later [outer-loop CI programme](FORGE_OUTER_LOOP_CI_V1.md); it does not
hold basic chat delivery hostage. It must later prove recommendations reenter
advisory conversations/Candidates without turning into approved Missions.

New executable service modules require >80% coverage with explicit negative
proof for authority, scope, idempotency, ambiguity and stale-state boundaries.
Documentation guards do not count as runtime or real-model quality proof. Live
provider/profile qualification, where required, is separately bounded and
budgeted; this increment performs none.

## Completion and parked scope

Service capability closure requires qualified RC-FC/FS/FA/FP/FQ evidence at exact
source/artifact versions. Full user journey additionally requires owning Workspace
RC-WQ. Rollout advertises actual supported versions/modes and retains existing
sessions/decisions across upgrade. No migration may synthesize historical approvals.

Deferred: autonomous advisor panels, image/design-provider integrations,
prototype execution, broad enterprise collaboration, new mandatory UX roles,
formal read-only EP execution support, and general model-routing optimization.
These are not implicit obligations of this design or the first live canary.
No existing canary, grant, retry/repair allowance, execution DAG, installed process,
Console programme or EP PR is changed.
