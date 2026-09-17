# Forge bootstrap

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
The separate, non-empty draft Finalization PR #129 reconciles this rolling
checkpoint without changing runtime semantics.

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
