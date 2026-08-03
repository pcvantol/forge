# Forge Architecture Review Engine 3.6

## Purpose and boundary

The Architecture Review Engine is a deterministic, local, repository-evidence
assessment after a completed Mission. It produces immutable Architecture
Reviews and advisory Mission Recommendations. It evaluates; it does not
perform engineering, read repositories, invoke AI, change repository state,
approve work, create executable Missions, or operate an Execution Host.

Its sole input contract is `ArchitectureReviewInput`. The allow-list contains
the Constitution, Architecture Handbook, Bootstrap Completion Record,
Capability Catalogue, Mission documents and state, Repository Truth, Execution
Evidence and reports, engineering history, maturity, Portfolio, existing
recommendations, and Roadmap. Historical conversations, temporary Runtime
Prompts, and Execution Host implementation details have no input type and are
therefore excluded by construction. Repository Truth remains authoritative.

```text
Completed Mission → Execution Evidence → Repository Truth
  → Architecture Review Engine → Architecture Review
  → Mission Recommendation(s) → Business Workspace / Portfolio
```

## Artefacts

An `ArchitectureReview` has a content-derived identity and input digest. It
records all ten maturity areas, architectural and implementation observations,
strengths and weaknesses, four pressures, inconsistencies, duplication,
capability gaps, recommendation candidates, rationale, and bounded confidence.
Its dataclasses are frozen and expose no lifecycle mutation.

`MissionRecommendation` is an immutable Portfolio artefact. Its kinds are new
capability, reconciliation, qualification, documentation, runtime improvement,
and governance improvement. It is always marked advisory and is not a Mission,
Mission approval, Engineering Intent, Engineering Action, or execution order.
The Business Workspace owns Mission Candidates; the Architecture Review Engine
may only recommend candidate creation, update, retirement, or priority review.

## Maturity and confidence methodology

Every review assesses Architecture, Runtime, Planning, Engineering,
Governance, Portfolio, Execution Host, Documentation, Knowledge, and
Qualification. For each area, its documented required evidence kinds produce a
bounded class: `not_evidenced`, `foundation`, `established`, or `qualified`.
The implementation uses set membership only; it does not interpret evidence
content or make probabilistic inferences.

Confidence is `insufficient` without both Repository Truth and Execution
Evidence, `medium` with those two sources, and `high` when Mission State and
Portfolio evidence are also present. Insufficient evidence yields only an
advisory qualification recommendation; it never fabricates a conclusion.

## Pressure taxonomy

The engine keeps pressure distinct:

- Architecture Pressure records a repository inconsistency only when high
  Implementation Pressure demonstrates necessity.
- Implementation Pressure records evidence-backed implementation failure.
- Repository Growth Pressure records repository-growth signals.
- Operational Pressure records operational failure signals.

An architectural reconciliation recommendation is impossible from an
architectural inconsistency alone. This prevents normal growth or an isolated
design observation from being treated as a reason to change architecture.

## Determinism and integration

Input evidence, signals, and Portfolio identifiers are canonicalized by stable
sorting; review and recommendation identifiers derive from SHA-256 canonical
input representations. Identical Repository Truth, Execution Evidence,
Portfolio, and Mission State therefore produce equal Architecture Reviews and
equal recommendations regardless of input order.

The Engine follows a completed [Mission](engineering-mission.md), using its
state and evidence. It informs the [Portfolio](portfolio-model.md) after the
Architecture Workspace review, while [Mission Intake](engineering-mission.md),
the Mission Planner, Forge Runtime, and the Execution Host remain unchanged.
Human Business and Architecture approval remain the authority boundary in the
[Product Model](product-model.md).

## Next boundary

Forge can now determine evidence-based Mission Recommendations from Repository
Truth and Execution Evidence alone. The next architectural increment is the
AI Mission Planner: it will consume an already approved Mission, Mission State,
Architecture Review, Mission Recommendation, and Repository Truth to generate
Engineering Intents. It will not create or approve Missions.
