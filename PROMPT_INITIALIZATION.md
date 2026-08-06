# Forge Prompt Initialization

**Status:** Canonical execution-facing admission checklist

Before a Forge agent acts on a bounded prompt, it must establish a `GO` only
when all of the following are true:

- the actual target repository contains the four root execution-facing
  documents and has been inspected;
- repository identity and local Git state are valid for the declared execution
  mode;
- the objective is a bounded, approved Mission or an explicitly authorized
  Mission-scoped action;
- the governing architecture record and applicable tests have been identified;
- independently issued Execution Host evidence passes Development Host,
  workspace, and capability qualification; and
- the requested change remains within the Mission's objective, constraints,
  and success criteria.

If any condition is absent or fails, record `NO-GO` and stop before repository
mutation. Missing or failed host qualification is an infrastructure blocker;
Forge documentation cannot waive it.

## Responsibilities at initialization

| Responsibility | Owner |
| --- | --- |
| Portfolio value and Business approval | Business Workspace |
| Technical refinement and Architecture approval | Architecture Workspace |
| Approved Mission validation and durable Mission State | Mission Intake |
| Mission planning, Action derivation, and Producer Contract | Forge |
| Runtime invocation, host qualification, execution receipts, telemetry, and reports | Execution Host |
| Prompt production and bounded hand-off | Producer |

The canonical models are [Mission-driven engineering](docs/architecture/engineering-mission.md),
[Producer Contract](docs/architecture/producer-contract.md), and the
[Execution Host Contract](docs/architecture/execution-host-contract.md).
