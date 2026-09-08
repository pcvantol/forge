# Canonical product versioning adoption

Forge adopts Forge Platform's [canonical product versioning policy](https://github.com/pcvantol/forge-platform/blob/main/docs/architecture/CANONICAL_PRODUCT_VERSIONING.md), policy v1.

`product-version.json` (`product=forge`, `schema_version=1`, `version`) is
Forge's only product-release version source. The checked-in baseline is
`2.3.0`; it is not evidence of a published release. Its version does not change
Forge schema, Mission, Producer Contract, Execution Host Contract or provider
compatibility versions.

The helper separates read-only `--check`, non-mutating planning, and an
explicit guarded apply (`--bump patch|minor` or `--set-version X.Y.Z`). An
apply requires an operation ID, expected Git head, expected baseline version,
event/branch lineage and policy revision. It writes a committed durable receipt
under `.github/product-version-operations/`; the same operation ID and inputs
return the same target, while altered inputs conflict. The receipt is staged
before the manifest so an interrupted local write can be resumed without
deriving a second bump. Each file uses atomic replacement, but this is not a
cross-file transaction: a caller must commit and qualify the complete resulting
candidate as one delivery boundary. The helper does not commit, push,
qualification, artifact publication or compatibility approval. Stable release publication remains
blocked unless an explicit compatibility classification, approved exact source,
exact target version and immutable artifact identity are supplied.

Engineering Platform PR [#105](https://github.com/pcvantol/engineering-platform/pull/105)
is the pending source-level bounded version-preparation adapter. It validates a
declared product helper, isolates its candidate, verifies its allowlisted
receipt/projection diff and binds exact-head qualification evidence. It is not
yet installed-runtime evidence, a version grant, a protected merge authority or
publication proof; Forge therefore retains the fail-closed boundary below.

The workflow intentionally has read-only permissions. The former token-pushed
version commit could not prove qualification of its new SHA and could not safely
provide exactly-once event delivery. The required protected version-preparation
delivery route must bind operation ID, event/branch lineage, expected head and
policy revision before automated feature-patch/main-minor allocation is enabled.
Until then this repository has no automatic version writer; builds consume the
committed source only. This is product-owned groundwork, not Forge's future
generic version/release planner.

## Candidate delivery and release guard

Forge's active `main` ruleset requires a pull request and the exact `Test and
static validation` status. The normal PR workflow checks out the PR head, so a
version-preparation commit pushed to an existing PR receives qualification for
that new candidate rather than borrowing the preceding head's result. The
repository currently has no authorized GitHub App, trusted dispatch route, or
write-capable workflow that can create that preparation commit; the helper and
workflow therefore do not attempt one.

Before any existing authorized publication route can act, its caller must run
`--verify-release-candidate --release-branch release-X.Y.Z --approved-head
<exact-sha> --approved-version X.Y.Z`. This read-only guard requires the
current branch name, canonical source and exact checked-out head to agree. It
does not treat a branch name as approval, establish compatibility, inspect a
registry, create a tag, or publish an artifact. Those facts must be supplied
and recorded by the authorized release route.
