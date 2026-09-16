# Forge bootstrap

## Current pickup checkpoint — 16 September 2026

Implementation PR #125 merged the deterministic, read-only aggregate-health
evaluator at `9208cc8ff0f6582a936a861a8c8bfa67f320989b`. The evaluated candidate
`1d6a6faef5efb0a4aa57aea6bdf251a1a722a872` passed the focused health and
architecture regressions, the full canonical validation suite, and distinct
Quality and Security reviews. Start health work with
[`forge/runtime/health.py`](forge/runtime/health.py), its
[`focused regressions`](tests/test_runtime_health.py), and the
[`aggregate-health contract`](docs/architecture/FORGE_AGGREGATE_HEALTH_V1.md).
The separate, non-empty finalization PR #126 is merged at
`406b1d8cc409916bc7fe321eb705f25bdab39586`; this rolling checkpoint is
reconciled to that protected delivery.

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
