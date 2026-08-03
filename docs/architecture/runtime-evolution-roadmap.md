# Forge Runtime Evolution Roadmap

**Status:** Canonical implementation strategy

## Decision

Forge evolves CLI-first. The deterministic Forge CLI is the first executable
Forge runtime. The Forge Runtime Service follows only after the CLI has been
qualified end to end; it automates the proven CLI workflow and is not a second
engineering engine.

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

Mission Intake belongs to the Forge CLI. It transforms an approved Mission
Document into Mission State; it neither creates a Mission nor grants approval.
The CLI owns deterministic intake, execution, resume, and status. Mission
Runner and Mission Scheduler remain CLI workflow components, not services.

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

### Stage 4 — Forge Studio

Forge Studio is the primary user interface. It owns the Business Workspace,
Architecture Workspace, Execution Workspace, and Analytics. Studio owns
interaction, visualization, and governance workflows; it orchestrates the
Runtime but never owns execution.

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

There is no direct Engineering Platform integration in Forge core, the CLI,
the Runtime Service, or Studio. Execution remains owned by the Execution Host.

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
Business Approval
  ↓
Architecture Approval
  ↓
Mission
```

Forge never creates executable Missions autonomously.

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
End-to-End Bootstrap Mission Canary
  ↓
Forge CLI
  ↓
Mission Intake
  ↓
Architecture Review Engine
  ↓
Mission Recommendation Engine
  ↓
Forge Runtime Service
  ↓
Forge Studio
```
