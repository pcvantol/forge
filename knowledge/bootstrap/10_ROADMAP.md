# Forge Roadmap

## Purpose and authority

This is Forge's canonical strategic roadmap. Roadmap presence does not authorize execution; bounded Engineering Intents/Missions and governance remain required. Forge evolves capability-first while preserving repository-first knowledge, human governance and execution-host independence.

## Strategic progression

```text
Bootstrap -> Foundation -> Self Engineering -> Runtime -> Production
```

Foundation is complete. Self Engineering is underway. Runtime and Production remain governed future maturity states rather than implied implementation commitments.

## Forge + Workspace V1 implementation programme

The V1 programme is dependency/capability driven. Cross-product milestones do not allocate another repository's implementation work. The derived `FORGE_WORKSPACE_V1_CROSS_PRODUCT_DEPENDENCIES.md` is an index, not authority.

### Productization reconciliation baseline

The [Productization Reconciliation](../../docs/architecture/FORGE_PRODUCTIZATION_RECONCILIATION.md)
is the target architecture for Product Vision, Portfolio/Roadmap/Forecast,
Runtime Service, Workspace, application services and MCP adapters. It does not
renumber L0–L10 or allocate cross-product work. Application-service/API,
Runtime Service, Workspace-facing projections, Business/Architecture session
support, Portfolio Intelligence, and MCP exposure are dependencies to be
introduced through approved Missions alongside the existing L0–L10 learning
increments. Installed-product qualification remains gated by L0/L1/L1-R/L10
and owner-qualified Workspace/EP contracts.

### L0 — Engineering Contract Foundation

**Node type:** CAPABILITY_MILESTONE. **Implementation owner:** Engineering Platform through `EP::ENGINEERING_CONTRACT_FOUNDATION_V1`; Forge is consumer.

The foundation must provide packaged baseline contracts, capability classification, Effective DoR, pre-dispatch readiness, Effective DoD, proof requirements, Human Gates, workflow projection, completion enforcement, `ActionQualityOutcome` and immutable Action snapshots.

It must also support consequence-driven transition profiles so migration/replacement/authority-transfer work can compose explicit readiness/retirement proof rather than relying on prompt prose.

Required baseline transition profiles/capabilities include the semantic equivalents of:

- `MIGRATION`
- `REPLACEMENT`
- `AUTHORITY_TRANSFER`
- `CUTOVER`
- `MIGRATION_RETIREMENT_COMPLETENESS`
- `AUTHORITY_TRANSFER_COMPLETENESS`

The exact representation is an EP implementation contract, but the resulting criteria must be first-class Action evidence.

**Exit:** installed EP can enforce Ready/Done, including applicable transition consequence/retirement criteria, without source-repository access.

### L1 — Learning Evidence + New-Project Bootstrap Contract

**Owner:** Forge + EP contract boundary.

Define versioned Action learning evidence and self-contained project bootstrap: installed baseline provenance, project-owned contract creation, Action contract versioning, privacy/redaction/retention and clean-install behavior. Include transition-quality evidence such as retirement findings, compatibility exceptions, successor-assumption proof and authority-transfer violations where applicable.

### L1-R — Managed Repository Governance Baseline

**Owner:** Forge with repository-host adapters and EP/CI proof integration.

Define a generic versioned Managed repository desired state rather than copying pcvantol settings. Cover protected/default branch, PR/review/conversation policy, validation-derived checks, security/CodeQL, trusted delivery, ownership, merge/cleanup, workflow permissions, dependency policy, rulesets and host limitations. Provision idempotently and read back actual state. Existing repositories use drift/adoption governance rather than silent overwrite.

**Exit:** a new Managed repository proves `REPOSITORY_GOVERNANCE = PASS` before general Ready.

### L2 — Quality Observer v1

**Owner:** Forge.

Run lightweight post-Action analysis. In addition to general DoR/DoD/late-failure signals, transition Actions must emit signals for unresolved legacy/retirement findings, old authority still reachable or writable, secondary operational authority/store, compatibility exceptions without retirement condition, obsolete packaged/runtime artifacts, successor assumptions discovered late, tests that preserve retired behavior and human-review discovery of incomplete transition consequences.

