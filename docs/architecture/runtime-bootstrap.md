# Forge Runtime Bootstrap, Location Resolution and Evidence Recovery

## Canonical runtime

Every Forge repository has exactly one canonical Runtime Database.  Its
Runtime Identity consists of a generated immutable Runtime ID, Repository
Identity, canonical Repository Root, database version and location, creation
and last-access timestamps, and active status.  The Runtime ID and repository
identity never change during a migration or relocation; database location and
last-access time are operational metadata.

Repository Truth remains architectural authority.  The Runtime Database is
operational authority for Mission State, Architecture Reviews, Mission
Recommendations, Decision Evidence, immutable Execution Receipts, and
Planning State.  Engineering Platform remains owner of Execution Evidence;
Forge records only the immutable receipt identity and references.

## Resolution and bootstrap

`RuntimeResolver` resolves locations before SQLite is opened. It considers a
configured location, a shared Git-common-dir registration, the repository
default `.forge/runtime.db`, and discovered runtime files. Candidates must
belong to the current Repository Identity. Exactly one existing candidate is
opened; more than one fails closed. No candidate causes bootstrap at the
configured or repository-default location.

Bootstrap creates the database, applies migrations, validates SQLite and
foreign references, then initializes Runtime Identity. It does not create
missions, decisions, receipts, or any execution evidence.

Explicit relocation validates an SQLite backup at its destination before it is
registered and the former location is removed. The Runtime ID is preserved.
The shared registration makes the canonical location stable across branches,
worktrees, host restarts, and normal repository cleanup.

## Recovery and integrity

`RuntimeRecovery` first runs Runtime Database integrity validation, then
returns persisted Mission State, Decision Evidence, Architecture Reviews,
Mission Recommendations, Execution Receipts, and Planning State. It never
reads repository source files, old side databases, JSON caches, or Execution
Host evidence to reconstruct state.

Integrity validates schema and migration versions, Runtime Identity,
SQLite/foreign-key integrity, and Decision Evidence receipt references.
Failures prevent runtime startup. Execution Receipts remain append-only and
are verified by their persisted identity, mission ownership, and Decision
Evidence references.

## Bootstrap Qualification

Generation 1 Bootstrap Qualification consumes the Runtime Database projection
only. Qualification never reconstructs execution history: it reads Mission
State, Decision Evidence, Architecture Reviews, Mission Recommendations, and
immutable Execution Receipts already persisted by Forge. This preserves
Repository Truth and Engineering Platform ownership boundaries.
