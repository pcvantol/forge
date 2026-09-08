# Governed progression and delivery authority

## Decision and status

Increment: `GOVERNED_PROGRESSION_AND_DELIVERY_AUTHORITY_V1`.
Capability target: `FORGE::GOVERNED_PROGRESSION_V1`.
This is a coordinated architecture/roadmap increment, canonical on each owning
main after merge and otherwise PENDING_PR. It implements no resolver, API,
workflow, external integration or deployment and activates no policy or grant.

This elaborates [policy governance](POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES.md),
[the product lifecycle](product-model.md), [Governance Profiles](governance-model.md)
and [Mission architecture](engineering-mission.md). It groups the previously
proposed gate-resolution/execution-governance ideas under one capability; those
names do not denote extra parallel engines. Reuse existing ExecutionPolicy,
profile resolution, governance persistence, Action/evidence and decision seams.
See [the scoped roadmap/DAG](../roadmap/GOVERNED_PROGRESSION_V1.md).

## Three gate families, separate authority

| Family | Meaning | Owner of decision/enforcement |
| --- | --- | --- |
| Lifecycle governance | Business approval of Candidate, Architecture approval for Engineering | Forge governance contract and assigned human authorities |
| Engineering progression | Review after Action/Intent/Capability, at Mission end, or supported custom boundaries | Forge resolves effective progression policy and blocks successor release |
| Delivery/promotion | Permission before publish, store submission, install, deploy or irreversible migration to an exact target | The declared project/organization delivery or approval authority; never assumed by Forge |

Mission Intake validates an already approved Mission; Candidate intake/refinement
precedes Business and Architecture approval. Those approvals remain separate and
explicit, including under Solo. Governance Profiles supply defaults/assignments,
not permission to remove lifecycle stages or infer approval from maturity.
Human review, automated quality/security review, technical qualification, merge
approval and production approval are distinct obligations. One does not
implicitly replace another.

## Ownership invariant

Forge plans what/why/next, resolves its governance requirements and reconciles
authoritative evidence. EP admits and executes bounded engineering Actions,
qualifies candidates and produces execution evidence. Workspace presents/routs
permitted decisions, records the human interaction and submits it to the owning
service; it is not the final authority for Forge state or external deployments.
Forge Platform owns qualified product distribution/installation composition,
not every project's CD system. Existing external CD owns its own approvals,
execution, production credentials, publication and rollback unless the project
explicitly delegates a bounded operation through its approved control contract.

```text
HUMAN_GATE_REQUIREMENT != HUMAN_GATE_AUTHORITY
TRIGGER_PERMISSION != APPROVAL_PERMISSION != DEPLOYMENT_PERMISSION
WORKSPACE_PRESENTATION_DOES_NOT_TRANSFER_AUTHORITY = TRUE
EXTERNAL_DELIVERY_AUTHORITY_PRESERVED = TRUE
```

## Project defaults and Mission assignments

A progression profile declares cadence, review scope, required role/decision,
applicable evidence, supported boundaries and permitted overrides. Supported
cadences include continuous, after Action, after Intent, Capability boundary,
Mission-end review and explicit custom boundaries. These are not a universal
ordered scale: allowed combinations and override bounds are defined by policy.
Mission-end acceptance and continuous intermediate progression are independent
fields/obligations, not contradictory enum shortcuts.

Resolve product invariants + applicable organization/project requirements +
project default + approved Mission assignment + mandatory context/risk rules +
current grants/capability. Distinguish a default from a non-overridable obligation.
A Mission may select a less frequent review only where the higher-scope policy
permits that override and the actor is authorized. Free-form Mission/prompt text
cannot turn off required gates. Selecting Solo does not mean every project must
run continuously; selecting Enterprise does not fix every prototype to per-Action
review. Missing or conflicting assignments are not an autonomous default.

Examples are target profiles, not active configuration:

| Project/Mission | Intermediate cadence | Final review | Exceptional/target gates |
| --- | --- | --- | --- |
| Disposable prototype | Continuous | Mission acceptance required | Still enforce scope, security and delivery restrictions |
| Production-critical engineering | After every Action | Applicable Mission acceptance | Still enforce separate before-PROD gates |
| Prototype Mission in stricter project | Mission-specific override if permitted | As explicitly assigned | Cannot waive project mandatory controls |

