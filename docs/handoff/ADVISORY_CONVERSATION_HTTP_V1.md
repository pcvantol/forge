# Business / Architecture textual advisory HTTP V1

Assignment `L3-FORGE-ADVISORY-CONVERSATION-HTTP-V1-20261008`, plan r38,
JOIN `L3-L4-ADVISORY-CONVERSATION-HTTP-V1-20261008`.
Base protected `e64302ffd2385926c1d5fad3e1417778798309aa` / Forge 2.7.69.
Selected new capability boundary: normal MINOR **2.8.0**, one event lineage.
State: source candidate; not PRODUCER_QUALIFIED until protected exact-main
installed delivery. Prior r37/GP/FCI/serial assignments remain closed.

## Outcome and authority

An explicitly scoped consumer submits a Business or Architecture text turn,
reads its admitted reasoning session/invocation and validated advice, and resumes
that correlated history across restart. Only submit can request generation.
Forge owns admitted requests, immutable snapshots, identities, consumption and
validated result provenance. Workspace owns navigation/title/drafts/archive.
Advice COMPLETE finishes advice, never a Mission or approval. No Candidate,
Action, proposal/apply receipt, target file or formal decision is created.
UX, attachments, export, streaming, tool execution and provider-stop are unsupported.
Cancellation is an intent flag; its receipt states `provider_stopped:false`.

## Actual consumer and owner routes

Separate owner-issued capability; existing admin/status/review/worklist/hold
bearers cannot access these routes. Actor/role/provider/model are not client
request authority. Owner commands require the current installation operator.

| Method | Route | Meaning |
| --- | --- | --- |
| GET | `/v1/advisory/capability` | Supported textual contracts, exact scope/conversations, selected source metadata and limitations; no provider probe |
| POST | `/v1/advisory/{conversation_id}/turns` | One explicit bounded admitted turn; exact turn ID/payload recovery |
| GET | `/v1/advisory/{conversation_id}` | Own private history, cursor0..8, limit1..4 |
| GET | `/v1/advisory/{conversation_id}/turns/{turn_id}` | Exact original turn plus separately current conversation revision |
| POST | `/v1/advisory/{conversation_id}/turns/{turn_id}/cancel` | Record a scope/CAS-bound cancel request, never assert provider cancellation |

Machine contracts: `forge/api/advisory-conversation-v1.json`, owning OpenAPI and
Postman;47 route catalogue, unchanged legacy contract bytes. Preauthentication401
uses the existing Forge authentication envelope. All advisory app errors use
`forge-advisory-conversation/v1`, including scoped403, typed stale/conflict/busy/
budget409, missing404, malformed/unsupported400 and unavailable503.

`forge-advisory-grant --data-root ... issue --principal-id ... --project-id ...
--repository-id ... --conversation-id ... --expires-at ... --token-file ...
--maximum-turns ...` issues a private bearer to a new output file, never stdout.
Expiry is future/max30days, max16 exact conversation IDs,64 retained grants,
maximum1..8 turns. Revoke uses the same owner CLI and exact grant ID. The scope
must match the instance's existing canonical configured project/repository.
Grant IDs are separate from principals; renewal never rewrites retained budgets.
A conversation belongs to one actual principal; its ID grants no access and is
unique within instance/project/repository. `capability` is a reserved ID.

`forge-advisory-context --data-root ... publish --source-id ... --revision ...
--path docs/...` reads only the configured public GitHub repository through the
existing bounded HTTPS artifact reader at an exact40hex revision. No credential
discovery, arbitrary URL, filesystem harvesting or private repository fallback.
Only documentary `.md/.txt/.json` paths under docs/knowledge, max2048 safe text
characters,16 immutable sources,64KiB private catalog. Revoke retains old bytes
but removes access, including through saved turns. Only explicit selected source
IDs/versions enter a provider request; capability can preview selections through
matching `source_id`/`source_version` query parameters (at most two sources).
Selected revisions are immutable observations, not current repository-head proof.
Missing canonical Vision/Portfolio/roadmap/live-repository data remain explicit.

`forge-advisory` provides capability/history/turn/submit CLI parity through the
same application service and private scoped token; no local-admin fallback.
Its structured status does not equate transport success with advice COMPLETE.

## Turn, provider and recovery

