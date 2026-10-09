# Chat-first Mission ready — r42 working contract

Assignment `L3-CHAT-FIRST-MISSION-READY-V1-20261008`; JOIN
`L3-L4-CHAT-FIRST-MISSION-READY-V1-20261008`. Same sole L3 source writer.
r41 remains CLOSED. This is source development evidence, not a protected release,
installed qualification or complete native UX acceptance.

## Existing route reuse and bounded delta

| Existing owner | Reuse | Delta | Required proof |
| --- | --- | --- | --- |
| AdvisoryService / AdvisoryProvider | Actual scoped context, current provider policy, durable finite turn consumption | Typed concept output and immutable generated revision | Natural refinement/questions, malformed/late output, crash without regeneration |
| AdvisoryCandidateService / canonical lifecycle | Recommendation/Candidate lineage and immutable registration | Generated provenance separate from EXPLICIT_USER; deterministic identities | Exact promotion and restart/alias recovery |
| CandidateDecisionService / GovernedCandidateIntake | Actual G001 signer and separate canonical approvals | Frozen package and bounded durable compound intent | Solo confirmation, authority drift, torn stores, zero-Action Intake |
| Approved worklist / serial eligibility | Actual approved subjects, completion facts, holds and release | Scoped catalog and current dependency/readiness projection | Exact predecessor revisions, real blockers and supported positive release |

## Generated content and owner setup

`forge-chat-first-mission/v1` is defined in
`forge/mission_concept_contract.py`; HTTP schemas are in
`forge/api/mission-concepts-v1.json`. Model output contains only contract_version,
request_digest and definition. The definition carries title, objective,
business_value, expected_result, scope, exclusions, acceptance_criteria,
architecture_choices, risks, dependencies, dependency_reasons, questions,
change_summary, work_kind, components and possible_subresults. Closed finite bounds apply to every field.

Work kind follows the intended human effect: INVESTIGATE, DESIGN, BUILD,
DOCUMENT or UNDECIDED with meaningful questions. Dependencies require actual
scoped catalog references and substantive human reasons. IDs, signer, roles,
policies, technical ceilings, digests and approval status are never model fields.
An incomplete definition remains an unapproved concept. An explicit split request
can propose up to four human subresults (title, expected result and testable
criteria). These remain content suggestions, never child Mission/Action IDs or
bulk approval. Workspace may organize presentation groups using canonical object
references; semantic dependencies still require actual scoped canonical subjects.
Catalog labels describe the proposed work kind and never confer grants.

`forge-mission-concept-setup` configures finite supported profiles over an
existing genuinely scoped advisory grant and actual G001 primary operator.
Profiles are trusted ceilings, not permission to broaden the human objective.
Optional owner-configured components have human names/descriptions and finite
read/write paths strictly within the ceilings. The model selects existing names;
product code narrows the effect policy to those actual component bounds. Missing
component configuration/choice yields a meaningful question, never ceiling paths
as a fictional per-Mission default. Legacy profile records remain immutable and
readable; no allowance or grant is expanded by this change. Canonical Candidate
constraints bind every human IN SCOPE item, EXPECTED RESULT and selected trusted
COMPONENT description, so distinct scope cannot disappear downstream.
Aliases retain minimum prior Mission allowance. Advice and concept generation
share retained consumed budgets; confirmation never expands grants or budgets.
No technical field entry is required per Mission. Ordinary owner provisioning
remains a separate genuine configuration action.

## Implemented source HTTP routes

- `GET /v1/mission-concepts/capability`
- `POST /v1/mission-concepts/resolve`
- `GET /v1/mission-concepts/{conversation_id}/context`
- `POST /v1/mission-concepts/{conversation_id}/turns`
- `GET /v1/mission-concepts/{conversation_id}`
- `GET /v1/mission-concepts/{conversation_id}/turns/{turn_id}`
- `POST /v1/mission-concepts/{conversation_id}/turns/{turn_id}/cancel`
- `GET /v1/mission-concepts/{conversation_id}/package?revision=...`
- `POST /v1/mission-concepts/{conversation_id}/approve`
- `GET /v1/mission-concepts/{conversation_id}/operations/{operation_id}`
- `GET /v1/mission-concepts/catalog?cursor=0&limit=4&snapshot_revision=sha256:...`

