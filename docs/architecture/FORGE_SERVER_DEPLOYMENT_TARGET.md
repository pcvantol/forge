# Forge Server deployment and peer-binding target

**Status:** Canonical target architecture; implementation, migration and qualification remain separately governed.

Forge Server is a headless installed service. Its central runtime-storage root is outside every Git/source checkout and contains the Forge-owned SQL database plus durable files, dispatch/correlation journals, artifacts/references, logs, backups and cache. It exposes a versioned HTTP API above interface-neutral Forge application services. The Forge CLI remains an administration, qualification and recovery client of those services; the runtime core requires no GUI. The optional future [Forge Operations Console](FORGE_OPERATIONS_CONSOLE_V1.md) adds instance administration without making a browser a runtime dependency. On macOS its installed service is launchd-managed.

The current repository-bound `.git/forge-runtime` placement is historical/bootstrap-compatible runtime placement, not the target authority. Migration/relocation must preserve the existing Forge instance ID, grants, Missions, budgets, requests, cursors and evidence, use a product-owned quiesced cutover with backup/integrity checks, and leave no dual writer or old-location fallback writer. A source checkout must never create a replacement runtime because it cannot find the installed one.

Forge binds to EP and Workspace only through their versioned authenticated HTTP APIs. It never reads their databases or controls their services. The shared discovery/pairing vocabulary and descriptor are defined by Forge Platform's [contract](https://github.com/pcvantol/forge-platform/blob/main/docs/architecture/INSTANCE_DISCOVERY_AND_PAIRING_CONTRACT.md): LAN DNS-SD/mDNS and configured/unicast/tailnet endpoints locate candidates, while authenticated pairing pins peer product, stable instance ID, identity fingerprint, endpoint/version/capability set and scope in Forge-owned storage. Discovery is not authorization; a binding never silently retargets to a discovered instance.

## Optional local Operations Console

`FORGE::OPERATIONS_CONSOLE_V1` is a **PLANNED**, post-autonomy local web
administration surface for host components, logs, configuration, active Missions
and historical Missions. It uses the same interface-neutral Forge services and
versioned authenticated API; no browser SQL, second runtime, implicit data-root
initialization or EP service control is introduced. The [scoped roadmap/DAG](../roadmap/FORGE_OPERATIONS_CONSOLE_V1.md)
separates read projections, UI, bounded configuration/control and installed
qualification. Workspace retains project/governance/approval/chat UX, while
Forge Platform orchestrates product-owned installation/lifecycle requests; Forge
owns its service definitions, safe restart semantics and readbacks. The console is
not a new prerequisite for the first Forge -> EP -> Forge E2E, and this target
document is not an implementation, release or runtime-authorization claim.

## Managed Console, relay and CENTRAL extension

The [hosting/component/CENTRAL contract](FORGE_CONSOLE_HOSTING_AND_CENTRAL_V1.md)
and [linked roadmap/DAG](../roadmap/FORGE_CONSOLE_HOSTING_V1.md) now require
separate Forge-owned launchd services for Server, subordinate Console and relay,
all declared components with status/detail modals, and safe authorized restart.
This explicitly refines the initial Console's no-OS-restart/unspecified-relay
wording. Console is functionally subordinate but a separately launchd-supervised
job: the Server must not also spawn the same child. There remains one runtime
and one Forge CENTRAL authority, using the existing `forge.db` data root.

Relay capability is required for V1 but activation is opt-in. It exposes the
Console on a Forge-owned port through qualified Tailnet access, not EP's relay
or a wildcard listener. The Python/HTML/CSS/plain-JS pattern, five-language and
quality contracts remain; no Workspace replacement or first-E2E prerequisite is
introduced. These are target service requirements, not installed availability.

## F2 HTTP-only transport and CLI parity refinement

The [owning API/transport design and roadmap](FORGE_HTTP_API_AND_TRANSPORT_PARITY_V1.md)
and [FH documentary DAG](../roadmap/forge-http-api-v1.json) refine F2. Shared
application services precede HTTP and CLI adapters; FH-Q qualifies each delivered
slice for the Server-only FSH-SERVICES milestone and its Console/Workspace
consumers. The API is a Server foundation, not a separate dashboard business API.
No complete Console, relay, chat, outer-loop or installer dependency is added.

