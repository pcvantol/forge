# Forge Mission-driven Engineering

## Purpose and boundary

A **Mission** is Forge's highest operational engineering artifact and the
Architect-approved engineering contract. It defines the engineering objective,
architectural boundaries, success criteria, and constitutional constraints for
a coherent outcome. A Mission does not prescribe individual Engineering
Intents, an Intent sequence, Runtime Prompts, or execution steps.

This is an architecture reconciliation only. It introduces no Mission Planner
implementation, scheduler, storage migration, Runtime, provider, Execution
Host, Studio, repository operation, or autonomous execution.

## Canonical hierarchy and feedback loop

```text
Vision
  ↓
Architecture
  ↓
Roadmap
  ↓
Mission
  ↓
Mission Planner
  ↓
Engineering Intent
  ↓
Engineering Action
  ↓
Runtime Prompt
  ↓
Execution Host
  ↓
Repository
  ↓
Evidence
  ↓
Mission Planner
```

The loop is deliberate: repository evidence continuously informs the Mission
Planner's next planning decision. It is not a claim that any of these future
runtime capabilities is implemented.

## Mission and human governance

Humans approve Missions and remain responsible for governance. They do not
approve every Engineering Intent. The approved Mission is the stable human
contract; Forge is responsible for the iterative engineering planning that
operates within that contract. Evidence never broadens a Mission's objective,
boundaries, success criteria, or constitutional constraints without further
human governance.

## Mission Intake

**Mission Intake** is the CLI-owned admission step for an approved Mission
Document. It validates the approved contract and transforms it into Mission
State for deterministic execution. It is not Mission Planner: Mission Planner
remains the future Forge planning responsibility for dynamic Intents within an
approved Mission. Intake neither creates executable Missions nor grants
Business or Architecture Approval.

The operational placement and later autonomous recommendation loop are
canonical in the [Runtime Evolution Roadmap](runtime-evolution-roadmap.md).

## Mission Planner

The **Mission Planner** is Forge's future planning responsibility between an
approved Mission and dynamic Engineering Intents. It owns engineering planning,
sequencing, dependency management, progress evaluation, creation of
Engineering Intents, and reprioritisation. It continuously evaluates
repository evidence and may create, supersede, merge, split, or retire active
Intents while preserving the Mission contract.

The Mission Planner is not a scheduler, does not execute Actions, does not
operate a repository, does not approve Missions, and does not weaken human
governance. This document defines the responsibility only; implementation is
explicitly deferred.

## Dynamic Engineering Intents

An Engineering Intent is a tactical, model-independent planning artifact
created by the Mission Planner during Mission execution. It gives a coherent
body of work its rationale, boundaries, validation, expected evidence, and
architectural traceability. It may contain one or more Engineering Actions.

Active Intents are not static Mission membership. As the Planner learns from
repository evidence, an Intent may be created, superseded, merged, split, or
disappear. A historical Intent remains immutable: historical records preserve
the exact planning decision and its provenance, rather than being rewritten to
fit a later plan.

## Actions, prompts, repositories, and evidence

An Engineering Action is the smallest intentional executable engineering unit.
An Action produces a provider-specific Runtime Prompt. The Execution Host uses
that prompt; the Repository records the resulting implementation reality; and
Evidence makes that reality assessable by the Mission Planner. Engineering
Intents do not directly produce Runtime Prompts.

The temporary Engineering Platform 1.5 Genesis runner is an external Execution
Host during bootstrap. It does not become Forge's planner, Runtime, repository
owner, or governance authority.

## Compatibility and next increment

Earlier Mission and Intent contracts preserve historical bootstrap provenance.
Their fixed membership and direct Intent-to-prompt language is not the
canonical future architecture and must not be extended. A separately governed
migration may reconcile implementation contracts later.

The recommended next increment is the **Bootstrap Mission Scheduler**. It
should schedule released Engineering Actions, retain Mission and Intent context,
and preserve the non-executing boundary established here.
