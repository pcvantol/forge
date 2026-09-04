# Forge Roadmap

## Purpose and authority

This is Forge's canonical strategic roadmap captured from bootstrap knowledge.
It explains strategic evolution, architectural maturity, and long-term
destination without creating an implementation backlog, selecting delivery
order, or authorizing work. The [Forge Constitution](01_CONSTITUTION.md),
[Vision](02_VISION.md), [Core Architecture](03_ARCHITECTURE.md), [Engineering
Model](05_ENGINEERING_MODEL.md), [Knowledge Model](06_KNOWLEDGE_MODEL.md),
[Governance Model](07_GOVERNANCE.md), and [Capability Catalogue](09_CAPABILITIES.md)
remain authoritative for their respective boundaries.

## Roadmap philosophy

### Context

Forge needs a stable account of strategic evolution without treating a list of
possible features as an implementation plan.

### Current state

Bootstrap established a local, deterministic foundation and a capability-first
model. The canonical lifecycle distinguishes Roadmap, Backlog, Proposal,
Engineering Intent, Approval, Runtime Provider, Runtime Prompt, Execution,
Evidence, and Knowledge Evolution.

### Target state

The roadmap remains capability-driven: it frames the enduring direction in
which Forge can evolve, while individually bounded Capabilities make that
direction concrete. It is independent from Engineering Intents. A Roadmap may
inform an Intent, but an Engineering Intent is the canonical, model-independent
statement of one bounded engineering change and does not derive authority from
roadmap presence alone.

### Rationale

Separating strategic direction from bounded work preserves human governance and
prevents a roadmap from becoming either an implied approval or an execution
instruction. Engineering Intents implement Roadmap direction only when a
separately governed proposal and approval bound the work.

### Dependencies

This philosophy depends on the Constitution's human-governance,
repository-first, and capability-first principles; the Engineering Model's
Intent and evidence boundaries; and the Knowledge Model's reconciliation
boundary.

## Bootstrap path

### Context

Forge required an engineering environment before it could own its future
runtime. Bootstrap was therefore intentionally conducted through the temporary
Engineering Platform 1.5 Bootstrap Execution Host.

### Current state

Bootstrap preceded autonomous engineering so that Forge could first establish
its Workspace, knowledge, engineering, governance, and evidence boundaries in
repository-held form. The temporary host executed bounded Genesis transactions;
it did not become the owner of Forge knowledge, engineering meaning, or
governance.

### Target state

Forge can progress from its completed Foundation through Self Engineering and
later runtime maturity toward a governed Production state. The progression is
strategic rather than a delivery sequence.

### Rationale

Autonomous behavior without a durable product model would allow an execution
environment to define its own work. Bootstrap first established the durable
boundaries that let future execution remain governed, repository-first, and
provider-independent.

### Dependencies

The path depends on the temporary Bootstrap Execution Host boundary, durable
Engineering Intent, Runtime Provider abstraction, human approval, and
evidence-based phase completion.

```mermaid
flowchart TD
    B[Bootstrap] --> F[Foundation]
    F --> SE[Self Engineering]
    SE --> R[Runtime]
    R --> P[Production]
```

`Self Hosting` was named in the bootstrap objective but is not established in
the captured Forge architecture as a phase, capability, or runtime commitment.
It is therefore not asserted by this roadmap; any future use requires its own
reconciled architectural evidence and governed Intent.

## Phase A — Foundation (complete)

### Context

Phase A was the bootstrap effort to create a small, deterministic engineering
foundation before Forge attempts to perform its own engineering through a
Forge-owned runtime.

### Current state

**Phase A is complete.** It established the Workspace and Foundation Model;
Knowledge source and consumption boundaries; Engineering planning, proposal,
Prompt Artifact, and Engineering Intent architecture; Governance boundaries;
Bootstrap Knowledge Packages; and the local, evidence-first foundation needed
to assess phase completion. The architectural outcome is a repository-first
model in which Workspace product meaning, canonical Intent, runtime-specific
translation, execution, governance, and evidence have separate authorities.

