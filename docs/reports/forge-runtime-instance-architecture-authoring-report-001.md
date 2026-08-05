# Forge Runtime Instance Persistence Architecture Authoring Report 001

## Scope

Phase E — Increment 5.9 establishes Runtime Instance Persistence. Runtime
Instance is the public architectural concept; Runtime Database is validated
SQLite storage beneath it.

## Decision

Immutable Runtime Identity is separated from mutable instance placement and
access metadata. Repository Identity derives from the initial Git commit, not
an absolute path. A durable registry resolves exactly one instance and is
outside `.forge`; a configured Runtime Root supports persistence beyond
repository cleanup. Missing, corrupt, ambiguous, mismatched, or inconsistent
registrations fail closed. Explicit relocation preserves the Runtime ID.

## Boundaries preserved

Repository Truth remains architectural authority. Engineering Platform keeps
Execution Evidence ownership. Forge persists only its operational state and
immutable Execution Receipt references. Recovery and Generation 1
qualification consume persisted Runtime Instance records, never repository
source to recreate runtime state.

## Validation basis

Regression coverage exercises identity persistence, discovery, configured
durable roots, repository cleanup, workspace relocation, worktree/branch
transitions, restart recovery, Mission/Decision/Receipt persistence, multiple
instance detection, and fail-closed registry behavior.
