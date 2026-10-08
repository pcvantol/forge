# Explicit advice to unapproved Candidate — HTTP/CLI V1

Assignment L3-FORGE-ADVISORY-CANDIDATE-HANDOFF-V1-20261008, plan r39.
SOURCE_SLOT_JOIN=L1-L3-FORGE-RELEASE-SOURCE-HANDOFF-20261008;
FUTURE_CONSUMER_JOIN=L3-L4-ADVISORY-CANDIDATE-HANDOFF-V1-20261008.
L1 source release207/6055910178 and L3 ACK207/6058332838 precede source effects.
Base815932ceeaf4235a4971f5e1055b44082fa4dc9a /Forge2.8.1.
Normal capability MINOR2.9.0 under one assignment/event lineage.
State: SOURCE_IMPLEMENTED, owning convergence/protected/installed gates pending.
Earlier r38 and published2.8.1 artifacts/release-operation remain unchanged.

## Outcome and boundaries

An explicitly authorized consumer uses a genuine COMPLETE/CONFIRMED validated
Business/Architecture advice turn to save an immutable Candidate proposal,
preview it, explicitly confirm its exact revision/digest and register one
unapproved canonical Candidate. Reads and proposal save are providerless and do
not create a Candidate. Registration creates only the existing advisory
Recommendation PROPOSED→RECOMMENDED and Candidate, with durable correlation.
It calls no approve/allocate/admit/provider/dispatch service and changes no
workset. Both separate Business and Architecture decisions remain necessary;
existing intake refuses an unapproved Candidate. Advice stays applied:false.

Selected RC-FP text Candidate subset and necessary consumer authority only.
No general proposalengine, allocator/decisionstore, Vision/Portfolio/ADR/DAG
writes, delegated approvals, Mission start, EP dispatch, native proposal UI,
UX/attachments/export, full RC-FP/RC-FQ/F2/family or consumer completion.
Live model quality remains NOT_QUALIFIED; this handoff adds no model generation.
L4 native chat remains independently pinned Forge2.8.0/88f7560.

## Actual routes and separate authority

| Method | Route | Effect |
| --- | --- | --- |
| GET | /v1/advisory-candidates/capability | Exact grant scope and finite supported bounds |
| GET | /v1/advisory-candidates/{conversation_id}/source/{turn_id} | Own validated completed advice provenance/summary |
| POST | /v1/advisory-candidates/{conversation_id}/proposals | Save a user-authored immutable proposal revision |
| GET | /v1/advisory-candidates/{conversation_id}/proposals/{proposal_id}?revision=1 | Preview/original proposal and separately current registration |
| POST | /v1/advisory-candidates/{conversation_id}/proposals/{proposal_id}/registrations | Explicit Candidate-only canonical mutation |
| GET | /v1/advisory-candidates/{conversation_id}/proposals/{proposal_id}/registrations/{operation_id} | Durable pending/original receipt and current canonical readback |

[Closed machine contract](../../forge/api/advisory-candidate-v1.json).
OpenAPI/Postman/frozen catalogue retain all51 existing routes plus these6.
Old admin/advice/read/review/worklist/hold grants do not authorize this namespace.
The new grant cannot use the old namespaces or any approval/execution route.

Owner provision uses forge-advisory-candidate-grant issue with explicit
--data-root, --principal-id, --project-id, --repository-id, --conversation-id,
repeatable --proposal-id, --maximum-registrations, --expires-at and --token-file.
Use an owned private instance and output file; no token is printed. Revoke uses
--grant-id. Current installation operator and existing configured project/repo
are required. At most16 proposal IDs per grant,64 retained grants,64KiB private
store, max30-day expiry and1..8 registrations. The conversation must belong to
the same principal if already present. Capability grants access only to this
own conversation/source/proposal lineage; it does not revive an old advice
bearer's generation privilege. Current operator/grant/project/source ACL are
rechecked on mutations and operation reads. Revoked/expired grants deny.

Thin forge-advisory-candidate commands: capability, source, save, preview,
register and operation. All use the same application service with a private
--token-file; save/register require private --request-file. No admin fallback.

## Requests and immutable proposal provenance

Save body fields: contract_version, instance_id, project_id, repository_id,
conversation_id, proposal_id, turn_id, expected_revision (0 for new),
expected_conversation_revision, context_revision and fields.