The completed state is local and deterministic. It provides schemas, immutable
models, loaders, registries, declarations, and typed evidence references. It
does not provide intent persistence, Runtime Providers, a Mission Runtime,
repository operation, execution, Studio, cloud service, or multi-user model.

### Target state

Foundation remains the durable base for subsequent capability evolution. Its
boundaries are preserved as Self Engineering acquires separately governed
capabilities; it is not replaced by provider prompts or a future execution
host.

### Rationale

Establishing Foundation first makes future engineering accountable to durable
knowledge and observable evidence instead of to a temporary bootstrap prompt
or runtime convention.

### Dependencies

Phase A relies on the Constitution, the Foundation Model, read-only knowledge
sources, repository evidence, and human governance. Future use of the
Foundation relies on preserving those same boundaries.

## Phase B — Self Engineering (underway)

### Context

Self Engineering is the established direction in which Forge turns its
repository-held engineering model into more durable, governed engineering
capabilities without giving execution authority to a runtime.

### Current state

Phase B is underway but incomplete. Its delivered Increment 1.0 is the
evidence-only Phase Completion Framework: it assesses declared criteria from
reproducible evidence and does not orchestrate work, operate repositories, or
grant execution authority. It does not establish Engineering Intent
persistence, migration, Runtime Providers, or execution.

Bootstrap has also established the following as directions or conceptual
boundaries, not implemented behavior: Engineering Intent lifecycle and durable
local persistence; reconstruction and migration of bootstrap intents;
Knowledge Reconciliation; Runtime Provider abstraction and derived Runtime
Prompts; Mission Runtime; and Architecture Stewardship. Repair reports exist
as evidence references; a separate `Repair Engineering` capability has not
been established by this capture.

### Target state

Self Engineering can mature through independently bounded capabilities that
persist and validate Intent, reconcile knowledge, derive runtime-specific
representations from canonical Intent, and assess evidence against declared
outcomes. It preserves Prompt Artifact compatibility until Runtime Providers
are separately implemented and governed.

### Rationale

The direction makes Forge progressively able to engineer itself while keeping
Intent canonical, runtime prompts derived and temporary, and human governance
outside execution.

### Dependencies

This phase depends on the completed Foundation, the Engineering Intent
architecture, the Phase Completion Framework, knowledge reconciliation,
repository truth, explicit human approval, and separately qualified
Capabilities.

## Capability evolution

### Context

Forge grows through bounded Capabilities rather than through an undifferentiated
product surface or an implicit runtime.

### Current state

Bootstrap defines a Capability as a declared, versioned, discoverable,
composable, independently evolvable unit. Present declarations do not imply
implementation, installation, approval, qualification, compatibility, or
production trust.

### Target state

Over time, Capabilities can become discoverable, versioned, qualified,
installable, and composable. Qualification remains evidence-first and
Production remains a future governed operating state rather than a phase made
real by documentation.

### Rationale

Capability evolution drives Forge evolution because it permits engineering
responsibilities to become useful independently while preserving explicit
dependencies, non-goals, and governance. It prevents names such as runtime or
Studio from silently becoming a monolithic product commitment.

### Dependencies

It depends on repository-held knowledge, explicit declarations, qualification
evidence, Governance, Workspace context, and compatible runtime and execution
boundaries where a Capability needs them.

```mermaid
flowchart LR
    K[Knowledge] --> C[Capabilities]
    C --> E[Engineering]
    E --> EV[Evolution]
    EV -. assessed learning .-> K
```

## Knowledge evolution

### Context

Forge must preserve useful discoveries without allowing conversations,
transcripts, generated output, or provider prompts to become product truth.

### Current state

Bootstrap establishes the path from conversations and working material through
Knowledge Packages and reconciliation to repository knowledge. After review,
the repository—not its originating conversation or package—is canonical.

### Target state

The long-term knowledge direction is:

```text
Conversations
  ↓
Knowledge Packages
  ↓
Repository Knowledge
  ↓
Architecture Handbook
  ↓
Engineering Intents
  ↓
Engineering
```