Zero automatic governance mutation.

### L3 — Quality Learning Review + Hardening Proposals

**Owner:** Forge.

Implement multi-Action reviews using `defect -> root cause -> pattern -> systemic hardening` and requirement-to-enforcement audits. For architecture transitions, explicitly evaluate whether prior work stopped at replacement validation instead of consequence closure.

Forge may propose strengthening transition DoR/DoD profiles, retirement completeness matrices, authority guards, dead-code/package audits, installed-product qualification and successor-assumption gates. Accepted hardening remains governed project policy.

### L4 — Workspace Quality Governance

**Owner:** Workspace dependency marker.

Workspace presents DoR/DoD/Human Gates and Quality Learning proposals. For transition Actions, the UX should expose consequence/retirement criteria, intentional compatibility exceptions and required human decisions without turning Workspace into execution authority.

### L5-L8 — Knowledge Learning

L5 defines the governed evidence export boundary to the independent Knowledge Base; L6 adds Forge Knowledge Observer proposals; L7 is the Workspace knowledge-governance dependency; L8 consumes Certified Knowledge read-only in Forge planning. Project policy remains distinct from Certified Knowledge and KB availability never becomes an EP execution dependency.

### L9 — Continuous Dual Learning

Run Quality and Knowledge observers after eligible Actions with bounded cost/health, milestone/release reviews, repeated-defect escalation and drift/gap triggers. Automation proposes/prepares; it never self-approves project governance or KB certification.

### L10 — Learning Effectiveness + Distribution Qualification

Measure first-pass qualification, DoR misses, DoD escapes, human-review escapes, repeated defects and time-to-Done. Use negative/mutation proof where practical.

Transition effectiveness additionally measures whether accepted hardening prevents recurrence of incomplete authority transfer, dead legacy runtime paths, unexplained compatibility code, obsolete packaged assets/services and successor-phase assumption escapes.

Permanent clean-install qualification proves local baseline contracts, project bootstrap, Managed repository governance, DoR/DoD/Human Gates and absence of source-repository runtime authority.

## Consequence-driven transition quality requirement

Architecture transitions are a first-class quality concern for Forge V1.

For every Action classified as migration/replacement/authority-transfer/cutover, planning and completion must reason beyond the immediate replacement:

```text
replacement works
    -> consumers/writers migrate
    -> old authority becomes impossible
    -> obsolete config/UI/services/state retire
    -> dead implementation/package artifacts retire
    -> historical evidence and justified compatibility remain classified
    -> anti-regression proof exists
    -> installed product proves the resulting topology
    -> successor assumptions are safe
```

The canonical semantics are defined in `docs/architecture/engineering-quality-learning-loop.md`.

This requirement exists specifically so future users do not have to remember ad hoc that a migration needs a dead-code audit, authority audit, package audit or successor-phase check. Applicability is derived from Action classification and becomes part of Effective DoR/DoD.

## Dependency guidance

```text
EP migration/cutover prerequisites
  -> EP::ENGINEERING_CONTRACT_FOUNDATION_V1 (L0 producer)
  -> L1 project/evidence bootstrap
  -> L1-R Managed repository governance
  -> L2/L3 Quality Learning
  -> Workspace L4 governance

Knowledge integration readiness
  -> L5 -> L6 -> L7 -> L8

Quality + Knowledge observers stable
  -> L9 -> L10
```

Safe parallelism is determined by the canonical cross-product dependency graph and stable producer contracts, not roadmap prose alone.

## Non-goals and authority constraints

- Forge does not become a second execution engine.
- EP does not autonomously rewrite project policy.
- Workspace does not become execution authority.
- Forge/EP/Workspace do not certify reusable engineering knowledge.
- KB does not mutate source repositories or become an execution dependency.
- Product upgrades do not silently rewrite project/repository policy.
- Transition hardening does not authorize blind deletion: historical evidence, migration tooling and intentional compatibility require explicit classification.
