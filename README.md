# Forge

Forge is a local-first, AI-native engineering platform foundation. It gives an
engineering workspace a small, explicit vocabulary before it gains automation:
the workspace it operates in, the repositories it knows, and the human
governance that constrains its work.

## Version 0.5 scope

Forge 0.2 defines a versioned Foundation Model. It includes:

- separate Workspace, Repository, Repository Catalog, Knowledge Source, and
  Capability contracts;
- full Engineering Mode and Governance Profile value catalogs;
- bootstrap activation of `prototype` and `solo` only;
- deterministic, human-readable local JSON persistence; and
- versioned JSON Schemas, an example, architecture records, and tests.

Forge 0.3 additionally loads one versioned Foundation Document through a
strictly local pipeline: version detection, packaged-schema resolution,
validation, immutable model construction, cross-reference checks, and a
deterministic validation report. It does not fetch schemas or follow document
supplied `$schema` values.

Forge 0.4 adds a local Knowledge Source Registry and a deterministic,
metadata-only consumption interface. Registered sources declare their version,
reference, trust classification, lifecycle, and mandatory read-only access
mode. Consumption returns source evidence references only; it performs no
source extraction, semantic retrieval, LLM call, or mutation.

Forge 0.5 adds Engineering Planning Foundation: versioned, local contracts
for Goals, Increment Proposals, Plans, dependencies, risk, rationale, and
typed evidence references. The planning loader and registry validate and
persist declarations only. Plans do not retrieve knowledge, approve work,
operate repositories, execute tools, or create commits.

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

## Knowledge consumption

Knowledge sources remain external, versioned evidence providers. Certified
sources are authoritative; registering a reference or a generated Forge output
does not make it authoritative knowledge. Forge persists only its own local
declarations and never modifies a source. See
[Knowledge Consumption 0.4](docs/architecture/knowledge-consumption.md).

## Engineering planning

Planning references Knowledge Sources, evidence records, architecture
documents, and foundation documents without copying their content. When a
known source set is supplied, the loader rejects unknown knowledge-source
references; all processing remains local and deterministic. See
[Engineering Planning Foundation 0.5](docs/architecture/engineering-planning.md)
and [the example](examples/planning.example.json).

## Roadmap direction

The next increment can define the governed Architect Provider boundary for
read-only, evidence-backed planning assistance and human review. It must not
add agents, runtime execution, remote APIs, cloud services, or write access
without a separate foundation decision.

See [docs/architecture/core-concepts.md](docs/architecture/core-concepts.md),
[docs/architecture/workspace-foundation.md](docs/architecture/workspace-foundation.md),
and [docs/handoff/forge-bootstrap-increment-002.md](docs/handoff/forge-bootstrap-increment-002.md).
