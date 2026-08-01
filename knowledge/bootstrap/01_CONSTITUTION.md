# Forge Constitution

## Purpose and authority

This Constitution is Forge's canonical constitutional layer. It records the
architectural invariants established during bootstrap. These principles change
only through the exceptional constitutional-change process described in
Article 12. The architecture documents linked by each article elaborate the
concepts; they must remain consistent with this Constitution.

## Article 1 — Repository-first Engineering

### Principle

Repository evidence is authoritative. Repository state outweighs reviewer
observations, reports, conversations, and assumptions.

### Rationale

Engineering decisions require an observable source of truth. The repository
contains the implemented state and the evidence needed to assess it, whereas
other accounts can be incomplete, stale, or mistaken.

### Consequences

- Repository reality determines the outcome of repository assessment.
- Conflicting observations or reports do not override observable repository
  evidence.
- Engineering work must preserve enough repository evidence to be assessed.

### Relationships

This principle governs the Repository Reality side of Architecture Drift and
the repository-facing checks of Workspace Readiness. It is elaborated in the
[Repository Model](../../docs/architecture/repository-model.md).

## Article 2 — Workspace-first Product Model

### Principle

A Workspace models a product, while repositories model engineering
implementation. A Workspace may manage multiple repositories, with exactly
one canonical repository.

### Rationale

Product identity and engineering implementation have different
responsibilities. Keeping them distinct allows one product to have a clear
identity and repository catalog without reducing it to a single checkout.

### Consequences

- A Workspace is not a repository and does not perform engineering work.
- Repository identity remains distinct from its catalog role.
- Supporting, documentation, and future capability repositories remain
  attributable to one product through the Workspace catalog.

### Relationships

This principle defines the scope assessed by Workspace Readiness and provides
the product context for Engineering Intent. It is elaborated in the
[Workspace Model](../../docs/architecture/workspace-foundation.md).

## Article 3 — Engineering Intent

### Principle

Engineering Intent is the canonical engineering artifact. It records the
objective, rationale, constraints, validation, and expected evidence.
Runtime prompts are not canonical.

### Rationale

Bounded engineering work needs a durable, model-independent meaning that does
not change with a runtime's prompt format. Intent preserves that meaning for
assessment and governance.

### Consequences

- Runtime-specific representations cannot redefine engineering work.
- Validation and expected evidence are declared with the work they assess.
- Approval authorizes progression but does not make a prompt canonical.

### Relationships

Engineering Intent is evaluated against Repository Reality for Architecture
Drift and may be translated by Runtime Providers. It is elaborated in
[Engineering Intent](../../docs/architecture/engineering-intent.md).

## Article 4 — Runtime Independence

### Principle

Forge owns engineering knowledge. Runtime Providers translate Engineering
Intent into runtime-specific prompts, and Execution Hosts execute work.
Execution Hosts do not own engineering knowledge.

### Rationale

Engineering knowledge must outlast any one runtime or host. Separating
knowledge ownership, translation, and execution keeps Forge independent of
provider conventions and replaceable execution infrastructure.

### Consequences

- Provider prompts are derived execution artifacts rather than authorities.
- Replacing an Execution Host must not require changing engineering meaning.
- Runtime-specific execution behavior remains outside Forge's knowledge
  ownership.

### Relationships

This principle applies Article 3 across Runtime Providers and Execution Hosts.
It is elaborated in [Engineering Intent](../../docs/architecture/engineering-intent.md)
and [Architecture Principles](../../docs/architecture/architecture-principles.md).

## Article 5 — Human Governance

### Principle

AI may analyse, plan, propose, and execute within explicit authority. Human
governance remains authoritative.

### Rationale

Engineering automation can assist with bounded work, but authority to progress
or approve work is a governance decision. Explicit human control prevents
runtime availability or generated artifacts from becoming implicit approval.

### Consequences

- AI execution is limited by granted authority and declared scope.
- Lifecycle labels and generated artifacts do not authorize work by
  themselves.
- Human approval controls progression between engineering stages.

### Relationships

This principle constrains Engineering Intent progression and the governance
profiles selected by a Workspace. It is elaborated in the
[Governance Model](../../docs/architecture/governance-model.md).

## Article 6 — Evidence-first Engineering

### Principle

Engineering completion requires evidence. Engineering success alone is
insufficient, and repository evidence is mandatory.

### Rationale

A claim that work succeeded does not demonstrate that declared completion
criteria were met. Reproducible evidence makes completion assessable and keeps
the result grounded in repository reality.

### Consequences

- A phase completes only after an evidence-backed assessment reaches
  `COMPLETE`.
- Opinion, a closure statement, or implementation success alone cannot close
  a phase.
