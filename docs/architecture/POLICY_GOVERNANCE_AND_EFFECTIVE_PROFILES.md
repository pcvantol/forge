# Policy governance and effective profiles

## Decision, scope and authority

Decision ID: `POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES_V1`.
This is one coordinated **documentation and roadmap increment** across Forge,
Engineering Platform (EP), Workspace and Forge Platform. On the owning `main`
branches these documents define the target architecture; on proposal branches
they remain `PENDING_PR`. Documented does not mean implemented, qualified,
installed or active. This increment changes no code, CI workflow, configuration,
version manifest, schema migration, grant, budget or runtime instance.

Forge maintains the Forge-family policy vocabulary and planning integration
specified here. This does not make Forge a global policy server or replace the
independently owned generic AI-development contracts. Each product owns its
policy definitions, interpretation, activation and enforcement. A coordinated
change is complete only when the affected owning contracts agree.

| Owner | Policy responsibility | Not acquired through this design |
| --- | --- | --- |
| Forge | Mission progression/pause, governance-profile resolution, planning/model preferences, native version/release planning, policy-change impact and proposals | EP admission, provider execution, repository mutation or a universal installer |
| EP | Execution/assurance/validation/repair/provider policies, actual admission, resource leases, qualification and receipts | Mission planning, self-approval or authority to weaken a producer's requirements |
| Workspace | Role-aware policy UX, proposal/decision presentation, effective-policy and historical explanations; its own session/UX policy | A second Forge/EP policy evaluator or credential-bearing execution authority |
| Forge Platform | Deployment presets, artifact composition and policy/runtime compatibility, controlled installation/update choreography | A cross-product version allocator, direct product SQL writes or another policy engine |
| Project/product authority repository | Repository-owned policy definitions, validation-tool configuration, product/component version source and compatibility promises | Authority from an incidental checkout or branch name |

See [governance model](governance-model.md),
[server target](FORGE_SERVER_DEPLOYMENT_TARGET.md), the
[policy inventory](POLICY_INVENTORY.md) and the
[scoped roadmap/DAG](../roadmap/POLICY_GOVERNANCE_V1.md).

## Classify before exposing a setting

| Kind | Example | Change semantics |
| --- | --- | --- |
| `INVARIANT` | No fabricated evidence; no self-approved repair; no trust from discovery | Not an ordinary UI toggle; changes require a separately governed architecture/security decision |
| `GOVERNED_POLICY` | Required review/validation profile, release decision rule, authorized budget ceiling | Versioned definition, scoped proposal, required authority, controlled activation |
| `OPERATIONAL_CONFIGURATION` | Endpoint, bounded polling interval, timeout within an approved range | Product-owned configuration writer and actor authorization; not an arbitrary workflow script |
| `AUTHORIZATION_GRANT` | Named owner delegation for repositories/scopes/time | Separate auditable grant lifecycle, expiry and revocation; selecting a profile creates no grant |
| `RUNTIME_FACT` | Two repair rounds consumed; current instance/run identity | Immutable/auditable observation or counter; not editable preferences |
| `IMPLEMENTATION_LIMIT` | Only one action can currently be in flight | Capability constraint until separately implemented and qualified; no setting can manufacture support |

Code constants are not automatically defects. Classify and expose their origin
before migrating them. Preserve safe defaults and unsupported-feature errors.
A policy definition must state whether it is configurable, constrained or fixed.

## Logical records, not a new runtime schema in this increment

These are required semantics for future versioned contracts, not implemented
classes, API routes or tables:

- `PolicyDefinition`: stable identity, owning product/domain, schema version,
  immutable revision and content digest, typed parameters, allowed ranges,
  applicability, composition rules, required change authority and supported
  runtime/evaluator versions.
- `PolicyAssignment`: definition revision bound to an installation, organization,
  project, repository, releaseable component, programme, Mission or Action.
  Supported scopes are declared per family; not every family supports all scopes.
- `PolicyChangeProposal`: exact before/after references, expected current
  revision, rationale, affected scope, required roles, impact evidence and
  migration/activation proposal.
- `PolicyDecision`: authenticated actor and role claims, decision, exact proposal
  digest, time, scope and authority provenance. Proposal generation is not approval.
- `PolicyActivation`: accepted revision, target instance/scope, effective boundary,
  predecessor activation, state and owning-service receipt.
- `EffectivePolicy`: immutable resolved values, contributing definition/assignment
  revisions and digests, evaluator version, scope and source references.
- `PolicyEvaluation`: rule identifiers, relevant input/evidence references,
  outcome, obligations and bounded explanation. No secrets or private reasoning
  transcripts are required to explain a decision.

