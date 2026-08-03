# End-to-End Bootstrap Mission Canary 3.5

## Qualification purpose

The Bootstrap Mission Canary is Forge's canonical deterministic regression qualification for one approved bounded Mission. It proves the bootstrap execution path without continuous execution, autonomous planning, or a Forge Runtime Service.

```text
Approved Mission → Mission Intake → Mission State → one Intent → one Action
→ Codex CLI Runtime Prompt → Bootstrap Execution Host Adapter
→ Engineering Platform 1.5 → Execution Evidence → Mission State → completion
```

The Canary creates exactly one approved Intent, one active Action, one rendered Runtime Prompt, and one Execution Host run. It uses normal adapter dispatch and report translation; it has no Runner or Scheduler bypass.

## Identity, evidence, and failure behaviour

The scenario pins Mission, Intent, Action, Runtime Prompt, host run, and correlation identities. Prompt persistence restores the typed Codex CLI artifact and original retry correlation. The host returns execution, engineering, repository, and validation references; Mission State records completion. Repository Truth is the host-observed repository evidence, not the rendered prompt or fixture.

Admission is ordered: Execution Host Preflight Level 1 validates contract compatibility; Workspace Preflight Level 2 validates execution mode; Capability Preflight Level 3 validates required capabilities. A capability or workspace failure prevents Inbox submission and leaves the Mission pending. A terminal execution failure is translated to Execution Evidence and a deterministic failed Mission State. Neither case changes identity or invents a retry.

`tests/test_bootstrap_mission_canary.py` is the required bootstrap regression. Runtime, renderer, adapter, intake, and state-store changes must preserve its successful `YES` result before Architecture Review Engine work.

## Relationships

- [Engineering Mission](engineering-mission.md) defines the approved contract.
- [Mission State Store](mission-state-store.md) owns durable state.
- [Bootstrap Mission Runner](bootstrap-mission-runner.md) advances it.
- [Codex CLI Runtime Prompt Renderer](codex-cli-runtime-prompt-renderer.md) renders the artifact.
- [Bootstrap Execution Host Adapter](bootstrap-execution-host-adapter.md) is the sole Engineering Platform 1.5 boundary.
- [Execution Host Contract](execution-host-contract.md) preserves host independence.
