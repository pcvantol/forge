# Forge Server configuration and data operations V1

**Parent:** [Forge Operations Console V1](FORGE_OPERATIONS_CONSOLE_V1.md).
**Status:** PLANNED / POST_AUTONOMY. Documentation and future acceptance only.
**Scope:** the Configuration section of the Forge Server Console, not EP or the
separate Forge Platform installer. This extends the parent allow-list with
explicit, guarded data operations; it does not authorize their execution now.
The [scoped roadmap](../roadmap/FORGE_OPERATIONS_CONSOLE_V1.md) and
[documentary DAG](../roadmap/forge-operations-console-v1.json) track this work.

## 1. Locality and ownership

```text
Host A: Forge Server
  Forge-owned Codex binary + explicitly selected local session context
  Forge-local Python venv + installed forge-autonomy package
  Forge data root: database, identity, journals, evidence and configuration
       |
       | authenticated/versioned contracts only
       v
Host B: EP Server / execution host
  EP-owned Python, Codex, execution tools, state and credentials
```

Forge must not depend on an EP-managed executable or venv, even when both
products happen to run on the same computer. Different hosts and independently
qualified tool versions are supported design requirements, not exceptional
layouts. The browser's host is not the Forge host either. Installation/version
selection belongs to the owning provisioning contract; the console observes
and requests allowed operations, never implements a second installer.

### Forge-local Codex — FC-CODEX

Use an explicitly configured absolute executable from Forge-owned local tooling,
with resolved-path and installation/provenance readback. Reject an EP runtime,
EP-managed binary, symlink to EP tooling, remote-host path or arbitrary PATH
fallback as the Forge provider. A matching version string alone is insufficient.
Removal/update of EP must not remove, replace or retarget Forge's Codex.

Pin the invocation to the selected Forge binary, qualified CLI compatibility,
local OS-user/service identity and Forge-scoped session/configuration context.
The public CLI/session interfaces own authentication. Do not import EP's auth
files, scrape tokens or proxy Forge planning through EP. A Forge-scoped context
must also prevent Forge logout from invalidating an EP session on the same host.
Independence does not require a different subscription/account; do not invent an
API-key purchase requirement or fallback to a different provider.

The card shows Codex path (privileged local diagnostic), version, installation
identity/source when available, service context, supported login state, selected
model/default policy, adapter compatibility, last non-generating preflight and
redacted failure. Separate installed, signed in, model verified and ready.
A model default is not a verified pinned model.

Sign-in/sign-out controls, when supported by an owning backend operation, use
explicit local consent and current authority. Show target/session impact before
logout; reject or safely defer it during active/uncertain work. No hidden logout
on page refresh, no token in a URL/browser store and no automatic account switch.
Unsupported auth controls stay disabled with a reason. Installing/updating the
binary remains outside direct browser/shell execution.

### Forge-local Python — FC-PYTHON

Forge uses its own venv, not EP's venv, a source-checkout environment or an
unqualified shell python. The qualified base interpreter may be shared as a
system dependency; the venv, packages and release binding are Forge-specific.
No required equality with EP's Python or Codex version is introduced.

Show actual executable, resolved base interpreter, Python version/architecture,
venv prefix, installed Forge distribution/version/module location, source and
artifact identity, compatibility and read-only health. Detect a loaded-module/
wheel mismatch and stale interpreter process rather than trusting a directory
name. Local filesystem paths are visible only to the authorized administrator;
logs/exports intended for sharing redact them.

Label this card Forge runtime environment. It does not claim that EP repository
validation ran in this interpreter; EP retains validation/execution authority.
Code/runtime tooling roots are separate from the data root. Exporting or moving
Forge data must not move a venv or copy a host-specific Codex installation.

## 2. Forge data root and maintenance

The card shows the resolved Forge data location, database size, durable storage
size where measurable, actual schema, integrity result/time, instance identity,
last successful operation, pending operation and maintenance schedule/result.
Do not copy the EP screenshot's path, size, schema or current health values.
No arbitrary database browser/editor is introduced.

