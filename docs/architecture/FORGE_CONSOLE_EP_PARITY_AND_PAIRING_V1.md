# Forge Server Console: EP parity, logging and pairing V1

**Parent capability:** `FORGE::OPERATIONS_CONSOLE_V1`
**Disposition:** PLANNED / POST_AUTONOMY; future design and qualification only.
**Scope:** Forge's complementary instance-admin interface, never Workspace replacement.

This owner-requested refinement is mandatory for the future Console. It extends
[the console design](FORGE_OPERATIONS_CONSOLE_V1.md) and
[configuration/data operations](FORGE_SERVER_CONFIGURATION_AND_DATA_OPERATIONS_V1.md).
The [scoped roadmap](../roadmap/FORGE_OPERATIONS_CONSOLE_V1.md) and its
[parent DAG](../roadmap/forge-operations-console-v1.json) reference the
[parity sub-DAG](../roadmap/forge-console-admin-parity-v1.json).
It creates no current Mission, implementation, credentials or runtime authority.

## 1. Evidence baseline and explicit refinements

Source observations were made on 2026-09-12, not on an installed host:

| Source | Pinned revision |
| --- | --- |
| Forge | `a64d3445e6162d2266dfd1b8acfd6ba2d88a50a5` |
| Engineering Platform | `c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3` |
| Forge Platform | `cb6a10a4ffca90e2b689af62349da2075fe47a77` |

