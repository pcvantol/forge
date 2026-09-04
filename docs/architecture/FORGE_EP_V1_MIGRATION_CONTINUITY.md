# Forge / EP V1 migration continuity cross-check

**AUTHORITY = DERIVED.  EP_NODE_AUTHORITY = ENGINEERING_PLATFORM.** This is a
Forge planning/readiness projection, not an EP roadmap, delivery allocation or
qualification receipt. EP `main` decides canonical nodes and ordering; EP PR
#33 is recorded only as explicitly non-canonical in-flight evidence.

## Evidence baseline

| Evidence | Exact revision / observation | Role |
| --- | --- | --- |
| Forge `main` | `2aabfecdbf3a98e63a174434e712d459504e4cba` | Canonical Forge V1 DAG; PRs #10, #11 and #12 are merged. |
| EP `main` | `fc5111d173a407af50c6a66c962a9bc1c875e3dc` | Canonical EP roadmap and migration-to-V1 dependency authority. |
| EP PR #33 | `215d42f29855052144ec5dc200c0ac66917de354` | Open, mergeable but `BEHIND` candidate; P-TRANSPORT implementation evidence. |
| Workspace `main` | `85f86400b05f82665daa5d0c40fdde514b94e59a` | Consumer dependency check only. |

`BASELINE_VALIDATION = PASS`: Forge `bash scripts/validate.sh` completed 293
tests and offline projection validation. The EP working tree was deliberately
not used for validation because it contains unrelated local work; the audit
uses the pinned `main` and PR refs. `EP_MIGRATION_AUTHORITY_AMBIGUITY = 0`.

Canonical EP sources are `ENGINEERING_PLATFORM_ROADMAP.md` (allocation),
`ENGINEERING_PLATFORM_EXTRACTION_MIGRATION_PLAN.md#migration-to-v1-dependency-authority`
(stable nodes/order), `PHASE_P_MIGRATION_GAPS_REGISTER.md` (Phase-P completion),
and `PHASE_P_TO_STANDALONE_MIGRATION_ROADMAP.md` (implementation meaning).
The zero-loss audit and source-retirement sections are supporting canonical
evidence. Earlier migration reports/old cutover material are historical unless
the current authority expressly retains them.

## PR #33 — P-TRANSPORT, classified separately

| Dimension | Canonical EP `main` | PR #33 at exact head |
| --- | --- | --- |
| Node state | `ACTIVE GAP`; `EP::P_TRANSPORT_V1` remains required before standalone verification. | **IMPLEMENTED** and locally functionally qualified; not merged or canonical. |
| Ingress | Required three canonical transports. | HTTP, installed CLI and Server-owned File Inbox normalize through Submission Service/CENTRAL. |
| File Inbox | Required transport with no lifecycle authority. | `FILE_INBOX_RUNTIME_OWNER = EP_SERVER`; `FILE_INBOX_EXTERNAL_RUNTIME_SUPPORTED = FALSE`; no local DB/StateStore/queue/retry authority. |
| Human intent | Required canonical ingress semantics. | `.json` structured submission; `.md`/`.txt` deterministic `submission-intake-v1` normalisation, explicit metadata and fail-closed quarantine. |
| Functional evidence | No completed main qualification. | Ingress matrix, file durability, negative ingress, storage authority and functional ingress gates report `PASS`; source includes installed-wheel matrix/harness. |
| Console / UI | P-CENTRAL-CONSOLE is accepted baseline. | Platform-route ownership, central component projection/logs, localisation and legacy inbox-control retirement are implemented; five review captures are present. |
| Human/hosted/owner | Not applicable until candidate is reviewed. | Route matrix says `P-TRANSPORT AWAITING_HUMAN_UI_REVIEW`; final GitHub observation has successful CodeQL, projection, smoke, security, Trusted Delivery, validation-profile, UI-localisation and four browser-shard checks; `validate` remains `IN_PROGRESS`, Golden Regression is skipped, and exact-head `Owner Authorization` is `FAILURE`. There are no reviews/decision. |
| Merge | N/A | Open, mergeable, but `BEHIND` EP main. |

