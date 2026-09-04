# Dual Engineering Learning System

## Status

Canonical Forge target architecture. This document consolidates the product-level learning model that was previously split between Forge quality-learning design and Forge Platform integration analysis. It does not claim the capabilities are implemented.

## Decision

Forge uses two complementary learning loops over Engineering Action evidence:

1. **Quality Learning Loop** — learns how a specific project should be engineered more reliably and proposes executable hardening of that project's engineering contract.
2. **Knowledge Learning Loop** — extracts reusable engineering knowledge from observable work and routes it through the independent AI Platform Engineering Knowledge Base (KB) lifecycle toward governed Certified Knowledge.

The loops share evidence but never share authority.

```text
                              Engineering Action
                                     |
                       evidence + outcome + review
                                     |
                    +----------------+----------------+
                    |                                 |
             Quality Observer                  Knowledge Observer
                    |                                 |
          project-specific learning             reusable implication
                    |                                 |
          Quality Learning Review              Engineering Observation
                    |                                 |
        DoR/DoD/guards/tests/Goldens           Knowledge Candidate
                    |                                 |
          project engineering contract          Concept -> Generalized
                    |                                 |
                    |                          governed certification
                    |                                 |
                    |                          Certified Knowledge
                    |                                 |
                    +---------------+-----------------+
                                    |
                           future Forge planning
                                    |
                           future Engineering Actions
```

## Why two loops

A single incident can produce two different forms of learning.

Example: a platform-scoped operation accidentally changes behavior when a project is selected.

- **Quality learning** may propose a project-specific route-ownership guard, a Definition-of-Done criterion, and a cross-context contract test. These controls belong to that project's executable engineering contract.
- **Knowledge learning** may record the incident as traceable evidence for a broader candidate such as "platform-scoped operations should remain independent of project-selection context." That statement is not authoritative merely because Forge inferred it; it must progress through the KB lifecycle before it can become Certified Knowledge.

This separation prevents project policy from masquerading as universal knowledge and prevents generalized knowledge from silently rewriting project governance.

## Shared evidence envelope

Every completed or terminal Engineering Action may expose a bounded learning evidence envelope containing references to:

- Action intent and capability classification;
- Effective Definition of Ready and readiness failures;
- implementation/delivery outcome;
- Effective Definition of Done and proof evidence;
- validation, CI, security, qualification and Golden results;
- human review findings and Human Gate outcomes;
- repair iterations and late defects;
- architecture decisions and trade-offs;
- relevant commits, pull requests and reports;
- incidents, rollbacks or blocked execution;
- `ActionQualityOutcome`;
- source repository/version/commit anchors.

Evidence is immutable input. Neither observer may rewrite execution history.

The envelope must support explicit inclusion/exclusion, redaction and privacy policy before evidence is exported outside the project/EP boundary.

## Quality Learning Loop

The Quality Learning Loop is defined in detail by [Engineering Quality Learning Loop](engineering-quality-learning-loop.md).

Its purpose is operational project improvement:

```text
Action evidence
  -> Quality Observer
  -> Learning Signals
  -> defect/root-cause/pattern clustering
  -> requirement-to-enforcement audit
  -> hardening proposals
  -> Workspace human review
  -> approved Managed hardening Action
  -> canonical project engineering contract
  -> EP/CI enforcement
```

It may evolve Effective DoR/DoD profiles, architecture invariants, guards, tests, Goldens, validation profiles, CI requirements, observability requirements and Human Gates. It never silently changes policy.

## Knowledge Learning Loop

The Knowledge Learning Loop preserves the lifecycle and authority model owned by `pcvantol/ai-platform-engineering-knowledge-base`.

Canonical lifecycle:

```text
Engineering Source
  -> Engineering Observation
  -> Knowledge Candidate
  -> Knowledge Concept
  -> Generalized Knowledge
  -> governed certification
  -> Certified Knowledge
  -> derived publication/consumption
```

An Engineering Observation is evidence, not knowledge. Candidate, Concept and Generalized Knowledge remain non-authoritative until governed certification. AI may assist observation discovery, candidate proposals, classification, relationship discovery, duplicate detection and generalization; AI does not certify knowledge.

Registered Knowledge Sources remain read-only. Knowledge operations must not mutate source repositories.

## Knowledge Observer

The target Forge Knowledge Observer runs as a lightweight post-Action analysis, analogous to the Quality Observer but with a different output contract.

It may propose:

- new Engineering Observations;
- links to existing observations/candidates;
- reusable implications;
- source/evidence classifications;
- duplicate/relationship suggestions;
- confidence and uncertainty notes;
- candidate extraction work for the KB.

It must not:

- create Certified Knowledge;
- claim generated summaries are evidence;
- remove source lineage;
- mutate source repositories;
- bypass KB source approval/extraction policy;
- make KB availability an EP admission or execution dependency.

The first implementation may emit a governed observation/export package rather than calling a network service. The KB is currently Git/CLI-backed and does not require a new server/API merely for product symmetry.

## Authority and product boundaries

### Engineering Platform

EP executes Engineering Actions, enforces the current per-Action engineering contract, records DoR/DoD/Human Gate proof and produces durable execution/quality evidence. EP is an evidence producer, never KB certification authority and never autonomous project-policy author.

