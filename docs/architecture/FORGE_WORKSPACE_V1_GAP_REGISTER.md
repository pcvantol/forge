# Forge + Workspace V1 Gap Register

Status is `OPEN` unless stated otherwise. An item becomes closed only by a canonical decision, implementation increment, and its stated qualification evidence.

| ID | Affected capability | Owner | Status | V1 disposition / roadmap disposition |
| --- | --- | --- | --- | --- |
| FWV1-G001 | installation, Workspace/project identity | Workspace (product), Forge/EP integration | OPEN | V1_BLOCKER; L0/L1 and cross-product installation work |
| FWV1-G002 | baseline, Project Contract, Effective Action Contract | Forge + EP release capability | ARCHITECTURE_RESOLVED | V1_REQUIRED implementation/qualification; L0/L1 |
| FWV1-G003 | Genesis, adoption, repository provisioning/attachment | EP protocol; Workspace UX | OPEN | V1_BLOCKER; L1/L1-R |
| FWV1-G004 | managed repository governance | Forge policy; EP/provider execution | ARCHITECTURE_RESOLVED | V1_REQUIRED implementation/qualification; L1-R |
| FWV1-G005 | Action graph, multi-repository execution | Forge graph; EP admission | OPEN | V1_BLOCKER; post-L1 cross-product dependency |
| FWV1-G006 | DoR, DoD, Human Gate | Forge/EP composition; Workspace consumers | ARCHITECTURE_RESOLVED | V1_REQUIRED implementation/qualification; L0/L4 |
| FWV1-G007 | history, attention, recovery, delivery | Workspace projection; Forge/EP sources | OPEN | V1_REQUIRED; post-L1 Workspace dependency |
| FWV1-G008 | contract/project upgrade | Forge with owner-specific migration consumers | OPEN | V1_REQUIRED; post-L1 cross-product dependency |
| FWV1-G009 | archive, restore, deletion, retention | Workspace/Forge/EP by owned record | OPEN | V1_REQUIRED; post-L1 cross-product dependency |
| FWV1-G010 | installation self-containment | all products; Forge coordination | OPEN | V1_BLOCKER; L0/L1/L1-R/L10 |
| FWV1-G011 | authentication, authorization, secrets, audit | each product; cross-product security decision | OPEN | V1_BLOCKER; L1/L10 plus cross-product security dependency |
| FWV1-G012 | quality and knowledge learning | Forge + KB authority | ARCHITECTURE_RESOLVED | V1_FOUNDATION_ONLY; L2–L10 / POST-V1 execution dependency |
| FWV1-G013 | Workspace UX/accessibility/responsiveness | Workspace | OPEN | V1_REQUIRED; L4/L7 and Workspace implementation work |

