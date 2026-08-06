# Forge Agent Instructions

Read [BOOTSTRAP.md](BOOTSTRAP.md), [ENGINEERING_METHOD.md](ENGINEERING_METHOD.md),
and [PROMPT_INITIALIZATION.md](PROMPT_INITIALIZATION.md) before acting.

Agents work only within an approved, bounded Mission and must preserve the
Forge-to-Engineering-Platform boundary:

- Forge owns Mission planning, Action derivation, Producer Contracts, and
  interpretation of evidence.
- The Execution Host owns Development Host, workspace, and capability
  qualification, plus runtime invocation, execution evidence, telemetry, and
  cleanup.
- Business owns portfolio value and Business approval; Architecture owns
  technical refinement and Architecture approval. Mission Intake only admits
  an already approved Mission into durable Mission State.

Do not treat repository documentation as host-qualification evidence. Do not
allocate a Mission ID, change a Mission lifecycle state, or expand an objective
without the applicable recorded governance and host evidence. Keep this file
as execution guidance; canonical architecture remains in
[docs/architecture](docs/architecture/).
