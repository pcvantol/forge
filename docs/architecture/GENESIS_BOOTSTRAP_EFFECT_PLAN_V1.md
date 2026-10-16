# Genesis bootstrap effect plan V1 — selected pre-admission subset

R56/plan1, L3-GENESIS-BOOTSTRAP-EFFECT-PLAN-V1-20261016.
JOIN L2-L3-GENESIS-LOCAL-BOOTSTRAP-V1-20261016. Forge2.22.0/schema46 candidate.
This is the early concrete contract and pure frozen-plan implementation, not
qualified HTTP/decision delivery. R55 and predecessors remain CLOSED.

## Exact outcome and ownership

A retained R52 pb-render/1.0 authority/GENESIS/LOCAL_POSIX proposal with the
original portable-docs/1.0.0 document bytes becomes a finite immutable
CREATE_GENESIS_LOCAL/1.0 plan, then a separately authorized human effect decision.
R50 rendering and R52/R54 services/stores are reused. No target writer, EP apply
coordinator, network/scan/provider/Action/Mission or automatic EP grant issuance.
L2 owns actual placement, absent-target checks, identity reservation, execution,
validation, Git commit and committed B8R registration. A Forge plan or decision
confers no EP execution authority or READY status.

All plans remain EP_ADMISSION_REQUIRED, identity PROPOSED_NOT_RESERVED,
reservation NOT_REQUESTED, target absence NOT_OBSERVED_BY_FORGE. Proposed
IDs are copied exactly from the original document proposal. Changed IDs/profile
require a new source proposal and its own content decisions. A changed target,
effect/binding/source decision revision creates a new linked plan; no old effect
approval is inherited. Physical paths, reservation and authenticated execution
rights remain EP-owned. No portable bytes are rewritten to fit a target.

## Concrete JOIN mapping and synthetic fixed files

| Original owning value | Frozen Forge value | EP meaning / missing evidence |
| --- | --- | --- |
| R52 plan/result/record + R54 exact subject | source_subject plus exact input/result/record/manifest digests | Existing immutable document proposal, not resource reservation |
| R54 actual original history / revision | original_content_decisions and content_history_digest | Positive effect decision needs applicable BUSINESS AND ARCHITECTURE approvals over this exact subject |
| R50 catalog common_paths/authority_paths/asset pins | Exact37-file authority Genesis set, original UTF8/content/size/mode0644/afterSHA | No caller-added file, hook, command or second renderer |
| Original bootstrap manifest | Same manifest bytes and semantic manifest_digest; separate manifest_file_sha256 | Existing self-reference exclusion retained, no recursive hash or regenerated manifest |
| Original declaration | Same project.id / project.authority_repository_id / repository.id / authority role | PROPOSED IDs, EP must reserve these same IDs before effects and register only after committed readback |
| Owner-supplied EP instance + placement_ref + target_ref | Opaque target object with required_before ABSENT | No absolute path, actual absence proof, reservation, admission or attachment claim |
| Original scripts/validate.sh | Literal bash scripts/validate.sh, mode0644, exact script SHA | Invoke through bash; never invent executable mode |
| Pinned original validate.py/catalog/renderer | Original asset SHA, Python3.14, ISOLATED_NO_SITE_PACKAGES | EP must independently trust/qualify its external validation entrypoint; bundle self-hash is insufficient |
| Finite selected effect set | CREATE_NEW_TARGET, INITIALIZE_LOCAL_GIT, WRITE_EXACT_MANIFEST_FILES, RUN_EXTERNALLY_PINNED_VALIDATION, CREATE_LOCAL_COMMIT, REGISTER_COMMITTED_AUTHORITY_ATTACHMENT | Requested exact local effects, not a grant, generic command DSL or remote plan |
| Original product.open_questions | Unchanged visible questions; explicit blocking subset | Required unanswered effect questions block effect approval; future engineering choices do not invent completeness |
| Explicit expires_at / fixed limits / retention | Exact frozen expiry, proposed300s max execution, retain original evidence/no automatic rollback | EP independently validates current authority and its own finite constraints before effects |

Synthetic files under examples/genesis-bootstrap: synthetic-original-frozen-bundle.json
and synthetic-pre-admission-plan.json. Both contain original unmodified R50
example bytes; no human approvals, actual EP identity or reservation. The fixed
example expiry is test data, never an active grant. The full plan is currently a
pure source fixture; normal product requests will reference owning R52 records,
not accept a client-uploaded bundle/approved JSON.

## Selected own HTTP / CLI contract being implemented

Contract forge-genesis-bootstrap-effect-plan/v1; separate explicit finite
GENESIS_BOOTSTRAP_EFFECT_ONLY/1.0 owner grants. Existing PREPARE/READ/content
DECIDE/peer/admin grants do not gain effect rights. DECIDE_EFFECT will bind the
actual installed human operator and current existing OWNER_PROGRAMME_AUTHORIZATION
capability, plus exact finite plan ID/digest and selected source/target scope.
This does not create a new canonical role or EP capability. No chat/actorheader
or general read token acts as a human decision.

Selected routes (implementation in progress, not already shipped):

- GET /v1/genesis-bootstrap/capability
- POST /v1/genesis-bootstrap/plans
- GET /v1/genesis-bootstrap/plans/{plan_id}?dossier_id=...
- GET /v1/genesis-bootstrap/intents/{operation_id}?dossier_id=...
- POST /v1/genesis-bootstrap/decisions
- GET /v1/genesis-bootstrap/decisions/{decision_id}?dossier_id=...
- GET /v1/genesis-bootstrap/decision-intents/{operation_id}?dossier_id=...

Bearer plus X-Forge-Bootstrap-Audience. Ordinary local CLI parity will share
these owning services and existing private publication/storage primitives.
There is no EP route in this interface. L2 publishes its own actual routes,
headers, scope and receipt; no historical design endpoint is presumed live.

A preview can show missing content conditions. Positive effect approval needs
both original valid content roles, an exact unchanged plan and a currently
human-authorized separate finite effect decision. Historical decision records
remain facts; current applicability is recomputed separately on read/decision
and publication, including expiry/revoke/source/CAS/supersession. No duplicate
document reapproval is required for an unchanged valid original source.

Durable original intents, exact request digests, append-only predecessor/CAS,
finite capacity and initialized-store-loss refusal remain mandatory. Current
scope/source before read/commit/bounded publication, no lock during client wait.
Lost replies and separate Server OS restart recover original records only.
Private bytes, credentials and actual host paths are not public evidence.

## Delivery boundary

Initial six pure source/bundle tests are not installed acceptance. The required
first installed own HTTP chain must include actual retained R52 proposals,
separate synthetic R54 role decisions and a real separate finite synthetic effect
decision; no EP effect is needed or simulated as product evidence. Independent
Quality/Security, required regression/coverage/CI, normal protected implementation,
own nonempty finalization/protected merge and NEW exact-final-main installed
HTTP/restart/readback/non-effect/cleanup remain OPEN. Full PB-F0/PB-F2/HOB,
PB-F3 apply coordination, actual Genesis readiness, adoption/Managed/promotion
remain open. L4-plan107/progresspin and R55 EP2.3.121 inspection pin unchanged.
No general peer ACK, native UI, signing or installer wait; no automatic successor.
