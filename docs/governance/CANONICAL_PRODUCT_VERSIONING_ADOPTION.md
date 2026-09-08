# Canonical product versioning adoption

Forge adopts Forge Platform's [canonical product versioning policy](https://github.com/pcvantol/forge-platform/blob/main/docs/architecture/CANONICAL_PRODUCT_VERSIONING.md), policy v1.

`product-version.json` is Forge's only product-release version source. Its
version does not change Forge schema, Mission, Producer Contract, Execution
Host Contract or provider compatibility versions. Those remain independent,
explicit contracts. `scripts/advance_product_version.py` and the scoped
`Canonical product versioning` workflow are the only automatic mutators.
