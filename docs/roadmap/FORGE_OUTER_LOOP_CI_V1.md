# Forge outer-loop CI — later implementation roadmap

**Status:** PLANNED. **Lane:** LATER_RUNTIME_QUALIFICATION.
The [contract](../architecture/FORGE_OUTER_LOOP_CI_INTEGRATION_V1.md) and
[documentary DAG](forge-outer-loop-ci-v1.json) extend, not replace, the
[inner-loop CI plan](FORGE_INNER_LOOP_CI_V1.md). This is not an executable schedule
or a new prerequisite for the current live E2E.

## Sequence

```text
Inner CI: Candidate -> approvals -> one Mission inner loop -> completion
  -> FCI-CI qualified
  -> later outer CI: completed M1 -> Context -> Candidate -> governance -> M2

Current live E2E result reviewed
  -> existing FSH-SERVICES backend milestone: standalone Forge Server
  -> later same CI scenarios through its installed process/API
```

The server line is independent of the outer-loop suite and the dashboard.
Review the actual live outcome, including blockers; do not claim a successful
live run from a green simulator. The inner CI plan can proceed independently
of live-canary success, Console, relay, Workspace and installer development.

## Delivery DAG

| Node | Deliverable | Internal dependencies |
| --- | --- | --- |
| FCO-CONTRACT | Outer-loop fixture, provenance and scenario contract | none |
| FCO-FLOW | Completed Mission through governed next Mission | FCO-CONTRACT |
| FCO-RESTART | Idempotent new-process outer-loop recovery | FCO-FLOW |
| FCO-NEGATIVE | Authority, scope, evidence and no-work scenarios | FCO-FLOW |
| FCO-CI | Required deterministic outer-loop CI and release reuse | FCO-RESTART, FCO-NEGATIVE |

FCO-FLOW also requires **FCI-CI** from the existing inner-loop graph. Reuse its
installed harness and stateful mock EP. All five nodes remain PLANNED;
FCO-CONTRACT completion requires implemented fixture validation, not this text.
Before FCO-FLOW implementation, verify the owning public outer services and
record any missing seam as bounded production work rather than hiding it in tests.

## Completion criteria

FCO-CI is delivered only when FOE-01..10 run from a source/artifact-bound installed
Forge distribution on PR/main and local/release paths, with real Forge internals
and only external deterministic doubles. Governance blocking, M1-to-M2 linkage,
no-work, duplicates, stale scope, failed evidence and process restart are required.
A failing/absent/skipped scenario must block required qualification. Keep full
scenario and request-count evidence; never substitute coverage for flow proof.

The standalone Server is an explicit post-live-E2E product delivery: real serve
entrypoint, automatic progression/readback, safe stop/reopen, one data root and
product-owned API/lifecycle. Reuse FSH-SERVICES, do not allocate a duplicate
server node or require the entire Console to ship first. Existing launchd,
CENTRAL and account/credential qualification requirements still apply.

The present documentation update runs no new integration suite, starts no
Server, changes no workflow and touches no live instance, Mission or authority.
