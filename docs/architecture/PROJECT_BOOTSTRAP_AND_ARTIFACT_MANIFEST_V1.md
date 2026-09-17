# Project bootstrap and artifact manifest V1

**Increment:** `PROJECT_BOOTSTRAP_AND_ARTIFACT_MANIFEST_V1`. **Owner:** Forge.
**Status:** canonical target design after protected merge; implementation and installed qualification remain **PLANNED**. **Version decision:** NO_BUMP.

This is the detailed project-bootstrap decomposition of L1/L1-R, consuming L0 and the qualified F2/FH application-service boundary. It refines [self-contained bootstrap](self-contained-engineering-contract-bootstrap.md), not a second initializer or execution engine. The [roadmap](../roadmap/PROJECT_BOOTSTRAP_V1.md), [documentary DAG](../roadmap/project-bootstrap-v1.json), [artifact inventory](project-bootstrap-artifact-manifest-v1.json) and [qualification catalogue](PROJECT_BOOTSTRAP_QUALIFICATION_V1.md) are one design. EP owns its companion `docs/engineering/PROJECT_BOOTSTRAP_EXECUTION_V1.md`; Workspace owns `docs/PROJECT_BOOTSTRAP_V1.md`.

## 1. Evidence, scope and three different operations

Source observations on 2026-09-17: Forge `eee7f8dadd5b2df9e836627b43de4928a46eeb35`, EP `d7fe0af363fb36f1f819fedc7a63919e01b88e66`, Workspace `92da171c97dc3f67cc844125b08cf8a2a0e56a1e`. These identify reviewed source, not installed capabilities. At that Forge source, `forge server init` initializes/open-validates the installation data root and `forge.db`; it does not create a product, repository, baseline tree, approval or Mission. `execution-host configure` binds already-issued peer/project identities. Existing Solution Templates produce advisory Candidates, not repository scaffolds. EP already has a local Genesis execution profile and B8R attachment primitives; these are reused, not reclassified as a complete cross-product onboarding service.

Keep installation initialization, **project bootstrap**, and approved Mission intake separate. `--data-root` continues to select Forge storage, never a target product checkout. The new project-bootstrap operation is interface-neutral. Exact CLI spelling, HTTP paths and schema bindings are delivered by PB-F7/FH; the names below are design operation names, not newly shipped commands. Existing installations and active projects are not changed by this document.

The outcome is a verifiable product foundation for either Genesis or Managed engineering. It is not automatically a finished application or permission to execute a first Mission. This programme adds no prerequisite to Mission 3 or to the existing configured-repository inner-loop canary.

## 2. Mode, origin and authority are orthogonal

| Requested journey | Repository starting point | Successful foundation disposition |
| --- | --- | --- |
| `CREATE_GENESIS_LOCAL` | A missing or explicitly selected empty directory under an EP-approved workspace root; possibly an unborn Git repository | `GENESIS_READY`, local Git history and local engineering contract, no remote effects |
| `ADOPT_GENESIS_LOCAL` | Existing local content/history whose inventory and adoption have been explicitly accepted | `GENESIS_READY` without overwriting unrelated content or inventing earlier approvals |
| `CREATE_MANAGED_REMOTE` | Explicit provider namespace/name/visibility and an absent remote, or an explicitly verified unborn remote | `MANAGED_READY` only after remote foundation and governance readback |
| `ADOPT_MANAGED_REMOTE` | Existing remote with any committed content, including only a README; local checkout optional | `MANAGED_READY` following drift review and protected delivery of approved additions |
| `PROMOTE_GENESIS_TO_MANAGED` | A qualified local project with existing identity and history | Same project/repository identities and preserved history, with newly qualified Managed binding |

Qualification-only is a separate purpose/retention attribute, not permission to delete or bypass policy. A remote already present during Genesis adoption is reported and left untouched; no push/fetch/API use is implied, and conflicting placement/mode requires an explicit decision. An unavailable Managed remote never causes automatic Genesis fallback. Selecting Genesis does not mean ungoverned, disposable, or fully autonomous development.

