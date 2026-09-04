# Forge + Workspace V1 Product Model

**Status:** proposed V1 architecture; not implementation authority.  
**Review basis:** Forge PR #7 baseline `ee1eed8`, Forge Platform PR #14 head `31c6761`, Workspace `4440332`, and the installed Engineering Platform working tree observed on 2026-09-04. This supersedes the pre-PR-#7 review. Cross-repository evidence is descriptive only: Forge remains the authority for Forge product semantics; Workspace and EP retain authority for their own products.

## Decision standard and conclusion

This record separates evidence from target decisions. `DOCUMENTED_DECISION` is an existing canonical decision; `IMPLEMENTED_BEHAVIOR` and `TESTED_BEHAVIOR` describe the observed local repositories; `INFERRED_INTENT` is non-authoritative; `UNRESOLVED_DESIGN_GAP` blocks a V1 claim where it affects a required journey.

**Conclusion: `FORGE_WORKSPACE_V1_ARCHITECTURE_IMPLEMENTATION_READY` is not yet supported.** PR #7 now supplies canonical target semantics for the three-layer engineering contract, effective DoR/DoD/Human Gates, managed GitHub desired-state/read-back qualification, and the dual learning loops. It does not supply implementation or qualification evidence. Workspace still has a documented stateful control-plane direction but no implementation. The remaining gaps in `FWV1-G001`, `G003`, `G005`, `G007–G011`, and `G013` must be resolved and qualified before that state can be claimed.

## V1 boundary and concept inventory

| Concept | V1 classification | Evidence and disposition |
| --- | --- | --- |
| Installation, operator, Workspace, Project, Repository, Repository Host | V1_REQUIRED | `DOCUMENTED_DECISION`: Workspace is a peer control plane; EP separates logical attachment from host locality. Exact installer/identity contract is unresolved. |
| Project Contract, Product Baseline, Effective Action Contract | V1_REQUIRED | `DOCUMENTED_DECISION`: PR #7 defines a locally packaged baseline, project-owned contract, immutable per-Action snapshot and no source-repository runtime authority. `IMPLEMENTED_BEHAVIOR`/qualification remain absent. |
| Genesis, managed/adopted project, repository governance | V1_REQUIRED | `DOCUMENTED_DECISION`: PR #7 defines desired state, read-back qualification and non-destructive adoption outcomes; `IMPLEMENTED_BEHAVIOR`: none in Workspace. Provisioning/registration protocol remains unresolved. |
| Intent, Mission, Plan, Roadmap, Backlog, Action, dependency, priority | V1_REQUIRED | `DOCUMENTED_DECISION`: Mission → Intent → Action is Forge-owned. `IMPLEMENTED_BEHAVIOR`/`TESTED_BEHAVIOR`: local models, runtime database, intake and planner components exist. Plan/backlog operational semantics remain incomplete. |
| DoR, DoD, Human Gate, validation, evidence | V1_REQUIRED | `DOCUMENTED_DECISION`: PR #7 defines deterministic profile composition, stable criterion/proof identity, gate evidence and immutable historical projection. EP L0 implementation is a prerequisite, not current Forge+Workspace V1 evidence. |
| Execution Host, EP Server, Project Agent, provider, scheduling, dispatch, run/retry/delivery | V1_REQUIRED through the producer boundary | `DOCUMENTED_DECISION`: Forge decides what/why and EP owns how/where, admission, scheduling, retries, execution evidence and cleanup. `IMPLEMENTED_BEHAVIOR`/`TESTED_BEHAVIOR`: EP documents/persists those concerns. Forge must not duplicate them. |
| PR, merge, release | V1_REQUIRED | EP supports a bounded operator merge handoff. Cross-product release policy and Forge completion semantics are unresolved. |
| Quality Learning | V1_FOUNDATION_ONLY | `DOCUMENTED_DECISION`: PR #7 defines `ActionQualityOutcome`, observer, review, hardening and Workspace governance; L2–L4 remain planned. |
| Knowledge Learning, certified knowledge | V1_FOUNDATION_ONLY | `DOCUMENTED_DECISION`: PR #7 defines the evidence/export boundary and KB-owned certification; L5–L10 remain planned and non-blocking for execution. |
| history, notifications/attention, settings, audit | V1_REQUIRED | Durable Forge and EP evidence projections are documented. Unified projection, attention ownership and retention policy are unresolved. |
| secrets/credentials, authorization | V1_REQUIRED | EP/Workspace prohibit credentials in portable declarations. The supported V1 identity, secret store and authorization model are unresolved. |
| upgrade/migration, archive/delete | V1_REQUIRED | Runtime DB migration is fail-closed; project/baseline migration and retention/deletion policy are unresolved. |
| marketplace, cloud runtime, enterprise collaboration, localization beyond UI strings | POST_V1 | Existing records explicitly defer these. |

