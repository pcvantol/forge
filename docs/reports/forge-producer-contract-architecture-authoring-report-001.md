# Forge Producer Contract Architecture Authoring Report 001

## Architecture decision

Forge now exposes planning to every Execution Host through one canonical,
versioned Producer Contract. The contract separates immutable Producer-owned
Mission planning, Intent, Action, Runtime Prompt, policy constraints, and
Decision Evidence from Host-owned execution, receipt, report, telemetry, and
Execution Evidence.

The contract is intentionally producer-neutral: `HUMAN`, `FORGE`, `EXTERNAL`,
and `UNKNOWN` are canonical values, while valid future uppercase values remain
preservable. Producer identity is audit data only; it cannot select a runtime,
change policy, or modify Host semantics.

## Boundary decision

The Execution Host core imports no Codex renderer or Engineering Platform
implementation. A transitional bridge materializes existing Runtime Prompt
objects into the host-neutral envelope. The Bootstrap adapter remains the only
Engineering Platform-aware location, so its later adoption does not require a
Forge-core dependency or migration of current human-authored workflows.

## Outcome

The Producer Contract is canonical. Forge owns it, and Execution Hosts consume
it. Future Cloud and Enterprise Execution Hosts can consume the same envelope
without inheriting Forge implementation details.
