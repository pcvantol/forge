# Mission Recommendation Engine

## Boundary

The Mission Recommendation Engine is the deterministic, advisory boundary between an Architecture Review and the future Business Workspace. It converts declared Repository Truth, Execution Evidence, an Architecture Review and its declared Portfolio references into immutable Mission Recommendation artefacts. It never retrieves a repository, invokes an AI provider, changes Portfolio state, approves work, prioritises work, creates a Mission Candidate, creates a Mission, schedules work or invokes the Mission Planner.

Architecture Review remains assessment-only. Its output records Repository Truth, maturity, pressure and candidate signals. The separate Recommendation Engine alone derives Portfolio-facing opportunities from that assessment.

## Model and lifecycle

Each immutable recommendation includes a content-derived identity, repository context, Architecture Review reference, repository maturity digest, rationale, business and architectural value, bounded engineering effort, deterministic confidence, advisory dependencies, required and explicitly missing disciplines, capability impact, timestamp, source signals and Portfolio references.

```text
Completed Mission -> Execution Evidence -> Repository Truth -> Architecture Review
  -> Mission Recommendation -> Business Workspace -> Mission Candidate
  -> Business Approval -> Architecture Approval -> Mission
```

The Business Workspace owns approval, rejection, refinement and prioritisation. A recommendation is only an artefact available to that workspace; it is not a state transition and has no approval field. A later Mission Candidate and Mission must retain their own explicit governance.

## Categories, dependencies and disciplines

The extensible `RecommendationCategory` catalogue contains New Capability, Architecture Reconciliation, Qualification, Technical Debt, Documentation, Governance, Execution Host, Runtime, Portfolio, Developer Experience and Infrastructure. The current pure rules generate categories only where the Architecture Review supplies matching evidence; the complete catalogue is available for future evidence-backed rules.

Dependencies may name predecessor and successor Mission IDs, grouping and optional sequencing. They are advisory annotations, never scheduler input. Required disciplines are explicit enum values. The engine compares each required discipline with declared available disciplines and records the missing set; it does not infer or fabricate expertise.

## Confidence and determinism

`RecommendationConfidence` is the integer mean of six declared 0--100 factors: repository maturity, architecture pressure, implementation pressure, execution evidence, capability completeness and evidence quality. Its level is low below 45, medium below 75 and high otherwise. Every factor comes from the Architecture Review and its repository-only evidence. Historical conversations, clock access, external providers and hidden state are excluded.

The recommendation timestamp is an explicit, declared input supplied as part of execution evidence. Sorted immutable inputs, canonical JSON digests and no side effects mean identical Repository Truth, Architecture Review, Execution Evidence, Portfolio reference and timestamp produce identical recommendations.

## Relationships

Architecture Review is the evidence assessment. Mission Recommendation is its advisory Portfolio artefact. Business Workspace is the future human-facing owner of recommendation decisions and Mission Candidate refinement. Architecture Workspace remains the approval authority for a candidate that may become a Mission. Mission Planner consumes only an already approved Mission; it cannot consume a recommendation as work authority. Portfolio is the business-owned collection of advisory opportunities, not an execution queue.
