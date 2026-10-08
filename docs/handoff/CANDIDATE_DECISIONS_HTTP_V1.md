# Separate Candidate Business and Architecture decisions — HTTP/CLI V1

Assignment L3-FORGE-CANDIDATE-DECISIONS-HTTP-V1-20261008 /r40; same sole
Forge writer. Base8923be501c4b83fb102d88420eda36160f759a5a /2.9.0 and closed
r39 evidence remain intact. New capability uses normal MINOR2.10.0; normal
source finalization shares this event lineage. Implementation/qualification
is in progress; this document does not assert future installed or protected PASS.

## Actual route → authority → service → canonical evidence

| HTTP route | Authority and product path | Actual result |
| --- | --- | --- |
| GET /v1/candidate-decisions/capability | Separate owner CandidateDecisionGrant, explicit READ | Exact Candidate/revision/project scope and selected permissions |
| GET /v1/candidate-decisions/{candidate_id} | Current READ grant, operator/project/source ACL | Canonical subject and separate decisions, applicability, allowed operations, missing user planning inputs |
| POST /v1/candidate-decisions/{candidate_id}/business | Explicit BUSINESS + READ, exact G001 signer/Solo assigned Business role | GovernedCandidateIntake.approve_business → BusinessWorkspace → canonical Runtime decision and lifecycle transition/receipt |
| POST /v1/candidate-decisions/{candidate_id}/architecture | Explicit ARCHITECTURE + READ, same exact signer/Solo Architect role and actual matching Business decision | Supplied ArchitectureMission/ArchitecturePlanningEvidence → existing approve_architecture and approved_envelope validation, without admit |
| GET /v1/candidate-decisions/{candidate_id}/operations/{operation_id} | Current READ and original decision-kind permission, principal-scoped operation | PENDING or original immutable receipt, separately current applicability |

[Closed machine contract](../../forge/api/candidate-decisions-v1.json), OpenAPI,
Postman and frozen62-route catalogue preserve all57 existing routes. Old advice,
Candidate-registration, review, worklist, status and administrator tokens do not
authorize this namespace. Decision tokens cannot use those namespaces, provider
commands, Mission admin, intake/start or dispatch. There is no admin fallback.

## Provisioning and the actual signer boundary

Owner identity/inspect CLI returns actual nonsecret signer and Candidate revisions
without credentials or mutation. Canonical approval subject_revision uses the existing
UTF-8 canonical_digest; source_registration_subject_revision preserves r39 ASCII JSON
hashing. These may differ for Dutch/non-ASCII text; original receipts/pins stay intact.

Owner CLI forge-candidate-decision-grant uses the existing configured project,
canonical registered Candidate aggregate, current G001 operator and existing
resolved governance profile. Issue requires explicit principal/project/repository,
profile, repeatable permission, Candidate-ID=sha256:revision, maximum-decisions,
finite expiry and private token-file. Revoke takes an exact grant ID. Token bytes
never print. At most64 retained grants,64KiB private store,16 exact Candidate
bindings,1..8 decisions and30-day validity. READ is explicitly selected; a
READ-only grant gains no decision right. Each corresponding decision permission
is selected independently. Token renewal and operation aliases do not clear
retained distinct-decision consumption or history.

The installed G001 model signs as its currently bound OS operator. A decision
principal must be that exact canonical16-character operator fingerprint; issue
captures actual installation/operator/binding version and authorizes the
existing assigned role and capability. Under supported Solo, both roles already
belong to primary_operator, but Business and Architecture remain two commands
and two canonical decision identities. A new token cannot create a role or
impersonate a different remote person. READ-only principals may be distinct,
within their explicit exact Candidate set and current source ACL.

Separate actual operator principals are supported in their separately bound
isolated instances. An arbitrary remote person's ID, mismatching G001 signer,
or Duo/multi-human abstract role assignment is refused for writes. This producer
does not introduce multi-user identity delegation/IAM or claim a two-person Duo
approval. These incompatible combinations require a separately selected genuine
identity binding before support, rather than using the local operator as someone
else. Current grant/profile/operator/capability/project/source/subject checks run
again at each real effect and protected read boundary. Operator revocation denies
remaining publication steps without deleting any earlier genuine decision.

## Exact subject, user inputs and preparation

Initial admitted population is project-/repository-bound Candidates registered
by the qualified r39 advice → explicit user proposal → Candidate route. Original
registration receipts are reconstructed against the actual immutable intent,
proposal and recommendation; legacy project ownership is not inferred.
Commands require the granted exact current original Candidate digest. Changed
subjects cannot be silently reapproved. Historical operation reads preserve the
original receipt and expose only current digest/status/applicability when a
changed subject falls outside the grant; changed Candidate content is withheld.
Advice source remains COMPLETE/CONFIRMED and validated, with current source ACL
and context; no additional provider invocation is permitted.

Both commands have closed fields contract_version, operation_id, instance_id,
project_id, repository_id, candidate_id, subject_revision, kind, rationale,
confirm:true. BUSINESS adds explicitly chosen human_gates. ARCHITECTURE adds
actual business_decision_id/business_decision_digest, complete mission_preview
and planning. Actor/role/success flags from request JSON are rejected.