Knowledge Distillation may make candidate discoveries reusable, while
Knowledge Reconciliation compares each candidate with Repository Context and
Architecture Stewardship guides coherent handbook evolution. Neither is an
automatic authority transfer or repository mutation.

### Rationale

Repository knowledge becomes canonical because it is reviewable against the
existing architectural baseline, can retain provenance and rationale, and can
be reconciled with repository reality. This makes the engineering loop durable
across conversations, providers, and execution hosts.

### Dependencies

It depends on versioned, read-only knowledge sources; Knowledge Candidates;
Repository Context; Architecture Review; Knowledge Packages; assessed evidence;
and human architectural judgment.

## Runtime evolution

### Context

Forge distinguishes the knowledge that defines engineering from the
environment that executes it.

### Current state

Engineering Platform 1.5 is only the temporary Bootstrap Host. Forge already
owns its conceptual engineering model, but its first operational runtime is a
future deterministic Forge CLI, not a Forge Runtime Service.

### Target state

The canonical implementation direction is CLI-first:

```text
Mission Document
  ↓
Mission Intake
  ↓
Forge CLI
  ↓
Mission qualification and canary
  ↓
Forge Runtime Service
  ↓
Forge Studio
```

The Runtime Service is an operational evolution of the validated CLI: it adds
continuous operation, supervision, automatic resume, evidence polling, and
scheduling without changing engineering behavior. Execution remains owned by
the Execution Host, and Engineering Platform 1.5 is reached only through the
Execution Host Contract and Bootstrap Execution Host Adapter.

### Rationale

Separating engineering knowledge from execution lets Forge retain its meaning
when providers and hosts change. It prevents temporary bootstrap transport and
execution availability from becoming permanent architectural authority.

### Dependencies

Runtime evolution depends on the CLI, Mission Intake, a Runtime Prompt Renderer,
the Bootstrap Execution Host Adapter, mission qualification, human approval,
repository truth, and evidence capture.

## Studio evolution

### Context

Bootstrap records a future Studio boundary but explicitly establishes no UI,
Studio, renderer, SaaS service, cloud runtime, or multi-user implementation.

### Current state

Studio remains deferred. `Electron Studio`, `Renderer Hosts`, and a
workspace-centric UX have been discussed as possible terms, but no captured
Forge architecture defines them as products, implementation details, or
roadmap commitments.

### Target state

A future Studio direction, if separately reconciled and governed, is the
primary user interface for the Business Workspace, Architecture Workspace,
Execution Workspace, and Analytics. It orchestrates the Runtime while
remaining independent of an execution host and never owning execution.

### Rationale

A user experience must not collapse Workspace ownership, canonical knowledge,
or governance into a provider-specific execution interface.

### Dependencies

Any Studio evolution depends on the Workspace model, runtime independence,
Governance, knowledge and capability boundaries, and a separately authorized
Capability. It has no established implementation dependency in bootstrap.

## Future evolution boundaries

### Context

Bootstrap identified several long-term directions beyond the current
Foundation without implementing or sequencing them.

### Current state

Forge Runtime, Knowledge Distillation, Architecture Handbook evolution,
Execution Host independence, expanded governance profiles, product identity,
and a Capability Marketplace direction appear as conceptual or deferred
boundaries. A Mission Runtime, queue, Studio, API, cloud, and multi-user
capabilities are explicitly deferred. No marketplace, multi-user governance
mechanics, cloud product, or execution system is currently established.

### Target state

Future evolution can make these directions independently useful only through
bounded, evidence-backed Capabilities. A Capability Marketplace could become a
future discoverability and composition direction, but this capture establishes
neither marketplace behavior nor installation mechanics. Multi-user governance
remains a future profile and governance boundary, not roles, access control,
or workflow implementation.

### Rationale

Recording strategic directions preserves bootstrap learning without converting
it into backlog work, a product promise, or a runtime commitment.

### Dependencies

Every future direction depends on the Foundation, repository-first knowledge,
explicit Capability boundaries, human governance, qualification evidence, and
a separately authorized Engineering Intent.