`EP_PR33_INSPECTED = TRUE`  
`EP_PR33_CURRENT_CHECKS = HOSTED_QUALIFICATION_PARTIAL; validate=IN_PROGRESS; Owner Authorization=FAILURE; Golden Regression=SKIPPED`  
`EP_PR33_CURRENT_CLASSIFICATION = IMPLEMENTED + FUNCTIONALLY_QUALIFIED_IN_FLIGHT + WAITING_EP_HUMAN_REVIEW + WAITING_EP_HOSTED_QUALIFICATION + WAITING_EP_OWNER_AUTHORIZATION + WAITING_EP_MERGE`

Remaining closure is explicit: reconcile/rebase the candidate onto current EP
main; complete the in-progress exact-head validation and any required skipped
Golden qualification; complete human UI review; resolve the failed exact-head
Owner Authorization; resolve review findings; merge; then
reconcile the Phase-P register on `main`. Consequently it is **not**
`QUALIFIED`, `MERGE_READY`, `MERGED`, or `CANONICALLY_COMPLETE`.

## Current EP migration frontier

```text
completed:                  LOCAL_CONSUMER_API_V1; retained P-CENTRAL-CORE/CONSOLE repairs
implemented_in_flight:      P_TRANSPORT_V1 (PR #33 only)
functionally_qualified:     P_TRANSPORT ingress/durability/negative/storage/human-file matrix (PR #33 only)
awaiting_human_review:      P_TRANSPORT UI review
awaiting_hosted_qualification: P_TRANSPORT exact-head hosted checks
awaiting_owner_authorization: P_TRANSPORT exact-head authorization if required by trusted delivery
awaiting_merge:             P_TRANSPORT PR #33 (also behind main)
next_after_transport:       P_QUEUE_V1 -> P_NEUTRAL_V1; package/install work may proceed only at its named EP prerequisites
blocked:                    re-audit, P-D Goldens, minimum Phase-S, B8E, B9 and Phase-4 producers
post_v1:                    source retirement; broader Phase-S real-project dogfooding
```

`CURRENT_EP_MIGRATION_FRONTIER = RESOLVED`.

## EP V1 prerequisite register

All rows are EP-owned. `V1_BLOCKING` here means blocking one of the two V1
consumer producer capabilities, never Forge allocation.