Forge owns archive/schema/integrity semantics and typed data-operation services.
Forge Platform retains normal installation and OS-service restart choreography;
it consumes published product-owned operations instead of peer SQL. The console
requests those services and displays their receipts. Missing routes are future
implementation work, not permission to shell out or mutate files directly.
This distinction preserves the [Server deployment contract](FORGE_SERVER_DEPLOYMENT_TARGET.md).

### Shared data-operation contract — FC-STATE

Bind each operation to actor, current authority, exact instance and resolved
source/destination, expected configuration/storage revision, operation ID and
immutable request digest. Preview effects and confirm explicitly; a generic
settings Save does not authorize restore or relocation. Validate paths,
permissions, capacity, archive contents and compatibility before changing state.

Coordinate all writers with the owning runtime: provider permits, callbacks,
configuration and reconciliation are relevant, not just an empty Mission queue.
Use a consistent snapshot or quiesced boundary. Record progress/checkpoints and
resume the same operation after interruption. An accepted request is not a
completed operation; require authoritative final identity/integrity readback.
No backup restore to erase attempts, budget use, expiry or external effects.

Browser polling remains read-only. The server may perform explicitly authorized
data work behind its typed API; this does not give the browser SQL/filesystem
access. Validate every import path against traversal, symlink escape, expansion
limits and unexpected payloads. Never execute code from an archive. Snapshot
hashes prove byte integrity, not trusted provenance or execution authority.

### Export platform data — FC-EXPORT

Produce a versioned, integrity-verifiable consistent archive of Forge-owned
state and required durable referenced artifacts: database, identity metadata,
configuration references, journals/evidence and the retention-defined history.
Declare included/excluded entries and per-entry digests in a manifest with
source schema, product/source revision, instance identity and snapshot time.
Do not copy a live SQLite main file alone or include transient locks as durable
truth. Use the owning qualified snapshot protocol for all related state.

Exclude secret values, Keychain entries, Codex/session auth material, provider
credentials, caches and installed tooling/venvs. Reject or sanitize unexpected
secret-bearing data without silently corrupting an integrity-bound evidence
record; report unexportable entries explicitly. Keep opaque references and
public trust/provenance records only as allowed by the archive contract.
A recovery archive still contains private Mission/project data: restrict access
and storage/transport. It is not the redacted diagnostic/log-export product and
must not be offered as a public shareable link.

### Import platform data — FC-IMPORT

Inspect/stage first: format, digests, trusted provenance, complete referenced
files, schema compatibility, source/target identity and required migrations.
Show a preview and an explicit destructive-impact confirmation. Back up the
current target consistently before applying an authorized restore. Reject
unknown/newer unsupported schemas; only existing qualified migration routes
may be used. No blind merge into an unrelated instance and no bootstrap grant.

Restore/recovery preserves the intended instance and immutable lineage, but a
stale snapshot is not current authority. Fence the old writer and require
current expiry, operator/host binding, budget and EP-side-effect reconciliation
before any generation/submission resumes. Never restore consumed permits to
usable ones or blindly replay pending dispatch. If current state cannot be
reconciled, keep the restored instance recovery-blocked/read-only.

Cross-host recovery must not produce two active copies of one identity. Local
credentials are not portable archive content: re-resolve/rebind them only via
explicit owning authentication/trust routes; no automatic EP-credential issuance.
Record final integrity, instance/configuration readback and restore provenance.
Keep rollback evidence; do not silently discard newer history or successful EP
work merely because it is absent in the snapshot.

### Relocate platform data — FC-RELOCATE

