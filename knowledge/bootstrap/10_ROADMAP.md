# Forge Roadmap

## Purpose and authority

This is Forge's canonical strategic roadmap. Roadmap presence does not authorize execution; bounded Engineering Intents/Missions and governance remain required. Forge evolves capability-first while preserving repository-first knowledge, human governance and execution-host independence.

## Strategic progression

```text
Bootstrap -> Foundation -> Self Engineering -> Runtime -> Production
```

Foundation is complete. Self Engineering is underway. Runtime and Production remain governed future maturity states rather than implied implementation commitments.

## Current bootstrap autonomy critical path — 2026-09-06

The immediate objective is the shortest safe route to a real autonomous Forge operating loop, not completion of every future EP/Workspace productization capability.

`AUTONOMY_BOOTSTRAP_DONE` is earned only when one approved Mission enters Forge, Forge itself derives a bounded Engineering Action, submits it through the installed canonical EP machine boundary, and EP persists/adopts it, performs a real repository mutation, validates/reviews/finalizes it, and exposes canonical terminal evidence. Forge must then observe and exactly reconcile that result, re-evaluate the same Mission, derive any required successor work, and continue without the owner relaying prompts or results until Mission completion is evidence-proven. The critical dogfood proof remains `FORGE_CAUSES_REAL_FORGE_REPOSITORY_CHANGE_VIA_EP = TRUE`; the stronger autonomy proof is `OWNER_IS_NOT_ACTION_MESSAGE_BUS = TRUE`.

Current qualified Forge foundation includes canonical governance persistence, Mission Intake/amendment lineage, Action-Derivation evidence, G011/provider boundaries, token-preflight binding, governed reattempt lineage, a real Action-Derivation provider canary, post-canary Security qualification and immutable canary closure. PR #40 is merged; this foundation must not be reopened without regression evidence.

The current critical path is:

```text
installed EP producer + assurance evidence
  -> installed Forge Server execution consumer
  -> one approved Mission enters Forge
  -> Forge derives Action A
  -> EP executes/reviews/repairs/finalizes A
  -> Forge reconciles A + refreshes Project Context
  -> Forge re-evaluates the same Mission
  -> Forge derives successor B without owner message when work remains
  -> EP executes B
  -> Forge may insert B2/C or retire forecast work from new evidence
  -> Mission completion proven from evidence
```

The outer Portfolio/Mission-Candidate loop follows this inner-Mission autonomy proof; it is not a substitute for it.

### Critical-path corrections

1. **P-TRANSPORT is merged/closed.** EP already owns canonical HTTP submission/readback surfaces; Forge reuses them.
2. **Workspace is not required for the first autonomy canary.** Workspace remains human/project control plane and later projection/onboarding consumer.
3. **Owner gates are reserved for genuine authority expansion.** Engineering repair/validation/re-review and ordinary Action replanning inside an approved Mission should run autonomously.
4. **The first Forge canary is one dynamic Mission, not a predeclared A/B script.** The owner supplies Mission objective/boundary/success criteria; Forge derives and revises the Action plan.
5. **Mission completion is evidence-derived.** Finishing an initial Action list is not sufficient if new evidence exposes additional required work.
6. **Cross-repository parallelism is a separate follow-on qualification.** It must not delay the first dynamic inner loop, but it is a core Runtime capability rather than optional architecture trivia.

`P_TRANSPORT_HTTP_IS_CANONICAL_FORGE_SUBMISSION_TARGET = TRUE`
`WORKSPACE_ON_FIRST_AUTONOMY_CRITICAL_PATH = FALSE`
`OWNER_SUPPLIES_APPROVED_MISSION_NOT_ACTION_SCRIPT = TRUE`
`MISSION_COMPLETION_IS_EVIDENCE_DERIVED = TRUE`

## Installed Forge Server and peer discovery — target-productization lane

The canary's smallest Forge-owned prerequisite is an installed headless Forge Server with central product storage outside Git, stable instance identity, versioned HTTP application boundary, a pinned authenticated EP binding and restart-safe migration/recovery. The legacy repository-bound runtime must relocate without resetting grants, Missions or budgets and without dual writers. This is architecture-defined in [Forge Server deployment and peer-binding target](../../docs/architecture/FORGE_SERVER_DEPLOYMENT_TARGET.md).

LAN DNS-SD/mDNS candidate discovery, configured/unicast/tailnet bootstrap, Workspace peer binding and universal installer choreography are valid later productization work. They do not block the first Forge→EP→Forge loop; discovery never authorizes a peer or silently retargets an existing binding.

## Dynamic Living Mission Graph — first Runtime autonomy milestone

The canonical target is defined in [Living Mission Graph and cross-repository Engineering Action DAG](../../docs/architecture/LIVING_MISSION_GRAPH_AND_CROSS_REPOSITORY_ACTION_DAG.md).

