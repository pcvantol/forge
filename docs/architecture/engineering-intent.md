# Forge Engineering Intent Architecture 0.8

## Canonical engineering instruction

An **Engineering Intent** is Forge's canonical, model-independent engineering
artefact. It is the durable statement of what bounded engineering work means,
before any execution runtime represents that work in its own format.

Every Engineering Intent describes these required concerns:

- context;
- goal;
- architecture decisions;
- scope;
- constraints;
- deliverables;
- validation; and
- expected evidence.

This is an architectural domain definition, not a storage contract or a
runtime capability. Forge 0.8 introduces no parser, generator, persistence
model, execution pipeline, or provider integration.

## Relationships and authority

| Concept | Relationship to Engineering Intent | Authority boundary |
| --- | --- | --- |
| Vision | Informs the enduring product outcome that an intent serves. | Vision does not execute or replace a bounded intent. |
| Roadmap | Sequences and frames the intended direction that can lead to an intent. | A roadmap does not itself authorize work. |
| Backlog | Prioritizes candidate work from which an intent may be formed. | Backlog priority is not an engineering instruction or approval. |
| Engineering Proposal | Bounds and justifies a candidate intent with rationale, dependencies, risk, and traceable evidence. | A proposal remains governed input; it does not replace the canonical intent. |
| Approval | Authorizes progression according to governance. | Approval changes no intent content and does not make a prompt canonical. |
| Repository | Provides the target repository and its observable reality. | Repository reality is used to evaluate the intent; a repository does not redefine the intent. |
| Runtime Provider | May consume a derived Runtime Prompt to perform work. | A provider is an execution consumer, never the source of truth for the intent. |
| Evidence | Validates whether the repository reality and outcomes satisfy the intent. | Evidence supports verification; it neither rewrites intent nor grants approval. |

## Runtime Prompt and drift

A **Runtime Prompt** is a temporary, provider-specific execution artefact
derived from an Engineering Intent. Examples include representations for Codex
CLI, Claude Code, Gemini CLI, and future Runtime Providers. A Runtime Prompt
is not a canonical source of truth and must not be used to determine what the
engineering work means.

Repository Drift is determined by comparing Engineering Intent with Repository
Reality. It is not determined by comparing a Runtime Prompt with repository
content. This keeps drift assessment stable when prompts, providers, or
provider rendering conventions change.

## Bootstrap continuity

Existing bootstrap prompts are predecessors of Engineering Intents. A later,
separately bounded bootstrap capability may reconstruct and migrate them. Forge
0.8 performs no such migration and does not change bootstrap functionality.
