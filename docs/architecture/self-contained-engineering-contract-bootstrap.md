# Self-Contained Engineering Contract Bootstrap

## Status

Canonical Forge target architecture for clean-install engineering-contract and Managed repository bootstrapping. This document defines future product behavior; it does not claim the capability is implemented.

It sharpens the Dual Engineering Learning System with one deployment invariant: a released Forge + Engineering Platform + Workspace installation must be able to create and govern a brand-new project without access to pcvantol development repositories or other source-authority repositories.

## Decision

Development repositories are build-time/source authorities, not runtime dependencies of a customer installation.

A clean installation carries a qualified baseline engineering capability inside the released product artifacts. Creating a new project bootstraps a project-owned engineering contract from that shipped baseline. For a Managed project with a supported repository host such as GitHub, the same bootstrap also applies a qualified Repository Governance Baseline before ordinary engineering begins. Each Engineering Action receives an immutable Effective DoR/DoD/Human-Gate snapshot composed from the project contract.

```text
source/development contracts
        -> build-time materialization
qualified Forge / EP release artifacts
        -> install
local baseline contract registry
        -> new Managed project bootstrap
project engineering contract + repository desired state
        -> provision and qualify repository host
        -> per-Action composition
immutable Effective DoR / Effective DoD / Human Gates
```

There must be no runtime dependency on pcvantol development/source repositories or on a network connection to a development-contract source repository.

## Three contract layers

The architecture distinguishes three layers of engineering rules.

### 1. Product baseline contract

Owned and versioned by the released Forge/EP product capability. It defines generic qualified profiles such as `BASE`, `DOCS`, `UI`, `API`, `PLATFORM_COMPONENT`, `TRANSPORT`, `SECURITY`, `INSTALLATION`, `DATA_MIGRATION`, and repository-governance profiles. The baseline is present locally after installation and usable offline.

### 2. Project engineering contract

Created when Forge bootstraps a project and owned thereafter by that project. It may contain baseline provenance, enabled profiles, project-specific DoR/DoD overlays, architecture invariants, guards, validation profiles, Goldens, Human Gate policy, repository governance overlays and accepted Quality Learning hardening.

Accepted Quality Learning changes this project contract, never hidden Forge memory. EP and CI must be able to enforce the project contract without Forge being continuously present.

### Default project production-code coverage policy

This section is the canonical Forge default-policy authority for project
production-code coverage. It is a product-baseline rule inherited by every
governed software project unless that project's governed contract records a
stricter rule or an explicit exception. Quality Learning may propose a change
to a project contract, but it does not create a second coverage-policy
authority.

#### Production scope

`PROJECT_PRODUCTION_CODE_COVERAGE` is measured over the aggregate of **all**
production code in the project. Production code includes code shipped or used
as part of supported runtime, application, domain, infrastructure,
persistence, security, and integration/adapter behavior. It is not limited to
changed files, selected protected modules, or another reduced path subset.

Tests, test fixtures, generated artifacts, browser/static assets, package
metadata, and genuine build/packaging tooling may be outside the denominator
when appropriate to the project's implementation and coverage tooling.
Production code must not be excluded merely because it is difficult to test.
Dead, unsupported code should be removed rather than excluded or tested solely
to improve coverage figures.

#### Default gate and governed evolution

```text
PROJECT_PRODUCTION_CODE_COVERAGE_THRESHOLD = 80.00%
PROJECT_PRODUCTION_CODE_COVERAGE_GATE = REQUIRED
```

The project may inherit this Forge default unchanged, define a stricter
aggregate threshold, or add stricter per-module thresholds. It may not
silently weaken the default. Any exception below `80.00%` must be explicit in
the governed project contract, justified, approved through the project's
normal governance, time-bounded where appropriate, and visible as quality debt
and a readiness impact.

Where the project's coverage tooling supports branch coverage, canonical
quality evidence also collects branch coverage. A project must not satisfy
this policy by measuring only an artificially reduced subset of reachable
production paths.

#### Critical-module visibility and anti-gaming invariants

An aggregate pass does not make severely under-tested critical production
modules acceptable. Quality evidence must keep security, authority,
persistence, orchestration, recovery, and other high-risk modules visible even
when aggregate coverage passes. A project may impose stricter per-module gates
for those modules.

```text
PRODUCTION_CODE_EXCLUDED_FOR_CONVENIENCE = FALSE
COVERAGE_THRESHOLD_SILENTLY_LOWERED = FALSE
BLANKET_NO_COVER_FOR_REACHABLE_PRODUCTION_CODE = FALSE
MEANINGLESS_TESTS_FOR_PERCENTAGE_ONLY = FALSE
```

#### Qualification, CI, and readiness meaning

Coverage evidence comes from the project's canonical qualification/test suite
and, where the product installation model requires it, from a clean candidate.
A stale installation, incomplete test collection, or contaminated candidate
cannot produce authoritative coverage evidence.

