# Self-Contained Engineering Contract Bootstrap

## Status

Canonical Forge target architecture for clean-install engineering-contract bootstrapping. This document defines future product behavior; it does not claim the capability is implemented.

It sharpens the [Dual Engineering Learning System](dual-engineering-learning-system.md) and [Engineering Quality Learning Loop](engineering-quality-learning-loop.md) with one deployment invariant: a released Forge + Engineering Platform + Workspace installation must be able to create and govern a brand-new project without access to pcvantol development repositories or other source-authority repositories.

## Decision

Development repositories are build-time/source authorities, not runtime dependencies of a customer installation.

A clean installation must carry a qualified baseline engineering capability inside the released product artifacts. Creating a new project must bootstrap a project-owned engineering contract from that shipped baseline. Each Engineering Action then receives an immutable Effective DoR/DoD snapshot composed from the project contract.

```text
source/development contracts
        |
        | build-time materialization
        v
qualified Forge / EP release artifacts
        |
        | install
        v
local baseline contract registry
        |
        | new project bootstrap
        v
project-owned engineering contract
        |
        | per-Action composition
        v
immutable Effective DoR / Effective DoD / Human Gates
```

There must be no runtime dependency on:

- `pcvantol/ai-development-contracts`;
- `pcvantol/forge` source checkout;
- `pcvantol/engineering-platform` source checkout;
- any private pcvantol repository;
- a network connection to a development-contract source repository.

## Existing development projection pattern

Forge and EP already use offline generated AI-development projections in their source repositories. Those projections are bound to a source repository/commit, profile, digest and materializer version and are committed into the product source tree.

That pattern remains useful as a development-time provenance mechanism, but product distribution must carry the required executable baseline in the release artifact itself. A deployed product must never fetch its governing baseline from the original projection source at runtime.

The desired supply chain is:

```text
AI-development source contracts
        -> development-time projection/materialization
        -> Forge/EP source trees
        -> product build and qualification
        -> signed/versioned release artifacts
        -> installed local baseline registry
```

The source repository proves where a baseline came from. The installed artifact must be sufficient to execute it.

## Three contract layers

The architecture distinguishes three layers of engineering rules.

### 1. Product baseline contract

Owned and versioned by the released Forge/EP product capability.

It defines generic, qualified profiles and semantics required for a usable installation, for example:

- `BASE`;
- `DOCS`;
- `UI`;
- `API`;
- `PLATFORM_COMPONENT`;
- `TRANSPORT`;
- `SECURITY`;
- `INSTALLATION`;
- `DATA_MIGRATION`.

The exact profile set evolves by product version. The baseline is present locally after installation and is usable offline.

### 2. Project engineering contract

Created when Forge bootstraps a project and owned thereafter by that project.

It may contain or reference:

- project identity and baseline provenance;
- enabled capability profiles;
- project-specific Effective DoR/DoD overlays;
- architecture invariants;
- guards;
- validation profiles;
- Goldens;
- Human Gate policy;
- accepted Quality Learning hardening;
- explicit project adoption of reusable Certified Knowledge where governed.

Accepted Quality Learning changes this project contract, never hidden Forge memory. EP and CI must be able to enforce the project contract without Forge being continuously present.

The exact repository layout is an implementation decision, but project authority must be explicit and portable.

### 3. Action engineering contract

For each Engineering Action, Forge/EP deterministically compose an immutable snapshot from:

```text
product baseline version
+ project contract version
+ applicable capability profiles
+ explicit Action requirements
= Effective Action Contract
```

The snapshot includes Effective DoR, Effective DoD and applicable Human Gates. It is durably attached to the Action for auditability.

Later project-policy evolution must not retroactively alter the historical contract of an already admitted or completed Action.

## Executable contract representation

Engineering requirements must not exist only as prose and should not exist only as opaque hard-coded workflow branches.

The target representation combines three layers:

1. **declarative contract data** — stable criterion/profile identities, applicability, required proof and composition rules;
2. **evaluation/execution code** — implementation of proof mechanisms and state transitions;
3. **human-readable documentation** — intent, rationale, governance and operator guidance.

Conceptual example:

```yaml
criterion: LOCALIZATION_5_LOCALE
profile: UI
required: true
proof:
  - locale_key_parity
  - strict_no_fallback
  - five_locale_browser
```

The contract declares what is required. Qualified product code knows how each proof mechanism is evaluated. Documentation explains why the requirement exists and how it is governed.

A Markdown statement such as "all UI is localized" without executable proof is not sufficient completion enforcement.

## EP responsibility

The Engineering Platform release artifact must contain the runtime primitives required to enforce its supported contract version, including where applicable:

- Action capability/profile resolution contracts;
- Effective DoR evaluation;
- pre-dispatch readiness enforcement;
- Effective DoD evaluation;
- proof-state evaluation;
- Human Gate state and completion blocking;
- Action contract/evidence persistence;
- workflow projection;
- versioned baseline contract registry or equivalent packaged resource;
- migration/compatibility handling when installed product baselines evolve.

EP does not need access to Forge or development-contract source repositories to enforce an already composed Action contract.

## Forge responsibility