Project execution profile, Business/Architecture roles, release/activation policy, and recommended versus committed work priority remain independent. Default new-project progression uses explicit human governance; `AUTO_WHEN_ELIGIBLE` only applies to already-approved released work. Full autonomous selection requires separately recorded bounded delegation under [live roadmap management](LIVE_PROJECT_ROADMAP_MANAGEMENT_V1.md); a template or project creation must never mint it.

## 3. Owning responsibilities and the bootstrap authority boundary

| Concern | Owner and permitted effect |
| --- | --- |
| Product goals, topology interpretation, artifact selection, capability profiles, desired contract/governance and semantic readiness | Forge application services; produce a versioned plan and evaluate source-backed results |
| Human choices, draft presentation, approvals and recovery UX | Workspace through authenticated owning APIs; a UI acknowledgement is not a result |
| Repository inventory, filesystem/Git mutation, remote creation/settings, attachment, locks, execution validation and receipts | EP and its qualified host/provider facilities |
| Definition/adoption of project direction and exceptions | Applicable named Business/Architecture/operator authorities, with scope-bound decisions |
| Product installation, runtime updates and machine lifecycle | Existing product/Forge Platform management; not the project bootstrap service |

Forge never writes the target repository or invokes an EP library/CLI. Forge-to-EP and Workspace-to-owner traffic is authenticated versioned HTTP, also on one machine. Local Forge CLI may call its own services under the qualified local-admin contract. No second scheduler, shared DB, File Inbox fallback, browser-held provider secret or peer import is introduced.

Project bootstrap is a **typed owner-authorized infrastructure operation**, not a fabricated Mission with a fake baseline commit. It creates only approved foundational artifacts/settings. Its capability cannot implement arbitrary product features, relax ordinary Mission admission or promote a draft to an executable Mission. Rich product code generation is a separately governed Mission. Deterministic templates may include selected build/test scaffolding, but only the exact approved bytes, dependencies and effects in the plan.

A project-scoped EP consumer cannot authorize creation of its own missing project or broaden its scope. Creation uses EP's qualified provisioning/operator authority, bound to the reserved target IDs, allowed namespace/path, visibility, artifact-tree digest and expiry. Existing matching credentials are reused; any necessary new scoped grant/credential is a separate explicit owning operation with secure delivery. Failure to obtain that authority yields `AUTHORITY_REQUIRED`; it never prints a bearer or temporarily installs a universal admin token.

## 4. Stable identity before the first commit

Reserve one project identity, one authority repository identity and one operation identity durably through owning services before an external effect. Existing identities are adopted only after exact matching and approval, never regenerated from folder names. The EP declaration `.engineering-platform/repository.json` remains the canonical portable logical attachment declaration; its existing versioned schema is not extended ad hoc. `engineering/project.json` references those identities and defines the Forge-owned project context/artifact mapping, not a second EP topology authority.

A new repository identity must survive the unborn-to-first-commit transition, relocation, worktrees and promotion. Do not bind a new project solely to a path hash and silently change identity when HEAD first exists. Initial commit(s), repository-host immutable resource ID and physical attachment are additional evidence. Explicit fork/import-as-new is different from attaching the same project; copied declarations alone do not authorize attachment. Multiple existing roots or conflicting declared IDs fail closed until an explicit mapping/adoption decision exists.

Exactly one authority repository exists per project. Child repositories retain independent repository IDs and a reference to that authority; they receive only their applicable repository artifacts, not competing copies of the product Vision/roadmap. A multi-repository bootstrap records per-target results and is not a distributed atomic Git transaction. No ordinary Action starts against a partially qualified target.

## 5. Versioned artifact manifest: exact default tree

The new defaults below apply only when this capability is implemented and selected. Existing products are not migrated by this document. The complete conditional inventory is [JSON](project-bootstrap-artifact-manifest-v1.json). Empty directories are not falsely described as tracked Git artifacts.

