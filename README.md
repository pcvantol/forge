# Forge

## Managed repository status

Forge is the first-class repository [`pcvantol/forge`](https://github.com/pcvantol/forge),
promoted with its complete Genesis ancestry preserved. Its current repository
governance baseline is documented in [Managed Repository Baseline](docs/governance/managed-repository-baseline.md)
and its source-history record in [Forge Genesis Provenance](FORGE_GENESIS_PROVENANCE.md).

Start a new development session with [BOOTSTRAP.md](BOOTSTRAP.md), then
[ENGINEERING_METHOD.md](ENGINEERING_METHOD.md), [PROMPT_INITIALIZATION.md](PROMPT_INITIALIZATION.md),
and [AGENTS.md](AGENTS.md). Use [HANDOFF.md](HANDOFF.md) for the local
handoff navigation. Run local validation with:

```text
bash scripts/validate.sh
```

Forge remains independent of Engineering Platform, which is a replaceable
Execution Host; Forge and Workspace are first-class peers. The canonical
architecture entrypoint is the [Founding Architecture Handbook](docs/architecture/FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md).
Roadmap entrypoints are [Bootstrap Roadmap](knowledge/bootstrap/10_ROADMAP.md)
and [Runtime Evolution Roadmap](docs/architecture/runtime-evolution-roadmap.md).

Phase E — Increment 5.14 formally completes Generation 1 and makes Generation
2 ready. The [Generation 1 Completion Record](GENERATION_1_COMPLETION.md)
establishes that `MISSION-0001` through `MISSION-0005` are historical Portfolio
Seed Missions, never reconstructed as Runtime Instance state. The Runtime
Instance is operational and intentionally empty, its Dispatcher is `IDLE`, and
its Approved Mission Queue is empty until the first Business- and
Architecture-approved Generation 2 Mission. The next architectural increment
is [Portfolio Intelligence Foundation](docs/architecture/generation-1-transition.md).

Forge is a local-first, AI-native engineering platform foundation. It gives an
engineering workspace a small, explicit vocabulary before it gains automation:
the workspace it operates in, the repositories it knows, and the human
governance that constrains its work.

Generation 2 also provides a canonical, read-only [Execution Context
projection](docs/architecture/runtime-database.md#execution-context-projection).
It is an immutable Runtime Instance snapshot of the active Mission's
operator-facing state, derived after Runtime reconciliation rather than from
repository source. It is safe for Engineering Platform, Apple, Windows, CLI,
API and future-client projections because it excludes prompts, hidden
reasoning and Execution Host internals.

Phase E — Increment 5.10 qualifies Generation 1 only from a resolved,
persistent Runtime Instance. The read-only projection derives its portfolio,
global lifecycle order, completion state, and receipt identities from runtime
records; it neither imports a dispatcher portfolio nor reconstructs state from
repository files. Engineering Platform remains the sole owner of Execution
Evidence and Forge retains only immutable receipt references. A successful
qualification recommends the Generation 1 Completion Record.

Phase E — Increment 5.9 adds [Runtime Instance Persistence](docs/architecture/runtime-bootstrap.md).
Forge now resolves one persistent Runtime Instance through a location-independent Git Repository Identity and a durable fail-closed registry. Runtime recovery preserves Runtime Identity across independent executions, restarts, cleanup, relocations, branches, and worktrees; the Runtime Database remains storage only.

Phase F — Increment 6.0 adds the [Integration Coordination Framework](docs/architecture/integration-coordination-framework.md).
Forge now owns deterministic integration readiness, conflict events, immutable
integration evidence, and Mission pause/resume state independently from the
Execution Host. The next architectural increment is Parallel Mission Execution.

Phase E — Increment 5.7 adds [Generation 1 Bootstrap Qualification](docs/architecture/bootstrap-mission-sequence-qualification.md).
Forge projects an already persisted Runtime Database through a read-only qualification boundary. It never reconstructs a portfolio from repository files, dispatches work, or copies Engineering Platform evidence while qualifying Generation 1.

Phase E — Increment 5.6 adds [Runtime Bootstrap, Location Resolution and Evidence Recovery](docs/architecture/runtime-bootstrap.md).
Forge now deterministically resolves one canonical Runtime Database with an immutable Runtime Identity, fails closed on ambiguity or integrity errors, and recovers operational state only from persisted runtime records.

Phase E — Increment 5.5 adds the [Capability Delegation Framework](docs/architecture/capability-delegation-framework.md).
Forge now assesses a required capability before an Engineering Action executes,
pauses durably when internal execution is unavailable, delegates only the
bounded Action, verifies the external result, and continues its Mission without
transferring ownership or bypassing governance.

## Bootstrap Phase A — complete

Bootstrap Phase A is complete. Forge currently provides a deterministic,
local-only foundation through 0.8, including the repaired Foundation Document
Loader, Engineering Proposal Generator, and Engineering Prompt Artifact
foundation. The closure record is the
[Bootstrap Milestone A Report](docs/reports/bootstrap-milestone-a.md).

## Current scope

Forge 0.2 defines a versioned Foundation Model. It includes:

- separate Workspace, Repository, Repository Catalog, Knowledge Source, and
  Capability contracts;
- a legacy bootstrap Engineering Mode and Governance Profile value catalog;
- bootstrap activation of `prototype` and the persisted `solo` legacy value;
- deterministic, human-readable local JSON persistence; and
- versioned JSON Schemas, an example, architecture records, and tests.

Forge 0.3 additionally loads one versioned Foundation Document through a
strictly local pipeline: version detection, packaged-schema resolution,
validation, immutable model construction, cross-reference checks, and a
deterministic validation report. It does not fetch schemas or follow document
supplied `$schema` values.

Forge 0.4 adds a local Knowledge Source Registry and a deterministic,
metadata-only consumption interface. Registered sources declare their version,
reference, trust classification, lifecycle, and mandatory read-only access
mode. Consumption returns source evidence references only; it performs no
source extraction, semantic retrieval, LLM call, or mutation.

Forge 0.5 adds Engineering Planning Foundation: versioned, local contracts
for Goals, Increment Proposals, Plans, dependencies, risk, rationale, and
typed evidence references. The planning loader and registry validate and
persist declarations only. Plans do not retrieve knowledge, approve work,
operate repositories, execute tools, or create commits.

Forge 0.6 adds deterministic Engineering Proposal generation. It transforms
validated planning context into a separate, traceable proposal artifact with
structured scope, rationale, dependencies, risk, evidence, and lifecycle.
Generation always produces `DRAFT`; explicit lifecycle changes remain local
state transitions and never execute work or grant approval.

Forge 0.7 adds a deterministic Engineering Prompt Artifact layer. It converts
an approved proposal into a versioned, provider-independent instruction draft
with context, objective, scope, typed evidence, constraints, and validation
requirements. The artifact lifecycle is `DRAFT` then `READY`; ready remains an
instruction only and never invokes a provider or operates a repository. See
[Engineering Prompt Artifact Foundation 0.7](docs/architecture/engineering-prompt-artifacts.md)
and [the example](examples/engineering-prompt-artifact.example.json).

Forge 0.8 introduces Engineering Intent as the canonical, model-independent
architecture concept for bounded engineering work. An intent defines context,
goal, architecture decisions, scope, constraints, deliverables, validation,
and expected evidence. Runtime Prompts are temporary, provider-specific
representations derived from an intent; they are not the canonical source of
truth. This increment is documentation-only: it adds no intent storage,
prompt generator, runtime provider, or execution pipeline. See
[Engineering Intent Architecture 0.8](docs/architecture/engineering-intent.md).

Phase B — Increment 1.0 adds the evidence-only [Phase Completion
Framework](docs/architecture/phase-completion-framework.md). It assesses a
declared phase from reproducible references and does not orchestrate work,
operate repositories, or grant execution authority.

Phase B — Increment 1.1 adds the local [Constitutional Validation
Framework](docs/architecture/constitutional-validation-framework.md). It
assesses declared architecture against applicable constitutional articles with
deterministic findings, but does not retrieve repository knowledge, enforce a
result, or perform runtime work.

Phase B — Increment 1.2 adds the immutable, local [Engineering Intent
Lifecycle](docs/architecture/engineering-intent-lifecycle.md). It defines
versioned statuses, typed relationships, reproducible evidence, mandatory
traceability, and pure lifecycle validation. It neither migrates historical
work nor implements a provider, execution, queue, or Studio.

Phase B — Increment 1.3a adds the immutable,
evidence-only [Historical Engineering Intent](docs/architecture/historical-engineering-intent.md)
model. It preserves engineering that predates Intent governance without
inventing historical proposals or approvals. It performs no bootstrap migration
and does not modify the normal Engineering Intent lifecycle.

Phase B — Increment 1.4 adds [Engineering Intent Authoring](docs/architecture/engineering-intent-authoring.md):
a deterministic, repository-grounded context for authoring future Intents from
the Constitution, Architecture Handbook, Roadmap, Engineering History,
Repository Evidence, Capability Catalogue, and Knowledge Model. It authorizes
neither an Intent nor runtime activity, and it implements no prompt generation
or execution.

Phase B — Increment 1.5 adds [Architecture Reasoning](docs/architecture/architecture-reasoning.md):
an immutable, human-governed pre-authoring model from repository knowledge to
assessment, findings, opportunities, capability and roadmap impact, and a
traceable handoff into the existing Engineering Proposal process. It performs
no AI reasoning, autonomous planning, proposal or Intent creation, Runtime,
or execution.

Phase B — Increment 1.6 adds the provider-independent [AI Architect Provider
Contract](docs/architecture/ai-architect-provider.md): Forge supplies complete,
versioned repository context and providers return evidence-linked reasoning
candidates only. It implements no concrete provider, Runtime Provider, prompt
generation, lifecycle execution, or engineering execution.

Phase B — Increment 1.7 adds the
[AI Provider Registry](docs/architecture/ai-provider-registry.md): immutable
provider declarations, repository-owned qualification, and deterministic
selection. It selects a declaration only; it does not implement, load, or
invoke a provider.

Phase B — Increment 1.8 adds the [AI Architect Session](docs/architecture/ai-architect-session.md):
an immutable, bounded reasoning record that composes complete request context,
a selected provider declaration, repository snapshot, and advisory output.
Its lifecycle is human-governed and non-executing; it neither invokes a
provider nor approves architectural decisions or Engineering Intents.

Phase B — Increment 1.9 adds [Runtime Prompt Generation](docs/architecture/runtime-prompt-generation.md):
an immutable, deterministic derivation of a transient, provider-specific
Runtime Prompt from an approved Engineering Intent and complete versioned
context. It defines the provider-neutral section structure and provenance only;
it implements no provider-specific template or runtime execution.

Phase B — Increment 1.10 adds the [Engineering Mission Model](docs/architecture/engineering-mission.md).
Phase B — Architecture Transition now reconciles that model around
mission-driven engineering: the Mission is the Architect-approved engineering
contract, while Engineering Intents are dynamic planning artifacts created and
reconciled during Mission execution.

Phase B — Architecture Correction adds [Engineering Action](docs/architecture/engineering-action.md):
the smallest intentional executable engineering unit. Missions are strategic
and contain Intents; Intents are tactical and contain Actions; Actions produce
provider-specific Runtime Prompts. This reconciliation adds no scheduler,
Runtime, provider, prompt generator, or execution implementation.

Phase B — Increment 2.0 adds the deterministic [Bootstrap Mission
Scheduler](docs/architecture/bootstrap-mission-scheduler.md). The subsequent
2.1 contract reconciliation makes it release one evidence-gated Engineering
Action at a time only through the canonical Execution Host Contract. Engineering
Platform 1.5 remains a replaceable bootstrap reference host behind its adapter;
Forge implements no Runtime, host, queue, provider, background service, or
autonomous planning.

Phase B — Increment 2.1 adds the canonical
[Execution Host Contract](docs/architecture/execution-host-contract.md).
Execution Hosts own operational execution, transport, observability,
qualification, and evidence return; Forge owns engineering reasoning and
evidence interpretation. Engineering Platform 1.5 is the reference
implementation during bootstrap, while Forge remains decoupled from it.

Phase B — Increment 2.2 adds the durable, versioned
[Mission State Store](docs/architecture/mission-state-store.md). It owns
restart-safe Mission execution state, atomic transitions, progress,
correlation, evidence references, resume data, and immutable history. It adds
no Mission Runner, daemon, Execution Host, queue, AI planning, Studio, or
repository operation.

Phase C — Increment 3.0 adds the deterministic
[Bootstrap Mission Runner](docs/architecture/bootstrap-mission-runner.md). It
coordinates one persisted Mission through the Scheduler, injected Runtime
Prompt derivation, and canonical Execution Host Contract. It adds no AI
planning, Execution Host implementation, parallelism, background service, or
repository operation.

Phase C — Increment 3.3 adds the deterministic, immutable
[Codex CLI Runtime Prompt Renderer](docs/architecture/codex-cli-runtime-prompt-renderer.md).
It renders one Mission-pinned active Engineering Action into a Codex CLI
execution artifact with explicit compatibility and correlation metadata. It
does not plan, invoke Codex, communicate with a host, or execute engineering.

Phase C — Increment 3.4 adds the deterministic, configuration-driven
[Bootstrap Execution Host Adapter](docs/architecture/bootstrap-execution-host-adapter.md).
It is the only Engineering Platform 1.5-aware component: it admits and
translates a rendered Runtime Prompt into an Inbox transaction, then returns
canonical evidence. It neither plans nor executes engineering.

Phase C — Increment 3.7 adds the deterministic, evidence-only
[Mission Recommendation Engine](docs/architecture/mission-recommendation-engine.md).
It turns Architecture Reviews into immutable advisory Portfolio artefacts with
confidence, dependencies and explicit missing-discipline detection. It does
not approve, prioritise, create or execute a Mission; Business approval remains
mandatory.

Phase C — Increment 3.5 adds the deterministic [End-to-End Bootstrap Mission
Canary](docs/architecture/bootstrap-mission-canary.md). It qualifies one
approved Mission through Mission Intake, State, Intent, Action, prompt,
adapter, Engineering Platform 1.5 admission, evidence, and completion.

Phase C — Increment 3.6 adds the deterministic
[Architecture Review Engine](docs/architecture/architecture-review-engine.md).
It evaluates completed work using allow-listed Repository Truth and Execution
Evidence only, producing immutable Architecture Reviews. The separate Mission
Recommendation Engine produces advisory Portfolio Mission Recommendations. It
neither creates nor approves executable Missions.

Forge also has a deterministic, provider-independent [Agent Role and Model
Selection Policy](docs/architecture/agent-role-model-selection-policy.md). It
selects Forge-owned role, model and reasoning profiles plus execution
constraints before Runtime Prompt rendering. Execution Hosts receive only the
rendered constraints and policy provenance; they never choose models.

Phase E — Increment 5.1 adds the immutable, local [Decision Evidence
Framework](docs/architecture/decision-evidence-framework.md). It records why
significant planning and governance decisions were made using Repository Truth
references, explicit confidence provenance, alternatives, constraints and
outcomes. It does not replace human approval or duplicate Execution Evidence.

Phase E — Increment 5.2 adds the canonical local [Forge Runtime
Database](docs/architecture/runtime-database.md). It owns durable Mission,
planning, review, recommendation and Decision Evidence runtime state in
`.forge/runtime.db`, while Repository Truth and Engineering Platform Execution
Evidence remain independent authorities.

Phase E — Increment 5.3 adds [Runtime Evidence](docs/architecture/runtime-evidence.md).
Qualification, governance, and workspace runtime reports are now projections of
the Runtime Database; Execution Host Evidence remains external and Repository
Truth remains architectural authority.

Phase C — Architecture Reconciliation adds the canonical
[Governance Profile Model](docs/architecture/governance-model.md). Solo, Duo,
Startup, and Enterprise scale the same lifecycle by changing role assignments,
approval authority, workspace visibility, advisor availability, execution
permissions, and explicit shortcuts only. It adds no workflow engine, identity
system, RBAC, UI, or profile-specific operating mode.

Phase D — Increment 4.0 adds the local, business-only
[Business Workspace](docs/architecture/business-workspace.md). It persists and
lists Mission Candidates, renders advisory Mission Recommendations, supports
business refinement and auditable approval/rejection/archive decisions, and
resolves canonical Governance Profiles with legacy read compatibility. It does
not perform architecture, create a Mission, start engineering, operate a
repository, or implement a Runtime or UI framework.

Phase D — Increment 4.1 adds the local, non-executing
[Architecture Workspace](docs/architecture/architecture-workspace.md). It
admits only Business-approved Mission Candidates, refines architecture-owned
engineering constraints, provides immutable Architecture Advisor guidance, and
records the distinct approval for engineering. It does not implement Mission
planning, execution, runtime controls, providers, repository mutation, or a
UI framework.

Phase D — Increment 4.2 adds the deterministic, repository-only
[AI Mission Planner](docs/architecture/ai-mission-planner.md). It turns an
engineering-approved Architecture Mission and digest-pinned evidence into
bounded Engineering Intents and Actions, then continuously replans after
Mission State and Execution Evidence updates. It neither changes Mission or
Architecture authority nor performs Runtime or Execution Host work.

Phase D — Increment 4.5 added a historical [Bootstrap Mission Sequence
Qualification](docs/architecture/bootstrap-mission-sequence-qualification.md)
harness. It remains regression evidence for the bootstrap portfolio only; it
does not create Runtime Instance state and does not govern Generation 2
dispatch.

Phase D — Increment 4.3 adds the [Approved Mission Dispatcher](docs/architecture/approved-mission-dispatcher.md).
It activates exactly one Architecture-approved Mission from a persistent,
deterministic FIFO queue, resumes it safely, and re-evaluates the queue only
after independently verified completion. It does not plan or execute work.

Phase D — Increment 4.4 adds the deterministic
[Autonomous Mission Execution Loop](docs/architecture/autonomous-mission-execution-loop.md).
It composes one active approved Mission through planning, single-Action Host
execution, evidence processing, durable Mission State, explicit recovery and
completion notifications. Business and Architecture governance remain outside
the loop; the Execution Host remains independent. See the
[Execution Loop Report](docs/reports/forge-autonomous-mission-execution-loop-report-001.md).

Policy-Driven Mission Execution extends that loop with versioned
[Execution Policy](docs/architecture/execution-policy.md): continuous, Action,
Intent, Capability, Mission, and Custom review pauses preserve identical
planning and Execution Host behaviour. See the
[Execution Policy Report](docs/reports/forge-execution-policy-report-001.md).

Phase E — Increment 5.0 adds the versioned, advisory
[Solution Template Framework](docs/architecture/solution-template-framework.md).
It turns reusable solution archetypes into deterministic, editable
Business-review Mission Candidate drafts while preserving separate Business and
Architecture approvals. It does not approve, plan, or execute a Mission.

The canonical engineering hierarchy and iterative feedback loop are:

```text
Vision → Architecture → Roadmap → Mission → Mission Planner → Engineering Intent →
Engineering Action → Runtime Prompt → Execution Host → Repository → Evidence →
Architecture Review → Mission Recommendation → Portfolio
```

Prompt Artifact is retained as the compatible transitional execution
representation introduced during bootstrap. Runtime Prompts are instead
provider-specific artifacts produced from an Engineering Action.

It intentionally does not include a UI, SaaS service, cloud runtime,
multi-user model, agent runtime, repository mutation engine, or remote
integration.

## Bootstrap context

Forge is a new product and an independent Git repository. It is not a rename,
migration, or modification of Engineering Platform 1.5. During this bootstrap,
Engineering Platform 1.5 provides the local Codex CLI execution context only.
Forge makes no runtime dependency on it.

## Working model

Start with the Foundation Model schemas and example:

```text
schemas/
        +
examples/foundation.example.json
```

A Workspace is a software product, not a repository. It references a separate
Repository Catalog, which assigns exactly one canonical repository and any
supporting, documentation, or future-capability repositories. Repository
identity remains independent of its catalog role. The catalog is declarative:
it does not clone, modify, push, or otherwise operate on repositories.

## Knowledge sources

This bootstrap used the AI Platform Engineering Knowledge Base as a read-only
source of generic principles: certified knowledge authority, traceability,
metadata, and human-governed lifecycle decisions. DJConnect and Technical Debt
Engine were observed only as read-only reference implementations for patterns
such as repository-first operation, explicit scope, evidence, and stable public
contracts. No product code, product architecture, or domain concepts were
copied into Forge.

The evidence record is in
[docs/evidence/bootstrap-evidence.md](docs/evidence/bootstrap-evidence.md).

## Knowledge consumption

Knowledge sources remain external, versioned evidence providers. Certified
sources are authoritative; registering a reference or a generated Forge output
does not make it authoritative knowledge. Forge persists only its own local
declarations and never modifies a source. See
[Knowledge Consumption 0.4](docs/architecture/knowledge-consumption.md).

## Engineering planning

Planning references Knowledge Sources, evidence records, architecture
documents, and foundation documents without copying their content. When a
known source set is supplied, the loader rejects unknown knowledge-source
references; all processing remains local and deterministic. See
[Engineering Planning Foundation 0.5](docs/architecture/engineering-planning.md)
and [the example](examples/planning.example.json).

## Architecture and next direction

The canonical [Product Model](docs/architecture/product-model.md) places Forge
Engineering within a portfolio-driven capability lifecycle. Mission Candidates
belong to the Business Workspace, Missions require explicit Business Owner and
Platform Architect approval, and Forge remains autonomous only within an
approved Mission.

The [Forge Constitution](knowledge/bootstrap/01_CONSTITUTION.md) is the
canonical authority for Forge's permanent engineering principles. It is
elaborated by [Architecture Principles](docs/architecture/architecture-principles.md),
[Workspace Readiness](docs/architecture/workspace-readiness.md), and the
[Bootstrap Knowledge Capture Reports](docs/reports/).

With the scheduler now reconciled to the Execution Host Contract, the
recommended next increment may be a minimal Mission Runner that preserves the
one-Action, explicit-recovery boundary. Forge still does not provide a concrete
Runtime Provider, Runtime, queue, Studio, repository operations, or execution.

See [docs/architecture/core-concepts.md](docs/architecture/core-concepts.md),
[docs/architecture/workspace-foundation.md](docs/architecture/workspace-foundation.md),
and [docs/handoff/forge-bootstrap-increment-002.md](docs/handoff/forge-bootstrap-increment-002.md).
