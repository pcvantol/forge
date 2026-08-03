# Forge Core Concepts

Forge 0.2 creates stable, local-only data contracts for future capabilities.
Every contract has a `schema_version` and a standalone JSON Schema under
`schemas/`. Python dataclasses in `forge.models` mirror those contracts for
local callers without adding a framework dependency.

| Concept | Stable responsibility | Explicitly not responsible for |
| --- | --- | --- |
| Workspace | Represents a software product and selected operating profiles. | Repository execution. |
| Repository | Identifies one repository and its local locator. | Workspace role or authority. |
| Mission | Is the Architect-approved engineering contract for an objective, architectural boundaries, success criteria, and constitutional constraints. | Predeclare or directly execute Engineering Intents. |
| Mission Planner | Is Forge's future iterative planning owner for Mission sequencing, dependencies, evidence evaluation, and dynamic Intent creation. | Replace human governance or execute work. |
| Engineering Intent | Is a dynamic, model-independent planning artifact created by the Mission Planner; it preserves tactical rationale, boundaries, validation, evidence, and architectural traceability and contains Engineering Actions. | Provider-specific prompting, direct execution, persistence, or Architect approval. |
| Engineering Action | Is the smallest intentional executable engineering unit within an Intent and produces a Runtime Prompt. | Expanding its Intent, provider execution, persistence, or approval. |
| Agent Role and Model Selection Policy | Deterministically selects a Forge-owned role, provider-neutral model and reasoning profiles, and execution constraints for an Action. | Provider resolution, model invocation, execution, or host override. |
| Workspace Readiness | Assesses whether a Workspace is prepared for a declared execution profile. | Completing a phase or executing work. |
| Product Identity | Defines a separately governed public product identity. | Making runtime names architectural concepts. |
| Runtime Prompt | Is a temporary, provider-specific execution representation produced from an Engineering Action. | Defining canonical engineering work or measuring repository drift. |
| Prompt Artifact | Is the versioned, provider-neutral transitional execution representation retained from bootstrap. | Replacing Engineering Intent or serving as input to a Runtime Prompt. |
| Repository Catalog | Assigns repository roles and enforces one canonical entry. | Git operations. |
| Knowledge Source | Declares a versioned, read-only external evidence provider and its authority/lifecycle metadata. | Editing, synchronizing, extracting, or authoring that source. |
| Capability | Declares a reusable engineering capability. | Implementing or running it. |
| Engineering Mode | Catalogs maturity choices. | Activating a choice by itself. |
| Governance Profile | Resolves human roles, assignments, approvals, workspace visibility, advisors, execution permissions, and explicit shortcuts for one canonical lifecycle. | Replacing human approval or defining a separate workflow. |

`forge.core.JsonStore` is the initial persistence boundary: a local UTF-8 JSON
file with sorted keys and indentation. It is deterministic, versionable, and
human-readable. It has no database, network, or runtime-execution dependency.

Engineering Intent is an architectural concept in 0.8 only; it is not yet a
stored Forge contract. See [Engineering Intent Architecture 0.8](engineering-intent.md).

The permanent authority boundaries are defined once in [Architecture
Principles](architecture-principles.md). Workspace Readiness is a generic,
future capability with initial Genesis and Managed profiles; see [Workspace
Readiness](workspace-readiness.md).

The canonical engineering chain is:

```text
Vision → Architecture → Roadmap → Mission → Mission Planner → Engineering Intent → Engineering Action → Runtime Prompt → Execution Host → Repository → Evidence → Mission Planner
```

Runtime Prompt Generation 1.9 is the existing local derivation contract. The
Engineering Action architecture defines the canonical future source boundary;
any contract migration remains a future capability. Concrete Prompt Generators
and Runtime Providers remain future capabilities.
Prompt Artifact remains compatible as the transitional bootstrap
representation and is not an input to a Runtime Prompt.