```text
PROJECT_PRODUCTION_CODE_COVERAGE < 80.00%
  -> quality gate FAIL
  -> not qualification-ready / merge-ready where the gate applies

PROJECT_PRODUCTION_CODE_COVERAGE >= 80.00%
  -> coverage gate PASS
  -> other quality, security, and readiness gates remain independent
```

For illustration only, an Engineering Platform measurement of `75.59%` across
all of that project's production code would fail this default even if selected
protected modules met stricter per-file gates. This does not make EP-specific
modules or thresholds part of the generic Forge policy.

### 3. Action engineering contract

For each Engineering Action, Forge/EP deterministically compose an immutable snapshot from product baseline version + project contract version + applicable profiles + explicit Action requirements. The snapshot includes Effective DoR, Effective DoD and applicable Human Gates and is durably attached to the Action.

## Executable contract representation

Engineering requirements must not exist only as prose and should not exist only as opaque hard-coded workflow branches. The target combines declarative contract data, qualified evaluation/provisioning code and human-readable documentation.

The contract declares what is required. Qualified product code knows how proof/provisioning mechanisms are executed and verified. Documentation explains intent and governance.

## Managed Repository Governance Baseline

A Managed project is not Ready merely because a remote repository exists. Forge must bootstrap the repository into a qualified desired governance state appropriate to the selected repository host and project capabilities.

The baseline must be generic product policy, not a blind copy of settings from pcvantol repositories. During baseline definition, observed settings from Forge, EP, TDE, AI Development Contracts and other mature repositories must be classified as:

- generic best practice;
- capability-dependent;
- organization/project-specific;
- technically required by Forge/EP workflow semantics;
- historical/incidental and therefore not baseline material.

The first GitHub profile should be a versioned `MANAGED_GITHUB_BASELINE_V1` (name/version illustrative until implemented).

### Baseline policy dimensions

The GitHub Managed baseline must explicitly model, where supported/applicable:

- canonical default branch (normally `main`);
- prohibition of direct protected-main mutation by automation;
- pull-request requirement for governed changes;
- review/approval policy and stale-approval semantics where applicable;
- conversation-resolution policy;
- required status/check policy;
- validation and security baseline checks;
- CodeQL/security scanning policy where supported;
- Trusted Delivery / owner-authorization integration when the project profile requires it;
- CODEOWNERS/ownership policy where applicable;
- allowed merge strategies and branch cleanup policy;
- workflow permission/security policy;
- dependency-update policy where supported;
- repository visibility and feature defaults only when explicitly selected by project/org policy;
- ruleset/branch-protection desired state;
- repository-host capability/version limitations.

The baseline must distinguish universal requirements from capability-derived checks. A UI project may add browser qualification; a Python project may add Python validation; a security-sensitive project may add stronger security gates. Required-check names must derive from the installed/project validation profile rather than being globally hard-coded.

### Desired state, provisioning and qualification

Repository governance is declarative desired state plus qualified provisioning and verification:

```text
Product repository-governance baseline
        + project/org overlay
        + capability profiles
        = Repository Desired State
                |
                v
        Forge provisions GitHub
                |
                v
Repository Governance Qualification
                |
                v
actual host state == expected governed state
```

A successful API call is not proof of compliance. Forge must read back the supported repository-host state and produce bounded qualification evidence.

Required target result:

`REPOSITORY_GOVERNANCE = PASS`

A Managed project must not become generally Ready while mandatory repository-governance requirements are failed or unknown. Unsupported host features must be represented explicitly as `N/A`, degraded policy, or a fail-closed incompatibility according to the profile; they must not silently disappear.

### New Managed GitHub project flow

Target flow:

```text
New Project -> Managed -> GitHub
        -> create/attach repository
        -> create bootstrap project tree
        -> materialize project engineering contract
        -> resolve capability profiles
        -> resolve Repository Desired State
        -> install required CI/security workflow assets
        -> configure ruleset/branch protection
        -> configure PR/review/merge policy
        -> configure required checks and ownership policy
        -> read back GitHub state
        -> Repository Governance Qualification
        -> READY only when required bootstrap/DoR evidence passes
```

This bootstrap is idempotent and must distinguish create, reconcile, drift detection and explicit governed policy evolution. It must not overwrite an existing project's intentional governance without an explicit reconciliation/adoption decision.

### Existing repository adoption

Attaching an existing repository is different from creating a new one. Forge must inspect actual governance, compare it with the applicable baseline/project policy and produce a drift/adoption plan. It must not silently rewrite repository settings merely because the repository differs from the current product baseline.

Possible outcomes include `COMPLIANT`, `DRIFT_REVIEW_REQUIRED`, `INCOMPATIBLE`, and governed reconciliation. Historical project policy remains auditable.

### Quality Learning relationship

Repository-governance failures and human/CI escapes are valid Quality Learning signals. Forge may later propose strengthening or relaxing repository policy, but accepted changes follow normal project governance. A repeated failure in a supposedly enforced repository rule must trigger analysis of whether provisioning, read-back qualification or the baseline itself is ineffective.

