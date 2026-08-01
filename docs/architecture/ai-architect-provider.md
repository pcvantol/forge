# AI Architect Provider Contract 1.6

## Purpose

Forge owns engineering reasoning and its durable knowledge. An AI Architect
Provider is a replaceable reasoning adapter: it analyses the complete
Forge-supplied context and returns advisory candidates. This contract is
immutable, local, provider-independent, and non-executing. It creates neither
runtime prompts nor runtime work.

The contract supports future adapters for OpenAI, Claude, Gemini, and Local
LLMs without making any one of them architectural authority. No provider is
implemented by this increment.

## Contract

`AIArchitectRequest` is prepared by Forge and must include versioned,
read-only references for every source class:

- Repository Knowledge, Architecture Handbook, Constitution, Engineering
  History, Engineering Intents, and Repository Evidence;
- Workspace Context, Roadmap Context, and Capability Catalogue.

`AIArchitectResult` is advisory and must provide evidence-linked Architectural
Finding Candidates, Engineering Opportunity Candidates, an Engineering
Proposal Draft Candidate, an Engineering Intent Draft Candidate, Reasoning
Evidence, Confidence, and Recommendations. Confidence indicates only the
provider's stated certainty; it never overrides repository evidence, the
Constitution, or a human decision.

Candidates are deliberately distinct from `ArchitecturalFinding`,
`ArchitecturalOpportunity`, `EngineeringProposalHandoff`, and
`EngineeringIntent`. A provider cannot call `accept_for_proposal`, create an
`EngineeringProposalHandoff`, create a canonical Intent, or assign any
approval or lifecycle status.

## Responsibilities and boundaries

A provider may analyse, reason, explain, and propose. It may not redefine
architecture, bypass governance, change repository knowledge, execute
engineering, access a Runtime Provider, or generate runtime prompts. Forge and
human governance evaluate the returned candidates through the existing
Architecture Reasoning, Proposal, and Intent processes.

This preserves the canonical chain:

```text
Repository Knowledge → Forge Architecture Reasoning → AI Architect candidates
→ human-governed Proposal and Intent → Runtime Provider → Execution → Evidence
```

Runtime Providers are a different future boundary. They translate approved
Engineering Intent into provider-specific runtime prompts; AI Architect
Providers supply pre-governance architectural reasoning only.

## Provider lifecycle (documented only)

Future provider management follows seven stages: Registration, Qualification,
Selection, Invocation, Result, Evidence, and Retirement. Registration records
an adapter identity and contract version. Qualification establishes whether an
adapter can be selected. Selection is a Forge and governance decision.
Invocation supplies a complete immutable request. Result records advisory
output and its traceability. Evidence records reproducible qualification and
use evidence. Retirement removes an adapter from future selection while
preserving historic evidence. This increment implements none of those stages.

## Qualification principles

Before future use, qualification should evaluate reasoning quality,
architectural consistency, constitutional compliance, engineering usefulness,
determinism where applicable, and evidence quality. Qualification is separate
from a provider's confidence statement and never grants execution authority.

## Repository structure

Future adapters belong in `forge/ai_architect/providers/`. The folder is a
documented reservation, not an implementation or registration mechanism.
