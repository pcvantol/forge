# Forge handoff

This is Forge's local handoff navigation entrypoint. It does not restate the
generic handoff contract.

1. Start with [BOOTSTRAP.md](BOOTSTRAP.md), the committed generic projection,
   and [the Forge development extension](docs/ai-development/FORGE_DEVELOPMENT_EXTENSION.md).
2. Review the [Founding Architecture Handbook](docs/architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md),
   [current roadmap](knowledge/bootstrap/10_ROADMAP.md), and
   [Genesis provenance](FORGE_GENESIS_PROVENANCE.md).
3. Validate a bounded change with `bash scripts/validate.sh` and record the
   Forge-specific result in the handoff.

Forge remains a first-class peer of Workspace. An installed Engineering
Platform may serve as an Execution Host, but its source checkout is not a
Forge runtime dependency.
