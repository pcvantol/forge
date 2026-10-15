# Project bootstrap V1 — Forge implementation roadmap

**Owner:** Forge. **Status:** R50–R54 selected subsets CLOSED; R55 inspection adoption implementation delivered, own finalization/final qualification OPEN; full remaining nodes PLANNED. **NO_BUMP.**
This scoped roadmap concretizes L1/L1-R in the [canonical strategic roadmap](../../knowledge/bootstrap/10_ROADMAP.md), consumes L0 baseline enforcement and F2/FH services, and does not replace those programmes. Design closure is not implementation closure of FWV1-G002/G003/G004/G010.

Read the [architecture and artifact contract](../architecture/PROJECT_BOOTSTRAP_AND_ARTIFACT_MANIFEST_V1.md) and [40 qualification families](../architecture/PROJECT_BOOTSTRAP_QUALIFICATION_V1.md). The [JSON DAG](project-bootstrap-v1.json) is a non-executable delivery index. It contains only Forge work; peer nodes below are evidence requirements owned and scheduled by peers.

| Node | Depends on | Deliverable / closure proof |
| --- | --- | --- |
| PB-F0 | none | Versioned manifest/operation/identity and capability contracts; EP B8R/F2 compatibility mapping, not new incompatible identity fields |
| PB-F1 | PB-F0 | Packaged offline baseline registry, conditional artifact renderer and portable project contract; PB-12..18, PB-39..40 |
| PB-F2 | PB-F0, PB-F1 | Inspect-input interpretation, adoption mappings, immutable preview/approved plan and no implicit grants; PB-05,10,11,14,22 |
| PB-F3 | PB-F2; EP PB-E1 | Restart-safe HTTP provisioning coordinator using the existing runtime/services; same-operation recovery; PB-23..25,32 |
| PB-F4 | PB-F3; EP PB-E2 | Genesis readiness/reconciliation, absent/unborn/existing local inputs; PB-02..06 |
| PB-F5 | PB-F3; EP PB-E3 | Managed readiness/adoption and actual governance readback; PB-07..11,19..21 |
| PB-F6 | PB-F4, PB-F5; EP PB-E4 | Guarded Genesis-to-Managed promotion with immutable identity/history; PB-26..30 |
| PB-F7 | PB-F3; qualified FH services/transport subset | Thin local/remote CLI and HTTP operation/read/export capabilities with published inventory; PB-01,32,38 |
| PB-FQ | PB-F1..PB-F7; EP PB-EQ | Installed Genesis + Managed + promotion qualification; no source checkout, no auto-Mission, preserved policies/roadmap and all applicable PB families |

EP roadmap: `pcvantol/engineering-platform:docs/development/PROJECT_BOOTSTRAP_V1_ROADMAP.md`.
Workspace roadmap: `pcvantol/workspace:docs/PROJECT_BOOTSTRAP_V1_ROADMAP.md`.
EP PB-EQ consumes Forge request fixtures/contracts, not PB-FQ; Workspace PB-WQ consumes qualified peer slices and never precedes headless bootstrap. This prevents a cross-product qualification cycle.

Parallel lanes: PB-F1 deterministic rendering and EP inventory/ledger can advance after their contract alignment. Genesis PB-F4 and Managed PB-F5 independently qualify their modes. Promotion joins both; Workspace is optional for headless qualification. Full GitHub provisioning remains online, while installed baseline availability is proven without access to development repositories.

No runtime, package version, active policy, existing project, executable programme graph or current Mission-3 acceptance is changed by this design. Next work must be a separately authorized bounded implementation increment with fresh source/installed capability evidence.

## R50 portable proposal implementation

[Portable render contract](../architecture/PROJECT_BOOTSTRAP_PORTABLE_RENDER_V1.md) maps the selected PB-F0/PB-F1 subset and actual CLI. Full PB-F1/remote profiles and PB-F2..FQ remain open. Protected delivery and exact-final-main installed/offline proof are recorded by the owning R50 delivery receipt; source availability alone is not installed PASS.

