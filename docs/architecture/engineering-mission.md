# Forge Mission-driven Engineering

## Purpose and boundary

A **Mission** is Forge's highest operational engineering artifact and the
Architect-approved engineering contract. It defines the engineering objective,
architectural boundaries, success criteria, and constitutional constraints for
a coherent outcome. A Mission does not prescribe individual Engineering
Intents, an Intent sequence, Runtime Prompts, or execution steps.

The target runtime semantics for evidence-driven replanning, cross-repository
Action dependencies and parallel eligibility are defined in
[Living Mission Graph and cross-repository Engineering Action DAG](LIVING_MISSION_GRAPH_AND_CROSS_REPOSITORY_ACTION_DAG.md).

This is an architecture reconciliation only. It introduces no Mission Planner
implementation, scheduler, storage migration, Runtime, provider, Execution
Host, Studio, repository operation, or autonomous execution.

## Admission from the product lifecycle

A Mission is not an opportunity, a roadmap item, or a Mission Candidate. The
Business Workspace owns the latter together with portfolio prioritisation,
value, and strategic alignment. A Mission Candidate reaches Architecture
Review only after explicit Business Owner approval. The Platform Architect may
then create and approve the Mission for Engineering. Only that approved Mission
may enter Forge. Candidate maturity, Business Review, and Architecture Review
are defined in the [Product Model](product-model.md). The [Governance Profile](governance-model.md)
determines the assigned approvers and permitted execution authority, never
Mission admission stages or the Mission contract.

## Canonical hierarchy and feedback loop

```text
Vision
  ↓
Architecture
  ↓
Roadmap
  ↓
Mission
  ↓
Mission Planner / Living Mission Graph
  ↓
Engineering Intent
  ↓
Engineering Action
  ↓
Runtime Prompt
  ↓
Execution Host
  ↓
Repository
  ↓
Evidence
  ↓
Mission Planner / Living Mission Graph
```

The loop is deliberate: repository and execution evidence continuously informs
the Mission Planner's next planning decision. The approved Mission remains
stable while the remaining Intent/Action plan may change.

## Mission and human governance

Humans approve Missions and remain responsible for governance. They do not
approve every Engineering Intent or every ordinary Action iteration inside the
approved boundary. The approved Mission is the stable human contract; Forge is
responsible for iterative engineering planning inside it. Evidence never
broadens a Mission's objective, boundaries, success criteria, destructive
authority, security authority, or constitutional constraints without further
human governance.

In the Solo profile, a shared Business Owner and Platform Architect identity
still creates distinct auditable approval records before Engineering; migration
to a profile with separate people needs no Mission migration.

## Mission Intake

**Mission Intake** is the CLI-owned admission step for an approved Mission
Document. It validates the approved contract and transforms it into Mission
State for deterministic execution. It is not Mission Planner: Mission Planner
is Forge planning responsibility for dynamic Intents and Actions within an
approved Mission. Intake neither creates executable Missions nor grants
Business or Architecture Approval.

The operational placement and later autonomous recommendation loop are
canonical in the [Runtime Evolution Roadmap](runtime-evolution-roadmap.md).

## Mission Planner and Living Mission Graph

The **Mission Planner** owns engineering planning, sequencing, dependency
management, progress evaluation, creation of Engineering Intents and Actions,
and reprioritisation. Its active plan is the **Living Mission Graph**.

The Planner evaluates real execution/repository evidence after every material
Action result. It may create, supersede, merge, split or retire remaining
Intents; derive new Actions; insert new hard dependency edges; remove no-longer
required planned work; and release more than one independent eligible Action.
It must preserve the Mission contract.

A human owner therefore supplies the approved Mission boundary rather than a
predeclared Action script. Forge may derive `A`, reconcile A, then determine
that `B`, `B2` and `C` are required without the owner relaying each result or
approving ordinary replanning.

The Mission Planner is not an execution scheduler, does not operate a
repository, does not approve Missions and does not weaken human governance. EP
owns actual admission, execution-resource scheduling, locks/leases, Agent
capacity and execution evidence.

## Dynamic Engineering Intents

An Engineering Intent is a tactical, model-independent planning artifact
created by the Mission Planner during Mission execution. It gives a coherent
body of work its rationale, boundaries, validation, expected evidence, and
architectural traceability. It may contain one or more Engineering Actions.

Active Intents are not static Mission membership. As the Planner learns from
repository evidence, an Intent may be created, superseded, merged, split, or
disappear. A historical Intent remains immutable: historical records preserve
the exact planning decision and its provenance, rather than being rewritten to
fit a later plan.

## Actions, dependencies, repositories, and evidence

An Engineering Action is the smallest intentional executable engineering unit.
The normal Action targets one repository and may declare hard dependencies on
other Actions, including Actions in other repositories. Forge owns those
logical dependency decisions; EP may persist and enforce the submitted
predecessor requirements during admission but does not invent the plan.

A materialized Action produces a provider-specific Runtime Prompt. The
Execution Host uses that prompt; the target Repository records the resulting
implementation reality; and Evidence makes that reality assessable by the
Mission Planner. Engineering Intents do not directly produce Runtime Prompts.

A materialized/submitted Action is immutable. Evidence changes the future graph
by creating or revising successor Actions; it never rewrites historical Action
identity or execution evidence.

## Mission completion

Mission completion is evidence-derived. It is not equivalent to completion of
the Actions that happened to be present in the first plan.

After each reconciliation Forge evaluates the approved Mission success
criteria against current evidence. If required work remains, Forge replans. If
new evidence makes forecast work unnecessary, Forge must not execute it merely
because it once existed. Only when the success criteria are actually satisfied
and no unresolved required work remains inside the approved boundary may the
Mission become complete.

The temporary Engineering Platform bootstrap runner is an external Execution
Host during bootstrap. It does not become Forge's planner, Runtime, repository
owner, or governance authority.

## Compatibility and qualification

Earlier Mission and Intent contracts preserve historical bootstrap provenance.
Their fixed membership and direct Intent-to-prompt language is not the
canonical target architecture and must not be extended.

Qualification proceeds in two steps: first one Mission proving dynamic
`Action -> evidence -> replan -> successor` without owner relay; then a later
cross-repository Mission proving Forge-derived dependency edges, parallel
eligibility for independent repositories, evidence-gated successor release and
continued replanning. The detailed proof is defined in the Living Mission Graph
architecture document.