Relocation moves the authoritative data root, not the installation or Mission
meaning. Validate canonical paths and conflicts, quiesce/fence writers, take a
consistent backup, stage/copy the durable data, verify identities/digests and
integrity, then atomically cut over through the owning resolver/service contract.
Reopen the same instance and verify state, configuration and evidence. Ensure
all configured launch/operational references use the new resolved root, not a
new CLI override while a background process still uses the old one.

The old root becomes a retained non-writer, not an automatic fallback or deletion
target. Runtime/installation identities, grants, attempt counters and expiry do
not reset. Failure before cutover leaves the original authoritative; failure
after cutover reconciles the recorded operation and never starts dual writers.
OS stop/start, when needed, uses the separately authorized provisioning route.
Neither this button nor restoration can migrate or edit EP CENTRAL.

### Database maintenance interval (VACUUM) — FC-VACUUM

Provide an explicit durable maintenance interval and disabled option, with last
attempt/result, last success, next due time, duration and postponed reason.
The screenshot's one-hour setting is a reference example, not a measured Forge
requirement or a silently applied default. Select/document the shipped default
when performance and safe-maintenance qualification exist.

The interval makes maintenance eligible, not entitled to interrupt execution.
The Forge maintenance service rechecks exclusive safe access and storage/space
conditions before VACUUM; postpone while relevant work/writers are active.
Coalesce missed intervals; no catch-up storm, forced session kill or duplicate
maintenance workers. Bound execution and verify integrity afterwards. Preserve
logical records, evidence, budgets and identity; VACUUM is not pruning, retention
delete, schema migration, backup or a Mission. Observation never starts it.

## 3. Console refresh settings — FC-REFRESH

Provide separate controls for:
- refresh interval of an opened component detail;
- Operations Console status-update interval.

The screenshot's 5 seconds / 1 second are presentation examples; the future
backend must declare supported ranges, shipped defaults and effective values.
Persist only non-sensitive viewer/instance-scoped presentation preferences; any
server-wide sampling policy is a separate authorized operational setting.
Display configured versus effective interval when backoff/rate limits apply.

Refresh only visible/selected authorized data, coalesce overlapping reads and
back off on failure. Do not spawn a new Codex login/version subprocess, Keychain
prompt or expensive integrity scan each second: reuse freshness-labelled,
bounded server observations. Closing a detail cancels its dedicated polling.
Auto-refresh OFF stops automatic view updates, not Missions, logs, maintenance
or server work; manual refresh stays available. Reconnect must not discard
unsaved configuration or replay operations. Refresh settings do not alter an
AI timeout, EP poll contract, lease, authority expiry or retry budget.

## 4. Forge provider timeout policy — FC-TIMEOUT

### Source observations, not installed readback

Inspected Forge source: `4b5afb909b1f7a1a90abcbdb25a8621f4d542218` on 2026-09-12
UTC. Source references below are pinned. Existing source fields are distinguished
from future UI/service work; no local runtime setting was read or changed here.

| Operation | Observed source behavior | Console treatment |
| --- | --- | --- |
| Initial Action derivation and evidence-driven replanning through Codex | `PlanningProviderInvocationPolicy.timeout_seconds` is loaded from Forge-owned policy and passed to the Codex subprocess; the same provider policy applies to both. | Relevant Forge AI-call timeout. Show configured/effective value, provider, origin/version and enforcement scope. Allow changes only through the authorized versioned service; do not invent separate phase fields. |
| Codex version and login-status preflight | Two separate non-generating calls, each `timeout=5`. | Fixed/source-managed probe deadlines, shown separately from generation; not editable absent a product setting. |
| Optional Responses provider: token-count preflight and generation | Each distinct HTTP request uses the same configured `timeout_seconds`. | Relevant only for that configured provider. Distinguish count and generation; an HTTP timeout is not proof of one end-to-end Mission deadline. Do not enable an API-key provider by this design. |
| Forge-to-EP transport/readback | Peer configuration has its own `timeout_seconds`, validated as greater than zero and at most 60 seconds. | Connection/transport setting, not an AI-call or EP execution timeout. |
| Deterministic proposal validation, evidence verification, reconciliation and completion | These are not made AI calls by the planning-provider interface. | No copied LLM phase timer. If a future real provider call is added, declare and qualify its own operation first. |
| EP specialist review, implementation, local validation, autonomous quality, repair, finalization, final reconciliation | These screenshot phase categories belong to EP execution, not Forge's planning adapter. | Exclude from Forge-editable provider policy. Any later informational EP view must remain clearly EP-owned. |