```text
<authority-repository>/
  .engineering-platform/repository.json
  engineering/
    project.json
    project-contract.json
    baseline.lock.json
    bootstrap-manifest.json
    repository-governance.json
    baselines/<baseline-id>/<version>/...   # exact selected contract assets
  README.md
  BOOTSTRAP.md
  AGENTS.md
  .gitignore
  .gitattributes
  docs/product/VISION.md
  docs/architecture/ARCHITECTURE.md
  docs/architecture/decisions/README.md
  docs/roadmap/ROADMAP.md
  docs/roadmap/capability-dag.json
  docs/engineering/VALIDATION.md
  docs/engineering/HANDOFF.md
  scripts/validate.sh                     # supported POSIX profile only
  .github/workflows/validation.yml         # Managed GitHub only
  .github/workflows/security.yml           # profile-dependent
  .github/workflows/codeql.yml             # only supported/required profile
  .github/CODEOWNERS                       # only approved ownership profile
  .github/PULL_REQUEST_TEMPLATE.md          # Managed GitHub only
  .github/dependabot.yml                   # supported dependency profile
  LICENSE                                 # only an explicit owner choice
  <selected-language build/test scaffold> # explicit finite manifest, optional
```

Genesis and Managed share the product/engineering foundation. Genesis does not create GitHub workflow/ownership assets solely to look Managed. A selected future-Manged asset can be stored as an explicitly dormant proposal, never as proof of active protection. The intended profile is a governed setting; lack of a remote is not a reason to omit product knowledge or local validation.

### Content and authority per artifact family

`project.json`: stable project/authority references, declared repositories and roles, artifact-map revision, product document references, selected bootstrap/technology profile IDs, document language, contract and roadmap source references. No physical checkout, server address, consumer secret or authority grant. All referenced identity values must agree with the EP declaration.

`project-contract.json`: product-pinned baseline identities and hashes, enabled capabilities, validation/proof definitions, applicable DoR/DoD and Human Gates, architecture constraints, governed overlays/exceptions and progression policy references. EP/CI must enforce the materialized project contract without a continuously running Forge. Policy selection does not create runtime approval records. The existing aggregate-production coverage default remains 80% unless a governed exception applies; a project with no production code reports the denominator/not-applicable reason, never fictitious 100% coverage.

`baseline.lock.json` and `baselines/`: selected immutable packaged contract/profile/schema/validator asset versions, license/redistribution metadata and content hashes. Baseline material is copied only from qualified released bundles, not fetched from development repos at runtime. Include the portable contract subset and its qualified validation entrypoint, not a copy of Forge/EP engines. Adoption of a later baseline is a new reviewed changeset; installed product updates do not silently rewrite a project.

`bootstrap-manifest.json`: manifest/schema/renderer versions, operation and plan references, profile selection, approved input digest, exact normalized paths/modes, artifact IDs, template provenance, expected-before hashes or ABSENT, expected-after hashes, ownership/update policy and proof requirements. Its canonical digest excludes the digest field itself. Self-inclusion is represented by manifest identity rather than a recursive hash; resulting Git tree/commit and execution receipts live in the external operation result. The renderer freezes bytes before approval/execution; dates, AI output or randomness do not change bytes on replay.

`repository-governance.json`: mode-specific desired-state profile and supported provider capabilities, default branch, review/required-check/security/merge policy, explicit exceptions and source pins. Genesis records remote controls as `NOT_APPLICABLE_GENESIS`, not PASS. Managed controls are qualified from actual host readback, not this file. Secrets and host-specific endpoints remain in owning operational stores.

`VISION.md`: purpose, intended users/value, outcomes, non-goals, assumptions/risks, constraints and named unresolved questions. `ARCHITECTURE.md`: system boundary, components/interfaces, data/security model, selected technology rationale and unresolved decisions. Human input and approved decisions are distinguished from AI suggestions. Bootstrap need not invent a complete architecture; unresolved issues that affect a proposed Action block that Action's readiness.

