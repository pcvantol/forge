# Forge Roadmap

## Purpose and authority

This is Forge's canonical strategic roadmap. Roadmap presence does not authorize execution; bounded Engineering Intents/Missions and governance remain required. Forge evolves capability-first while preserving repository-first knowledge, human governance and execution-host independence.

## Strategic progression

```text
Bootstrap -> Foundation -> Self Engineering -> Runtime -> Production
```

Foundation is complete. Self Engineering is underway. Runtime and Production remain governed future maturity states rather than implied implementation commitments.

## Current bootstrap autonomy critical path — 2026-09-06

The immediate objective is the shortest safe route to a real autonomous Forge operating loop, not completion of every future EP/Workspace productization capability.

Current qualified Forge foundation includes canonical governance persistence, Mission Intake/amendment lineage, Action-Derivation evidence, G011/provider boundaries, token-preflight binding, governed reattempt lineage, a real Action-Derivation provider canary, post-canary Security qualification and immutable canary closure. PR #40 is merged; this foundation must not be reopened without regression evidence.

The current critical path is:

```text
EP P-NEUTRAL closure
  -> qualify the minimum existing installed EP execution path
  -> EP::STANDALONE_EP_VERIFIED
  -> Forge materialization + execution admission
  -> existing EP P-TRANSPORT HTTP submission ingress
  -> EP canonical run/finalization/result evidence
  -> Forge result observation + reconciliation
  -> first Forge -> EP -> Forge governed execution canary
  -> autonomous next-Mission selection/repetition
```

### Critical-path corrections

1. **P-TRANSPORT is merged/closed.** EP already owns three canonical submission transports: HTTP, installed CLI and Server-owned File Inbox. Forge must reuse the canonical HTTP submission ingress; it must not wait for or invent a second mutation transport.
2. **The Local Consumer API read-only foundation and P-TRANSPORT submission HTTP are distinct.** The Phase-1 API was initially qualified read-only; later P-TRANSPORT added canonical mutating submission ingress. Derived documentation must not collapse these into “EP HTTP is read-only”.
3. **Workspace is not required for the first autonomy canary.** Workspace remains the human/project control plane and later projection/onboarding consumer, not planning or execution authority.
4. **B8R project identity supersedes the older Workspace-ID assumption.** Durable project/repository identity is declared in the Canonical Project Authority Repository at `.engineering-platform/repository.json` and validated by EP. Workspace may project that identity and own mutable human-facing state.
5. **Broader Agent separation/generalized dispatch is follow-on work.** The first standalone EP/Forge canary may use the existing installed execution path if it can prove one bounded governed execution, finalization and canonical result evidence. Multi-host, multi-Agent and generalized dispatch/scheduling are not default prerequisites.
6. **Queue/B8E work is evidence-driven, not blanket blocking.** Only concrete queue, lease, recovery, finalization or zero-loss gaps required by the first installed execution are on the immediate bootstrap path. Broader productization remains separately governed follow-on work.
7. **Owner gates are reserved for genuine authority expansion.** Engineering repair/validation/re-review inside an approved boundary should run autonomously to a merge/activation gate rather than creating approval micro-gates.

`P_TRANSPORT_STATUS = MERGED_CLOSED`

`WORKSPACE_ON_FIRST_AUTONOMY_CRITICAL_PATH = FALSE`

`GENERAL_AGENT_SEPARATION_ON_FIRST_AUTONOMY_CRITICAL_PATH = FALSE`

`P_TRANSPORT_HTTP_IS_CANONICAL_FORGE_SUBMISSION_TARGET = TRUE`

## Forge + Workspace V1 implementation programme

The V1 programme is dependency/capability driven. Cross-product milestones do not allocate another repository's implementation work. The derived `FORGE_WORKSPACE_V1_CROSS_PRODUCT_DEPENDENCIES.md` and `FORGE_V1_IMPLEMENTATION_DAG.md` are indexes/projections, not product authority.

The [Productization Reconciliation](../../docs/architecture/FORGE_PRODUCTIZATION_RECONCILIATION.md) remains the target architecture for Product Vision, Portfolio/Roadmap/Forecast, Runtime Service, Workspace, application services and MCP adapters. It does not turn future productization into prerequisites for the first executable bootstrap canary.

## Immediate executable slice

After `EP::STANDALONE_EP_VERIFIED`, Forge should implement/qualify one narrow F3/F4 slice:

1. one new low-risk Mission; do not reuse the Action-Derivation-only canary Mission;
2. one immutable Action snapshot/materialization;
3. one execution-admission record with exact repository/write-scope/human-gate bindings;
4. persist intended submission identity/idempotency/correlation before the EP call;
5. submit once through canonical EP P-TRANSPORT HTTP;
6. observe the exact EP run through canonical status/result/evidence projections;
7. reconcile terminal evidence idempotently in Forge;
8. stop after the first real canary;
9. only then add autonomous next-Mission selection/repetition.

