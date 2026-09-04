# Forge / Workspace / EP V1 Cross-Product Dependency View

> **THIS DOCUMENT IS A DERIVED DEPENDENCY VIEW. IT DOES NOT REPLACE PRODUCT
> ROADMAP AUTHORITY.** Forge owns this index only as an interpretation of
> evidence. Each product owns allocation, implementation, qualification and
> changes to its own roadmap nodes.

## Method and node types

`CAPABILITY_MILESTONE` is a consumer-visible outcome. `IMPLEMENTATION_INCREMENT`
has exactly one owner. `QUALIFICATION_GATE` makes a producer capability
available to consumers. `EXTERNAL_DEPENDENCY` is an edge only, never an
allocation of another product's work. A consumer may begin fixture-based work
after a contract is frozen, but may not complete an integration claim before
the stated producer qualification gate passes.

This view is derived from Forge [10_ROADMAP](../../knowledge/bootstrap/10_ROADMAP.md),
Workspace [ROADMAP](https://github.com/pcvantol/workspace/blob/codex/workspace-roadmap-authority/ROADMAP.md),
and EP [Engineering Platform Roadmap](https://github.com/pcvantol/engineering-platform/blob/codex/ep-v1-dependency-closure-main/docs/development/ENGINEERING_PLATFORM_ROADMAP.md).
The EP link names the proposed EP-owned documentation increment; until it is
merged, its disposition remains planned rather than available.

## Canonical node index

| Node ID | Node type | Owner repo | Canonical roadmap reference | Depends on | Provides / consumed by | Qualification gate | V1 disposition / readiness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `EP::LOCAL_CONSUMER_API_V1` | IMPLEMENTATION_INCREMENT | Engineering Platform | Phase 1 / Increments 1–3 | EP local runtime foundation | Versioned, scoped consumer envelope and registration base; consumed by project attachment | Phase 1 closure: schema 40, registration and credential lifecycle qualified | RESOLVED / available |
| `EP::STANDALONE_EP_VERIFIED` | QUALIFICATION_GATE | Engineering Platform | Phase 3, B8C → B8D → B9 | Installed Server/Agent, attachment, canonical ingress | Installed EP execution authority | Retained B8C/B8D/B9 qualification bundle | RESOLVED node / not yet satisfied |
| `EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1` | IMPLEMENTATION_INCREMENT | Engineering Platform | Phase 4 / Increment 1 | `EP::LOCAL_CONSUMER_API_V1`, `EP::STANDALONE_EP_VERIFIED` | Idempotent project registration refresh, repository/Agent attachment and admission-ready project; consumed by Workspace onboarding | Clean-install, fresh-registration, idempotency, project-routing and first-governed-execution evidence | RESOLVED allocation / BLOCKED_BY `EP::STANDALONE_EP_VERIFIED` |
| `EP::ENGINEERING_CONTRACT_FOUNDATION_V1` | IMPLEMENTATION_INCREMENT | Engineering Platform | Phase 4 / Increment 2 | `EP::LOCAL_CONSUMER_API_V1`, `EP::STANDALONE_EP_VERIFIED` | Capability classification, Effective DoR/DoD, proofs, Human Gates, Action quality outcome, immutable Action snapshots and live/historical projection; consumed by Forge L0 | `EP::ENGINEERING_CONTRACT_FOUNDATION_V1_QUALIFIED`: installed-artifact contract, negative/admission, recovery and evidence-projection qualification | EP_ROADMAP_GAP resolved by planned allocation / BLOCKED_BY `EP::STANDALONE_EP_VERIFIED` |
| `Forge::L0_ENGINEERING_CONTRACT_FOUNDATION` | CAPABILITY_MILESTONE | Forge (consumer interpretation) | Forge L0 | `EP::ENGINEERING_CONTRACT_FOUNDATION_V1_QUALIFIED` | Common capability milestone; unlocks L1 | Producer qualification above | RESOLVED / blocked externally |
| `Forge::L1_BOOTSTRAP_EVIDENCE_CONTRACT` | IMPLEMENTATION_INCREMENT | Forge | Forge L1 | Forge L0 | Project-owned bootstrap/evidence composition; consumed by L1-R and Workspace quality surface | Forge contract and EP integration qualification | BLOCKED_BY `Forge::L0_ENGINEERING_CONTRACT_FOUNDATION` |
| `Forge::L1R_MANAGED_REPOSITORY_GOVERNANCE` | IMPLEMENTATION_INCREMENT | Forge | Forge L1-R | Forge L1 | Versioned desired-state governance and read-back evidence | Managed repository qualification | BLOCKED_BY Forge L1 |
| `Workspace::ONBOARDING_CONTROL_PLANE_V1` | IMPLEMENTATION_INCREMENT | Workspace | Workspace “Proposed repository onboarding and control plane” | `EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1`; Forge L1 for managed bootstrap flows | Workspace project identity, permitted intent and onboarding UX | Workspace UX/accessibility/no-secondary-authority proof plus EP producer qualification | BLOCKED_BY `EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1` |
| `Workspace::QUALITY_GOVERNANCE_SURFACE` | IMPLEMENTATION_INCREMENT | Workspace | Workspace dependency register | Forge L0/L1 evidence and onboarding contract | Governed presentation and intent only | Attribution, freshness/degraded-state, accessibility and no-secondary-authority proof | CONTRACT_FIRST_PARALLEL_AFTER Forge L0 contract freeze |
| `Forge::L2_L3_QUALITY_LEARNING` | IMPLEMENTATION_INCREMENT | Forge | Forge L2–L3 | Forge runtime/planning maturity | Quality observation and proposals | Forge review/hardening qualification | READY_NOW only after separately approved Forge work |
| `Workspace::KNOWLEDGE_GOVERNANCE_SURFACE` | IMPLEMENTATION_INCREMENT | Workspace | Workspace dependency register | KB export/consumption contracts | Governed knowledge presentation and permitted intent | Lineage/redaction, unavailable-KB degradation, accessibility and no-direct-certification proof | POST_V1 / nonblocking |
| `Forge::L5_L8_KNOWLEDGE_CONSUMPTION` | CAPABILITY_MILESTONE | Forge + KB boundary | Forge L5–L8 | KB-owned explicit export and read-only consumption contracts | Additive, read-only knowledge use | KB lifecycle/provenance qualification | POST_V1 / nonblocking |
| `TDE::OBSERVE_ONLY_PUBLIC_RUNTIME` | EXTERNAL_DEPENDENCY | Technical Debt Engine | TDE Product Roadmap — operational maintenance | Applicable public capability | Nonblocking evidence observation only | TDE public-runtime and consumer evidence | RESOLVED / nonblocking; no Forge/Workspace V1 build edge |
| `ForgePlatform::QUALIFIED_COMPOSITION` | EXTERNAL_DEPENDENCY | Forge Platform | MVP W0–W4 | Published product artifacts and product-owned contracts | Installation/release composition | Forge Platform clean-install and composition qualification | POST_V1 for this graph; never an EP/Forge/Workspace implementation allocation |
| `KB::GOVERNED_LIFECYCLE` | EXTERNAL_DEPENDENCY | Knowledge Base | KB future evolution recommendation | KB governance | Certified knowledge and observation lifecycle | KB-owned lifecycle/provenance evidence | POST_V1 / nonblocking; no V1 runtime dependency |

## Directed edge register

| From producer | To consumer | Capability contract | Qualification required before consumer completion | Classification |
| --- | --- | --- | --- | --- |
| `EP::LOCAL_CONSUMER_API_V1` | `EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1` | Versioned project scope, consumer identity and registration base | Phase 1 closure | RESOLVED |
| `EP::STANDALONE_EP_VERIFIED` | `EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1` | Installed Server/Agent execution authority | B8C/B8D/B9 retained bundle | RESOLVED |
| `EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1` | `Workspace::ONBOARDING_CONTROL_PLANE_V1` | `PROJECT_ATTACHMENT_AND_ADMISSION_V1` | Clean-install/fresh-registration/idempotency/project-routing/first-run evidence | RESOLVED |
| `EP::STANDALONE_EP_VERIFIED` | `EP::ENGINEERING_CONTRACT_FOUNDATION_V1` | Installed EP foundation | B8C/B8D/B9 retained bundle | RESOLVED |
| `EP::ENGINEERING_CONTRACT_FOUNDATION_V1` | `Forge::L0_ENGINEERING_CONTRACT_FOUNDATION` | `ENGINEERING_CONTRACT_FOUNDATION_V1` | Installed artifact, negative admission/recovery and evidence-projection qualification | RESOLVED |
| `Forge::L0_ENGINEERING_CONTRACT_FOUNDATION` | `Forge::L1_BOOTSTRAP_EVIDENCE_CONTRACT` | Effective contract/evidence semantics | EP producer gate plus Forge composition evidence | RESOLVED |
| `Forge::L1_BOOTSTRAP_EVIDENCE_CONTRACT` | `Forge::L1R_MANAGED_REPOSITORY_GOVERNANCE` | Project-owned contract and baseline provenance | Forge L1 qualification | RESOLVED |
| `Forge::L1_BOOTSTRAP_EVIDENCE_CONTRACT` | `Workspace::ONBOARDING_CONTROL_PLANE_V1` | Managed bootstrap flow only | Forge L1 qualification; it is not required for identity-only onboarding | RESOLVED |
| `Forge::L0_ENGINEERING_CONTRACT_FOUNDATION` | `Workspace::QUALITY_GOVERNANCE_SURFACE` | Effective DoR/DoD/Gate projection | Producer evidence freshness and attribution | RESOLVED |
| `Forge::L1_BOOTSTRAP_EVIDENCE_CONTRACT` | `Workspace::QUALITY_GOVERNANCE_SURFACE` | Governance state/drift projection | Forge L1 qualification | RESOLVED |
| `Forge::L2_L3_QUALITY_LEARNING` | `Workspace::QUALITY_GOVERNANCE_SURFACE` | Governed Quality Learning proposals | Forge observer/review qualification and Workspace attribution/freshness proof | RESOLVED |
| `KB::GOVERNED_LIFECYCLE` | `Forge::L5_L8_KNOWLEDGE_CONSUMPTION` | Explicit export and read-only consumption | KB provenance/certification | POST_V1 |
| `KB::GOVERNED_LIFECYCLE` | `Workspace::KNOWLEDGE_GOVERNANCE_SURFACE` | Evidence-linked lifecycle projection | KB lineage/redaction/degraded-state proof | POST_V1 |
| `TDE::OBSERVE_ONLY_PUBLIC_RUNTIME` | Forge/Workspace/EP consumers | Applicable public observe capability | Consumer-owned, nonblocking observation evidence | POST_V1 |
| Forge/Workspace/EP published artifacts | `ForgePlatform::QUALIFIED_COMPOSITION` | Versioned artifact/protocol compatibility | Forge Platform composition qualification | POST_V1 |

No edge is a duplicate work allocation. No V1 build edge points to a historical
branch term. The graph is acyclic: runtime interaction between Forge, Workspace
and EP is not a build dependency; the producer contract and qualification gate
break the integration sequence.

## Safe parallelism

| Increment / capability | Current classification | Safe condition |
| --- | --- | --- |
| `EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1` | BLOCKED_BY `EP::STANDALONE_EP_VERIFIED` | EP-only implementation and qualification after the installed boundary exists |
| `EP::ENGINEERING_CONTRACT_FOUNDATION_V1` | CONTRACT_FIRST_PARALLEL_AFTER `EP::LOCAL_CONSUMER_API_V1` | Its contract design may proceed in EP; consumer integration waits for its qualification |
| Forge L1 | CONTRACT_FIRST_PARALLEL_AFTER L0 contract freeze | Forge may compose fixtures; no integration-complete claim before the EP gate |
| Workspace onboarding | CONTRACT_FIRST_PARALLEL_AFTER registration/attachment contract freeze | UX fixtures may proceed; real attachment/admission waits for EP qualification |
| Workspace quality surface | CONTRACT_FIRST_PARALLEL_AFTER Forge projection contract freeze | UI fixtures may proceed; governed live view waits for freshness/attribution proof |
| Knowledge surfaces | POST_V1 | Additive only; never blocks standalone execution |

## Adversarial review and counts

An independent reader can determine each V1 prerequisite owner, canonical
reference, contract and evidence gate from the node/edge tables. The former
`P-TRANSPORT` label was found only as unmerged EP branch terminology and has no
canonical roadmap meaning; it is not retained as an edge.

| Measure | Count |
| --- | ---: |
| `V1_NODES` | 10 |
| `V1_EDGES` | 11 |
| `UNRESOLVED_NODES` | 0 |
| `DANGLING_EDGES` | 0 |
| `DUPLICATE_ALLOCATIONS` | 0 |
| `UNDEFINED_CONTRACT_EDGES` | 0 |
| `UNDEFINED_QUALIFICATION_EDGES` | 0 |
| `STALE_REFERENCES` | 0 |
| `V1_BUILD_DEPENDENCY_CYCLES` | 0 |

`P_TRANSPORT_CANONICAL_MAPPING = none; historical unmerged EP branch label`

`P_TRANSPORT_REFERENCE_RESULT = PASS`

`FORGE_L0_CANONICAL_EP_PRODUCER = EP::ENGINEERING_CONTRACT_FOUNDATION_V1`

`FORGE_L0_EP_IMPLEMENTATION_TRACE = PASS`

`WORKSPACE_ONBOARDING_EP_REGISTRATION_PRODUCER = EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1`

`WORKSPACE_ONBOARDING_EP_REGISTRATION_TRACE = PASS`

`CROSS_PRODUCT_V1_DEPENDENCY_GRAPH = CLOSED` is valid only when the referenced
EP producer-map change is merged alongside the Forge and Workspace changes.
