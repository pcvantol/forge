# Forge bootstrap

## Current pickup checkpoint — 10 September 2026

Read the [consolidation and parking roadmap](docs/roadmap/CONSOLIDATION_PARKING_2026_09_10.md)
and [documentary DAG](docs/roadmap/CONSOLIDATION_PARKING_2026_09_10_DAG.json)
before selecting work. Unfinished product work is PARKED, not cancelled or
qualified. This is not an instruction to implement the next installer,
bootstrap-orchestrator or quality-workflow increment. Local inventories are
owner-reported and require per-target safety checks before any cleanup.
The documents become canonical only through their protected owning merges.

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
