# Forge Engineering Intent Architecture 0.8

## Canonical engineering instruction

An **Engineering Intent** is Forge's canonical, model-independent dynamic
planning artefact. The Mission Planner creates it during an Architect-approved
Mission to state what coherent bounded engineering work means before any
execution runtime represents that work in its own format.

Every Engineering Intent describes these required concerns:

- context;
- goal;
- architecture decisions;
- scope;
- constraints;
- deliverables;
- validation; and
- expected evidence.

An Intent contains one or more Engineering Actions. The Intent is tactical: it
owns the rationale, boundaries, validation, evidence, and architectural
traceability for that coherent work. It is not directly executable, and it
does not generate a Runtime Prompt directly. Active Intents may be created,
superseded, merged, split, or disappear as repository evidence changes the
Mission Planner's plan; historical Intents remain immutable.

This is an architectural domain definition, not a storage contract or a
runtime capability. Forge 0.8 introduced no parser, generator, persistence
model, execution pipeline, or provider integration. The separately bounded
[Engineering Intent Lifecycle 1.2](engineering-intent-lifecycle.md) now adds
immutable local lifecycle contracts, but still introduces no persistence,
provider integration, or execution pipeline.

## Relationships and authority

| Concept | Relationship to Engineering Intent | Authority boundary |
| --- | --- | --- |
| Mission | Supplies the Architect-approved objective, boundaries, success criteria, and constitutional constraints. | Mission does not prescribe individual Intents. |
| Mission Planner | Creates and reconciles dynamic Intents from repository evidence. | It does not replace human governance or execute work. |
| Vision | Informs the enduring product outcome that an intent serves. | Vision does not execute or replace a bounded intent. |
| Roadmap | Sequences and frames the intended direction that can lead to an intent. | A roadmap does not itself authorize work. |
| Backlog | Prioritizes candidate work from which an intent may be formed. | Backlog priority is not an engineering instruction or approval. |
| Engineering Proposal | Bounds and justifies a candidate intent with rationale, dependencies, risk, and traceable evidence. | A proposal remains governed input; it does not replace the canonical intent. |
| Approval | Authorizes progression according to governance. | Approval changes no intent content and does not make a prompt canonical. |
| Repository | Provides the target repository and its observable reality. | Repository reality is used to evaluate the intent; a repository does not redefine the intent. |
| Runtime Provider | May consume a derived Runtime Prompt to perform work. | A provider is an execution consumer, never the source of truth for the intent. |
| Evidence | Validates whether the repository reality and outcomes satisfy the intent. | Evidence supports verification; it neither rewrites intent nor grants approval. |
| Engineering Action | Is the smallest intentional engineering unit contained by the Intent. | An Action cannot expand or replace its Intent. |

## Runtime Prompt and drift

A **Runtime Prompt** is a temporary, provider-specific execution artefact
produced by an Engineering Action. Examples include representations for Codex
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
Lifecycle 1.2 also performs no migration; its successor migration capability
must preserve this distinction.

The later Engineering Action reconciliation corrects the historical
Intent-to-prompt shortcut without changing those delivered records: an Action
now provides the canonical handoff from Intent to Runtime Prompt. See
[Engineering Action Architecture 1.11](engineering-action.md).