Evidence: [policy/configuration](https://github.com/pcvantol/forge/blob/4b5afb909b1f7a1a90abcbdb25a8621f4d542218/forge/provider_security.py),
[Codex calls and diagnostics](https://github.com/pcvantol/forge/blob/4b5afb909b1f7a1a90abcbdb25a8621f4d542218/forge/planner/codex_cli_session.py),
[Responses calls](https://github.com/pcvantol/forge/blob/4b5afb909b1f7a1a90abcbdb25a8621f4d542218/forge/planner/openai_responses.py),
[provider interface](https://github.com/pcvantol/forge/blob/4b5afb909b1f7a1a90abcbdb25a8621f4d542218/forge/planner/provider_adapter.py),
[peer timeout](https://github.com/pcvantol/forge/blob/4b5afb909b1f7a1a90abcbdb25a8621f4d542218/forge/execution_host_configuration.py).

Current Codex source accepts an absolute executable path and probes it; this
alone does NOT enforce Forge-owned installation/session isolation. FC-CODEX is
therefore a real future qualification requirement, not already delivered proof.
The provider generation timeout is not the whole call wall time: setup, the two
readiness probes and cleanup are distinct. Timeout/cancellation does not prove
that remote generation never happened. Retain typed diagnostics and attempt
lineage; no automatic retry or new budget from changing the timeout.

Changes require expected policy revision, operator authorization, audit and
readback. A committed generation uses its bound policy: reject/defer mutation
as the owning service requires. Do not extend programme expiry, EP phase limits,
Mission scope or counters. Token/context/output fields remain separate; never
claim Codex spend/token enforcement solely because those fields are configured.
Future advisory/learning-provider calls may have per-purpose policy only when
an actual call contract exists; no seven-row EP timeout clone is justified.

## 5. Delivery and qualification

All FC work packages in the documentary DAG remain PLANNED under the existing
FOC nodes. Read-only delivery includes truthful runtime/tool/data/timeout cards;
mutation buttons are disabled until their exact owning backend is qualified.
FOC-5 requires the guarded configuration and data operations, not just button
rendering. FOC-Q additionally proves two-host separation, EP removed/upgraded
without breaking Forge, cross-host credential non-portability, export/import
and relocation crash recovery, stale-snapshot safety, deferred maintenance,
refresh/load behavior and timeout/retry semantics.

Use isolated acceptance state, never the real canary. Source/documentation PASS
is not installed/live operation PASS. Keep this work outside MISSION-0006 and
first-E2E recovery; no installer programme is resumed by documenting it.

At the opening snapshot, PR #86 (`f6b684d776e5fda9a40afef87c751e8a3689e926`) was
PENDING_PR, not assumed merged/installed support. Before publication, refreshed
main `c4fed4c4321297746524c4c461b9a81dc42a0277` integrates that journal through
PR #87. The [canonical logging contract](FORGE_OPERATIONAL_LOGGING_CONTRACT.md)
now provides `operational_log_page()` and `record_operational_event()`; reuse
those owning projections/writers, not a second journal. This records source
integration, not installed runtime proof. No existing log implementation was
changed by this documentation. Peer ownership reference:
[Forge Platform matrix](https://github.com/pcvantol/forge-platform/blob/cb6a10a4ffca90e2b689af62349da2075fe47a77/docs/architecture/OWNERSHIP_MATRIX.md),
source-pinned observation on 2026-09-12, not peer implementation authority.
