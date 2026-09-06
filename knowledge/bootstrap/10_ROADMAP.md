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

Forge is intentionally **on hold for execution integration** while EP proves the external execution producer. The current critical path is:

```text
EP P-NEUTRAL closure
  -> DJConnect real-project declaration + CENTRAL attachment
  -> one real governed DJConnect EP Action
  -> EP::STANDALONE_EP_VERIFIED
  -> EP self-development through CENTRAL
  -> EP::SELF_HOSTED_ENGINEERING_VERIFIED
  -> direct EP dogfood on Forge repository
  -> Forge materialization + execution admission
  -> existing EP P-TRANSPORT HTTP submission ingress
  -> EP canonical run/finalization/result evidence
  -> Forge result observation + reconciliation
  -> first Forge -> EP -> Forge governed execution canary
  -> autonomous next-Mission selection/repetition
```

### Critical-path corrections

1. **P-TRANSPORT is merged/closed.** EP already owns three canonical submission transports: HTTP, installed CLI and Server-owned File Inbox. Forge must reuse canonical HTTP submission ingress; it must not invent a second mutation transport.
2. **Local Consumer API read-only foundation and P-TRANSPORT submission HTTP are distinct.** Describing all installed EP HTTP integration as read-only is stale.
3. **Workspace is not required for the first autonomy canary.** Workspace remains human/project control plane and later projection/onboarding consumer.
4. **B8R project identity supersedes the older Workspace-ID assumption.** Durable identity is declared in `.engineering-platform/repository.json` and validated by EP.
5. **Broader Agent separation/generalized dispatch is follow-on work.** Multi-host, multi-Agent and generalized dispatch/scheduling are not default prerequisites.
6. **Queue/B8E work is evidence-driven, not blanket blocking.** Only concrete capabilities required by the installed real-project canary are immediate prerequisites.
7. **Real-project dogfooding precedes Forge orchestration.** DJConnect proves standalone; EP then proves self-development; Forge then proves it can be engineered directly by EP before Forge itself orchestrates EP.
8. **Owner gates are reserved for genuine authority expansion.** Engineering repair/validation/re-review inside an approved boundary should run autonomously.

`P_TRANSPORT_STATUS = MERGED_CLOSED`
`WORKSPACE_ON_FIRST_AUTONOMY_CRITICAL_PATH = FALSE`
`GENERAL_AGENT_SEPARATION_ON_FIRST_AUTONOMY_CRITICAL_PATH = FALSE`
`P_TRANSPORT_HTTP_IS_CANONICAL_FORGE_SUBMISSION_TARGET = TRUE`
`FORGE_EXECUTION_INTEGRATION_ON_HOLD_UNTIL_EP_REAL_PROJECT_PROOFS = TRUE`

## EP real-project producer proof required by Forge

Forge must not treat repository-local protocols or synthetic adapters as installed EP execution evidence. Before Forge resumes live execution integration, EP should provide these real-project proofs:

### Gate A — `EP::STANDALONE_EP_VERIFIED`

DJConnect is the mandatory first physical project canary:

```text
committed DJConnect .engineering-platform/repository.json
  -> EP validates + attaches repository to CENTRAL
  -> canonical P-TRANSPORT submission
  -> admission/run
  -> real provider/repository mutation
  -> DJConnect canonical validation
  -> finalization
  -> immutable receipt/result/provenance
  -> canonical observation
```

### Gate B — `EP::SELF_HOSTED_ENGINEERING_VERIFIED`

Immediately after standalone, the installed EP must execute one real bounded Engineering Platform repository change through CENTRAL. This proves EP can maintain its own product source through the same authority it exposes to consumers. This is the preferred producer-confidence gate before Forge depends on EP for normal engineering execution.

### Gate C — Forge repository direct-EP dogfood

Before or during Forge's execution-integration increment, the Forge repository receives its own committed B8R declaration and one real direct EP-governed development Action. This proves “EP can engineer Forge” independently from “Forge can orchestrate EP”, avoiding circular qualification.

