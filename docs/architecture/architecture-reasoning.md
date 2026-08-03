# Forge Architecture Reasoning 1.5

## Purpose and boundary

Architecture Reasoning makes the pre-authoring architectural decision process
explicit. It exists so a future Engineering Intent follows durable repository
knowledge, observable repository reality, constitutional constraints, and a
human architectural decision rather than a conversation, a runtime prompt, or
an unexamined roadmap item.

This is a canonical reasoning model, not an AI reasoning system. Its immutable
local contracts record declared assessments and decisions only. They do not
read a repository, discover findings, retrieve knowledge, score alternatives,
plan autonomously, create an Engineering Proposal or Engineering Intent,
invoke a provider, or operate a Runtime.

## Canonical pipeline

```text
Repository Knowledge → Repository Assessment → Architectural Findings
  → Architectural Opportunities → Capability Impact → Roadmap Impact
  → Engineering Proposal → Engineering Intent
```

Repository Knowledge supplies versioned context. A Repository Assessment makes
the relevant knowledge and repository evidence explicit. Findings record what
the assessment discovered. Opportunities are possible improvements, not yet
engineering work. Their capability and roadmap impacts frame an architectural
review. An accepted opportunity becomes eligible for the existing governed
Engineering Proposal process; a proposal then remains governed input to
Engineering Intent authoring.

The complete authority boundary is:

```text
Knowledge → Reasoning → Proposal → Engineering Intent → Runtime
```

Reasoning owns engineering decisions. Runtime owns execution. Neither a
runtime, provider, proposal lifecycle label, nor an Intent lifecycle label
authorizes work without the human governance required by the Constitution.

## Architecture Workspace review boundary

Architecture Review has two distinct product-model roles. Before engineering,
the Platform Architect refines a Business-approved Mission Candidate's scope,
technical feasibility, architectural boundaries, and engineering constraints,
then explicitly approves a resulting Mission for Engineering. After execution,
Architecture Review assesses Repository Truth and Execution Evidence and may
create an advisory Mission Recommendation for the Portfolio. Neither review
creates a Mission automatically. The Architecture Advisor may assist with
evidence-grounded analysis but neither approves work nor performs engineering.

## Findings and opportunities

`ArchitecturalFindingCategory` is deliberately closed to: missing
architecture; missing capability; architectural inconsistency; repository
drift; knowledge gap; governance gap; and documentation gap.

An `ArchitecturalFinding` retains its assessment, evidence references, and
affected capabilities. An `ArchitecturalOpportunity` groups one or more
findings into a possible improvement and records its capability and roadmap
impact. It has no engineering authority.

## Evaluation and proposal handoff

An `ArchitecturalEvaluation` must address every declared criterion, without a
score or algorithm: constitutional compliance, architecture alignment,
capability impact, knowledge impact, engineering value, complexity, and
dependencies. It records a human-readable conclusion and constitutional
references; it does not calculate a recommendation.

The opportunity dispositions are `IDENTIFIED`, `ACCEPTED_FOR_PROPOSAL`, and
`DECLINED`. `ACCEPTED_FOR_PROPOSAL` is a narrowly defined human architectural
review decision. It is not an approval of engineering, an Engineering Proposal
status, an Engineering Intent approval, or a Runtime authorization. It requires
a durable human decision reference.

Only an accepted opportunity can produce an `EngineeringProposalHandoff`. The
pure handoff preserves source finding identifiers, the evaluation, capability
impact, roadmap impact, and decision reference. It does not create an
`EngineeringProposal`; the existing Engineering Proposal process supplies that
separate governed artifact. That proposal can then be used by the established
[Engineering Intent Authoring](engineering-intent-authoring.md) path.

## Constitutional, knowledge, and provider relationships

Architecture Reasoning applies repository-first evidence (Article 1), the
canonical Engineering Intent boundary (Article 3), human governance (Article
5), evidence-first engineering (Article 6), capability-first evolution
(Article 7), and repository-owned knowledge (Article 8). The Constitution is
authoritative: an assessment or evaluation cannot reinterpret it.

Knowledge remains the reviewed input to reasoning. Reasoning adds the explicit
architectural evaluation needed before a proposal; it does not replace the
Knowledge Model, Constitutional Validation, Engineering Planning, Proposal
generation, or Intent authoring.

A future AI Architect Provider may assist a human by preparing declared
assessments, findings, opportunities, or evaluations using these same
provider-independent contracts. It must remain evidence-grounded and human
governed. It cannot silently infer authority, accept an opportunity, generate
an approved proposal, author an Intent, or invoke a Runtime. Its abstraction is
the next separately bounded increment.

## Next boundary

Forge Phase B — Increment 1.6 — AI Architect Provider Abstraction should
define a provider-independent interface for proposing Architecture Reasoning
records while preserving human acceptance, deterministic traceability, and the
strict non-executing boundary.
