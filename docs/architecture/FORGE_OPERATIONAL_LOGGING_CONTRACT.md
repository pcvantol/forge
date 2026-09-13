# Forge operational logging contract 1.0

## Purpose and authority

`forge_operational_logs` is Forge's canonical, durable operational journal.
It gives Forge an operator-facing timeline that is structurally comparable to
Engineering Platform's CENTRAL component logs without claiming any Execution
Host authority.  Forge logs its own planning, runtime, operator and
Forge-to-EP boundary activity.  EP remains the sole authority for execution,
host lifecycle, host telemetry, reports and terminal execution evidence.

The journal complements rather than replaces immutable domain records such as
Mission State history, Decision Evidence, provider-security audit, operator
audit and the Forge↔EP exchange audit.  A domain record answers its specialised
contract; an operational event answers what the Forge runtime did, when and
under which safe correlation context.

## Event shape

Every row is append-only and has these normalized fields:

| Field | Meaning |
| --- | --- |
| `occurred_at` | Canonical UTC event or local ingest time. |
| `level` | `DEBUG`, `INFO`, `WARNING` or `ERROR`, matching EP's level vocabulary. |
| `component` | Closed Forge component identity. |
| `event` | Closed, machine-readable snake-case event name. |
| `mission_id`, `action_id` | Forge planning context when available. |
| `correlation_id`, `run_id` | Cross-boundary and Execution Host correlation when available. |
| `operator_reference` | One-way operator fingerprint; never a credential or generated UID. |
| `details` | Bounded allow-listed scalar metadata and `event_contract_version: "1.0"`. |

The closed component set is `forge_runtime`, `forge_mission_runtime`,
`forge_execution_host`, `forge_planning_provider`, `forge_operator` and
`forge_administration`.

`RuntimeDatabase.operational_log_page()` uses filter-before-pagination,
bounded search and the same practical sort/filter concepts as EP's component
log page.  It is the dashboard query seam; a future Forge dashboard must use
this projection rather than parse individual audit tables.

## Redaction and integrity

The writer rejects unallowlisted detail keys, nested values, secret-shaped keys
and secret-shaped values.  It never stores prompts, provider output, AI
messages, bearer material, Keychain references, repository checkout paths,
configuration endpoints or host evidence bodies.  Failures are represented by
bounded classifications and outcomes, not raw exception text.

SQLite triggers deny `UPDATE` and `DELETE`.  A state-changing Forge operation
appends its corresponding journal event in the same database transaction where
that is available.  The journal starts at this migration; it does not invent
historical events for installations created before schema 36.

## Required coverage for Forge-owned operations

The current runtime records these categories:

- runtime initialization; Mission intake, lifecycle, state, runtime-projection
  and dispatcher state changes; Architecture review, recommendation, Decision
  Evidence and integration-evidence recording;
- immutable execution-context refreshes, scheduler submission creation/state
  changes and host receipt recording;
- Execution Host binding persistence and both Forge→EP submission / EP→Forge
  submission-receipt events, including safe version and digest bindings;
- the Forge v1 Action Context Envelope metadata (envelope version, generator
  identity/model/version, summary digest and envelope digest), never the
  summary's source prompt or any unredacted Action text;
- accepted, host-proven EP operator-retry resolution evidence, bound to the
  original Forge correlation, original host run, resolved EP submission and
  terminal successor run without recording host evidence bodies;
- creation, replacement and idempotent no-change handling of the selected EP
  peer configuration;
- operator binding, revocation and governance-capability upgrade actions;
- planning-provider configuration, generation-permit acquire/commit/release,
  bounded token-preflight receipt/failure facts, and redacted
  provider-invocation start/finish outcomes; and
- Forge Action-Derivation lifecycle transitions, evidence facts, explicit
  reattempt authorization/consumption and canary closure.

New Forge code that changes durable runtime, operator, provider, scheduler or
Forge↔EP state must append a semantic event through
`RuntimeDatabase.record_operational_event()` (or its in-transaction writer).
Read-only status and inspection paths deliberately remain read-only; they do
not mutate the journal merely because an operator viewed a projection.

## Version and migration

Runtime schema 36 introduces the journal and its immutable indexes/triggers.
Schema 35 installations migrate additively.  Existing domain audit tables and
historical Mission/Execution Context records remain readable without being
rewritten.
