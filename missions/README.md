````markdown
# Forge Missions

## Purpose

The `missions` directory contains the canonical business-approved Missions that drive Forge engineering.

A Mission is **not** an Engineering Prompt.

A Mission is **not** an Engineering Intent.

A Mission is the highest-level engineering contract approved by the appropriate human governance roles.

Forge autonomously plans and executes engineering **within** an approved Mission.

Forge never changes Mission objectives.

---

# Mission Lifecycle

The canonical capability lifecycle is:

```text
Vision

↓

Portfolio

↓

Mission Candidate

↓

Business Review

↓

Approved for Architecture

↓

Architecture Review

↓

Approved for Engineering

↓

Mission

↓

Engineering

↓

Execution

↓

Evidence

↓

Architecture Review

↓

Mission Recommendation

↓

Portfolio
```

Only **Approved Missions** are stored in this directory.

Mission Candidates and Mission Recommendations are separate artefact types.

---

# Responsibilities

## Business Owner

Owns:

- Portfolio
- Mission Candidates
- Business approval

The Business Owner decides:

> Should this capability be built?

---

## Platform Architect

Owns:

- technical refinement;
- architectural constraints;
- engineering feasibility.

The Platform Architect decides:

> How should this capability be engineered?

---

## Forge

Owns:

- Mission planning;
- Engineering Intents;
- Engineering Actions;
- Runtime Prompt generation;
- autonomous engineering execution.

Forge never changes Mission objectives.

---

## Execution Host

Owns:

- engineering execution;
- execution evidence;
- reports;
- telemetry;
- diagnostics.

Execution Hosts execute Engineering Actions only.

Execution Hosts never interpret Mission intent.

---

# Mission Structure

Each Mission defines:

- business objective;
- business value;
- governance boundaries;
- scope;
- out-of-scope items;
- success criteria;
- dependencies;
- expected deliverables;
- completion criteria.

Implementation details remain the responsibility of Forge.

---

# Portfolio Seed Missions

The first Missions are Portfolio Seed Missions.

They establish Forge itself.

Current Portfolio Seeds:

- MISSION-0001 — Autonomous Engineering Foundation
- MISSION-0002 — Architectural Intelligence Foundation
- MISSION-0003 — Forge Studio Foundation
- MISSION-0004 — Portfolio Governance Foundation
- MISSION-0005 — Multi-Disciplinary Intelligence Foundation

These Missions bootstrap Forge into an AI-native Product Development Platform.

---

# Future Directory Structure

The current bootstrap contains Portfolio Seeds only.

Future repository evolution is expected to introduce:

```text
missions/

    README.md

    portfolio-seeds/

    active/

    completed/

    archived/

    recommendations/
```

Mission Recommendations remain advisory.

Only approved Missions become executable.

---

# Relationship with Forge Runtime

Mission documents are repository artefacts.

They are not executed directly.

The canonical execution pipeline is:

```text
Mission

↓

Mission Intake

↓

Mission State

↓

Mission Planner

↓

Engineering Intents

↓

Engineering Actions

↓

Runtime Prompt Renderer

↓

Execution Host

↓

Execution Evidence
```

Mission Intake transforms an approved Mission into runtime state.

Execution Hosts never consume Mission documents directly.

---

# Governance

Forge remains autonomous only within approved Mission boundaries.

Mission approval always remains a human responsibility.

Business approval determines **what** should be built.

Architecture approval determines **how** it may be built.

Forge determines **how to execute** the approved engineering.

---

# Repository Truth

Mission documents are canonical repository artefacts.

Historical engineering conversations are not authoritative.

Repository Truth remains the sole architectural source of truth.
````