Workspace may receive the same real-project dogfood later, but it is not blocking for the first Forge autonomy loop.

## Immediate executable Forge slice

After the EP producer proofs above, Forge should implement/qualify one narrow F3/F4 slice:

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

## Forge + Workspace V1 implementation programme

The V1 programme is dependency/capability driven. Cross-product milestones do not allocate another repository's implementation work. Derived DAG/dependency documents are indexes/projections, not product authority. Future productization must not be promoted onto the bootstrap critical path without evidence.

## L0 — Engineering Contract Foundation

Long-term L0 remains an EP-produced rich contract for packaged baselines, capability classification, Effective DoR/DoD, readiness, proof requirements, Human Gates, workflow projection, completion enforcement and immutable Action snapshots. The first bootstrap canary consumes the minimum already-proven contracts and exposes genuinely missing producer capabilities as bounded gaps.

## L1 / L1-R — Bootstrap evidence and Managed repository governance

These harden project-owned contracts, baseline provenance and generic repository desired-state/read-back evidence. Full productization is not a prerequisite for the first bounded canary when the target repository already satisfies its explicitly pinned execution contract.

## L2–L3 — Quality Learning

Observe eligible Action outcomes and propose governed hardening after a reliable Action/EP outcome contract exists. Zero automatic governance mutation.

## L4 — Workspace Quality Governance

Workspace-owned dependency marker. Workspace presents governed projections and permitted human intent; it does not become runtime authority and does not block the first Forge -> EP -> Forge machine loop.

## L4-AI / L5–L10

AI exposure, Knowledge Learning, continuous dual learning and effectiveness/distribution qualification remain later maturity lanes. They consume canonical application/execution evidence and do not block the first autonomous execution proof.

## Authority and state rules

- Forge owns why/what: roadmap, Mission, Action intent, planning dependencies and governance.
- EP owns how: submission/admission, execution lifecycle, queue/lease where applicable, provider execution, finalization, receipts and canonical execution evidence.
- Workspace owns human/project UX and projections, never execution lifecycle authority.
- Canonical Project Authority Repository declares project/repository identity; EP validates it.
- Forge records intended Action/submission identity before EP submission; EP persists canonical submission/run evidence; Forge reconciles by correlation/run identity.
- A retry never invents a second submission when the first POST outcome is ambiguous.
- Provider output is never directly executable authority.
- Reports, logs, browser selection and current checkout are not lifecycle authority.

## Dependency guidance

```text
CURRENT EP PRODUCER BOOTSTRAP:
P-NEUTRAL
  -> DJConnect real Action
  -> STANDALONE_EP_VERIFIED
  -> EP self-development real Action
  -> SELF_HOSTED_ENGINEERING_VERIFIED
  -> Forge repository direct-EP dogfood

FORGE RESUMES:
materialization/admission
  -> existing P-TRANSPORT HTTP
  -> result observation/reconciliation
  -> first Forge -> EP -> Forge canary
  -> autonomous next-Mission loop

FOLLOW-ON EP PRODUCTIZATION:
broader Agent separation / generalized dispatch / multi-host / multi-repository

FOLLOW-ON CROSS-PRODUCT:
Workspace dogfood/control plane; L1/L1-R hardening; Quality/AI/Knowledge maturity
```

## Non-goals and authority constraints

- Forge does not become a second execution engine.
- EP does not become a planner or autonomously rewrite Forge policy.
- Workspace does not become execution authority.
- Forge must not duplicate the existing P-TRANSPORT submission transport.
- Broader Agent/queue architecture must not be inserted onto the bootstrap critical path without evidence that the minimum installed canary needs it.
- Real-project dogfood does not authorize parallel multi-project mutation; serial execution is sufficient for these proofs.
- Product upgrades do not silently rewrite project/repository policy.
- Historical evidence and intentional compatibility require explicit classification before retirement.
