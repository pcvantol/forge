# Forge AI Provider Registry Authoring Report 001

## Scope

Phase B — Increment 1.7 establishes the canonical AI Provider Registry. It
adds immutable provider metadata, repository-owned qualification records,
declarative workspace policy, deterministic selection, canonical repository
locations, documentation, and focused tests.

## Decisions

- Providers declare capabilities and reasoning modes explicitly; Forge remains
  independent of any vendor or model family.
- Only active, repository-qualified providers may be selected.
- Preferences, default, fallback, then provider identity/version give selection
  one reproducible outcome without AI invocation.
- The former 1.6 recommendation is corrected: registry precedes any concrete
  OpenAI provider.

## Validation

Focused tests cover registration, capability declaration, qualification
matching, ineligible-provider exclusion, and deterministic selection.
Repository-wide unit tests and whitespace validation are the local Genesis
completion evidence.

## Recommended next increment

Forge Phase B — Increment 1.8 — AI Architect Session must establish the
bounded session, lifecycle, snapshot, and review record before a concrete
provider. A later provider adapter will use the Provider Contract, Provider
Registry, and Session Contract without altering Forge's ownership or
governance boundaries.
