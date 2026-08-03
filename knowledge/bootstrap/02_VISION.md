# Forge Vision

## Purpose and authority

This is Forge's canonical product-vision document. It captures product
direction that emerged during bootstrap. It does not change the
[Forge Constitution](01_CONSTITUTION.md), select roadmap work, define a new
architecture, or authorize a capability. The Constitution remains the
authority for Forge's permanent engineering principles; this document explains
the product outcome those principles serve.

## Why Forge exists

### Context

Software products need more than generated code. They need an enduring product
context, architecture, bounded engineering work, accountable approval,
observable execution, and evidence that the intended result was achieved.

### Vision

Forge exists to become an AI-native Product Development Platform capable of
engineering software products under human governance. Engineering is one
bounded stage of its broader capability lifecycle; it does not own product
opportunity selection or architectural approval.

### Rationale

Code generation alone cannot preserve product meaning, establish authority to
act, or demonstrate completion. Forge therefore treats engineering as a
governed lifecycle that connects durable product knowledge to bounded work and
verifiable outcomes.

### Consequences

- Forge's product boundary includes product and engineering meaning, not only
  provider instructions or generated source.
- Generated code, a prompt, or an available runtime is not by itself a
  complete engineering outcome.
- Future behavior must preserve human governance and evidence as integral
  parts of engineering.

## The product capability lifecycle

### Context

Bootstrap established that enduring product meaning, bounded engineering
intent, runtime-specific translation, execution, and evidence have distinct
responsibilities.

### Vision

Forge's intended product capability lifecycle is:

```text
Vision
  ↓
Portfolio
  ↓
Mission Candidate
  ↓
Business Review
  ↓
Approved for Architecture
  ↓
Architecture Review
  ↓
Approved for Engineering
  ↓
Mission
  ↓
Engineering
  ↓
Execution
  ↓
Evidence
  ↓
Architecture Review
  ↓
Mission Recommendation
  ↓
Portfolio
```

### Rationale

The lifecycle separates concerns that otherwise become conflated in a prompt
or runtime. The Business Workspace owns opportunities, value, prioritisation,
and strategic alignment. The Architecture Workspace turns a business-approved
candidate into an architect-approved Mission with explicit boundaries. Forge
then owns only the engineering chain inside that Mission. Architecture Review
interprets evidence and may produce an advisory Mission Recommendation for the
Portfolio; it never creates a new Mission automatically.

### Consequences

- No lifecycle stage silently replaces the authority of another stage.
- Mission Candidates are opportunities, never executable work or implicit
  Missions.
- A Mission exists only after Business and Platform Architect approvals.
- Forge remains autonomous only within an approved Mission and never changes
  its objective.
- Evidence connects outcomes to declared engineering intent and repository
  reality; recommendations return to the Portfolio through human governance.

## Human governance

### Context

AI can analyse, plan, propose, and execute useful engineering work, but those
activities do not independently create product authority.

### Vision

Humans define vision, architecture, governance, and approvals. Forge performs
engineering within those boundaries.

### Rationale

The human role is to establish what the product is for, which architectural
constraints endure, how authority is exercised, and when work may progress.
Forge can make that direction operational without treating its output or
runtime availability as implicit approval.

### Consequences

- AI work is limited by explicit authority and declared scope.
- Approval authorizes progression but does not alter the content of an
  Engineering Intent.
- Governance remains authoritative as Forge gains additional engineering
  capabilities.

## Product scope

### Context

Forge begins with a local, deterministic foundation for product context,
knowledge, planning, proposals, intent, and evidence references. Bootstrap
identified the broader responsibilities that the platform is intended to bring
together over time.

### Vision

Forge is intended to provide a coherent engineering platform for:

- Workspace management;
- Architecture management;
- Capability management;
- Knowledge management;
- Engineering planning;
- Engineering execution;
- Governance; and
- Runtime abstraction.

### Rationale

These responsibilities form one engineering model: a product Workspace is not
reduced to a repository, engineering knowledge is not reduced to a prompt,
and execution infrastructure is not allowed to own the meaning of the work it
performs.