Closed request: contract_version, instance/project/repository/conversation,
turn_id, advisor_kind, objective(max1000), expected_revision, context_revision,
selected_sources. No hidden mode routing, actor, role or model override.
Output: bound request_digest/lens, summary(max512), bounded alternatives/questions/
unapplied suggestions and only supplied evidence references; `applied:false`.
Plain text has no active HTML/control/credential content; consumers render it
literally. Source/model text is untrusted data and never expands authority.

Each accepted turn persists request digest, Forge session/invocation IDs,
context versions, selected G011 policy binding and consumption before generation.
One admitted reasoning turn per conversation; overlapping send is promptly409.
Private transcript64KiB, max64 conversations and retained principal budget max8
across conversation/grant changes; the first conversation bound cannot expand.
At exactly64 retained conversations, fresh admission is denied before storage or
provider consumption; existing read/replay/continuation remain supported. The
installed matrix includes disposable declared budget-metadata input faults for
this boundary, alongside a real retained/replayed/continued provider conversation.
Plain multiline documentary text remains intact; credentials anywhere in the
full bounded text are rejected, with no legacy500-character summary truncation.
Capacity exhaustion is visible; no transcript deletion, grant replacement or new
conversation erases consumed/uncertain attempts. Reads/reopen/cursor/capability
cause no provider/planning/intake/decision/dispatch or canonical DB writes.

Uses the existing Forge canonical external ChatGPT-session configuration,
instance-owned provider HOME/config, bounded tool-disabled ephemeral read-only
CLI transport and actual generation permit. Advice has its own request/schema/
instructions/validator, not the Action-Derivation result parser. Requested model,
profile, effort and bounds remain distinct from observations. Unreported model/
effort/usage stay NOT_REPORTED. Current stronger observed-usage gates reject an
unreported or over-bound result as authoritative advice; no fabricated zero.
No EP provider, model purchase, metered fallback or new commercial model choice.
Live commercial model quality remains NOT_QUALIFIED by deterministic service proof.

Same turn ID/payload recovers original result and separately current revision;
changed payload is409. Old turns retain their original lens/context. Durable
validated outcome is stored at REVIEW before COMPLETE; exact confirmed orphan
permit reconciliation is tied to its original generation digest. Lost response
or new process never regenerates. Without durable result provenance, execution
remains MAY_HAVE_HAPPENED, including a process killed after intent admission;
new IDs/conversations and cancel flags cannot clear that uncertainty or budget.
Only supported explicit same-ID recovery advances a stored validated REVIEW.
Retained private source ACL and current grant/operator/project/generation are
checked on reads and at the provider boundary; revoke and context changes deny.

## Selected coverage and finish line

| Owning subset / scenario | Evidence boundary |
| --- | --- |
| RC-FC / F2 necessary subset | Closed v1 routes/schema, actual private principal/instance/project/repository/conversation grant and provision/revoke, truthful unsupported modes |
| RC-FS / T04,05,06,08,09,16 | Business→Architecture identity continuity, retained private history/cursor/reopen, original result/CAS/context isolation and real restart/lost response |
| RC-FA / T07,10,14,15,20 | Actual bounded external executable request/result, injection/unsafe-output validation, timeout/cancel/uncertainty/budget preservation, providerless reads, no governance/repository effects |
| T11,12 | Plain “yes”/advice grants no approval/apply; Business and Architecture lenses never become governance roles |

Only submitted/history text subset of T05; no Workspace draft/archive UI.
No T01/02 formal Candidate/refinement proposal, T03 UX, T17 promotion or full
RC-FP/RC-FQ/F2/family closure. Existing owning DAG edges stay unchanged.
Target: protected implementation + nonempty normal finalization, exact tracked
committed main wheel/noneditable outside checkout, full selected installed matrix
and genuine positive-replay revoke control, actual required CI retaining FCI102/
serial24/read/hold43/Action-authority, complete owning validation and changed
production executable-line coverage strictly>80.2%, independent exact-head
Quality/Security after owner convergence, necessary fixes, terminal readback and
safe own cleanup. Candidate, source merge and installed qualification differ.

Only external executable/model, OS identity and public repository transport are
deterministic fixtures; advice/auth/context/session/validator/recovery remain real.
Declared disposable expiry/corrupted-private-record inputs test failclosed parsing,
never seed successful advice or approvals. No live EP/provider/login/paid probe,
Keychain/historical runtime, signing, public release or operational activation.
TDE observe workflow and actual policy assessment remain separately recorded.
L4's independent native hold assignment remains pinned Forge2.7.69/e64302f.
Native chat requires a later separately selected consumer; no Workspace writer.
