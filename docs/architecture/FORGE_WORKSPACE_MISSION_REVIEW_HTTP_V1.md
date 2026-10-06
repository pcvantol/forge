# Forge Workspace Mission review HTTP V1

**Producer join:** `L4-L3-GP-REVIEW-INBOX-V1-20261006` in Forge [#207](https://github.com/pcvantol/forge/issues/207). **Consumer:** Workspace [#208](https://github.com/pcvantol/forge/issues/208). This is an explicitly scoped review seam for an already-approved Mission. It does not create or approve a Mission, change progression policy, accept a Mission end, invoke EP directly, or let Workspace become a second governance store.

The versioned JSON Schema shipped in the Forge wheel is `forge/api/workspace-review-inbox-v1.json`. The route catalogue is `forge/api/server-openapi-v1.json`. The Server stays on its existing loopback listener. Its ordinary administrator bearer and the existing `forge-workspace-status-read/v1` bearer retain their own meanings. Neither credential is a Workspace review principal.

## Owner provisioning and subject binding

The owner selects one **existing installed Forge Runtime Instance**, one actual authenticated Workspace actor identifier, an explicit set of 1–32 existing Mission IDs, and an expiry no more than 90 days away. The installed command creates a random private bearer file and records its SHA-256 digest, instance, actor identifier, Mission set, expiry, canonical `platform_architect` role, `primary_operator` role actor and `ARCHITECTURE_APPROVAL` capability in `<data-root>/credentials/workspace-review/grants.json`. Grant files, token files and their lock are private. The bearer never appears on stdout, in a response or in the stored grant. A new token path is required for each issuance. The owner revokes by grant ID; the next request is denied. A missing, foreign-instance, expired, revoked, public-mode, malformed or symbolic-link grant fails closed.

```sh
forge-workspace-review-grant --data-root <existing-root> issue \
  --principal-id <authenticated-workspace-actor-id> \
  --mission-id <existing-mission-id> --expires-at 2026-10-07T12:00:00Z \
  --token-file <new-private-token-file>
forge-workspace-review-grant --data-root <existing-root> revoke --grant-id <issued-grant-id>
```

The provisioning output contains the grant ID and bound scope, never the token. An owner may issue separate grants for separate actors. Workspace Server must bind its own authenticated client actor and selected Forge instance to the corresponding owner-issued bearer. Client JSON `actor`, `role`, `capability` or a locally selected project cannot establish authority. Forge authenticates the bearer on every request and rechecks the live grant, current required role, capability, Mission, requirement, subject/evidence/policy revisions and operator governance authority under the canonical decision lock at mutation. The installed Solo profile currently supports only the Platform Architect primary-operator progression role. A separate Business owner acceptance capability is not supplied by this seam.

## Scoped reads

| Method | Path | Result |
| --- | --- | --- |
| `GET` | `/v1/reviews` | Current items for only the grant's explicit Mission set; `scope.complete_within_scope=true` never means globally complete. |
| `GET` | `/v1/reviews/missions/{mission_id}` | One currently authorized Mission's safe review projection. |

Each item identifies its Forge instance, Mission, bound review authority, current lifecycle state and state revision. `review_kind` is `PROGRESSION`, `FINAL_ACCEPTANCE`, `EXTERNAL_GATE` or `NONE`. A progression requirement includes its exact requirement/subject/evidence/policy revisions, required role/capability, blocker scope, completed Action ID, safe evidence digest and receipt reference when available. Unsafe or unknown facts are null. The projection does not return raw provider prompts, Host evidence bodies, secrets, guessed project membership, percentages or deadlines. Reads cause no decision, provider or Host effect. `observed_at` and `freshness=CURRENT_FORGE_RUNTIME_READBACK` describe the time and source of that individual read.

`allowed_outcomes` is nonempty only for an undecided, current `AWAITING_APPROVAL` progression requirement matching the grant. The canonical decisions are `approve`, `reject`, `amend`, `defer`. A recorded nonapproval remains visible with its decision digest and an empty outcome list. Mission-end acceptance is a separate owner obligation with no progression outcomes. An external gate is never locally approvable. Granted Missions with no current review remain visible with `review_kind=NONE`; an empty review selection must not be presented as global absence.

## One durable decision operation

`POST /v1/reviews/missions/{mission_id}/decisions` accepts only the exact `forge-workspace-review-decision/v1` request: `operation_id`, `requirement_id`, `subject_digest`, `mission_state_revision`, `evidence_digest`, `policy_revision`, `decision`, and `reason`. The `operation_id` becomes the canonical Forge decision ID; it must be durable on the Workspace transport side before sending. No actor or role field is accepted. A successful 201 returns `forge-workspace-review-operation/v1`, the canonical operation receipt, current requirement/fence readback, runtime status and `recorded=true`. An identical replay uses the **same** operation ID and request, returns 200 with `recorded=false`, and creates no second canonical decision. Recovery may finish an interrupted authorized continuation without a duplicate successor. A conflicting payload, stale fence or other principal fails closed.

`GET /v1/reviews/missions/{mission_id}/decisions/{operation_id}` returns the same-principal durable decision receipt plus a fresh current Mission review item. After a lost POST response or process restart, Workspace reads this operation ID first. A 404 means the operation was not found for that principal; a 200 proves the canonical decision exists. A 503 during simultaneous requests is inconclusive: read back the same operation and, if necessary, retry the **same** request and ID. No blind new ID is permitted. Workspace reports success only when the receipt and authoritative current fence have both been validated; it must not infer success from transport delivery alone.

All review routes return 401 for an invalid, expired or revoked review bearer, and 403 for a valid bearer outside its Mission/route/role scope. The admin and status read bearers receive 403 on review routes. Review bearers receive 403 on admin and status routes. The Server rejects an unauthenticated or out-of-Mission POST before reading its body or dispatching a mutation. Only Forge records the decision and releases a successor; `reject`, `amend` and `defer` do not cancel already running EP work.

## Qualification boundary

Producer acceptance requires full Forge validation, strict greater than 80.2% executable-line coverage for each changed production source file, independent Quality and Security review of the exact head, hosted checks, protected merge, and a noneditable wheel installed from exact protected main. The installed matrix must use two isolated principals and scopes, real private storage and HTTP listener, receipt/restart/replay and negative authorization cases. Synthetic Mission/Host/provider fixtures may adapt only external EP, LLM and OS boundaries. The exact source, wheel digest and test receipt are recorded in #207. Workspace must independently qualify its authenticated actor binding, native client, Server transport and installed app in #208.