Workspace -> Forge, Workspace -> EP and Forge -> EP are HTTP-only regardless of
host locality. The separate Console -> Forge Server link is also HTTP-only;
this supersedes earlier local API/IPC optionality. CLI stays an own-product
management/AI-automation ingress, not peer transport or business logic. Explicit
local-only init/start/recovery uses the same owning rules without requiring a
running HTTP endpoint, and cannot silently start a second writer. Locality never
makes peer CLI/import/SQL/File Inbox fallbacks acceptable. EP retains its own
supported File Inbox; Forge and Workspace need not add one. Existing canary
state and API implementation statuses are not changed by documenting this rule.

## HTTP API implementation requirement

Forge does not yet expose its own HTTP server. When that implementation is
introduced, its versioned OpenAPI document is the canonical public transport
contract and must describe every implemented Forge-owned route, method,
authentication requirement, request/response/error envelope and version
behavior. The implementation must ship an exhaustive Postman collection
derived from that contract, covering every documented operation and its
declared authorization and error cases without embedding credentials.

CI must run the collection against an isolated Forge server state and fail on
any drift between the OpenAPI document, the routes actually exposed by that
server, and the Postman collection. A route may not be added, removed or
semantically changed without updating all three artifacts in the same change.
This requirement applies only to a future Forge-owned HTTP API; it neither
redefines the EP API nor makes Forge an EP proxy.

The autonomy canary requires only installed Forge/EP storage, stable identities, the existing versioned authenticated Forge→EP HTTP seam, a configured/pinned EP binding and restart recovery. Workspace UI, LAN discovery and universal-installer completion are post-canary productization and must not block that proof.

## Durable EP peer configuration boundary

`FORGE_DURABLE_EP_PEER_CONFIGURATION_V1` implements the Forge-owned source
boundary for one explicitly selected EP binding. Runtime schema 33 stores one
secret-free `execution_host_peer_configuration` record in `forge.db`, separate
from per-correlation `execution_host_bindings`. The versioned record binds its
own identity, revision and canonical digest to the owning Forge runtime ID,
`engineering-platform`, one fixed endpoint, expected EP instance ID, Execution
Host ID, EP project and repository IDs, Forge repository identity, the exact
producer-readback and terminal-evidence contract `1.2`, one opaque credential
reference, bounded timeout, loopback-HTTP decision and creation/update
provenance.

Configuration writes are idempotent. A changed binding requires an explicit
replacement with both the observed revision and digest. Each newly created
correlation persists that configuration identity in the existing correlation
binding; recovery and evidence readback reject historic records without it and
reject any later endpoint, instance, project, repository or binding retarget.
This does not grant Mission, submission or mutation authority.

The shared `EngineeringPlatformExecutionHostFactory` is the sole product
composition route for both CLI preflight and runtime use. It rereads the
persisted binding, verifies the Forge runtime identity and contract, resolves
the Keychain reference, and constructs the existing
`EngineeringPlatformHttpExecutionHost`. That adapter now rejects request
host/repository scope mismatches before submission and repeats exact product,
instance and v1.2 compatibility checks for dispatch, recovery and evidence
readback.

The supported reference is
`keychain://<service>/<account>?namespace=<optional>&version=<optional>` and is
resolved through an explicit `/usr/bin/security find-generic-password` lookup;
Forge never enumerates Keychain or persists the result. HTTPS retains normal
certificate validation. HTTP is restricted to an explicitly enabled loopback
origin. Redirects are not followed, so a bearer value is never forwarded to a
different origin.

`forge execution-host preflight` uses only EP's existing read-only
`/v1/producer-compatibility` route. It can verify product, instance and
contracts, but deliberately reports EP project/repository existence and
current mutation authority as `NOT_VERIFIED`. The instance-ID comparison is
identity consistency, not a cryptographic identity claim, which remains
`NOT_ASSERTED`. Source qualification uses
isolated roots, test credentials and a simulated peer. No real Forge/EP
installation has been configured, no live E2E has run, and planning-provider
configuration, Mission governance, installer/Workspace work and EP #175 remain
separate and parked.