## Forge + Workspace V1 implementation programme (proposed)

This section is the dependency-aware implementation roadmap arising from the
[V1 architecture completeness review](../../docs/architecture/FORGE_WORKSPACE_V1_PRODUCT_MODEL.md).
It does not approve a Mission, allocate a Mission ID, or authorize execution.
Each increment requires its own approved Mission and must preserve the
Forge/Workspace/EP ownership boundaries. The gap register is the authoritative
open-decision list.

| Increment | Objective and owner repo | Affected repos / depends on | Parallel-safe with / integration point | DoR / DoD / goldens / Human Gates / exit evidence |
| --- | --- | --- | --- | --- |
| I01 — Installed control-plane foundation | Establish a supported single-installation bootstrap, named-operator identity boundary and Workspace Server project-state contract. **Owner: Workspace.** | Workspace, Forge, EP; depends on no V1 implementation increment, but resolves `FWV1-G001/G010/G011`. | Can run with I02 only after interface stub review. Integrates through versioned setup/health and no-secret references. | **DoR:** approved installation/trust ADR and owned schemas. **DoD:** clean install/restart/offline-health flows. **Goldens:** installed artifact manifest, redacted setup audit. **Gate:** security review. **Exit:** qualification proves source-checkout-free installed startup. |
| I02 — Baseline and effective Action contract | Define and implement Forge Product Baseline, Project Contract and immutable Effective Action Contract composition. **Owner: Forge.** | Forge; Workspace/EP contract consumers; resolves `G002`. | Parallel-safe with I01/I03 schema exploration, not their shared contract mutation. Integrates as hash/versioned Action snapshot. | **DoR:** approved composition/compatibility ADR. **DoD:** deterministic composition, migration and rejection tests. **Goldens:** component versions/hash fixtures. **Gate:** Architecture approval. **Exit:** consumer compatibility qualification. |
| I03 — Project/repository onboarding contract | Freeze Workspace request model and EP registration/attachment/provisioning handoff for Genesis and adoption. **Owner: EP** for registration; **Workspace** for request UX; Forge supplies plan input only. | Workspace, EP, Forge; depends on I01 and EP attachment predecessor; resolves `G003`. | I04 can prepare policy profiles. Integration is accepted EP request + read-back qualification, never direct Agent command. | **DoR:** approved authority/auth/idempotency contract. **DoD:** new, existing, failed/partial and qualification-only flows. **Goldens:** portable declaration and correlation fixtures. **Gate:** provider/operator approval. **Exit:** end-to-end read-back qualification. |
| I04 — Managed governance baseline | Define generic repository governance profiles, capability discovery, drift and bounded reconciliation. **Owner: Forge** policy; **EP/provider** execution/read-back. | Forge, EP, Workspace; depends on I02/I03; resolves `G004`. | Parallel-safe with I06 UI design only. Integrates desired-policy revision to qualified provider result. | **DoR:** policy and unsupported-capability decision. **DoD:** drift/no-op/exception/reconcile behavior. **Goldens:** host capability and provider read-back fixtures. **Gate:** governance/security review. **Exit:** qualified managed/adopted repository. |
| I05 — Action graph and execution admission | Stabilize repository scope, dependencies, priority handoff and EP lease/admission responses; retain one mutating lane/repository. **Owner: Forge** graph; **EP** admission/leases. | Forge, EP, Workspace projection; depends on I02/I03; resolves `G005`. | Parallel-safe with I04 after shared IDs freeze. Integration is Producer Submission Envelope and run correlation. | **DoR:** frozen graph/lease API. **DoD:** duplicate, conflicting, retry and multi-repo read-only/mutating cases. **Goldens:** dependency and correlation fixtures. **Gate:** Architecture review. **Exit:** qualified dispatch without scheduler duplication in Forge. |
| I06 — Effective gates and review | Compose Effective DoR/DoD, proof identities, human decisions and repair loop. **Owner: Forge** composition; **Workspace** review UI; **EP** proof persistence. | Forge, Workspace, EP; depends on I02/I05; resolves `G006`. | I07 projections can develop after event schema freezes. Integration is immutable gate snapshot and attributable decision. | **DoR:** human-gate policy/identity decision. **DoD:** approve/reject/repair/timeout/replay tests. **Goldens:** gate and evidence-envelope fixtures. **Gate:** governance approval. **Exit:** one qualified human-gated Action. |
| I07 — History, attention and recovery projections | Create cross-product freshness-labelled histories, attention taxonomy and recovery views without secondary operational authority. **Owner: Workspace.** | Workspace, Forge, EP; depends on I05/I06; resolves `G007`. | Parallel-safe with I08. Integration uses immutable EP evidence and Forge decision projections/cursors. | **DoR:** projection ownership/cursor contract. **DoD:** restart, stale, retry, blocked and terminal displays. **Goldens:** replay cursor fixtures. **Gate:** UX/accessibility review. **Exit:** observed recovery drill. |
| I08 — Lifecycle migration and retention | Define and implement baseline/project upgrade, archive/restore/delete and interrupted migration behavior. **Owner: Forge** contract; Workspace/EP own their records. | Forge, Workspace, EP; depends on I02/I07; resolves `G008/G009`. | Parallel-safe with I09. Integration is owner-specific state machines and retention references. | **DoR:** retention/destruction authorization. **DoD:** compatibility preflight, interruption recovery, active-run block. **Goldens:** migration/retention fixtures. **Gate:** operator/security approval. **Exit:** qualified upgrade and archive drill. |
| I09 — Security and self-containment qualification | Package and verify released artifacts, secure references, revocation and redacted audit for the supported trust model. **Owner: each product; coordination: Forge.** | Forge, Workspace, EP; depends on I01–I08 interfaces. | Can begin threat modelling with I01; final qualification serial after all interfaces. | **DoR:** threat model and artifact manifest. **DoD:** no source checkout dependency, no secret leakage, revocation/offline tests. **Goldens:** manifest/redacted audit. **Gate:** security approval. **Exit:** `SOURCE_REPOSITORY_RUNTIME_DEPENDENCIES = 0` proof. |
| I10 — Workspace V1 interaction implementation | Implement the approved Workspace surfaces and responsive/accessibility/error contracts. **Owner: Workspace.** | Workspace, Forge/EP read APIs; depends on I01/I03/I06/I07/I09; resolves `G013`. | Presentation work may parallelize by surface once read/write contracts are frozen; not parallel-safe with API/schema changes. | **DoR:** interaction contracts and accessible acceptance criteria. **DoD:** all V1 surface states/roles/responsive behavior. **Goldens:** accessible workflows and degraded-state fixtures. **Gate:** human UX review. **Exit:** clean-install V1 journey qualification. |

