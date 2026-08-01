# Forge Engineering Action Architecture 1.11

## Purpose and boundary

An **Engineering Action** is Forge's smallest intentional engineering unit.
It is the executable unit that expresses one bounded change, documentation
update, repair, qualification step, or Runtime Prompt production. An Action is
contained by exactly one Engineering Intent; an Intent may contain one or more
Actions. This boundary was discovered during bootstrap when a single Intent
repeatedly proved too broad to safely become one runtime instruction.

This is an architectural reconciliation only. It adds no Action storage,
authoring workflow, scheduler, prompt generator, Runtime, provider, execution
host, or execution implementation.

## Canonical hierarchy

```text
Vision
  ↓
Architecture
  ↓
Roadmap
  ↓
Mission
  ↓
Engineering Intent
  ↓
Engineering Action
  ↓
Runtime Prompt
  ↓
Execution
  ↓
Evidence
```

| Level | Responsibility | Must not do |
| --- | --- | --- |
| Vision | Set the durable outcome and product purpose. | Specify or execute work. |
| Architecture | State enduring concepts, boundaries, and invariants. | Become an execution instruction. |
| Roadmap | Sequence strategic capability movement. | Authorize or execute work. |
| Mission | Own the strategic engineering objective, scope, progress, and Engineering Intent memberships. | Become executable. |
| Engineering Intent | Own tactical rationale, boundaries, validation, evidence, and architectural traceability. | Generate a Runtime Prompt directly or execute itself. |
| Engineering Action | State the smallest intentional, executable engineering unit within an Intent. | Expand its Intent, replace governance, or redefine architecture. |
| Runtime Prompt | Carry the provider-specific execution artifact generated from an Action. | Become canonical engineering knowledge. |
| Execution | Perform the released bounded work in an execution environment. | Redefine the Action, Intent, or architecture. |
| Evidence | Record assessable outcomes and repository reality where applicable. | Authorize or execute work. |

Proposal, approval, and provider selection remain supporting governance and
translation concerns. They do not replace a level in this hierarchy.

## Why the Action boundary exists

An Intent preserves tactical meaning across a coherent body of engineering:
why it exists, its boundaries, how it is validated, what evidence is expected,
and how it traces to Architecture. That scope can legitimately include several
independent changes. Treating an Intent as one executable prompt collapses
tactical meaning into provider wording and forces a false one-to-one mapping.

An Action is therefore equivalent to the smallest intentional engineering
unit: it has a single bounded outcome that can be released for execution
without silently selecting or enlarging adjacent Intent work. It provides the
stable handoff from tactical Intent to transient Runtime Prompt while retaining
the distinction between canonical knowledge and provider-specific execution
material.

## Relationships and scheduler impact

```text
Mission
  ↓ contains
Engineering Intent
  ↓ contains
Engineering Action
  ↓ produces
Runtime Prompt
  ↓ guides
Execution
  ↓ produces
Evidence
```

The future Bootstrap Mission Scheduler coordinates Mission, Engineering
Intent, Engineering Action, and Execution. It releases Engineering Actions,
not Engineering Intents. Releasing an Action is the only future scheduling
operation implied here; it does not approve an Intent, generate a prompt,
operate a provider, execute a repository change, or assess evidence.

## Compatibility and next increment

The existing Engineering Intent Lifecycle, Mission Model, and Runtime Prompt
Generation contracts remain unchanged by this documentation-only correction.
Their earlier direct Intent-to-prompt wording is historical architecture and
must not be extended as the canonical future path. A future migration, if
needed, requires a separately authorized capability.

The recommended next increment is the Bootstrap Mission Scheduler. It should
model only Action release and its Mission/Intent context while preserving this
document's non-executing boundary.