Forge never writes the target repository directly and never reconstructs EP execution authority from logs, Console state or local process state.

## L0 — Engineering Contract Foundation

**Node type:** CAPABILITY_MILESTONE. **Producer owner:** Engineering Platform; Forge is consumer.

Long-term L0 still provides packaged baseline contracts, capability classification, Effective DoR, pre-dispatch readiness, Effective DoD, proof requirements, Human Gates, workflow projection, completion enforcement, `ActionQualityOutcome` and immutable Action snapshots. The first bootstrap canary should consume the minimum already-qualified EP contracts and expose any genuinely missing producer contract as a bounded gap rather than blocking on the full future L0 surface by assumption.

## L1 — Learning Evidence + New-Project Bootstrap Contract

**Owner:** Forge + EP contract boundary.

Define versioned Action learning evidence and self-contained project bootstrap: installed baseline provenance, project-owned contract creation, Action contract versioning, privacy/redaction/retention and clean-install behavior. This is not a prerequisite for the first single-project execution canary beyond the exact evidence fields that canary requires.

## L1-R — Managed Repository Governance Baseline

**Owner:** Forge with repository-host adapters and EP/CI proof integration.

Define generic versioned Managed repository desired state and read-back evidence. Existing repositories use drift/adoption governance rather than silent overwrite. Full managed-repository productization is not a blocker for the first bounded canary when the target repository already satisfies its explicitly pinned execution contract.

## L2–L3 — Quality Learning

L2 observes eligible Action outcomes; L3 reviews repeated patterns and proposes governed hardening. Zero automatic governance mutation. These follow the first reliable Action/EP outcome contract and do not block initial autonomy proof.

## L4 — Workspace Quality Governance

Workspace-owned dependency marker. Workspace presents governed projections and permitted human intent; it does not become runtime authority and does not block the first Forge -> EP -> Forge machine loop.

## L4-AI — AI Capability Exposure v1

Expose canonical Forge project intelligence through interface-neutral read/explain/propose adapters such as MCP after stable Forge application-service contracts. MCP remains adapter, never internal authority or execution transport.

## L5–L8 — Knowledge Learning

Governed export, observation, Workspace knowledge surface and read-only Certified Knowledge consumption remain additive/post-V1 relative to the first execution loop.

## L9 — Continuous Dual Learning

Run Quality and Knowledge observers after eligible Actions with bounded cost/health. Automation proposes/prepares; it never self-approves project governance or KB certification.

## L10 — Learning Effectiveness + Distribution Qualification

Measure first-pass qualification, DoR misses, DoD escapes, human-review escapes, repeated defects and time-to-Done. Permanent installed-product qualification remains a later maturity gate after the core autonomous execution loop exists.

## Authority and state rules

- Forge owns why/what: roadmap, Mission, Action intent, planning dependencies and governance.
- EP owns how: submission/admission, execution lifecycle, queue/lease where applicable, provider execution, finalization, receipts and canonical execution evidence.
- Workspace owns human/project UX and projections, never execution lifecycle authority.
- Forge records intended Action/submission identity before EP submission; EP persists canonical submission/run evidence; Forge reconciles by correlation/run identity.
- A retry never invents a second submission when the first POST outcome is ambiguous; reconcile by canonical identity.
- Provider output is never directly executable authority.
- Reports, logs, browser selection and current checkout are not lifecycle authority.

## Dependency guidance

```text
CURRENT BOOTSTRAP:
P-NEUTRAL
  -> minimum installed EP execution qualification
  -> STANDALONE_EP_VERIFIED
  -> Forge F3/F4 executable slice
  -> first Forge -> EP -> Forge canary
  -> autonomous next-Mission loop

FOLLOW-ON EP PRODUCTIZATION:
broader Agent separation / generalized dispatch / multi-host / multi-repository

FOLLOW-ON FORGE PRODUCTIZATION:
L1/L1-R hardening -> L2/L3 -> Workspace surfaces -> AI/Knowledge -> L9/L10
```

Safe parallelism is determined by actual producer contracts and qualification evidence, not historical phase labels or derived roadmap prose alone.

## Non-goals and authority constraints

- Forge does not become a second execution engine.
- EP does not become a planner or autonomously rewrite Forge policy.
- Workspace does not become execution authority.
- Forge must not duplicate the existing P-TRANSPORT submission transport.
- Broader Agent/queue architecture must not be inserted onto the bootstrap critical path without evidence that the minimum installed canary needs it.
- Product upgrades do not silently rewrite project/repository policy.
- Historical evidence and intentional compatibility require explicit classification before retirement.
- External AI clients do not receive implicit governed-mutation or execution authority.
