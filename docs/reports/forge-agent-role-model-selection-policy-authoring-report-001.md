# Forge Agent Role and Model Selection Policy Authoring Report 001

## Result

Forge now owns an immutable, versioned deterministic policy that maps a bounded
Engineering Action context to an Agent Role, provider-neutral Model Profile,
Reasoning Profile, execution constraints, rationale, and stable decision digest.
The model contains the nine canonical roles and does not contain provider,
credential, transport, or host implementation data.

Agent Roles belong to Forge because they allocate engineering responsibility
within the Mission-to-Action planning chain. Model Selection belongs to Forge
because it is a planning constraint, not an execution transport decision.
Execution Hosts remain provider-agnostic because they receive only a Runtime
Prompt carrying policy provenance and execution constraints. They cannot select
or override role, model, reasoning, or host selection.

Providers can later be replaced by changing the separately qualified Provider
Registry mapping, without changing Mission planning, Agent Role policy, or
Engineering Action identity. The Business Workspace retains Mission priority
and approval, the Architecture Workspace retains evidence-led recommendation,
and the Execution Workspace applies policy before rendering a Host artifact.

## Verification boundary

Regression coverage verifies role selection, profile selection, deterministic
canonicalization and digesting, policy versioning, absence of provider or host
resolution, policy constraints, Runtime Prompt projection, and Host override
prohibitions. No provider invocation or Execution Host operation occurred.

## Recommended next architectural increment

The repository already records Architecture Review Engine 3.6 as implemented.
The next increment should integrate its approved advisory recommendation output
with the Mission Planner. Do not implement a provider before that Architecture
Review Engine integration is complete.