| EP node / canonical name | Current status | Predecessors → successor | Qualification | V1 classification |
| --- | --- | --- | --- | --- |
| `EP::LOCAL_CONSUMER_API_V1` | AVAILABLE_FROM_EP_MAIN | Phase-1 foundation → attachment/contract producers | schema-40 registration/credential closure | HISTORICAL_COMPLETE |
| `EP::PHASE3_STANDALONE_PACKAGE_AND_INSTALL_QUALIFICATION_V1` | AUTHORIZED / incomplete | Phase 0/1, clean-slate decision → installer/B9 | B8C/B8D package, schema-41, Server/Agent evidence | V1_BLOCKING |
| `EP::P_TRANSPORT_V1` | main `ACTIVE GAP`; PR #33 in flight | central repairs → queue/re-audit/B9 | three ingress + no authority leakage | V1_BLOCKING |
| `EP::P_QUEUE_V1` | qualification remains | transport → neutral/re-audit/B9 | project FIFO, lease/recovery/finalisation/isolation | V1_BLOCKING |
| `EP::P_NEUTRAL_V1` | ACTIVE GAP | queue → installer/re-audit/B9 | zero active DJConnect identity/local authority | V1_BLOCKING |
| `EP::P_INSTALLER_V1` | planned / incomplete | Phase3 package + neutral → release/Goldens/B9 | idempotent verify/repair/activation | V1_BLOCKING |
| `EP::P_RELEASE_V1` | ACTIVE GAP | Phase3 package + installer → re-audit/B9 | signed pinned release, compatibility, rollback | V1_BLOCKING |
| `EP::PHASE_P_REAUDIT_V1` | planned / incomplete | transport + queue + neutral + release → Goldens/B8E | no active gaps or approved retirement | V1_BLOCKING |
| `EP::PD_INSTALLED_PRODUCT_GOLDENS_V1` | blocked by re-audit | re-audit + installer → Phase-S/B8E | installed Managed, Genesis, armed retry | V1_BLOCKING |
| `EP::PHASE_S_EXECUTION_PROTOCOL_FOUNDATION_V1` | blocked by P-D | P-D → B8E/B9 | minimum CENTRAL-to-Agent first governed execution | V1_BLOCKING |
| `EP::B8E_ZERO_LOSS_PASS` | `B8E_REPAIR_PLAN_REQUIRED` | re-audit + P-D + Phase-S → B9 | every live capability installed-evidenced; unresolved=0 | V1_BLOCKING |
| `EP::STANDALONE_EP_VERIFIED` | planned / unavailable | all preceding standalone prerequisites → Phase-4 producers | B9 installed Server, newly registered Agent, attached project, first governed execution | V1_BLOCKING |
| `EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1` | planned / unavailable | Local Consumer API + B9 → Workspace onboarding | clean install, fresh registration, idempotency, routing, first execution | V1_BLOCKING |
| `EP::ENGINEERING_CONTRACT_FOUNDATION_V1` | planned / unavailable | Local Consumer API + B9 → Forge F4/L0 | its named qualification gate | V1_BLOCKING |
| `EP::ENGINEERING_CONTRACT_FOUNDATION_V1_QUALIFIED` | unavailable | contract foundation → Forge F4/L0 | installed contract, negative-admission, recovery and evidence-projection tests | V1_BLOCKING |
| `EP::SOURCE_RETIREMENT_DJCONNECT_V1` | post-standalone | B9 → retirement | reverse responsibility audit | V1_ENABLING_NON_BLOCKING |
| `EP::PHASE_S_REAL_PROJECT_DOGFOODING_V1` | post-standalone | B9 + minimum Phase-S → broad Agent classification | multi-project dogfooding/reconnect | POST_V1 |

`EP_V1_PREREQUISITE_COUNT = 15` (the first fifteen rows through the
contract-foundation qualification); `EP_V1_PREREQUISITE_WITHOUT_CANONICAL_SOURCE = 0`;
`EP_V1_PREREQUISITE_WITHOUT_SUCCESSOR_TRACE = 0`.

Historical-name disposition: P-TRANSPORT **STILL_CANONICAL/IN_FLIGHT**;
P-QUEUE **STILL_CANONICAL**; P-NEUTRAL **STILL_CANONICAL**; P-INSTALLER
**STILL_CANONICAL**; P-RELEASE **STILL_CANONICAL**; Phase-P re-audit
**STILL_CANONICAL**; P-D Goldens **RENAMED** to
`EP::PD_INSTALLED_PRODUCT_GOLDENS_V1`; Phase-S **MERGED_INTO_OTHER_NODE** as
the minimum `EP::PHASE_S_EXECUTION_PROTOCOL_FOUNDATION_V1` plus post-V1 real
project dogfooding; B8E **STILL_CANONICAL** as `EP::B8E_ZERO_LOSS_PASS`; B9 /
STANDALONE_EP_VERIFIED **MERGED_INTO_OTHER_NODE** as
`EP::STANDALONE_EP_VERIFIED`; `CUTOVER-DJCONNECT` **RENAMED** to post-B9
`EP::SOURCE_RETIREMENT_DJCONNECT_V1`. `UNCLASSIFIED_HISTORICAL_EP_NODE = 0`.

The authoritative non-cyclic order is Phase-P → re-audit/P-D → minimum
Phase-S + B8E → B9/standalone verification → Phase-4 producers → source
retirement/broader dogfooding. `EP_MIGRATION_DEPENDENCY_CYCLES = 0`.

## Producer-to-consumer continuity

