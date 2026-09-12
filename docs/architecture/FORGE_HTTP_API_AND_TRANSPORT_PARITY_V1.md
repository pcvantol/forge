# Forge HTTP API and transport parity V1

**Increment:** `HTTP_ONLY_PEERS_AND_THIN_CLI_V1`. **Owner:** Forge.
**Status:** documentary target; implementation and qualification PLANNED. NO_BUMP.
This refines existing F2, not a second API programme. The
[documentary DAG](../roadmap/forge-http-api-v1.json) and delivery table below are
linked from the [Server target](FORGE_SERVER_DEPLOYMENT_TARGET.md).

## Decision and source boundary

The owner's clarified rule is HTTP-only between products and thin CLI ingress
for administration/AI automation of each product. Forge source was inspected at
`f2f1d8d8535d23323397df4ff7af8586f2c6364f`, Workspace at
`a12d5b925da1e04b86c1142e709f6f0fb4c7f617`, and EP at
`bd4c09ff85bc82783da6efb9f1f781dfb8100e17` on 2026-09-12.
These are source pins, not installed or HTTP-route qualification.

The existing F2 contract, Server-only milestone of FSH-SERVICES and Console
FOC-1 remain the owning lanes. F2 supplies shared application/transport contracts;
FSH-SERVICES supplies installed Server lifecycle; FOC-1 supplies operational
projections ON that API, not a second business API. Existing F1-F11 statuses and
canary dependencies are not upgraded or retrospectively blocked by this design.

## Explicit transport matrix

| Caller | Owning target | Only allowed product-integration transport |
| --- | --- | --- |
| Workspace Client | Workspace Server | Authenticated versioned HTTP(S) |
| Workspace Server | Forge Server | Authenticated versioned HTTP(S) |
| Workspace Server | EP Server | Authenticated versioned HTTP(S), directly to EP |
| Forge Server | EP Server | Authenticated versioned HTTP(S) |
| Separate Forge Console service | Forge Server | Authenticated versioned HTTP(S), including loopback |

Same-machine deployment changes none of these boundaries. No peer CLI/subprocess,
Python import invocation, direct database, shared queue, File Inbox, Unix-domain
RPC or in-process shortcut may replace a listed link, including on outage.
Immutable schemas/DTOs may be shared as qualified build dependencies, never peer
runtime/storage implementations. A client may implement a typed HTTP SDK only.

This closes the earlier Console-hosting `API/IPC` option: its target is HTTP,
not alternative IPC. Console is a presentation/access adapter over the same API;
its own static asset origin/relay is not a second Mission engine. Workspace asks
Forge about Forge-owned semantics and EP about EP-owned operations; Forge is not
a generic EP proxy. Browser clients do not hold reusable peer credentials.
Discovery (DNS-SD/mDNS), OS service control and provider/Git tooling are distinct
scoped facilities, not exceptions that can carry peer product commands.

## One application-service boundary, multiple local adapters

```text
HTTP adapter ----+
CLI adapter -----+--> own application services --> own canonical state/runtime
                 |       authorization / validation / idempotency / evidence
EP File Inbox ---+       (EP only; not a Forge or Workspace requirement)
```

Each product owns its adapter and service implementation. HTTP translates wire
requests/status/errors; CLI translates arguments/stdin, JSON/text and exit codes.
Business validation, scope, lifecycle, policy and persistence belong to shared
application services, not CLI command handlers, HTTP routes or browser JavaScript.
A runtime worker also uses those services and remains the background executor.

The local Forge CLI may call its OWN service in-process where explicitly supported,
or be an HTTP client to its own server. A remote CLI uses the server HTTP API.
The transport-mode choice is explicit; server failure never silently starts a
second runtime/writer. Shared rules do not imply identical privilege: supported
capabilities declare LOCAL_ONLY_ADMIN versus HTTP_EXPOSED. Do not expose every
privileged CLI operation over HTTP merely for symmetry. LOCAL_ONLY_ADMIN is not
a governance bypass or a peer-integration escape hatch.

Init, service installation/start, quiesced recovery and maintenance may use a
qualified own-product local management service when HTTP is unavailable. Resolve
exact installed identity/root and OS principal; use the same locks, preconditions,
versioned intents and audit/receipt semantics. Refuse conflicting writers and
ambiguous state. No direct ad hoc SQL, test constructor, new instance fallback,
automatic credential issuance or root/account change. The selected venv and
runtime core remain independent of EP/Workspace installations.

## API contract and progressive scope

