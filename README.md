# Forge

Forge is a local-first, AI-native engineering platform foundation. It gives an
engineering workspace a small, explicit vocabulary before it gains automation:
the workspace it operates in, the repositories it knows, and the human
governance that constrains its work.

## Version 0.1 scope

Forge 0.1 defines a versioned Workspace Foundation only. It includes:

- a workspace metadata contract;
- a repository catalog with canonical repository references;
- explicit `prototype` engineering mode and `solo` governance profile;
- a JSON Schema and a valid example; and
- architecture, governance, roadmap, and bootstrap-evidence records.

It intentionally does not include a UI, SaaS service, cloud runtime,
multi-user model, agent runtime, repository mutation engine, or remote
integration.

## Bootstrap context

Forge is a new product and an independent Git repository. It is not a rename,
migration, or modification of Engineering Platform 1.5. During this bootstrap,
Engineering Platform 1.5 provides the local Codex CLI execution context only.
Forge makes no runtime dependency on it.

## Working model

Start with the schema and example:

```text
schemas/workspace.schema.json
        +
examples/workspace.example.json
```

A workspace owns descriptive metadata and a catalog. Each catalog entry has
one canonical repository reference, expressed as a stable repository ID plus
one local path. The catalog is declarative; it does not clone, modify, push,
or otherwise operate on any repository.

## Knowledge sources

This bootstrap used the AI Platform Engineering Knowledge Base as a read-only
source of generic principles: certified knowledge authority, traceability,
metadata, and human-governed lifecycle decisions. DJConnect and Technical Debt
Engine were observed only as read-only reference implementations for patterns
such as repository-first operation, explicit scope, evidence, and stable public
contracts. No product code, product architecture, or domain concepts were
copied into Forge.

The evidence record is in
[docs/evidence/bootstrap-evidence.md](docs/evidence/bootstrap-evidence.md).

## Roadmap direction

The next increment should load and validate a local Workspace Foundation file
without performing repository mutations. Subsequent increments can add
repository discovery and human-approved execution plans only after their
governance and evidence contracts are explicit.

See [docs/roadmap/0.1.md](docs/roadmap/0.1.md) for the bounded roadmap and
[docs/architecture/workspace-foundation.md](docs/architecture/workspace-foundation.md)
for the architecture.
