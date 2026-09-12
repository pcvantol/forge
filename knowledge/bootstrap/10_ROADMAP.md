# Forge Roadmap

## Purpose and authority

This is Forge's canonical strategic roadmap. Roadmap presence does not authorize execution; bounded Engineering Intents/Missions and governance remain required. Forge evolves capability-first while preserving repository-first knowledge, human governance and execution-host independence.

## CI integration and the post-E2E Server — explicit delivery sequence

The [inner-loop CI plan](../../docs/roadmap/FORGE_INNER_LOOP_CI_V1.md) covers the
FULL Mission Candidate -> canonical Business/Architecture approvals -> intake
with zero Actions -> dynamic execution -> evidence-derived completion flow.
EP is a stateful HTTP mock; Forge's application services, adapter, validation,
persistence and reconciliation remain real. External LLM/OS fixtures keep CI
reproducible and free of live credentials/provider spend. FCI-CI is a planned
required PR/main/release gate, independent of the current live canary or Console.

LATER, the [deterministic outer-loop CI plan](../../docs/roadmap/FORGE_OUTER_LOOP_CI_V1.md)
and [DAG](../../docs/roadmap/forge-outer-loop-ci-v1.json) reuse that qualified
suite: completed M1 -> refreshed Project Context -> Expected Missions/Candidate
-> applicable explicit approvals -> M2 inner loop -> completion or no-work.
The five FCO nodes remain PLANNED. Neither a suggestion nor M1 completion grants
M2 execution authority. Mock-CI results are not live EP/provider proof.

After the current live E2E run and review of its actual outcome, deliver the
standalone Forge Server as the backend milestone of existing FSH-SERVICES:
see [runtime sequencing](../../docs/architecture/runtime-evolution-roadmap.md)
and [hosting roadmap](../../docs/roadmap/FORGE_CONSOLE_HOSTING_V1.md).
It reuses the existing runtime core, its own API/service lifecycle and CENTRAL;
no Console, relay or outer-loop completion is needed to ship the server first.
A RuntimeService class or storage CLI is not already an installed daemon.
These plans do not change current execution authority or activate new CI jobs.

## Forge Operations Console — planned instance administration

`FORGE::OPERATIONS_CONSOLE_V1` is a future minimal operational dashboard for
one Forge Server instance, organized comparably to the EP Operations Console:
**Local host components, Logs, Configuration, Active Missions and Historical
Missions**. Its [architecture](../../docs/architecture/FORGE_OPERATIONS_CONSOLE_V1.md),
[scoped roadmap](../../docs/roadmap/FORGE_OPERATIONS_CONSOLE_V1.md) and
[documentary DAG](../../docs/roadmap/forge-operations-console-v1.json) define
read-only projections, controlled configuration and safe pause/resume requests
through Forge-owned application services. Forge remains headless without it.

Priority is `POST_AUTONOMY`; all eight FOC nodes remain **PLANNED**. Contracts
FOC-0 precede read APIs FOC-1 and the authenticated shell FOC-2; their joint
consumers are host/logs FOC-3, Missions FOC-4 and configuration FOC-5. FOC-6 adds
guarded controls after Mission views; FOC-Q qualifies the integrated installed
console. The JSON records the exact dependencies. This feature is not a new
first-E2E prerequisite and changes no executable bootstrap graph or live Mission.

This is instance administration, not a revival of Forge Studio or a replacement
for Workspace's project, Mission-authoring, approval, chat and policy UX.
EP retains execution/assurance/Git mutation; Forge Platform retains installation
and host-process lifecycle. The browser owns neither planning nor execution,
has no direct database access, and cannot turn logs, cached status or a save
acknowledgement into canonical evidence or authority. Implementation, qualification
and deployment require later bounded work; this record authorizes none of them.

## Project Hygiene and Repository Reconciliation — documented target