`ROADMAP.md` is the human-readable approved direction. `capability-dag.json` is its machine projection with stable capability IDs, explicit dependencies, contribution links, source revision/digest and claim classification. It contains no fake Mission/Action IDs and starts with no claimed completed capabilities. Proposed work is visibly advisory. Contradictory edits produce drift review; neither JSON nor Markdown silently overwrites the approved source. A zero-capability draft is valid for a registered project but is not evidence of engineering-ready scope.

`decisions/README.md` defines decision recording; do not create an ADR stating that someone approved an architecture when no such decision occurred. `HANDOFF.md` is a bounded navigation/status projection with as-of/source references, not runtime state. EP retains execution evidence and telemetry; the repo stores safe references or deliberately published summaries, not operational databases.

`README.md`, `BOOTSTRAP.md` and `AGENTS.md` route humans/tools to actual local product policy and validation. Thin agent guidance does not invent owner approval. Generic rules are materialized from the qualified baseline with license/provenance, not copied from pcvantol-specific histories. `VALIDATION.md` states exact commands, applicable profiles, proof types, failure meanings and unsupported conditions. Scripts fail on missing required tools; no always-green placeholders. Windows/non-POSIX projects receive the selected qualified equivalent and a matching EP validation declaration.

The optional language template has a finite approved path set, dependency locks and test/build entrypoints appropriate to the selected stack (for example .NET, Python, Node or static documentation). It does not imply the application has been implemented. No default public license, cloud account, telemetry vendor or deployment permission is chosen on the owner's behalf.

## 6. Rendering, adoption and update rules

Each selected artifact has an ID, path, required condition, semantic owner, physical writer (EP), renderer/template version, input/output hashes, size/mode/encoding and validation list. The four update classes are `PROJECT_OWNED`, `PINNED_BASELINE`, `DERIVED_PROJECTION` and `APPEND_ONLY_EVIDENCE_REFERENCE`. Creation never turns project-owned files into disposable templates.

For an absent path, creation requires the approved ABSENT precondition. Identical content yields NO_CHANGE with readback. Existing differing project-owned content yields a proposed diff/explicit path mapping, not overwrite. Generated projections require their source revision/digest and expected current hash; a user-edited projection yields conflict/review rather than unconditional regeneration. Accepted new paths or changed mappings revise the plan and invalidate incompatible approvals. Do not create duplicate VISION/README/policy files when adoption can map an existing canonical equivalent; EP's declaration path remains fixed.

Preserve unrelated files, history, staged changes, ignored data and permission bits. Existing uncommitted work is inventoried but never silently committed, stashed or discarded. Execution uses an approved clean checkpoint/isolated workspace or stops with a specific contamination diagnostic. Do not traverse symlink parents, nested repositories, submodules, case-folding/Unicode collisions or linked worktrees outside the approved target; inventory them and require a separately supported profile. Revalidate path/target identity under EP's lock immediately before writes. Reject absolute/traversal paths, reserved .git internals, external URLs-as-template includes, executable hooks and untrusted schema resolution.

## 7. Operation and API semantics

Design operations: `InspectProjectTarget`, `PrepareProjectBootstrap`, `ApproveBootstrapPlan`, `ApplyProjectBootstrap`, `ReadBootstrapOperation`, `ReconcileBootstrapOperation`, `PrepareManagedPromotion`. Implement them through existing owning application services and publish supported operations in F2/FH's versioned inventory. A missing service is UNSUPPORTED, not an invitation to invent a private endpoint or shell shortcut.

Preparation persists an inspectable plan, but performs no target-repository/provider mutation. A request carries caller/installation/project scope, stable operation/idempotency/correlation IDs, expected target/base revision or explicit unborn evidence, pinned manifest/baseline hashes, mode, path-placement reference, remote namespace/resource identity, explicit visibility and approved effect set. The semantic plan includes required decisions, disclosed files/history, tool/network limits, expiry and rollback/retention constraints. Physical target paths are restricted EP-owned placement data and are omitted from portable artifacts.

Approval binds the exact plan digest and effects; a changed preview requires the applicable new decision. EP independently verifies actual authority and persists its accepted operation before effects. Forge stores EP receipt references and its own reconciliation decisions, not copies of EP operational authority. A trusted caller, existing peer binding or UI-selected project does not grant provisioning rights.