EP's [canonical design system](https://github.com/pcvantol/engineering-platform/blob/c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3/src/engineering_platform/OPERATIONS_CONSOLE_DESIGN_SYSTEM.md),
[component-log service](https://github.com/pcvantol/engineering-platform/blob/c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3/src/engineering_platform/component_logging.py),
[validation workflow](https://github.com/pcvantol/engineering-platform/blob/c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3/.github/workflows/engineering-platform-validation.yml),
[Playwright config](https://github.com/pcvantol/engineering-platform/blob/c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3/playwright.config.mjs) and
[browser package](https://github.com/pcvantol/engineering-platform/blob/c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3/package.json)
are the comparison sources. Screenshots are presentation examples, not proof
that every represented route is implemented, enabled or safe for Forge.

This refinement explicitly replaces the initial parent wording that leaves the
frontend choice unspecified: use the EP technical pattern and design system
below. It also extends the initial no-log-deletion V1 restriction ONLY for
eligible diagnostic records through a qualified owning retention contract.
It does not remove immutable-journal or evidence protections. Pairing becomes
an explicit admin UX operation; discovery still cannot silently authorize it.
Other parent restrictions, especially Workspace ownership, remain unchanged.

## 2. GitHub: actual use versus a conditional provider card

The inspected installed Mission composition
[`InstalledDynamicMissionRuntime`](https://github.com/pcvantol/forge/blob/a64d3445e6162d2266dfd1b8acfd6ba2d88a50a5/forge/runtime/dynamic_mission.py)
composes Forge governance/planning and the EP Execution Host factory. It does
not compose a standalone GitHub provider. The inspected
[Repository Truth contract](https://github.com/pcvantol/forge/blob/a64d3445e6162d2266dfd1b8acfd6ba2d88a50a5/forge/repository_truth.py)
is an input-only evidence snapshot, not a GitHub client. Local Git revision
inspection, GitHub URLs and consuming GitHub-related EP evidence do not by
themselves establish a Forge GitHub login dependency.

GitHub IS used elsewhere in this repository: the
[production-release workflow](https://github.com/pcvantol/forge/blob/a64d3445e6162d2266dfd1b8acfd6ba2d88a50a5/.github/workflows/forge-production-release.yml)
uses `gh release view/download/create` with the workflow token. That is governed
release infrastructure, not a Forge Server provider session. EP's
[Server boundary](https://github.com/pcvantol/engineering-platform/blob/c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3/src/engineering_platform/server.py)
and [console services](https://github.com/pcvantol/engineering-platform/blob/c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3/src/engineering_platform/server_console_services.py)
explicitly use `GitHubProvider`; EP retains engineering GitHub mutations.
This assessment concerns those source paths, not a claim that the entire
Forge repository contains no GitHub integrations of any kind.

**Current requirement:** do not make a Forge GitHub installation/login a health
or E2E prerequisite when the selected runtime has no direct GitHub consumer.
An integrations inventory may say `NOT_REQUIRED / managed by EP`; it must not
show a fabricated local GitHub session. EP auth/readiness, when shown, is a
scoped producer projection/link, not a copied Forge credential or local path.

If a future declared Forge-owned consumer really needs direct GitHub access,
its integration must expose the same applicable administration contract as
Codex rather than only a status dot:

- used-for purpose, owner/host, configured and effective adapter; local executable
  path/version/provenance only if that adapter actually uses `gh`;
- installed/compatible, authenticated account and GitHub host, effective
  repository/permission scope, last supported non-generating readback, failure
  and remediation; no token/authfile disclosure;
- explicit sign-in/sign-out, install/update, reconnect and recheck controls only
  through supported owning services and current authority; unsupported controls
  visibly disabled with a reason;
- Forge-local executable/session isolation where required, no EP/PATH fallback,
  no logout of a shared EP session and no silent change during active work;
- account/permission changes audited with impact and expected revision, without
  granting Mission approval, a broader GitHub scope or execution authority.

The same account/subscription may be used without sharing a mutable runtime or
copying auth files. No new GitHub provider is implemented just to fill the UI.
Future direct read-only Repository Truth access must not move branch/PR/merge
execution from EP into Forge.

## 3. Logging: functional parity with an explicit retention boundary

### Source-derived behavior and adaptation

EP's design specifies copy of the current visible filtered/sorted/page result
with headers, time presets Today/Yesterday/day/range, minimum-severity/event
filters and semantic selected-row styling. Its current component-log service
supports search, events, date bounds, deterministic sorting and pagination
BEFORE returning the bounded page. The older design paragraph about filtering
only loaded entries is not the full current backend contract: Forge must query
retained authorized history, not silently search only a recent sample.
EP's service also exposes component clear and retention pruning with allowed
periods 30, 60, 90, 120, 180 and 360 days. These source capabilities do not prove
that any particular installed EP clearing route is currently authorized.

### Required log-view behavior

| Function | Forge acceptance contract |
| --- | --- |
| Search | Bounded text query across authorized retained history; safe escaping, reset/empty/no-match states, not only loaded rows. |
| Filter | Component, minimum severity DEBUG/INFO/WARNING/ERROR, event, Mission/Action/correlation and time. Today/Yesterday use the viewer's local calendar; persist/query unambiguous UTC bounds. A custom inclusive end is explicitly displayed. |
| Sort | Allow-listed columns, ascending/descending with stable event-ID tie-break; header state and pagination agree with the backend. |
| Select | Individual rows, multi/range selection and select/clear current page; show count and scope. Freeze selected IDs/snapshot. Cross-page/all-filtered selection is explicit, never an invisible consequence of select-all. |
| Copy | Default: visible filtered/sorted current page including headers. Separate clearly labelled selected-row copy when selected. No hidden rows or unredacted payload; clipboard failure has localizable feedback. |
| Download | Explicit selected/visible/filtered/full-component choice only where supported, with bounded export or owning export job. Include source/time/filter provenance; an unfiltered export must be labelled unfiltered. No arbitrary filesystem route or secret-bearing URL. |
| Delete | Separate destructive operation on EXACT eligible selected records or explicitly previewed component/time/filter scope. Show count, protected records and irreversible effects; cancellation is a no-op. Backend rechecks identity, authorization, expected revision, retention eligibility and idempotency. Readback proves deletion; hiding rows is not deletion. |

Loading/refresh never changes selection into newly arrived rows. Changing filters
or project either clears selection explicitly or preserves an identified scope;
stale selected IDs cannot delete unseen work. Keep inspection available after
errors and display unavailable/stale rather than a misleading successful empty
log. Show structured error categories; escape hostile log text. No raw prompt,
provider output, credential, secret reference or private path is exported by the
ordinary diagnostic view.

### Log settings and immutable evidence

Expose **recording level** and **retention period** separately from the current
view's severity filter. Show policy source/revision, configured/effective value,
last application, next retention run, last result and deferral reason. EP's
DEBUG/INFO/WARNING/ERROR vocabulary and 30/60/90/120/180/360-day choices are the
parity baseline for eligible diagnostic logs; no live default is applied by this
document. A shorter retention is a destructive-impact change with preview and
explicit authorization, not an immediate unannounced purge during Save.

Forge's [canonical journal](FORGE_OPERATIONAL_LOGGING_CONTRACT.md) currently
rejects UPDATE and DELETE. Mandatory operational/domain audit, governance,
provider-attempt, correlation, terminal evidence and Mission history therefore
remain protected. Lowering diagnostic verbosity cannot suppress mandatory audit
facts. Retention is not permission to erase active-work or unresolved-ambiguity
records, reset counters, or remove evidence backing a completion decision.

The owning logging service must classify deletable diagnostic material versus
protected journal/evidence and qualify the deletion/retention path before the
buttons become enabled. Use the existing `operational_log_page()` query boundary
and canonical operational-event writer; no independent UI log authority or
frontend direct SQL. Do not weaken immutable triggers as a shortcut. A later
archive/retention change for protected records needs its own explicit preservation
contract; it is not authorized here. Deleting a downloaded copy is distinct from
deleting its canonical source. VACUUM only compacts storage; it is not log pruning.

## 4. Same design system, five languages and frontend/backend pattern

**Same design system**, not merely a similar palette. Use EP's source-pinned
semantic tokens, category/status distinction, system typography, geometry,
buttons, tables/selection, modal/focus/toast behavior, responsive and accessibility
rules. Baseline examples: house-style orange `#f0b66a`, 14px body, 18px main
panels, shared 25/32/44px circular controls, native details/summary and local-path
copy controls. Use Forge product name/mark and Forge concepts; do not mislabel
Forge as Engineering Platform. No browser-native alert/confirm/prompt, color-only
status, dead link, per-cell selection rings or inaccessible mobile dialogs.

Pin the adopted EP design revision and record changes with a parity matrix and
visual tests. Reuse qualified shared assets when legitimately available; otherwise
keep a source-attributed, controlled local adaptation. Do not load live EP assets
at runtime, require its checkout, import its Python implementation, or start a
new shared-component product as a prerequisite. Any deliberate divergence needs
a documented reason, owner decision and updated tests, not accidental CSS drift.

**Languages:** English (`en`), Nederlands (`nl`), Deutsch (`de`), Français (`fr`)
and Español (`es`). EP catalogs them in `assets/dashboard_locales.mjs`.
Ship complete key/parameter parity for visible labels, dynamic states/errors,
tooltips, aria names, confirmations, copy/download/delete feedback and pairing.
No embedded UI literals or AI translation on refresh. Stored machine codes,
identities and evidence remain unchanged. Format dates/numbers in the selected
locale and expose timezone; unknown diagnostics use a safe translated template.

**Same technical pattern:** a product-owned Python server and application-service
boundary, server-rendered HTML shell, packaged CSS/JavaScript, plain browser JS
with focused ES modules (including the snapshot store and locale catalogs),
authenticated JSON requests and supported event-stream/polling read projections.
This follows EP's `server.py`, `server_console_services.py`, packaged
[`assets`](https://github.com/pcvantol/engineering-platform/tree/c6bf2ea13159fb464a5c3ec3f24e1c05e9809fa3/src/engineering_platform/assets)
and `dashboard_status_store.mjs`, not a new React/Vue SPA or Node production
server. Node/npm are build/test tooling; Forge serves its own assets from its
installed distribution. Do not copy EP's legacy root-bound delegates.

```text
Forge Console browser (view state only)
  -> Forge-owned authenticated HTTP/API (versioned OpenAPI + Postman)
    -> interface-neutral Forge queries and authorized commands
      -> one resolved Forge instance / canonical stores
      -> existing EP consumer and shared pairing contract (no peer SQL)
```

Project/instance/revision bind every request. Stale snapshot responses cannot
replace newer state; auth, CSRF/origin protection, redaction, validation and
idempotency live on the backend. Browser state holds preferences/drafts, not
credentials, grants, Mission truth or scheduling. UI refresh/read endpoints do
not create work. Reuse already-defined APIs; missing Forge-facing routes are
bounded future backend work, never permission to shell out from the browser.

## 5. EP instance connection, discovery and automatic pairing

The Configuration connection card always shows **unbound** or the exact bound
EP product/instance, authenticated fingerprint state, endpoint/host, observed
version, negotiated contracts/capabilities, authorized scope, binding revision,
last successful contact and current error/freshness. Do not confuse a matching
instance string with cryptographic authentication. Display not-verified fields
as such. Existing project selection does not retarget the peer.

Use the SAME [instance discovery/pairing contract v1](https://github.com/pcvantol/forge-platform/blob/cb6a10a4ffca90e2b689af62349da2075fe47a77/docs/architecture/INSTANCE_DISCOVERY_AND_PAIRING_CONTRACT.md)
that the universal installer will consume: `forge-platform.instance-descriptor/v1`,
stable opaque instance IDs, short-lived public descriptors, compatible APIs,
capabilities, identity fingerprint and expiry. LAN DNS-SD/mDNS locates candidates;
configured HTTPS/unicast/tailnet endpoints work when multicast cannot. No private
project, path, account, queue or bearer data in discovery advertisements.

The UX provides **Find EP / Connect / Connection details / Recheck / Disconnect
or re-pair where supported**. Select the intended compatible instance and show
identity, requested scope and trust impact. After that authorized user intent
(or a recorded policy already authorizing this exact target/scope), perform the
technical handshake, single-use ceremony, scoped credential exchange, secret-store
placement, binding persistence and readback AUTOMATICALLY. No manual token,
UUID, fingerprint or Python-script copy/paste as the standard happy path.
Unbound setup shows one coherent progress/result view, not an arbitrary sequence
of product-internal commands. A real OS/provider consent boundary is surfaced
when needed, never automated away.

Console and installer are clients of the same product-owned pairing services,
state machine, descriptors and receipts. No second Console-only protocol or
requirement to run the whole installer. Each peer persists ONLY its own state.
Read the existing compatible binding first; idempotent reconnect reuses it.
Ambiguous multiple candidates, changed fingerprint/identity, expired ceremony,
revocation or uncertain acknowledgement fail closed with a specific next action.
Discovery is not authorization and cannot silently pick a new default peer.

A partial handshake has a durable operation ID and coordinated recovery/revocation
of only the newly issued credential; it cannot leave an orphan privileged session
or create duplicate bindings. Stop/reopen resumes that operation. Re-pair or
disconnect requires explicit impact/authority checks and preserves historical
correlations; reject/defer active-work retargeting. No new Mission authority or
budget is created by a successful binding. Test separate Forge/EP/browser hosts.

The shared contract is target architecture. Current manual peer configuration
or v1.2 compatibility readback does not prove discovery/automated pairing is
implemented. This requirement remains outside the first E2E critical path.

## 6. Matching CI, Playwright and coverage gates

### Observed EP baseline

EP's pinned validation workflow uses Python 3.14, installed-wheel validation,
branch coverage, API/OpenAPI/Postman consistency, conditional localization and
four complete deterministic Playwright shards on separate hosted runners.
`npm ci` and pinned `@playwright/test` (1.62.1 in that snapshot) reproduce browser
dependencies; Chromium is installed for CI. The Playwright config uses CI retry
1, worker 1 and maxFailures 3. Its local wrapper runs the same four shards with
one worker each, a host-wide batch lock, five-minute deadline and owned-process
cleanup. JS logic tests use Node's test runner; locale validation is a separate
`UI-GOLDEN-LOCALIZATION` gate. TDE is observation, not invented approval.

The actual Python coverage workflow requires aggregate >=80.00 and each shipped
module >=80.20, with missing production modules failing. This is NOT evidence
that EP currently enforces JavaScript code coverage or a strict aggregate >80.

### Required Forge Console gates

Use that same layered setup with Forge-owned package paths, services, fixtures
and check names. Do not copy EP execution/Genesis fixtures and call them Forge
qualification. Keep dependencies/actions pinned and refresh their approved
versions explicitly rather than treating this source snapshot as permanently
latest. Complete browser shards and localization must gate Console-affecting
changes; narrowly classified docs-only changes do not pretend to run a browser.

Required future evidence:
- Python unit/service tests plus isolated installed-wheel smoke, packaged asset
  and API/HTML/locale delivery, and API/OpenAPI/Postman parity including auth,
  malformed requests, unavailable state and expected-revision conflicts;
- JS unit tests for snapshot order, log selection/filter/page behavior, redaction
  formatting, pairing progress and locale-key/parameter completeness;
- all four Playwright shards, one worker per CI shard, bounded retries/failures,
  a local CI-parity wrapper with host lock/deadline/process cleanup, and retained
  screenshots/traces/failure diagnostics by shard. Track flaky retry evidence;
  green-on-retry is not silently treated as a deterministic first-pass result;
- five-locale browser cases, desktop dark/light, phone portrait/landscape and
  touch/keyboard cases; shared tokens, modals, hover/focus/disabled/selected states,
  no native dialogs, clipboard denial, destructive cancellation, log isolation,
  retained drafts and discovery/pairing failure/reopen cases;
- security/CodeQL, version/projection checks and applicable observe-only TDE,
  qualified on the actual final head. Source merge is not installed operation.

**Coverage must exceed 80%.** Use a numeric minimum of **80.20%**, assessed before
rounding, for both aggregate and each shipped Python module in the applicable
production scope; retain branch measurement. Require the same >80% floor for
production frontend statements, lines, functions and branches, overall and per
module. Include unimported/unexecuted production files; missing measurement is
a failure, not exclusion. Zero executable units are explicitly N/A with an
inventory, not manufactured 100%. This frontend gate and stronger aggregate
floor are explicit Forge requirements beyond the observed EP Python gate.

Keep backend/frontend reports separate: a large backend score cannot conceal
uncovered browser logic. Playwright interaction or screenshots alone are not
code coverage. Document the instrumented production inventory and artifact/source
bindings. No coverage exclusion, shortened suite, mock-only pairing PASS or fake
review to satisfy the target. These checks are future implementation DoD, not
new claims about today's documentation-only CI.

## 7. Admin only: Workspace remains the human project control plane

The Console observes and administers its Forge Server instance: tooling, peers,
logs, operational settings, data maintenance and bounded controls on already
approved work. Workspace retains project/portfolio experience, Mission authoring,
Business/Architecture approval, Human Gates, chat and Policy & Automation UX.
Console actions go through existing typed authorized services, not a second
approval domain. Deep links may lead to Workspace when available; Workspace is
not required merely to inspect local admin state. Conversely, pairing/login or
a green health badge never approves or starts a Mission.

All work packages remain PLANNED. Implement only through later bounded work,
with fresh owning-source/readiness checks. This source update changes no runtime,
provider session, peer binding, loglevel/retention, workflow or Mission state.
