# Integration Coordination Framework

## Purpose

Forge owns integration after independently completed Engineering Actions. The
Execution Host remains limited to execution and Execution Receipts; it does
not decide merge readiness, ordering, conflict handling, or Mission outcome.

## Canonical flow

`Mission → Mission Planner → Engineering Actions → Execution Host → Execution
Receipts → Integration Coordinator → Integrated Mission State → Architecture
Review → Mission Recommendation`

Every completed Action becomes an immutable Integration Unit carrying its
action and Mission identity, Execution Receipt, repository commit/branch/scope,
runtime metadata, and Decision Evidence references.

## Coordination rules

The coordinator first verifies completion inputs: receipts, validation,
dependencies, approvals, current Mission ownership, and deterministic unit
ordering. It then detects overlapping repository scopes with distinct commits.
It never executes engineering work, modifies a repository, invokes a Git
provider, or resolves a merge automatically.

`WAITING_INTEGRATION` pauses a completed Mission before integration starts.
`INTEGRATION_RUNNING` records a Forge-owned integration decision. A conflict
becomes `INTEGRATION_BLOCKED` and the event `MERGE_CONFLICT`; it is not an
Engineering failure. Conflict resolution is represented as a new delegated
Engineering Action with capability `merge_conflict_resolution`, while Forge
retains Mission ownership. A successful decision reaches
`INTEGRATION_COMPLETE`; only then may the Mission enter `COMPLETED` and become
eligible for Architecture Review and Mission Recommendation.

## Evidence and boundaries

Integration Evidence is append-only and immutable. It preserves Integration
ID, ordered units, receipts, merge outcome, conflicts, resolution, Decision
Evidence references, timestamp, and outcome. This complements the Runtime
Database and Decision Evidence Framework; it does not replace either source.
It establishes coordination only, not parallel execution, Git-provider
integration, automatic merge resolution, or cloud orchestration.
