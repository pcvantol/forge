# Policy governance V1 roadmap and cross-product DAG

Scoped roadmap under the [Forge roadmap](../../knowledge/bootstrap/10_ROADMAP.md).
Decision: [POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES_V1](../architecture/POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES.md).
Machine-readable companion: [policy-governance-v1.json](policy-governance-v1.json).

This increment delivers documentation and sequencing only. All implementation
nodes below are PLANNED. POL-0 records the design deliverable, not implemented
policy services. Peer rows describe dependencies; each peer roadmap owns its
local delivery and status. No dates, runtime readiness or grants are inferred
from this graph. It is not the executable bootstrap programme DAG.

| ID | Owner | Deliverable / acceptance boundary | Depends on | Disposition |
| --- | --- | --- | --- | --- |
| POL-0 | Four owning repositories; Forge coordinates vocabulary | Catalogue, source ownership, change/activation semantics, grant/fact separation and typed resolution documented consistently | none | Documentation increment; canonical only after owning merges |
| POL-F | Forge | Existing policy objects wired to owner services, revisioned assignments, effective snapshots and explanation; migration preserves lineage | POL-0 | PLANNED; independent of rich UI |
| POL-E | EP | Effective admission/validation/assurance profiles, shared repair consumption and applied-policy receipt evidence | POL-0 | PLANNED; owning assurance lane supplies required subset |
| POL-WC | Workspace | Role-aware view/proposal/decision consumer contract, historical/freshness semantics and negative authority cases | POL-0 | PLANNED contract-first; parallel/non-blocking |
| POL-B | Forge + EP, independent owner adapters | Exact materialized-request -> accepted-policy binding; conflicts/unsupported profiles denied; restart/revocation rules proven | POL-F, POL-E | PLANNED bounded integration |
| POL-Q | Forge + EP | Cross-product tests: no weaker override, no fourth repair, no stale grant, historic snapshot fidelity, no policy self-approval or duplicate side effect | POL-B | PLANNED integration qualification |
| POL-W | Workspace | Policy & Automation UI backed by real owner APIs; impact/role decisions, audit, no arbitrary workflow/SQL | POL-WC, POL-Q | PLANNED; POST_AUTONOMY UI |
| VR-F | Forge | Native version/release operations and immutable component/source/artifact lineage; no independent push-bot authority | POL-F | PLANNED release-capability slice |
| VR-X | EP | Authorized field-aware version preparation, clean exact-version build, qualified publication and receipts | POL-E | PLANNED execution slice; no Forge planning inside EP |
| VR-Q | Forge + EP | Idempotent version/dispatch/publish roundtrip and final artifact evidence; candidate qualified after version preparation | VR-F, VR-X, POL-Q | PLANNED production-release prerequisite |
| POL-P | Forge Platform | Policy/runtime compatibility manifest and 1/2/3-role deployment composition; owner acceptance receipts, no direct SQL | POL-Q, VR-Q | PLANNED; installer production qualification |

```text
POL-0 -> POL-F -> VR-F -----------+
   |        |                    |
   +----> POL-E -> VR-X ---------+|
   |        |                   ||
   |        +--+                ||
   |           v                vv
   |  POL-F -> POL-B -> POL-Q -> VR-Q -> POL-P
   |                       |
   +----> POL-WC ----------+----> POL-W
```

The table and JSON are the precise AND-dependencies; the ASCII is an orientation
view. POL-W additionally requires POL-Q. Owner services may start independently;
full UI is never needed to resolve or enforce a run policy.

## First canary versus installer release

For the first same-Mission Forge -> EP -> Forge canary, implement and qualify
only the applicable effective-policy/provenance and authorization/assurance
seams. Existing bounded profiles can implement those semantics without a generic
administration UI. Do not add all of POL-F/POL-E/POL-W/VR-F as artificial umbrella
gates before a canary that does not exercise release publication.

For a production universal-installer composition that does exercise release
management, require VR-Q and POL-P plus its existing artifact/deployment proof.
A documentary promise or a matching version string cannot satisfy those gates.
Workspace UI, full discovery and cross-repo parallel scheduling are independent
capabilities, not hidden prerequisites introduced by policy administration.

## Integration with existing proposals

Forge #48 (observed `455b22a5`) owns the pending Living Mission Graph/cross-repo
DAG proposal; this policy sub-DAG does not supersede its F10/F11 or renumber it.
Forge #49, Workspace #14, Platform #17 and EP #100 retain their owning
implementation/review work. Their relevant target design must be reconciled
before merge; this increment does not approve those heads or implement their fixes.
EP #102 and Platform #16 remain separate dependency/artifact contract proposals.

Adopt executable programme-DAG changes only through explicit authorization
staleness reconciliation. Do not reset historical budgets, extend expiry or
turn these PLANNED documentary nodes into executable Missions.

## Closure proof for this documentation increment

Four linked PRs; owner/source matrix agrees; catalogue entries are source-pinned;
all new graph edges reference known nodes and the graph is acyclic; roadmaps link
to owning designs; only Markdown and documentary DAG JSON changed. Existing
runtime, workflows, package versions, tests and deployment are untouched.
