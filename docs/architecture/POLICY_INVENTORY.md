# Policy inventory and migration register

Increment: `POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES_V1`.
This is a source-pinned inventory, not a live configuration dump or a claim that
all repository constants have been audited. Target semantics are in
[Policy governance and effective profiles](POLICY_GOVERNANCE_AND_EFFECTIVE_PROFILES.md).
Runtime/effective values require the owning product API when implemented.

## Evidence baseline

Observed source on 2026-09-08:
Forge main `a1f2ef65d007f13423bc576a1f5ac026220ca218`;
EP main `51c2def28f23a5b1942ebdcbc5a240fd98fc2f23`;
Workspace main `c8240c39f295f3c976955a7cfd04a08c0147470b`;
Forge Platform main `bbdb299ca06217b69220db02c4cc3e86df67a009`.
These pins are historical observation sources once the repositories advance.
No installed runtime was inspected for this increment.

## Forge-owned inventory

| Stable inventory ID | Source at Forge baseline | Classification/current form | Target action and proof |
| --- | --- | --- | --- |
| F-PROGRESSION | `forge/governance/execution_policy.py` | Versioned ExecutionPolicy: continuous, Action/Intent/Capability/Mission pauses, custom boundaries | Retain semantics; expose supported definition/assignment/evaluation contracts and test pause/restart/approval identity |
| F-GOVERNANCE-PROFILE | `forge/governance/profiles.py`, `docs/architecture/governance-model.md` | Code-defined roles/defaults/matrices and legacy mappings, not a full management UI | Reconcile advertised profiles and aliases; explicit role decisions remain distinct, including Solo |
| F-AGENT-PROFILE | `forge/models/agent_policy.py` | Deterministic abstract model/reasoning/cost/latency selection with version/digest | Preserve provider-independent intent; EP retains actual provider/host admission; migrate mappings only through approved revision |
| F-PLANNING-PROVIDER | `forge/provider_security.py` | Runtime-owned configuration writer with expected version, audit, model/time/token parameters and secret references | Register as OPERATIONAL_CONFIGURATION constrained by policy; preserve secure-store boundary and in-flight permit rules |
| F-PROGRAMME-GRANT | `forge/programme_authorization.py`, `forge/governance_authority.py` | Separate concrete authorization/grant, exact-head qualification, Action-lineage repair authorization and squash boundary | Keep grant distinct from policy and consumption; no UI profile selection grants write/merge authority |
| F-SINGLE-FLIGHT | `forge/models/agent_policy.py`, `forge/mission_scheduler.py`, `forge/autonomous_orchestrator.py` | IMPLEMENTATION_LIMIT: single active Mission/Action assumptions | Catalogue visibly; parallel capability must be separately implemented/qualified, not enabled by a new numeric setting |
| F-BACKOFF | `forge/runtime/service.py` | Constructor-level operational bounds, default 0.25 to 5 seconds, wakeable wait | Publish supported range and effective runtime evidence without implying existing admin API |
| F-EVIDENCE-GATES | `forge/scheduler/ep_v11.py`, `forge/runtime/runner.py` | Contract/integrity validation and persisted request recovery | Retain invariants; evidence honesty/correlation is not an optional policy |
| F-VERSION-RELEASE | Pending #49, observed `a0602ba702fcf0ec3807599526257c410084b02f` | PENDING_PR repository-local manifest/helper/push workflow, not native managed-project release planning | Reconcile with FORGE::VERSION_RELEASE_MANAGEMENT_V1 and SemVer findings before adoption; no code changed here |

## Observed governance drift and disposition

The baseline bootstrap governance decision contained two conflicting descriptions:
new-SHA/per-head repair budgets versus the implemented Mission/Action-lineage
counter, and mandatory human merge text versus qualified delegated squash merge.
The accompanying edit to
[the owning decision](FORGE_V1_BOOTSTRAP_GOVERNANCE_DECISION.md) removes those
contradictions for the target contract. It does not claim that every runtime/CI
merge adapter already consumes delegation, or modify a live grant.

Exact-head proof becomes stale when the candidate changes; consumed repair
budget does not reset. EP operational rounds and Forge programme ceilings are
correlated constraints, not additive repair loops. Any unmapped legacy record
requires explicit compatibility treatment, not inferred fresh allowance.

## Peer observations, not peer authority copies

| Owner / inventory family | Pinned source or proposal | Observation | Owning migration document |
| --- | --- | --- | --- |
| EP validation | EP baseline `src/engineering_platform/validation_profile.py` | Code registry, diff paths, control launchers and branch-specific exception; producer selects a registry profile but cannot substitute controls | `pcvantol/engineering-platform:docs/engineering/POLICY_GOVERNANCE_AND_ASSURANCE_PROFILES.md` |
| EP timeouts | EP baseline `src/engineering_platform/execution_timeout_policy.py` | Named code-defined bounded provider timeouts | Same EP document |
| EP assurance | #100; detailed earlier observation `1357f21a6895b027d47f3ae8be69b2fe4dd2764b`; refreshed open head `c9cbe95e5205c8d2d4aa27703c7b9b0bb80704aa` | PENDING_PR: review/budget/receipt work, not proof of deployed configurable profiles; do not reuse old defect status without rechecking current head | Same EP document; #100 remains owning implementation lane |
| Workspace governance | Workspace baseline `docs/ARCHITECTURE.md`, `ROADMAP.md` | Role-aware governance is target product direction; application stack and policy administration are not qualified implementation | `pcvantol/workspace:docs/POLICY_AND_AUTOMATION.md` |
| Forge Platform composition | Platform baseline architecture and pending #16/#17 | Installer/composition owns compatibility, not peer runtime policies; pending event-driven versioning must reconcile with native Forge planning | `pcvantol/forge-platform:docs/architecture/POLICY_AWARE_COMPOSITION.md` |

## Required fields for the maintained catalogue

Each future entry records owning product/domain, source mode and exact source,
current form (hardcoded baseline, configurable, grant, fact or implementation
limit), supported scopes and data types, effective resolution, who may change,
non-overridable boundaries, snapshot/evaluator identity, explanation evidence,
qualification tests, migration status and legacy disposition. Hidden/hardcoded
must remain visible labels until the real writer/reader/enforcer is integrated.

Do not put bearer tokens, raw secret values or current consumption copies in this
repository catalogue. Use redacted runtime views with freshness/provenance.