The resolver accepts operation_id and Workspace conversation/draft references.
Workspace authenticates its own references before forwarding; Forge requires
current scoped principal/project/G001/setup. It atomically binds the pair to an
existing unused permitted conversation slot. Same/new operation keys and restart
preserve the pair. Existing unbound transcripts are not adopted or overwritten.
Capacity exhaustion denies resolution; no new grants, slots or resets are issued.
Forge conversation IDs have the general identifier grammar, independent of
Workspace's own 32-hex IDs.

A focused context read precedes explicit refinement. Transport bindings and
revisions are client-resolved fields, not user forms. Only explicit turns invoke
the production bounded tool-disabled provider. Concept transcripts preserve
source turn/context/invocation/result provenance and historical revisions.
Reads, preview, catalog, resolution and confirmation invoke no model.

## Frozen confirmation and genuine effects

The package binds full human definition, trusted technical planning/effects,
exact dependencies, source provenance and current signer/profile/bounds.
Confirmation submits contract_version, operation_id, revision, package_digest
and confirm=true after displaying that exact meaning. No generation follows
confirmation.

A durable intent precedes canonical effects. Existing services register one
Candidate, record distinct actual Business and Architecture decisions and admit
one genuine Mission with zero predefined Actions/Intents. Current source,
configuration, provider policy, subject and signer are checked at effect
boundaries. Generated provenance is VALIDATED_MODEL_PROPOSAL with
TRUSTED_OWNER_CONFIGURATION for planning; confidence is unknown. Historical
EXPLICIT_USER and older decision contracts retain their meaning.

Operation GET returns the immutable original frozen_package and actual
partial/complete effect lineage. Refinement after approval creates a new concept
revision; old effects remain immutable and source_fresh=false/SUPERSEDED prevents
new approval authority from their receipt. Same/new-key recovery does not create
duplicate Candidates, canonical decisions or Missions. An alias adds an operation
journal row, while the distinct registration key and consumed allowance remain
unchanged.

## Scoped catalog and current readiness

The catalog is AUTHORIZED_ADMITTED_CONCEPTS_ONLY, not a full portfolio. Exact
snapshots bind pagination. Promotion keeps one object_id and links its actual
Candidate/Mission. REQUIRES edges carry actual predecessor object/subject
references and human reasons. PROPOSED and APPROVED_DEFINITION describe approval
of the definition, not committed execution order. Cycles, foreign and unresolved
references fail closed. The integrity graph retains actual historical own
subjects even though selectable references exclude the current conversation;
A can be refined after B depends on its old approved subject. Parent/group placeholders carry no semantic authority.

Independent catalog growth does not stale an unchanged frozen subject. Current
owner/source bounds and actually referenced canonical subject revisions are
revalidated. Dependency changes, source revoke, profile/signer/provider drift or
new own definition revision still block the old package.

Approval, operation and catalog use the same existing approved-worklist
projection and real predecessor completion facts. They expose release,
activation-input, hold, eligibility and subject blockers. Physical resources are
NOT_OBSERVED and execution_ready=false until actual owning evidence exists.
READY_FOR_GOVERNED_ACTIVATION denotes only the supported logical next step;
it does not observe host resources, start a controller or dispatch to EP.

## Development evidence and remaining delivery

Actual source HTTP tests generate and promote two independent scoped subjects
with a reasoned A-to-B dependency; enforce real hold/release/missing-input
blockers; preserve context across promotion and unrelated catalog growth; and
keep historical meaning after later refinement.