Every structured field is explicitly supplied by the user: title, objective,
business_value, engineering_value, architectural_value, rationale, confidence,
scope, exclusions, acceptance_criteria, architecture_constraints, dependencies,
and the existing typed MissionEffectPolicy. No confidence/priority/criteria or
model-generated structure is inferred from free text. Substantive criteria are
required. Source stores turn/session/invocation/request/result/lens/context and
selected-source versions plus the validated advice summary. Field origins are
EXPLICIT_USER versus VALIDATED_ADVICE, visibly separated. Amendments create a
new immutable proposal_revision/digest; earlier revisions/registrations and
original advice remain intact. Private proposal files have64KiB capacity,
max64 logical proposals and8 revisions each. At capacity new admission denies
before save, while old preview/readback remains available.

READ_ONLY_ASSESSMENT/EVIDENCE_ONLY permits no write paths. Documentation/design
Git proposals require exact documentary file paths; they do not authorize
implementation. Exclusions and constraints are preserved in canonical Candidate
fields. The existing policy remains a proposed boundary awaiting decisions.

Registration body fields: contract_version, operation_id, instance_id,
project_id, repository_id, conversation_id, proposal_id, proposal_revision,
proposal_digest, expected_conversation_revision, context_revision, confirm:true.
No actor/role/approval flag from JSON constitutes authority. Natural-language
"yes" is not this typed confirmation. Proposal/source staleness denies new
effects. A replay of a completed original command returns its original receipt
and separately current status/subject digest/freshness; it does not relabel the
old receipt after amendment or canonical Candidate changes. A new-key alias
must still meet current preconditions and returns the same Candidate/receipt.

## Durable canonical effect and recovery

Canonical RecommendationLifecycleStore retains append-only intent rows and
unique logical proposal-revision registration rows in the existing Candidate
aggregate. Operation IDs are principal-scoped. One retained key consumes one
registration allowance; IDs/grant renewal/restart do not clear consumption.
The original proposal bound is checked against its retained creation-grant.
Maximum8 retained keys per principal and64 instance operation intents.

Intent commits before effect. The existing canonical recommendation creation,
non-approval RECOMMENDED transition, Candidate creation and immutable receipt
join one aggregate transaction. Nested canonical services do not commit partial
parents. A process killed before effect leaves one pending original operation;
recovery requires that same operation, never a fresh-ID bypass. A process killed
after effect/lost HTTP-body discovers the same committed Candidate and original
receipt. Duplicate requests preserve identity; changed same-ID payload conflicts.
A new operation key on the same registered proposal revision cannot create a
second Candidate. There is no direct SQL recovery/repair or history reset.

Current reads open the canonical database read-only without migration/schema
creation. Source validation uses actual persisted advice and current catalog
ACL. Canonical readback verifies original receipt/model/proposal correlation,
retains original Candidate/recommendation hashes, and separately reports current
Candidate document/hash/status and whether an allocation exists. No receipt is
manufactured from a client-provided Candidate or success flag.

Errors:401 credential unavailable;403 scope/ACL denied;404 unknown scoped
subject;400 malformed/unsupported request;409 stale/conflict/pending/budget/
capacity;503 source/provenance unavailable. Public diagnostics contain bounded
codes, never private reasoning, bearer tokens or real conversation text.

## Acceptance and full delivery gates

Actual HTTP matrix covers advice→proposal→Candidate, explicit amendment,
original/current separation, two scopes/principals, source ACL and grant expiry/
revoke, unsafe/foreign/stale requests with zero effect, providerless preview/CLI,
retained bounds/private input faults, concurrency, genuine SIGKILL before/after
canonical effect, lost response/fresh-process recovery without duplicate, and
real intake refusal without the two decisions. Qualification uses real product
HTTP/auth/advice/context/proposals/lifecycle/intent/storage/readback. Only external
model executable, OS identity and public repository transport are doubles;
no internal authority/service mock or seeded successful advice/approved Mission.
Disposable negative capacity/corrupt-input records are explicitly labelled.

Finish requires full owning tests/version/projection, per changed production
file strictly>80.2% executable coverage, mandatory independent exact-head
Quality/Security after owner convergence, required CI/protected implementation,
nonempty normal finalization and exact-final-main tracked-source wheel/noneditable
installed matrix/genuine revoked-positive control/cleanup/terminal register.
Existing FCI/read/serial/hold/advisory and Action-authority gates remain required.
TDE workflow completion and actual policy outcome remain separate; no suppression
or broad unrelated remediation. Source/preview, merge and installed qualification
are distinct states; this document asserts no future SHA or completion.

No live EP, paid model probe, personal Keychain, production CENTRAL/historical
instances, signing, real GitHub-target writes, public product release or user
instance installation. L1's immutable released bytes and L4's selected chat
scope/pin remain preserved. Future native Candidate UI needs separate selection.
