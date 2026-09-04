# Forge V1 Bootstrap Governance Decision

**Status: canonical governance decision.** This governs a temporary V1
bootstrap programme only; it neither implements a runner nor changes EP's
execution or lease authority.

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

## Owner authorization

Forge has no inherited EP Owner Authorization workflow. This decision creates
the Forge mapping: `NORMAL_LOW` changes need no separate owner authorization;
`ELEVATED` persistence/schema, cross-product-contract or repository-governance
changes require exact-head Owner Authorization; `HIGH` security/auth,
credential, execution/lease, installer/update, remote-access or autonomous
mutation changes require exact-head Owner Authorization plus security review.
New commits invalidate it. It is distinct from CI and Human UI Review.

`FORGE_OWNER_AUTHORIZATION_RISK_MAPPING = DEFINED`  
`OWNER_AUTHORIZATION_APPLICABILITY = DEFINED`  
`OWNER_AUTHORIZATION_STALENESS = DEFINED`  
`OWNER_AUTHORIZATION_SCHEDULER_CONTRACT = RESOLVED`

## Merge and operating boundary

Bootstrap V1 auto-merge is disabled. A node reaches `MERGE_READY` only after
implementation, local and exact-head hosted qualification, resolved reviews,
applicable UI/owner/security gates, valid authority, fresh contracts and
mergeability. It then enters `WAITING_HUMAN_MERGE`; human merge is followed by
post-merge qualification before `DONE`. A bounded merge packet includes node,
PR, exact head, risk, DoR/DoD, CI/reviews/gates, scopes, unlocked dependents and
known risks. Parallel PRs re-evaluate after every merge.

`BOOTSTRAP_AUTO_MERGE = FALSE`  
`HUMAN_MERGE_REQUIRED = TRUE`  
`MERGE_DECISION_PACKET = DEFINED`  
`PARALLEL_PR_MERGE_REEVALUATION = TRUE`

Autonomous repair remains disabled: a future runner may classify and stop at
`REPAIR_REQUIRED`, never reinvoke itself without a separate finite policy.
The first operating mode is autonomous preparation/observation only; programme
approval, out-of-envelope decisions, security/UI/owner gates, repair authority
and merge stay human.

`AUTONOMOUS_REPAIR_ENABLED = FALSE`  
`UNBOUNDED_AUTONOMOUS_REPAIR = FALSE`  
`BOOTSTRAP_RUNNER_CAN_SELF_AUTHORIZE = FALSE`  
`BOOTSTRAP_GOVERNANCE_FORWARD_COMPATIBLE = TRUE`
