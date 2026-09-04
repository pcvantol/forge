# Forge V1 Productization Decision Contract

**Status:** Canonical V1 decision contract; implementation and qualification remain separately governed.

## Baseline and gate closure

This closes the *decision* portion of `FWV1-G001`, `G003`, `G005`, `G007`,
`G008`, `G009`, `G010`, `G011`, and `G013`; their implementation and
qualification evidence remain open. The [gap register](FORGE_WORKSPACE_V1_GAP_REGISTER.md)
retains their identifiers and owners. Every decision below preserves the
[Productization Reconciliation](FORGE_PRODUCTIZATION_RECONCILIATION.md).

| Gate | Owner | Decision | Later proof |
| --- | --- | --- | --- |
| G001/G010/G011 | Forge, Workspace, EP | separate installed processes, identities and authenticated APIs | clean-install/security canary |
| G003 | EP protocol; Forge integration | idempotent explicit attachment/read-back | attach/adopt/recover qualification |
| G005 | Forge graph; EP admission | multi-repo project; EP repository write lease | isolated/cross-repo delivery canary |
| G007-G009 | owners by record | owner-specific retention, recovery and deletion | crash/restore/retention qualification |
| G013 | Workspace | authenticated responsive control plane with degraded read-only UX | accessibility/control-plane Golden |

## Topology, identity and access

Forge Runtime Service, EP Server and Workspace Server are separate,
independently restartable and independently versioned processes, even when
installed on one machine. EP Agents are EP-managed processes. Workspace client,
CLI and MCP are clients. Forge and EP continue while Workspace is closed.

Each installation creates random opaque stable IDs for `machine`, Forge service,
EP service, Workspace client, Agent, Project and Repository. User identity is
provided by the authenticated Workspace/CLI/MCP principal; display names and
hostnames are metadata only. Reinstall creates service/machine identity unless
a restored encrypted identity/operational backup is explicitly adopted.
Rotation revokes prior credentials and records audit evidence.

V1 supports same-machine authenticated loopback and private-overlay access;
LAN and arbitrary remote listeners are disabled by default and require TLS,
explicit endpoint configuration and the same authentication policy. Browser
origins are allow-listed and mutation requires CSRF protection. Local secure
stores hold bearer/client credentials; credentials never enter repository
records, portable contracts, events or logs. Every service call authenticates
the caller, authorizes project scope and records actor/correlation/audit.

`FORGE_RUNTIME_PROCESS_MODEL = DECIDED`  
`EP_RUNTIME_PROCESS_MODEL = DECIDED`  
`WORKSPACE_RUNTIME_MODEL = DECIDED`  
`IDENTITY_MODEL = DECIDED`  
`V1_SECURITY_MODEL = DECIDED`  
`UNAUTHENTICATED_REMOTE_MUTATION = FALSE`

Threat response is fail-closed for unauthenticated/malicious clients, forged
service identity, stale/replayed idempotency keys, stolen credentials,
cross-project/confused-deputy requests and unauthorized submissions. Compromised
Workspace/MCP clients receive only their scoped authority; MCP cannot approve
or execute. Credentials are revocable, redacted and auditable.

## Attachment, repositories and delivery

A Forge governed attach intent names immutable `project_id` and one or more
`repository_id`s; no CWD, folder, first-project, remote or UI selection is
authority. Forge requests EP registration; EP validates/adopts and returns an
immutable registration/attachment ID. Forge persists only that reference after
read-back. Repeated equal requests return the same result; mismatch, cloned,
moved, unknown, deleted or conflicting metadata becomes `ADOPTION_REQUIRED`,
`DRIFTED`, `BROKEN`, `DETACHED` or `RECOVERY_REQUIRED`, never silent repair.

One Project may contain multiple repositories with role, canonical location
metadata, remote metadata, managed status, attachment state and execution
eligibility. Forge plans dependencies; EP owns the sole repository write lease
(`repository_id`, worktree/branch, Action, Agent, expiry, renewal/release and
crash recovery). One mutating lane per repository is V1; cross-repository
Actions are ordered and independently delivered, with Mission completion based
on final multi-repository Repository Truth and DoD. No distributed transaction.

`PROJECT_ATTACHMENT_PROTOCOL = DECIDED`  
`PROJECT_ATTACHMENT_IDEMPOTENT = TRUE`  
`ATTACHMENT_DRIFT_POLICY = DECIDED`  
`MULTI_REPOSITORY_V1_POLICY = DECIDED`  
`REPOSITORY_WRITE_LEASE_OWNER = EP`  
`DUAL_EXECUTION_LEASE_AUTHORITY = FALSE`  
`MULTI_REPO_DELIVERY_MODEL = DECIDED`

