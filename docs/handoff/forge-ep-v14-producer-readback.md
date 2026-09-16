# Forge–EP v1.4 producer readback handoff

## Bounded delivered change

This increment qualifies Forge's existing Engineering Platform adapter against
Engineering Platform main `1cbbeb28d556141a6b8b74d2054b0bd388d67cb6`
(merged PR #222).  The qualified contract pair is:

- producer readback `1.2`; and
- terminal evidence `1.4`.

The Forge revision is the protected-PR merge commit that contains this
handoff.  The change is contract adaptation only: it neither starts a Mission,
Action, dispatch, retry, peer configuration change, nor a live EP execution.
In particular, historic EP run `inbox-0d8aa407b23f4448bffe858c5ea172f6`
remains `BLOCKED` / `NOT_QUALIFIED`.

## Immutable request binding

Every *new* installed Forge-to-EP request has a persisted
`RepositoryRevisionBinding` in both its `ExecutionRequest` and canonical
Producer Contract before any transport attempt.  The payload projects its
deliberately narrow EP form as a sibling of `constraints.forge_execution`:

```json
{
  "constraints": {
    "forge_execution": { "...": "existing Forge execution constraint" },
    "repository_revision_binding": {
      "requested_revision": "<40 lowercase hexadecimal SHA>",
      "allowed_baseline_revision": null
    }
  }
}
```

`requested_revision` is the immutable `revision` in the active Mission's
persisted Repository Truth record.  Forge also retains that record's
`source_id` and `content_digest` in the producer binding.  It is never taken
from the checkout, local `HEAD`, remote `main`, an EP build revision, or prompt
text.

An exact pin has `allowed_baseline_revision: null`.  A non-null allowed
baseline comes only from a `RecoveryAuthorization` for that same Mission and
unresolved Action; its `authorization_id` is retained in Forge's binding and
audit material.  Thus a transition has explicit authority and cannot be
silently introduced on an ordinary resume.

The binding's canonical digest and the exact canonical submission-payload
digest are persisted with the correlation.  Forge also independently
recomputes EP #222's accepted-request digest from the actual prompt bytes and
constraints before accepting a receipt or readback.  Re-dispatch/recovery uses
the stored request bytes and correlation.  A request whose binding or payload
digest differs is rejected instead of being sent under the old correlation.
Existing requests that predate this change keep no added binding or constraint.

## Evidence and history

For terminal `1.4` artifacts Forge verifies the actual saved request binding,
not merely agreement between EP response fields.  It checks producer,
submission, Mission, Action, correlation, run and provenance identities;
accepted-request and artifact digests; requested revision; actual execution
baseline; exact or authorized baseline transition; a present candidate; and a
delivery revision only when EP says delivery was qualified.  `BLOCKED` and
`FAILED` terminal checkpoints remain valid terminal evidence with no delivery
qualification, but cannot complete a Forge Mission.  A `VALIDATION_ONLY`
result cannot satisfy implementation delivery criteria.

The adapter continues to read stored terminal `1.3` artifacts using their
original contract and correlation binding.  It also recognizes EP's explicit
v1.4 `UNSPECIFIED` request-binding shape for a submission that predated the
constraint, but rejects a historic artifact that invents a pin or transition.
It does not inject v1.4 fields, rewrite bytes, or retarget old peer/correlation
records to a newer binding.

A v1.4 correlation written before explicit consumer binding can already carry
its immutable repository revision binding while omitting only
`expected_ep_consumer_id`. Forge accepts that precise read-only shape only when
an immutable configuration event proves a single guarded schema `1.0` to `1.1`
consumer adoption with the original target identity preserved. Current
Keychain authentication must still prove the configured EP instance, consumer,
project and repository before readback. The adapter neither backfills the old
record nor sends a POST; unverified adoption or target retargeting fails closed.

## Peer-configuration transition

New work requires the peer configuration pair `1.2` / `1.4`.  A persisted
`1.2` / `1.3` peer may be upgraded only through the existing explicit
`forge execution-host configure --replace` route with the exact currently
observed configuration revision and digest.  The replacement audit carries the
previous state and its request digest as well as the new configuration
identity.  This is a guarded future operator action; no configuration command
was run for this source increment.  Old correlation records remain bound to
their stored configuration and evidence history.

## Later authorised retry: real route and remaining gap

The existing public installed-composition route is
`InstalledDynamicMissionRuntime.recover(mission_id, authorization)`.  It
accepts one `RecoveryAuthorization` for the already blocked/failed Mission and
its exact unresolved Action.  The existing execution loop then creates the
retry request with recovery lineage and, when supplied, the authorised allowed
baseline.  This is a new EP execution attempt in the same Mission/Action
failure lineage; it is not a new Forge planning attempt, does not generate a
new Mission, and does not expand the approved objective.

By contrast, an authorised new Forge planning attempt remains the separate
`resume_authorized_next_planning_attempt` path and is only available for its
own lost-provider-result case.  It is not a retry mechanism for terminal EP
execution.

The shipped CLI exposes peer administration and read-only preflight, not an
operator command or public HTTP endpoint for calling the installed runtime's
`recover` method.  That is the remaining concrete activation gap: a later
Forge-owned public runtime ingress must be introduced and governed before an
operator can invoke this recovery path.  This increment deliberately does not
add a private runtime patch, a new framework, or a Human-to-EP bypass.

## Required activation evidence

Before a separately authorised installed activation, retain and verify:

- the scoped, persisted Repository Truth `source_id`, full revision SHA, and
  content digest;
- the persisted Execution Request/Producer Contract, correlation binding,
  binding digest, and submission-payload digest;
- when a transition is intended, the matching RecoveryAuthorization including
  Mission, Action, authority identity, reason, and allowed baseline SHA;
- the configured peer's observed revision/digest and the guarded replacement
  receipt, if a `1.3` to `1.4` upgrade is required;
- EP's producer-readback `1.2` acceptance record and the immutable terminal
  `1.4` artifact bytes, SHA-256 digest, report/run references, and delivery
  evidence; and
- separate installed qualification with its own non-production credentials,
  host checks, Quality and Security review evidence.

Those records are evidence for a future authorised activation.  They are not
created by this PR and do not turn a source-level contract test into a live
Forge-to-EP E2E claim.