No cadence setting weakens EP assurance, increases repair allowance, authorizes
merge/publish or changes the Mission boundary. Policy/grant/runtime consumption
remain distinct. Risk assessment may inform classification; a model cannot
approve its own exceptions or reinterpret PROD as TST.

## Boundary resolution and successor fence

Before the applicable lifecycle/progression transition, Forge derives an
Effective Governance Requirement set from pinned policy and current evidence.
Persist each requirement identity, type, boundary, blocking scope, required
roles/authority, policy/evaluator references, subject revision/digest, evidence
requirements, rationale codes and invalidation rules. Materialize requirements
before work is released, not after discovering an unauthorized side effect.

For after-Action review:

```text
EP Action A terminal evidence -> Forge verifies/reconciles A
 -> evaluate the Mission's progression boundary
 -> CONTINUE, or persist a blocking DecisionRequirement
 -> Workspace shows the owner-authorized decision
 -> owning service validates decision/authority and exact subject
 -> Forge may derive/release the next bounded Action
```

Forge may collect evidence and prepare non-executable forecasts while waiting;
it may not materialize an approval bypass by dispatching B early. Continuation
approval binds the reviewed Action/evidence and a defined continuation scope,
not an unbounded wildcard for future work. A material change invalidating that
scope requires reevaluation; dynamic in-scope planning remains possible without
an owner-supplied A/B script. Materialized/dispatched Action identity is immutable.

The default review fence is Mission-scoped: no new execution in that Mission
until satisfied. A narrower graph/subscope fence needs an explicit supported
policy and qualification; unrelated Missions/projects need not stop. Already
in-flight Actions are governed by their owning pause/cancellation contract,
not retrospectively undone. Avoid holding an EP repository mutation lease
solely while waiting for Forge human review after completed delivery.

A Decision has approve/reject/amend/defer outcomes, authenticated actor/role,
exact requirement/subject/policy references, timestamp, scope and decision
provenance. Pending, rejected, deferred, expired, superseded and satisfied are
not interchangeable. A newer revision or a stale browser click cannot silently
satisfy a different requirement. Replays reconcile one decision/continuation;
restart never loses a fence or dispatches twice.

Evidence-proven engineering completion and required human acceptance are
separate facts. Do not report unconditional Mission completion while its
required end-acceptance is unresolved, and do not erase proven delivery because
acceptance is deferred. Normal review cadence is not a reapproval of every
Mission's Business/Architecture boundary.

## Project-owned Delivery Control Contract

Environment is a first-class classification bound to a stable target, not just
a free-text label. Each target contract declares:

- project/product/component and target identity;
- environment class TST/ACC/PROD/custom, account/resource/audience and approved
  endpoint/registry/store scope;
- supported operations: build, publish artifact, install, deploy, store upload,
  submit for review, public release, migration or rollback as applicable;
- trigger/request, approval and execution/deployment authorities separately;
- pipeline/entrypoint identity and relevant configuration revision;
- artifact/source/version input contract, compatibility and qualification;
- gate mapping, decision evidence, receipt/readback, freshness and cancellation.

The project authority repository owns the declaration. The declared external
system remains authoritative for actual gates/configuration; observed drift
must be reconciled, not overwritten by Forge's cached declaration. A Mission
can request delivery to an allowed target but cannot replace that target's CD.

TST/ACC can be automatic while PROD requires human approval under the chosen
profile. TST and ACC may also be stricter when project policy requires it.
A production endpoint cannot be relabeled ACC to obtain a weaker policy.
App upload, submission to review, reviewer approval and public availability
are separate outcomes; a store submission does not prove public release.

## Resolve requirements to existing authorities; do not duplicate gates

One logical requirement has one authoritative satisfaction binding. Resolve it
to the existing external gate where that gate demonstrably covers the required
semantics, artifact, target and operation. Gate equivalence is not determined
by matching names or by one pipeline having a green status. A configured binding
is NOT a satisfied approval: WAITING_EXTERNAL_DECISION remains pending until
validated matching decision evidence exists.

Workspace shows an external gate's owner, state, reason, freshness and approved
deep-link. It must not show a local Approve control for that same external gate.
An unavailable external service does not authorize a replacement Workspace gate.
Two distinct approvals are valid only when policy explicitly requires different
obligations, such as business release approval and SRE production approval.
Track their identities independently; no duplicate click for one requirement
and no accidental collapse of genuine separation-of-duties obligations.

