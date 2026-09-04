# Forge + Workspace V1 Capability Completeness Matrix

Legend: `DEFINED`, `PARTIAL`, `MISSING`, `N/A`, `CONFLICT`, `IMPLEMENTED_NOT_CANONICAL`, `DOCUMENTED_NOT_IMPLEMENTED`. Evidence notes use the classifications defined in the product model. Cells do not imply authorization to build.

| Capability | Semantics/scope/authority | State, persistence, contracts | UX / Forge / EP / repository host | Trust, failure, history, upgrade, qualification, gate, roadmap, maturity |
| --- | --- | --- | --- | --- |
| Install and initial setup | PARTIAL / V1_REQUIRED / CONFLICT | MISSING | Workspace/Forge/EP split PARTIAL | secrets, upgrade and clean-install qualification MISSING; `FWV1-G001`; DOCUMENTED_NOT_IMPLEMENTED |
| Project identity and Workspace | DEFINED / V1_REQUIRED / Workspace | PARTIAL | Workspace UX DOCUMENTED_NOT_IMPLEMENTED | auth/migration/qualification MISSING; `FWV1-G001`; Forge models TESTED, Workspace not implemented |
| New repository / Genesis | DEFINED target / V1_REQUIRED / Workspace intent + Forge bootstrap + EP provision | MISSING | UI/EP/GitHub contract PARTIAL | auth, idempotency, recovery, qualification MISSING; `G003`; DOCUMENTED_NOT_IMPLEMENTED |
| Existing repository adoption | DEFINED target / V1_REQUIRED / Forge interpretation + EP attachment | MISSING | Workspace proposal/EP declaration PARTIAL | `COMPLIANT`/drift/incompatible/reconcile semantics are DOCUMENTED; protocol implementation MISSING; `G003` |
| Project Contract / baseline | DEFINED target / V1_REQUIRED / released Forge/EP baseline + project-owned contract | MISSING | all consumers MISSING | immutable snapshot/migration/gate semantics DOCUMENTED; L0/L1 qualification MISSING; `G002` architecture resolved |
| Repository governance | DEFINED target / V1_REQUIRED / Forge desired, EP/provider actual | MISSING | Workspace projection PARTIAL | versioned baseline/read-back/adoption semantics DOCUMENTED; L1-R implementation/qualification MISSING; `G004` architecture resolved |
| Mission / planning / Action | DEFINED / V1_REQUIRED / Forge | PARTIAL | Forge IMPLEMENTED_BEHAVIOR; Workspace view MISSING | Action snapshot/DoR coverage PARTIAL; `G005`; TESTED local foundation |
| Dependency / priority scheduling | PARTIAL / V1_REQUIRED / Forge graph, EP admission | PARTIAL | EP scheduling documented; Workspace MISSING | leases/parallel rules PARTIAL; `G005`; IMPLEMENTED_NOT_CANONICAL |
| Producer submission and dispatch | DEFINED / V1_REQUIRED / Forge→EP | DEFINED | EP execution, Workspace projection PARTIAL | lineage, replay, audit TESTED in EP evidence; `G007`; PARTIAL cross-product |
| Run/retry/delivery/PR merge | DEFINED / V1_REQUIRED / EP | DEFINED in EP | Workspace surface MISSING | bounded repairs/history PARTIAL; release semantics `G007`; EP IMPLEMENTED, Forge integration PARTIAL |
| Effective DoR/DoD/Human Gate | DEFINED target / V1_REQUIRED / Forge/EP composition + human | MISSING | Workspace review MISSING | proof identity and attributable gate semantics DOCUMENTED; L0/L4 implementation MISSING; `G006` architecture resolved |
| Evidence/history/attention | PARTIAL / V1_REQUIRED / EP source, Forge interpretation, Workspace projection | PARTIAL | no unified UX | retention/freshness/notification MISSING; `G007/G009` |
| Provider/Agent health | PARTIAL / V1_REQUIRED / EP | PARTIAL | Workspace view MISSING | credential lifecycle/redaction MISSING; `G011` |
| Quality learning | DEFINED target / FOUNDATION_ONLY / Forge | MISSING | Workspace view MISSING | observer/review/hardening contract DOCUMENTED; L2–L4 MISSING; `G012` |
| Knowledge learning | DEFINED target / FOUNDATION_ONLY / Forge + KB authority | MISSING | Workspace view MISSING | export/redaction/lineage and no-certification DOCUMENTED; L5–L10 MISSING; `G012` |
| Settings/security/audit | PARTIAL / V1_REQUIRED / owners split | PARTIAL | Workspace UX MISSING | V1 named-operator model `G011`; DOCUMENTED_NOT_IMPLEMENTED |
| Multi-repository | PARTIAL / V1_REQUIRED (one lane/repo) / Forge+EP | PARTIAL | topology view PARTIAL | coordinated delivery and leases `G005`; cross-repo atomic POST_V1 |
| Upgrade/archive/delete | PARTIAL / V1_REQUIRED / owner-specific | PARTIAL runtime DB only | Workspace UX MISSING | project retention/migration MISSING; `G008/G009` |
| Localization/responsiveness | MISSING / V1_REQUIRED for Workspace | MISSING | Workspace only | accessibility and qualification MISSING; `G013` |
| Enterprise/multi-user/cloud | NOT V1 | N/A | N/A | explicit POST_V1 boundary |
