# Project bootstrap V1 — Forge implementation roadmap

**Owner:** Forge. **Status:** R50 PB-F0/portable PB-F1 subset qualified; R51 PB-F2 supplied-input preview implementation delivered; full remaining nodes PLANNED. **NO_BUMP.**
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