## R50 reconciliation and selected R51 subset

R50 is CLOSED on Forge2.16.0/final-main18ad9b5, with original
[terminal register](https://github.com/pcvantol/forge/issues/207#issuecomment-6132396962)
and new exact-main41-case installed/offline evidence. The prior selected-subset
IMPLEMENTATION_PENDING_QUALIFICATION label is reconciled to that actual narrow
closure; original receipts and parent node IDs/statuses are not rewritten.

[Supplied-inventory adoption preview](../architecture/PROJECT_ADOPTION_PREVIEW_V1.md)
selects only PB-F2 offline interpretation/mapping/preview. Not a repository scan,
EP wire inspector, approved effect plan, HTTP/apply, registration or readiness.
R51 implementation is protected-delivered via PR285/main eb717036; complete
Quality/Security and current candidate installed qualification PASS. The
[delivery record](../qualification/R51_PROJECT_ADOPTION_DELIVERY_2026_10_13.md)
keeps finalization and NEW exact-final-main installed qualification open. Full PB-F1/PB-F2 and peerflows
remain open. Existing R50 pins and L2/L4 tasks/pins/budgets remain unchanged.

## Current selected-subset reconciliation — R54

The earlier R51 delivery-stage checkpoint above remains historical. Its
[terminal record](https://github.com/pcvantol/forge/issues/207#issuecomment-6148412716)
closed only supplied-input preview on Forge2.17.0/b3581003.
[R52 terminal](https://github.com/pcvantol/forge/issues/207#issuecomment-6155303736)
closed private PREPARE/READ on Forge2.18.0/96e1d736;
[R53 terminal](https://github.com/pcvantol/forge/issues/207#issuecomment-6168444579)
closed pre-project advisory on Forge2.19.0/877602f. Their original history,
qualification receipts, producer pins and operational counters are preserved.

The selected R54 PB-F2/HOB-F02 subset adds exact human-bound, finite
CONTENT_BASELINE_ONLY/1.0 decisions over existing portable GENESIS proposals.
[Contract](../architecture/PROJECT_PROPOSAL_CONTENT_DECISION_V1.md) and
[delivery record](../qualification/R54_PROJECT_PROPOSAL_CONTENT_DECISION_DELIVERY_2026_10_15.md)
bind protected implementation PR292/main13cd5d2, complete source assurance and
candidate evidence. The [R54 terminal](https://github.com/pcvantol/forge/issues/207#issuecomment-6195361250)
closed this bounded subset at final main0ea1b1a, preserving its original pins,
failures, counters and TDE-FAIL boundary.
Business AND Architecture are required; open points remain visible; original
R52 proposal bytes remain unchanged. This closes no full PB-F2/PB-F7/HOB family,
effect/apply/provisioning/readiness or native active-approval workflow.


## Current selected inspection-consumer subset — R55

R55 implements only PB-F2/HOB-F02 original qualified EP inspection -> private
source-bound documentary adoption preview. [Owning contract and field mapping](../architecture/EP_INSPECTION_ADOPTION_PREVIEW_V1.md),
[delivery record](../qualification/R55_EP_INSPECTION_ADOPTION_DELIVERY_2026_10_15.md)
and implementation PR294/main7061874 bind the actual independent assurance,
normal full CI and candidate installed HTTP proof. Existing R50 renderer/R51
rules/R52 storage are reused; historical SUPPLIED_UNVERIFIED is unchanged.

Qualified EP2.3.121/f3b56303 is pinned; owning authenticated original GET only,
no new inspection, identity/approval/effect/model/Action/Mission. Missing mode,
content/context/currentness/absence stays unknown. Full PB-F2/PB-F7/HOB,
provisioning/effect/remote and full qualification families remain open. L2's
independent later progress work and L4plan106/pins/budgets are unchanged.

This own nonempty finalization still requires its independent reviews/checks,
normal protected merge and NEW exact-final-main installed HTTP/restart/readback/
cleanup plus immutable handoff/terminal record. No automatic successor.
