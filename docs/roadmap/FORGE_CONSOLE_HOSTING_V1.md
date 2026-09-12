# Forge Console hosting and CENTRAL — scoped roadmap

**Capability:** `FORGE::OPERATIONS_CONSOLE_V1`
**Status:** PLANNED / POST_AUTONOMY. **First E2E prerequisite:** FALSE.

The [hosting architecture](../architecture/FORGE_CONSOLE_HOSTING_AND_CENTRAL_V1.md)
and [documentary sub-DAG](forge-console-hosting-v1.json) refine the existing
[Console roadmap](FORGE_OPERATIONS_CONSOLE_V1.md). The parent
[admin-parity graph](forge-console-admin-parity-v1.json) explicitly references
this extension. Its FCP-Q qualification now requires FSH-Q; the existing parent
FOC-Q already requires FCP-Q. This is a nested completion gate, NOT an executable
Action plan, another programme or a change to the current canary.

## Explicit scope refinement

A Forge Tailnet relay is a REQUIRED V1 product capability, though activation
remains optional and opt-in. Its disabled state never blocks local operation.
All declared components get status and detail modals; safe component restart
is now in scope through owning services. This supersedes the original blanket
no-OS-restart exclusion, not its prohibition on arbitrary shell or peer control.

Forge Server, Console and relay have separate Forge-owned launchd jobs; Console
is product-subordinate, not additionally spawned by Server. The Python/HTML/CSS/
plain-JS design remains unchanged. Forge CENTRAL reuses the existing data-root
and forge.db. No new database name, schema bump, account migration or runtime
reset follows from this design. Workspace remains the human project interface.

## Work packages and exact internal edges

| Package | Internal dependencies | Delivery / qualification |
| --- | --- | --- |
| FSH-CENTRAL | none | FOC-0, FOC-1, FOC-5; Reuse canonical Forge CENTRAL |
| FSH-COMPONENTS | none | FOC-0, FOC-1, FOC-3; Canonical component and service registry |
| FSH-SERVICES | FSH-CENTRAL, FSH-COMPONENTS | FOC-0, FOC-1, FOC-5; Installed Server and Console service lifecycle |
| FSH-RELAY | FSH-SERVICES | FOC-1, FOC-3, FOC-5; Forge-owned Tailnet Console relay |
| FSH-DETAILS | FSH-COMPONENTS | FOC-1, FOC-2, FOC-3; All-component status and detail modals |
| FSH-RESTART | FSH-SERVICES, FSH-RELAY, FSH-DETAILS | FOC-3, FOC-5, FOC-6; Guarded durable component restart |
| FSH-Q | FSH-CENTRAL, FSH-RELAY, FSH-DETAILS, FSH-RESTART | FOC-Q; Installed hosting and remote administration qualification |

The JSON contains the same internal edges and separately names inherited
prerequisites from the existing FC/FCP graphs. FSH-SERVICES consumes FC-STATE,
FC-CODEX and FC-PYTHON; FSH-DETAILS consumes FCP-DESIGN/I18N; FSH-Q consumes
FCP-CI and the FC-RELOCATE cutover contract. FSH-Q does NOT depend on FCP-Q,
which would make the nested completion chain circular. Full completion means
FOC-Q -> FCP-Q -> FSH-Q in addition to every pre-existing node's own evidence.
"delivered_by" is a decomposition mapping, not an execution dependency edge.

## Milestones and evidence

Read-only delivery includes the complete declared component registry, component
modals, explicit central-root status and relay unconfigured/disabled/missing
states. It does not claim working remote access, launchd provision or restart
from a green mock, a static row or a rendered button.

Operational V1 requires actual independently managed Server/Console/relay
services, guarded restart, and local plus second-host Tailnet access. Qualify
installation idempotency and boot/logout behavior in the declared service
account/domain; an interactive developer Python process is not that evidence.
Preserve Forge-local Codex/Python ownership and supported session consent.

Every package inherits the same EP design system, five locales, four complete
Playwright shards, API/installed/security checks and strict >80% coverage
(minimum 80.20% including production-module gates). Native service/relay code
needs its own declared verification/coverage scope. Reopen and relocation must
retain the exact runtime, installation, peer binding, approvals, budgets,
correlations and immutable evidence without duplicate generation or submission.

EP's read-only system-service foundation is a design reference, not evidence
of completed service provisioning. Forge Platform consumes Forge's owning
service/paired-instance APIs; this graph allocates no peer implementation.
Do not add completion of the universal installer, Workspace, or an EP console
upgrade as a prerequisite for implementing this bounded Forge capability.

## Resume rules

Refresh source refs, component/service definitions and applicable authority before
picking a package. Inventory existing services/ports/data roots without mutation;
preserve unknown state and report inspection limits. Use the normal protected
source route and separately authorize installation/runtime changes. Never start
an E2E, repair an ambiguous Mission, move data, alter credentials or restart an
existing service merely because this documentary graph was updated.
