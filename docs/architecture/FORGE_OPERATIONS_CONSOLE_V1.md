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
Forge Operations | instance / host | installed identity | connection / freshness
  Local host components
  Logs
  Configuration
  Active Missions
  Historical Missions
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
