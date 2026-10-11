# Scoped workset activity read V1 — r49 active

Selected L3-SCOPED-WORKSET-ACTIVITY-READ-V1-20261011, same writer/base091ec16.
No source delivery claimed; implementation, qualification/reviews/CI/merges and NEWfinal-main installed evidence remain open.

## Source → fact → identity → original time/sequence matrix

| Existing source | Public fact | Stable identity | Time/sequence boundary |
| --- | --- | --- | --- |
| Canonical workset governance decisions | Business / Architecture approved exact workset | decision_id | original occurred_at |
| workset release_commands | explicit future release/disarm applied | canonical operation_id | persisted observed_at; not query time |
| control_operations | PENDING intent or APPLIED hold/unhold receipt | original operation_id + state | original intent/applied receipt time if recorded; otherwise UNKNOWN |
| order_intents / order_amendments | PENDING intent separately from applied order | original operation_id + state | original created_at / receipt.applied_at |
| actual workset claims | activation claimed, not execution started | claim operation_id + candidate | original persisted claim time if available; otherwise UNKNOWN |
| Mission state_history | recorded lifecycle transition, including acceptance wait/reconciliation | Mission-ID + original sequence | original occurred_at + sequence; stable presentation order is not cross-source causality |
| immutable Mission execution_history | external host result, separate from Forge reconciliation/acceptance | Mission-ID + receipt_id | original host execution time if recorded; otherwise UNKNOWN |
| canonical final acceptance decisions | actual human approval, separate from terminal result | decision_id | original occurred_at and real evidence bindings |

Current state uses the existing worklist v1/v2 effective-order/completion/condition projection separately. Missing historic portions are PARTIAL, not invented backfill. No migration, eventbus, materialized history writer or generations from reads.

## Cursor contract under development

Bounded signed checkpoint, fixed16 events/page, maximum128 offered events and32768-byte page/cursor. Cursors bind actual instance, dataset generation, original workset and current reader context. Every call rechecks READ scope. Changed source snapshot during an unfinished page sequence requires explicit RESYNC_REQUIRED; no quietly mixed pages. Completed checkpoints preserve event identities/digests and pick up newly visible older facts regardless of presentation timestamp. Removed/changed known facts require explicit resync. Duplicate requests reproduce event IDs; caller can identify replay. No read creates cursor-key/authority/storage.

## Supported setup and consumer route

Forge 2.15.0 / runtime schema 46. Existing current Solo/G001 authority can explicitly
issue a finite READ-only grant with `forge-workset-activity-grant issue`; that
explicit setup provisions the private cursor key once. GET and CLI reads never
provision it. The activity grant grants neither reorder nor release nor acceptance.
Discover capability, read pages, resume the returned checkpoint, or follow an
individual event's authenticated source reference with `forge-workset-activity`.
Current worklist conditions remain separate from historic facts; private paths and
credential values are removed from public labels. Exports cannot overwrite the
selected runtime or input credentials/checkpoint.

Original execution_host_exchange_audit records add two distinct retained facts:
Forge's actual submission sent and EP's submission receipt received. They prove
neither physical execution nor a terminal result nor human final acceptance.
Each has its original audit ID/time and original source digest. Missing exchange
records are PARTIAL; the route never reconstructs them from a claim.

Unfinished cursors bind the exact retained-source snapshot, including source data
not displayed in event summaries. A changed snapshot requires explicit resync.
Completed checkpoints admit new older facts without losing previously seen IDs.
The scan bound is 2 MiB, each source document 256 KiB, each page/cursor 32 KiB.

## Qualification boundary and remaining delivery

The installed gate reuses the existing typed owning-worker receipt validation and
process-group cleanup. Its 19 tests run in three isolated workers (9/5/5), with a
390-second shared deadline. A separate isolated control removes the actual
snapshot guard and must fail the linked race test. Public receipts bind exact
source revision, noneditable wheel, every installed payload file, supported CLI
entrypoints, runtime version/schema, raw worker receipts/logs and own cleanup.
The external model, OS identity and EP HTTP simulator remain explicitly fixtured.
This does not qualify a live EP environment or user installation.

The actual product A→C→B chain passed during development, including retained
submission exchanges and original acceptance evidence. This is development
progress, not final delivery: exact-head full validation, per-file coverage,
independent complete Quality/Security, protected implementation and nonempty
finalization merges, and a new exact-final-main installed qualification remain
mandatory. The formal correction admission remains 0/3 until the first formal
review pair and any correction booking.
