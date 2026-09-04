# Forge + Workspace V1 Gap Register

Status is `OPEN` unless stated otherwise. An item becomes closed only by a canonical decision, implementation increment, and its stated qualification evidence.

| ID | Affected capability | Owner | Status | V1 disposition / roadmap disposition |
| --- | --- | --- | --- | --- |
| FWV1-G001 | installation, Workspace/project identity | Workspace (product), Forge/EP integration | OPEN | V1_BLOCKER; I01 |
| FWV1-G002 | baseline, Project Contract, Effective Action Contract | Forge | OPEN | V1_BLOCKER; I02 |
| FWV1-G003 | Genesis, adoption, repository provisioning/attachment | EP protocol; Workspace UX | OPEN | V1_BLOCKER; I03 |
| FWV1-G004 | managed repository governance | Forge policy; EP/provider execution | OPEN | V1_BLOCKER; I04 |
| FWV1-G005 | Action graph, multi-repository execution | Forge graph; EP admission | OPEN | V1_BLOCKER; I05 |
| FWV1-G006 | DoR, DoD, Human Gate | Forge composition; Workspace/EP consumers | OPEN | V1_BLOCKER; I06 |
| FWV1-G007 | history, attention, recovery, delivery | Workspace projection; Forge/EP sources | OPEN | V1_REQUIRED; I07 |
| FWV1-G008 | contract/project upgrade | Forge with owner-specific migration consumers | OPEN | V1_REQUIRED; I08 |
| FWV1-G009 | archive, restore, deletion, retention | Workspace/Forge/EP by owned record | OPEN | V1_REQUIRED; I08 |
| FWV1-G010 | installation self-containment | all products; Forge coordination | OPEN | V1_BLOCKER; I01/I09 |
| FWV1-G011 | authentication, authorization, secrets, audit | each product; cross-product security decision | OPEN | V1_BLOCKER; I01/I09 |
| FWV1-G012 | quality and knowledge learning | Forge | OPEN | V1_FOUNDATION_ONLY; POST_V1 |
| FWV1-G013 | Workspace UX/accessibility/responsiveness | Workspace | OPEN | V1_REQUIRED; I10 |

| ID | Title and evidence | Classification / impact | Required decision; owner; dependencies | V1 / roadmap disposition |
| --- | --- | --- | --- | --- |
| FWV1-G001 | Installation, named operator, Workspace project identity and cross-product bootstrap are absent. Workspace explicitly has foundation only. | V1_BLOCKER | Define installed topology, local identity, Workspace Server state and setup handoff. Workspace owns its product; Forge owns Forge integration. Depends on G010/G011. | V1_REQUIRED; I01. |
| FWV1-G002 | No Product Baseline → Project Contract → Effective Action Contract composition/snapshot model. | V1_BLOCKER | Forge canonical contract, hash, storage, compatibility and migration rules. Depends on G005/G006. | V1_REQUIRED; I02. |
| FWV1-G003 | Genesis/new/adopted repository flows are only proposed; provisioning and registration authority unresolved. | V1_BLOCKER | EP-owned accepted request/attachment protocol and Workspace intent model; Forge interpretation boundary. | V1_REQUIRED; I03. |
| FWV1-G004 | Generic managed-repository governance desired state, capability detection, drift/reconcile and unsupported-host outcome undefined. | V1_BLOCKER | Forge policy profile; EP/provider executor/read-back proof; human exception policy. | V1_REQUIRED; I04. |
| FWV1-G005 | Action graph, multi-repo scope, leases, scheduling handoff and coordinated delivery are incomplete across products. | V1_BLOCKER | Freeze Forge Action scope/dependency contract and EP admission/lease response. | V1_REQUIRED; I05. |
| FWV1-G006 | Effective DoR/DoD, proof identity, gate approval/rejection and repair semantics are not composed. | V1_BLOCKER | Forge composition and immutable snapshot; Workspace review record; EP evidence mapping. | V1_REQUIRED; I06. |
| FWV1-G007 | Unified run/history/attention/recovery projection and release terminal semantics are undefined. | V1_REQUIRED | Cross-product projection cursor, freshness, retry/attention taxonomy and retention policy. | I07. |
| FWV1-G008 | Project/baseline upgrade and interrupted migration semantics are undefined. | V1_REQUIRED | Version compatibility, preflight, backup/rollback/fail-closed policy. | I08. |
| FWV1-G009 | Archive/restore/delete with repositories, evidence and active Actions lacks retention and authority rules. | V1_REQUIRED | Owner-specific deletion state machine and legal/operational retention policy. | I08. |
| FWV1-G010 | Installed product self-containment is not qualified; local source/repo documents are current evidence only. | V1_BLOCKER | Package baselines/schemas/fixtures and prove `SOURCE_REPOSITORY_RUNTIME_DEPENDENCIES = 0`. | I01/I09. |
| FWV1-G011 | V1 identity, authorization, secure storage, provider/Agent identity, audit and revocation are not defined. | V1_BLOCKER | Single-installation named-operator trust model; secret references and redaction. | I01/I09. |
| FWV1-G012 | Dual learning has boundaries but lacks observer persistence, cost/privacy, dedupe, unavailable-KB and governed feedback. | V1_FOUNDATION_ONLY | Keep non-blocking for initial V1 execution; define only if shipped. | POST-V1 unless V1 scope changes. |
| FWV1-G013 | Workspace UX interaction contracts have no implementation, accessibility/responsive standard, or error-state qualification. | V1_REQUIRED | Workspace-owned UI contract and end-to-end accessibility qualification. | I10 after I01/I07. |

## Staleness and contradiction audit

| Finding | Classification | Disposition |
| --- | --- | --- |
| Forge bootstrap describes Workspace as product boundary; independent Workspace defines a stateful server/client peer and project-control plane. | UNRESOLVED_CONFLICT | G001 must establish the cross-product semantic mapping; neither repository may unilaterally redefine the other. |
| Forge Runtime DB/models/tests substantially precede the originally deferred Studio/runtime narrative. | IMPLEMENTATION_AHEAD_OF_DESIGN | Preserve tested local behavior, but do not call it Workspace V1. Map it in I05–I07. |
| Workspace onboarding is explicitly proposed and EP attachment is B5 foundation with unresolved registration/auth. | ARCHITECTURE_WITHOUT_ROADMAP | I03 supplies dependency-aware implementation order. |
| EP producer/run evidence is more concrete than Forge effective contract/gate semantics. | PRODUCT_CONTRACT_WITHOUT_TEST_STRATEGY | I02/I06 must define goldens and cross-product contract tests. |
