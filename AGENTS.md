# Forge agent instructions

Read [BOOTSTRAP.md](BOOTSTRAP.md), [ENGINEERING_METHOD.md](ENGINEERING_METHOD.md),
[PROMPT_INITIALIZATION.md](PROMPT_INITIALIZATION.md), and the generated
[AI-development projection](docs/ai-development/GENERATED_PROJECTION.md)
before acting. Generic agent workflow rules are authoritative only in that
projection.

Forge-specific boundaries are immutable for this repository: Forge owns Mission
planning, Action derivation, Producer Contracts and interpretation of evidence;
the installed Execution Host owns host qualification, runtime invocation,
execution evidence, telemetry and cleanup. Business owns portfolio value and
approval; Architecture owns technical refinement and approval. Mission Intake
admits an already-approved Mission only. Do not allocate a Mission ID, change a
Mission lifecycle state, expand an objective, or use repository documentation
as host-qualification evidence.

Canonical Forge architecture remains in [docs/architecture](docs/architecture/).
The Forge-to-Engineering-Platform boundary is defined by the versioned Producer
and Execution Host contracts.
