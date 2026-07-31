# Forge Workspace Foundation 0.1

## Intent

Forge begins with a declarative local workspace model rather than an execution
runtime. The model provides a stable boundary for later engineering
orchestration while preserving repository-first practice and human authority.

## Concepts

| Concept | Meaning in 0.1 | Boundary |
| --- | --- | --- |
| Workspace | A named local engineering context. | Holds metadata, mode, governance profile, and a catalog. |
| Repository catalog | The ordered set of repositories known to a workspace. | Descriptive only; it performs no repository operation. |
| Canonical repository reference | Stable identity for a catalog entry. | `provider` plus `owner/name`; it is not inferred from a filesystem path. |
| Workspace metadata | Creation, update, runtime, and optional description data. | Records context, never credentials or execution history. |
| Engineering mode | The intended maturity of work. | 0.1 permits only `prototype`. |
| Governance profile | The authority model for decisions. | 0.1 permits only `solo`; human approval remains required. |

## Data boundary

`schemas/workspace.schema.json` is the versioned interchange contract. A valid
0.1 document has a `schema_version`, a `workspace`, and `repositories`.

```text
Workspace Foundation document
  ├── Workspace identity and metadata
  ├── Engineering mode: prototype
  ├── Governance profile: solo
  └── Repository catalog
        └── Canonical repository reference + local path
```

The canonical reference is the repository identity. The local path is a
workspace-specific locator and can change without changing identity. Metadata
is intentionally narrow and string-valued for catalog extension without
introducing a product domain model.

## Invariants

- Git remains the source of truth for a repository; catalog data does not
  replace repository history, configuration, or governance.
- Knowledge sources are read-only to Forge operations.
- Certified knowledge is authoritative where it applies; generated artifacts
  are derived and non-authoritative.
- The foundation does not store secrets, tokens, credentials, raw prompts, or
  execution logs.
- A valid catalog entry has one canonical reference and one local path.
- Forge 0.1 has no mutation capability: no clone, branch, commit, push, pull
  request, deployment, or cloud call is defined by this model.
- Human governance is required for all future execution capabilities.

## Extensibility

Schema versions are explicit. A future version may add a new mode, profile,
repository source kind, or lifecycle metadata only through a documented,
backward-compatibility-aware schema change. It must not silently reinterpret
the 0.1 contract.

## Non-goals

This foundation is not a UI, SaaS product, cloud service, multi-user system,
knowledge base, or engineering agent. It establishes the smallest portable
contract on which those capabilities can later be considered.
