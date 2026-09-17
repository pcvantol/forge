# Forge bootstrap

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

## Current pickup checkpoint — 17 September 2026

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
