# Forge Bootstrap

**Status:** Canonical repository entry point

This document is the bootstrap contract for Forge when it is admitted by an
Engineering Platform Execution Host. It is intentionally an entry point, not a
second architecture handbook. Repository evidence is authoritative whenever it
differs from a prompt, checkpoint, or prior execution record.

## Admission baseline

Forge is a Git repository with this root `BOOTSTRAP.md`. A Genesis transaction
uses a local Git workspace and does not require an upstream remote. The
Execution Host owns platform, Development Host, workspace, and capability
qualification; Forge consumes the resulting evidence and never substitutes
repository documentation for host qualification.

Before a bounded change, inspect the current repository state and then read:

1. [README.md](README.md) for the current Generation and scope;
2. [Generation 1 Completion Record](GENERATION_1_COMPLETION.md) for historical
   bootstrap completion;
3. [Founding Architecture Handbook](docs/architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md)
   for canonical architecture navigation;
4. the architecture document governing the requested bounded work; and
5. the applicable regression tests in `tests/`.

## Canonical responsibility map

Forge's responsibility boundaries are deliberately defined once in the
architecture records below.

| Responsibility | Canonical record |
| --- | --- |
| Repository truth and Forge engineering scope | [Repository model](docs/architecture/repository-model.md) and [product model](docs/architecture/product-model.md) |
| Mission contract, lifecycle, and Mission Intake | [Mission-driven engineering](docs/architecture/engineering-mission.md) |
| Runtime state and recovery | [Runtime bootstrap](docs/architecture/runtime-bootstrap.md) and [runtime database](docs/architecture/runtime-database.md) |
| Execution Host operations and qualification | [Execution Host Contract](docs/architecture/execution-host-contract.md) |
| Producer boundary and Runtime Prompt hand-off | [Producer Contract](docs/architecture/producer-contract.md) |
| Business governance and Mission Candidates | [Business workspace](docs/architecture/business-workspace.md) and [product model](docs/architecture/product-model.md) |
| Architecture governance and engineering approval | [Architecture workspace](docs/architecture/architecture-workspace.md) and [product model](docs/architecture/product-model.md) |

The boundary is strict: Business owns portfolio value and Business approval;
Architecture owns technical refinement and engineering approval; Forge plans
and coordinates engineering only inside an approved Mission; the Execution
Host owns execution, qualification, reports, telemetry, and execution
evidence. Mission Intake validates an already approved Mission and creates
durable Mission State; it neither creates a Mission nor grants either approval.

The Forge-to-Engineering-Platform boundary is the versioned Producer and
Execution Host contracts. Engineering Platform remains a replaceable Execution
Host, not a Forge governance, planning, or repository authority.

## Document review

Current Engineering Platform Bootstrap Contract `2026.12` requires this root
bootstrap document and Git repository identity for repository admission.
`ENGINEERING_METHOD.md`, `PROMPT_INITIALIZATION.md`, and `AGENTS.md` are not
separate Forge admission artefacts: their subjects are already owned by the
canonical records linked above. Do not create duplicate Forge copies unless a
future Engineering Platform contract explicitly requires them.