Conceptual lifecycle: DRAFT -> PLANNED -> AWAITING_AUTHORIZATION -> ACCEPTED -> APPLYING -> VERIFYING -> RECONCILED. Alternative dispositions include REJECTED, BLOCKED, FAILED, CANCEL_REQUESTED, CANCELLED and EFFECT_UNCERTAIN. These are target operation semantics, not new runtime enums in this change. Show the physical mutation outcome, bootstrap readiness, repository-governance outcome and Mission acceptance separately. `ACCEPTED` is not `READY`; a completed operation can truthfully yield a blocked project.

The operation ledger preserves step identity and intent/result before/after each external boundary. Repeated identical requests return/readback the same operation; different bytes under the same idempotency identity conflict. Loss of acknowledgement triggers bounded readback, not creation of a second repo or fresh submission. Cancellation after an effect records remaining work; it is not proof of rollback. No automatic deletion, force-push, protection removal or credential rotation as compensation. Before a destructive compensation, require exact resource ownership, unchanged expected state and explicit corresponding authority. Otherwise preserve partial resources and surface a recovery decision.

## 8. Complete Genesis flow

1. Resolve the exact allowed direct-child workspace target and placement on an eligible EP host; reject the host product repo, another active project or an ambiguous/nested target. Scope expansion beyond the existing Genesis placement contract is separate, not implicit here.
2. Inspect existing content, Git metadata and optional declared identities without executing hooks, repository scripts or network operations. Distinguish absent directory, empty directory, unborn Git and existing committed local repo. Freeze adoption exclusions and a clean baseline where necessary.
3. Prepare the common artifact tree from installed baselines and owner-approved product inputs. Explicitly select Genesis-local delivery/validation; remote controls have a typed not-applicable reason. Approve the exact allowed creation/adoption effects.
4. EP creates the missing local repository through its qualified Genesis primitives or uses the approved existing clean history. Stage only manifest-approved paths, run applicable trusted local validation and required assurance, and create local commit/checkpoint and reconciliation evidence. Repository birth may have no predecessor commit: represent ABSENT/unborn explicitly, not an invented SHA.
5. Reopen/read the resulting local tree, declarations, contract and identity independently. Forge verifies EP result bindings and sets only scoped `GENESIS_READY` when all applicable proofs hold.
6. Show the local canonical repository, unresolved product questions and current bootstrap outcome. No remote, PR, GitHub CI, publication, dummy Mission or provider feature-work is created. A first Candidate may be proposed separately; no automatic Mission start.

Genesis is offline-capable for baseline materialization and local checks whose dependencies are installed. It is not a promise that arbitrary tool installation or a cloud planning provider works offline. Missing required local tooling/evidence blocks the relevant readiness. Local review/validation outcomes are not relabelled remote CI or protected-merge evidence.

## 9. Complete Managed flow and repository birth

1. Resolve provider/account/namespace, explicit visibility and supported governance profile. Inspect authoritative remote identity and any selected local attachment. Existing remote content, even a seed README, follows adoption; do not overwrite it as empty.
2. Prepare the common artifact/contract tree plus required host-specific CI, security and ownership assets. Derive required check names from the selected shipped/project profile. Disclose both file diff and settings diff, expected base and required provider permissions.
3. For existing history, EP applies the approved changes by normal protected branch/PR/review/merge delivery; preserve current rules. Unsupported mandatory controls or denied permissions are explicit incompatibility, not silent omission.
4. For an actually unborn remote, use EP's qualified **repository-birth** operation with a single-use authority bound to that exact absent resource/ref and reviewed tree. This is not permission to push to existing protected main. Validate the seed locally before first ref creation, read back its exact tree/commit, and record that no ordinary PR into a nonexistent base was possible. Never fabricate such a PR. If provider/organization policy cannot permit this bounded birth path, stop and require a separately authorized owner-created baseline; do not disable protection.
5. Keep ordinary engineering admission fenced while seeding required workflow assets, applying desired host rules and collecting actual workflow/host readback. Required CI contexts must demonstrably exist/run on the resulting seed; no absent check becomes PASS. A host plan requiring unavailable features remains not ready.
6. Reconcile actual immutable repository ID, branch/tree, declarations, attachment and governance to the approved plan. Forge then evaluates `MANAGED_READY`; registration, successful API responses and a remote URL alone do not establish it.

