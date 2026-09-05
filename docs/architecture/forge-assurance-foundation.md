# Forge Assurance Foundation

## Status

This document defines the canonical architectural direction for **Assurance** as a first-class Forge Foundation capability.

Assurance is part of the Foundation model, alongside Mission/Governance and Knowledge Learning. This decision does **not** require the complete Assurance system or all Assurance domains to be implemented for Forge V1. Roadmap placement is capability-driven and may be delivered incrementally after V1 where dependencies, product maturity, or cost justify it.

## Foundation model

Forge autonomy is not complete merely because Forge can plan and execute engineering work. The Foundation must support three complementary feedback systems:

```text
FORGE FOUNDATION
|
+-- Mission / Governance Core
|   +-- Business -> Architecture -> Mission
|   +-- Mission Planner / Action Derivation
|   +-- governed execution
|
+-- Knowledge Loop Foundation
|   +-- observe -> learn -> knowledge -> reuse
|
+-- Assurance Loop Foundation
    +-- observe -> evidence -> finding -> remediation
        -> re-audit -> qualification
```

Knowledge and Assurance are intentionally distinct. Knowledge Learning determines what Forge and its projects can learn and reuse. Assurance continuously attempts to falsify quality, safety, compliance, architecture, delivery, and runtime claims against evidence.

## Assurance Core

Forge should implement Assurance through one generic, interface-neutral core rather than separate lifecycle infrastructure for each assurance domain.

First-class concepts should include semantic equivalents of:

- `AssurancePolicy`
- `AssuranceEvidence`
- `AssuranceFinding`
- `AssuranceAuditRun`
- severity and confidence
- exact-head, release, deployment, installation, and runtime provenance
- baseline and trend evidence
- remediation state
- re-audit state
- qualification outcome

An Assurance domain contributes policies, collectors/auditors, evaluators, and domain-specific evidence. It does not create a second Mission, planning, execution, or governance authority.

Canonical lifecycle:

```text
observation / evidence
        -> Assurance audit
        -> Finding
        -> policy + severity + confidence
        -> remediation proposal
        -> Mission Planner / Action Derivation
        -> governed Action
        -> execution
        -> new evidence
        -> re-audit
        -> resolved / still open / qualified
```

Evidence and findings never directly authorize engineering execution. Existing Mission, risk, Human Gate, security, and execution contracts remain authoritative.

## First-class Assurance domains

### Security Assurance

Continuously evaluates security contracts, authorization and authority boundaries, secret handling, dependency and vulnerability evidence, threat-model invariants, security regressions, and exact-head qualification.

The long-term goal is an autonomous `find -> remediate -> re-audit` loop so ordinary implementation findings do not require repeated human prompting. A genuinely new security/authority boundary still escalates to human governance.

### Privacy Assurance

Evaluates data flows, data minimization, classification, retention/deletion, redaction, consent where applicable, cross-boundary transfer, telemetry/privacy contracts, and privacy regressions.

Telemetry is evidence, not authority. Privacy-sensitive evidence must remain subject to minimization and retention policy.

### Accessibility Assurance

Evaluates accessibility policy and product evidence, including WCAG-oriented conformance, keyboard operation, focus management, semantic/ARIA behavior, contrast, zoom/reflow, reduced motion, touch targets, and relevant human-review evidence.

Machine-verifiable accessibility evidence may drive remediation proposals; subjective usability claims remain eligible for Human Gates.

### Quality Assurance

Owns continuous product/code quality evidence, including:

- test quality and production-code coverage;
- branch/negative-test coverage where supported;
- regressions and flaky tests;
- complexity, duplication, dead code, and maintainability;
- technical debt and deferred-work aging;
- deprecated APIs, stale compatibility, feature flags, migrations, TODO/FIXME debt;
- quality trends and repeated defects.

The default Forge project quality policy is repository-wide coverage across **all production code**, with a default minimum of **80%** unless a stricter governed project policy applies. Selected protected-module gates may be stricter, but do not replace the repository-wide production-code gate. Production code may not be excluded merely to make the metric pass.

Technical-debt detection is primarily a Quality Assurance responsibility. Debt should be observable as evidence and trends rather than only as static backlog text.

### Architecture / Contract Assurance

Evaluates implementation drift against canonical architecture, contracts, authority boundaries, dependency rules, migration/retirement invariants, documentation/runtime truth, and anti-regression requirements.

Drift detection may be performed by Quality or generic collectors, but a finding is routed to the Assurance domain that owns the violated contract. Examples:

