# Forge Core Concepts

Forge 0.2 creates stable, local-only data contracts for future capabilities.
Every contract has a `schema_version` and a standalone JSON Schema under
`schemas/`. Python dataclasses in `forge.models` mirror those contracts for
local callers without adding a framework dependency.

| Concept | Stable responsibility | Explicitly not responsible for |
| --- | --- | --- |
| Workspace | Represents a software product and selected operating profiles. | Repository execution. |
| Repository | Identifies one repository and its local locator. | Workspace role or authority. |
| Repository Catalog | Assigns repository roles and enforces one canonical entry. | Git operations. |
| Knowledge Source | Declares a versioned, read-only external evidence provider and its authority/lifecycle metadata. | Editing, synchronizing, extracting, or authoring that source. |
| Capability | Declares a reusable engineering capability. | Implementing or running it. |
| Engineering Mode | Catalogs maturity choices. | Activating a choice by itself. |
| Governance Profile | Catalogs human authority shapes. | Replacing human approval. |

`forge.core.JsonStore` is the initial persistence boundary: a local UTF-8 JSON
file with sorted keys and indentation. It is deterministic, versionable, and
human-readable. It has no database, network, or runtime-execution dependency.