Preparation deterministically projects existing Candidate/recommendation fields
and the expected MISSION-PREVIEW identity. It is not a persisted Mission or
approval. Technical assumptions, capabilities/disciplines, risks, exact human
gates, context bounds and complete typed planning remain explicit user inputs;
none are invented from advice prose. Explicit empty dependencies are valid;
existing typed planning/readiness checks retain that declared absence rather
than requiring a fabricated dependency merely to obtain approval. Source/project/repository, scope, criteria,
constraints, dependencies, effect policy, all optional criterion contracts and
planning/evidence digests must match. Business must actually be published before
Architecture. Gates and planning are validated before any new canonical approval.
Existing READ_ONLY/documentary/design effect exclusions remain intact; no implicit
implementation authority or third UX approval is introduced.

Same-service CLI forge-candidate-decision provides capability, prepare, business,
architecture and operation using a private token file and, for writes, a private
request file. It follows the same authority and effect boundaries as HTTP.

## Durable cross-store publication and original/current evidence

Immutable principal/operation/decision-kind/Candidate-version/payload intents
commit before effects, binding the original profile, signer, source and applicable
Business/planning identities. Existing stable decision_ids are preserved. There
is no parallel governor, allocator, planner or decision truth.

Canonical Runtime governance evidence commits through the existing Workspace
service first. The existing Candidate lifecycle transition and derived original
receipt publish together in one aggregate transaction. Thus a kill before effect
or between stores leaves PENDING, and approved_envelope cannot accept that partial
decision as complete. Recovery uses the original operation, rechecks current
authority and reuses any genuinely committed canonical decision before finishing
the original publication. It does not delete signatures/history or repair SQL.
After publication a lost body/restart recovers the same original receipt.

Same-key changed payload conflicts. A fresh key for a pending decision cannot
bypass the original operation. A completed same-content alias retains the same
decision/receipt and consumes no second distinct decision; foreign principal or
changed content cannot adopt it. At most64 retained operation intents and8 distinct
decisions per principal remain bounded across grants/processes. Real canonical
decision, lifecycle evidence, signer and payload joins reconstruct the receipt;
HTTP acceptance or status text alone is insufficient. Original receipt is
separate from current Candidate, source freshness, status and applicability.

## Qualification and finish line

Real product paths: installed HTTP/CLI/auth, G001 roles/operator/governance,
genuine advice/r39 registration, new grants/intents, existing Workspace decisions,
lifecycle evidence/readbacks and approved_envelope/intake validation. Only external
model executable, OS identity and public repository transport are deterministic
doubles. Successful advice/approved Candidate/Mission records are not seeded.

The integrated11-group matrix includes two separate positive decisions; different
actual operators/instances and READ principals; namespace/role/project/subject
denials; expired/revoked grant and actual operator revocation; planning/gates and
missing-approval refusal; source/subject drift; pure reads/private CLI parity;
same/new-key/conflict/retained allowances/capacity/immutable history; actual owned
SIGKILL before/between/after both decisions, lost HTTP body and new OS processes;
true concurrent commands; and a positive grant subsequently revoked to prove
the independent negative detector. No admit, Mission-ID allocation or execution
occurs. Canonical decision counts are0/1/2 as appropriate; Mission/Action/EP/workset
and post-fixture provider counts remain unchanged.

Full owning Python3.14 validation, changed production coverage strictly>80.2%,
all historical installed gates plus new decisions/control, mandatory independent
whole-slice exact-head Quality and Security, protected checks/merge, nonempty normal
source finalization and exact-final-main tracked-source/noneditable installed
proof, main-CI, actual readbacks and owned cleanup are required before terminal
PRODUCER_QUALIFIED. Actual TDE policy outcome remains separate from workflow success.
This is selected RC-FP decision routing and necessary consumer authority only,
not full RC-FP/FQ/F2/node/family completion, live user approval, provider advice
quality, native UI, public product release or operational user installation.

FUTURE_CONSUMER_JOIN=L3-L4-CANDIDATE-DECISIONS-V1-20261008 carries an early preview
and later the actual qualified producer handoff. L4's selected native registration
remains independently pinned Forge2.9.0/8923be50, with no approval buttons, wait or
automatic upgrade. Previous histories, consumer pins, primary checkouts, published
2.8.1 operation and consumed budgets remain intact. No automatic next assignment.


## Protected implementation and normal source finalization

[PR261](https://github.com/pcvantol/forge/pull/261) merged at `f2e5dc04be07dcaea56773bcd0c89340c44df8f2` /2.10.0.
[Immutable selected producer proof](../qualification/candidate-decisions-selected-completion-2026-10-08.json)
records independent exact-candidate Quality/Security, full1308-test validation,
per-file coverage and exact implementation-main tracked-source noneditable
installed11-group decisions matrix plus genuine revoked-positive control and owned cleanup.
Normal NO_BUMP2.10.0 finalization shares the original assignment/event lineage.
Finalization review/required CI/protected merge and exact-final-main installed,
main CI, current readback and terminal register are subsequent gates.
L4 native Candidate registration remains pinned2.9.0/8923be50; this does not qualify a native Candidate decision
consumer or full RC-FP/FQ/F2 family. No public release or operational install.

The candidate TDE observation timed out before assessment because it ran the full
1308-test suite twice. Finalization uses the existing standard validate entrypoint
once with coverage, retaining compilation, every test, version, projection, JSON
and whitespace checks, then emits XML for the unchanged published TDE runtime.
The 15-minute limit, observe mode, TDE policy and protected checks stay unchanged.
Cancellation is not an assessment policy decision.
