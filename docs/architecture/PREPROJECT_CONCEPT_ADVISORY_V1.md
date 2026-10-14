# Pre-project concept advice V1

Selected R53 subset: HOB-F01/S3 with HOB-F02 proposal handoff.
Assignment `L3-PREPROJECT-CONCEPT-ADVISORY-V1-20261014`, JOIN
`L3-L4-CONCEPT-CHAT-BRIEF-V1-20261014`. Implementation and qualification OPEN.
R52 and all predecessors remain closed.

The owning wire contract is `forge-preproject-concept-advisory/v1`, independently
versioned from the proposed HOB contracts. The existing Forge Server composes
one service over the existing `AdvisoryProvider.invoke` adapter, transport,
security policy and durable generation permits. Existing project-scoped advice
keeps its project requirement. No repository, project, Mission or approval is
created. The six briefing fields are `name`, `purpose`, `users`, `non_goals`,
`constraints`, `open_questions`; explicit null means unknown.

## Consumer wire and authority

- `GET /v1/concept-advisory/capability`: current instance, finite scope, READ/ADVISE,
  provider receiver/profile/model disclosure, transfer digest and quota.
- `POST /v1/concept-advisory/turns`: explicit submit only.
- `GET /v1/concept-advisory/history?dossier_id=ID&conversation_id=ID`.
- `GET /v1/concept-advisory/intents/{operation_id}?dossier_id=ID&conversation_id=ID`.

Each request uses the distinct owner-issued concept-advice bearer and
`X-Forge-Concept-Audience`. R52 READ/PREPARE and old advisory/admin/worklist tokens
have no model right. No actor/viewer header grants authority. Workspace owns
its user's concept visibility and uses its own explicit CAS action to adopt a
proposal. Forge never edits the concept; a chat yes is not governance approval.

The explicit instance-owned provider policy includes recipient/profile, model
selection (when session-owned: `SESSION_CONFIGURED_NOT_REPORTED`), input/context/
output token bounds and timeout. The peer grants bind its current transfer digest.
A capability/read/refresh never generates. A session profile is not a verified
observed model. No ambient HOME/PATH credentials or model fallback.

## Source, history and changes

The [synthetic turn](../../examples/concept-advisory/business-turn.json) names
operation and turn before transport, concept revision, exact briefing digest,
conversation expected revision, role BUSINESS/ARCHITECTURE, language en/nl/de/fr/es,
and original user message. Capability supplies the actual instance and transfer
digest; synthetic placeholders are not grants.

Results separate answer, questions, assumptions and typed changes. Each change
binds an allowed field, its exact before-value, proposed content, reason and
supplied briefing/current or accepted prior turn references. No arbitrary patch,
tool, file or URL fetch. Supplied content is unverified; absent information stays
unknown. Existing R50/R51 documents are never automatically translated.

Known operation replay reads its original bytes. An unavailable admission may be
explicitly resubmitted with exactly the same operation only after authenticated
healthy intent-readback says CONCEPT_TURN_NOT_FOUND. Missing/corrupt initialized
storage is a different non-success, never healthy 404. Pending/uncertain or
existing turns are read back, never automatically regenerated. The qualifier
allows at most one such caller recovery; no backoff loop or new operation ID. Changed same-key input conflicts;
new turns use explicitly current briefing and exact conversation revision.
Accepted prior turns retain their original source. Finite retained principal
turn/token reservations survive role/conversation/grant changes and process
restart; no truncation, summary or quota reset. Pending/uncertain generation
blocks another call. Recovery is read-only, without invented provider cancellation.

## Limits and lifecycle boundaries

Request/result each 32 KiB, six changes, each text at most 2000 characters
(user message 4000), eight turns per principal, total reserved tokens at most
384000 and total reserved generation time at most 960 seconds, eight dossiers/conversations per grant, 64 retained turns and 1 MiB store.
Grant expiry at most thirty days; generation timeout comes from existing provider
policy. No authority lock spans generation or waiting for a client. Short current
owner/grant boundaries govern admission/start authorization, outcome persistence
and each bounded publication chunk. A sent provider request or sent response byte
cannot be withdrawn; unknown outcomes stay honest and do not trigger a new call.
Private HMAC-sealed storage and initialization witness fail closed on corruption,
missing initialized files or uncertain writes; no healthy-empty reset.

## Qualification boundary

Technical proof uses a visibly modeled external provider executable at the actual
existing transport boundary, measured requests/permits/call count, genuine installed
HTTP and separate processes. It is not live advice-quality PASS. No new paid model,
transfer or user-credential authority is granted. Independent semantic assessment
of synthetic advice and visible uncertainty remains required. Complete tests,
coverage, Q/S, protected implementation/finalization and NEW exact-final-main
installed proof remain open until actual evidence is delivered.
