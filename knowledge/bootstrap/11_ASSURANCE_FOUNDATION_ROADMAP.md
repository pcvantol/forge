# Assurance Foundation Roadmap Lane

## Purpose

This roadmap companion records the future delivery lane for the Forge Assurance Foundation defined in `docs/architecture/forge-assurance-foundation.md`.

It does not renumber or replace the canonical L0–L10 sequence in `10_ROADMAP.md`, does not authorize execution, and does not make full Assurance implementation a Forge V1 completion requirement. It exists to keep the Foundation architecture visible in strategic planning while allowing implementation to mature incrementally after V1.

## Strategic placement

Forge Foundation maturity is defined as three complementary feedback capabilities:

```text
Mission / Governance Core
Knowledge Loop Foundation
Assurance Loop Foundation
```

The Assurance Loop Foundation is architectural Foundation scope, but its complete runtime realization is deliberately **not a V1 gate**.

Existing V1 Quality Learning, security qualification, CI, Human Gates, repository governance, transition-quality evidence, Knowledge Learning, and runtime/productization work remain valid. They are predecessor evidence and future integration points rather than reasons to force a complete Assurance platform into V1.

## Future Assurance Core capability

Introduce one generic Assurance Core with shared first-class concepts for:

- policies;
- evidence;
- findings;
- audit runs;
- severity/confidence;
- exact-head/release/deployment/runtime provenance;
- baseline/trend evidence;
- remediation state;
- re-audit;
- qualification.

The Core integrates findings with canonical Mission Planner / Action Derivation through bounded remediation proposals. It never becomes execution or governance authority.

## Initial domain lanes

The first planned domain families are:

1. **Security Assurance** — authority, secrets, threat contracts, vulnerability/security evidence and autonomous re-audit.
2. **Privacy Assurance** — data flows, minimization, classification, retention/deletion, redaction and privacy regressions.
3. **Accessibility Assurance** — WCAG-oriented evidence, keyboard/focus/semantic behavior, contrast, reflow, reduced motion and relevant Human Gates.
4. **Quality Assurance** — testing, repository-wide production coverage, regressions, maintainability, technical debt, debt trends and quality drift.
5. **Architecture / Contract Assurance** — architecture, authority, dependency, migration/retirement and implementation-contract drift.
6. **Deployment / CI-CD Assurance** — pipeline failures/flakes, duration/queue/cache benchmarks, runner drift, delivery reliability and evidence-backed optimization proposals.
7. **Runtime Observability & Reliability Assurance** — metrics/logs/traces/crashes/exceptions, anomaly and regression detection, performance/availability, causal analysis and post-remediation observation.

## Quality default carried into Assurance

The default Forge project quality policy is a minimum **80% aggregate coverage over all production code**. Projects may govern stricter thresholds and stricter critical-module gates. Selected protected-module coverage never substitutes for the repository-wide production-code metric, and production code must not be excluded merely to make the gate pass.

This policy is expected to become a Quality Assurance policy when the Assurance Core is implemented; until then existing project/CI qualification mechanisms may enforce it.

## Drift and technical debt

Technical-debt detection is primarily a Quality Assurance concern. Drift detection is a shared observation capability: findings are routed to the domain that owns the violated contract.

Examples:

- production coverage or complexity regression -> Quality;
- secret leakage -> Security;
- unnecessary personal-data persistence -> Privacy;
- keyboard/focus regression -> Accessibility;
- implementation reintroduces forbidden project-authority inference -> Architecture / Contract;
- CI duration/flake regression -> Deployment / CI-CD;
- crash/performance regression -> Runtime Observability & Reliability.

## Delivery sequencing

The implementation sequence is intentionally capability-driven rather than assigned to V1:

```text
existing V1 evidence / Quality Learning / Knowledge Learning
        -> shared Assurance evidence + finding model
        -> bounded Assurance Core
        -> first domain auditors
        -> remediation proposal integration with Action Derivation
        -> automatic exact-head / deployment / runtime re-audit
        -> trend, benchmark and effectiveness learning
```

Individual domains may be introduced independently once the shared contracts they need are stable. Security or Quality may mature earlier than Runtime Observability, for example. The roadmap must not require all seven domains to ship as one release.

## Autonomy maturity target

Long-term Forge autonomy is:

```text
build + learn + assure
```

The target is that ordinary findings can move through:

```text
observe -> evidence -> finding -> remediation proposal
        -> governed planning/execution -> re-audit -> qualification
```

without repeated human prompting. Human governance remains mandatory for genuinely new authority/security boundaries and any configured Human Gate.

## V1 boundary

Explicit roadmap invariants:

- `ASSURANCE_IS_FOUNDATION_ARCHITECTURE = TRUE`
- `ASSURANCE_FULL_IMPLEMENTATION_REQUIRED_FOR_V1 = FALSE`
- `ASSURANCE_DOMAINS_MAY_SHIP_INCREMENTALLY = TRUE`
- `ASSURANCE_CORE_IS_SHARED_NOT_SEVEN_DUPLICATE_SYSTEMS = TRUE`
- `ASSURANCE_EVIDENCE_IS_NOT_EXECUTION_AUTHORITY = TRUE`
- `ASSURANCE_DOES_NOT_BYPASS_MISSION_GOVERNANCE = TRUE`
- `KNOWLEDGE_AND_ASSURANCE_ARE_DISTINCT_FIRST_CLASS_LOOPS = TRUE`

## Non-goals

This roadmap addition does not allocate implementation work to Forge, EP, Workspace or the Knowledge Base; does not change the V1 implementation DAG; does not declare any Assurance domain complete; and does not authorize automatic policy mutation, approval, merge, deployment or remediation execution.