## Product boundaries

| System | Owns | Must not own | V1 degradation |
| --- | --- | --- | --- |
| Forge | Mission interpretation after approval; planning; Action and Producer Contract composition; dependency reasoning; repository-truth and decision-evidence interpretation; planning/learning proposals | EP scheduler, provider invocation, host qualification, execution telemetry, credentials, repository filesystem operations | Planning/history can be read if EP is offline; no dispatch. |
| Workspace Server + Client | Product-specific project/team state, user interaction, presentation, permitted write intents, review surfaces and operator attention | Forge planning authority, EP admission/execution, provider credentials, direct Agent filesystem actions | Read-only cached/projection views where data freshness is labelled; no lifecycle mutation. |
| EP Server/CENTRAL | Submission persistence, admission, scheduling, run lifecycle, host/Agent placement, retry, execution evidence and operational audit | Mission/planning/governance/portfolio semantics | EP is authoritative for an in-flight execution even if Forge or Workspace is unavailable. |
| Project Agent | Checkout/worktree/toolchain/provider-host readiness and local host work | project topology authority, user approval, direct Workspace control | Agent unavailable produces EP-visible retry/block state. |
| Repository host | Git resource and provider-side state | product or Action authority | Provider results are qualified read-back evidence, not intent. |

Workspace is therefore a **stateful peer product**: Server is authoritative for Workspace-owned collaboration/presentation state; Client is a projection and intent sender. It is neither a stateless Forge UI nor a replacement operational store. Forge can run planning without Workspace; Workspace can show independently stored/projected information without Forge, but cannot fabricate planning or execution state.

## Contract chain and non-negotiable snapshots

```text
Product Baseline (versioned, installed artifact)
  + Project Contract (versioned project policy/topology)
  + immutable Action classification and repository scope
  = Effective Action Contract (hash + component identities)
  → Forge Producer Submission Envelope
  → EP immutable submission/run/qualification records
  → repository/provider evidence
  → Forge decision-evidence and Workspace projections
```

PR #7 is the `DOCUMENTED_DECISION` for the first three layers: the baseline is local after installation; project changes are governed and project-owned; Action snapshots are immutable after admission. The target chain is not a claim of current behavior. A dispatch is idempotent only by a stable Forge Action ID plus submission idempotency key. EP may retry or resume a run only under its persisted lineage contract. Forge never reconstructs an in-flight run from a report; Workspace never infers a completed mutation from a browser action. Unknown, stale, conflicting, or mismatched correlation evidence fails closed and creates operator attention.

## Decomposed product language

| Phrase | Hidden responsibilities that V1 must make explicit |
| --- | --- |
| Create project / Genesis | identity; topology; approved repository request; baseline selection; Project Contract creation; governance desired state; EP registration/Agent attachment; read-back qualification; initial roadmap; visibility. |
| Adopt existing repository | identity match; discovery evidence; topology registration; governance drift report; explicit adoption decision; contract bootstrap; no destructive reconciliation without approval. |
| Managed project | effective policy version; governance desired state; qualified actual state; drift/reconcile loop; auditable exceptions. |
| Plan work | approved Mission check; repository truth; dependency graph; Action classification/scope; immutable contract snapshot; DoR evaluation. |
| Dispatch Action | selected host eligibility is EP-owned; producer envelope persistence; idempotency; admission; correlation; user-visible status. |
| Review / Done / release | automated evidence; Human Gate identity and decision; repair loop; DoD; delivery/merge/release evidence; history. |
| Learn | evidence envelope; observer; proposal; deduplication; governed acceptance; no automatic project-policy or certified-knowledge mutation. |
| Connect GitHub / configure provider | least-privilege identity; secret-store reference only; scope/expiry checks; redacted audit; revocation and degraded status. |
| Open Workspace | authenticated context selection; freshness-labelled projections; permitted intents; no authority derived from selected project or UI state. |