## API, Workspace and operational model

Forge application contracts are versioned independently from transport:
`v1` query, intent, event and error envelopes carry schema version, project,
actor, correlation, cursor/page, provenance and capability discovery. Every
mutation requires expected version/precondition and idempotency ID; conflicts
return a stable conflict result, never last-client-wins. Unsupported versions
fail closed with supported versions/capabilities. Workspace calls Forge for
Forge-owned queries/intents/events and EP directly for EP-owned queries/control;
Forge is not an EP proxy. Workspace neither reads Forge DB nor duplicates rules.

Forge owns one installation operational store, partitioned by project, with
versioned migrations and backup/restore. It stores runtime/product state,
cursors, proposals, sessions, projections, jobs, service metadata and attachment
references; repository-local DBs are never authority. Decisions, approvals,
Mission lineage and provenance are backup-required; projections/cursors are
rebuildable; EP evidence remains EP-owned reference; transient chat is
ephemeral unless submitted proposal/session provenance is retained. Loss never
invents approvals; restore uses backup plus repository truth and EP references.

`FORGE_API_VERSIONING_MODEL = DECIDED`  
`STALE_CLIENT_SILENT_OVERWRITE = FALSE`  
`ADAPTER_SPECIFIC_MUTATION_AUTHORITY = FALSE`  
`WORKSPACE_FORGE_INTERACTION = CANONICAL_API`  
`WORKSPACE_DIRECT_FORGE_DB_ACCESS = FALSE`  
`WORKSPACE_EP_INTERACTION = CANONICAL_EP_API`  
`FORGE_IS_NOT_GENERIC_EP_PROXY = TRUE`  
`FORGE_OPERATIONAL_STORE_AUTHORITY = DECIDED`  
`REPOSITORY_LOCAL_FORGE_OPERATIONAL_DB = FALSE`  
`HISTORY_RETENTION_MODEL = DECIDED`  
`FORGE_RECOVERY_MODEL = DECIDED`

## Workers, proposals, projections and qualification

Repository Truth and EP receipt observers are event-driven where available with
cursor-based reconciliation fallback. Scheduler, Portfolio Intelligence,
Quality/Knowledge observers and Roadmap/Forecast projector use durable jobs,
idempotency keys, checkpoints, bounded retry/backoff and operator attention on
ambiguity. Only Scheduler may create Forge submission intent; observers propose
only. Recommendation -> Candidate Proposal -> registered Candidate -> explicit
Business/Architecture approvals -> Mission Intake; no worker creates an
executable Mission. Forecast is a materialized, invalidation-driven projection
with input versions, confidence and uncertainty.

Business/Architecture sessions retain messages, context snapshot, provider
provenance, structured proposals, dispositions and resulting decision evidence;
transcript text is not authority. Workspace reconnects from cursors, labels
staleness, permits offline read-only cache and presents conflicts/service loss.
Control-plane qualification must prove Workspace->Forge query/intent,
Workspace->EP query/control, Forge->EP->receipt->projection, and Forge operation
while Workspace is closed. Packages include schemas, baseline/policy/migration,
capability/API and qualification metadata; peers negotiate versions and fail
closed when unsupported.

`BACKGROUND_WORKER_MODEL = DECIDED`  
`AUTONOMOUS_EXECUTABLE_MISSION_CREATION = FALSE`  
`MISSION_CANDIDATE_GENERATION_CONTRACT = DECIDED`  
`ROADMAP_DAG_OPERATIONAL_CONTRACT = DECIDED`  
`FORECAST_OPERATIONAL_CONTRACT = DECIDED`  
`CHAT_TRANSCRIPT_IS_AUTHORITY = FALSE`  
`BUSINESS_REFINEMENT_SESSION = DECIDED`  
`ARCHITECTURE_REFINEMENT_SESSION = DECIDED`  
`WORKSPACE_ACCESSIBILITY_MODEL = DECIDED`  
`WORKSPACE_CLOSED_FORGE_CONTINUES = TRUE`  
`CONTROL_PLANE_QUALIFICATION_CONTRACT = DECIDED`  
`CLEAN_INSTALL_SELF_CONTAINED = TRUE`  
`CROSS_PRODUCT_VERSIONING_MODEL = DECIDED`
