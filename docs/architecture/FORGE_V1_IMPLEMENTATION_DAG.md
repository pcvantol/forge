# Forge V1 Implementation DAG

> **Deployment reconciliation:** the installed Forge Server/storage migration,
> pinned EP binding and restart recovery are a minimum autonomy seam. Full LAN
> discovery, Workspace Client and installer productization remain parallel/post-
> autonomy nodes; see [Forge Server deployment target](FORGE_SERVER_DEPLOYMENT_TARGET.md).

> **Runtime planning reconciliation:** the canonical inner-Mission target is the
> [Living Mission Graph and cross-repository Engineering Action DAG](LIVING_MISSION_GRAPH_AND_CROSS_REPOSITORY_ACTION_DAG.md).

**AUTHORITY = DERIVED.** Source authority is the canonical Forge roadmap and product-owned EP/Workspace/Forge Platform contracts. This document never allocates peer implementation work.

## Current bootstrap reconciliation — 2026-09-07

```text
Forge Action-Derivation foundation
  -> installed EP producer + assurance
  -> installed Forge Server/EP consumer
  -> one approved Mission
  -> Forge derives Action A
  -> EP executes/finalizes A
  -> Forge reconciles A
  -> Forge replans same Mission from evidence
  -> Forge derives successor B without owner relay
  -> EP executes B
  -> optional B2/C from new evidence
  -> evidence-proven Mission completion
```

This is the first real Forge -> EP -> Forge autonomy proof. It is deliberately stronger than a predeclared `A -> B` scheduler script.

## Critical corrections

- Forge owns the Mission, Action derivation, per-Action repository target and hard logical dependency graph.
- EP owns admission, execution-resource scheduling, repository/resource leases, Agent/provider capacity, validation/review/repair, finalization and canonical execution evidence.
- EP may persist/enforce the producer-supplied dependency snapshot; it does not invent engineering dependencies.
- Workspace is not a runtime prerequisite for the first inner-Mission canary.
- General Agent fleet/distributed execution and multi-repository parallel mutation do not block the first inner-Mission canary.
- Multi-repository Action DAG execution is nevertheless a core follow-on Runtime qualification, not a replacement for the first serial proof.
- Mission completion is derived from current success evidence, not from completion of the initial Action list.

`OWNER_SUPPLIES_APPROVED_MISSION_NOT_ACTION_SCRIPT = TRUE`
`MISSION_COMPLETION_IS_EVIDENCE_DERIVED = TRUE`
`ROADMAP_DAG_IS_NOT_LIVING_MISSION_GRAPH = TRUE`

## Capability inventory

| Capability | Current status | Disposition |
| --- | --- | --- |
| Forge governance/Mission/Action-Derivation foundation | QUALIFIED FOUNDATION | Keep; feed live Runtime integration. |
| EP submission/readback/terminal evidence | PRODUCER CAPABILITY | Reuse canonical authenticated HTTP. |
| Installed Forge Server / peer binding | IMPLEMENTATION/QUALIFICATION LANE | Required before live inner-loop canary. |
| Forge exact receipt reconciliation | IMPLEMENTATION LANE | Required before replanning from live evidence. |
| Dynamic same-Mission `reconcile -> replan -> derive successor` | TARGET RUNTIME GAP | First autonomy canary. |
| Per-Action repository target | TARGET RUNTIME GAP | Required before cross-repository Mission graph. |
| Forge-owned hard `depends_on` snapshot | BOOTSTRAP SEED EXISTS | Generalize from current Action dependencies. |
| Multiple independently eligible Actions in flight | TARGET RUNTIME GAP | Second cross-repository canary. |
| EP dependency enforcement/resource/capacity separation | EP-OWNED TARGET | Consume producer contract; Forge does not schedule resources. |
| Evidence-gated cross-repository artifact unlock | CROSS-PRODUCT TARGET | Second canary; Forge Platform manifest is reference scenario. |
| Project Intelligence / outer Mission loop | FOLLOW-ON CORE PRODUCT | Consumes completed Mission evidence. |
| Workspace Roadmap/DAG Governance | FOLLOW-ON CORE PRODUCT | Not required for first machine loop. |

## First autonomy DAG — dynamic inner Mission loop

```text
          approved Mission
                |
                v
       Forge Mission Planner
                |
                v
          derive Action A
                |
                v
        immutable materialization
                |
                v
              EP
     execute/review/repair/finalize
                |
                v
        terminal evidence A
                |
                v
       Forge exact reconcile
                |
                v
        refresh Project Context
                |
                v
      evaluate Mission success
          /              \
       complete          work remains
         |                    |
         v                    v
 Mission COMPLETE       replan graph
                              |
                              v
                     derive B / B2 / C
                              |
                              +----> EP ...
```

Qualification must prove that the owner does not predeclare B and sends no message between A and the successor decision.

## Second autonomy DAG — cross-repository dependencies and parallel eligibility

```text
Mission Planner / Living Mission Graph
       |
       +--> EP-A2  target=engineering-platform -----+
       |                                             |
       +--> FP-A2  target=forge-platform --------+   |  independent => concurrently eligible
                                                  |   |
EP-A5 publish qualified EP artifacts <------------+---+
       |
       | hard evidence dependency
       v
FP-A3 final component manifest
  target=forge-platform
  depends_on=[EP-A5, FP-A2]
       |
       v
FP-A4 installer qualification
```

The graph expresses logical dependencies only. EP separately decides whether an eligible Action may actually run based on leases, Agent capabilities and capacity.

## Dependency semantics

