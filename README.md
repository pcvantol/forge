# Forge

Forge is a local-first, AI-native engineering platform foundation. It gives an
engineering workspace a small, explicit vocabulary before it gains automation:
the workspace it operates in, the repositories it knows, and the human
governance that constrains its work.

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
- full Engineering Mode and Governance Profile value catalogs;
- bootstrap activation of `prototype` and `solo` only;
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

The canonical engineering chain is:

```text
Repository Knowledge → Architecture Reasoning → Engineering Proposal →
Engineering Intent → Runtime Provider → Runtime Prompt → Execution → Evidence
```

Prompt Artifact is retained as the compatible transitional execution
representation introduced during bootstrap. Runtime Prompts are instead
provider-specific artifacts derived from Engineering Intent once Runtime
Providers are implemented.

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

The [Forge Constitution](knowledge/bootstrap/01_CONSTITUTION.md) is the
canonical authority for Forge's permanent engineering principles. It is
elaborated by [Architecture Principles](docs/architecture/architecture-principles.md),
[Workspace Readiness](docs/architecture/workspace-readiness.md), and the
[Bootstrap Knowledge Capture Reports](docs/reports/).

The recommended next increment is Forge Phase B — Increment 1.7 — OpenAI AI
Architect Provider. Forge still does not provide an AI Architect Provider, a
Runtime Provider, a Mission Runtime, a queue, Studio, repository operations,
or execution.

See [docs/architecture/core-concepts.md](docs/architecture/core-concepts.md),
[docs/architecture/workspace-foundation.md](docs/architecture/workspace-foundation.md),
and [docs/handoff/forge-bootstrap-increment-002.md](docs/handoff/forge-bootstrap-increment-002.md).
