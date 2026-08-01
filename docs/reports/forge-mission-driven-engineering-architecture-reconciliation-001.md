# Forge Mission-driven Engineering Architecture Reconciliation Report 001

## Outcome

Forge's canonical architecture is reconciled around mission-driven engineering.
This is a documentation-only transition. The Constitution is unchanged and no
Mission Planner, scheduler, Runtime, provider, Execution Host, Studio, or
autonomous execution is implemented.

## Architectural changes

- Mission is the highest operational engineering artifact and the
  Architect-approved contract for objective, architectural boundaries, success
  criteria, and constitutional constraints.
- Mission Planner is the future Forge-owned iterative planning responsibility.
  It owns planning, sequencing, dependency management, progress evaluation,
  dynamic Intent creation, and reprioritisation from repository evidence.
- Engineering Intent is no longer a static plan known at Mission start. Active
  Intents may be created, superseded, merged, split, or disappear; historical
  Intent records remain immutable.
- Engineering Action is the smallest intentional executable unit. Actions,
  rather than Intents, produce Runtime Prompts.
- Repository is explicit between Execution Host and Evidence, and Evidence
  feeds Mission Planner continuously.

## Canonical hierarchy

```text
Vision → Architecture → Roadmap → Mission → Mission Planner → Engineering Intent →
Engineering Action → Runtime Prompt → Execution Host → Repository → Evidence →
Mission Planner
```

## Governance consequence

Humans approve Missions and remain responsible for governance. Humans do not
approve every Engineering Intent. Forge owns iterative planning only within the
approved Mission contract; it cannot expand that contract or execute work by
virtue of planning.

## Future development consequence

Future planning and execution capabilities must use the Mission Planner loop,
preserve immutable historical Intent provenance, and release Engineering
Actions as executable units. Earlier fixed Mission membership and direct
Intent-to-prompt wording is retained only as historical bootstrap provenance.

## Recommended next increment

Implement the Bootstrap Mission Scheduler based on released Engineering Actions
rather than Engineering Intents as executable units. It must remain bounded to
scheduling and must not implement autonomous execution.
