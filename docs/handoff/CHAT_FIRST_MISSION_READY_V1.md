# Chat-first Mission ready — r42 working contract

Assignment `L3-CHAT-FIRST-MISSION-READY-V1-20261008`; JOIN
`L3-L4-CHAT-FIRST-MISSION-READY-V1-20261008`.
This is an implementation checkpoint, not an available HTTP capability or installed proof.
Existing textual advice and explicit-user Candidate contracts retain their meaning.

## Existing route reuse and bounded delta

| Existing owner | Reuse | Required delta | Qualification |
| --- | --- | --- | --- |
| AdvisoryService / AdvisoryProvider | Actual authorized project/context, current provider policy, durable turn intent and finite consumption | Separate typed concept output and immutable revision bound to source turn | Natural prompt/refinement/questions, malformed/late output, crash without regeneration |
| AdvisoryCandidateService / canonical lifecycle | Stable recommendation/Candidate lineage and immutable registration | Generated-content provenance separate from EXPLICIT_USER; deterministic internal identities | Exact promotion, restart/alias duplicates, no authority from model text |
| CandidateDecisionService / GovernedCandidateIntake | Current G001 signer, real separate canonical Business/Architecture decisions | Frozen complete package and durable bounded composite intent with effect-boundary revalidation | Single Solo confirmation, revocation between steps, torn writes, actual zero-Action intake |
| Approved worklist / serial eligibility | Actual approved subject, hold/dependency/release/provider conditions | Project/principal-bound catalog, stable concept-to-Mission correlation and typed edges | Scoped pagination, cycles/foreign references, blocked vs ready current readback |

## First concrete content schema

`forge/mission_concept_contract.py` defines `forge-chat-first-mission/v1`.
The external generation result has only `contract_version`, `request_digest`,
and `definition`. Definition carries title, objective, business_value,
expected_result, scope, exclusions, acceptance_criteria, architecture_choices,
risks, dependencies, questions and change_summary. All fields are closed/bounded.
Dependencies resolve against the actual authorized catalog. A missing substantive
scope/criterion requires a meaningful question. This content validator alone
makes no planning, authority, approval or readiness claim.

Model output cannot supply IDs, signer, roles, effect policy, approved status,
planning evidence or mechanical digests. Trusted configuration and existing
services must resolve those separately, with unresolved content/configuration
shown as owning gaps. The client displays the full frozen human meaning before
explicit confirmation; previews/catalog/confirmation make zero provider calls.

## HTTP integration status

Pending implementation: supported owner setup with finite project/draft bounds,
refine operation, immutable definition detail, authorized catalog snapshot,
exact frozen approval package and durable composite operation current readback.
No endpoint name or shape in this checkpoint is an advertised available route.
A concrete versioned API schema will supersede this status before L4 integration.

## Tested source checkpoint: concept routes only

The local source now implements, under the existing explicitly scoped advisory
credential and its retained shared principal/provider budgets:

- `GET /v1/mission-concepts/capability`
- `POST /v1/mission-concepts/{conversation_id}/turns`
- `GET /v1/mission-concepts/{conversation_id}`
- `GET /v1/mission-concepts/{conversation_id}/turns/{turn_id}`
- `POST /v1/mission-concepts/{conversation_id}/turns/{turn_id}/cancel`
- `GET /v1/mission-concepts/catalog?cursor=0&limit=4&snapshot_revision=sha256:...`

Refine reuses the existing bounded turn request fields under the new contract:
contract_version, turn_id, instance_id, project_id, repository_id,
conversation_id, advisor_kind, objective, expected_revision, context_revision,
selected_sources. These are client-resolved context/operation fields, never
technical form input. Source currentness and grant/provider authority remain
checked by the real owning service. Generation is persisted in distinct immutable
concept transcripts while the existing shared retained-principal budget counts
both advice and concept turns. Replay reuses the original admitted result.