Ship a versioned OpenAPI contract with typed requests/results/errors and a
capability/operation inventory. Inventory entries identify owner, required
principal/scope, mutating versus read-only behavior, available adapters and
LOCAL_ONLY_ADMIN restrictions. Unsupported operations are explicit, not implicit
private endpoints. Actual API paths/ports and schemas are later versioned delivery,
not invented shipped routes in this document.

The API grows by qualified slices: instance/capability/status; project/evidence
queries; governance/Candidate/Mission operations; operational configuration/log/
data controls; role-aware sessions/proposals. A minimal status API does not close
all F2, and the first Server need not wait for every future chat/Portfolio endpoint.
All Console and Workspace features consume their specific qualified slice.

Peer bindings pin expected instance, version/capability and project scope. Server
revalidates identity and actual authority; discovery or a selected UI project is
not permission. Preserve caller identity separately from service identity; reject
confused-deputy/cross-project requests and never trust roles supplied in JSON.
Protect browser-origin mutation, bound inputs/uploads and redact credentials.
HTTPS is the remote default; any permitted HTTP loopback/overlay exception must
be explicit and qualified. No arbitrary endpoint redirect or secret forwarding.

Mutations use stable operation/idempotency IDs, expected revisions/digests and
canonical result readback. Request acceptance is not task completion. Expose
bounded status polling or versioned HTTP event streams with cursors, freshness
and reconnect semantics. Cancellation is a request, not proof of no effect.
Lost acknowledgement resumes/readbacks the same operation, never switches to CLI
or Inbox or creates another Mission/submission. Provider MAY_HAVE_HAPPENED and
existing grants/budgets retain their owning semantics across adapters and restart.

## Delivery DAG and existing-lane joins

| Node | Internal dependencies | Required delivery/evidence |
| --- | --- | --- |
| FH-CONTRACT | none | Operation inventory, versioned request/result/error and transport/authority mapping |
| FH-SERVICES | FH-CONTRACT | Reuse own application services and exact-root composition; adapter-neutral tests |
| FH-HTTP | FH-SERVICES | Real foreground HTTP host over those services, auth, OpenAPI/Postman and readback |
| FH-CLI | FH-SERVICES | Thin own CLI, explicit local/remote management modes and effect-equivalence tests |
| FH-Q | FH-HTTP, FH-CLI | Installed transport parity, negative boundaries and actual HTTP integration |

FH-SERVICES consumes the qualified F1 identity/storage/auth subset, not a second
foundation. F2 is the parent/decomposition relationship, never a child dependency
that would create a cycle. FH-Q qualifies the delivered API slice; remaining
F2 operations stay open. The Server-only FSH-SERVICES milestone consumes this
API proof plus its independent process/launchd lifecycle evidence. FH-HTTP runs
as a real foreground installed server before launchd qualification, so neither
layer waits circularly on the other. Console/relay are not prerequisites.

FOC-1/FOC-5/FOC-6 consume their HTTP read/config/control slices. RC-FS consumes
the authenticated session API subset, not private library access from Workspace.
Workspace's WH-PEERS qualifies its HTTP clients against the published contract;
no reverse edge makes Forge's API depend on the Workspace UI.

The canonical roadmap still places installed Server delivery after review of the
current live-E2E outcome. Inner-loop CI may test own application services before
HTTP exists; once this slice ships, reuse the same scenarios through HTTP. Do not
mock the new HTTP adapter into PASS. Outer-loop CI follows its separate plan.

## Qualification (future, not run by this documentation)

HT-01: supported HTTP and CLI operations yield equivalent owning decisions and
receipts, including invalid input, denied authority, stale revision and conflicts.
HT-02: duplicate/cancel/lost response/restart retains identity, usage and budgets.
HT-03: run real installed HTTP servers with external EP/provider fixtures; capture
HTTP requests; make peer CLI/import/SQL/Inbox shortcuts fail the tests.
HT-04: same- and separate-process/host profiles have identical wire semantics;
peer outage fails without fallback, and wrong instance/version/scope is rejected.
HT-05: OpenAPI, implemented route inventory and derived Postman collection agree;
CI runs permitted and denied cases and fails on missing, skipped or drifting routes.
HT-06: local-only recovery is unavailable to remote callers; concurrent local/
server mutations cannot create a second writer; opening help/status is non-mutating.
HT-07: Console/Workspace UI tests use HTTP service boundaries, reflect stale/
partial states, and cannot infer success or leak credentials from optimistic UI.

Reuse existing Python 3.14, installed-wheel, security and production coverage
requirements; retain the Console's frontend/backend >80% and five-language/browser
gates for relevant UI. Contract tests alone are not live peer/installed proof.
NO_BUMP: no routes, jobs, services, CLI behavior, schema, grants, installations,
Mission, current E2E or EP File Inbox are changed by this documentary increment.
