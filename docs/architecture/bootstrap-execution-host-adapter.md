# Bootstrap Execution Host Adapter 3.4

## Purpose

The Bootstrap Execution Host Adapter is Forge's first concrete, replaceable
Execution Host Adapter. It translates exactly one immutable Codex CLI Runtime
Prompt into one Engineering Platform 1.5 engineering transaction and translates
the terminal host report back into canonical `ExecutionHostEvidence`.

```text
Mission → Engineering Intent → Engineering Action → Runtime Prompt
  → Bootstrap Execution Host Adapter → Engineering Platform 1.5
  → Execution Evidence → Forge
```

Forge core remains independent of Engineering Platform. The core knows only
the provider-neutral Execution Host Contract. Engineering Platform names,
Inbox transport, receipt identifiers, report shape, and retry transport exist
only in `forge/scheduler/adapter.py`.

## Translation and admission

The adapter consumes a `CodexCliRuntimePrompt`, rather than producing or
altering one. It deterministically maps its rendered text to an engineering
prompt; Mission, Intent revision, Action, and correlation identities to
execution metadata; constraints to host metadata; and compatibility metadata
to Capability Preflight input. The adapter delegates admission before Inbox
submission. Preflight remains authoritative for Execution Host, Workspace, and
Capability requirements.

The adapter resolves only `ExecutionHostConfiguration` through the canonical
Configuration Resolver protocol. Inbox locations, host identifiers, supported
capabilities, runtime minimums, and other host configuration are supplied by
that resolver; no path, workspace, repository, or Engineering Platform runtime
location is hard-coded by the adapter.

## Transport, retry, and evidence

Only the adapter writes an Engineering Platform Inbox transaction. Its payload
contains the immutable engineering prompt, all source identities, correlation,
the original correlation, retry predecessor, constraints, validation,
compatibility, resolved host identity, and resolver-provided transport location.
It never plans, executes, invokes a runtime, or interprets repository evidence.

Every retry is a new correlation and new host run. The payload retains both the
immediate retry predecessor and original correlation, preventing merged runs.
Engineering Platform reports are translated to canonical execution evidence:
host identity, run and terminal state, repository revision and digest,
validation and diagnostic references, retry lineage, and execution timing.
Inbox-specific detail is not returned outside this adapter boundary.

## Relationships

- [Codex CLI Runtime Prompt Renderer](codex-cli-runtime-prompt-renderer.md)
  creates the immutable execution artifact; it does not transport it.
- [Execution Host Contract](execution-host-contract.md) is the generic Forge
  boundary consumed by Runtime and Scheduler code.
- Capability Preflight receives compatibility only through the adapter and
  remains the authority that accepts or rejects delivery.
- Mission Intake and Mission Runner remain Forge-owned; neither knows the
  Engineering Platform transport.
- Engineering Platform 1.5 is a temporary reference Execution Host, not a
  Forge dependency or engineering authority.

## Future hosts

Future adapters can translate the same Runtime Prompt and canonical evidence
contract to another host without modifying Forge core. The next increment is
the **End-to-End Bootstrap Mission Canary**, which will prove the full chain
from Mission through this adapter and back to Forge using controlled evidence.