### Consequences

- Scope is organized around engineering responsibilities, not a single tool
  surface.
- Each new behavior remains a separately bounded, governed capability.
- Present bootstrap implementations do not imply that every intended
  responsibility is already implemented.

## Explicit non-goals

### Context

Forge must retain a clear boundary as it evolves. Existing bootstrap records
exclude several adjacent tool categories and execution services from the
current product responsibility.

### Vision

Forge is not a coding assistant, prompt manager, IDE replacement, Git
replacement, deployment platform, or CI server. Forge orchestrates
engineering.

### Rationale

Those tools may contribute to an engineering workflow, but they do not by
themselves supply Forge's product model: governed intent, durable knowledge,
runtime independence, and evidence-based outcomes. Conflating Forge with them
would obscure its responsibility and make provider or host details
architecturally authoritative.

### Consequences

- Forge does not claim ownership of editing environments, version control,
  deployment, or CI infrastructure.
- A Runtime Provider or Execution Host may use such tools without turning
  Forge into a replacement for them.
- Adjacent capabilities require an explicit, governed decision rather than
  being inferred from this vision.

## Bootstrap philosophy

### Context

Forge began by engineering itself in a local bootstrap environment. Its
foundation was discovered and captured through bounded engineering increments,
repository evidence, and subsequent knowledge capture.

### Vision

Forge intentionally began by engineering itself. Architecture emerged through
engineering rather than being fully specified beforehand, and bootstrap
discoveries are valuable engineering knowledge.

### Rationale

The bootstrap journey exposed the distinctions between Workspace and
repository, Intent and prompt, governance and execution, and evidence and a
claim of success. Capturing those discoveries in the repository preserves them
for assessment and future work without elevating temporary conversations or
bootstrap prompts into permanent authority.

### Consequences

- Bootstrap discoveries are retained as reviewed repository knowledge.
- Product knowledge evolves from evidence-backed engineering experience.
- Bootstrap history informs the product but does not override the Constitution
  or authorize future work.

## Long-term product evolution

### Context

Bootstrap discussed a direction beyond the initial local foundation while
keeping unimplemented behavior outside the present scope.

### Vision

The intended direction includes Self Engineering, Knowledge Distillation,
Runtime abstraction, a Capability Marketplace, and Multi-user governance.
These are product-direction concepts, not implemented capabilities or an
approved roadmap commitment.

### Rationale

Self Engineering applies Forge's engineering model to Forge itself. Knowledge
Distillation expresses the value of turning assessed engineering discoveries
into durable, reusable knowledge. Runtime abstraction preserves the separation
between Forge-owned meaning and replaceable providers or hosts. A Capability
Marketplace and Multi-user governance describe future ways the engineering
model may grow beyond the initial local, solo bootstrap context while retaining
explicit authority boundaries.

### Consequences

- The concepts do not introduce storage, execution, cloud, marketplace, or
  multi-user functionality in this capture.
- Any realization remains subject to separately bounded intent, architecture,
  governance, approval, and evidence.
- Forge's long-term direction remains compatible with replaceable runtime
  providers and explicit human authority.

## Relationship to Engineering Platform 1.5

### Context

Engineering Platform 1.5 supplied the bootstrap execution environment and
transport for Forge's initial engineering work.

### Vision

Engineering Platform 1.5 is the bootstrap execution host, temporary
implementation, and execution infrastructure. Forge is the engineering model,
engineering knowledge, and future runtime owner. Forge is not a rename of
Engineering Platform.

### Rationale

Bootstrap needed a working execution environment without allowing that
environment to define Forge's enduring identity. Stable execution contracts
preserve the value of the host while allowing Forge to own the model and
knowledge that outlast a particular implementation.

### Consequences

- Forge has no permanent runtime dependency on Engineering Platform 1.5.
- Replacing an Execution Host must not require changing engineering meaning.
- Future Forge runtime ownership is a product direction; it does not imply a
  currently implemented Runtime Provider or execution system.