- Completion evidence must include repository evidence where repository
  reality is relevant.

### Relationships

This principle operationalizes Article 1 for phase completion and supports
Architecture Drift assessment. It is elaborated in the
[Phase Completion Framework](../../docs/architecture/phase-completion-framework.md).

## Article 7 — Capability-first Evolution

### Principle

Forge evolves through explicit, versioned capabilities. Capabilities
contribute engineering behavior.

### Rationale

Explicit capability boundaries distinguish an established behavior from an
idea or document. Versioning keeps the responsibility and evolution of that
behavior legible.

### Consequences

- Documented concepts do not become implemented capabilities automatically.
- New behavior requires a separately bounded and governed capability.
- Capabilities declare their responsibility and non-goals as they evolve.

### Relationships

This principle governs future contributions to Workspace Readiness and the
capability model. It is elaborated in the
[Capability Model](../../docs/architecture/capability-model.md).

## Article 8 — Knowledge Ownership

### Principle

Architectural knowledge belongs in the repository. Engineering conversations
are temporary. Knowledge Packs are bootstrap sources, while repository
knowledge is permanent.

### Rationale

Repository-held knowledge can be reviewed, linked, and continued by later
work. Conversations and bootstrap inputs are useful context but cannot serve
as the durable architectural record.

### Consequences

- Bootstrap discoveries are captured in repository documentation.
- Conversations do not establish lasting architectural authority.
- Knowledge Packs inform bootstrap capture without replacing repository-held
  knowledge.

### Relationships

This Constitution is itself a repository-owned bootstrap knowledge capture.
It complements the [Knowledge Consumption](../../docs/architecture/knowledge-consumption.md)
boundary between external sources and Forge-owned declarations.

## Article 9 — Bootstrap Principle

### Principle

Engineering Platform 1.5 is the temporary bootstrap Execution Host. Forge
must not become architecturally coupled to Engineering Platform. Execution
contracts are stable and Execution Hosts are replaceable.

### Rationale

Bootstrap needs an execution environment without allowing that temporary
environment to define Forge's permanent architecture. Stable contracts retain
the value of bootstrap while preserving host replacement.

### Consequences

- Forge makes no permanent runtime dependency on Engineering Platform 1.5.
- Genesis remains a bootstrap execution profile rather than a host-owned
  product architecture.
- Future hosts must operate through stable execution contracts.

### Relationships

This principle is the bootstrap application of Runtime Independence and
Workspace Readiness. It is elaborated in
[Workspace Readiness](../../docs/architecture/workspace-readiness.md).

## Article 10 — Architecture Drift

### Principle

Architecture Drift compares Engineering Intent with Repository Reality. Prompt
history is never authoritative.

### Rationale

Prompts are derived and may vary by provider or change over time. Comparing
the canonical intent with the observable repository maintains a stable basis
for identifying divergence.

### Consequences

- Drift assessment does not compare prompt text with repository content.
- Prompt history cannot redefine intended work or repository reality.
- Drift evidence must connect the relevant intent to observable repository
  state.

### Relationships

This principle joins Article 1's repository authority with Article 3's intent
authority. It is elaborated in [Engineering Intent](../../docs/architecture/engineering-intent.md).

## Article 11 — Workspace Readiness

### Principle

Workspace Readiness is a generic capability. Execution profiles contribute
readiness checks; Genesis and Managed are profiles, not different
capabilities.

### Rationale

Readiness needs one common assessment model while allowing execution contexts
to state their distinct evidence and checks. Treating profiles as separate
products would duplicate that model and obscure shared authority boundaries.

### Consequences

- Readiness is assessed against the declared execution profile.
- Future capabilities may add declarative checks without replacing the common
  assessment model.
- Genesis and Managed remain profile boundaries, not implementation claims.

### Relationships

This principle applies the Workspace model to execution preparation and the
capability model to future readiness contributions. It is elaborated in
[Workspace Readiness](../../docs/architecture/workspace-readiness.md).

## Article 12 — Constitutional Change

### Principle

Changes to this Constitution require explicit Engineering Intent, rationale,
architectural review, and approval. Constitutional changes are exceptional.

### Rationale

These articles are the stable invariants discovered during bootstrap. Changing
them changes Forge's enduring authority boundaries and therefore requires a
deliberate, reviewable decision rather than ordinary documentation evolution.

### Consequences

- A constitutional change cannot be made by implication or through a runtime
  prompt.
- The proposed change must state its intent and rationale.
- Architectural review and approval are required before a constitutional
  change takes effect.

### Relationships

This principle applies Human Governance to the constitutional layer and uses
Engineering Intent as the canonical change artifact. It preserves the
authority relationships established by every preceding article.