| ID | Title and evidence | Classification / impact | Required decision; owner; dependencies | V1 / roadmap disposition |
| --- | --- | --- | --- | --- |
| FWV1-G001 | Installation, named operator, Workspace project identity and cross-product bootstrap are absent. Workspace explicitly has foundation only. | V1_BLOCKER | Define installed topology, local identity, Workspace Server state and setup handoff. Workspace owns its product; Forge owns Forge integration. Depends on G010/G011. | V1_REQUIRED; L0/L1 plus Workspace installation dependency. |
| FWV1-G002 | PR #7 `self-contained-engineering-contract-bootstrap` defines Product Baseline → project-owned contract → immutable Action snapshot. | DESIGN_AHEAD_OF_IMPLEMENTATION | Implement/version/qualify the specified representation and cross-product consumption. Depends on EP L0 and L1. | V1_REQUIRED; L0/L1. |
| FWV1-G003 | PR #7 defines target bootstrap/adoption semantics, but EP accepted-request/registration and Workspace intent protocol are still only proposed. | V1_BLOCKER | Freeze EP-owned accepted request/attachment protocol and Workspace intent model; Forge remains planner/interpreter. | V1_REQUIRED; L1/L1-R plus EP/Workspace predecessor. |
| FWV1-G004 | PR #7 defines versioned Managed GitHub desired state, idempotent provisioning/read-back, adoption/drift outcomes and explicit unsupported capability disposition. | DESIGN_AHEAD_OF_IMPLEMENTATION | Implement/qualify the generic profile; do not copy current pcvantol settings. | V1_REQUIRED; L1-R. |
| FWV1-G005 | Action graph, multi-repo scope, leases, scheduling handoff and coordinated delivery are incomplete across products. | V1_BLOCKER | Freeze Forge Action scope/dependency contract and EP admission/lease response after L0/L1 contract identities stabilize. | V1_REQUIRED; post-L1 cross-product increment. |
| FWV1-G006 | PR #7 defines Effective DoR/DoD composition, stable proof identity, attributable Human Gates and immutable projection. | DESIGN_AHEAD_OF_IMPLEMENTATION | EP L0 implements enforcement; Workspace L4 implements governed presentation; qualify repair flow. | V1_REQUIRED; L0/L4. |
| FWV1-G007 | Unified run/history/attention/recovery projection and release terminal semantics are undefined. | V1_REQUIRED | Cross-product projection cursor, freshness, retry/attention taxonomy and retention policy. | post-L1 Workspace increment. |
| FWV1-G008 | Project/baseline upgrade and interrupted migration semantics are undefined. | V1_REQUIRED | Version compatibility, preflight, backup/rollback/fail-closed policy. | post-L1 cross-product increment. |
| FWV1-G009 | Archive/restore/delete with repositories, evidence and active Actions lacks retention and authority rules. | V1_REQUIRED | Owner-specific deletion state machine and legal/operational retention policy. | post-L1 cross-product increment. |
| FWV1-G010 | PR #7 defines the no-source-authority target but it is not qualified. | V1_BLOCKER | Package baselines/schemas/fixtures and prove `SOURCE_REPOSITORY_RUNTIME_DEPENDENCIES = 0`. | L0/L1/L1-R/L10. |
| FWV1-G011 | V1 identity, authorization, secure storage, provider/Agent identity, audit and revocation are not defined. | V1_BLOCKER | Single-installation named-operator trust model; secret references and redaction. | L1/L10 plus cross-product security increment. |
| FWV1-G012 | PR #7 defines dual-loop evidence, redaction, non-blocking KB behavior, authority and governed feedback. Observer persistence/cost/deduplication are staged implementation concerns. | V1_FOUNDATION_ONLY | Implement only under L2–L10; KB remains additive and independently governed. | POST-V1 unless V1 scope changes. |
| FWV1-G013 | Workspace UX interaction contracts have no implementation, accessibility/responsive standard, or error-state qualification. | V1_REQUIRED | Workspace-owned UI contract and end-to-end accessibility qualification. | L4/L7 plus Workspace implementation work. |

## Staleness and contradiction audit

| Finding | Classification | Disposition |
| --- | --- | --- |
| Forge bootstrap describes Workspace as product boundary; independent Workspace defines a stateful server/client peer and project-control plane. | UNRESOLVED_CONFLICT | G001 must establish the cross-product semantic mapping; neither repository may unilaterally redefine the other. |
| Forge Runtime DB/models/tests substantially precede the originally deferred Studio/runtime narrative. | IMPLEMENTATION_AHEAD_OF_DESIGN | Preserve tested local behavior, but do not call it Workspace V1. Map it after L0/L1 contract stabilization. |
| Workspace onboarding is explicitly proposed and EP attachment is B5 foundation with unresolved registration/auth. | ARCHITECTURE_WITHOUT_ROADMAP | L1/L1-R define target semantics; a separate EP/Workspace protocol predecessor remains required. |
| PR #7 now makes the Forge effective contract/gate target more concrete than its implementation. | DESIGN_AHEAD_OF_IMPLEMENTATION | L0/L1/L4 require Goldens and cross-product contract qualification. |
| Forge Platform PR #14 moves canonical learning-loop architecture to Forge while retaining KB productization/deployment limits. | CONSISTENT | Forge owns learning orchestration; Forge Platform owns only future qualified distribution/composition. Keep KB Git/CLI-backed and additive until its own qualified artifact exists. |