- coverage regression -> Quality;
- secret in logs -> Security;
- unnecessary personal-data persistence -> Privacy;
- keyboard/focus regression -> Accessibility;
- CWD reintroduced as project authority -> Architecture / Contract.

### Deployment / CI-CD Assurance

Continuously evaluates the delivery system itself rather than treating CI/CD as a passive gate. Evidence includes:

- pipeline failure and flake rates;
- queue time and total duration;
- job/runtime benchmarks and regressions;
- cache efficiency and duplicate work;
- runner/environment instability;
- deploy success and rollback rates;
- change failure rate and time to recovery;
- obsolete actions/tooling and pipeline drift;
- cost/efficiency where available.

The loop should form evidence-backed improvement proposals and compare before/after benchmarks rather than blindly rewriting pipeline configuration.

### Runtime Observability & Reliability Assurance

Consumes bounded runtime evidence from metrics, logs, traces, crash reports, exceptions, health, performance, availability, and runtime events.

Responsibilities include:

- crash fingerprinting and deduplication;
- regression detection and exact deployment/version correlation;
- anomaly and trend detection;
- probable root-cause analysis with confidence;
- latency, memory, resource, and availability regressions;
- remediation proposals;
- post-deployment re-observation and qualification.

Observability data is evidence. A crash, metric, log, trace, or anomaly never directly authorizes an Action.

## Shared finding model and routing

Assurance findings should share one canonical model containing at least:

```text
AssuranceFinding
  domain
  policy
  evidence
  severity
  confidence
  affected_scope
  exact_head / release / deployment / runtime provenance
  remediation_state
  re_audit_state
  qualification_state
```

Collectors may discover cross-domain drift. Ownership is determined by the violated policy/contract rather than by the collector that found it.

## Relationship to Mission Planning and execution

Assurance must integrate with the canonical Mission Planner / Action Derivation boundary. An auditor may create a finding and a bounded remediation proposal; it does not hand-author runtime execution authority or bypass Mission governance.

A normal future autonomous flow is:

```text
exact head / deployment / runtime
        -> Assurance evidence
        -> Finding
        -> remediation proposal
        -> Action Derivation
        -> governed Action
        -> execution
        -> re-audit
        -> qualification
```

Human intervention remains required where project policy, risk, Business, Architecture, Security, Privacy, Accessibility, or other Human Gates require it.

## Relationship to Knowledge Learning

Knowledge and Assurance share evidence/provenance infrastructure where useful but remain separate semantic loops:

- **Knowledge Loop:** observe -> learn -> knowledge -> reuse.
- **Assurance Loop:** observe -> challenge claim -> finding -> remediation -> re-audit -> qualification.

Assurance findings may later become Knowledge Learning evidence. Certified Knowledge does not automatically become Assurance policy, and Assurance findings do not certify reusable knowledge.

## Autonomy principle

Forge autonomy should ultimately be evaluated as **build + learn + assure**, not only autonomous execution.

The target maturity invariant is:

> Forge can autonomously observe supported engineering, delivery, and runtime evidence; form bounded findings; propose remediation; route it through canonical planning/execution governance; and re-audit the result, escalating to humans only when policy or a genuinely new authority boundary requires it.

This is a Foundation architectural invariant, not a V1 implementation completion criterion.

## V1 boundary

This document deliberately does **not** require all Assurance domains, collectors, remediation automation, observability integrations, or continuous autonomous loops to be delivered for V1.

V1 may continue to use existing explicit CI, Security review, Quality Learning, Human Gates, and qualification mechanisms. Later roadmap increments can converge those mechanisms onto the shared Assurance Core.

Therefore:

- `ASSURANCE_IS_FOUNDATION_ARCHITECTURE = TRUE`
- `ASSURANCE_FULL_IMPLEMENTATION_REQUIRED_FOR_V1 = FALSE`
- `ASSURANCE_DOMAINS_MAY_SHIP_INCREMENTALLY = TRUE`
- `ASSURANCE_DOES_NOT_BYPASS_MISSION_GOVERNANCE = TRUE`
- `ASSURANCE_EVIDENCE_IS_NOT_EXECUTION_AUTHORITY = TRUE`
- `KNOWLEDGE_AND_ASSURANCE_ARE_DISTINCT_FIRST_CLASS_LOOPS = TRUE`

## Non-goals of this decision

This decision does not:

- implement the Assurance Core;
- implement autonomous Security/Privacy/Accessibility/Quality auditors;
- add telemetry collection or crash-report infrastructure;
- change V1 readiness to require full Assurance implementation;
- grant auditors execution, merge, policy-mutation, or approval authority;
- replace existing Quality Learning or Knowledge Learning;
- allocate EP or Workspace implementation work.
