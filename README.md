# Forge

Forge is a local-first, AI-native engineering platform foundation. It gives an
engineering workspace a small, explicit vocabulary before it gains automation:
the workspace it operates in, the repositories it knows, and the human
governance that constrains its work.

## Version 0.2 scope

Forge 0.2 defines a versioned Foundation Model. It includes:

- separate Workspace, Repository, Repository Catalog, Knowledge Source, and
  Capability contracts;
- full Engineering Mode and Governance Profile value catalogs;
- bootstrap activation of `prototype` and `solo` only;
- deterministic, human-readable local JSON persistence; and
- versioned JSON Schemas, an example, architecture records, and tests.

It intentionally does not include a UI, SaaS service, cloud runtime,
multi-user model, agent runtime, repository mutation engine, or remote
integration.

## Bootstrap context

Forge is a new product and an independent Git repository. It is not a rename,
migration, or modification of Engineering Platform 1.5. During this bootstrap,
Engineering Platform 1.5 provides the local Codex CLI execution context only.
Forge makes no runtime dependency on it.

## Working model

Start with the Foundation Model schemas and example:

```text
schemas/
        +
examples/foundation.example.json
```

A Workspace is a software product, not a repository. It references a separate
Repository Catalog, which assigns exactly one canonical repository and any
supporting, documentation, or future-capability repositories. Repository
identity remains independent of its catalog role. The catalog is declarative:
it does not clone, modify, push, or otherwise operate on repositories.

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

See [docs/architecture/core-concepts.md](docs/architecture/core-concepts.md),
[docs/architecture/workspace-foundation.md](docs/architecture/workspace-foundation.md),
and [docs/handoff/forge-bootstrap-increment-002.md](docs/handoff/forge-bootstrap-increment-002.md).
