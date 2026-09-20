# Forge bootstrap

## Production Mission 3 joint-reset stop — 20 September 2026

The [production acceptance record](docs/operations/MISSION_3_PRODUCTION_ACCEPTANCE_2026_09_20.md)
preserves the single authorized clean-CENTRAL operation's partial reset and
pre-T0 failure. Forge reached dataset generation 1; EP stopped after artifact
archiving at generation 0. Both products remain in maintenance under the same
operation identities. No Mission was allocated or started, and no C01–C20
autonomy acceptance is claimed. Use the owning recovery receipts and the
two lane handoff records before touching either runtime or target repository.

## Temporary dual-lane development before Forge cutover

For the owner's two concurrent Codex architect sessions, read
[the dual-lane plan](docs/roadmap/DUAL_LANE_DEVELOPMENT_V1.md),
[LANE_1](docs/roadmap/lanes/LANE_1.md) or
[LANE_2](docs/roadmap/lanes/LANE_2.md), and both linked live coordination issues.
The [allocation index](docs/roadmap/dual-lane-development-v1.json) covers the
existing 34 families without changing their owning dependency graphs or the
historical count. Every assignment must follow
[vertical-slice delivery](docs/roadmap/VERTICAL_SLICE_DELIVERY_V1.md): one kickoff
covers implementation, required tests/refactoring, review fixes, supported owner
authorization, PR, protected main merge and declared artifact/installed delivery.
The owner has delegated those ordinary lifecycle steps within the selected
released scope; do not ask for routine reapproval or issue separate test/DoD/
merge prompts. Real permissions, independent assurance and material effect
boundaries remain mandatory. This is not a fabricated runtime grant.
Select independent complete outcomes; do not issue duplicates or mutate another
lane's repository/runtime. Move supported scope to qualified Forge Missions as
soon as possible, not after the whole portfolio. Reading this planning does not
start a scheduler, reset, release or Mission, or change Mission-3 acceptance.

## Roadmap overview and autonomy-first focus

Read the [roadmap overview and autonomy-first focus](docs/roadmap/ROADMAP_OVERVIEW_AND_AUTONOMY_FOCUS.md)
for the preserved four-product sizing analysis and the shortest-path orientation
toward Forge executing governed work packages itself through EP. Its dated
[inventory](docs/roadmap/inventory/2026-09-17.json) records 194 named records,
165 analytical rollup units and 34 possible kickoff families, not 34 approved
Missions or a minimum prompt count. Reconcile actual owning evidence before
selection. This is a documentary reference, not a new backlog, execution grant,
peer-status authority or prerequisite to finish every product before autonomy.

## Project bootstrap design — Genesis and Managed

For new-project initialization or adoption, read the canonical target
[Project bootstrap and artifact manifest V1](docs/architecture/PROJECT_BOOTSTRAP_AND_ARTIFACT_MANIFEST_V1.md),
its [exact conditional artifact inventory](docs/architecture/project-bootstrap-artifact-manifest-v1.json),
[scoped L1/L1-R roadmap](docs/roadmap/PROJECT_BOOTSTRAP_V1.md),
[documentary DAG](docs/roadmap/project-bootstrap-v1.json) and
[qualification catalogue](docs/architecture/PROJECT_BOOTSTRAP_QUALIFICATION_V1.md).
They specify complete Genesis-local and Managed-remote creation/adoption,
plus history-preserving promotion; implementation remains PLANNED.
`forge server init` is still installation storage initialization, not a project
scaffolder. This design neither starts a Mission nor changes Mission 3, live
policies, credentials, runtime schemas or package versions.

## Criterion completion remediation — 18 September 2026