`FORGE::PROJECT_HYGIENE_AND_REPOSITORY_RECONCILIATION_V1` extends Project
Intelligence with scoped post-EA/provider delta observations, bounded periodic
and on-demand scans, a source-backed Branch Provenance Ledger and reconciliation
cases. See the [architecture](../../docs/architecture/PROJECT_HYGIENE_AND_REPOSITORY_RECONCILIATION.md),
[scoped roadmap](../../docs/roadmap/PROJECT_HYGIENE_V1.md) and
[documentary DAG](../../docs/roadmap/project-hygiene-v1.json).

Local sequence: EP `HY-E` observations -> Forge `HY-F` cases/projections ->
`HY-S` semantic/residual reasoning; EP `HY-C` reuses safe cleanup primitives;
`HY-Q` joins their contracts. Workspace read-only `HY-WO` need not wait for
mutation UI `HY-WM`; Forge Platform `HY-P` preserves release/install authority.
All implementation/qualification nodes remain PLANNED. This changes no executable
programme graph, live grant, package version or installed runtime.

EP own-run cleanup is not a Mission. A Forge reconciliation case is not a Mission
or execution authorization either; genuine residual product work follows existing
governed engineering intake. Semantic equivalence alone never authorizes deletion.
Protected/active/unknown-owned work and untracked/ignored runtime data are retained.
Only relevant source/operation conflicts block a release: neither this full
capability nor deletion of unrelated old branches is a new first-canary gate.

## Policy governance and native release management — documented target

The coordinated `POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES_V1` increment defines
[policy ownership and lifecycle](../../docs/architecture/POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES.md),
a [source-pinned policy inventory](../../docs/architecture/POLICY_INVENTORY.md), and
the [scoped implementation roadmap/DAG](../../docs/roadmap/POLICY_GOVERNANCE_V1.md)
with its [machine-readable documentary graph](../../docs/roadmap/policy-governance-v1.json).
These are documentation deliverables; the services and management UI remain PLANNED.

Forge owns planning/progression and native `VERSION_RELEASE_MANAGEMENT_V1`;
EP owns effective execution/assurance profiles and operational repair accounting;
Workspace owns Policy & Automation UX; Forge Platform owns policy-aware artifact
composition and installation. Policies, grants, runtime consumption and hard
implementation limits are distinct. A new candidate SHA does not reset repairs.

Local progression is `POL-0 -> POL-F -> POL-B -> POL-Q`, with native release
planning `POL-F -> VR-F -> VR-Q`. EP-owned POL-E/VR-X join at the corresponding
integration gates; POL-WC can be designed in parallel, POL-W is post-autonomy UI,
and POL-P qualifies production installer composition after release evidence.
The scoped DAG does not alter the executable bootstrap node set or live grants.
Relevant policy/provenance seams must be real for the operations being claimed;
full UI or migration of every legacy setting is not a new first-canary prerequisite.
Pending Forge #48 and #49 retain their respective graph and implementation lanes;
this documentation neither merges them nor claims their features implemented.

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

The minimal serial product slice is source-delivered and deterministically
qualified: an approved provider-derived scope may start with no owner-supplied
Actions, derive and validate A, replan only after canonical A evidence, append a
previously absent B without rewriting A, survive restart with B current, and
complete only from explicit per-criterion evidence. This is source
qualification, not the live Forge→EP canary.

Dynamic successor containment additionally requires B (and every later
provider-derived successor) to carry an immutable current-snapshot binding to
an `UNSATISFIED` approved Mission criterion or to a causally evidenced blocker
created by current Mission work. Same-repository optional improvements remain
follow-up rather than executable Mission work. No general autonomous
progression budget exists yet; that is separate non-canary hardening.

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

`DYNAMIC_SUCCESSOR_CAPABILITY = SOURCE_DELIVERED_QUALIFIED`
`EVIDENCE_DERIVED_COMPLETION = SOURCE_DELIVERED_QUALIFIED`
`F_E2E = NOT_EXECUTED`
`CONFIGURATION_BLOCKER = STILL_OPEN`
`GOVERNANCE_BLOCKER = STILL_OPEN`

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
