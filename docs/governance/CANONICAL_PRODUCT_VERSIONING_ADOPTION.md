# Canonical product versioning adoption

Forge adopts Forge Platform's [canonical product versioning policy](https://github.com/pcvantol/forge-platform/blob/main/docs/architecture/CANONICAL_PRODUCT_VERSIONING.md), policy v1.

`product-version.json` (`product=forge`, `schema_version=1`, `version`) is
Forge's only product-release version source. The checked-in baseline is
`2.3.0`; it is not evidence of a published release. Its version does not change
Forge schema, Mission, Producer Contract, Execution Host Contract or provider
compatibility versions.

The helper separates read-only `--check`, non-mutating planning, and an
explicit guarded apply (`--bump patch|minor` or `--set-version X.Y.Z` with an
optional expected baseline). It performs a single-file atomic replacement, but
does not claim a cross-file transaction, commit, push, qualification, artifact
publication or compatibility approval. Stable release publication remains
blocked unless an explicit compatibility classification, approved exact source,
exact target version and immutable artifact identity are supplied.

The workflow intentionally has read-only permissions. The former token-pushed
version commit could not prove qualification of its new SHA and could not safely
provide exactly-once event delivery. The required protected version-preparation
delivery route must bind operation ID, event/branch lineage, expected head and
policy revision before automated feature-patch/main-minor allocation is enabled.
Until then this repository has no automatic version writer; builds consume the
committed source only. This is product-owned groundwork, not Forge's future
generic version/release planner.
