# Aggregate health and HTTP qualification V1

**Owner:** Forge. **Status:** PLANNED refinement of existing F2/FH, NO_BUMP.
The owner requested an aggregate health endpoint with degraded checks on
13 September 2026. Source baseline: `1cea418a5fa8f59d303f2a0d6ff27573c4a11752`.
This is a backlog acceptance contract, not implemented routes or live evidence.

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

## Implemented installed snapshot slice

The installed Server now exposes one bounded read-only assessment as
`forge --data-root ROOT health snapshot` and authenticated `GET /v1/health`.
Both transports consume the packaged
`forge/api/installed-health-component-registry-1.0.json` registry and the same
collector. The response binds registry version and digest, the
`validation-profile-registry:FULL@1.0` profile, runtime and installation
identity, observation provenance, and one of the distinct healthy, failed,
stale, expired, missing, timed-out, future, or unknown outcomes.

The collector reads only the installed identity marker, runtime metadata,
durable operational-reset maintenance state, dispatcher state, schema revisions,
and one bounded SQLite integrity result. Installation bootstrap persists a
distinct installation identity before operator binding, and the collector never
substitutes shared repository identity. Active maintenance is a required failing
readiness observation while liveness remains visible. The collector
uses an immutable read when no SQLite sidecars exist and a bounded temporary
copy when an active WAL snapshot exists, so the installed database, WAL, and SHM
are not changed. It does not query Mission or execution records or import a
provider. Registry and runtime schemas newer than the supported reader are
rejected. This is the installed-health slice only; it does not claim the other
FH-Q cases or service-account/reboot qualification complete.

The wall-clock timeout covers resolution, registry and marker reads, snapshot
copying, SQLite observation, response construction, and cleanup through a
terminable collector-process boundary. Integrity observation has a smaller
sub-deadline so a timed-out integrity check can still be returned and the
snapshot can complete within its outer bound. The canonical registry supplies
observation expiry policy separately from freshness timeout, allowing stale and
expired evidence to remain distinct. A missing dispatcher row produces a
missing required observation; it is never synthesized as an idle dispatcher.
Runtime installation identity is reconciled with any durable operator binding
and protected against both update and deletion.
