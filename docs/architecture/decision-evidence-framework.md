# Decision Evidence Framework

## Purpose

Decision Evidence is Forge's immutable runtime audit layer for significant planning and governance decisions. It answers **why Forge decided this**. Repository Truth remains the architectural source of truth; Execution Evidence remains owned by the Execution Host and answers **what happened**.

The canonical local runtime location is `.forge/runtime.db`, opened through `forge.runtime.RuntimeDatabase`. The append-only store rejects duplicate identifiers and content, and SQLite triggers reject updates and deletes. Records contain pointers and content digests, never copied evidence, conversations, provider output, logs, telemetry, prompts, or approval automation.

## Record contract

Each versioned record contains a Decision ID, Decision Type, timestamp, Repository and Mission contexts, decision and concise reasoning summary, canonical evidence references, explicit confidence, alternatives and rejections, selected alternative, required disciplines, architecture and business constraints, repository maturity and execution-evidence references, approval state, and outcome.

The initial decision types are Mission Recommendation, Architecture Review, Business Advisor Recommendation, Architecture Advisor Recommendation, Mission Planning, Engineering Intent, Engineering Action Selection, Execution Policy, Solution Template Selection, and Portfolio Recommendation. The enum is deliberately extensible by later schema versions.

## Reasoning, alternatives, and confidence

Reasoning describes the evidence and constraints that led to the selected alternative concisely. At least one alternative is retained, every alternative has a rejection reason, and the selected alternative must name one of them.

Confidence is explicit and cannot be derived from opaque model output alone. Every record includes typed pointers to Repository Truth, Architecture Review, Execution Evidence, and Mission State; these four inputs are the required provenance for the numeric score and level.

## Traceability and governance boundary

References are typed, revision-pinned, and digest-pinned. They can point to Mission, Mission Recommendation, Architecture Review, Execution Evidence, Repository Evidence, Solution Template, Engineering Intent, Engineering Action, Mission State, and Repository Truth. `DecisionEvidenceRepository` requires a Repository Truth resolver and `append` resolves every pointer through it before persistence.

Decision Evidence explains decisions but never performs them. Business approval remains human, Architecture approval remains human, and the framework creates no approval, planning, execution, repository mutation, provider invocation, logging, or telemetry action.

## Workspace projections

Business Workspace exposes recommendation rationale, alternatives, confidence, and human approval state. Architecture Workspace exposes review, decomposition, Intent, Action, constraints, and traceability rationale. Execution Workspace exposes only Decision Evidence identifiers and Execution Evidence references; it never duplicates reasoning or becomes the owner of Decision Evidence.

Mission Recommendation and Architecture Review remain independent canonical artefacts. Decision Evidence references them to explain a decision; it does not replace, mutate, or duplicate them.
