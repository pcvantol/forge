# Forge Operations Console V1 — scoped roadmap

**Capability:** `FORGE::OPERATIONS_CONSOLE_V1`
**Status:** PLANNED; documentation/design only, no implementation or installed claim.
**Priority lane:** POST_AUTONOMY. **First E2E blocker:** FALSE.

The [canonical roadmap](../../knowledge/bootstrap/10_ROADMAP.md) owns sequencing.
The [architecture](../architecture/FORGE_OPERATIONS_CONSOLE_V1.md) owns scope and
boundaries. The [machine-readable DAG](forge-operations-console-v1.json) is a
non-executable projection of this scoped plan, not an Action schedule, Mission
allocation or authority grant. Existing executable bootstrap graphs are unchanged.

## Delivery DAG

All nodes below are Forge-owned and PLANNED. Documentary contract design may
advance independently now; implementation remains future work selected through
normal governance. There is no dependency edge from this console to the first
Forge -> EP -> Forge canary, and no requirement to finish all Workspace or
installer productization before the minimal local console.

| Node | Deliverable | Hard dependencies | Evidence required before completion |
| --- | --- | --- | --- |
| FOC-0 | Typed operations/view/command contracts, explicit ownership and authentication boundary | none | Reviewed mappings for all five sections, read/write separation and unchanged product authorities |
| FOC-1 | Forge-owned instance/component/log/config/Mission read projections and bounded API | FOC-0 | Instance/project isolation, redaction, freshness, empty/error states, OpenAPI/Postman/route parity |
| FOC-2 | Local authenticated console shell and shared detail/navigation UI | FOC-0 | Installed assets, operator-session checks, local-only default, accessibility and unavailable-state tests |
| FOC-3 | Local host components and logs sections | FOC-1, FOC-2 | Actual versus expected identity/status, bounded log filters/tail/export, no filesystem or secret leakage |
| FOC-4 | Active and historical Missions sections | FOC-1, FOC-2 | Correct lifecycle groups, criteria/Action/evidence lineage, ambiguity visibility and history after reopen |
| FOC-5 | Configuration view/editor and explicit non-generating preflight | FOC-1, FOC-2 | Authorized allow-list, preview/save/readback, expected-revision conflicts, audit and no active-binding retarget |
| FOC-6 | Guarded pause/resume requests for existing approved Forge work | FOC-0, FOC-4 | Current backend capability/authority checks; safe boundary acknowledgement; no duplicate EP submission or budget reset |
| FOC-Q | Integrated installed-console qualification | FOC-3, FOC-4, FOC-5, FOC-6 | Five sections end-to-end from installed artifact, reopen/degraded/security cases and exact artifact/evidence linkage |

```text
FOC-0 -> FOC-1 --+--> FOC-3 ---------------------+
   |            +--> FOC-4 -> FOC-6 ------------+--> FOC-Q
   +--> FOC-2 --+--> FOC-5 ---------------------+
```

FOC-3/4/5 each require BOTH FOC-1 and FOC-2; the JSON dependency lists are the
unambiguous edge definition. No node may be marked delivered from documentation
alone. An unavailable pause/resume capability produces a disabled UI action;
it does not authorize a replacement execution loop.

## Shared platform status and basic shell requirements

The owner's EP status-panel, toolbar and footer references are specified in
[Forge platform status and basic shell functions](../architecture/FORGE_OPERATIONS_CONSOLE_V1.md#forge-platform-status-and-basic-shell-functions).
They belong to the EXISTING eight nodes, not a new programme or a prerequisite
for the first E2E. Here platform status refers to Forge Server, not the separate
Forge Platform installation product. All requirements remain PLANNED.

| Requirement | Delivering nodes | Added completion evidence |
| --- | --- | --- |
| `FOC-STATUS` | FOC-0, FOC-1, FOC-2, FOC-3 | Backend-owned aggregate and Platform/Access/Ingress/Execution groups; per-scope required/optional impact; component links; no-project, idle, stale and optional-relay cases |
| `FOC-SHELL` | FOC-0, FOC-1, FOC-2 | Status indicator, manual refresh, project/language/theme selectors, expand/collapse and automatic-refresh toggle; presentation-only actions with retained drafts and no hidden writes |
| `FOC-FOOTER` | FOC-0, FOC-1, FOC-2 | Installed product/version identity, genuine last live signal with timezone/freshness, truthful serverpush or polling/connection state |

FOC-4 uses the same execution snapshot for Mission activity and queue details.
FOC-5 preserves unsaved configuration under view refresh, and FOC-6 retains
separate authorized pause/resume: disabling automatic refresh never pauses work.
FOC-Q qualifies all three shared requirements together with the five sections.
The JSON `shared_requirements` and node mappings are the traceable decomposition.

The read-only milestone includes all toolbar/status/footer features, even though
configuration writes and Mission controls remain deferred to FOC-5/6. Optional
relay/push support is displayed truthfully when present, not required as a new
implementation dependency. Snapshot aggregation, project isolation, actual
installed identity and stale-state handling must be tested, not inferred from
EP screenshots or mocked green indicators.

## Milestones and capability prerequisites

**Read-only console:** FOC-0 through FOC-4 provide all five navigation entries;
Configuration is read-only until FOC-5. This is observable delivery, not full V1.
**Minimum operational V1:** FOC-5/6 plus FOC-Q add safely applied settings and
bounded controls with authoritative readback. Neither milestone is currently
implemented or qualified by this documentation increment.

Before implementing each relevant slice, verify the exact existing Forge
capabilities it consumes: resolved Server-instance/operator binding, durable
Mission/Action/history projections, structured redacted log access, typed
configuration services and bounded lifecycle controls. Add only a missing
consumer-facing seam required by that slice, not a parallel state store or
scheduler. Reconcile actual capability availability at execution time.

EP is consumed through its versioned authenticated contracts and evidence
references. Workspace integration is a later optional navigation consumer;
Workspace keeps project/governance UX. Forge Platform owns normal deployment
and process/install lifecycle. These peer facts are not allocated as peer work
by this Forge graph; peer changes, if ever required, need owning proposals.

## Resume rules

Fresh-fetch the owning sources and open proposals before picking a node.
Confirm the previous node's exact producer evidence, installed/API identity and
applicable authority; stale UI state and historical CI summaries are not gates.
Qualify each change through the existing protected route. Keep local console
implementation out of the current canary recovery/Mission envelope.

A later run must retain distinct source, qualification, release, installation
and live-operational states. This future feature creates no current Mission,
Action, submission, provider invocation, grant, schema or version allocation.
