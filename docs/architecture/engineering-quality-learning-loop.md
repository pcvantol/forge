# Engineering Quality Learning Loop

## Status

Canonical target architecture for Forge/Workspace quality learning. This document defines future product behavior; it does not claim the capability is implemented.

This is the project-quality half of the canonical [Dual Engineering Learning System](dual-engineering-learning-system.md). Quality Learning and Knowledge Learning share Action evidence but never share authority.

## Purpose

Forge must become better at engineering a project as evidence accumulates. Quality Learning is not merely remembering defects: it converts observed failures, rework, human-review findings, late qualification failures and recurring friction into proposed improvements to the project's executable engineering contract.

> Quality Learning is not remembering what went wrong; it is converting what went wrong into enforceable project capability.

The inherited Forge default coverage policy is defined only in the canonical
[Self-Contained Engineering Contract Bootstrap](self-contained-engineering-contract-bootstrap.md#default-project-production-code-coverage-policy).
Quality Learning can use its evidence, propose governed project hardening, and
surface debt; it does not redefine the threshold, production scope, or
exception process.

## Responsibility boundary

- **EP** executes and enforces the current Engineering Action contract and durable proof; it does not autonomously rewrite project policy.
- **Forge** plans and learns from evidence, proposing DoR/DoD, validation, guard, Golden and policy evolution.
- **Workspace** is the human governance surface for inspecting and accepting/modifying/rejecting learning proposals.

Accepted hardening belongs to the project-owned engineering contract, not hidden Forge memory.

## Per-Action Quality Observer

A lightweight Quality Observer runs after every eligible Engineering Action. It records signals including DoR misses, DoD failures, repair iterations, late CI/hosted failures, human-review rejection, security findings, architecture-boundary violations, green tests that missed product requirements, documented requirements lacking executable enforcement, repeated manual checks and time/attempts to actual Done.

A durable `ActionQualityOutcome` preserves these observations without changing execution history.

## Quality Learning Review

Forge may review recent Actions, a milestone/release, human-review rejection, security findings, repeated failures or threshold signals. Findings are clustered as:

1. **Defect** — concrete observed failure.
2. **Root cause** — why it was possible.
3. **Pattern** — recurring/generalizable weakness.
4. **Systemic hardening** — control that prevents/detects the class earlier.

Multiple defects may be manifestations of one missing invariant.

## Requirement-to-enforcement audit

For relevant requirements Forge evaluates:

```text
Requirement
  -> where is it canonical?
  -> how is it enforced?
  -> what proof demonstrates compliance?
  -> can an invalid implementation still qualify green?
```

Useful gaps include `MISSING_REQUIREMENT`, `REQUIREMENT_DOCUMENTED_ONLY`, `ENFORCEMENT_INCOMPLETE`, `TESTS_WRONG_ABSTRACTION`, `ARCHITECTURE_PERMITS_INVALID_STATE`, and `HUMAN_JUDGEMENT_REQUIRED`.

## Consequence-driven architecture transitions

Migration, replacement, authority-transfer and cutover Actions require a stronger quality model than ordinary feature work.

A replacement is not complete merely because the new path works. Forge must reason forward from the architecture decision and close its necessary consequences.

For an architecture transition, the planner/observer asks four layers of questions:

1. **Direct completion** — is the replacement capability correct?
2. **Architecture consequences** — which previous truths/authorities can no longer remain valid?
3. **Product consequences** — what must change in UI, configuration, persistence, logging, services, packaging, installation, tests, security and recovery?
4. **Successor assumptions** — what will the next phase assume is already true, and has that actually been proven?

Three questions are mandatory during transition planning/review:

- **What becomes impossible now?** Which old code/state/configuration/authority may no longer exist?
- **What becomes mandatory next?** Which new capability or proof necessarily follows from this transition?
- **What will the next phase assume?** Which claims become implicit prerequisites for successor work?

This is the generic lesson from authority migrations: architecture transitions require **consequence closure**, not merely replacement validation.

## Migration / replacement capability classification

Forge target capability classification includes transition-sensitive profiles such as:

- `MIGRATION`
- `REPLACEMENT`
- `AUTHORITY_TRANSFER`
- `CUTOVER`

These classifications compose additional Effective DoR/DoD criteria. They do not depend on a particular product such as EP.

### Transition DoR

Before dispatch, applicable transition work should identify at minimum:

- old and new authority/capability;
- affected consumers and writers;
- state/persistence implications;
- configuration and service implications;
- compatibility obligations;
- historical evidence that must remain;
- successor-phase assumptions;
- retirement scope and explicit exceptions;
- qualification strategy for replacement and retirement.

An authority transfer with an unknown old writer/consumer set is not fully Ready merely because the new implementation is specified.

## MIGRATION_RETIREMENT_COMPLETENESS profile

For `MIGRATION`, `REPLACEMENT` or `CUTOVER` work, the Effective DoD should compose a reusable `MIGRATION_RETIREMENT_COMPLETENESS` profile where applicable.

Target criteria include:

```text
replacement implemented
consumers migrated
old reads stopped
old writes stopped
old routes unreachable
old configuration retired
old UI retired
old services/processes retired
old persistence authority retired
dead implementation removed
obsolete packaged assets removed
obsolete tests retired/reclassified
historical evidence preserved
intentional compatibility exceptions registered
anti-regression guard installed
installed-product proof completed
successor assumptions proven
```

A criterion may be explicit `N/A`, but it must not disappear silently.

### Retirement classification

Legacy findings discovered during transition closure are classified as:

- `ACTIVE_CANONICAL`
- `RETIRE_AND_REMOVE`
- `HISTORICAL_EVIDENCE_KEEP`
- `TEST_FOR_RETIREMENT_GUARD_KEEP`
- `INTENTIONAL_COMPATIBILITY_KEEP`
- `MIGRATION_TOOLING_KEEP`
- `UNRESOLVED`

Retained compatibility requires a reason, current authority/caller and retirement condition/milestone. Historical migration/ADR/provenance evidence is not dead production code.

## AUTHORITY_TRANSFER_COMPLETENESS profile

An `AUTHORITY_TRANSFER` additionally requires proof that runtime authority is singular after cutover.

Target invariants include:

```text
exactly one supported runtime authority
no secondary writers
no secondary operational store
no fallback authority
no authority derived from CWD/UI selection/implicit local state
restart and recovery preserve authority
supported reads and writes share the intended owner
```

The exact proof mechanisms are project/capability-specific, but absence of secondary authority is part of Done, not an optional cleanup task.

## Dead-code and packaged-runtime consequence

When a transition retires a runtime responsibility, Forge must not stop at route unreachability. Applicable qualification should inspect production reachability, imports/callers, services, packaged artifacts, templates/assets, localization keys, configuration, tests and installer/update/uninstall behavior.

Dead implementation should be removed when evidence proves it has no remaining responsibility. Compatibility and migration tooling are retained only through explicit classification. Guards should prevent high-risk retired authority from returning without creating brittle global word blacklists.

## Successor-assumption proof

A phase/increment may not declare transition completion solely from its own local acceptance criteria when the next phase depends on stronger consequences.

Example pattern:

```text
new runtime authority works
    -> old authority cannot read/write
    -> obsolete service/config/UI removed
    -> package contains only justified runtime artifacts
    -> installed candidate proves new topology
    -> successor installer/release work may rely on that topology
```

The roadmap/dependency graph should name these producer/consumer assumptions when they cross increment or repository boundaries.

## Effective Definition of Ready

An Engineering Action has a first-class Effective DoR before dispatch. It answers whether the Action is sufficiently prepared to begin engineering, distinct from EP execution preflight (whether a particular runtime/Agent can execute already-ready work).

Effective DoR is composed from a base contract plus applicable capability profiles such as UI, API, platform-component, transport, security, installation, data-migration and the transition profiles above. A failing DoR leaves the Action `NOT_READY`.

## Effective Definition of Done

An Engineering Action has a first-class Effective DoD describing the evidence required before completion. Validation, Goldens, security, hosted checks, delivery/finalization, retirement proof and human approvals become explicit proof requirements rather than an implicit collection of gates.

Each criterion has stable identity, applicability source/profile, state (`PENDING`, `PASS`, `FAIL`, explicit `N/A`), proof mechanism, evidence reference and timestamp. An Action is not Done while a required criterion is pending or failed.

## Human Gates and workflow projection

Human judgement is a first-class proof mechanism. Effective DoR, DoD and Human Gates are visible in running and historical Action workflows. Transition Actions should make retirement/consequence proof visible without permanently expanding the normal compact workflow; criteria and evidence are expandable.

## Capability-based contract composition

DoR/DoD are composed rather than universal checklists. Examples:

```text
Docs-only:              BASE + DOCS
Console change:         BASE + UI
Platform API + UI:      BASE + API + UI + PLATFORM_COMPONENT
Authority migration:    BASE + MIGRATION + AUTHORITY_TRANSFER
Runtime replacement:    BASE + REPLACEMENT + MIGRATION_RETIREMENT_COMPLETENESS
```

Quality Learning may propose profile evolution; accepted changes remain governed project changes.

## Quality Learning Record and regression proof

A Quality Learning Record preserves observations, failure clusters, root causes, prior enforcement, hardening proposals, accepted/rejected changes and resulting Actions. Where practical, hardening should prove that the historical defect would now be caught through negative/mutation qualification.

A repeated defect is a high-priority signal: Forge must ask why previously accepted hardening failed to prevent recurrence.

## Quality metrics

Useful diagnostics include first-pass qualification rate, human-review escape rate, post-ready repair count, late requirement discovery, DoR miss rate, DoD escape rate, repeated defect rate and time from implementation-ready to actual Done. Transition work may additionally track unresolved retirement findings, compatibility exceptions and successor-assumption escapes.

## Workspace experience

Workspace presents learning proposals with evidence and enforcement impact and allows authorized `Accept`, `Modify` or `Reject`. For architecture transitions it should expose consequence/retirement criteria and unresolved compatibility exceptions where operator judgement is required.

Forge never silently changes DoR, DoD, CI, Goldens, architecture policy or governance because the observer found a pattern.

Aggregate production-code coverage and optional stricter protected-module or
per-module coverage are complementary: selected-module passes never substitute
for the aggregate project gate, while aggregate passes do not hide critically
low-covered modules.

## Motivating lesson

The Engineering Platform CENTRAL migration demonstrated the generic failure mode. Green route/browser tests proved many replacement boundaries, while later human review exposed platform/project ownership leakage, localization enforcement gaps, incomplete operational contracts, stale legacy UI models, logging/settings incompleteness and remaining dead legacy paths.

The generic lesson is broader than EP:

> A component or capability is not fully migrated merely because its replacement path works. Its applicable reads, writes, actions, settings, logging, health, state, services, UI, packaging, compatibility, retirement, qualification and successor assumptions must be explicit and proven.

This is motivating evidence, not a Forge dependency on EP implementation details.

## Relationship to reusable knowledge learning

Quality Learning evidence may also feed the Knowledge Learning Loop, but project hardening is not Certified Knowledge. Conversely, Certified Knowledge may suggest controls but does not automatically rewrite project DoR/DoD.

## Roadmap boundary

Delivery is staged in the canonical Forge Roadmap. The Engineering Contract Foundation must support capability-based profiles including transition/consequence profiles before Forge can automatically enforce this method. Quality Observer/Review stages then learn from transition escapes and propose hardening.

**EP enforces. Forge learns. Workspace governs.**
