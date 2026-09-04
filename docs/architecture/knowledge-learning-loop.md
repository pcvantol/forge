# Governed Engineering Knowledge Learning Loop

## Status

Canonical Forge product-integration architecture for reusable engineering knowledge learning. This document migrates the product-level learning-loop responsibility previously documented in Forge Platform. The AI Platform Engineering Knowledge Base (KB) remains canonical for its own knowledge lifecycle, extraction, ingestion, generalization, certification and publication rules.

This is the reusable-knowledge half of the [Dual Engineering Learning System](dual-engineering-learning-system.md).

## Authority decision

`pcvantol/ai-platform-engineering-knowledge-base` is the independent authority for reusable AI Platform Engineering knowledge lifecycle, certification and publication. It is not Forge runtime state, Workspace state, an Engineering Platform component, or an execution dependency.

Forge orchestrates learning and later consumes Certified Knowledge read-only. Workspace presents governed review/control UX. EP and Project Agents produce engineering evidence. None may certify reusable knowledge.

## Canonical lifecycle

The KB lifecycle remains:

```text
Engineering Source / Repository
  -> Engineering Observation (evidence)
  -> Knowledge Candidate (proposal)
  -> Knowledge Concept (reviewed interpretation)
  -> Generalized Knowledge
  -> governed certification
  -> Certified Knowledge
  -> Publication / read-only consumption
```

Key invariants:

- observations are evidence, not canonical knowledge;
- candidate confidence is not certification;
- AI outputs are proposals;
- certification remains governed;
- source repositories are read-only to knowledge operations;
- full source/version/evidence lineage is preserved;
- conflicting/negative evidence is retained rather than hidden;
- no system self-certifies knowledge merely because it produced successful evidence about itself.

## Current KB capability boundary

At the time this architecture was migrated, the KB is a Git-backed repository-local CLI capability rather than a long-running server/API. Its implemented CLI supports source onboarding, extraction to Engineering Observations, classification to Candidates, review to Concepts, generalization, certification readiness/records, query, generation, evolution, validation, improvement, status and statistics.

The implemented extractor is narrower than the conceptual lifecycle: it primarily observes selected Markdown evidence from registered Git sources. PRs, EP receipts, Prompt History, raw telemetry, incidents and TDE evidence require explicit evidence/export and extraction-profile work.

Forge must not invent a KB network service merely for product symmetry. Initial integration may remain explicit CLI/Git-backed and read-only where qualified.

## Forge Knowledge Observer target

After each eligible Engineering Action, a lightweight Knowledge Observer may inspect the bounded learning-evidence envelope and determine whether extraction-worthy engineering evidence exists.

It may propose:

- Engineering Observations;
- reusable implications;
- links to existing observations/candidates;
- candidate/classification suggestions;
- relationship/duplicate suggestions;
- confidence and uncertainty;
- source/version/evidence lineage.

It may not certify, promote, publish as canonical, mutate the source repository, invent evidence, or bypass KB governance.

The observer output is an export/proposal contract, not KB authority.

## Evidence feedback loop

```text
Certified Knowledge
  -> Forge planning (read-only, traceable)
  -> Engineering Action
  -> EP/Agent engineering evidence
  -> Knowledge Observer
  -> approved evidence/export boundary
  -> KB Engineering Observation
  -> Candidate -> Concept -> Generalized
  -> governed certification
  -> Certified Knowledge
```

TDE qualification evidence, security findings, failures, rollbacks, blocked work, invalid assumptions and human review findings may all be legitimate evidence when an approved source/extraction policy preserves provenance and excludes secrets/private data.

Negative evidence does not automatically invalidate Certified Knowledge. It becomes drift/impact evidence for governed evolution.

## Cross-project reuse

Independent observations across projects preserve source identity. Multiple sources may strengthen a reusable concept without collapsing their evidence. Product-specific details are generalized only when engineering meaning and lineage remain intact.

Quality Learning output may become Knowledge Learning input: a project-specific hardening rule can be observed as evidence for a reusable implication, but it does not bypass Candidate/Concept/Generalized/Certification stages.

## Integration contracts required

The target system requires explicit contracts rather than direct internal coupling:

- **EP -> learning evidence:** bounded Action/evidence export with inclusion/exclusion/redaction policy;
- **Forge -> KB:** governed observation/export profile for durable decisions, Action outcomes and learning evidence;
- **KB -> Forge:** read-only Certified Knowledge consumption adapter with lineage/version;
- **Workspace -> learning:** UX may initiate governed actions but does not directly write Certified Knowledge;
- **TDE -> KB:** explicit selected qualification-evidence profile if/when integrated.

KB availability must remain additive. EP admission/execution cannot depend implicitly on KB health.

## Workspace target

Workspace should show:

- proposed observations/candidates;
- source/evidence lineage;
- reusable implication;
- uncertainty/confidence;
- duplicate/relationship suggestions;
- KB lifecycle state;
- governed review/promotion actions appropriate to the operator's authority.

Workspace does not become knowledge authority.

## Automation target

Automation may assist source polling, observation discovery, candidate generation, relationship/classification suggestions, duplicate detection, review preparation, drift/gap detection and impact analysis.

Automation may never certify knowledge, approve lifecycle transitions, invent evidence, mutate source history or modify Certified Knowledge automatically.

The per-Action Knowledge Observer is the first Forge-facing background primitive. Broader continuous extraction remains a later roadmap stage.

## Deployment/productization boundary

The KB is not assumed to be an installable Forge Platform server role. Productization requires an independently qualified KB artifact and supported persistence, backup, update, concurrency and operating model. A service/API should be introduced only if CLI/Git-backed integration proves insufficient.

## Roadmap

Implementation is planned in the canonical [Forge Roadmap](../../knowledge/bootstrap/10_ROADMAP.md), primarily stages L5-L10. The detailed KB-internal lifecycle remains owned by the KB repository and is not duplicated here.

## Canonical rule

**Forge orchestrates learning. The KB certifies reusable knowledge. Workspace governs human decisions. EP executes and produces evidence.**