**Parallelism rule:** only implementation work with no mutation of a shared schema/API can run in parallel. A shared contract predecessor must be complete, reviewed, and qualified before its dependent work starts. I12-quality/knowledge learning, enterprise identity and cross-repository atomic delivery remain outside V1 unless a new approved scope decision changes this roadmap.

## Long-term vision

### Context

Forge's vision is an AI-native engineering platform that engineers products
under human governance, rather than a prompt manager or code generator.

### Current state

Forge is repository-first and local-first. It has captured the conceptual
model for knowledge, Capabilities, Intent, runtime independence, governance,
and evidence, but it does not yet execute engineering through Forge-owned
runtime capabilities.

### Target state

Forge ultimately aims to engineer itself; evolve through Capabilities;
maintain its own Architecture Handbook; distill engineering knowledge;
reconcile architecture continuously; and remain repository-first. The target
preserves human authority, explicit approval, and evidence-based assessment
rather than claiming autonomous self-authorization.

### Rationale

This destination closes the loop from durable knowledge to bounded engineering
and assessed evidence, so Forge can improve its product model without losing
architectural continuity as runtimes and execution hosts evolve.

### Dependencies

The destination depends on all preceding roadmap areas: the completed
Foundation, governed Self Engineering, Capability qualification, knowledge
reconciliation, runtime independence, repository truth, and human governance.