Forge owns the active Intent/Action dependency graph inside an approved Mission. After each terminal EP result it reconciles evidence, refreshes Project Context, evaluates Mission success criteria, and may add, split, supersede, reorder or retire not-yet-materialized work. A materialized/submitted Action remains immutable.

The first real qualification must prove:

```text
FORGE_DERIVES_ACTION_A = TRUE
ACTION_A_EXECUTED_BY_EP = TRUE
FORGE_RECONCILES_A_AND_REPLANS = TRUE
FORGE_DERIVES_SUCCESSOR_WITHOUT_OWNER_MESSAGE = TRUE
FORGE_CAN_INSERT_NEW_ACTION_AFTER_NEW_EVIDENCE = TRUE
MISSION_COMPLETION_DECIDED_FROM_EVIDENCE = TRUE
OWNER_IS_NOT_ACTION_MESSAGE_BUS = TRUE
```

This replaces a weaker canary that would predeclare Action A/B and prove only automatic scheduling.

## Cross-repository Action DAG — second Runtime autonomy milestone

After the single-Mission inner loop is qualified, Forge must support Actions in multiple repositories with Forge-owned hard `depends_on` edges and per-Action repository targets.

Independent Actions in different repositories become concurrently eligible when the Living Mission Graph permits it. EP independently applies repository/resource leases, Agent capability and provider capacity. Different repositories do not imply independence; a hard cross-repository dependency remains closed until predecessor evidence satisfies its contract.

Qualification must prove:

```text
FORGE_DERIVES_CROSS_REPO_DEPENDENCIES = TRUE
INDEPENDENT_REPOSITORIES_BECOME_CONCURRENTLY_ELIGIBLE = TRUE
DEPENDENT_ACTION_NEVER_EXECUTES_EARLY = TRUE
ARTIFACT_EVIDENCE_UNLOCKS_SUCCESSOR = TRUE
EP_RESOURCE_POLICY_REMAINS_SEPARATE_FROM_FORGE_PLAN = TRUE
MISSION_REPLANS_AFTER_PARALLEL_RESULTS = TRUE
```

A suitable dogfood Mission is: make Engineering Platform Execution Agents production-ready and installable through Forge Platform. EP implementation/package Actions and Forge Platform installer-role work may advance in parallel, while the final platform component-manifest Action must depend on actual publication of qualified EP Server/Agent artifacts and their artifact digests/source revisions.

## Governance-minimal execution

Within an approved Mission boundary, ordinary implementation, validation, quality/security review, bounded repair, exact-head requalification, evidence reconciliation and Action replanning are engineering iterations rather than new owner decisions. Manual owner input remains reserved for actual authority expansion, destructive operation, wider write scope, weakened security invariants or materially ambiguous product decisions.

`BOOTSTRAP_MICRO_APPROVALS_EXPECTED = FALSE`
`EP_ENGINEERING_REPAIR_LOOP_AUTONOMOUS = TRUE`
`FORGE_ACTION_REPLAN_INSIDE_MISSION_AUTONOMOUS = TRUE`

## EP producer proof required by Forge

Forge trusts installed EP producer capability only through explicit producer/installed evidence. The first dynamic Mission canary requires an installed EP Server with authenticated submission/readback, terminal evidence, quality/security assurance and bounded repair semantics. General Agent fleet productization and multi-repository parallel execution are not prerequisites to the first inner-loop canary.

## Immediate executable Forge slice

The immediate Forge execution-integration slice is now:

1. preserve one approved Mission objective/boundary/success criteria;
2. let Forge derive the first bounded Action A from current Mission/Project Context;
3. materialize an immutable Action snapshot with exact repository/write-scope/dependency/provenance bindings;
4. persist intended submission identity/idempotency/correlation before the EP call;
5. submit through canonical EP HTTP;
6. observe exact canonical EP run/result/evidence;
7. reconcile terminal evidence idempotently in Forge;
8. refresh Project Context and evaluate Mission completion;
9. when work remains, let Forge derive/materialize successor B without an owner message;
10. repeat evidence-driven replanning until the Mission success criteria are proven.

Forge never writes the target repository directly and never reconstructs EP execution authority from logs, Console state or local process state.

## Project Intelligence and dynamic roadmap planning

Forge distinguishes:

- **Roadmap / Capability DAG** — approved canonical direction, milestones and dependencies;
- **Expected Mission** — dynamic, confidence-bearing inference from current Project Context; never canonical backlog authority;
- **Mission Candidate** — advisory concrete possible next Mission;
- **Mission** — governed canonical work;
- **Living Mission Graph** — dynamic Intent/Action dependency graph inside one approved Mission;
- **Roadmap/DAG Insight** — Forge inference that the approved plan may need structural change;
- **Roadmap Change Proposal** — explicit before/after changeset requiring applicable governance before canonical mutation.

Expected Missions and Roadmap DAG are not the Living Mission Graph. The Roadmap DAG concerns approved Mission/product sequencing; the Living Mission Graph concerns dynamic engineering work inside one Mission.

### Early architecture seams to establish

