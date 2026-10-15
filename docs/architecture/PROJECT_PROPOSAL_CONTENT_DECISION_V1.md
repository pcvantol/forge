# Project proposal content decisions V1

Selected R54/plan1: L3-PROJECT-PROPOSAL-CONTENT-DECISION-V1-20261015.
Forge 2.20.0/schema46. The profile/contract was published before first
qualification. Implementation is protected-delivered; final scoped qualification
is governed by the delivery record below. This specification is not a human
business approval receipt. R53 and predecessors remain closed.

## CONTENT_BASELINE_ONLY/1.0

The first profile is pb-render/1.0, portable-docs/1.0.0, authority,
GENESIS/LOCAL_POSIX, DOCUMENT_ONLY security, NO_PRODUCT_CODE stack. It requires
separate BUSINESS and ARCHITECTURE decisions over exactly the same frozen
proposal. A single role is DECISION_NEEDED, a latest role's REQUEST_CHANGES
produces CHANGES_REQUESTED, and both latest role approvals produce CONTENT_APPROVED.
Each next decision carries expected_decision_revision and the previous decision ID.

Approval acknowledges all original product.open_questions, verbatim and in order;
it does not claim to resolve them. A future database choice may remain open.
Exact valid original input/artifact/manifest binding, supported document-only
profile, current human role authority and a reason are mandatory. No newly
invented EP inspection, product scan or model review is required.

The machine profile is forge/api/project-proposal-content-profile-v1.json.
Content approval authorizes NO registration, repository effect, risk waiver,
execution plan, Action or Mission. Physical target, security/TDE/engineering
readiness remain NOT_ASSESSED. Existing provisional identity references are not
verified physical IDs. R52 result bytes remain PROPOSED_NOT_APPROVED, unchanged.

## Rights and original subject

Separate finite READ/DECIDE grants are issued by the existing trusted owner/setup,
scoped to actual instance/operator, principal, audience, source proposal owner,
dossiers, profile, explicit roles and expiry (maximum thirty days). DECIDE binds
the human principal to the existing canonical operator fingerprint and requires
its current BUSINESS_APPROVAL/ARCHITECTURE_APPROVAL role capabilities. Explicit
owner-selected grant roles are required even for the already-bound solo operator.
No ordinary HTTP issuance, admin/READ/PREPARE/ADVISE fallback or actor/role header.
A forwarding consumer uses the explicit human-bound grant, not a generic service
credential as proof of a human decision. READ-only observers have no role right.

Original input/result/record/manifest digests, proposal ID, baseline/profile and
supplied source references are frozen in the decision. R52 has no structured
trusted concept revision; concept_revision is null, explicitly NOT_STRUCTURALLY_
PROVIDED_BY_R52. Opaque supplied source references are not reinterpreted as a live
Workspace revision. New IDs, inputs or profiles inherit no decision.

## Routes and durability

Contract forge-project-proposal-content-decision/v1, closed JSON schema:
forge/api/project-proposal-decisions-v1.json. Bearer plus X-Forge-Content-Audience.

- GET /v1/project-proposal-decisions/capability: current scope and decision profile.
- GET /v1/project-proposal-decisions/proposals/{plan_id}?dossier_id=...: exact subject, append-only history and current content-only projection.
- POST /v1/project-proposal-decisions/decisions: explicit frozen subject, role, APPROVE_CONTENT or REQUEST_CHANGES, reason, acknowledged open points, operation ID, CAS/predecessor.
- GET /v1/project-proposal-decisions/intents/{operation_id}?dossier_id=...: original decision and current separate projection.

CLI forge-project-proposal-decisions provides init/issue/revoke and equivalent
capability/read/decide/intent. Known operation IDs and frozen requests precede
transport. Duplicate/concurrent identical operations return the original record;
changed same-key input conflicts. No new ID or silent retry after a lost response.
Separate Server OS restart reads the same original. Historical decisions retain
their original human/grant/time/source, even after grant revocation; current
read/decision authority is separate and still required.

Existing R52 private IO, initialization witness, keyed seals, bounded publication
and canonical writer boundary are reused. Lock order: R52 source grant, own grant,
canonical writer. No render/model/network/client wait occurs under these short
boundaries. Source and exact CAS are checked at admission/commit/publication;
stale response publication is denied. Revoke/expiry/operator/capability changes
block current access, without claiming to retract bytes already received.
Missing/corrupt initialized stores fail closed, not empty history.

Limits: 64 KiB request, eight decisions per proposal, 64 globally, 1 MiB decision
store, eight dossiers and 32 grants. Capacity is a conflict, never eviction.
The full HOB/PB family, effect/apply and active native approval UI remain open.
Early consumer mapping does not change L4 scope/pins or introduce a peer ACK gate.

## Protected implementation and closure boundary

[PR292](https://github.com/pcvantol/forge/pull/292) merged at
`13cd5d2b37fedceddd8d4dda65477f3494e9d4c1` after complete independent
Quality/Security, required full CI and changed-production coverage strictly>80.2%.
The [delivery record](../qualification/R54_PROJECT_PROPOSAL_CONTENT_DECISION_DELIVERY_2026_10_15.md)
preserves actual Mac and labeled hosted HTTP evidence, original failures,
current separate TDE FAIL, predecessor terminals and the remaining finalization/
NEW exact-final-main gates. Only the owning terminal register can close those
future gates after fresh actual evidence; candidate PASS is not final-main PASS.
