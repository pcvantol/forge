# AI Architect Session 1.8

## Purpose

An AI Architect Session is one bounded architectural reasoning interaction
between Forge and a selected AI Architect Provider declaration. It binds the
exact workspace, provider identity and version, objective, complete request,
repository snapshot, constitutional context, architecture context, and any
advisory output into an immutable record.

The contract is conceptual and local. It does not implement OpenAI, Claude,
Gemini, a Runtime Provider, invocation, prompt generation, persistence,
Studio, or engineering execution.

## Inputs and preparation

Each session composes the complete `AIArchitectRequest` from the existing
[AI Architect Provider Contract](ai-architect-provider.md). That request
requires versioned references to Repository Knowledge, Architecture Handbook,
Constitution, Engineering History, Engineering Intents, Repository Evidence,
Workspace Context, Roadmap Context, and Capability Catalogue.

The session adds a repository snapshot—repository identity, revision, and
evidence references—and explicit constitutional and architecture contexts.
These fields preserve the bounded repository reality against which advisory
reasoning is reviewed. Forge normalizes references and request inputs in a
stable order, so an equivalent declared session has deterministic structure.

## Outputs and human review

At review, a session records one advisory `AIArchitectResult`: Architectural
Findings, Opportunities, an Engineering Proposal Draft, an Engineering Intent
Draft, Confidence, Reasoning Evidence, and Recommendations. The output must
match the session request and selected provider identity.

Sessions produce recommendations only. Humans remain responsible for
architectural decisions, approvals, and Engineering Intent acceptance. A
session has no approval field or authority and cannot accept an opportunity,
create a canonical Engineering Proposal or Intent, invoke a Runtime Provider,
or execute engineering work.

## Lifecycle

```text
CREATED → PREPARED → REASONING → REVIEW → COMPLETE
              │           │          │
              └───────────┴──────────┴→ ABANDONED
```

`CREATED` binds declared context. `PREPARED` confirms that the immutable
session boundary is ready for a future provider interaction. `REASONING`
marks the bounded advisory phase. Moving to `REVIEW` requires an already
produced, traceable advisory result; the lifecycle function does not produce
it. `COMPLETE` preserves that result for human review records. `ABANDONED` is
terminal and makes no recommendation authoritative. All transitions are pure
immutable replacements; none invokes a provider or grants approval.

## Relationships

The session consumes Forge Knowledge and the Founding Architecture Handbook
through the complete request. It supplies pre-governance advisory material to
the existing Architecture Reasoning, Engineering Proposal, and Engineering
Intent processes. Engineering Intent remains the canonical human-governed
record of bounded work.

Runtime Providers remain a later, distinct boundary. They derive transient,
provider-specific Runtime Prompts only from an eligible Engineering Intent;
they do not run an AI Architect Session or replace its human review.

```text
Knowledge + Handbook + Evidence
  → AI Architect Session (advisory)
  → Human review and architecture decision
  → Engineering Proposal / Engineering Intent
  → Runtime Provider (future) → Execution (outside this model)
```

## Canonical repository locations

- Session records: `forge/ai_architect/sessions/`
- Session History: `forge/ai_architect/session_history/`
- Session Evidence: `forge/ai_architect/session_evidence/`

Those directories declare durable locations only. This increment persists no
records and performs no evidence capture. The local contract is
`forge/models/ai_architect_session.py`.

## Next increment

The next increment should implement the first concrete AI Architect Provider
against the established Provider Contract, Provider Registry, and Session
Contract. It must remain separately authorized and prove qualification without
turning advisory output into approval or execution authority.