A hard Action edge means the successor is not eligible until the required predecessor terminal-success evidence exists. The edge may also name required predecessor evidence, for example published artifact identity, artifact SHA-256, source revision and qualification/provenance references.

Do not infer hard dependencies from project/repository membership. Do not use Action dependencies to encode execution-resource exclusion or capacity.

A materialized dependency snapshot is immutable. Forge may change only not-yet-materialized future graph nodes/edges after new evidence.

## Project Intelligence planning DAG

The Roadmap/Project Intelligence loop is separate from the Living Mission Graph:

```text
canonical Project Context
        |
        v
dynamic inference
   /             \
Expected Missions  Roadmap/DAG Insights
   |               |
Mission Candidates Roadmap Change Proposals
   \               /
    governed decisions
           |
           v
     approved Mission
           |
           v
   Living Mission Graph
           |
           v
          EP
           |
        evidence
           |
           v
 refreshed Project Context
```

Canonical distinctions:

- Roadmap/Capability DAG = approved project direction;
- Expected Mission = dynamic non-canonical likely future work;
- Mission Candidate = advisory possible next Mission;
- Mission = governed canonical work;
- Living Mission Graph = dynamic Intent/Action dependency graph inside one Mission;
- Roadmap Change Proposal = governed before/after Roadmap changeset.

## V1 architecture preparation seams

```text
stable Mission/Intent/Action identities
        |
per-Action target repository + write scope
        |
hard dependency edge identity + predecessor evidence requirement
        |
immutable materialized Action/dependency snapshot
        |
Project Context snapshot/digest provenance
        |
exact EP receipt/artifact identity
        |
evidence-driven Mission completion
```

These seams are required before the Runtime can safely generalize beyond the first serial canary.

## Real qualification contracts

### Dynamic inner-loop canary

One approved Mission enters Forge. Forge itself derives A, EP executes A, Forge reconciles A and derives a successor only if evidence says work remains. The sequence continues until Forge can prove Mission completion.

Required proof:

```text
FORGE_DERIVES_ACTION_A = TRUE
FORGE_RECONCILES_A_AND_REPLANS = TRUE
FORGE_DERIVES_SUCCESSOR_WITHOUT_OWNER_MESSAGE = TRUE
SUCCESSOR_MAY_DIFFER_FROM_INITIAL_FORECAST = TRUE
FORGE_CAN_INSERT_NEW_ACTION_AFTER_NEW_EVIDENCE = TRUE
OWNER_IS_NOT_ACTION_MESSAGE_BUS = TRUE
MISSION_COMPLETION_DECIDED_FROM_EVIDENCE = TRUE
```

### Cross-repository DAG canary

A later approved Mission spans at least two repositories. Forge derives per-Action targets and hard dependencies. At least two independent Actions become concurrently eligible, while a dependent successor remains closed until predecessor evidence exists.

Required proof:

```text
FORGE_DERIVES_CROSS_REPO_DEPENDENCIES = TRUE
INDEPENDENT_REPOSITORIES_BECOME_CONCURRENTLY_ELIGIBLE = TRUE
DEPENDENT_ACTION_NEVER_EXECUTES_EARLY = TRUE
ARTIFACT_EVIDENCE_UNLOCKS_SUCCESSOR = TRUE
EP_RESOURCE_POLICY_REMAINS_SEPARATE_FROM_FORGE_PLAN = TRUE
MISSION_REPLANS_AFTER_PARALLEL_RESULTS = TRUE
```

The Execution Agent + Forge Platform installer-role Mission is a preferred real dogfood candidate after the corresponding EP multi-execution/lease/capacity capability is qualified.

## Authority boundaries

| Boundary | Owner |
| --- | --- |
| Mission objective/boundary governance | Applicable human governance |
| Mission/Intent/Action reasoning and hard logical dependencies | Forge |
| Per-Action repository target/write scope planning | Forge |
| Immutable submission/admission/run/finalization/receipt | EP |
| Dependency enforcement of the submitted snapshot | EP |
| Repository/resource locks and execution capacity | EP |
| Execution artifact publication | Producing product/repository through EP delivery |
| Forge Platform component composition/manifest | Forge Platform |
| Human projection and decisions | Workspace |

## Readiness chain

```text
FIRST INNER-MISSION CANARY:
installed Forge/EP readiness
  -> derive A
  -> EP A
  -> reconcile/replan
  -> derive successor without owner relay
  -> evidence-proven Mission completion

SECOND CROSS-REPO CANARY:
per-Action repository target
  + multiple Action persistence/in-flight state
  + EP multi-execution/lease/capacity qualification
  -> Forge cross-repo depends_on graph
  -> independent Actions concurrently eligible
  -> evidence-gated successor unlock
  -> replan after parallel results
```

Project Intelligence/Workspace governance and universal installer productization are not inserted into the first inner-loop readiness chain.

## Safe parallelism

- The first dynamic Mission canary may remain serial; it proves intelligence/replanning, not parallelism.
- The second canary must separate logical dependency from execution-resource constraints.
- Different repositories may become concurrently eligible when Forge declares no dependency.
- EP can still delay either Action for repository/resource/Agent/provider reasons.
- Same-repository parallel mutation is a separate, stricter qualification and is not implied.

## Roadmap-to-action rule

A derived node becomes ready only when its actual producer evidence exists. A source merge is not automatically a published artifact. A published artifact without required qualification evidence is not automatically a satisfied hard dependency. Expected Missions/Mission Candidates are not executable authority.

Reconcile this DAG whenever canonical Forge, EP, Forge Platform or Workspace authority changes.
