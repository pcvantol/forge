# Forge Engineering Action Architecture 1.12

## Purpose and boundary

An **Engineering Action** is Forge's smallest intentional engineering unit and
the executable unit for one bounded change, documentation update, repair,
qualification step, or Runtime Prompt production. It is contained by one
dynamic Engineering Intent; an Intent may contain one or more Actions.

The target semantics for cross-repository dependencies and evidence-driven
replanning are defined in
[Living Mission Graph and cross-repository Engineering Action DAG](LIVING_MISSION_GRAPH_AND_CROSS_REPOSITORY_ACTION_DAG.md).

Bootstrap Mission Scheduler 2.0 implements an earlier local Action contract,
deterministic scheduling, dependencies and Action provenance in Runtime Prompt
generation. Its single-in-flight and runner-wide repository assumptions are
bootstrap implementation limits, not target invariants.

## Canonical hierarchy

The established Action boundary remains explicit inside the richer feedback
loop:

```text
Mission
  ↓ governs
Mission Planner
  ↓ creates and reconciles
Engineering Intent
  ↓ contains
Engineering Action
  ↓ produces
Runtime Prompt
```

The full evidence-driven target loop is:

```text
Vision → Architecture → Roadmap → Mission → Mission Planner / Living Mission Graph
→ Engineering Intent → Engineering Action → Runtime Prompt → Execution Host
→ Repository → Evidence → Mission Planner / Living Mission Graph
```

| Level | Responsibility | Must not do |
| --- | --- | --- |
| Mission | Is the Architect-approved contract for objective, boundaries, success criteria, and constitutional constraints. | Predeclare an immutable Action list or become executable. |
| Mission Planner / Living Mission Graph | Iteratively creates/reconciles Intents, Actions and hard dependencies from evidence. | Replace human governance or execute work. |
| Engineering Intent | Preserves tactical rationale, boundaries, validation, evidence, and traceability as a dynamic planning artifact. | Generate a Runtime Prompt directly or execute itself. |
| Engineering Action | States one bounded executable outcome, target repository/write scope and hard predecessor requirements. | Expand its Intent/Mission, own execution resources, or redefine architecture. |
| Runtime Prompt | Carries the provider-specific execution artifact generated from a materialized Action. | Become canonical engineering knowledge. |
| Execution Host / EP | Performs admitted bounded work and returns canonical execution evidence. | Invent Forge planning dependencies. |
| Repository | Holds implementation reality created by execution. | Authorize or plan work. |
| Evidence | Records assessable repository outcomes for future planning. | Authorize or execute work. |

## Action target

The normal V1 Action targets exactly one repository. The materialized Action
snapshot must carry the stable target repository identity and bounded write
scope needed by EP admission. Cross-repository outcomes should normally be
decomposed into independent repository-targeted Actions connected by hard
`depends_on` edges.

This makes execution evidence, locks/leases, ownership and retries explicit.
A future atomic multi-repository Action requires a separately qualified contract
and is not implied by this model.

Conceptual target fields include:

```text
id / revision
mission_id / mission_revision
intent_id / intent_revision
target_repository_id
write_scope
objective
acceptance / expected_evidence
depends_on[]
dependency_evidence_requirements
```

## Hard `depends_on` semantics

`depends_on` expresses a **Forge-owned hard logical dependency**. A successor is
not execution-eligible until each required predecessor has terminal success and
the predecessor evidence required by the edge exists.

Dependencies may cross repository boundaries. Examples include:

- an installer manifest Action waiting for a producer's qualified artifact;
- a documentation/client Action waiting for a versioned API contract;
- a release Action waiting for package publication and validation evidence.

`depends_on` does not mean:

- “same repository”;
- “same project”;
- preferred ordering;
- Agent/provider capacity;
- repository lock contention;
- forecast likelihood.

Those concerns remain separate. Forge plans logical dependencies. EP owns
admission, execution-resource exclusion and capacity.

## Materialization and immutability

An unmaterialized graph node may be changed, split, superseded, reordered or
removed by Forge as new evidence arrives. Once an Action is materialized for
submission its execution identity, target, objective, dependency snapshot and
expected evidence are immutable.

If evidence changes the required work, Forge creates/revises future graph nodes
or edges. It never rewrites an already materialized or executed Action to make
history fit the new plan.

## Why the Action boundary exists

An Intent preserves tactical meaning across a coherent body of engineering:
why it exists, its boundaries, how it is validated, expected evidence, and its
architectural traceability. That scope can legitimately include several
independent changes, including changes in different repositories.

Treating an Intent as one executable prompt collapses tactical meaning into
provider wording and prevents the Runtime from expressing safe parallel work
and precise hard dependencies. Actions are therefore the graph nodes that
cross the planning-to-execution boundary.

## Scheduler and EP boundary

Forge may release more than one dependency-eligible Action from one Mission.
Each Action is submitted independently with its immutable repository/dependency
snapshot. EP validates the producer-supplied predecessor requirements, then
applies its own admission, repository/resource lease, Agent capability and
capacity rules.

A dependency wait and a resource wait are different facts:

```text
WAITING_DEPENDENCY       -> Forge-planned predecessor evidence is absent
WAITING_RESOURCE/LEASE   -> plan allows execution but EP cannot safely admit it yet
WAITING_CAPACITY         -> plan allows execution but qualified execution capacity is unavailable
```

EP enforcing a submitted dependency does not make EP the planner.

## Evidence-gated successor example

For a Mission that makes EP Execution Agents installable, Forge may derive:

```text
EP-A5 publish qualified server/agent artifacts
  -> evidence: artifact identity + SHA-256 + source revision + qualification refs

FP-A3 final Forge Platform component manifest
  depends_on = [EP-A5, FP-A2-installer-support]
```

`FP-A3` may not finalize merely because EP source is merged. It requires the
actual installable artifact evidence specified by `EP-A5`.

## Compatibility and next increments

The existing `EngineeringAction.dependencies` field is the bootstrap seed for
this graph, but the current scheduler permits only one in-flight Action and the
current runner binds one repository to the whole runner. Target implementation
must move repository identity to the Action/submission boundary and support
multiple independently eligible in-flight Actions.

First qualify dynamic evidence-driven Action derivation inside one Mission.
Then qualify cross-repository dependencies and safe parallel eligibility using
real EP execution evidence.
