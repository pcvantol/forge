# Forge Workspace Model

> **Productization status:** this is the historical Foundation model of a
> Forge-owned declarative Workspace aggregate. It remains valid repository
> provenance and compatibility context, but it is not the authority for the
> separate Workspace product's interaction/control-plane role. The current
> target division is in [Productization Reconciliation](FORGE_PRODUCTIZATION_RECONCILIATION.md).

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

Bootstrap selects `prototype` and the legacy persisted `solo` catalog value.
Those values are not the canonical Governance Profile Definition. The
[Governance Profile Model](governance-model.md) defines the canonical Solo,
Duo, Startup, and Enterprise scaling vocabulary and the required compatibility
path for a later versioned contract.

## Governance Profile consumption

The selected Governance Profile is resolved by future Workspace capabilities
as declarative context: role assignments, approval authority, workspace
visibility, advisor availability, execution permissions, and explicit
shortcuts. Business, Architecture, Execution, and Analytics Workspaces remain
canonical regardless of profile. A Workspace consumer must render or enforce
the resolved policy without changing the product lifecycle, creating a
profile-specific workflow, or inferring approval from the profile selection.

## Portfolio relationship

The future Portfolio is the Business Workspace's governance and learning view.
It owns Mission Candidates, prioritisation, business value, and strategic
alignment; it does not own engineering. Only a Mission approved by the
Platform Architect after Business Review and Architecture Review may enter
Mission Intake and the Forge CLI. Engineering outcomes can produce advisory
Mission Recommendations for the Portfolio, but neither the Portfolio nor a
Workspace creates executable Missions autonomously. The canonical flow is in
the [Product Model](product-model.md). Changing from Solo to Duo, Startup, or
Enterprise changes assignments only; it preserves Workspace identity, Mission
records, and the canonical workflow.
