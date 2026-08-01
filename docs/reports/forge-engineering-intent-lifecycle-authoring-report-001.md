# Forge Engineering Intent Lifecycle Authoring Report 001

## Scope

Phase B — Increment 1.2 establishes the canonical, versioned local lifecycle
for Engineering Intents. The delivered contract covers the complete requested
state set, governed transitions, established categories, typed relationships,
reproducible evidence, required traceability, and canonical future repository
layout.

## Architectural decisions

- Engineering Intent status progression is explicit and pure; no transition
  performs persistence, approval, repository activity, provider activity, or
  execution.
- Intent records are immutable. Approval is explicit human provenance rather
  than an automatic consequence of a generated or transitioned record.
- `IMPLEMENTED` requires implementation evidence. `VERIFIED` additionally
  requires validation and repository evidence, preserving repository-first
  assessment.
- Supersession requires a distinct successor and reciprocal `supersedes` and
  `replaces` links, preventing an untracked replacement claim.
- The `engineering/intents` layout is documented and reserved only; no
  bootstrap or existing work is migrated.

## Validation

Focused lifecycle tests cover all statuses, allowed and rejected transitions,
immutability, evidence closure requirements, relationship validation,
supersession reciprocity, and mandatory Vision-to-Repository traceability.
The repository-wide test suite and whitespace validation are the required
implementation checks.

## Out of scope retained

This increment does not implement intent persistence, Bootstrap Intent
Migration, Runtime Providers, runtime execution, queues, Studio, or
repository operations.

## Recommended next increment

Forge Phase B — Increment 1.3 — Bootstrap Intent Migration. It should
reconstruct eligible historical bootstrap work as Intent artifacts using this
lifecycle, without treating prior prompts as canonical records.
