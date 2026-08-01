# Forge Engineering Action Architecture 1.11

## Purpose and boundary

An **Engineering Action** is Forge's smallest intentional engineering unit and
the executable unit for one bounded change, documentation update, repair,
qualification step, or Runtime Prompt production. It is contained by one
dynamic Engineering Intent; an Intent may contain one or more Actions.

Bootstrap Mission Scheduler 2.0 implements the local Action contract,
deterministic scheduling, and Action provenance in Runtime Prompt generation.
It still adds no Action storage, authoring workflow, Runtime, provider,
Execution Host, or execution implementation.

## Canonical hierarchy

```text
Vision → Architecture → Roadmap → Mission → Mission Planner → Engineering Intent →
Engineering Action → Runtime Prompt → Execution Host → Repository → Evidence →
Mission Planner
```

| Level | Responsibility | Must not do |
| --- | --- | --- |
| Mission | Is the Architect-approved contract for objective, boundaries, success criteria, and constitutional constraints. | Predeclare Intents or become executable. |
| Mission Planner | Iteratively creates and reconciles dynamic Intents from repository evidence. | Replace human governance or execute an Action. |
| Engineering Intent | Preserves tactical rationale, boundaries, validation, evidence, and traceability as a dynamic planning artifact. | Generate a Runtime Prompt directly or execute itself. |
| Engineering Action | States the smallest intentional executable unit within an Intent. | Expand its Intent, replace governance, or redefine architecture. |
| Runtime Prompt | Carries the provider-specific execution artifact generated from an Action. | Become canonical engineering knowledge. |
| Execution Host | Performs released bounded work in an execution environment. | Redefine the Action, Intent, or architecture. |
| Repository | Holds the implementation reality created by execution. | Authorize or plan work. |
| Evidence | Records assessable repository outcomes for future planning. | Authorize or execute work. |

## Why the Action boundary exists

An Intent preserves tactical meaning across a coherent body of engineering:
why it exists, its boundaries, how it is validated, expected evidence, and its
architectural traceability. That scope can legitimately include several
independent changes. Treating an Intent as one executable prompt collapses
tactical meaning into provider wording and forces a false one-to-one mapping.

An Action therefore has one bounded outcome that can be released for execution
without silently selecting or enlarging adjacent Intent work. It is the stable
handoff from tactical planning to a transient Runtime Prompt while retaining
the distinction between canonical knowledge and provider-specific material.

## Relationships and scheduler impact

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
  ↓ guides
Execution Host
  ↓ changes
Repository
  ↓ provides
Evidence
  ↓ informs
Mission Planner
```

The Bootstrap Mission Scheduler coordinates released Engineering Actions,
not Engineering Intents. Releasing an Action is the only scheduling operation
implied here; it does not approve an Intent, generate a prompt, operate a
provider, execute a repository change, or assess evidence.

## Compatibility and next increment

Earlier direct Intent-to-prompt wording is historical architecture and must not
be extended as the canonical future path. A future migration, if needed,
requires a separately authorized capability.

The recommended next increment is the first AI-assisted Mission Planner. It
may propose new Engineering Intents from repository evidence within explicit
human-governed Mission boundaries, without executing work.