### Forge

Forge plans work, composes/uses project engineering contracts, runs/coordinates the Quality and Knowledge observers, performs higher-order analysis, consumes Certified Knowledge read-only when that integration exists, and proposes future work. Forge learns; it does not self-certify.

### Workspace

Workspace is the human governance UX. It presents live/historical Action contracts, quality-learning proposals, knowledge-learning proposals/status, evidence and approval decisions. Workspace may initiate governed actions; it does not become execution or knowledge authority.

### Project repository

The project repository owns accepted project-specific executable engineering rules: DoR/DoD profiles, guards, tests, Goldens, validation policy and other project contracts. This keeps project quality controls enforceable without hidden Forge memory.

### AI Platform Engineering Knowledge Base

The KB independently owns reusable knowledge lifecycle, source registration, observation/candidate lineage, generalization, certification and publication. Certified Knowledge is the reusable knowledge authority. The KB is not part of EP runtime authority.

### Forge Platform

Forge Platform owns distribution/composition boundaries, not learning semantics. The prior Forge Platform learning-loop analysis is superseded as the canonical product architecture by this Forge document. Forge Platform may later package a qualified KB artifact only if the KB defines a supported productization contract.

## Closed dual learning cycle

The target closed loop is:

```text
Certified Knowledge ----------------------+
       |                                   |
       v                                   |
Forge planning                             |
       |                                   |
       v                                   |
Effective DoR -> Engineering Action -> Effective DoD
                         |
                         +-----------------------+
                         |                       |
                         v                       v
                  Quality Observer        Knowledge Observer
                         |                       |
                         v                       v
                  project hardening       KB observation/candidate
                         |                       |
                         v                       v
                  future project rules    governed certification
                         |                       |
                         +-----------+-----------+
                                     |
                                     v
                              future planning
```

The cycle is deliberately asymmetric: project hardening can become enforceable after project governance; reusable knowledge requires the independent KB lifecycle and certification.

## Background operation

After every Engineering Action:

- the **Quality Observer** runs and records `ActionQualityOutcome`/learning signals;
- the **Knowledge Observer** evaluates whether the Action contains extraction-worthy evidence and creates only proposals/export evidence;
- neither observer blocks normal completion unless a separately declared Action contract explicitly requires a learning artifact;
- neither observer silently mutates project policy or Certified Knowledge.

Heavier analysis is event- or threshold-driven rather than mandatory after every Action:

- Quality Learning Review over N Actions, milestone, release, repeated defect, human rejection or security finding;
- Knowledge consolidation/extraction review over new observations, source changes, releases, architecture decisions, drift/gap signals or explicit operator request.

## Workspace experience

Workspace should expose two related but distinct review surfaces.

### Quality Review

Shows recurring defect classes, DoR/DoD escapes, existing requirement/enforcement gaps, proposed controls, regression proof and `Accept / Modify / Reject` governance.

### Knowledge Review

Shows proposed observations/candidates, source lineage, reusable implication, duplicate/relationship suggestions, uncertainty, KB lifecycle status and governed review actions.

A user may navigate from one Action to both learning outputs without confusing their authority.

## Feedback from Certified Knowledge

When the KB later exposes a qualified read-only consumption contract, Forge may use Certified Knowledge to:

- inform architecture and Mission planning;
- suggest applicable engineering patterns/constraints;
- explain planning rationale with knowledge lineage;
- identify likely DoR/DoD profile needs;
- detect conflicts between current project practice and Certified Knowledge.

Certified Knowledge remains advisory/planning input unless a project explicitly adopts it into its governed project contract. KB availability must not become an implicit EP execution dependency.

## Required invariants

- `EP_ENFORCES_FORGE_LEARNS_WORKSPACE_GOVERNS = TRUE`
- `PROJECT_POLICY_IS_NOT_CERTIFIED_KNOWLEDGE = TRUE`
- `CERTIFIED_KNOWLEDGE_IS_NOT_AUTOMATIC_PROJECT_POLICY = TRUE`
- `OBSERVATION_IS_EVIDENCE_NOT_KNOWLEDGE = TRUE`
- `NO_SELF_CERTIFICATION = TRUE`
- `KNOWLEDGE_SOURCE_READ_ONLY = TRUE`
- `LEARNING_NOT_EXECUTION_DEPENDENCY = TRUE`
- `TRACEABILITY_TO_ACTION_AND_SOURCE = REQUIRED`
- `HUMAN_GOVERNANCE_FOR_POLICY_EVOLUTION = REQUIRED`
- `GOVERNED_KB_CERTIFICATION = REQUIRED`

## Canonical ownership of documents

Forge is the canonical product-architecture home for the dual learning system because Forge owns planning and learning orchestration.

The KB remains canonical for the knowledge lifecycle itself. This document references that lifecycle; it does not duplicate or override KB governance.

Forge Platform may retain a short compatibility/deprecation pointer but must not maintain a competing canonical learning-loop architecture.

## Implementation boundary

This architecture is staged. It does not require the KB to become a daemon, does not require EP to depend on the KB, and does not require Workspace to exist before structured evidence can be captured.

The product roadmap in `docs/roadmap/0.1.md` defines the planned implementation increments.