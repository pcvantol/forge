# Forge Operations Console V1

**Capability:** `FORGE::OPERATIONS_CONSOLE_V1`
**Status:** documented future target; implementation and operational qualification **PLANNED**.
**Owner:** Forge. **Placement:** `POST_AUTONOMY`; not a prerequisite for the first Forge -> EP -> Forge E2E.

The owner requested a minimal Forge operational dashboard with an organization
comparable to the EP Operations Console: local host components, logs,
configuration, active Missions and historical Missions. This document defines
that bounded administration surface, not an implementation or execution grant.
The [canonical roadmap](../../knowledge/bootstrap/10_ROADMAP.md) owns priority;
the [scoped roadmap](../roadmap/FORGE_OPERATIONS_CONSOLE_V1.md) and
[documentary DAG](../roadmap/forge-operations-console-v1.json) decompose delivery.

## Purpose and ownership

A local operator should be able to answer: which Forge instance am I viewing,
is it healthy, what is it doing, why is it waiting, what happened previously,
and which operational settings are actually effective? Routine observation and
configuration should not require ad hoc Python, SQL, shell scripts or chat
handoffs. The console is optional: Forge remains headless and its API/CLI remain
usable without a browser or Workspace installation. This narrowly extends the
[source-pinned productization split](https://github.com/pcvantol/forge/blob/80dabdc2b3e4984ec846f040fc8f1037865c042d/docs/architecture/FORGE_PRODUCTIZATION_RECONCILIATION.md) with instance
administration; it does not restore the superseded primary Forge Studio.

| Boundary | Owner and console rule |
| --- | --- |
| Forge instance administration | This Forge-owned console presents operational projections and requests bounded changes through Forge application services. It is not a second runtime or scheduler. |
| Missions, Actions, planning, completion | Existing Forge services retain authority. The browser cannot infer approval, invent Actions, edit evidence or mark a Mission complete. |
| Human project/governance experience | Workspace retains portfolio, Mission authoring/approval, decision inbox, project chat and Policy & Automation UX. This console does not duplicate those workflows. Shared identifiers/evidence permit later navigation to Workspace. |
| EP execution | EP retains admission, runs, leases, validation, Quality/Security, corrective repair, GitHub mutation and terminal evidence. Forge may show verified references and link to EP; no direct CENTRAL SQL or copied EP execution engine. |
| Installation and host lifecycle | Forge Platform retains artifact composition, installation/update/repair, rollback and process restart choreography. This console does not run an installer, launchctl commands, arbitrary shell or peer service controls. |

EP is an interaction/organization reference, not a mandatory shared frontend or
runtime dependency. Reuse the shell/detail/filter pattern and the distinction
between instance-level and project-scoped data, not EP routes, its CENTRAL store
or its historical dashboard delegate. The consulted EP authority map is
[`P_CENTRAL_CONSOLE_AUTHORITY_MAP.md`](https://github.com/pcvantol/engineering-platform/blob/17abb3216d167f75d59a9f696a47c748ec4883a7/docs/engineering/P_CENTRAL_CONSOLE_AUTHORITY_MAP.md)
at `17abb3216d167f75d59a9f696a47c748ec4883a7` (observed 2026-09-12 UTC).
This is source-pinned design evidence, not a claim about an installed EP console.

## Navigation and common interaction contract

```text
Forge Operations | instance / host
[Platform status] [Refresh] Project [...] Language [...] Theme [...]
[Expand/collapse] [Auto refresh]
  Local host components
  Logs
  Configuration
  Active Missions
  Historical Missions
Footer: Forge / installed version | last live signal | connection / freshness
```

Use a compact responsive shell with readable lists/cards, bounded detail panels,
keyboard navigation, accessible status labels and shareable non-secret links.
Mission and log links preserve the selected instance/project/Mission identity.
No new frontend framework, frontend-package extraction or exact port is mandated
by this design. A later implementation selects the smallest shipping solution.

Every projection includes its source, observation time, stable identity and
freshness. Distinguish `UNKNOWN`, `STALE`, `UNAVAILABLE`, `NOT_CONFIGURED` and
`UNSUPPORTED` from healthy/idle/empty. A disconnected server cannot be painted
green from cached data. Show expected versus observed state and the last safe
error rather than claiming that process liveness proves application readiness.

### 1. Local host components

Present the selected Forge Server instance and only its declared components:
HTTP/admin surface, runtime/dispatcher, planning-provider adapter/session,
EP-peer connection and storage/log subsystem. Logical components need not be
separate processes; identify external dependencies and peers as such.

Show installed product version, source revision and artifact identity when
available, host/instance identity, runtime state, uptime/last observation,
schema/integrity readback, component availability and the last redacted failure.
Separate package version from historical database metadata and installed code
from current repository main. Never reconstruct installed proof from Git alone.

An authenticated local administrator may see an explicit data-root diagnostic;
raw storage contents and arbitrary filesystem browsing are excluded. No root
selection or silent fallback may create another runtime. Start/stop/restart of
OS services and install/update controls are outside V1; explain the owning
management route instead of implementing it in the browser.

### 2. Logs

Provide bounded tail/history queries with time range, severity, component and
Mission/Action/correlation filters, pause/follow, pagination and a redacted
export. Preserve structured event identity and actual exception/exit/status
classification when safely available; do not collapse every error into an
indistinguishable generic failure.

Forge owns its log index and retention policy beneath its data root. The browser
uses the Forge API, never supplied filesystem paths or direct SQL. Escape log
content as untrusted text; redact credentials, authorization headers, tokens,
secret references/values, user paths and raw prompts before transport/export.
Any privileged diagnostic detail needs its own allow-list, not a raw-log bypass.

Logs explain activity but do not prove Mission completion, submission acceptance
or review PASS. Link to canonical evidence for those claims. EP logs remain
EP-owned; show an authorized link or a versioned producer projection, not a
CENTRAL query. V1 has no log deletion/clearing or arbitrary file download.

### 3. Configuration

Show configured, validated and effective settings separately, with origin,
revision/digest and last applied/readback state. Permit editing only an explicit
allow-list through existing Forge-owned services: planning-provider selection,
model/default policy, bounded invocation settings and selected EP-peer settings.
Unsupported settings remain read-only with a reason, never silently editable.

The change sequence is: read current revision -> edit -> validate/preview the
redacted diff -> explicit save -> backend authorization and expected-revision
check -> durable audit record -> authoritative readback. Surface conflicts,
restart-required/pending application and failures without optimistic success.
Reject stale forms and cross-instance writes; repeated requests are idempotent.

Display configured limits separately from enforcement. Model default resolution
is not a pinned/verified model; non-generating login/compatibility preflight is
not proof of a generation, repository authorization or Mission execution.
Do not market token policy fields as a hard spend/subscription cap without
producer evidence of that enforcement.

Use opaque credential references and secret-state projections, not secret
values. OS sign-in/Keychain consent remains an explicit supported local flow;
the dashboard does not read Codex authfiles, enumerate a vault, automate consent
or put tokens in URLs/browser storage. Pairing/credential issuance remains a
separately authorized owning operation. No automatic fallback account, new
instance, first_bind or EP-peer retargeting. Active correlations keep their
original bindings; changes affecting active work must be rejected or deferred
by the owning service, never rewrite that work.

### 4. Active Missions

Show non-finalized work, including queued, planning, executing, awaiting evidence,
paused and blocked/recoverable states, with exact canonical lifecycle labels.
Display Mission title/ID, project/repository, approved goal/scope, current Action,
last progress/event, waiting reason, approval/authority state and expiry,
remaining budgets with their enforcement classification, provider-attempt state
and linked EP submission/run/evidence where present. Unknown counts are unknown,
not zero; never fabricate completion percentages for a dynamic Action graph.

A detail timeline relates approved criteria, dynamically materialized Actions,
provider attempts, EP outcomes and Forge reconciliation. In particular expose
`MAY_HAVE_HAPPENED` or unresolved acknowledgement distinctly; a generic Run/Retry
button must not create duplicate generations or submissions.

V1 operational controls are limited to requesting pause at a safe Forge boundary
and resume of the same already-approved work when the backend says it is legal.
They carry actor, expected Mission revision, authority, operation ID and audit
provenance. Pausing Forge does not cancel an EP run already admitted. A successful
HTTP acknowledgement is only request acceptance; display applied/readback state
separately. Disable with a reason when capabilities or current authority are
absent. No new Mission, new Action script, budget reset, scope expansion,
automatic ambiguity retry, grant renewal or manual COMPLETE command.

### 5. Historical Missions

Provide a paginated, filterable history using canonical finalized/archived
classification: title/ID, project, outcome, start/end times, actual Actions and
attempts, failure/recovery history, delivered revisions, verified evidence and
completion-criteria results. Terminal failure and cancellation are not success.
Unresolved/recoverable work must not disappear into history merely because a
process exited; expose it in Active Missions or visibly link its recovery state.

Details remain available after browser/server restart and after a source
worktree has gone. Browser storage and Git branches are not the history authority.
Do not recreate historical bootstrap Missions as live instance state. Preserve
failed and ambiguous attempts; no clear-history, clone/rerun or mutate-old-result
controls in V1. Read-only evidence export must retain provenance and redaction.

## Forge platform status and basic shell functions

These shared V1 requirements refine the five-section console rather than add a
sixth product or a new runtime. **Forge platform status means the health of the
selected Forge Server instance, not the separate Forge Platform installer.**
The owner's three EP screenshots are the presentation reference: an aggregate
status button with a grouped detail panel, the top toolbar and the live-status
footer. Their shown EP version, timestamp, components and health values are
examples, not Forge defaults or proof of Forge/EP installed state. In particular,
a red Server-Relay row alone does not prove why the illustrated aggregate is
blocked; the requirements below make the contributing reason explicit.

### Platform status projection — FOC-STATUS

Provide a persistent status indicator opening a keyboard/touch-accessible panel
with title `Platformstatus · <status>` and the following groups. Every row has
a readable localized state and an authorized link to its component/detail/log
view where available; no color-only meaning, fake link or unscoped file URL.
The same canonical snapshot drives the header, panel and component pages.

| Group / Dutch label | Forge projection |
| --- | --- |
| PLATFORM / Platform | Forge Server, Forge-owned platform database/storage, runtime and Mission dispatcher; declared planning/peer readiness may be shown as dependencies, not invented host processes. |
| ACCESS / Toegang | Operations Console and its real connection; a relay only when that installation declares a supported relay. Distinguish browser-to-server access from the server's own health. |
| INGRESS / Ingangen | Declared Forge HTTP/API and CLI entrypoints, with availability separate from process liveness. No automatic File Inbox, Dependabot producer or other EP-specific ingress is added to Forge. |
| EXECUTION / Uitvoering | Current Mission/Action activity, waiting/block reason and approved Mission queue state/count, scoped to the selected view. Linked EP execution is producer evidence, not an EP process owned by Forge. |

FOC-0/1 define a typed projection with stable component identity and owner,
`scope`, `observed_state`, `expected_state`, `required_for`, `observed_at`,
freshness, reason/evidence reference and authorized detail target. Separate
liveness, readiness, configuration and current execution state; do not call a
CLI unhealthy because it is not a daemon. Capability/installation declarations
select rows. A missing required component must remain visible as missing, not
be filtered away; an unsupported optional component is absent or explicitly
`NOT_APPLICABLE`, never invented as a running service.

The backend derives the aggregate for an explicit scope/capability:
`HEALTHY` (Gezond), `DEGRADED` (Verminderd), `BLOCKED` (Geblokkeerd) or `UNKNOWN`
(Onbekend), with contributing component/reason and observation time. A known
failed mandatory dependency blocks its declared scope. If no known blocker
exists but required observations are missing/stale, aggregate UNKNOWN rather
than healthy; retain the last-known value separately. A configured non-required
failure is degraded with limited impact. All applicable required observations
must be current and healthy before showing HEALTHY. Known blockers take
precedence over unknown state, which takes precedence over degraded/healthy.

An unused optional relay MUST NOT block local operation; a required failed
access route blocks only its declared scope. An empty approved queue and no
active Mission are normal idle states, not failures. A paused/blocked Mission
or expired Mission authority remains visible under execution, but does not by
itself mean the server/storage is unhealthy. Conversely, a green platform badge
is not permission to run that Mission or proof of its success. No hardcoded
rule may treat every red row as a global platform blocker.

Instance status remains readable to an authorized operator with no project
selected. Project-scoped activity then shows no selection, not guessed zeroes;
do not silently choose the first project. The panel does not grant access to
other projects, machines or peer databases.

### Basic toolbar — FOC-SHELL

| Control / reference label | Required behavior |
| --- | --- |
| Platformstatus indicator | Open/close the grouped status panel; accessible name includes the current aggregate and expanded state. |
| Manual refresh / Vernieuwen | Request one bounded fresh read snapshot, show busy/error state and coalesce overlapping clicks. Never restart a service, planning call or Mission. |
| Project selector / Project | List only authorized projects with an explicit no-selection state. Change view scope, not the canonical active project, Mission, peerbinding or dispatcher. Discard late responses for the previous selection. |
| Language / Taal | Select from shipped translations; localize labels, status/reasons and date/time. IDs, digests and machine-state codes stay unchanged. Unavailable translations use a declared fallback, not fabricated text. |
| Theme / Thema | Light/dark with system preference as initial default; accessible contrast in both themes. This is presentation only. |
| Expand/collapse / Uitklappen | Expand/collapse the current section cards/details, preserving individual control and keyboard focus. No query or mutation of unrelated projects. |
| Automatic refresh / Automatisch vernieuwen | Explicit on/off state. When enabled, bounded polling with backoff is sufficient; use supported server events when available without mandating a new push/relay system. When off, freeze automatic data-view updates and show that fact; manual refresh still works. |

Auto refresh OFF is NOT Mission pause or server disconnect. A server heartbeat
may still be observed separately, but it must not silently refresh frozen rows.
Resuming refresh obtains one current snapshot; it does not replay operations.
Project changes/refresh must not silently discard or overwrite unsaved settings;
keep the draft or ask before discarding it. Reconnects and refreshes preserve
navigation, filters and focus where valid without selecting another instance.

Only non-sensitive UI preferences (for example language/theme/expansion/refresh)
may persist locally, namespaced by viewer/instance where applicable. They carry
no approval, auth token, secret, operational policy or lifecycle authority.
All toolbar controls are read/presentation operations, not hidden execution.

### Live status footer — FOC-FOOTER

Match the reference layout with `FORGE`, the actually running installed product
version, `Laatste live-statussignaal` and connection status. Expose source/artifact
identity in an authorized detail view when known; do not substitute current Git
main, browser asset version or historical storage metadata for installed version.
If UI and server versions differ, show the mismatch and disable unsupported
mutations rather than silently trusting compatibility.

Display the last genuine received server observation/heartbeat with localized
date/time and timezone/age, not the time at which the browser merely rendered.
Separate `server_observed_at` from client receipt/render time. Mark stale/missing
signals and auto-refresh pause explicitly. Transport connection is not fresh
application readiness. Show `Serverpush: verbonden` ONLY when serverpush is
actually supported and connected; otherwise show truthful polling, reconnecting,
disconnected or unsupported status. Never make push a prerequisite for V1.

### Shared qualification requirements

The read-only milestone already includes FOC-STATUS, FOC-SHELL and FOC-FOOTER.
FOC-Q must cover optional relay absent, non-required relay failed, required
component failed, stale/unknown snapshot, idle/empty queue, no project selected,
blocked Mission with healthy core, disconnect/reconnect and out-of-order project
responses. Browser tests cover all toolbar controls, translation fallback,
light/dark contrast, keyboard/touch panel access, retained unsaved forms and
footer version/heartbeat/polling correctness. Assert that observation/refresh
creates zero Missions, generations, submissions or runtime/configuration writes.
These are future acceptance requirements, not claims of tests already run for
a shipped dashboard. Existing lifecycle controls retain their separate gates.

## Service, transport and security design

```text
Browser (presentation only)
  -> authenticated/versioned Forge operations API
    -> interface-neutral read/configuration/lifecycle application services
      -> the explicitly resolved Forge Runtime Instance and Forge-owned stores
      -> existing authenticated EP adapter for bounded producer readbacks
```

Bind each request to the expected installed instance plus authorized project/
Mission scope. Reuse the real operator/session boundary; local loopback is not
an authorization substitute. Default to local-only exposure; remote/LAN access
is a separate authenticated transport decision, not wildcard binding. Mutating
requests need server-side authorization, origin/CSRF protection, bounded inputs,
expected revision and idempotency. Neither page refresh nor a log subscription
may generate a proposal, start execution, migrate storage or issue credentials.

Every implemented HTTP route must be included in versioned OpenAPI and its
derived Postman collection, including authorization/error cases, with CI drift
checks as required by the [Server deployment target](FORGE_SERVER_DEPLOYMENT_TARGET.md).
These are requirements for the future console API, not claims that such routes
exist today. Prefer bounded polling first; any event stream is resumable and
must not become an alternate source of state. Closing or reloading the browser
must not interrupt or duplicate a Mission.

## Acceptance and scope limits

The integrated V1 qualification must prove all five sections from an installed
artifact outside a checkout; the UI/API/source versions and evidence must bind
the same runtime. Include fresh/empty, running, blocked, expired-authority,
ambiguous-provider, disconnected/stale, storage-unavailable and restart cases.
Prove project isolation, secret-free logs/exports, escaped hostile content,
read-only page access, stale-write rejection, config persistence after reopen,
and pause/resume without extra submissions, authority extension or budget reset.

The console is not DONE when only its shell, API mocks or screenshots exist.
Read-only delivery can precede configuration/control delivery; report those
milestones separately. Production installation remains Forge Platform-owned.

No portfolio, Mission editor, Human Gate approval UI, chat, workflow designer,
provider broker, fleet manager, installer, process supervisor, schema migration
programme or cross-repository execution is introduced by this capability.
The first autonomy/E2E line continues independently; this document does not
change an existing Mission, run, grant, repair budget or executable DAG.