[Implementation PR #149](https://github.com/pcvantol/forge/pull/149) is
protected-merged at `6199a7645c15f078aa69d6246023b078069a9742`.
Read the [separate source finalization](docs/operations/CRITERION_COMPLETION_SOURCE_FINALIZATION.md)
and [qualification boundaries](docs/operations/CRITERION_COMPLETION_QUALIFICATION.md)
for criterion-bound assessment and durable successor planning. The
[completion record](docs/operations/CRITERION_COMPLETION_REMEDIATION_2026_09_18.md)
binds the protected implementation and updater deliveries, exact published
Forge 2.7.25 artifacts, safe schema 38→39 activation, preservation and normal
installed readback. It does not authorize a reset or Mission 3.

The separately authorized Forge 2.7.25 Mission-3 acceptance preflight is
recorded in [Mission 3 on Forge 2.7.25 — blocked before T0](docs/operations/MISSION_3_FORGE_2_7_25_PREFLIGHT_ACCEPTANCE_2026_09_18.md).
It preserves PR #148, performs no reset or Mission allocation, and records the
failed functional-evidence-fit and autonomous installed-ingress conditions.

## Previous pickup checkpoint — 17 September 2026

Implementation PR #128 merged the deterministic aggregate-health timeout-boundary
correction at `1726f774cb42894d3d3386e80adee9444c7a7914`. The evaluated candidate
`dcf1e7a14f54e9c0eac0e0f0f95550b561232987` passed all 16 focused health
regressions, the 667-test canonical validation suite, and distinct Quality and
Security reviews. An observation whose age exactly equals its timeout is now
stale and cannot yield a passing aggregate; the evaluator remains read-only.
Start health work with
[`forge/runtime/health.py`](forge/runtime/health.py), its
[`focused regressions`](tests/test_runtime_health.py), and the
[`aggregate-health contract`](docs/architecture/FORGE_AGGREGATE_HEALTH_V1.md).
The separate, non-empty Finalization PR #129 is merged at
`49596812cefb41250fab184f35dc2c28571e05e0`; this rolling checkpoint is
reconciled to that protected delivery without changing runtime semantics.

This delivery is the local evaluation boundary only. It does not complete the
planned HTTP/CLI routes, installed Forge Server, OpenAPI/Postman drift gates, or
full FH qualification. Engineering Platform Prompt History remains immutable
execution evidence and is not copied into Forge architecture authority.

## Consolidation and parking baseline — 10 September 2026

Read the [consolidation and parking roadmap](docs/roadmap/CONSOLIDATION_PARKING_2026_09_10.md)
and [documentary DAG](docs/roadmap/CONSOLIDATION_PARKING_2026_09_10_DAG.json)
before selecting work. Unfinished product work is PARKED, not cancelled or
qualified. This is not an instruction to implement the next installer,
bootstrap-orchestrator or quality-workflow increment. Local inventories are
reconciled with the completed physical cleanup: the pre-documentation baseline
had one local `main` worktree, no local feature branches and no unpreserved WIP.
The bootstrap-orchestrator source remains preserved only at
`parking/2026-09-10/bootstrap-orchestrator-v0`; it is unreviewed and not a
Forge-E2E prerequisite. The documents become canonical only through their
protected owning merges.

This is Forge's thin local bootstrap entrypoint. The generated
[AI-development projection](docs/ai-development/GENERATED_PROJECTION.md) is
the sole authority for generic bootstrap, prompt, branch/worktree, validation,
TDE-integration, handoff, repository-governance and projection rules. Its
Forge-specific companion is the
[Forge development extension](docs/ai-development/FORGE_DEVELOPMENT_EXTENSION.md).

The companion local entrypoints are [ENGINEERING_METHOD.md](ENGINEERING_METHOD.md),
[PROMPT_INITIALIZATION.md](PROMPT_INITIALIZATION.md), and [AGENTS.md](AGENTS.md).

Continue with the [Founding Architecture Handbook](docs/architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md),
[current roadmap](knowledge/bootstrap/10_ROADMAP.md), [Genesis provenance](FORGE_GENESIS_PROVENANCE.md),
and the architecture and tests governing the bounded Forge change.

Forge retains product authority for Mission, planning, architecture, runtime
state, provider strategy and Forge-specific validation. Forge and Workspace
are peers. Installed Engineering Platform is a replaceable Execution Host:
Forge plans and interprets evidence; the Host executes and owns its runtime
operations and evidence production. These boundaries are product architecture,
not a replacement generic bootstrap contract.
