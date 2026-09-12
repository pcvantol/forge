# Role-aware conversations V1 — Forge services

## Status, scope and existing authority

Increment: `ROLE_AWARE_CONVERSATIONS_V1`; contract target version `1`.
This is a documentation/design increment, canonical only after its owning
protected merge. All new runtime and integration qualification remains PLANNED.
It does not implement chat, select a model, create a Mission, invoke a provider,
change credentials, grant approval or change an installed service.

The existing [product lifecycle](product-model.md),
[productization reconciliation](FORGE_PRODUCTIZATION_RECONCILIATION.md),
[decision contract](FORGE_V1_PRODUCTIZATION_DECISION_CONTRACT.md),
[Business Advisor](business-workspace.md),
[Architecture Advisor](architecture-workspace.md) and
[AI Architect Session](ai-architect-session.md) are the foundation, not replaced
engines. This design specifies their multi-turn product experience and introduces
UX Advisor as a target advice capability, not an implemented role enum or a new
approval authority. Earlier Forge Studio presentation wording remains superseded.

Source review: Forge `e7633814d4c1bc8ad1e4b25435ab9f064f0438c9` and Workspace
`f220f61ce214416287d6c696d63642dbe0e7d2a7`, observed 2026-09-12. These pins are
historical design inputs, not live peer-readiness or installed-runtime evidence.
The coordinated [Workspace UX contract](https://github.com/pcvantol/workspace/blob/main/docs/ROLE_AWARE_CONVERSATIONS_V1.md)
and [Forge delivery plan](../roadmap/ROLE_AWARE_CONVERSATIONS_V1.md) have separate
owners. A missing/unmerged peer document means pending coordination, not delivery.

## Product decision: one conversation, three advice modes

A project has multiple named conversations, each with its own objective and
explicit context. A conversation is not limited to an existing Mission: Vision,
Portfolio, a Candidate, a design artifact, a roadmap question or an assessment
can be its focus. The initial mode is chosen explicitly or shown as a suggested
mode for confirmation; an unexplained routing classifier does not choose authority.

Each submitted turn records `advisor_kind = BUSINESS | ARCHITECTURE | UX`.
These are conversation lenses, NOT authorization roles. Changing lens starts a
new bounded reasoning session within the same conversation; it retains links to
previous turns, artifacts, unresolved questions and decisions. Historical turns
keep their original lens and context. No three independent copies of project
truth or approval history are created.

One turn uses one advisor by default. Another advisor may be suggested; invoking
it is a visible bounded request, not a silent multi-agent fan-out. Read/explain
views and reopening conversations never generate AI output by themselves.
Business -> UX -> Architecture is a possible journey, not a mandatory lifecycle.
Existing Business and Architecture approvals remain separate. No mandatory UX
gate is added to every Mission, and mode selection never adds operator capabilities.

## Advisor responsibilities and reviewable results

| Advice mode | Questions and context | Results that may be proposed | Boundary |
| --- | --- | --- | --- |
| Business Advisor | What problem/outcome matters; for whom; value, priorities, assumptions, scope, constraints, feasibility evidence and success measures; Vision/Portfolio/Candidates | Clarifications, alternatives, business rationale, Vision/Portfolio changes, Candidate drafts and priority/roadmap proposals | Does not approve Architecture, invent market evidence or commit engineering work. |
| Architecture Advisor | How the intended result fits architecture; technical feasibility, dependencies, contracts, risks, acceptance criteria, existing assets and current repository evidence | Architecture findings, options/ADRs, design constraints, dependency changes, refinement and engineering-ready Mission proposals | Does not change business value/priority or approve its own proposal. |
| UX Advisor | User goals, journeys, information architecture, interaction states, accessibility, content/localization, design-system consistency and review evidence | User flows, wireframe/design specifications, copy variants, accessibility findings, prototype/review artifact proposals and UX acceptance criteria | Does not fabricate user research or grant business/architecture/execution approval. |

UX advice consumes available authorized screenshots/design assets and clearly
separates observed behavior, user-supplied claims and hypothetical alternatives.
Visual generation, external design services, interactive prototype execution and
new file types require separately qualified capabilities and cost/data policy.
Textual specifications are a sufficient initial slice; this design activates no
image provider, browser tool or Figma integration. Unsupported operations are
visible, never silently replaced with an unqualified tool.

Business decisions still belong to Business Owner; Architecture decisions to
the assigned Platform Architect. A project may have an already-governed
artifact-specific human UX review obligation. Show and route that existing
obligation rather than creating a third universal approval stage or granting a
new role here. Under Solo, the same person may perform the existing distinct
Business and Architecture decisions with separate attributable receipts.

## Ownership and durable records

| Record or operation | Owner and invariant |
| --- | --- |
| Conversation/navigation, title, selected view, unsent draft, user preferences | Workspace Server/Client; not Forge product or approval authority. |
| Submitted turn and reasoning session | Forge owns admitted objective/context/provider/result/proposal provenance; Workspace retains its presentation record and canonical session references, not an independently editable provider history. |
| Messages | Unsent text is a clearly labelled Workspace draft. Admitted turns and accepted outputs are retained with Forge session provenance under explicit retention policy. Reconnect projects those records; drafts are not reported as submitted. |
| Product context, refinement/proposal and decision evidence | Forge owning application services; repository representations remain versioned evidence, not chat authority. |
| Target repository changes and execution receipts | EP through normal admitted Action contracts; no conversational filesystem writer. |
| Runtime settings and local service health | Forge Server Console; no product-authoring conversation replacement. |

The conversation ID correlates, but never grants access. `conversation_id`,
`turn_id`, `session_id`, `proposal_id`, `artifact_revision_id` and `decision_id`
are distinct; none allocates `mission_id`, `action_id` or an EP submission.

A target `ConversationTurnRequest` carries contract version, project and
conversation identity, client turn/idempotency key, authenticated actor context,
advisor kind, objective, selected focus IDs, expected revisions, attachment
references and bounded provider-policy reference. Forge resolves authority from
the authenticated principal, not from client-declared roles.

A `ReasoningSession` records admitted request digest, context snapshot/digest,
source identities/revisions/freshness, advisor/profile version, invocation
identity/state, timestamps, result references and supported usage observations.
Requested and observed provider/model/effort are distinct; absent observations
remain NOT_REPORTED. Store auditable explanations and evidence, not private
chain-of-thought or bearer credentials.

## Context, continuity and access

Context is project-scoped and permission-filtered before retrieval, generation,
readback or export. It can include approved Vision/Portfolio, roadmap/DAG,
architecture, Candidate/Mission state, selected repository revisions, canonical
EP evidence references, design-system assets and deliberately selected prior
conversation material. Source access is rechecked on later retrieval; changing
mode does not widen visibility or pull in another project's private conversation.

The user sees included/excluded sources, revision/freshness, unknown or
conflicting evidence and a bounded summary. A saved summary remains derived
context with source references, never a replacement for canonical facts.
Context refresh preserves the old snapshot and creates a new revision. Applying
a proposal requires current preconditions even when its original chat looked
current. A stale offline cache is read-only and never confirmation evidence.

Attachments are untrusted data: typed/size-bounded ingestion, access checks,
content sanitization, secret redaction and safe preview are required. Repository
text, images, documents and model output cannot issue instructions that expand
scope or tools. Partial upload, unsupported format, inaccessible source or
insufficient context yields a visible clarification/degraded result, not an
invented fact or hidden retrieval from a different project.

## Common interaction and lifecycle

```text
Workspace draft -> explicit send -> Forge admitted turn/session
  -> bounded advice -> explanation + optional structured proposal/artifact draft
  -> inspect/amend/defer/reject OR explicitly apply/submit to required decision
  -> owning service receipt -> refreshed projection
```

Conversation lifecycle: OPEN -> ARCHIVED -> OPEN, with retirement/deletion only
under retention policy. Archiving has no effect on admitted provider work,
proposals, decisions or Missions. A user edit/fork creates a new turn or branch
of conversation history; it never changes a result that supported a decision.

The existing AI Architect Session lifecycle is retained: CREATED -> PREPARED ->
REASONING -> REVIEW -> COMPLETE, or ABANDONED. COMPLETE means the advice session
finished, not that a proposal was approved or a Mission completed. Business and
UX reuse this lifecycle target. Invocation outcomes such as FAILED,
MAY_HAVE_HAPPENED and cancellation pending are separate execution observations,
not fabricated session success states. ABANDONED does not prove no provider ran.

Only explicit send/reassess requests invoke the Forge-owned planning/advice
provider boundary. Forge-local provider installation/session policy is separate
from EP's engineering provider and role/model policy; no EP-host binary or
credential is assumed available. Reuse supported session authentication and
approved bounds; no mandatory separate API purchase or metered fallback.
Qualification of the current Action-Derivation adapter does not qualify these
new advice request/result schemas. Each advisor adapter/profile needs its own
contract tests, timeout/cancellation/ambiguity handling and data policy.

One admitted reasoning turn per conversation is the V1 serialization rule;
parallel conversations require qualified provider capacity and project policy.
Persist request/invocation identity before the provider boundary. Duplicate send
reuses the operation/result. Lost acknowledgement reconnects/readbacks that same
operation; MAY_HAVE_HAPPENED forbids blind regenerate or model-switch retry.
Cancel is a request: show acknowledgement/uncertainty and consumed budget, not
an assertion that work did not happen. No switch/fork/archive resets budgets.

## Proposal, artifact, decision and Mission are different

A target `AdvisoryProposal` carries type, source session and evidence, affected
owner/objects, expected versions, before/after changes, rationale, uncertainty,
required decision roles, validation obligations and a stable digest. Logical
proposal types are VISION_PORTFOLIO, MISSION_CANDIDATE, ARCHITECTURE_REFINEMENT,
ROADMAP_DAG_CHANGE, DESIGN_ARTIFACT and ASSESSMENT; these are design categories,
not new executable enums. Mixed-authority proposals expose their separate
owner-bound changes and approvals, without partial success being hidden.

Proposal presentation lifecycle: DRAFT -> PROPOSED -> AMENDED/SUPERSEDED,
DEFERRED, REJECTED or APPLIED. Required decisions have their own approval or
rejection receipts. APPLIED is shown only after current owning-service readback;
a model answer, optimistic UI response or APPROVED label alone is insufficient.
Amendment creates a new revision and reevaluates applicability of prior decisions.

"Save draft" persists advisory/session material, not product state or Git files.
"Apply" submits a typed governed intent with actor, idempotency, expected
versions and proposal digest; "Request decision" routes the same bounded
proposal to its existing authority. Natural-language confirmation is acceptable
only when exactly one pending proposal/revision and the intended decision are
unambiguous and the authenticated actor is authorized. Otherwise clarify.
A generic "yes" never approves several proposals, both governance stages or
future engineering. Do not add repeated owner clicks for effects already covered
by a valid, exact approval/delegation; execution authorization remains separate.

Artifact drafts have immutable revisions, media type, digest, origin and
verification status. Inline tables, Markdown, diagrams or safe image previews
can be exported as user-requested artifacts after access/redaction checks.
Repository delivery of docs, ADRs, designs, tests or code uses an approved
Mission and EP, never a direct write tool inside chat. Artifact usefulness and
review criteria, not extension or line count, determine completion.

Read-only explanation/assessment can finish with a durable session result and
no Mission. A formal read-only execution Mission is a distinct future
qualification: do not invent write scopes to bypass any current runtime
restriction. An architecture/design/documentation-only Mission must explicitly
exclude implementation where intended. After delivery, "now implement it" is a
new proposal unless already within the approved Mission's unmet criteria.

Candidate promotion reuses the existing chain: register Candidate -> explicit
Business approval -> Architecture refinement/approval -> Mission Intake with
zero owner-scripted Actions -> authorized inner loop -> EP evidence. A handoff
package links the conversation/session, exact artifact revisions, unresolved
questions, accepted decisions, objective, exclusions and success criteria.
Neither the handoff nor a chat lens changes the approved Mission boundary.

## Failure, safety and observability requirements

Expose loading/empty/draft/submitted/waiting-provider/streaming/result-ready,
permission denied, stale/conflict, unavailable/unsupported, interrupted,
cancel-requested and uncertain states with actionable owning-system status.
Partial streamed text is provisional: no complete proposal/apply control until
validated durable result readback. Tool output and rendered Markdown/HTML are
sanitized; source links do not bypass authorization.

Audit metadata records actor, scope, session/invocation/proposal/decision IDs,
source digests and outcomes. Operational logs stay redacted and separate from
conversation content and immutable decision evidence. Retention distinguishes
unsent drafts, admitted transcript/result data, derived caches and required
decision/mission provenance. "Delete conversation" cannot erase canonical
decisions or silently remove another owner's records; explain retained records
and supported redaction/tombstones without promising universal hard deletion.

## Future qualification catalogue

These are acceptance requirements, not claims of executed integration tests.
Deterministic fixtures replace external advice providers and EP HTTP; real
application services, governance, storage and validation are exercised. The
existing inner-loop CI harness is reused when qualified, not replaced by a
mocked Mission engine. Outer-loop integration extends the later FCO programme.

| ID | Required scenario |
| --- | --- |
| RC-T01 | Business turn yields grounded Candidate proposal, no implicit approval or Mission. |
| RC-T02 | Architecture turn preserves business objective and makes a versioned refinement proposal. |
| RC-T03 | UX turn yields reviewable design criteria; no invented research or mandatory UX gate. |
| RC-T04 | Switch lenses/handoff retains identities, decisions and snapshots without granting roles. |
| RC-T05 | Draft/edit/fork/archive/reopen preserves admitted and decision-linked history. |
| RC-T06 | Duplicate send and lost acknowledgement recover the same invocation/result. |
| RC-T07 | Provider timeout/ambiguity/cancel never silently regenerates or resets budget. |
| RC-T08 | Stale/conflicting context or proposal preconditions prevent silent overwrite. |
| RC-T09 | Cross-project/role access isolation covers retrieval, later readback and export. |
| RC-T10 | Attachment/model/repository prompt injection and unsafe rendering cannot expand authority. |
| RC-T11 | Save draft versus apply versus decision versus execution remain distinct; ambiguous yes clarifies. |
| RC-T12 | Solo records separate Business/Architecture decisions; unauthorized lens cannot approve. |
| RC-T13 | Document/design-only handoff preserves artifact revisions, scope and exclusions. |
| RC-T14 | Read-only advisory result causes no target-repository mutation or Mission allocation. |
| RC-T15 | Provider unavailable/unsupported result and partial streaming stay non-authoritative. |
| RC-T16 | Restart/reconnect/retention preserves required provenance with honest stale/read-only UX. |
| RC-T17 | Approved Candidate goes through real governance/intake and inner-loop services with mocked EP; no scripted successor or bypass. |
| RC-T18 | Later outer-loop recommendation returns to conversation/Candidate without auto-approval. |
| RC-T19 | Five-language accessible browser journeys preserve semantic parity and exact confirmation. |
| RC-T20 | Console remains administration; Workspace closure does not stop Forge/EP; chat causes no provider reconfiguration. |

`CHAT_TRANSCRIPT_IS_AUTHORITY = FALSE`
`ADVISOR_KIND_IS_AUTHORIZATION_ROLE = FALSE`
`UX_REVIEW_REQUIRED_FOR_EVERY_MISSION = FALSE`
`CHAT_DIRECT_REPOSITORY_MUTATION = FALSE`
`CHAT_CREATES_EXECUTION_AUTHORITY = FALSE`
`ROLE_CHAT_REQUIRED_FOR_FIRST_CANARY = FALSE`