The Forge release artifact must carry the planning and learning semantics needed for a clean project, including where applicable:

- project bootstrap rules;
- baseline/project contract composition semantics;
- Action capability classification;
- planning-side DoR/DoD composition inputs;
- Quality Observer schemas and rule identities;
- Knowledge Observer schemas and evidence-envelope contracts;
- quality-learning proposal types;
- governance and bootstrap templates.

Forge uses the installed product baseline to create a project contract. It must not clone a development repository merely to learn how to engineer a new project.

## Workspace responsibility

Workspace presents the resulting local/project contracts and Action snapshots. It must be able to show:

- product baseline/version provenance;
- project contract version;
- Effective DoR/DoD/Human Gates for running and historical Actions;
- which rules are baseline versus project-specific;
- proposed Quality Learning changes before acceptance.

Workspace is not the authority that defines or evaluates the contract.

## New-project bootstrap

A brand-new project created from a clean installation follows this target flow:

```text
Install Forge + EP + Workspace
        -> verify bundled baseline compatibility
        -> create project
        -> materialize/initialize project engineering contract
        -> record baseline provenance/version
        -> select/derive initial capability profiles
        -> create first Engineering Action
        -> compose Effective DoR
        -> NOT_READY or READY
        -> EP dispatch/execution preflight
        -> execute
        -> compose/evaluate Effective DoD and Human Gates
        -> completion only when required proof passes
        -> Quality/Knowledge learning evidence emitted
```

No private repository access is part of the flow.

## Updates and baseline evolution

Product upgrades may ship newer baseline contract versions. An upgrade must not silently rewrite a project's accepted engineering policy.

The future compatibility model must distinguish:

- installed product baseline version;
- project-pinned/adopted baseline version;
- available newer baseline version;
- required security/compatibility migration;
- optional governed project adoption;
- historical Action snapshots.

Where a product upgrade must change a baseline for safety or compatibility, the migration must be explicit, auditable and covered by release compatibility policy.

Quality Learning may propose project hardening independently of product baseline updates.

## Relationship to Certified Knowledge

The AI Platform Engineering Knowledge Base is deliberately not required for clean-install engineering execution.

A fresh Forge/EP/Workspace installation must remain fully usable when no KB is installed or reachable. Certified Knowledge integration is additive planning/learning capability, not runtime contract bootstrap authority.

Later distributions may consume a qualified versioned Certified Knowledge artifact or adapter, but only through an explicit KB productization/consumption contract. The system must not infer a dependency on a GitHub repository clone.

## Required clean-install invariant

The product must eventually qualify an air-gapped/bootstrap scenario conceptually equivalent to:

```text
AIR_GAPPED_BOOTSTRAP_GOLDEN

clean machine
no access to pcvantol private/source repositories
no ai-development-contracts checkout
no Forge source checkout
no EP source checkout

install released Forge + EP + Workspace
create brand-new project

verify:
  product baseline available locally
  project engineering contract created
  baseline provenance recorded
  Effective DoR composed
  NOT_READY Action is blocked before dispatch
  READY Action can proceed to EP execution preflight
  Effective DoD composed
  automated proof mechanisms run
  Human Gate can block completion
  Action history preserves DoR/DoD/Gate evidence
  ActionQualityOutcome can be produced
  project contract remains inspectable/portable
  no source-repository runtime dependency exists
```

This Golden is a cross-product release qualification target. The exact execution boundary may be split between EP Engineering Contract qualification and later Installer/Release qualification, but the end-state invariant is non-negotiable.

## Required invariants

- `SOURCE_REPOSITORIES_ARE_NOT_RUNTIME_AUTHORITY = TRUE`
- `CLEAN_INSTALL_ENGINEERING_BASELINE_LOCAL = TRUE`
- `NEW_PROJECT_BOOTSTRAP_OFFLINE_CAPABLE = TRUE`
- `PROJECT_CONTRACT_PROJECT_OWNED = TRUE`
- `ACTION_CONTRACT_IMMUTABLE_AFTER_ADMISSION = TRUE`
- `DOR_DOD_PROOF_EXECUTABLE_NOT_DOCUMENTATION_ONLY = TRUE`
- `EP_CAN_ENFORCE_WITHOUT_FORGE_SOURCE = TRUE`
- `FORGE_CAN_BOOTSTRAP_WITHOUT_DEVELOPMENT_CONTRACT_SOURCE = TRUE`
- `KB_NOT_REQUIRED_FOR_EXECUTION_BOOTSTRAP = TRUE`
- `AIR_GAPPED_BOOTSTRAP_QUALIFICATION = REQUIRED`

## Roadmap relationship

The Forge roadmap treats this as part of the earliest learning-system foundation rather than a late packaging concern:

- L0 must define/enforce packaged baseline Effective DoR/DoD/Human Gate semantics in EP;
- L1 must make baseline/project/Action contract provenance part of the learning evidence contract;
- new-project bootstrap support must exist before Forge learning can be considered generic for arbitrary new projects;
- Installer/Release qualification must prove the final clean-machine/no-source-repository invariant;
- later Quality Learning evolves project rules on top of this baseline;
- later Knowledge Learning remains additive and independent.