| EP producer | Availability / prerequisite trace | Forge consumer | Workspace consumer |
| --- | --- | --- | --- |
| Local Consumer API V1 | EP main; Phase-1 closure | fixture/contract boundary only | registration base only |
| Submission ingress | PR #33 only; P-TRANSPORT then B9 before an installed producer claim | F4 submission adapter | future permitted submission UX |
| Queue/scheduling, lease, retry/repair, receipts, multi-repository execution | P-QUEUE → neutral/re-audit/P-D/Phase-S/B8E/B9 | F4 reconciliation | execution/status/retry projections |
| Project attachment/admission | B9 → Phase-4 Increment 1 qualification | F3 | onboarding control plane |
| Engineering Contract Foundation / capability discovery | B9 → Phase-4 Increment 2 → its qualification | F4 and L0 | quality projection where applicable |
| Installed control plane | Phase3 + all Phase-P + P-D + Phase-S + B8E → B9 | F9 Golden | onboarding/control-plane qualification |

`EP_PRODUCER_WITHOUT_PREREQUISITE_TRACE = 0`. The current Workspace roadmap
uses precisely the attachment producer above; it does not treat the completed
Local Consumer API as attachment/admission evidence. `WORKSPACE_EP_GATE_WITHOUT_PRODUCER_TRACE = 0`.

Forge `main` has four total external gates, of which two are EP gates:
`EP::PROJECT_ATTACHMENT_AND_ADMISSION_V1` for F3 and
`EP::ENGINEERING_CONTRACT_FOUNDATION_V1_QUALIFIED` for F4. Thus
`FORGE_EP_EXTERNAL_GATE_COUNT = 2`; `FORGE_EXTERNAL_GATE_WITHOUT_EP_PRODUCER_TRACE = 0`.

## Forge gate resolution and safe parallelism

| Forge node | Required EP producer and exact readiness | Classification |
| --- | --- | --- |
| F1 | none | READY_NOW |
| F2 | none after F1 | READY_AFTER_FORGE_PREDECESSOR |
| F3 | `PROJECT_ATTACHMENT_AND_ADMISSION_V1`; B9 + Phase-4 Increment 1 | WAITING_EP_IMPLEMENTATION |
| F4 / L0 | `ENGINEERING_CONTRACT_FOUNDATION_V1_QUALIFIED`; B9 + Phase-4 Increment 2 qualification | WAITING_EP_IMPLEMENTATION |
| F5, F6 | none after F2 | READY_AFTER_FORGE_PREDECESSOR |
| F7 | Forge evidence contract/F4, optional V1 | READY_AFTER_FORGE_PREDECESSOR |
| F8 | KB producer | WAITING_WORKSPACE_PRODUCER / POST_V1 |
| F9 | F3/F4 plus Workspace onboarding qualification | WAITING_CROSS_PRODUCT_QUALIFICATION |

PR #33 therefore does not make F3/F4 available, but it is more precise than
`WAITING_EP_IMPLEMENTATION`: its direct ingress consequence is
`WAITING_EP_HUMAN_REVIEW`, `WAITING_EP_HOSTED_QUALIFICATION`,
`WAITING_EP_OWNER_AUTHORIZATION`, `WAITING_EP_MERGE`, then
`WAITING_EP_POST_MERGE_RECONCILIATION` before P-QUEUE. Forge has F1/F2/F5/F6
work available during EP migration. `HIDDEN_EP_SUCCESSOR_ASSUMPTIONS = 0`;
`OVERCONSTRAINED_FORGE_EP_DEPENDENCIES = 0`;
`UNDERCONSTRAINED_FORGE_EP_DEPENDENCIES = 0`.

The machine-readable DAG records the same producer/prerequisite trace. No
Forge node allocates or implements an EP node.

`FORGE_EXTERNAL_GATE_WITHOUT_EP_PRODUCER_TRACE = 0`  
`OPAQUE_EP_V1_GATE = 0`  
`EP_V1_PREREQUISITE_WITHOUT_DAG_TRACE = 0`