The catalog is explicitly an authorized admitted-concepts subset, not a full
portfolio. Snapshot revisions bind pagination; foreign principal concepts are
absent. Object IDs correlate a principal/project/conversation concept across its
refinements. Items include the human definition/digest, actual source turn and
conversation/context revisions. Candidate/Mission links remain null, state is
CONCEPT and approval_supported is false until the real owning promotion route
exists. No dependency edges are claimed before authorized canonical binding.

Remaining mandatory producer work: finite owner setup/project-draft permissions,
trusted planning derivation, typed dependency semantics/reason/proposed-versus-
committed validation, complete frozen approval package with human consequences,
substantive questions/current blockers, canonical registration/provenance,
durable composite separate real approvals and zero-Action governed intake,
complete negative/crash/integration/installed/coverage/CI assurance and protected
lifecycle. L4 must not enable Approve from this checkpoint.

## Current r42 source: one exact approval and actual canonical Intake

Normal capability source version is being advanced to 2.11.0 under the same
r42 operation; this is not publication or an installed delivery.

`work_kind` is generated from the intended human effect (INVESTIGATE, DESIGN,
BUILD, DOCUMENT, or UNDECIDED with a meaningful question). Real owner setup
supplies closed finite project profiles. The model cannot supply policy, role,
signer, Action ceilings or human gates. `forge-mission-concept-setup` supports
one owner configuration over an existing genuinely scoped advisory credential
bound to the actual G001 primary operator. No general admin proxy is provided.
Different aliases retain the minimum prior Mission allowance and the actual
shared generation/registration/decision consumption. No configuration changes
or extra capability issuance occur during a normal Mission confirmation.

Actual additional source routes:

- `GET /v1/mission-concepts/{conversation_id}/package?revision=...`
- `POST /v1/mission-concepts/{conversation_id}/approve`
- `GET /v1/mission-concepts/{conversation_id}/operations/{operation_id}`

Approve's closed request contains contract_version, operation_id, revision,
package_digest and explicit confirm. These are trusted client transport fields;
the user approves the exact full human card, not an internal field editor.
The package freezes the complete definition, true turn/session/invocation/result
provenance, actual scope/revisions, deterministic Candidate subject, canonical
Mission preview/planning and current owner profile/signer/bounds. Effects,
exclusions, risks and human gates are visible consequences of the same package.

The source compound route journals that complete intent before effects, reuses
the actual canonical Candidate store, records distinct actual Business and
Architecture decisions and invokes the existing governed zero-Action Intake.
Source/context/provider/config/signer/Candidate revision checks run at real
boundaries. Historical EXPLICIT_USER remains unchanged; generated origin is
VALIDATED_MODEL_PROPOSAL with TRUSTED_OWNER_CONFIGURATION for planning and
unknown confidence (never an invented numeric score). Legacy r40 decision grants
cannot admit this new versioned source as an old r39 Candidate.

Actual current qualification chain exercises meaningful question/refinement,
frozen package, one confirmation, two canonical decisions, one real allocation,
zero Actions/Intents/dispatcher start, same/new-key replay, canonical catalog
promotion on the same object, and post-approval refinement preserving prior
records. Permission/actor/confirmation/digest denials have no effects; actual
grant revoke denies further requests. Modelcalls occur only on explicit turns.

Operation GET returns `frozen_package` from the immutable original intent even
when the latest concept revision changes. Current authority is still required;
COMPLETE describes the original real effects. `source_fresh=false` and
SUPERSEDED describe a later definition; historical package bytes confer no
new approval or READY authority. Prepare/Approve reject an obsolete revision.

The present source route reports APPROVED_WAITING pending the owning worklist
release boundary. True dependency semantics and current eligibility/hold/release/
provider/resource integration remain required; a fixed waiting label is not
final readiness delivery. Full negative crash/concurrency/scope matrix,
whole validation/coverage, independent reviews, protected lifecycle, exact-main
noneditable producer and L4 native integration/UX acceptance remain OPEN.
