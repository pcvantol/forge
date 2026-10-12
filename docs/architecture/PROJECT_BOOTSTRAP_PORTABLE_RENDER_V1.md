# Portable project basis — PB-F0 and first PB-F1 profile

Assignment: `L3-PROJECT-BOOTSTRAP-BASELINE-RENDER-V1-20261012`, R50.
This implements a proposal renderer, not repository bootstrap execution.
The canonical [holistic bootstrap design](PROJECT_BOOTSTRAP_AND_ARTIFACT_MANIFEST_V1.md)
and [qualification catalogue](PROJECT_BOOTSTRAP_QUALIFICATION_V1.md) retain their full scope.

## What a user can do

Describe the product explicitly, select the supported document profile and supply
identity/source references. Forge produces a finite inspectable proposal bundle.
A child references its authority repository and has no competing vision/roadmap.
Unknown architecture and decisions remain visible questions. An empty draft DAG
has no approved capabilities, automatic Candidate or Mission.

```sh
forge-project-bootstrap catalog
forge-project-bootstrap validate-input --input description.json
forge-project-bootstrap render --input description.json --export new-proposal
forge-project-bootstrap check-bundle --bundle new-proposal
bash new-proposal/scripts/validate.sh
```

`new-proposal` must not exist. All parents must be real directories; a symlink
parent is rejected, including operating-system aliases. Choose an explicit
canonical parent. It is an export workspace, never a selected target repository.
An existing `.git` ancestor rejects export into a repository. There is no overwrite, Git initialization, commit, provider request or runtime
journal. `--data-root` remains installation storage and is not an export option.

Use the [authority input](../../examples/project-bootstrap/authority-input.json)
or [child input](../../examples/project-bootstrap/child-input.json) as a synthetic
example. Edit explicit product facts and reference bindings rather than deriving
IDs from names/paths/URLs. `OWNER_REGISTERED_REFERENCE` records the caller's
supplied reference, not independent verification or registration by this renderer.
Do not place secrets or private operational data in an export proposal.

## Finite contracts and actual support

All contracts are packaged under `forge/project_bootstrap/assets`:
`input.schema.json`, `manifest.schema.json`, `project-contract.schema.json`,
`project.schema.json`, `governance.schema.json`, `dag.schema.json`,
`baseline-lock.schema.json`, `catalog.schema.json`, `capability.schema.json` and
`operation-proposal.schema.json`. The latter describes PLANNED operations only;
it does not expose an approval/apply API. Objects are closed, versions and
proposal-only state are explicit; unknown required input fails before export.
The finite evaluator has no external resolver and rejects unsupported keywords.

- Contract `pb-render/1.0`, renderer `1.0.0`, baseline `portable-docs/1.0.0`.
- Document language: `en` only. Unsupported languages reject, never fall back.
- `GENESIS` / `LOCAL_POSIX`: local portable documents, no `.github` output.
- `MANAGED` / `GITHUB_DOCUMENTS`: same documents plus pinned actual validation
  workflow and PR template; desired check is `portable-documents` from that
  workflow. Actual host governance is `NOT_ASSESSED`.
- Authority and child variants; `NO_PRODUCT_CODE` / `DOCUMENT_ONLY`.
- Product license `UNDECIDED`. No implicit provider, CodeQL, dependency scanner,
  ownership policy, application stack, cloud account or product license.

Other profiles remain unsupported/planned. Coverage for a proposal containing
no product code is `NOT_APPLICABLE_NO_PRODUCT_CODE`, not fictitious 100%.
The original authored portable baseline carries Forge's Apache-2.0 provenance
and component hashes; this does not select a license for the described product.
This candidate baseline is not a publicly released baseline. Its protected-source
and wheel qualification are separate records. An upgrade never rewrites old pins.

## Determinism, trust and portable validation

Canonical JSON is sorted UTF-8 with LF, duplicate keys/nonfinite values reject.
Paths are finite ASCII POSIX paths, modes0644, text UTF-8; no user-supplied path
inventory or include resolver. The manifest binds frozen input, renderer source,
artifact IDs/conditions/owners/classes/versions, ABSENT preconditions, sizes,
maximums and after hashes. It excludes its own bytes; `manifest_digest` is omitted
when computing that digest. Full artifact bytes are bound separately by receipts.
There is no clock, random ID, environment-derived identity or model invocation.

The installed service verifies its independently pinned catalog and every asset,
validates input/output schemas and compares every bundle byte/mode to re-rendered
expected content. The portable validator embeds the same original renderer,
schema evaluator and bounded I/O source, without importing sibling/project code
or Forge/EP. Its trusted catalog projection excludes only its own file hash to
avoid recursion. The generated POSIX wrapper embeds the validator hash and checks
it before execution under isolated Python3.14 with sitepackages disabled.

As with any executable tool, trust its externally qualified entrypoint and digest.
An attacker replacing **all** executable entrypoints and their external trust
records is not detectable using a self-asserted in-bundle hash. The installed
`check-bundle` and exact-wheel qualification anchor this distinction; a replaced
always-green validator is an actual negative control. Never execute an arbitrary
untrusted bundle as a substitute for its qualified validator pin.

Before reading bytes, directory/file descriptors forbid symlink traversal and
special files; reads are bounded to131072 bytes and inventory to128 entries.
A descriptor swap cannot redirect the verified file read. Export uses new
exclusive no-follow paths; interrupted exports remain partial, never accepted
or overwritten. Original private failures are retained; public CI uploads contain
only the bounded synthetic receipt, not raw logs, absolute host paths or secrets.

`scripts/build_portable_bootstrap_validator.py` checks reproducible generated
assets by default. Its explicit `--write` is a development operation, not a
runtime downloader or baseline updater. Standard validation checks drift.

## Producer joins and exact scope

B8R `.engineering-platform/repository.json` keeps repository-attachment/1.0:
`project.id`, `project.authority_repository_id`, `repository.id/role` and
`validation`. Forge adds no EP fields, credentials, registration or remote claim.
Provisional/owner references stay in the Forge contract. Exactly one authority
is referenced; the authority-contract reference must match its declared ID.

F2/FH mapping is the local reusable `forge.project_bootstrap.service` and thin
packaged CLI. No PB-F7 HTTP provisioning API is claimed. HOB-F02 remains a
proposed future Workspace presentation/owning HTTP adapter. Existing advisory
primitives and project registers are reused in later selected slices, not copied
or invoked by pure rendering. L2/L4 receive concrete candidate contract/bundle
handoffs without becoming an ACK/full-implementation gate. Their scope and pins
remain unchanged.

Qualified scope maps PB-12/13/15/17/18/39/40 and portable portions of
PB-01/14/16/22/31/32/36/37. PB-14 proves no export overwrite, not adoption.
PB-31 proves child references, not distributed bootstrap. PB-32 proves own
service/CLI, not unavailable HTTP parity. Installed proofs use only own disposable
exports and genuine installed wheels with no development-source reads/network.
PB-F2..FQ, repository mutation, readiness, remote governance, live EP/Workspace
and full multi-language/stack onboarding remain open.

Source-level candidate tests and independent review do not preclaim protected
merge or exact-final-main proof. Delivery/finalization receipts record those
actual stages separately. No public release or automatic successor is authorized.
