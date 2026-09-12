# Forge Console hosting, component lifecycle and CENTRAL V1

**Capability:** `FORGE::OPERATIONS_CONSOLE_V1`
**Status:** PLANNED / POST_AUTONOMY; design and documentary dependencies only.
**Owner:** Forge. **First E2E prerequisite:** FALSE.

This owner-requested extension adds a Forge-owned Tailnet relay, a complete
component inventory with detail modals and safe restart, dedicated macOS service
installation, and explicit Forge CENTRAL semantics. It refines the
[Console architecture](FORGE_OPERATIONS_CONSOLE_V1.md),
[admin-parity contract](FORGE_CONSOLE_EP_PARITY_AND_PAIRING_V1.md) and
[Server target](FORGE_SERVER_DEPLOYMENT_TARGET.md). Its
[roadmap](../roadmap/FORGE_CONSOLE_HOSTING_V1.md) and
[sub-DAG](../roadmap/forge-console-hosting-v1.json) remain non-executable.

**Precedence:** for these four subjects this extension supersedes the initial
Console's blanket exclusion of OS-component restart and its relay-as-unspecified
future-option wording. The relay is a required V1 deliverable but optional to
activate on a particular installation. Installation remains separately authorized;
the browser requests typed operations, never arbitrary shell/launchctl commands.
The existing log/data, five-language, design-system, quality and Workspace
boundaries remain in force. No existing Mission authority is broadened.

## 1. Source observations, not installed claims

Sources were reviewed at these immutable revisions on 2026-09-12:

