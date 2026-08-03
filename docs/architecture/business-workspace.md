# Forge Business Workspace

## Purpose

The Business Workspace is Forge's first human-facing governance workspace. It
owns Portfolio decisions about Mission Candidates and Mission Recommendations.
It is deliberately separate from the Architecture Workspace and Forge's
Engineering Workspace.

Its minimal experience is a Mission Candidate list, Mission Recommendation
details, an advisory Business Advisor conversation contract, and the three
recorded decisions: approve for architecture, reject, or archive. The current
implementation supplies deterministic local view data and persistence; it is
not a web UI, identity service, workflow engine, or AI provider.

## Candidate contract and lifecycle

A versioned Mission Candidate records its title, summary, business objective,
business value, estimated engineering effort, confidence, required
disciplines, dependencies, Architecture Review reference, Mission
Recommendation reference, priority, business rationale, maturity, and status.
The canonical interchange contract is
[`mission-candidate-1.0.schema.json`](../../schemas/mission-candidate-1.0.schema.json).

```text
Mission Recommendation
  → Business review and refinement
  → Approved for Architecture | Rejected | Archived
```

Candidates enter `business_review`. Refinement is allowed only while in that
state. Business approval changes only the Candidate status to
`approved_for_architecture`; it does not create a Mission, start Architecture
Review, approve engineering, invoke Forge Runtime, or mutate a repository.
Rejection and archive are terminal business decisions. All changes require an
actor, time, rationale, and append-only local history.

Candidate maturity remains the product-model progression: `idea`, `research`,
`feasibility`, `proposal`, and `ready_for_architecture`. Maturity records
information quality and never substitutes for an approval.

## Business Advisor

`BusinessAdvisor` accepts a Candidate and returns immutable advisory content:
missing information, relevant missing disciplines, assumption challenges, and
a business-impact assessment. It cannot approve a Candidate, create a Mission,
execute engineering, call a provider, or mutate local candidate state or any
repository.

## Governance Profiles

The resolved Governance Profile contract uses canonical `solo`, `duo`,
`startup`, and `enterprise` definitions. It resolves role assignments,
Business/Architecture/Engineering approval matrix entries, workspace
visibility, and advisor availability. It accepts existing persisted
`two_person` and `team` values with an explicit compatibility note, mapping
them to Duo and Startup respectively.

Solo assigns one `primary_operator` to both Business Owner and Platform
Architect. The assignments are shared, but Business and Architecture are
separate approval stages and must each be recorded. Governance Profiles change
assignments and visibility only; they never alter the canonical lifecycle.

## Boundaries and relationships

```text
Architecture Review → Mission Recommendation → Business Workspace
  → Business-approved Candidate → Architecture Workspace
  → Architecture-approved Mission → Forge Engineering Workspace
```

The [Mission Recommendation Engine](mission-recommendation-engine.md) creates
only immutable advisory input. The [Portfolio Model](portfolio-model.md) is
the Business Workspace's governed opportunity view. The
[Product Model](product-model.md) remains the canonical lifecycle. The future
[Forge Studio](forge-studio.md) may present this workspace but cannot own its
approvals or bypass its boundaries.

The [Architecture Workspace](architecture-workspace.md) receives only
Business-approved Mission Candidates, prepares their architectural scope and
constraints, and retains the separate approval required before a Mission can
enter engineering.
