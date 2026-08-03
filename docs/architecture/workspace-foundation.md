# Forge Workspace Model

## Boundary

A Workspace represents one software product, never a single repository. It
holds product identity, a reference to one Repository Catalog, and its selected
Engineering Mode and Governance Profile. The catalog then names the product's
canonical repository and any supporting, documentation, or future capability
repositories.

```text
Workspace
  ├── Repository Catalog ──> Repository identities
  ├── Engineering Mode
  └── Governance Profile
```

The model is declarative. It does not discover, clone, inspect, or mutate a
cataloged repository.

## Contract

`schemas/workspace.schema.json` is the versioned Workspace interchange
contract. The 0.2 Workspace references a catalog by stable ID rather than
embedding repositories. This keeps product identity, repository identity, and
catalog role distinct.

Bootstrap selects `prototype` and `solo`. Those are active values, not the
entire available-value catalog.

## Portfolio relationship

The future Portfolio is a Workspace-level governance and learning view. Mission
Candidates enter through the Business Workspace; only an approved Mission may
enter Mission Intake and the Forge CLI. Engineering outcomes can produce
Mission Recommendations for the Portfolio, but neither the Portfolio nor a
Workspace creates executable Missions autonomously. The canonical flow is in
the [Runtime Evolution Roadmap](runtime-evolution-roadmap.md).