If required authority or evidence cannot be mapped, block the dependent operation
and request a real contract/authority decision. Do not silently take ownership,
weaken requirements, or claim a generic CI success proves human approval.

## Integration modes and the request-before-approval distinction

`OBSERVE_ONLY` is the default for an existing delivery system: read verified
state/evidence and never trigger or approve. `REQUEST_AND_WAIT` additionally
allows a bounded authorized request to an existing entrypoint. An authorized
direct trigger is a separately scoped permission within this mode, not a third
mode conferring deployment or approval rights.

The request/trigger actor must itself be authorized. It can be the existing EP
execution adapter or another explicitly declared delivery integration actor;
Forge never becomes an arbitrary shell/CD executor. Pipeline credentials remain
at the owning service. No ambient production/cloud/store credentials in Forge
or Workspace merely to request or observe a pipeline.

An external pipeline may need to start before its human gate can be presented.
An authorized request may therefore precede the external decision IF the owning
pipeline demonstrably prevents the protected deployment/publication until its
gate is satisfied. Verify that enforcement binding before the request. Do not
create a circular dependency requiring external approval before the pipeline
that materializes that approval can be requested. Conversely, if the trigger
itself performs the protected side effect, the gate must precede the trigger.

## Exact authorization and evidence binding

Bind approval to requirement/operation, applicable policy and contract revision,
project/component, exact artifact digest, qualified source/candidate provenance,
target/environment, pipeline identity/configuration and validity conditions.
A decision for ACC, artifact A or pipeline run R is not permission for PROD,
artifact B or a new unrelated attempt. Source SHA and artifact digest are distinct;
squash/merge relationships need actual provenance, not assumed equality.

At each protected side-effect boundary its owning executor rechecks current
scope, expiry/revocation, policy compatibility and decision validity. Pinned
snapshots preserve history but cannot override an emergency stop. A cadence
change affects new work by default; in-flight activation requires an explicit
controlled transition preserving grants, history, consumption and fences.

Persist outgoing operation identity before request. Reconcile ambiguous responses
against that same operation/authority, not by blindly triggering again. Observe
callbacks/readback through authenticated, scoped interfaces; verify run, target,
artifact and decision identity, handle duplicates/out-of-order events, and retain
append-only observations with clear current/freshness status. External systems
need not implement EP's receipt schema; qualified adapters map authentic evidence
without synthesizing facts. An insufficient producer is explicitly unsupported
or unverified, never silently successful.

Requested, accepted, awaiting approval, approved, executing, deployed, verified,
store-submitted and publicly released are separate facts. A green trigger job
is not deployment success. Forge releases successors only when their declared
requirements have authoritative evidence. Reject/defer/timeout/outage never
causes a direct deployment fallback or automatic bypass resubmission. Keep
already proven delivery separate from later cancellation, rollback or cleanup.

## Relationship to version/release management and current work

Native version/release planning (`FORGE::VERSION_RELEASE_MANAGEMENT_V1`) consumes
these authority/target requirements; this increment does not implement it or
claim repository SemVer helpers supply it. Version allocation, build, publication
and installer composition retain their existing owning boundaries. Final
component pins still require real qualified published artifacts.

The open Living Mission Graph proposal and EP dependency/assurance/queue/SemVer
lanes remain separate. This document does not merge them, close their findings,
change their implementation or make external deployment necessary for a canary
whose Mission does not request it. No live programme DAG/grant is changed.

## Acceptance for subsequent implementation

Require source, cross-product and installed proof as applicable:
prototype continuous-to-end versus production after-Action fence; permitted and
forbidden Mission override; distinct mandatory risk gate; restart without losing
pending review; stale/wrong-role decision rejected; no successor dispatch before
review; Mission acceptance separate from delivered evidence; automatic TST/ACC
versus external PROD approval; one external gate with no Workspace duplicate;
separate business/SRE gates; request-before-external-gate without bypass; target
relabeling denied; changed artifact/config invalidates approval; revoked grants;
lost trigger acknowledgment without duplicate deployment; authenticated wrong-run
or out-of-order evidence rejected; external outage; store submission not public
release; no production credential/SQL bypass. All remain PLANNED qualification.