- Forge `5004cdb028dbbcff6e7ae180628c4711aaa48edf`:
  [`DataRootResolver`](https://github.com/pcvantol/forge/blob/5004cdb028dbbcff6e7ae180628c4711aaa48edf/forge/runtime/data_root.py)
  already selects `--data-root`, `FORGE_DATA_ROOT`, then the native default;
  [canonical data-root documentation](canonical-data-root.md) defines `forge.db`
  and instance/artifact/journal/log/backup/cache/lock directories.
- EP `2cf0415c31699875eb894547b5319fc2102edc7a`:
  [`platform_components.py`](https://github.com/pcvantol/engineering-platform/blob/2cf0415c31699875eb894547b5319fc2102edc7a/src/engineering_platform/platform_components.py)
  defines one inventory. Its Console is Server-native; the lifecycle worker is
  in-process. The relay has a separate label and restart capability. This is
  NOT evidence of an existing independent EP dashboard subprocess.
- EP's [`server_relay.py`](https://github.com/pcvantol/engineering-platform/blob/2cf0415c31699875eb894547b5319fc2102edc7a/src/engineering_platform/server_relay.py)
  and [`dashboard_supervisor.swift`](https://github.com/pcvantol/engineering-platform/blob/2cf0415c31699875eb894547b5319fc2102edc7a/src/engineering_platform/dashboard_supervisor.swift)
  implement an access-only adapter from the Tailscale address to the loopback
  Console, using 8765 on both addresses. Its hard-coded EP port, local compiler
  dependency and fixed Tailscale executable path are not Forge requirements.
- EP's [`system_server_service.py`](https://github.com/pcvantol/engineering-platform/blob/2cf0415c31699875eb894547b5319fc2102edc7a/src/engineering_platform/system_server_service.py)
  is explicitly a read-only system LaunchDaemon foundation, not a completed
  provisioner. Its [`server_service.py`](https://github.com/pcvantol/engineering-platform/blob/2cf0415c31699875eb894547b5319fc2102edc7a/src/engineering_platform/server_service.py)
  describes per-user LaunchAgent compatibility as legacy. Do not copy either
  label or call a read-only contract a completed service installation.
- Forge Platform `cb6a10a4ffca90e2b689af62349da2075fe47a77`:
  the [shared discovery/pairing contract](https://github.com/pcvantol/forge-platform/blob/cb6a10a4ffca90e2b689af62349da2075fe47a77/docs/architecture/INSTANCE_DISCOVERY_AND_PAIRING_CONTRACT.md)
  keeps each service, identity and storage authority product-owned. The installer
  coordinates owning lifecycle requests, not direct peer storage or service writes.

The Forge service/process split below is a new explicit target, not a claim that
EP already uses that exact split or that current Forge wheels implement it.

## 2. Three service identities, one Forge runtime authority

```text
launchd (one supervisor for each installed job)
  Forge Server service       -> runtime, API, application services, Forge CENTRAL
  Forge Server Console service -> Python UI/transport subprocess, packaged assets
  Forge Console Relay service -> Tailnet-only access adapter

remote browser -> Forge Tailnet address : console_port -> Relay
local browser  -> loopback : console_port -------------> Console
Console        -> authenticated local API/IPC ----------> Forge Server
Forge Server   -> existing authenticated peer contract -> EP (possibly another PC)
```

The Console is a subordinate UI service/subprocess of the Forge PRODUCT. Because
it has its own launchd job, it is technically a sibling of the Server under
launchd, not a child also spawned/restarted by the Server. **One supervisor per
process**: no duplicate Server child plus launchd Console and no second scheduler.
The Server defines component lifecycle semantics; launchd supervises processes.

Canonical target component IDs are `forge_server`, `operations_console` and
`dashboard_relay`; their labels must be Forge-owned, unique within the installed
service domain, recorded by the product's component/service definition and never
reuse `com.engineeringplatform.*` or retired `com.djconnect.*` labels. Literal
labels and default port numbers are finalized in that single versioned definition
at implementation, not independently in a plist, UI and installer.

The Console continues to use the EP technical pattern: Python HTTP services,
server-rendered HTML, packaged CSS/plain JS/ES modules, no Node production server
or replacement SPA. This process separation does not duplicate business logic.
The Console is an authenticated adapter over the same Forge application-service
API, carries the operator's scope, and never reads/writes `forge.db` directly.
Local API/IPC is authenticated and versioned; loopback alone is not trust.
Static/degraded Console presentation can survive an unavailable Server, but no
cached state becomes healthy or authorizes a write. The browser holds no service
or peer credentials. Define the internal transport and OpenAPI/adapter parity as
part of service delivery; do not expose arbitrary Server routes through a proxy.

The Server can operate headlessly without the Console or relay. Console/relay
restart does not restart planning or cancel an EP Action. EP, Workspace and
Tailscale's own daemon are dependencies/peers, not Forge-managed child processes.

## 3. Forge-local relay and own port

Ship an installation-owned `dashboard_relay` component and its service route,
with enable/disable/status and guarded restart. Remote access is opt-in, not an
installer default that silently exposes an admin interface. The relay binds only
the observed, qualified Tailnet interface/address and forwards to the exact local
Forge Console endpoint. Never fall back to `0.0.0.0`, a LAN wildcard, public
Funnel, EP's port or EP's relay when Tailnet is unavailable.

`console_port` is a persisted Forge setting. Use the same configured port on the
loopback and Tailnet addresses where that qualified transport supports it.
A separate internal `server_api_endpoint` avoids Console/Server listener overlap.
Validate conflicts with EP and all other local listeners before activation;
report the occupied endpoint rather than silently scanning to another port.
If an approved HTTPS terminator needs a distinct external port, expose that
explicit mapping. Never display a fabricated HTTPS URL. Show both verified local
and Tailnet URLs, their actual scheme, port and last successful end-to-end probe.

Tailnet network authorization and Forge operator/session authorization are
separate gates. Tailnet membership alone does not authorize admin writes. Preserve
Origin/Host/CSRF controls and enforce the intended external origin. Forwarded
headers are untrusted unless supplied by the explicitly trusted adapter. TLS and
browser secure-context requirements (including clipboard) must be qualified for
the selected route; no certificate-validation disablement or session downgrade.
A raw HTTP-over-Tailnet mode, if supported, is identified as such, not called TLS.

Prove the complete remote path, not just loopback `/health`: from a second
Tailnet client open the Console, identify the intended Forge instance, read a
fresh authenticated snapshot, load assets and verify permitted UI operations.
A live relay PID does not prove backend readiness or remote reachability. Bound
resource use, connection timeouts and graceful drain; test streaming/polling,
large bounded downloads, disconnect/reconnect and a changed Tailnet address.

Tailscale missing, logged-out, stopped, disconnected and address/identity-changed
states remain distinct. Forge may read its supported status and explain recovery,
but must not restart/logout/reconfigure the host-wide Tailscale daemon or tailnet
policy. Use an explicitly qualified local dependency, not EP tooling or an
unverified PATH fallback. No Swift toolchain or local compile is required merely
to activate a released relay artifact.

For local-operation health, an explicitly disabled relay is `DISABLED`, not a
blocker. For enabled remote administration, an unavailable relay blocks that
access scope. For a user expecting the relay, missing installation stays visible
as `NOT_INSTALLED` with a next action; it is not filtered out. Required delivery
of the capability is distinct from whether the operator enabled remote access.

## 4. Complete component inventory and detail modals

Maintain ONE versioned Forge component registry consumed by backend projection,
UI rows/modals, log identities, service installation, restart allow-list and
qualification. No hand-maintained second UI list. Every declared component,
including disabled, missing, stale or failed ones, is visible. Dependencies and
logical components are explicitly typed, never presented as imaginary PIDs.
The initial inventory must cover at least:

| Component | Kind / authority | Restart/control rule |
| --- | --- | --- |
| `forge_server` | Forge launchd service, runtime/API authority | Quiesced, authorized service restart with durable recovery |
| `operations_console` | Forge launchd UI service | Restart its UI process only; retain runtime and operator-safe reconnect |
| `dashboard_relay` | Forge launchd access service | Drain/restart exact relay; remote access warning, no Server/EP restart |
| `platform_database` | Existing Forge CENTRAL storage | No process restart; only guarded existing data/maintenance operations |
| `mission_dispatcher` | Logical Server runtime component | Only a qualified owning control; otherwise explain Server restart dependency |
| `planning_provider` | Logical provider adapter/session | No generic kill/retry; never repeat an uncertain provider call |
| `codex_runtime` | Forge-local external executable/session dependency | Installation/login operations stay separately authorized; not a daemon |
| `python_runtime` | Forge-owned installed venv dependency | Identity/readiness; no imaginary standalone restart |
| `ep_peer` | External EP instance/binding | Readback/recheck or authorized pairing; NEVER restart EP |
| `http_ingress` / `cli_ingress` | Declared Forge transport entries | Host/service dependency or one-shot availability, not extra daemon |
| `operational_logging` | Forge diagnostic/journal subsystem | Query/settings within existing immutable-evidence boundary |
| `tailscale_access` | External host network dependency | Read-only status; no host-wide restart or sign-out |

An implementation may refine IDs only via the canonical registry and contract
migration; it must keep this coverage of roles and reject unsupported aliases.
Add any newly shipped component to the inventory and its tests in the same change.
No GitHub/File Inbox/Dependabot process is invented merely to imitate EP.

Every row opens a shareable, instance-bound detail modal: name/ID, owner, kind,
expected/observed state, freshness, safe failure and dependency/impact reason.
For real processes show available PID/start time/uptime, service label/domain,
service account, fixed installed executable/venv and artifact/source identity;
for logical dependencies these fields are explicitly N/A. Show applicable
endpoints/ports, redacted configuration revision, readbacks and filtered logs.
Do not turn runtime paths into arbitrary filesystem navigation or disclose secrets.

The modal lists backend-declared allowed actions with disabled explanations,
not inferred permissions based on green dots. Use the same EP design system,
all en/nl/de/fr/es labels/errors/aria text, keyboard/touch behavior and bounded
mobile dialogs. Preserve modal/selection through refresh, reject stale snapshots
and distinguish a stale last-known failure from a current measurement.

## 5. Safe restart is a durable operation, not retry

A restart request carries actor, authorization, expected runtime/installation,
component/service identity, configuration revision and idempotent operation ID.
The backend—not JavaScript—validates the allow-list, dependencies, active writers,
provider attempts, EP correlations, leases and service ownership immediately
before handoff. Show affected access/work and retain cancellation before acceptance.

For Server restart: stop new admission/dispatch, reach a supported safe boundary,
persist/reconcile known state, then hand off to the installed lifecycle service.
Reject/defer if the boundary cannot be proven. Never silently force-kill an
in-flight or `MAY_HAVE_HAPPENED` provider call, reset its outcome or retry it.
An EP run may continue independently; retain its exact correlation and reconcile
it after reopening rather than submit it again. An uncertain but already durable
state may reopen only when the existing recovery contract proves no re-execution;
that does not resolve the ambiguity. Expired authority is not renewed by restart.

For Console/relay restart: only their own serving connections are interrupted;
show the disconnect impact and let the same approved operation be read back after
reconnect. Persist ACCEPTED before the process exits. A bounded installed helper/
service coordinator executes the handoff even when the requesting web process
stops. It is not an arbitrary privileged shell endpoint. Deny unsafe handoff when
this capability is absent rather than presenting a working button.

Read back requested -> accepted/deferred -> stopping -> starting -> healthy or
failed using canonical operation states. Verify the expected service domain,
process generation, installed artifact and SAME Forge runtime/installation/root;
HTTP 200 or a new PID alone is insufficient. Restart never performs an upgrade,
changes the EP binding, creates a runtime, resets a budget or clones a Mission.
Limit automatic crash restarts/backoff; intentional stop/disable must not be
undone by an unconditional KeepAlive. On Server unavailability provide a documented
installed CLI/OS recovery route; do not create another privileged rescue daemon
merely to keep a restart button active. Observation/refresh never restarts anything.

## 6. Product-owned launchd installation and account boundary

Deliver three independently inspectable launchd jobs for Server, Console and
relay, using one Forge-owned installation/service manifest. Normal server-mode
deployment targets system-domain LaunchDaemons with explicit least-privileged
non-root service identities. Any per-user development LaunchAgent mode is a
separately declared profile, not an automatic substitute or parallel production
installation. Qualify boot without GUI login and login/logout behavior for the
advertised profile; do not label a login-dependent user helper a system service.

Service account, domain, labels, plist paths, absolute installed entrypoints,
normalized data root, endpoints, environment allow-list and artifact digest are
recorded and read back. Preserve the venv launcher itself: resolving its final
symlink to the base interpreter must not accidentally bypass installed packages.
No shell activation, source checkout, EP venv, inherited interactive HOME/PATH or
secret in argv, plist, logs or environment export is accepted as runtime authority.

An account transition is NOT a data/credential migration. A system service cannot
assume access to a user's login Keychain or Codex session. Prove secret resolution,
provider readiness and non-generating preflight in the ACTUAL installed account/
domain, with a supported explicit consent/enrollment flow. No copied authfiles,
automated OS consent, new required API-key subscription or broad ACL weakening.
Until qualified, show credential/session readiness as blocked; do not claim
headless operation from a test in an unrelated interactive terminal.

Forge owns fixed service definitions, provision/readback/status/start/stop/restart/
uninstall semantics and the narrowly privileged adapter needed for registration.
Forge Platform's universal installer orchestrates those same product-owned APIs
and receipts; it never implements a second service manager. Console installation
requests (where offered) have the same boundary. Routine component restart need
not run the installer. Privileged registration consent is separate from browser
session authentication, Mission approval and execution authority.

Install idempotently, inspect conflicts across declared system/user domains and
report inaccessible inventory surfaces. Never delete an unidentified service or
claim machine-wide uniqueness from a partial scan. Enforce single-writer locks
and exact instance bindings across manual and managed launches. Start Server
before Console readiness, then relay readiness; launchd load order is not a
substitute for authenticated dependency checks. Startup races back off safely.
Uninstall exact owned jobs only after a safe stop; preserve Forge CENTRAL,
credentials and historical artifacts unless separately authorized to delete them.

## 7. Forge CENTRAL reuses the existing data root

CENTRAL means **one canonical Forge storage authority per Forge installation**,
not EP's CENTRAL, a shared cross-product database, or necessarily another filename.
Reuse the existing `forge.db` and resolver; no `central.db` migration, schema bump,
instance reset or directory move is authorized by this naming clarification.
The current native macOS user default remains
`$HOME/Library/Application Support/Forge Server`. A future system installation
pins an explicitly provisioned accessible root; it must not recompute another
root from its service account's HOME. A configured canary root remains that root.

Server owns all durable Mission/governance/provider-policy/peer/configuration,
operation, component-observation and logging semantics beneath this root. Console
and relay hold no second authoritative configuration/database or Mission state;
they consume versioned Server projections. Minimal read-only launch descriptors
outside CENTRAL are explicit bootstrap projections, digest/version-bound to the
installation record, not an alternative configuration authority. Only a bounded
owning service coordinator may complete lifecycle receipts while Server is down.
Diagnostic stderr during unavailable storage is bounded/redacted; never create
checkout-local persistent state. Reuse the existing immutable journal and the
qualified eligible-diagnostic retention boundary.

In Configuration expose **Forge CENTRAL**: effective path, instance/installation,
schema, size, integrity, last check and maintenance state; show path copy and the
already planned export/import/relocate/VACUUM controls via their owning services.
Differentiate distribution version, database schema and historical metadata.
Integrity UNKNOWN/UNAVAILABLE is not PASS. Ordinary refresh must not run VACUUM
or full integrity scans. Heavy checks are bounded service operations.

Data relocation extends FC-RELOCATE's same-instance cutover: quiesce writers,
backup, verify destination, then repoint and read back ALL owned Server/Console/
relay descriptors that reference the root. The old root is fenced, not a fallback.
No second active installation, lost pairing, expired-grant refresh or replayed
submission is allowed after reboot. Secrets remain in the approved secure store;
exports do not acquire credentials or tooling simply because this is CENTRAL.

## 8. Required qualification and exclusions

Inherit FCP-CI: separate production frontend/backend coverage at least 80.20%
including applicable per-module and branch gates, Python 3.14 installed tests,
API/OpenAPI/Postman parity, all four Playwright shards, exact-head security checks
and five locales/two themes/desktop/phone interaction evidence. New native relay
or service-helper code needs its own declared test/coverage inventory, never an
unmeasured production-language loophole.

Add real macOS installed service/account and second-host Tailnet acceptance;
Linux fixtures alone cannot qualify launchd, Keychain or remote access. Prove
service registration/idempotency, reboot/logout, crash backoff, no duplicate jobs,
port conflicts, remote auth rejection, frontend/backend outage separation,
component/modal completeness and safe restart/reconnect with unchanged runtime,
Mission, budgets and EP correlations. Prove relocation/reboot resolves only the
new CENTRAL root. Preserve negative, failure and interrupted-operation evidence.

The Console remains complementary instance administration, NOT Workspace:
no portfolio/Mission editor, Business/Architecture approval UI, chat or second
scheduler. No EP/Tailscale service control, universal-installer implementation,
current E2E recovery, runtime migration or live service mutation is performed by
this documentation increment. PLANNED is not SOURCE_FIXED, installed or qualified.
