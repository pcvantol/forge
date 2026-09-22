# Forge AI Mission Planner 4.5

## Purpose and boundary

The AI Mission Planner continuously transforms one Architecture Workspace
Mission that is `approved_for_engineering` into tactical Engineering Intents
and the smallest executable Engineering Actions. It plans only: Forge Runtime
and the Execution Host continue to render prompts and perform execution.

```text
Mission → Action Derivation → Deterministic Validation → Graph Materialization
  → Engineering Intent → Engineering Action
  → Runtime Prompt Renderer → Execution Host → Repository → Execution Evidence
  → Repository Truth → Mission Planner
```

Business Workspace determines what should be built. Architecture Workspace
determines how it may be engineered. Mission Recommendation remains an
advisory Portfolio responsibility. The Planner neither recommends a Mission,
changes Mission objectives or business value, changes architecture constraints,
approves work, invokes an AI provider, produces a Runtime Prompt, nor executes.

## Internal stages and authority

The approved Mission remains the sole planning authority. Action Derivation is
an interface-neutral, provider-optional reasoning stage: it receives only an
immutable digest-pinned Planning Snapshot and returns untrusted rich planning
proposals. Deterministic validation checks snapshot freshness and provenance,
Mission scope, write authority, human gates, risk inputs, dependencies and
cycles. Only validated proposals are projected into the existing deterministic
materializer. A need for authority outside the Mission becomes
`GOVERNANCE_REFINEMENT_REQUIRED`, never a wider Action.

Provider, CLI, Workspace, MCP, chat and raw provider output are not planning
authority. A provider's identity/model are provenance only.

Required human gates and risk inputs are approved policy, not provider-owned
choices. The transport schema limits their array length and members, but the
supported strict-schema subset cannot express that every enum member occurs
exactly once. After parsing, Forge therefore verifies the bounded shape and
allow-list and binds each proposal to the complete canonical required set.
Unknown values and malformed cardinality fail closed. Deterministic validation
then checks the canonical binding again before graph materialization. This
prevents repeated allowed values from silently omitting an approved gate or
risk without granting the provider any new authority.

## Durable provider-return boundary

The installed dynamic runtime records an Action-Derivation attempt before it
crosses an external provider boundary. The attempt binds the runtime and
installation, Mission/revision, planning-snapshot digest, configured provider
revision/effective-policy digest, generation-request digest and typed
derivation-request digest. The claim is single-writer: a concurrent starter
must reconcile the existing attempt and cannot create a second provider call.
No SQLite write transaction remains open while the provider process runs.

After a confirmed provider return, Forge stores a bounded, versioned typed
result before deterministic validation begins. The result is `PROPOSALS`,
`GOVERNANCE_REFINEMENT`, or `CONTRACT_INVALID`; all remain untrusted provider
input. The receipt binds its immutable attempt digest, configured
provider/model/adapter, policy revision, generation request and typed
derivation request before it is accepted. Prompts, raw CLI output,
tool/reasoning transcripts, credentials, traceback messages and locals are
not stored; bounded provider fields that are oversized or prompt/credential
shaped are rejected rather than redacted into a different proposal.

The public installed readback is:

```python
InstalledDynamicMissionRuntime.action_derivation_readback(mission_id: str) -> tuple[dict[str, object], ...]
```

It exposes safe attempt, phase and digest metadata only. It never exposes the
payload and never starts, resumes or dispatches work. Processing phases make
at least `ATTEMPT_RECORDED`, `GENERATION_IN_PROGRESS`,
`GENERATION_MAY_HAVE_HAPPENED`, `RESULT_AVAILABLE`,
`GOVERNANCE_REFINEMENT`, `DETERMINISTIC_REJECTION`, `VALIDATED`,
`MATERIALIZATION_FAILED`, `MATERIALIZED`, and
`CONFIRMED_RESULT_UNAVAILABLE` distinct. A confirmed invocation remains
confirmed even if result storage, validation or materialization later fails.
`CONTRACT_INVALID` is retained as a bounded typed receipt and becomes an
explicit deterministic rejection; it is never rewritten as governance
refinement. `GENERATION_MAY_HAVE_HAPPENED` is likewise not downgraded merely
because no Action was materialized.

On installed `start` or `resume`, an available result is integrity-checked and
replayed through the same current deterministic validation rather than
invoking the provider. A materialized result is not materialized again. A
running, ambiguous or confirmed-but-unavailable result blocks automatic
generation; `CREATED` alone is never a reason to regenerate. Governance
refinement and deterministic rejection become explicit blocked outcomes, not
an Action or a generic success.

The Mission-state Action/intents/planning-history update and the attempt's
`MATERIALIZED` mark commit in one runtime-database transaction. Thus a process
loss before caller acknowledgement leaves either neither change or both; a
reopen cannot create a second Action set from that attempt.