## EP responsibility

EP contains runtime primitives required to enforce supported Action contracts: Effective DoR/DoD, proof state, Human Gates, persistence, workflow projection and versioned baseline compatibility. EP consumes repository-governance evidence when it is part of an Action's DoR/DoD, but Forge owns new-project planning/bootstrap and repository desired-state orchestration. EP does not need source-repository access to enforce an already composed contract.

## Forge responsibility

Forge carries project bootstrap rules, baseline/project composition semantics, Action capability classification, Quality/Knowledge observer contracts, and repository-governance desired-state/provisioning/qualification semantics for supported repository hosts. Forge must not clone a development repository merely to learn how to engineer or govern a new project.

## Workspace responsibility

Workspace presents product baseline/version provenance, project contract version, Effective DoR/DoD/Human Gates, repository-governance state/drift and proposed Quality Learning changes. It is not the authority that defines or evaluates the contract.

## Updates and baseline evolution

Product upgrades may ship newer engineering and repository-governance baseline versions. An upgrade must not silently rewrite a project's accepted engineering or repository policy. The compatibility model distinguishes installed baseline, project-pinned/adopted baseline, available newer baseline, mandatory safety/compatibility migration, optional governed adoption and immutable historical Action snapshots.

## Relationship to Certified Knowledge

The AI Platform Engineering Knowledge Base is deliberately not required for clean-install engineering execution or repository bootstrap. Certified Knowledge integration remains additive.

## Required clean-install invariant

The product must eventually qualify an air-gapped/bootstrap scenario conceptually equivalent to:

```text
AIR_GAPPED_BOOTSTRAP_GOLDEN

clean machine
no access to pcvantol private/source repositories
install released Forge + EP + Workspace
create brand-new Managed project

verify:
  product baseline available locally
  project engineering contract created
  repository governance baseline available locally
  repository desired state resolved
  supported GitHub governance provisioned and read back
  REPOSITORY_GOVERNANCE = PASS
  Effective DoR composed
  NOT_READY Action blocked before dispatch
  READY Action can proceed
  Effective DoD composed
  automated proof mechanisms run
  Human Gate can block completion
  Action history preserves contract/gate evidence
  project contract remains inspectable/portable
  no source-repository runtime dependency exists
```

The no-source-repository part must be air-gapped; remote GitHub provisioning obviously requires connectivity to the selected repository host. Qualification must therefore separately prove offline baseline availability and online repository-host provisioning without access to development/source-authority repositories.

## Required invariants

- `SOURCE_REPOSITORIES_ARE_NOT_RUNTIME_AUTHORITY = TRUE`
- `CLEAN_INSTALL_ENGINEERING_BASELINE_LOCAL = TRUE`
- `NEW_PROJECT_BOOTSTRAP_OFFLINE_CAPABLE = TRUE`
- `PROJECT_CONTRACT_PROJECT_OWNED = TRUE`
- `DEFAULT_PROJECT_PRODUCTION_COVERAGE_POLICY = DEFINED`
- `DEFAULT_PROJECT_PRODUCTION_COVERAGE_THRESHOLD = 80.00%`
- `PRODUCTION_SCOPE_AGGREGATE = ALL_PRODUCTION_CODE`
- `PROJECT_CAN_DEFINE_STRICTER_THRESHOLD = TRUE`
- `SILENT_WEAKENING_ALLOWED = FALSE`
- `GOVERNED_EXCEPTION_REQUIRED_BELOW_DEFAULT = TRUE`
- `CRITICAL_LOW_COVERAGE_REMAINS_VISIBLE = TRUE`
- `DUPLICATE_QUALITY_POLICY_AUTHORITY = 0`
- `ACTION_CONTRACT_IMMUTABLE_AFTER_ADMISSION = TRUE`
- `DOR_DOD_PROOF_EXECUTABLE_NOT_DOCUMENTATION_ONLY = TRUE`
- `MANAGED_REPOSITORY_GOVERNANCE_DECLARATIVE = TRUE`
- `REPOSITORY_GOVERNANCE_PROVISION_AND_READBACK = REQUIRED`
- `NEW_MANAGED_PROJECT_REPOSITORY_GOVERNANCE = PASS_BEFORE_READY`
- `EXISTING_REPOSITORY_POLICY_NOT_SILENTLY_REWRITTEN = TRUE`
- `KB_NOT_REQUIRED_FOR_EXECUTION_BOOTSTRAP = TRUE`
- `AIR_GAPPED_BOOTSTRAP_QUALIFICATION = REQUIRED`

## Roadmap relationship

L0 defines/enforces packaged Effective DoR/DoD/Human Gate semantics. L1 defines learning evidence and new-project bootstrap. L1-R adds the Managed Repository Governance Baseline, GitHub desired-state/provision/read-back qualification and existing-repository drift/adoption contract. Installer/Release qualification must prove the final clean-machine/no-source-authority invariant. Later Quality Learning may evolve project repository policy through governed hardening.
