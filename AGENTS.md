# Forge agent instructions

For current lane allocation, first read
[FOUR_LANE_DEVELOPMENT_V1](docs/roadmap/FOUR_LANE_DEVELOPMENT_V1.md) and
[its machine-readable plan](docs/roadmap/four-lane-development-v1.json).
They supersede only the older two-lane concurrency/default-pool instructions:
LANE_1 owns Forge Platform, LANE_2 EP, LANE_3 Forge and LANE_4 Workspace.
Existing #141 installer and #142 r30 assignments and resource boundaries remain
unchanged. Older two-lane documents remain historical inventory/navigation,
not a competing active allocation. Reading a plan never starts a Work session.

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
