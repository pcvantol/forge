# Project Intelligence and Dynamic Planning

## Status

Architecture direction for Forge project intelligence. This document defines concepts and authority boundaries; it does not make every described capability a V1 implementation prerequisite.

## Purpose

Forge should continuously understand a project's current state, likely future work and best next governed work without turning probabilistic inference into hidden roadmap authority.

The core model is:

```text
canonical Project Context
        |
        v
   Forge Knowledge
        |
        v
 dynamic inference
   /          \
  v            v
Expected     Roadmap/DAG
Missions      Insights
  |            |
  v            v
Mission      Roadmap Change
Candidates   Proposals
   \          /
    \        /
      Workspace human governance
              |
              v
     approved canonical change
              |
              v
         governed Mission
              |
              v
              EP
              |
           evidence
              |
              v
       refreshed Project Context
```

## Authority model

Forge owns reasoning, forecasting, Mission Candidate generation and Roadmap/DAG Change Proposal generation.

Workspace owns the human decision experience and role-specific projection of Forge proposals and canonical evidence.

Engineering Platform owns execution facts and canonical execution evidence.

Canonical project/repository sources remain durable authorities for approved roadmap, architecture, topology and policy where defined. Forge inference never silently rewrites them.

## Project Context

`Project Context` is the bounded canonical input to Forge planning at a point in time. It may include:

- approved roadmap and capability DAG;
- architecture decisions and constraints;
- project/repository topology;
- business objectives and priorities;
- governance and Human Gates;
- completed and active Missions;
- canonical EP execution evidence;
- quality/technical-debt evidence;
- learned project knowledge;
- current blockers and capability readiness.

Project Context is versioned or digest-bound when used to derive governed proposals so later reasoning can be traced to the evidence available at the time.

## Planning concepts

### Roadmap / Capability DAG

Canonical approved project direction: capabilities, milestones, outcomes, dependencies and gates. It answers: **where are we going and what must precede what?**

Roadmap nodes are not executable authority.

### Expected Mission

A dynamic Forge inference that work is likely to become necessary in the current project context.

Properties:

- non-canonical;
- confidence-bearing;
- may appear, change rank or disappear as evidence changes;
- may reference likely capability impact and dependency relevance;
- does not require cancellation history when it disappears because it was never approved work.

Expected Missions must not be persisted or projected as approved backlog items.

### Mission Candidate

An advisory, sufficiently concrete possible next Mission derived from Project Context, Forge Knowledge, current roadmap state and Expected Missions.

A Mission Candidate may be ranked by expected value, readiness, dependency impact, risk, uncertainty and critical-path contribution. It remains non-executable until selected and governed into a Mission.

### Mission

Canonical governed work selected for execution. A Mission is distinct from both an Expected Mission and a Mission Candidate and must satisfy the existing Mission governance lifecycle.

### Roadmap/DAG Insight

A non-canonical Forge inference about the structure of the approved plan, for example:

- a predecessor appears obsolete;
- a newly observed capability should unblock a node;
- work can safely move off the critical path;
- two capabilities can proceed in parallel;
- newly observed evidence suggests a missing dependency.

### Roadmap Change Proposal

A first-class advisory changeset produced from one or more Roadmap/DAG Insights. It can propose:

- add/remove dependency;
- reorder capability/milestone;
- add/remove/defer capability;
- change priority;
- change critical-path classification;
- mark an evidence-backed milestone complete;
- amend forecast assumptions.

A proposal must carry before/after structure, impact, evidence references, uncertainty and Forge reasoning. It is not canonical until the required human governance decision is approved.

## Fact, inference, forecast, recommendation and decision

Every user-facing project-intelligence claim must be classifiable as one of:

- `FACT`: directly supported by canonical evidence;
- `INFERENCE`: Forge-derived interpretation;
- `FORECAST`: probabilistic projection about future state/time/work;
- `RECOMMENDATION`: proposed next choice or plan change;
- `DECISION`: canonical human/governance outcome.

Workspace projections must preserve this distinction so inference is never presented as execution or roadmap evidence.

## Project Completion Model

Business-facing project progress should be a semantic projection, not a raw node-count percentage.

Forge may derive a `Project Completion Model` from:

- weighted approved capabilities/outcomes;
- remaining critical-path work;
- active Missions;
- high-confidence Expected Missions;
- historical delivery evidence;
- dependency structure;
- unresolved uncertainty.

Forecasts should expose ranges and confidence rather than false precision.

Example:

```text
Autonomous Engineering
  Platform extraction       COMPLETE
  Standalone EP             45%
  Forge orchestration       60%
  Workspace control plane   20%
  Autonomous operation      10%

Most-likely completion: 3-5 weeks
Confidence: 68%
Main uncertainty: first installed EP execution may expose finalization work
```

The concrete forecasting model is post-bootstrap product work; V1 should preserve the contracts needed to add it without changing authority semantics.

## Dynamic planning loop

After every material project event, Forge may refresh Project Context and re-evaluate planning:

```text
EP result / approved decision / architecture change
              |
              v
      refresh Project Context
              |
              v
   recompute Expected Missions
              |
              v
     rank Mission Candidates
              |
              +------> generate Roadmap/DAG Insights
                              |
                              v
                    Roadmap Change Proposal
```

Evidence-backed administrative transitions can eventually be policy-automated, but architectural dependency changes, business scope changes and other authority-bearing changes remain governed according to decision policy.

## Workspace contract

Workspace consumes Forge Project Intelligence through projections suitable for the user's role. Forge should expose stable identities and provenance for at least:

- project-context snapshot/digest;
- roadmap/capability node;
- dependency edge;
- Expected Mission;
- Mission Candidate;
- Roadmap Change Proposal;
- forecast/recommendation;
- evidence references;
- required decision type/role where known.

Workspace is not required for Forge to derive Mission Candidates or run the first autonomous machine loop. Workspace becomes the canonical human interaction surface for roadmap/DAG governance as that capability is productized.

## V1 preparation versus later productization

### Architectural preparation to establish early

- stable roadmap/capability/DAG node identity;
- explicit Expected Mission / Mission Candidate / Mission distinction;
- Project Context provenance/digest binding;
- Roadmap Change Proposal concept and immutable proposal identity;
- `FACT / INFERENCE / FORECAST / RECOMMENDATION / DECISION` classification;
- evidence-reference model compatible with Workspace projections;
- decision type / required role metadata seam.

### Not required for first Forge -> EP -> Forge canary

- interactive DAG editor;
- probabilistic completion forecasting engine;
- continuous automatic roadmap reordering;
- multi-role Workspace approval UI;
- automatic low-risk roadmap mutation;
- business portfolio forecasting.

These remain follow-on capabilities after the first reliable execution/reconciliation loop unless a concrete bootstrap dependency emerges.

## Non-goals

- Expected Missions are not a hidden second roadmap.
- Mission Candidates are not executable actions.
- Forge does not silently mutate canonical roadmap/DAG authority.
- Workspace does not become planning authority by rendering or approving Forge proposals.
- EP evidence is not reinterpreted by Forge as execution authority beyond the canonical EP contract.
