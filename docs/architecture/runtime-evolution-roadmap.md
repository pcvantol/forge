# Forge Runtime Evolution Roadmap

**Status:** Canonical implementation strategy

## Current CI qualification extension — 2026-09-12

The planned [Forge inner-loop CI integration contract](FORGE_INNER_LOOP_CI_INTEGRATION_V1.md)
and [roadmap/DAG](../roadmap/FORGE_INNER_LOOP_CI_V1.md) add a complete installed
Mission Candidate -> canonical approvals/intake -> dynamic Action execution ->
evidence-derived completion test line, with a stateful mock EP at the HTTP
boundary. Real Forge storage, governance, planning/validation, adapter and
reconciliation remain in the test; external LLM/OS boundaries use deterministic
fixtures. New-process reopen and an evidence-dependent successor are mandatory.

This is RUNTIME_QUALIFICATION work, independent of Console/Workspace/installer
and live-canary completion. A dedicated failing CI gate and release reuse are
planned, not activated by this document. Mock-backed PASS never substitutes for
real EP/provider qualification. Existing bootstrap stages below are historical
strategy context, not instructions to revert to their old provider version or
predeclared-Action canary. The scoped contract identifies the current source
and existing-test limitations without changing Mission semantics or authority.

## Post-live-E2E server and later outer-loop CI — 2026-09-12

The standalone **Forge Server process** is an explicit next product milestone
AFTER the current live E2E run is concluded and its actual outcome reviewed.
This is the server-only portion of existing [FSH-SERVICES](../roadmap/FORGE_CONSOLE_HOSTING_V1.md),
not a new prerequisite retrofitted onto the running canary. Reuse
InstalledDynamicMissionRuntime and ForgeRuntimeService in a shipped foreground
serve/API composition with graceful shutdown, single-writer protection, bounded
polling and durable restart, then qualify the owning launchd installation.
Server delivery does not wait for Console, relay or the outer loop; the later
Console is its admin client, not Workspace's replacement or runtime authority.

At source `206657698bb29caa6d22fda5020e4ebc8072700f`, `ForgeRuntimeService.serve`
exists as a library loop; `forge server` CLI exposes storage init/status. That
is useful foundation, not evidence of a complete independent installed daemon.
Existing CLI-first language below is historical sequencing, not a requirement
to throw away the public installed application composition to create another CLI.

The [outer-loop CI contract](FORGE_OUTER_LOOP_CI_INTEGRATION_V1.md) and
[roadmap/DAG](../roadmap/FORGE_OUTER_LOOP_CI_V1.md) are a LATER deterministic
qualification line after FCI-CI: verified Mission result -> Context -> Candidate
-> applicable governance -> next Mission -> its inner loop. No automatic new
Mission approval is introduced. Reuse the mock EP and installed harness; preserve
real Forge application logic. The application-level suites need no running
production daemon. Once Server exists, add the same scenarios through its real
entrypoint/API as an additional variant, not a separate orchestration engine.

## Decision

Forge evolves CLI-first. The deterministic Forge CLI is the first executable
Forge runtime. The Forge Runtime Service follows only after the CLI has been
qualified end to end; it automates the proven CLI workflow and is not a second
engineering engine.

The CLI is a reference/qualification adapter, not a second application
authority. Target services are interface-neutral and are shared by CLI,
Workspace API, MCP and Runtime Service workers; see the
[Productization Reconciliation](FORGE_PRODUCTIZATION_RECONCILIATION.md).

## Canonical implementation sequence

### Stage 1 — First executable runtime

```text
Mission Document
  ↓
Mission Intake
  ↓
Forge CLI
  ↓
Mission Runner
  ↓
Mission Scheduler
  ↓
Engineering Action
  ↓
Runtime Prompt Renderer
  ↓
Execution Host Contract
  ↓
Bootstrap Execution Host Adapter
  ↓
Engineering Platform 1.5
  ↓
Execution Evidence
  ↓
Mission State
  ↓
Forge CLI Resume
```

Mission Intake is a Forge application service invoked by the CLI. It transforms
an already-approved Mission into Mission State; it neither creates a Mission
nor grants approval. The CLI supplies deterministic intake, resume and status
as a qualification surface. Mission Runner and Scheduler are application
capabilities exposed through that adapter, not CLI-owned product authority.

### Stage 2 — CLI qualification

```text
Forge CLI
  ↓
End-to-End Mission Qualification
  ↓
Mission Canary
  ↓
Execution Qualification
  ↓
Repository Qualification
```

The qualified CLI is the reference implementation for all later runtime
operation.

### Stage 3 — Runtime Service

The Forge Runtime Service evolves from the qualified CLI. It adds continuous
operation, supervision, automatic resume, automatic evidence polling,
execution scheduling, and service lifecycle management. It reuses the same
CLI workflow and execution semantics; it introduces no new engineering
behavior.

### Stage 4 — Workspace integration

The separate Workspace product is the primary human interaction and control
surface. It presents Business, Architecture, Execution and Analytics views,
submits governed intents, and never owns Forge planning or execution. Historic
Forge Studio terminology is superseded as a product surface; its
presentation-only safeguards remain applicable.

The workspaces retain the product-model boundaries: Business owns Mission
Candidates and Portfolio decisions; Architecture refines and approves Missions
for engineering; Forge owns engineering only within an approved Mission; and
Execution Hosts own execution evidence. Studio does not collapse these
responsibilities or introduce automatic approval.

## Bootstrap execution boundary

Engineering Platform 1.5 remains the temporary reference Execution Host. Forge
core communicates with it only through:

```text
Execution Host Contract
  ↓
Bootstrap Execution Host Adapter
  ↓
Engineering Platform 1.5
```

There is no direct Engineering Platform integration in Forge core, application
services, CLI, Runtime Service or Workspace. Execution remains owned by the
Execution Host.

## Autonomous engineering boundary

Forge recommends work; humans approve executable Missions.

```text
Mission
  ↓
Mission Intake
  ↓
Forge CLI
  ↓
Mission Qualification
  ↓
Forge Runtime Service
  ↓
Mission Recommendation
  ↓
Business Review
  ↓
Architecture Review
  ↓
Mission
```

Forge never creates executable Missions autonomously.

The full lifecycle and its two approval decisions are canonical in the
[Product Model](product-model.md). This roadmap's implementation order does
not itself authorize any lifecycle transition.

## Portfolio relationship

```text
Mission Candidates
  ↓
Business Workspace
  ↓
Approved Mission
  ↓
Mission Intake
  ↓
Forge CLI
  ↓
Engineering
  ↓
Mission Recommendation
  ↓
Portfolio
```

The Portfolio is a governance and learning view. It records candidates and
recommendations; it does not bypass Business or Architecture Approval and does
not execute engineering.

## Next implementation increment

The reconciled dependency order is:

```text
Codex Runtime Prompt Renderer
  ↓
Bootstrap Execution Host Adapter
  ↓
Mission Intake
  ↓
End-to-End Bootstrap Mission Canary
  ↓
Architecture Review Engine
  ↓
AI Mission Planner
  ↓
Forge Runtime Service → Forge Studio
```