## V1 journeys and transition contract

All V1 transitions use this invariant: input intent has an actor, idempotency key and correlation ID; the authoritative owner persists the resulting state atomically or rejects it; every mutation emits auditable evidence; recovery resumes only from durable state.

| Journey | Required transitions | Authority / durable result | V1 qualification and unresolved item |
| --- | --- | --- | --- |
| Clean install → first project | setup → authenticate → create project → create repository → baseline/contract → Genesis → first Action → dispatch → delivery → history | Workspace owns setup/project-facing state; EP owns provisioning/execution states; Forge owns planning artifacts | `DOCUMENTED_DECISION`: PR #7 defines offline baseline/new-project bootstrap and `REPOSITORY_GOVERNANCE = PASS` before Ready. `FWV1-G001/G003/G010`; prove end-to-end qualification. |
| Existing repository → managed | request attach → inspect → governance drift → adoption gate → contract bootstrap → plan | EP owns attachment evidence; Forge owns interpretation/planning; Workspace owns request/review presentation | `DOCUMENTED_DECISION`: PR #7 requires `COMPLIANT`, `DRIFT_REVIEW_REQUIRED`, `INCOMPATIBLE` or governed reconciliation, never silent rewrite. `FWV1-G003`; no implementation evidence. |
| Normal iteration | request → Mission/plan → dependency-aware Action → DoR → submit → run → DoD → delivery → learning proposal | Forge/EP boundary as above | `FWV1-G002`, `G005`, `G006`. |
| Failure/recovery | detect → durable terminal/retryable state → bounded retry/resume or attention → evidence | EP owns run recovery; Forge owns planning disposition; Workspace owns attention presentation | `FWV1-G007`; no transient UI-only state. |
| Human-gated UI change | classify → generated review artifact → human approve/reject → repair or completion | Forge composes gate; Workspace records/presents intent; EP persists execution; approval authority remains human | `DOCUMENTED_DECISION`: gate evidence includes reason, state, artifacts, actor, timestamp and bounded outcome. L0 implementation evidence remains required. |
| Multi-repository project | topology → repository-scoped Actions → dependencies → EP leases/admission → coordinated delivery | Forge plans graph; EP owns concurrency/lease/delivery | Initial V1 supports one mutating lane per repository; cross-repo atomic delivery is `POST_V1` until EP contract exists. |
| Project lifecycle | setting/baseline evolution → drift → qualified migration → archive/restore/delete | owning product persists its state; EP owns runs and retention evidence | `FWV1-G008`, `G009`; delete is never implicit while an Action/run exists. |

## UX interaction contracts

Workspace must provide these surfaces; exact pixels and stack are out of scope. Each has a read model, permitted write intents, empty/loading/degraded/error state, responsive layout, and accessible human-review affordance.

| View | Primary actions / read model | Degraded and human review |
| --- | --- | --- |
| Home/portfolio | select/create project; project summaries and attention counts | freshness label; route approval decisions to named gate. |
| Project creation/onboarding | choose existing/new/Genesis/qualification-only; submitted request and qualification evidence | never expose secrets or claim provider success before EP read-back. |
| Project overview/topology | repositories, baseline/contract versions, governance drift, health | show conflicting/offline authority explicitly. |
| Roadmap/backlog/planning | propose/inspect Mission, Plan, Action and dependencies | immutable approved/snapshotted records distinguish from drafts. |
| Action workflow and DoR/DoD | submit permitted Action; inspect effective contract/evidence | blocked/unresolved proofs create attention; approval/rejection is attributable. |
| Active executions/history/evidence | inspect EP projection, run lineage, delivery and audit | stale data is labelled; no run control is inferred from view state. |
| Governance, provider/setup and repository health | request configuration/reconciliation; inspect redacted health | credential failures show remediation owner, never secret values. |
| Quality/knowledge learning | inspect observations/proposals and governed disposition | unavailable observers preserve action outcome; no auto-policy/certification. |
| Settings/notifications/failure recovery | change allowed preferences; acknowledge attention | acknowledgements do not resolve owning-system failures. |

## Failure and trust posture

