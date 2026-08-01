# Forge Phase B — Scheduler / Execution Host Contract Reconciliation 001

## Assessed components

The assessment covered the Bootstrap Mission Scheduler, Bootstrap adapter,
Execution Host Contract models, Action/Intent/Mission progress behavior,
architecture documentation, and deterministic tests.

## Initial classification

| Requirement | Initial state | Finding |
| --- | --- | --- |
| Contract-only scheduler communication | NON_COMPLIANT | Scheduler used scheduler-local repository evidence and the adapter's Platform report types. |
| Platform details isolated in bootstrap adapter | PARTIAL | Details were adapter-local but re-exported as scheduler API and documented as direct communication. |
| No host paths in scheduler core | COMPLIANT | No literal local host paths existed; a regression boundary test was absent. |
| Run-bound execution evidence | PARTIAL | Action/report matching existed but had no Mission, correlation, host-run, prompt, or retry proof. |
| Terminal-state behavior | PARTIAL | Complete/blocked/failed existed, but malformed or contradictory evidence was not fully closed. |
| Actions are the release unit | PARTIAL | Selection used Actions, while Intent/Mission completion was not derived from Action completion. |

## Changes made

- Added provider-neutral `ExecutionRequest`, `ExecutionDispatch`,
  `ExecutionHost`, and run-bound evidence identity to the canonical contract.
- Reworked scheduler dispatch and reconciliation to use only those types and
  to reject every identity mismatch before state progression.
- Made the Bootstrap Execution Host Adapter the exclusive Engineering Platform
  Inbox/report translator and removed Platform types from scheduler exports.
- Added Action-derived Intent and Mission progress.
- Corrected diagrams, boundary documentation, and the current README scope.
- Added deterministic fake-host, adapter-translation, boundary, stale-result,
  terminal-state, Action/Intent/Mission, and retry regression coverage.

## Final classification

All six requirements are **COMPLIANT**. The generic contract carries no
Engineering Platform fields; adapter-only data remains bounded to the adapter.
`ExecutionRequest` and terminal evidence now share exact Mission, Intent,
Action, Runtime Prompt, host, correlation, run, repository, and retry identity.

## Contract changes

The contract schema advances to `2.2`. The former local scheduler repository
evidence path is removed. Host evidence now uses the canonical request/run
correlation fields and an `ExecutionHost` protocol.

## Tests added

The reconciliation adds contract-bound scheduler dispatch, adapter translation,
scheduler-core dependency boundary, complete/stale/blocked/failed/unknown,
Action/Intent/Mission progress, and retry-isolation scenarios. All are local
deterministic tests; no real host, network, runtime, or repository execution is
used.

## Remaining limitations and readiness

The adapter is a bootstrap reference translator, not a live host integration.
No Mission Runner loop, daemon, retry transition, or real dispatch is included.
The scheduler boundary is ready for a minimal Mission Runner increment, provided
that increment preserves the contract and explicit recovery authority.
