# Forge Bootstrap Increment 002 Handoff

## Outcome

Forge now has a Foundation Model 0.2: separate versioned contracts for
Workspace, Repository, Repository Catalog, Knowledge Source, Capability,
Engineering Mode, and Governance Profile. It remains local-only and
declarative.

## Architecture decisions

- A workspace is a product container, not a repository container.
- Repository identity is separate from its catalog role.
- Repository Catalog owns canonical/supporting/documentation/capability roles
  and requires exactly one canonical repository.
- Mode and profile catalogs include every declared value; bootstrap activation
  is separately `prototype` and `solo`.
- Knowledge Sources are immutable-to-Forge evidence providers.
- JSON files via `JsonStore` are the deterministic initial persistence layer.

## Validation

Run `python3 -m unittest discover -s tests -v` and `git diff --check`.
The tests cover every Foundation Model contract, catalog invariants, full mode
and profile catalogs, read-only knowledge sources, declared capabilities, and
deterministic JSON persistence.

## Known limitations

- There is no composite Foundation document loader or cross-document resolver.
- JSON Schema alone cannot reject one repository ID appearing in two different
  catalog role arrays; `RepositoryCatalog` enforces that local invariant.
- No UI, API, cloud, scheduler, multi-user model, repository execution, or
  capability implementation exists.

## Recommended next increment

Implement a local, read-only Foundation document loader and validator. It
should resolve the existing schemas and model invariants, produce actionable
errors, and perform no repository or network operation.