| Failure or trust event | V1 classification | Required behavior |
| --- | --- | --- |
| Forge/Workspace crash | AUTO_RECOVER | Restart from their durable stores; transient draft may be lost only if clearly non-submitted. |
| EP/Agent/GitHub unavailable, expired provider auth, CI never completes | RETRY or OPERATOR_ACTION | EP records bounded retry/backoff or block; Workspace surfaces owner and evidence. |
| dirty/diverged repository, duplicate Action/submission, corrupted contract, incompatible schema | FAIL_CLOSED | Do not mutate; retain correlation evidence and require new/repair intent. |
| Human Gate unanswered | OPERATOR_ACTION | No automatic completion; visible attention with timeout policy. |
| repository renamed/deleted, baseline changes, migration interruption, project deleted with Action | FAIL_CLOSED | Reconcile durable identities; prevent destructive finality until retention/terminal-run rules pass. |
| KB/observer unavailable or conflicting learning proposal | DEGRADED | Action outcome remains independent; queue/retry observation with provenance. |
| conflicting governance decisions | FAIL_CLOSED | serialize via owning authority and record conflict; no last-UI-wins rule. |

V1 security is **single-installation, named-operator, least-privilege** only: distinct recorded Business and Architecture approvals may be made by the same Solo identity; provider and Agent credentials stay in their owning secure stores; portable project declarations carry no credentials; all execution and approval actions retain actor/correlation/audit attribution. Multi-user tenancy, enterprise RBAC, shared secret administration, and remote browser trust are POST_V1 until an identity architecture is approved.

## Source self-containment

The release target is `SOURCE_REPOSITORY_RUNTIME_DEPENDENCIES = 0`: installed Forge, Workspace and EP artifacts must include their versioned schemas, baselines, migrations, contract renderers and qualification fixtures. Runtime may reference a configured repository under management, but never needs the Forge/Workspace/EP source checkout or `ai-development-contracts` checkout. Current local source imports and documentation-only projections are `STALE_OR_INSUFFICIENT_EVIDENCE` for this target and are tracked by `FWV1-G010`.

## Forge Platform PR #14 reconciliation

`DOCUMENTED_DECISION`: Forge Platform PR #14 (`31c6761`) explicitly supersedes
its former learning-loop architecture in favour of Forge's canonical dual,
quality and knowledge learning documents. This is **CONSISTENT** with the V1
model: Forge owns planning and learning orchestration; Workspace governs human
review; EP executes and produces evidence; the independent KB owns knowledge
lifecycle and certification.

PR #14 retains two material deployment constraints. The KB is currently a
Git/CLI-backed repository capability, not an installable Forge Platform server
role, and no product may invent a KB daemon/API merely for symmetry. Any future
Forge Platform composition requires a separately qualified published artifact,
persistence, backup, update, concurrency and operating-model contract. These
constraints reinforce, rather than close, `FWV1-G012`: learning remains
additive, must not block EP admission/execution, and cannot be treated as an
installed V1 runtime dependency.

## Adversarial completeness pass

An agent with only the repositories cannot correctly implement V1 today. The
following challenges succeeded and are therefore gaps, not assumptions:

| Challenge | Result / disposition |
| --- | --- |
| “Which durable record turns an approved baseline and project policy into the exact contract of this Action?” | PR #7 supplies the target immutable snapshot; its storage/qualification must be delivered by L0/L1, not inferred as implemented. |
| “May a Workspace browser create a repository, attach an Agent, or tell an Agent to mutate a checkout?” | No; Workspace’s own onboarding design prohibits it, but the accepted-request protocol is absent: `FWV1-G003`. |
| “How is a GitHub ruleset policy made generic, read back, and reconciled if the host cannot support it?” | PR #7 defines the target desired-state/read-back and explicit unsupported result; L1-R must implement and qualify it. |
| “Which store wins after a crash during submit, retry, rejection, or project deletion?” | EP covers portions of run persistence; cross-product correlation/retention does not: `FWV1-G007–G009`. |
| “What proves a named person approved a required review, and what starts repair after rejection?” | PR #7 defines attributable gate evidence; L0/L4 must implement the proof and governed repair path. |
| “Can a released environment function after its source checkouts and private documents disappear?” | Not qualified: `FWV1-G010`. |
| “Which supported user, secret store and authorization model makes this safe?” | No V1 product contract: `FWV1-G011`. |

No challenge was resolved by interpreting a vague term or by treating a test in
one peer repository as cross-product product authority.
