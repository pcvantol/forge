# Forge Engineering Method

**Status:** Canonical execution-facing method

Forge uses one bounded Mission at a time. Repository evidence is authoritative
over a prompt, checkpoint, or prior execution record.

## Method

1. Read the root bootstrap contract and this companion document.
2. Inspect the local Git state and the architecture record governing the
   bounded objective.
3. Require independently issued Execution Host qualification evidence before
   execution. Forge does not self-qualify the Development Host, workspace, or
   capabilities.
4. Admit only a Mission that has recorded Business and Architecture approval.
   Mission Intake creates durable Mission State; it does not allocate approval,
   create a Mission, or broaden its scope.
5. Derive only the bounded Engineering Action and Runtime Prompt permitted by
   the approved Mission. The Execution Host performs execution and returns
   host-owned evidence.
6. Interpret returned evidence through Forge governance and repository truth;
   keep execution receipts, telemetry, and qualification owned by the Host.

Genesis transactions use a local Git repository and may reconcile a clean local
commit without an upstream remote. Managed transactions follow the Execution
Host's workspace and remote policy. Neither mode authorizes a change outside
the approved Mission.

## Canonical records

This document is deliberately thin. The canonical Mission lifecycle and Intake
boundary are in [Mission-driven engineering](docs/architecture/engineering-mission.md).
Business and Architecture approvals are in the
[Business Workspace](docs/architecture/business-workspace.md) and
[Architecture Workspace](docs/architecture/architecture-workspace.md).
Execution and qualification ownership are in the
[Execution Host Contract](docs/architecture/execution-host-contract.md).
