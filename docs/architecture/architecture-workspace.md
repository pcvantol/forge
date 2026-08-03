# Forge Architecture Workspace

## Purpose

The Architecture Workspace is Forge's canonical engineering-governance
workspace. It transforms a Business-approved Mission Candidate into an
engineering-ready Mission through human architectural refinement and a
separate Engineering approval. It owns architecture; it never owns execution.

The minimal experience is an approved-Mission list, Mission detail, the
advisory Architecture Advisor, refinement, approval for engineering, and
optional return-to-business, rejection, or archive decisions. The current
implementation is deterministic local persistence and view data, not a web
UI, identity service, workflow engine, provider, Runtime, or repository API.

## Admission and lifecycle

Only a Candidate with `approved_for_architecture` status may be admitted. The
source Candidate remains business-owned and is never changed by admission,
refinement, advice, or Architecture approval.

```text
Business-approved Mission Candidate
  → Architecture Review and refinement
  → Approved for Engineering | Returned to Business | Rejected | Archived
```

An Architecture Mission preserves Candidate identity, business objective,
portfolio context, and approval history. Refinement may update only scope,
engineering constraints, acceptance criteria, technical assumptions,
dependencies, required capabilities, required disciplines, and risks. An
approval is allowed only when each of those architectural fields is explicit.
It changes only the Architecture Mission state to `approved_for_engineering`.

The engineering-ready Architecture Mission is deliberately distinct from the
legacy `EngineeringMission` execution contract, whose Intent memberships are
created later by the out-of-scope Mission Planner. This prevents planning from
being required before human approval.

## Architecture Advisor

`ArchitectureAdvisor` returns immutable, provider-independent advice about
technical feasibility, architecture consistency, implementation boundaries,
dependencies, risks, repository consistency, capability reuse, and governance
compliance. It does not approve a Mission, perform engineering, access a
repository, invoke a provider, or mutate workspace state.

## Governance and boundaries

The resolved [Governance Profile](governance-model.md) supplies assignment and
approval authority. Under Solo, the `primary_operator` is both Business Owner
and Platform Architect, yet Business and Architecture approvals are still
separate auditable decisions. Duo, Startup, and Enterprise only change role
assignment, visibility, and authority; they never alter this lifecycle.

```text
Mission Recommendation → Business Workspace → Business approval
  → Architecture Workspace → Engineering approval → Mission Planner → Forge Engineering
```

The [Business Workspace](business-workspace.md) owns portfolio value and its
approval. The [Mission Recommendation Engine](mission-recommendation-engine.md)
supplies advisory input only. The future [Mission Planner](engineering-mission.md)
may consume an approved Mission to create Engineering Intents and Actions but
cannot change its objective or approvals. [Forge Studio](forge-studio.md) may
present the workspace; the future Execution Workspace and Execution Host own
engineering execution and repository activity.

## Explicit exclusions

This increment implements no Mission Planner, Execution Workspace, Forge
Runtime, Execution Host, AI provider, Architecture Review Engine change,
automatic engineering, repository mutation, or runtime control.
