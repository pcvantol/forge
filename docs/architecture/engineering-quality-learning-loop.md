# Engineering Quality Learning Loop

## Status

Canonical target architecture for Forge/Workspace quality learning. This document defines future product behavior; it does not claim the capability is implemented.

This is the project-quality half of the canonical [Dual Engineering Learning System](dual-engineering-learning-system.md). The sibling Knowledge Learning Loop extracts reusable engineering evidence toward the independent Knowledge Base lifecycle. Quality Learning and Knowledge Learning share Action evidence but never share authority.

## Purpose

Forge must become better at engineering a project as evidence accumulates. The objective is not merely to remember defects or write retrospective notes. Forge converts observed failures, rework, human review findings, late qualification failures, and recurring friction into proposed improvements to the project's executable engineering contract.

> Quality Learning is not remembering what went wrong; it is converting what went wrong into enforceable project capability.

The learning loop is generic and applies to every project engineered through Forge.

## Responsibility boundary

- **Engineering Platform (EP)** executes and enforces the current Engineering Action contract. It owns execution-time gates and durable evidence, but does not autonomously rewrite project engineering policy.
- **Forge** plans engineering and learns from execution evidence. It identifies patterns and proposes changes to Definition of Ready, Definition of Done, validation, guards, Goldens, and engineering policy.
- **Workspace** is the human governance surface. It presents learning evidence and proposals and allows an authorized operator to accept, modify, or reject policy evolution.

Accepted hardening belongs to the canonical project contract/repository, not hidden Forge memory. EP and CI must be able to enforce it without Forge being present.

```text
Engineering Action
  → EP execution and evidence
  → Quality Observer
  → Learning Signals
  → Forge Quality Learning Review
  → Hardening proposals
  → Workspace human review
  → Approved Managed hardening Action(s)
  → Project engineering contract
  → EP/CI enforcement on future Actions
```

## Per-Action Quality Observer

A lightweight Quality Observer runs after every Engineering Action. It produces evidence and advice; it never silently mutates governance.

It records signals including:

- Definition-of-Ready failures or missing readiness information;
- Definition-of-Done failures;
- repair iterations;
- late CI/hosted failures;
- human-review rejection and findings;
- security findings;
- unexpected architecture-boundary violations;
- tests that passed while the product still failed a requirement;
- documented requirements lacking machine enforcement;
- repeated manual checks;
- final qualification attempts and time from implementation-ready to actual Done.

A durable `ActionQualityOutcome` preserves these observations without changing historical execution evidence.

## Quality Learning Review

Forge may run a Quality Learning Review on demand, after a milestone/release, after human-review rejection, when signal thresholds are reached, or over a requested window such as the last N Engineering Actions.

The review clusters observations at four levels:

1. **Defect** — concrete observed failure.
2. **Root cause** — why the failure was possible.
3. **Pattern** — recurring/generalizable engineering weakness.
4. **Systemic hardening** — control that prevents or detects the failure class earlier.

Multiple defects may be manifestations of one missing invariant and should not automatically create multiple narrow rules.

Example:

```text
Defect:
  untranslated UI escaped review
Root cause:
  English fallback allowed browser tests to pass
Pattern:
  documented requirement lacked executable enforcement
Hardening:
  locale-key parity + strict no-fallback + five-locale Golden + required CI gate
```

## Requirement-to-enforcement audit

For relevant requirements Forge evaluates:

```text
Requirement
  → where is it canonical?
  → how is it enforced?
  → what proof demonstrates compliance?
  → can an invalid implementation still qualify green?
```

Useful gap classes include `MISSING_REQUIREMENT`, `REQUIREMENT_DOCUMENTED_ONLY`, `ENFORCEMENT_INCOMPLETE`, `TESTS_WRONG_ABSTRACTION`, `ARCHITECTURE_PERMITS_INVALID_STATE`, and `HUMAN_JUDGEMENT_REQUIRED`.

A documented rule with ineffective enforcement is not a completed quality control.

## Hardening mechanisms

A proposal chooses the appropriate enforcement layer rather than always adding another test. Proposal classes include documentation clarification, architecture invariant, DoR rule, DoD rule, source guard, unit/integration/contract test, completeness matrix, Golden, validation-profile requirement, required CI gate, security rule, observability requirement, and human review gate.

Forge may propose `ADD`, `STRENGTHEN`, `MERGE`, `RELAX`, or `RETIRE` for controls. The learning loop can simplify obsolete/redundant rules as well as add rules.

## Effective Definition of Ready

An Engineering Action has a first-class **Effective Definition of Ready (Effective DoR)** before dispatch. It answers: **is this Action sufficiently prepared to begin engineering?**

This is distinct from EP execution preflight, which answers whether a particular runtime/Agent can execute already-ready work.

```text
Intent / planned Action
  → capability classification
  → compose Effective DoR
  → readiness evidence
  → READY
  → EP admission/dispatch
  → execution preflight
  → execution
```

Effective DoR is composed from a base contract plus capability profiles such as UI, API, platform-component, transport, security-sensitive, installation, and data-migration.

A UI/platform Action may require acceptance criteria, PLATFORM/PROJECT scope, affected route ownership, localization impact, validation profile, and required human review to be explicit before dispatch.

An Action that fails Effective DoR remains `NOT_READY` and is not dispatched merely because repository/provider preflight would succeed.

## Effective Definition of Done

An Engineering Action has a first-class **Effective Definition of Done (Effective DoD)**. It answers: **what evidence must exist before this Action may be considered complete?**

Existing validation, Goldens, security checks, hosted checks, delivery/finalization and human approvals become explicit proof requirements rather than an implicit collection of gates.