- stable roadmap/capability/DAG node and dependency identities;
- Project Context snapshot/digest provenance;
- Expected Mission / Mission Candidate / Mission identity separation;
- Living Mission Graph node/edge identity and immutable materialized Action snapshot;
- per-Action repository target and write scope;
- hard Action dependency semantics and dependency evidence requirements;
- evidence references usable by Workspace;
- decision type / required role metadata seam;
- semantic claim classification (`FACT / INFERENCE / FORECAST / RECOMMENDATION / DECISION`).

### Not on the first execution critical path

The first dynamic Forge -> EP -> Forge Mission canary does **not** require interactive DAG editing, probabilistic completion forecasting, automatic Roadmap reordering, full Workspace UI, LAN discovery, universal installer completion or multi-repository parallel execution. Those remain follow-on capabilities unless real evidence creates a dependency.

## Forge + Workspace V1 implementation programme

The V1 programme is dependency/capability driven. Cross-product milestones do not allocate another repository's implementation work. Derived DAG/dependency documents are indexes/projections, not product authority.

## L0 — Engineering Contract Foundation

Long-term L0 remains an EP-produced rich contract for packaged baselines, capability classification, Effective DoR/DoD, readiness, proof requirements, Human Gates, workflow projection, completion enforcement and immutable Action snapshots. The dynamic Mission Graph adds Forge-owned repository/dependency planning semantics; it does not move execution authority from EP.

## L1 / L1-R — Bootstrap evidence and Managed repository governance

These harden project-owned contracts, baseline provenance and generic repository desired-state/read-back evidence. Full productization is not a prerequisite for the first bounded canary when the target repository already satisfies its explicitly pinned execution contract.

## L2–L3 — Quality Learning

Observe eligible Action outcomes and propose governed hardening after a reliable Action/EP outcome contract exists. Zero automatic governance mutation.

## L4 — Workspace Quality Governance

Workspace presents governed projections and permitted human intent; it does not become runtime authority and does not block the first Forge -> EP -> Forge machine loop.

## L4-AI / L5–L10

AI exposure, Knowledge Learning, continuous dual learning and effectiveness/distribution qualification remain later maturity lanes. They consume canonical application/execution evidence and do not block the first autonomous execution proof.

## Authority and state rules

- Forge owns why/what: Mission semantics, Action derivation, repository targets, logical dependencies, replanning, completion reasoning and governance proposals.
- EP owns how: submission/admission, execution lifecycle, durable dependency enforcement of the producer-supplied snapshot, repository/resource leases, Agent/provider capacity, validation/review/repair, finalization, receipts and canonical execution evidence.
- Workspace owns human/project UX and evidence projections, never execution lifecycle or Forge reasoning authority.
- A materialized Action is immutable; the not-yet-materialized Living Mission Graph may change from evidence.
- Forge records intended Action/submission identity before EP submission; EP persists canonical submission/run evidence; Forge reconciles by exact identity.
- A retry never invents a second submission when the first POST outcome is ambiguous.
- Provider output is never directly executable authority.
- Reports, logs, browser selection and current checkout are not lifecycle authority.
- Forge inference, forecast or recommendation never silently becomes canonical Roadmap state.

## Dependency guidance

```text
FIRST INNER-MISSION AUTONOMY:
approved Mission
  -> Forge derives A
  -> EP executes A
  -> Forge reconciles + replans
  -> Forge derives B without owner relay
  -> optional B2/C from new evidence
  -> evidence-proven Mission completion

SECOND CROSS-REPOSITORY DAG QUALIFICATION:
one Mission spanning >= 2 repositories
  -> Forge derives per-Action repository targets + depends_on
  -> independent Actions concurrently eligible
  -> EP enforces resource/capacity separately
  -> predecessor artifact/evidence unlocks dependent Action
  -> Forge reconciles parallel results + replans
  -> Mission completion

OUTER LOOP:
completed Mission evidence
  -> Project Intelligence / Portfolio / Roadmap
  -> Mission Candidate / governance
  -> next approved Mission

PROJECT INTELLIGENCE PREPARATION (non-blocking):
Project Context contracts
  -> Expected Missions
  -> Mission Candidate reasoning
  -> Roadmap Change Proposal contracts
  -> Workspace role-aware governance projections
```

## Non-goals and authority constraints

- Forge does not become a second execution engine or repository-lock manager.
- EP does not become a planner or autonomously invent Forge dependency edges.
- Workspace does not become Forge planning or EP execution authority.
- Forge must not duplicate the existing EP submission/readback transport.
- Full Agent fleet/distributed productization must not be inserted onto the first inner-loop critical path.
- Multi-repository parallelism is a later explicit qualification, not an implication of the first serial canary.
- Expected Missions and Mission Candidates are not approved backlog or execution authority.
- Roadmap Change Proposals require applicable governance before canonical mutation.
- Product upgrades do not silently rewrite project/repository policy.
- Historical evidence and intentional compatibility require explicit classification before retirement.
