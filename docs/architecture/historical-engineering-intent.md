# Forge Historical Engineering Intent 1.0

## Purpose and boundary

A Historical Engineering Intent is an immutable, evidence-based historical
record for engineering that genuinely occurred before Forge's Engineering
Intent lifecycle existed. It bridges repository history and the modern
engineering model while preserving historical truth. It is not a normal
`EngineeringIntent`, is not executable, and has no lifecycle transition API.

The model exists because a later governance model cannot retroactively create
governance that did not exist. Historical reconstruction preserves repository
truth, historical accuracy, evidence-first engineering, and human governance;
it prevents constitutional violations caused by rewriting history.

## Historical record

`HistoricalEngineeringIntent` is a frozen local value record with one terminal
status, `HISTORICAL`. It records a historical identifier, title and objective,
bootstrap milestone, reconstruction timestamp and rationale, repository
evidence, implementation commits, implementation reports, and bootstrap
documentation. Repository evidence and bootstrap documentation are mandatory.
At least one direct historical provenance reference—an implementation commit or
implementation report—is mandatory. All evidence references are reproducible
pointers with immutable identity and SHA-256 content digests where a document
is referenced; Forge does not retrieve or interpret them.

Historical authority derives only from repository commits, engineering reports,
repository evidence, and bootstrap documentation. It never derives from a
reconstructed assumption, a prompt, a Runtime Prompt, or a later normal
Engineering Intent.

## Historical governance

Historical proposal and approval records are closed types with the only
permitted status `HISTORICAL_NOT_AVAILABLE`.

- Historical proposal: no proposal existed at the time. Forge must never
  fabricate one.
- Historical approval: no approval workflow existed. Forge must never
  fabricate historical approval.

The model accepts neither proposal references, approvers, decision references,
normal lifecycle states, Engineering Actions, nor executable/runtime fields.
It has no approval operation and no transition function. Those omissions are
intentional evidence of unavailable historical governance, not missing data to
be reconstructed.

## Traceability

Historical records are traceable but not executable:

```text
Repository History
  ↓
Historical Engineering Intent
  ↓
Engineering Knowledge
  ↓
Future Engineering Intent
```

A future normal Engineering Intent may use a Historical Engineering Intent as
repository-held engineering knowledge. It remains separately authored and must
satisfy the complete current [Engineering Intent Lifecycle](engineering-intent-lifecycle.md),
including its proposal, approval, traceability, and evidence requirements.
Historical evidence never satisfies those governance requirements by itself.

## Constitutional and phase-completion relationship

The model preserves the Constitution's repository-first principle by requiring
repository evidence, its evidence-first principle by refusing unsupported
claims, and its human-governance principle by never inventing approval. It does
not modify the Constitution or create a new governance path.

[Phase Completion](phase-completion-framework.md) can assess declared future
phase evidence. It does not transition, approve, execute, or otherwise make a
Historical Engineering Intent complete. Historical status means the record is
historical, not that an assessed phase passed.

## Future boundary

Forge Phase B — Increment 1.3b — Bootstrap Historical Intent Reconstruction
may migrate eligible bootstrap repository history into Historical Engineering
Intents. It must use observed evidence and must not migrate that history into
normal Engineering Intents. No bootstrap migration is performed by this
increment.
