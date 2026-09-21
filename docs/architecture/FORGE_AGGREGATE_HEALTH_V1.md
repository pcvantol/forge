# Aggregate health and HTTP qualification V1

**Owner:** Forge. **Status:** bounded installed snapshot DELIVERED; remaining F2/FH scope PLANNED, NO_BUMP.
The owner requested an aggregate health endpoint with degraded checks on
13 September 2026. Source baseline: `1cea418a5fa8f59d303f2a0d6ff27573c4a11752`.
The authoritative installed snapshot is implemented by the canonical typed
component registry, the shared `forge health` application service and the
authenticated `GET /v1/health` projection. It performs one deadline- and
step-bounded read transaction with at most one bounded integrity observation.
The broader route inventory, live peer probes, service lifecycle and Console
qualification remain planned and are not claimed by this source delivery.

## Reuse rather than a second API programme

The [HTTP design](FORGE_HTTP_API_AND_TRANSPORT_PARITY_V1.md) already requires
an installed foreground HTTP API, versioned OpenAPI, derived Postman collection
and CI drift rejection (HT-05). Retain FH-CONTRACT -> FH-SERVICES -> FH-HTTP /
FH-CLI -> FH-Q in the [owning DAG](../roadmap/forge-http-api-v1.json).
This refinement supplies aggregate-health acceptance to those SAME nodes. It
does not add a new scheduler, database, Console dependency or canary prerequisite,
and does not decide the separate Console-process-topology discussion.

## Health semantics

Distinguish process liveness, readiness for named capabilities, and aggregate
component health. An HTTP listener answering does not prove planning/execution
readiness. A failed optional access adapter does not imply the runtime is dead.
Use the canonical component registry and existing owning status/application
services; do not maintain a second health-only component inventory.

The versioned response must bind product/version, runtime/installation identity,
observation timestamp and schema revision to a bounded set of checks. Each check
has stable component/check ID, scope, required/optional/disabled applicability,
observed state, bounded safe reason, observation age and timeout information.
Expose aggregate HEALTHY / DEGRADED / UNAVAILABLE / UNKNOWN semantics in the
contract; map existing component states without rewriting their authority.
Paths and exact wire enums are finalized in FH-CONTRACT, not claimed live here.

- HEALTHY: every applicable required check for the advertised scope is fresh
  and passes; an explicitly disabled optional Console/relay is not a failure.
- DEGRADED: some functions remain usable, but a configured optional dependency
  has failed or a particular capability is unavailable. Name usable and blocked
  capabilities; never advertise dispatch as ready when its required peer fails.
- UNAVAILABLE: required checks prove that the requested readiness scope cannot
  serve safely, such as inaccessible canonical storage or unavailable required
  execution capability. Liveness can still be healthy.
- UNKNOWN: missing, stale, timed-out or insufficient observations cannot be
  promoted to a pass. An unknown required check makes that readiness scope false;
  an unknown optional check remains visible and affects aggregate health by the
  declared applicability policy, not arbitrary severity ordering.

FH-CONTRACT defines a tested truth table and HTTP semantics. Liveness may return
200 while capability readiness returns 503. A degraded response may return 200
only for a scope that remains ready and with an explicit degraded body; unavailable
or unknown required readiness returns 503. Authentication/authorization failures
retain their normal status and are never disguised as a healthy empty result.
Startup and maintenance/drain states must be visible without inventing failures.

Separate a minimal non-sensitive liveness response from authenticated diagnostic
readiness/component detail. Never leak credentials, secret references, private
paths, provider output or detailed topology through public probes. Health is
read-only and non-generating: bounded local observations and supported scoped
peer capability reads only, no LLM generation, Mission intake, EP submission,
lease, credential prompt, repair, restart or implicit initialization. Polls may
use bounded freshness-labelled caches; avoid recursive cross-product health
calls, unbounded fan-out and provider-login work. Missing optional endpoints
remain unsupported rather than introducing peer CLI/SQL/Inbox fallbacks.

## Future qualification, within the existing delivery nodes

| Case | Required evidence |
| --- | --- |
| FH-H01 | Healthy, degraded, unavailable, unknown, startup and maintenance truth tables; liveness and per-capability readiness do not collapse into one green status. |
| FH-H02 | Disabled optional relay does not block local work; enabled unreachable relay degrades remote access; required EP outage blocks only dependent readiness. |
| FH-H03 | Required stale/unknown/timeout checks cannot pass; timestamps, bounded caching, request limits and nonrecursive peer observations are exercised. |
| FH-H04 | Public redaction and authenticated detail, wrong instance/scope and denied requests; repeated probes produce zero domain mutations or provider generations. |
| FH-H05 | Real installed HTTP server outside source checkout; OpenAPI, actual method/path/auth/error inventory and Postman cover all supported operations and cases. |
| FH-H06 | Deliberately add/remove/change a route, schema, authorization or error response: CI must fail; a missing/skipped required collection case is not a pass. |

FH-CONTRACT owns response/applicability/auth/HTTP mapping; FH-SERVICES owns real
aggregation; FH-HTTP and FH-CLI expose the permitted projections; FH-Q owns the
six cases and retains HT-01..07. Contract/probe work is usable for Server-only
FSH-SERVICES; it does not wait for Console, Workspace or the universal installer.
Actual service-account startup/reboot evidence remains a separate lifecycle
requirement. No workflow, runtime, schema, service or live authorization changes
are made by this documentation.
