# Forge Agent Role and Model Selection Policy 1.0

## Purpose

Forge owns deterministic selection of the Agent Role, Model Profile, Reasoning
Profile, and execution constraints for an Engineering Action. The policy makes
those choices before Runtime Prompt rendering. It is a local contract only: it
does not invoke an AI provider, resolve a provider, choose credentials, or
operate an Execution Host.

```text
Mission → Architecture Review → Mission Recommendation → Mission Planner
→ Engineering Action → Agent Role Policy → Model Selection Policy
→ Runtime Prompt Renderer → Execution Host
```

The Architecture Review Engine already exists as Forge 3.6 and remains the
next prerequisite for its evidence-led recommendation loop; this policy does
not replace, reorder, or implement that engine.

## Canonical policy contract

`forge.models.agent_policy` provides the immutable, versioned `1.0` policy
contract. `AgentPolicySelectionRequest` accepts Mission and Action identity,
work kind, repository context, reasoning depth, long-context requirement,
validation requirement, cost policy, and latency policy. It deliberately has
no provider id, provider type, model name, host id, transport, or credentials.

The closed canonical roles are Business Advisor, Architecture Advisor, Mission
Planner, Engineering Agent, Documentation Agent, Validation Agent,
Qualification Agent, Governance Agent, and Execution Observer. The policy
returns a provider-neutral Model Profile (`fast`, `balanced`, `deep_reasoning`,
`long_context`, `code_generation`, `documentation`, `validation`, or `review`)
and a Reasoning Profile (`light`, `standard`, or `deep`).

Each selection also returns immutable execution constraints and a stable
SHA-256 digest. Version and digest make the decision reproducible and provide
provenance without making a Runtime Prompt a policy-authoring record.

## Provider and host independence

Provider resolution is a later, distinct concern. The existing AI Provider
Registry qualifies and selects replaceable provider declarations; it is not an
Agent Role or Model Selection decision. A provider can be added, retired, or
requalified without changing Mission planning or this policy contract.

Execution Hosts receive only a rendered Runtime Prompt. The Codex CLI renderer
projects policy version, decision digest, and host-facing execution constraints
only. It never exposes the Agent Role, Model Profile, Reasoning Profile, or a
provider choice to a Host. The Execution Host Contract explicitly forbids Hosts
from selecting or overriding Agent Role, Model Profile, Reasoning Profile, or
Execution Host selection.

## Workspace integration

The Business Workspace owns approved Mission candidates and human priorities.
The Architecture Workspace evaluates Repository Truth and produces advisory
Mission Recommendations through the Architecture Review Engine. The Execution
Workspace plans and executes approved Mission work: the Mission Planner creates
Intent and Action context, Forge applies this policy, the Runtime Prompt
Renderer projects its execution consequences, and the Host returns evidence.
Neither a provider nor a Host changes Business or Architecture authority.

## Boundary and next increment

This policy is deterministic; it performs no optimization, dynamic routing,
provider SDK use, model invocation, prompt execution, or runtime adaptation.
No provider implementation should be introduced before the Architecture Review
Engine is complete and reconciled. Repository evidence currently records that
engine as implemented, so the next architectural work is to integrate its
recommendation output with the Mission Planner—not a provider implementation.
