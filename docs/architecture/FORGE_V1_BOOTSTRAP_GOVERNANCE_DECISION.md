# Forge V1 Bootstrap Governance Decision

**Status: canonical governance decision when present on owning main.** This
governs a temporary V1 bootstrap programme only; it neither implements a runner
nor changes EP's execution or lease authority. Policy clarifications are part of
[Policy governance and effective profiles](POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES.md).
They do not activate, renew or modify a live grant.

## Authority

`DAG_READY_IS_EXECUTION_AUTHORITY = FALSE` and
`MISSION_GOVERNANCE_BYPASS = FALSE`. The ordinary lifecycle remains canonical.
Forge autonomy begins only inside an approved Mission.

Forge adopts **Model C — bounded bootstrap programme authorization**. A human
may approve one immutable programme envelope covering only listed V1 DAG nodes.
Within that envelope, a passing node may become a bounded implementation
Mission/Action without redundant strategic re-approval. New product objective,
architecture/security decision, cross-product authority, undefined contract,
write-scope expansion, repository outside the allowlist, DAG objective change,
or scope expansion transitions the node to `BLOCKED_GOVERNANCE`; it produces a
structured proposal and returns through ordinary refinement/approval.

`BOOTSTRAP_SCOPE_EXPANSION_AUTO_ACCEPTED = FALSE`.

The durable authorization record contains `authorization_id`, `programme_id`,
programme/DAG version and digest, approved main SHA and node set,
productization-contract version, architecture references, allowed repositories
and write scopes, exclusions, preserved human/external gates, approver/time,
and supersession/revocation. It is stale on any material change to those
authority inputs; derived state/evidence refresh alone is not material.

`BOOTSTRAP_PROGRAMME_AUTHORIZATION_RECORD = DEFINED`  
`BOOTSTRAP_AUTHORIZATION_STALENESS = DEFINED`  
`BOOTSTRAP_NODE_DISPATCH_AUTHORITY = MACHINE_DECIDABLE`

The record is written only through Forge's canonical governance writer with
capability `OWNER_PROGRAMME_AUTHORIZATION`. Its source reference and verified
owner-account binding are immutable evidence; a local status write, a copied
prompt, or a retrospective assertion is not an authorization record.

## Owner authorization

Forge has no inherited EP Owner Authorization workflow. This decision creates
the Forge mapping: `NORMAL_LOW` changes need no separate owner authorization;
`ELEVATED` persistence/schema, cross-product-contract or repository-governance
changes require exact-head Owner Authorization; `HIGH` security/auth,
credential, execution/lease, installer/update, remote-access or autonomous
mutation changes require exact-head Owner Authorization plus security review.
New commits invalidate candidate qualification, not automatically the unchanged
programme grant. Exact-head evidence is distinct from CI and Human UI Review.

`FORGE_OWNER_AUTHORIZATION_RISK_MAPPING = DEFINED`  
`OWNER_AUTHORIZATION_APPLICABILITY = DEFINED`  
`OWNER_AUTHORIZATION_STALENESS = DEFINED`  
`OWNER_AUTHORIZATION_SCHEDULER_CONTRACT = RESOLVED`

## Merge and operating boundary

Within a valid programme authorization, a node may be squash-merged only after
executable exact-head qualification has passed. `MERGE_READY` requires
implementation, local and current hosted qualification, resolved reviews,
applicable UI/owner/security gates, valid authority, fresh contracts and
mergeability. A bounded merge packet binds node, PR, exact head, risk, DoR/DoD,
checks/reviews/gates, scopes, unlocked dependents and known risks.

Without a applicable delegation, retain the explicit human merge boundary.
With a valid scoped delegation, the existing authorized merge executor may
consume the exact qualified packet without another owner message. A policy
flag alone does not authorize a merge; branch protection is never bypassed.
Post-merge qualification is still required before `DONE`. Parallel PRs
re-evaluate after every relevant merge. This target does not assert that every
current runtime/CI merge adapter already consumes the grant.

`BOOTSTRAP_AUTO_MERGE = QUALIFIED_SQUASH_ONLY`
`QUALIFIED_SQUASH_MERGE_REQUIRED = TRUE`
`MERGE_DECISION_PACKET = DEFINED`  
`PARALLEL_PR_MERGE_REEVALUATION = TRUE`

## Repair budget and exact-head proof are separate

Autonomous repair requires a finite authorized budget. Consumption is bound to
the Action/run continuation lineage and survives new SHA, PR, phase, process
restart and resubmission of the same work. The current bootstrap upper bound is
three total operational repair rounds per run/continuation lineage, subject to
any stricter applicable programme ceiling. EP owns actual operational round
reservation/consumption; Forge correlates it and enforces programme limits,
not an additional independent provider-repair allowance.

Every changed candidate needs fresh exact-head qualification. It does not
receive a fresh repair budget. This explicitly supersedes the earlier per-PR/
per-head wording that could imply a budget reset on each commit. Previously
recorded consumption and provenance remain evidence and must be preserved.

The runner stops at scope expansion, expired/revoked authorization, unresolved
security/review/CI blockers or exhausted limits. Ordinary bounded corrective
work may continue under the same valid delegation; a failed check is not itself
new authority. A fourth repair cannot be created by a new run ID or a UI edit.

`AUTONOMOUS_REPAIR_ENABLED = BOUNDED_ACTION_LINEAGE`
`UNBOUNDED_AUTONOMOUS_REPAIR = FALSE`  
`BOOTSTRAP_RUNNER_CAN_SELF_AUTHORIZE = FALSE`  
`BOOTSTRAP_GOVERNANCE_FORWARD_COMPATIBLE = TRUE`

Documentation/DAG adoption does not renew expiry, mint capability grants,
retroactively approve candidates, reset counters or migrate runtime state.
Any material change to a live programme's authorized node set or objectives
requires explicit staleness reconciliation through the owning writer.