Old audit-only evidence is not retroactively converted into a typed result.
Before a first durable claim, Forge checks immutable external-session audit
evidence for the same planning snapshot and provider. A linked
`HAPPENED_AND_CONFIRMED` row is read back as
`LEGACY_EXTERNAL_SESSION_AUDIT` / `CONFIRMED_RESULT_UNAVAILABLE` and blocks
automatic generation. It creates neither an attempt record nor a payload;
insufficient linkage remains an explicit reconciliation requirement, never a
reconstructed proposal or invented result kind.
For a Mission that is still `CREATED`, the readback's `audit_id` may be used
as an explicit legacy predecessor only when it is the sole confirmed audit for
the exact Mission snapshot/provider, its external-session configuration binds
the same provider, and its request digests are complete. Forge records only a
new authorization and successor lineage that references that immutable audit;
it does not backfill a historical attempt, result kind, validation or old
authority. A different-Mission, malformed, or ambiguous audit is not
authority and fails closed.
Pre-durable `action_derivations` rows likewise read back as
`LEGACY_ACTION_DERIVATION_RECORD` / `LEGACY_RECONCILIATION_REQUIRED`; they do
not make a new attempt safe merely because they lack a replay payload.

When, and only when, a confirmed unavailable result is not replayable, the
installed public operation

```python
InstalledDynamicMissionRuntime.authorize_next_planning_attempt(
    mission_id: str, *, predecessor_attempt_id: str | None = None,
    predecessor_audit_id: str | None = None, rationale: str,
) -> dict[str, object]
```

records a native-operator-authorized successor reservation and an immutable
canonical `OWNER_PROGRAMME_AUTHORIZATION` decision for that exact predecessor.
Exactly one predecessor argument is required. `predecessor_attempt_id` names a
durable confirmed-result-unavailable attempt; `predecessor_audit_id` names the
safe `audit_id` emitted by a uniquely linked legacy readback. The latter is an
explicit new-generation authority, never a reconstruction or replay of the
old provider response.
It checks the
same Mission and semantic planning facts (the approved Mission, criteria and
non-bookkeeping evidence), no active Action or dispatch, binds predecessor and
successor identities, records a bounded reason/rationale, and does not invoke
a provider. A predecessor may have one such reservation. This is an explicit
new-generation authority, not replay, and is deliberately not consumed by a
readback, ordinary `start`, or ordinary `resume`.

Only the separate operation

```python
InstalledDynamicMissionRuntime.resume_authorized_next_planning_attempt(
    mission_id: str, *, successor_attempt_id: str,
) -> DynamicMissionRunResult
```

can atomically consume that exact reservation once. It rechecks the current native
operator, successor/predecessor linkage, semantic planning facts, provider
policy provenance and zero-Action/no-dispatch condition before it reaches the
provider. If a process stops after the one-time consume and durable result
write, the same operation replays that result without a second provider call.
It materializes only a valid Action set; it does not dispatch to EP.
For the narrowly supported legacy-audit predecessor, the original Mission may
remain `CREATED` with zero Actions; the reservation itself is still explicit,
one-time, and independently authorized. Ordinary `CREATED` Missions and all
other successor sources remain unable to use this continuation route.
The normal public resume route remains the sole route to that later transport.

`scripts/qualify_durable_installed_surface.py` is the non-generating artifact
qualification entry point. It is run with an installed wheel's interpreter
outside the checkout against an isolated runtime root; it configures only the
non-secret external-session record, opens the public runtime, and proves that
readback/resume reject an absent Mission without invoking a provider. Its EP
host boundary is controlled in-process because this is planner qualification,
not an EP credential or transport test.

## Inputs and determinism

`MissionPlannerInput` accepts only an approved Architecture Mission, its
Mission Planning State, an explicit Approved Scope map, and digest-pinned
Planning Evidence. The evidence allow-list includes Mission State, Repository
Truth, Architecture Review, Capability Catalogue, refinement, maturity,
engineering history, historical Intents and Actions, and Execution Evidence.
It has no type for conversations, temporary Runtime Prompts, or Execution Host
implementation details. Repository Truth is required and remains authoritative.

The planner canonicalizes every input and derives its plan identity from a
SHA-256 digest of that canonical value. Identical Mission, State, Repository
Truth, Architecture Review, and Execution Evidence therefore produce exactly
the same Intent plan and Action order.

## Boundaries and continuous planning

Architecture Mission boundaries begin as reviewed text. Before planning, each
boundary must have an `ApprovedScope` mapping with a Mission-required
capability, architecture references, and explicitly permitted atomic Action
definitions. The mapping must cover exactly every approved Mission scope; an
unknown capability, missing scope, duplicate Action, unapproved Mission, or
missing required evidence is rejected. This is the fail-closed enforcement
boundary rather than a free-text interpretation.

After a completed Action, persisted Mission State and Execution Evidence join
the next Repository Truth snapshot. `replan` removes completed Actions,
retains blocked Actions as blocked, and preserves explicitly postponed Actions
as deferred. A scope may split into its declared action definitions; definitions
with one explicit `merge_key` become one bounded Action. Their declared
priorities determine order. The Planner does not dispatch any of them.

## Planner-owned records

Every `PlannedEngineeringIntent` contains its objective, rationale,
architecture references, capability impact, validation strategy, expected
repository evidence, and owned generated Actions. `EngineeringAction` remains
the Runtime Prompt Renderer's smallest executable unit, but creation remains
planning—not execution or approval.

## Out of scope

No OpenAI, Claude, Gemini, LLM invocation, Runtime, Execution Host, Forge
Studio, Business approval, Architecture approval, Mission Recommendation, or
repository operation is implemented.
