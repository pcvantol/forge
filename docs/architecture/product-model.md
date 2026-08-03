# Forge Product Model

## Purpose and authority

Forge is an AI-native Product Development Platform. This document is the
canonical reconciliation of its portfolio-driven product model. It explains
the responsibilities and governance boundaries discovered during Phase C; it
does not implement a workflow, runtime behavior, user interface, approval
system, or automatic progression.

The [Founding Architecture Handbook](FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md),
[Governance Model](governance-model.md), [Mission architecture](engineering-mission.md),
and [Portfolio Model](portfolio-model.md) apply this model in their respective
domains.

## Canonical capability lifecycle

```text
Vision
  ↓
Portfolio
  ↓
Mission Candidate
  ↓
Business Review
  ↓
Approved for Architecture
  ↓
Architecture Review
  ↓
Approved for Engineering
  ↓
Mission
  ↓
Engineering
  ↓
Execution
  ↓
Evidence
  ↓
Architecture Review
  ↓
Mission Recommendation
  ↓
Portfolio
```

Engineering is one bounded stage of this larger lifecycle. It operates only
after an approved Mission exists, and it returns assessed learning through an
advisory recommendation rather than changing the product direction itself.

## Workspaces and responsibility boundaries

| Workspace or role | Owns | Does not own |
| --- | --- | --- |
| Business Workspace | Mission Candidates, Portfolio, prioritisation, business value, and strategic alignment. | Engineering planning, execution, or Mission approval for engineering. |
| AI Business Advisor | Candidate refinement, missing business information, required non-engineering disciplines, business risk, and value assessment. | Approval, engineering, or conversion of a candidate into a Mission. |
| Architecture Workspace | Scope, technical feasibility, architectural boundaries, and engineering constraints. | Portfolio priority, business-value approval, or engineering execution. |
| Platform Architect | Architecture Review and approval of a Mission for engineering. | Autonomous execution or changes to an approved Mission during engineering. |
| Architecture Advisor | Evidence-grounded architectural analysis and review assistance. | Approval or engineering execution. |
| Forge Engineering Workspace | Mission Planner, Engineering Intent, Engineering Action, Engineering, Execution coordination, and Evidence. | Changing Mission objectives, business priority, or either approval decision. |
| Execution Workspace / Execution Host | Execution, reports, telemetry, diagnostics, preflight, and evidence. Engineering Platform 1.5 is the current reference Execution Host. | Product meaning, Mission approval, or engineering planning. |

## Mission Candidate maturity

A Mission Candidate is a portfolio opportunity, not executable work. It may
exist at any maturity in this canonical progression:

```text
IDEA → RESEARCH → FEASIBILITY → PROPOSAL → READY_FOR_ARCHITECTURE
```

Maturity records the quality and completeness of opportunity information. It
does not grant approval, create a Mission, or authorize engineering. Candidates
become Missions only through the explicit approval stages below.

## Approval boundary

```text
Business Owner
  ↓ approves Mission Candidate for Architecture
Platform Architect
  ↓ approves Mission for Engineering
Forge
  ↓ engineers within that Mission
```

Forge must never bypass, infer, or replace these approvals. An approved Mission
is the immutable engineering contract for its objective, scope, success
criteria, architectural boundaries, and constitutional constraints. Forge may
adapt planning inside those bounds but must not change the Mission objective.

## Evidence and Mission Recommendations

After Engineering and Execution, Architecture Review evaluates Repository
Truth and Execution Evidence against the Mission and portfolio context. It may
produce a Mission Recommendation from four inputs:

```text
Repository Truth + Execution Evidence + Architecture Review + Portfolio
  → Mission Recommendation
```

A Mission Recommendation is advisory. It can inform the Portfolio, create or
refine a Mission Candidate, or identify a decision for human review. It never
becomes a Mission automatically and has no execution authority.

## Current implementation boundary

This is architectural knowledge only. Existing Forge runtime components remain
unchanged. The next implementation increment should be a bounded, declarative
Mission Candidate and Portfolio contract that captures the stated ownership,
maturity, approval references, and recommendation provenance without adding
workflow automation or user interfaces.