`scripts/qualification/qualify_mission_concept_recovery.py` kills owned OS
processes before/after generation and around canonical registration, both
approval stores/receipts and Intake. Fresh processes recover original lineage.
Only external OS/model/repository boundaries use explicit deterministic
adapters; product auth/governance/storage/planning/Intake remain real. Additional
tests deny current signer drift between effects and reject a concurrent
confirmation without duplicates.

An actual positive test joins a chat-approved subject to the existing separately
approved exact workset, validates a genuinely owner-published repository snapshot
and existing progression policy, and arms the workset through its owning control
service. Operation and catalog both report READY_FOR_GOVERNED_ACTIVATION; hold
restores APPROVED_WAITING with its actual blocker. Two real workset decisions are
additional to the two Candidate decisions. Resources remain unobserved, and no
controller, Action, Mission start or EP submission occurs.

Rejected malformed/foreign/authority-injecting model outputs preserve the exact
previously approved definition/package; a failed attempt is not a semantic
successor. The frozen accepted turn revision is distinct from later transport
ledger revisions. Catalog canonical_history retains actual prior Candidate/Mission
references on the same card; source_definition_revision binds an edge to its
historical source subject after refinement. subject_current describes that
canonical Candidate's bytes, not approval of the latest draft. Allocation without
a Mission document is real partial lineage/PENDING and recovers without repair.

Full owning validation and strict per-file coverage, whole exact-head
independent Quality/Security, protected implementation, nonempty finalization,
exact-final-main noneditable qualification and actual CI/TDE readback. L4 owns
final installed integration, genuine packaged GUI clicks and independent UX
acceptance. Existing development subsets and source examples do not satisfy
those terminal gates. No live EP environment, signing, start or paid probe is
part of this work.

Ordinary CI now includes the exact-wheel noneditable selected matrix and a real
revoked-grant positive failure control via
`scripts/qualification/qualify_installed_mission_concepts.py`. Qualification binds
source/tree/wheel/schema bytes and owns isolated test home/scratch/config cleanup.
This integration is source WIP until its actual installed and hosted gates pass.

## Independent review and bounded repair lineage

Exact head05a4a5a received whole-scope Security PASS and Quality FAIL. Quality's
human-scope loss and filtered A→B→refine-A graph counterexamples are preserved in
separate private receipts; that head is not deliverable. Repair round1 binds
human scope/results to the real canonical Mission, selects actual narrower
component bounds, preserves historical graph nodes/references, and tests genuine
approval/Intake/downstream planner input. The real allocation-to-Mission crash
boundary now returns PENDING before same-intent recovery. Old receipts, wheel and
review consumption remain preserved; fresh whole validation, exact-wheel evidence
and both independent exact-head reviews are required for the repaired candidate.


## Protected implementation and nonempty source finalization

Implementation PR265 is protected merged at
`6963099cdc5623c011436ff8cb7f18899487fc78`, tree
`d5c2f1be0e386473bcc9ad177123b1c19dde4950`, after required CI37895872247
SUCCESS and exact481b2f6 whole-scope Quality/Security PASS. The repository
permits only squash merge; original branch commits/reviews/receipts remain
preserved. No admin bypass, direct main push, second writer or budget reset.

Fresh actual noneditable implementation-main qualification records22PASS and
its actual revoked-positive-grant failure control, exact source/tree/schema/wheel
payload verification and owned cleanup. The selected completion JSON in
`docs/qualification/forge-chat-first-mission-selected-completion-2026-10-09.json`
binds those receipts and the retained review/repair lineage. Normal NO_BUMP
source-finalization shares the original event lineage and retains version2.11.0.

This source finalization is nonempty and reviewable. Exact-final-main producer,
hosted main CI/TDE readback, L4 protected integration, real packaged GUI clicks
and independent shared UX acceptance remain required external post-merge gates.
The completion JSON intentionally does not invent its own future final SHA.
TDE workflow success is separate from its actual observe-mode policyFAIL and
repositoryqualificationFAILED; no policyPASS is claimed.