Each criterion has at minimum a stable identity, applicability source/profile, status (`PENDING`, `PASS`, `FAIL`, explicit `N/A`), proof mechanism, evidence reference, timestamp, and human approval identity when applicable.

Example:

```text
BASE + UI + PLATFORM_COMPONENT + API
→ Effective DoD
  - implementation acceptance
  - integration validation
  - five-locale localization
  - installed-browser validation
  - responsive behavior
  - platform/project scope consistency
  - component completeness
  - security
  - human UI review
  - governed delivery
```

An Action is not Done while a required criterion is pending or failed.

## Human Gates

Human judgement is a first-class proof mechanism, not prose in a prompt. Examples include UI review, architecture approval and high-risk owner authorization.

A Human Gate records gate type, applicability/reason, state, review artifacts/evidence, requested-at timestamp, approving/rejecting identity and timestamp, and bounded outcome/comment.

For example, a UI-changing Action may require `HUMAN_UI_REVIEW` with desktop, mobile, degraded-state and interaction artifacts. EP must not mark the Action complete while the gate is pending.

## Workflow projection

Effective DoR, Effective DoD and Human Gates are first-class Engineering Action projection data and are visible for running and historical Actions.

```text
Received
  → Definition of Ready   8/8 PASS
  → Admitted / Dispatched
  → Executing
  → Automated validation 12/12 PASS
  → Definition of Done    9/11
  → Human UI Review       WAITING
  → Delivery
  → Complete
```

The normal workflow remains compact; details expand to criteria, proof and evidence. Historical Actions retain immutable readiness/completion evidence, including failed readiness that prevented dispatch. Human gates receive distinct visual attention because operator action is required. Workspace may later provide richer review UX, while the canonical Action projection remains part of the execution/governance contract.

## Capability-based contract composition

DoR and DoD are not one universal checklist. Forge classifies the Action and composes reusable profiles deterministically and audibly.

```text
Docs-only:                  BASE + DOCS
Console change:             BASE + UI
Platform API + Console:     BASE + API + UI + PLATFORM_COMPONENT
Installer change:           BASE + INSTALLATION + UI + SECURITY + PLATFORM_COMPONENT
```

Quality Learning may propose profile evolution; accepted changes remain governed project changes.

## Quality Learning Record

A durable review artifact should preserve:

```text
QualityLearningRecord
  review_id
  project_id
  review_window
  observations[]
  failure_clusters[]
  lessons[]
    pattern
    root_cause
    existing_requirement
    prior_enforcement
    why_prior_control_failed
  hardening_proposals[]
    type
    scope
    enforcement_layer
    regression_proof
  accepted_hardening[]
  rejected_hardening[]
  resulting_actions[]
```

It is governance evidence, not execution authority.

## Regression proof

Where practical, hardening should prove the historical defect would now be caught. Forge may propose negative/mutation qualification such as removing a locale key, routing a PLATFORM endpoint through project delegation, or creating repository-local operational storage. If the injected historical defect still qualifies green, hardening is not proven.

## Learning triggers

The Quality Observer runs after every Engineering Action. A heavier review may be triggered by explicit operator request (`review last N Actions`), milestone/release completion, human-review rejection, security finding, repeated CI/qualification failures, unusual repair cycles, repeated defect classification, or a configured signal/confidence threshold.

A repeated defect is itself a high-priority signal: Forge asks why previously accepted hardening failed to prevent recurrence.

## Quality metrics

Metrics are diagnostic inputs, not one opaque quality score. Useful measures include first-pass qualification rate, human-review escape rate, post-ready repair count, late requirement discovery rate, DoR miss rate, DoD escape rate, repeated defect rate, and time from implementation-ready to actual Done.

## Workspace experience

Workspace presents learning proposals with evidence and expected enforcement impact. The operator can inspect evidence and `Accept`, `Modify`, or `Reject` each proposal. Approval may create Managed Engineering Actions that update the project's canonical engineering contract.

Forge never silently changes DoR, DoD, CI, Goldens, architecture policy or governance because the observer found a pattern.

## Motivating lesson

The Engineering Platform CENTRAL migration demonstrated why this capability is needed. Green route/browser tests proved many intended boundaries, while later human review exposed recurring classes: platform/project ownership leakage, localization requirements without sufficient enforcement, incomplete component operational contracts, stale legacy UI models, and technically rendered but operationally incomplete logging/settings behavior.

The generic lesson is:

> A component or capability is not fully migrated merely because its read path works. Its applicable read, detail, action/repair, settings, logging, health, localization, context, qualification and human-review contracts must be explicit and proven.

This is motivating evidence, not a Forge dependency on EP implementation details.

## Relationship to reusable knowledge learning

Quality Learning may itself produce evidence worth observing by the Knowledge Learning Loop. For example, repeated localization escapes across multiple projects may support a reusable Knowledge Candidate. That does not make a Quality Learning rule Certified Knowledge: the Knowledge Observer must preserve source evidence and the KB lifecycle remains authoritative.

Conversely, Certified Knowledge consumed by Forge may suggest likely quality profiles or controls, but it does not automatically rewrite Effective DoR/DoD. Adoption into project policy is governed separately.

## Roadmap boundary

Delivery is intentionally staged in the canonical [Forge Roadmap](../roadmap/0.1.md). The early EP Engineering Contract Foundation provides Effective DoR/DoD/Human Gates and structured outcomes; Forge then adds the Quality Observer and review intelligence; Workspace adds governance UX. Knowledge-learning stages remain independent and additive.

**EP enforces. Forge learns. Workspace governs.**