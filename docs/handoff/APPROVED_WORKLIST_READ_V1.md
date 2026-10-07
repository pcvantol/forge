# Approved worklist read producer — selected JOIN

JOIN: `L3-L4-APPROVED-WORKLIST-READ-V1-20261007`.
Forge assignment: `L3-FORGE-APPROVED-WORKLIST-V1-20261007`, r36.
Workspace owns its native consumer; Forge owns this producer and authorization.

## Versioned HTTP read boundary

Schema: `forge/api/workspace-worklist-v1.json`, Draft202012.
Contract: `forge-workspace-worklist/v1`.

- `GET /v1/worksets`: explicit authorized scope IDs; not project discovery.
- `GET /v1/worksets/{workset_id}`: one complete finite snapshot, maximum64 members.
- Authorization: independent `forge-workspace-worklist-grant/v1` bearer, bound
  to instance, principal/client actor and exact workset IDs. Issue/revoke with
  `python -m forge.workspace_worklist_grant --data-root ROOT issue ...`.
  Credentials are written exclusively to owner-selected private token files.
- Status/review grants remain unchanged; neither grants workset-read access.
  A workset-read token grants no status, reviews, decisions, provider or mutation.
- Membership/selector revisions bind exact definition/order. Snapshot revision
  binds workset control revision and observed item facts. No pagination or mixed
  snapshot merging. Membership/selector revisions are SHA256 exact definition digests.
  Snapshot is SHA256 UTF8 compact JSON with sorted keys, ensure_ascii=false, over
  contract_version,instance_id,installation_id,scope,membership_revision,
  selector_revision,workset_revision,activation_support,completeness,items,continuation. Refresh replaces the complete selected snapshot.
- Scope is explicitly `EXPLICIT_WORKSET`; `project_id` is null. No inferred
  project attribution, synthesized edges, or phantom Mission ID before Intake.
- Candidate IDs/revisions, committed order and dependency refs are exact.
  Execution/review/final acceptance/completion are separate facts. Unknown is
  not false or successful. Detail ref is typed `MISSION_REVIEW` only after real
  canonical allocation; existing review authorization remains separate.
- Producer-owned continuation supplies READY/BLOCKED/IDLE/UNKNOWN and exact next
  Candidate/Mission/order or null at idle. The consumer never derives it from counts.
  Canonical allocation_binding ties exact Candidate/revision/Mission/installation/
  envelope; safe typed evidence_references preserve completion/final Business proof.
- The foundation reports `activation_support=NOT_YET_QUALIFIED` and
  `ACTIVATION_NOT_YET_QUALIFIED`. Read proof must never imply scheduler proof.
  Full serial qualification will publish `QUALIFIED_SERIAL_APPROVED_WORKLIST`
  within the same contract's declared enum, after actual installed evidence.

## Negative examples and fail-closed behavior

| Request/state | Result |
| --- | --- |
| absent/invalid/revoked/expired/foreign-instance workset credential |401 |
| existing status/review token on workset route |403 |
| valid actorA token requesting actorB's foreign workset |403 |
| workset token POST/hold/release/reorder/intake/status/review |403 |
| absent/corrupt storage, missing Candidate source or approval integrity failure |503 with sanitized unavailable code |
| selected workset expired/revoked/held/disarmed/unapproved or stale Candidate | typed blocker, no intake/provider/EP effect |

Projection uses existing validated read-only SQLite snapshot, without bootstrap,
migration, last-access updates, allocation, planning, provider or EP requests.
Strings are bounded/redacted; only typed IDs/digests are links, never arbitrary
credential-bearing paths or URLs. Native local sort does not alter committed order.

## Source and installed gates

This contract is a producer implementation proposal until a protected source,
exact wheel digest and installed HTTP/read-zero-mutation receipt are posted in
#207/#208. Workspace may prepare its consumer against this schema; it must not
claim integrated acceptance from this document or source-only fixtures.
The full approved-worklist execution matrix remains in the same serial Forge
assignment. No live EP, signing or L2 prerequisite is introduced.
