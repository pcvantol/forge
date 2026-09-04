# Forge AI Mission Planner 4.3

## Purpose and boundary

The AI Mission Planner continuously transforms one Architecture Workspace
Mission that is `approved_for_engineering` into tactical Engineering Intents
and the smallest executable Engineering Actions. It plans only: Forge Runtime
and the Execution Host continue to render prompts and perform execution.

```text
Mission → Action Derivation → Deterministic Validation → Graph Materialization
  → Engineering Intent → Engineering Action
  → Runtime Prompt Renderer → Execution Host → Repository → Execution Evidence
  → Repository Truth → Mission Planner
```

Business Workspace determines what should be built. Architecture Workspace
determines how it may be engineered. Mission Recommendation remains an
advisory Portfolio responsibility. The Planner neither recommends a Mission,
changes Mission objectives or business value, changes architecture constraints,
approves work, invokes an AI provider, produces a Runtime Prompt, nor executes.

## Internal stages and authority

The approved Mission remains the sole planning authority. Action Derivation is
an interface-neutral, provider-optional reasoning stage: it receives only an
immutable digest-pinned Planning Snapshot and returns untrusted rich planning
proposals. Deterministic validation checks snapshot freshness and provenance,
Mission scope, write authority, human gates, risk inputs, dependencies and
cycles. Only validated proposals are projected into the existing deterministic
materializer. A need for authority outside the Mission becomes
`GOVERNANCE_REFINEMENT_REQUIRED`, never a wider Action.

Provider, CLI, Workspace, MCP, chat and raw provider output are not planning
authority. A provider's identity/model are provenance only.

## Inputs and determinism

`MissionPlannerInput` accepts only an approved Architecture Mission, its
Mission Planning State, an explicit Approved Scope map, and digest-pinned
Planning Evidence. The evidence allow-list includes Mission State, Repository
Truth, Architecture Review, Capability Catalogue, refinement, maturity,
engineering history, historical Intents and Actions, and Execution Evidence.
It has no type for conversations, temporary Runtime Prompts, or Execution Host
implementation details. Repository Truth is required and remains authoritative.

The planner canonicalizes every input and derives its plan identity from a
SHA-256 digest of that canonical value. Identical Mission, State, Repository
Truth, Architecture Review, and Execution Evidence therefore produce exactly
the same Intent plan and Action order.

## Boundaries and continuous planning

Architecture Mission boundaries begin as reviewed text. Before planning, each
boundary must have an `ApprovedScope` mapping with a Mission-required
capability, architecture references, and explicitly permitted atomic Action
definitions. The mapping must cover exactly every approved Mission scope; an
unknown capability, missing scope, duplicate Action, unapproved Mission, or
missing required evidence is rejected. This is the fail-closed enforcement
boundary rather than a free-text interpretation.

After a completed Action, persisted Mission State and Execution Evidence join
the next Repository Truth snapshot. `replan` removes completed Actions,
retains blocked Actions as blocked, and preserves explicitly postponed Actions
as deferred. A scope may split into its declared action definitions; definitions
with one explicit `merge_key` become one bounded Action. Their declared
priorities determine order. The Planner does not dispatch any of them.

## Planner-owned records

Every `PlannedEngineeringIntent` contains its objective, rationale,
architecture references, capability impact, validation strategy, expected
repository evidence, and owned generated Actions. `EngineeringAction` remains
the Runtime Prompt Renderer's smallest executable unit, but creation remains
planning—not execution or approval.

## Out of scope

No OpenAI, Claude, Gemini, LLM invocation, Runtime, Execution Host, Forge
Studio, Business approval, Architecture approval, Mission Recommendation, or
repository operation is implemented.