Use existing product-owned SQL/storage and application services when implemented.
Do not add a separate policy daemon, shared cross-product database or second queue.

## Definition source and runtime snapshot are different

Every policy family declares exactly one definition writer/source mode:

1. Repository-owned definitions are changed through their approved repository
   engineering/review route. An owning service imports and activates the exact
   approved revision; it does not silently edit its own competing copy.
2. Installation/operator configuration uses the existing owning service writer,
   version checks and audit where this is its declared source mode.

Runtime assignments, activation receipts and per-execution snapshots do not
replace the definition's source of truth. Workspace caches/projections are never
a definition writer. UI edits to repository-owned policy create proposals and
bounded engineering intent, not direct SQL or unreviewed file writes.

Policy-changing work is assessed under the previously authorized policy. A
candidate cannot lower its own checks, coverage, required reviewers or authority
requirements to qualify itself. The replacement becomes active only through
its separately validated decision and activation boundary.

## Resolution and authority algebra

Do not use unrestricted last-writer-wins or assume that Action scope overrides
all earlier scopes. Each field has an explicit composition rule:

| Field category | Required resolution |
| --- | --- |
| Budget/time/capacity ceiling | Minimum applicable ceiling, further bounded by remaining authorized allowance and actual qualified capability |
| Required controls/evidence | Union of applicable obligations; a lower scope cannot remove a mandatory requirement |
| Allowed providers/targets/write scopes | Intersection of applicable allowlists and grants; empty intersection denies |
| Cost/latency/style preference | Documented override rule within invariant and permission boundaries |
| Incompatible or unknown policy/schema | Explicit conflict/unavailable result; no silent default or newest-version substitution |

This is not a universal ordering of every risk rule. Each policy family must
publish and test its own safe composition semantics. For example, a medium
severity defect that violates an explicit acceptance criterion can still block.

`auto_merge=true` is an execution preference, not merge authorization.
Policy, grant, technical qualification and actual capability must all permit
the operation. Forecast/model advice is not an authoritative release decision.

## Change lifecycle and cross-product activation

```text
DRAFT -> VALIDATED -> IMPACT_ASSESSED -> REQUIRED_DECISIONS
      -> APPROVED -> PUBLISHED_REVISION -> ACTIVATED
```

Reject, amend and defer remain explicit outcomes. Expected-revision checks
reject stale concurrent edits. Risk/role requirements come from the current
owning policy, not the proposed replacement. Routine evaluation and requalification
inside an existing valid delegation do not require repetitive human approval.

Impact preview shows affected scopes and future work, compatibility conflicts,
current grants, which in-flight executions retain their snapshot, and which
operations would be denied. It is advisory until the owning service decides.

There is no distributed SQL transaction across products. A coordinated change
references a shared change-set ID and owner-specific revisions/activation
receipts. Each owner validates independently. Partial preparation/activation
is visible; dependent new work waits until its required compatible revision
vector is accepted. Unaffected work is not globally stopped. Compensating
activation is explicit, never a silent claim of cross-product atomicity.

Rollback is a new audited activation of known content where still compatible,
not deletion of history, grant resurrection or resetting consumption.

## Action/admission binding and ongoing execution

Forge materializes its effective planning/release policy and requested
execution constraints before dispatch. EP resolves and pins its own effective
admission/assurance profile, validates the incoming requirements and records the
accepted policy references. Unsupported or conflicting requirements fail closed.
EP returns its applied profile/evaluation evidence; Forge verifies exact request,
run and profile correspondence. An opaque digest alone is not a permission token.

A run retains its immutable effective snapshot across restart, repair, new SHA
and historical display. A new policy normally applies to newly admitted work.
An explicit controlled migration is required to change policy for in-flight
work; it preserves lineage, consumed budget and prior evidence, and requalifies
any invalidated candidate.

Pinned snapshots do not defeat current revocation, expiry, emergency stops or
changed credential trust. Recheck applicable dynamic authority at each protected
side-effect boundary, including provider mutation, merge, publication and install.
An unavailable authority source follows the documented fail-closed/lease rule;
never use an indefinitely stale positive cache to grant a write. Preserve
already proven delivery and record a subsequent stop/cleanup issue separately.

EP owns the operation-level repair counter. Forge can impose stricter Mission/
programme ceilings and correlate consumption, but never adds another three
provider repairs. The current bootstrap maximum remains **three total repair
rounds per run/continuation lineage**; lower limits are allowed, a higher future
limit requires explicit new policy/authority and cannot reset an exhausted run.
Exact-head requalification is required after mutation; a new SHA is not a new
repair allowance or automatically a new human decision.

