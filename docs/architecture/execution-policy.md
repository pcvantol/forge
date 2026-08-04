# Execution Policy

## Purpose

Execution Policy is Forge-owned, versioned configuration that determines only when an active Mission pauses for human governance. It is evaluated after exact Execution Evidence completes an Engineering Action. It never changes the Mission, Mission State planning inputs, Engineering Intent, Engineering Action, Runtime Prompt, Execution Host, or Execution Evidence contract.

## Policies

| Policy | Pause boundary |
| --- | --- |
| Continuous | Never before Mission completion. |
| Engineering Action Review | Each completed Action. |
| Engineering Intent Review | Each completed Intent. |
| Capability Review | Each completed capability. |
| Mission Review | Completed Mission, before terminal completion is recorded. |
| Custom | An explicit, versioned set of Action, Intent, Capability, and/or Mission boundaries. |

The resolved policy is persisted with the Mission, so a later Workspace profile change cannot reinterpret active work.

## State and resume

`AWAITING_APPROVAL` is a distinct durable Mission State, not a failure or recovery state. It records policy, structured pause reason, completed boundary, resume point, and evidence. Resume requires an auditable approval record with identity, actor, timestamp, and decision reference. It returns to `ACTIVE`, or records `COMPLETED` for a Mission Review. Completed Actions are never repeated.

## Governance and boundaries

Governance Profiles provide defaults while explicit Execution Policy may override them: Solo maps to Continuous, Duo to Engineering Intent Review, Professional to Engineering Action Review, and Enterprise to Custom. Startup compatibility resolves to Engineering Action Review. Business Workspace and Architecture Workspace approvals are unchanged.

The Approved Mission Dispatcher keeps the single active Mission while paused. The AI Mission Planner continues only after approval. The Execution Host and adapter receive the same Runtime Prompt and return the same evidence for every policy; they are unaware of policy and approval data.

## Out of scope

Business or Architecture approval changes, Host changes, cloud execution, parallel Missions, and parallel Engineering Actions remain out of scope.
