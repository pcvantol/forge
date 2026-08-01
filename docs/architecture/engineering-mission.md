# Forge Engineering Mission Model 1.10

## Purpose and boundary

An Engineering Mission is Forge's highest operational grouping artifact. It is
owned by a Workspace and groups a coherent, long-running engineering objective
into ordered Engineering Intents. A Mission records
objective, explicit boundaries, sequencing, declarative progress,
dependencies, aggregate evidence, and completion. It does not replace the
canonical bounded Intent described by Constitution Article 3.

This Increment provides immutable, dependency-free Python contracts and pure
validation only. It creates no Mission artifact, storage, planner, queue,
scheduler, Runtime Provider, runtime, Studio, repository operation, or
execution capability. A future Mission Runtime remains separate and deferred.

## Ownership and relationships

Workspace ownership remains above the Mission. Forge owns the durable Mission
record and its aggregate meaning; an Engineering Intent owns one tactical body
of work and contains its bounded Engineering Actions. An Action, rather than
an Intent, is executable and produces a Runtime Prompt. A future Runtime
Provider may render or consume that prompt, while an external Execution Host
executes it and returns evidence. Neither a Mission nor a Runtime Provider
approves, alters, or executes an Intent.

```text
Workspace
  ↓ owns
Engineering Mission (objective, scope, ordered membership, progress, completion)
  ↓ groups
Engineering Intent (tactical rationale, boundaries, validation, evidence, traceability)
  ↓ contains
Engineering Action (smallest intentional executable unit)
  ↓ produces
Runtime Prompt
  ↓ future consumer
Runtime Provider
  ↓ external boundary
Execution
  ↓ produces
Evidence
```

## Immutable record

`EngineeringMission` is versioned at schema `1.10` and contains a stable id,
revision, title, objective, explicit `MissionScope`, ordered revision-pinned
`MissionIntentMembership` records, `MissionDependencies`, optional declared
evidence, status, and completion declaration. Membership order is consecutive
and is a grouping and sequencing declaration only, never a scheduler command.

`MissionProgress` is a declarative snapshot derived from the Mission's pinned
memberships and supplied Intent lifecycle states. It counts only `VERIFIED` or
`ARCHIVED` Intents as complete. It does not mutate the Mission, infer status,
or retrieve an Intent.

`MissionDependency` records an external version-pinned prerequisite. It is
provenance, not automatic dependency resolution. `MissionEvidence` is a
reproducible SHA-256-pinned reference and is never fetched by this model.

## Lifecycle

| Status | Meaning | Permitted next status |
| --- | --- | --- |
| `CREATED` | The Mission exists but has no active work. | `PLANNING` |
| `PLANNING` | Humans are organizing its bounded Intent sequence. | `ACTIVE` |
| `ACTIVE` | Its approved Intents may progress independently. | `BLOCKED`, `COMPLETED` |
| `BLOCKED` | A declared Mission cannot currently progress. | `ACTIVE` |
| `COMPLETED` | All member Intents and aggregate completion evidence are present. | `ARCHIVED` |
| `ARCHIVED` | The completed Mission is retained as history. | none |

There are no skipped transitions and no transitions out of `ARCHIVED`.
Lifecycle transitions only change status. They do not create plans, approve
Intents, operate a Runtime Provider, or execute work.

## Completion and evidence

`MissionCompletion` requires a terminal `VERIFIED` or `ARCHIVED` declaration
for every exact Intent id/revision membership. It aggregates reproducible
repository, validation, and constitutional-compliance evidence. A Mission can
enter `COMPLETED` or `ARCHIVED` only with such a complete declaration.

This is an aggregate closure rule. Every Engineering Intent still owns its own
approval, lifecycle, implementation, validation, repository evidence, and
constitutional meaning. Mission completion adds no shortcut around those rules
and provides no execution authority.

## Runtime Provider boundary

Missions do not produce or execute Runtime Prompts. Runtime Prompt Generation
is a per-Action derivation, and future Runtime Providers stay consumers of
provider-specific transient prompts. A Runtime Provider cannot infer Mission
membership, advance Mission status, or treat Mission completion as permission
to execute.

## Next boundary

The next increment should implement the Bootstrap Mission Scheduler using
Engineering Actions as released executable units. It must preserve this
Mission's strategic, local boundary and must not introduce Runtime execution,
providers, repository operations, or autonomous approval.