Genesis is not secretly used to bypass Managed birth requirements. Repository-host authorization, baseline-tree review and normal project-Mission approval remain distinct. The birth operation cannot publish application features or mutate an existing protected default branch.

## 10. Genesis-to-Managed promotion

Promotion is an explicit plan/review/apply/readback operation, not setting a mode flag or changing origin silently. Pause affected mutating work through owning controls and pin the local baseline/history. Keep project ID, authority repository ID and Git ancestry. Select an absent destination or prove a compatible existing remote with expected refs; reject unrelated/divergent history unless a separate reviewed migration resolves it.

Before any push, review the complete set of publishable refs/history for secrets, private inputs, licensing and visibility. An ignored working file is not proof that history is safe. A required history rewrite or deletion is separately authorized migration work, never an automatic promotion repair. Existing credentials are referenced, not embedded in portable configuration.

EP performs the approved remote creation/fast-forward history transfer and governs new CI/settings under the birth/adoption rules above. It then verifies commit ancestry/tree, actual remote identity, branch governance, required check evidence and attachment. Forge activates Managed mode only after the complete bound result; do not issue new Actions under a mixture of local and remote policies. Old Genesis receipts remain Genesis with their original contracts. No squashing away founding history, retroactive PRs, reset approvals/budgets or claimed past Managed qualification.

Uncertain push, partial governance or lost acknowledgement remains the same recoverable operation with publication effects visible. Promotion cannot promise to undo data already disclosed. No automatic deletion of the remote or reopening of a fenced Genesis writer while effects are uncertain. After a safe explicit reconciliation, the same local project may remain Genesis with a recorded incomplete promotion; it is not represented as two projects.

## 11. Readiness, continuous upkeep and portability

Readiness is an evidence vector: identity/topology, approved current artifact/contract versions, baseline availability, manifest materialization, local validation, host/attachment eligibility and mode-specific governance. Unknown mandatory evidence fails the relevant capability. Optional design questions may remain documented when they do not affect the requested Action. Distinguish REGISTERED, FOUNDATION_PRESENT, GENESIS_READY, MANAGED_READY and actual execution/provider readiness; these are design projections, not substitutes for owning lifecycle state.

Repository policy must be usable by EP/CI from the portable project contract. Reattaching on a new machine verifies identity, contract provenance and authorization without cloning Forge development sources or reconstructing live grants from Git. `.forge/runtime.db`, CENTRAL files, credentials, host placements, queues and raw provider transcripts are prohibited bootstrap artifacts. Repo content is untrusted input until the accepted validation boundary; no README or AGENTS text can expand the operation's permissions.

After bootstrap, factual progress follows the existing runtime/evidence-reconciliation services and governed repository publication. Roadmap recommendations, deferred findings and draft Candidates do not replace approved direction, committed priority or workset. Bootstrap never enables reviewer-driven autonomous follow-up selection. Read-only status/export/preview cannot start work. Product upgrades offer a reviewed baseline/adoption diff, not automatic rewrite; historical Action snapshots remain immutable.

## 12. Completion standard

A design merge proves only that the target is specified. Implementation closure requires the named per-owner roadmap nodes and the shared PB qualification families. Qualify Genesis and Managed independently, then promotion, on installed artifacts without source checkouts. Deterministic fixtures, real local Git effects, remote-provider readback and optional live provider execution are separately labelled; a successful mock-host test cannot prove live GitHub provisioning.

The current change creates no project bootstrap endpoint, production template bundle, new schemas at runtime, grants, repositories, Missions, package versions or installed service. All new node statuses remain PLANNED.