## Native Forge version and release management

`FORGE::VERSION_RELEASE_MANAGEMENT_V1` is a native planning/application-service
capability for managed products, not merely a script that versions Forge itself.
It consumes product-owned compatibility and version-source contracts, evaluates
impact/policy, reserves an idempotent release operation per releaseable component,
plans bounded Actions and reconciles resulting evidence. EP performs authorized
repository/build/publish operations through the existing execution route; Forge
Platform owns composition and installation of the qualified artifacts.

Repository, product and releaseable component are not interchangeable. EP Server
and Agent, or Workspace Server and Client, may share or separate a version series
only according to their owning contract. Matching baseline numbers do not imply
lockstep compatibility; this increment changes no baseline or product version.

A release operation binds product/component, policy revision, operation identity,
baseline version/source, intended version, grant references, qualified candidate,
artifact identities and actual publication receipt. `PROPOSED`, `RESERVED`,
`VERSION_COMMITTED`, `QUALIFIED`, `BUILT` and `PUBLISHED` are distinct facts.
Reconcile ambiguous publication against the same operation and registry evidence;
do not allocate another version merely because an acknowledgement was lost.

A branch-event numbering preference can be a selectable policy, but does not
prove semantic compatibility or publication authority. Stable release decisions
must address compatible fixes/additions, breaking changes and the explicitly
authorized major boundary. Branch names and commit subjects alone are not grants
or reliable operation identities. Independent candidate branches may not publish
different content under one supposedly immutable product release identity.

Required engineering acceptance for the future implementation:

- One named version source per product, with field-aware derived projections;
  no whole-file replacement of coincidentally equal dependency/protocol versions.
- Read/validate all intended changes before writing; per-file atomic replacement
  plus an explicit complete Git publication/recovery boundary. Do not claim that
  several file replacements are a distributed or multi-file transaction.
- Normal build reads the already committed version and does not allocate/bump it.
  Repeated build cannot silently change source or release identity.
- Version preparation precedes final candidate qualification. A later version
  commit creates a new candidate requiring actual checks/review/authorization;
  no assumption that bot events automatically qualify that SHA.
- Expected-head and durable operation/event identity handle retries, parallel
  writers, rebase and ambiguous pushes. No subject-only bump marker.
- Validate all declared package/UI/runtime projections, then separately verify
  the exact installed artifact without source-path shadowing.
- Publication binds approved source, explicit version, artifact bytes/digest,
  compatibility and qualification evidence; a release branch name is insufficient.

These requirements reconcile the findings on pending Forge #49, Workspace #14,
Forge Platform #17 and the versioning portion of EP #100. Those PRs are not
modified or approved here. Competing autonomous push-bump writers are not the
target under Forge-managed releases. Standalone EP use must remain possible with
its own explicit authorized policy and must not require Forge availability.

## Workspace interaction boundary

Workspace's target surface is **Policy & Automation / Beleid & automatisering**.
It provides catalogue, effective-policy explanation, diff/impact, role-routed
proposal/decision and historical views through authenticated owner APIs.
Clients do not receive ambient service-admin or provider credentials. An owner
validates the real actor/scope even when Workspace Server mediates the request.
A policy editor only exposes supported fields/extension points; it is not a
free-form workflow engine, arbitrary command launcher or safety-gate bypass.

Policy management must explain both "why allowed?" and "why waiting?", distinguishing
policy conflict, grant/expiry, capability absence, EP lease/capacity and budget
consumption. See owning design `pcvantol/workspace:docs/POLICY_AND_AUTOMATION.md`.

## Compatibility and bounded rollout

Reuse existing ExecutionPolicy, governance profiles, AgentPolicySelection,
provider configuration, programme grants and EP validation profiles. Publish an
inventory before migration. A data type in code is not proof of a wired management
API; a known legacy alias needs explicit mapping, and unresolved legacy data is
not silently upgraded to a new authority. Test profile coverage and aliases.

Keep native release integration and effective assurance contracts explicit
before a universal-installer production composition is approved. Full policy UI,
visual workflow editing and migration of every legacy knob are not new prerequisites
for the first Forge -> EP -> Forge Mission canary. Do not reopen completed producer
work or claim the canary from this documentation.

The [roadmap](../roadmap/POLICY_GOVERNANCE_V1.md) defines the future proof gates.
The existing executable bootstrap DAG, live programme digest and grants are not
changed by this documentary sub-DAG. Any later material programme-DAG adoption
must explicitly reconcile authorization without minting authority or resetting
budget as a documentation side effect.
