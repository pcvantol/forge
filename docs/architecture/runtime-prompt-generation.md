# Runtime Prompt Generation 1.9

## Purpose

Runtime Prompt Generation derives a transient, provider-specific execution
artifact from one approved Engineering Intent and complete versioned context.
It establishes prompt generation only. It does not invoke a Runtime Provider,
execute a prompt, operate a repository, queue work, or replace an Execution
Host.

Engineering Intent remains the canonical, model-independent record of bounded
engineering work. A Runtime Prompt is derived representation, never canonical
engineering knowledge and never an input for Engineering Intent authoring,
approval, or repository-drift assessment.

## Transformation

```text
Approved Engineering Intent + Repository Context + Architecture Handbook
+ Constitution + Workspace Context + Capability Context
                         ↓
                  Prompt Generator
                         ↓
                  Runtime Prompt
```

The generation request is immutable. It records the approved source Intent,
the Provider Prompt Definition identity and version, each versioned context
reference, and declared constraints, validation, and deliverables. The output
retains the source Intent id/revision and a stable digest of that complete
request. Identical requests therefore produce identical abstract Runtime
Prompts.

## Canonical structure

Every Runtime Prompt retains these abstract sections:

- **Context** — architecture handbook, Constitution, workspace, and capability
  references that bound the work.
- **Objective** — the source Intent's objective.
- **Repository** — the declared repository context.
- **Constraints** — non-negotiable boundaries for the work.
- **Validation** — required checks or evidence expectations.
- **Deliverables** — the expected outcomes.

The structure is intentionally abstract. Section names are Forge's stable
intermediate representation; no Codex, Claude, Gemini, or Local LLM wording
is prescribed by this increment.

## Lifecycle and ownership

Forge owns the source Intent, the generation request, its provenance, and the
abstract generation contract. A Runtime Prompt is derived, provider-specific,
and transient: it may be regenerated from its recorded inputs and is not a
durable source of engineering meaning. Provider definitions own only the
rendering identity and version. Future Runtime Providers may consume a Runtime
Prompt, but cannot alter its source Intent or grant approval.

```text
Engineering Intent (canonical, human-approved)
  → Runtime Prompt Generation (Forge-owned derivation)
  → Runtime Prompt (provider-specific, transient)
  → Runtime Provider (future consumer)
  → Execution Host (external execution boundary)
  → Evidence
```

An Execution Host remains responsible for execution and evidence collection.
Engineering Platform 1.5 remains the temporary external execution host during
Forge bootstrap. This contract neither imports nor replaces it.

## Provider independence

The same approved Engineering Intent and declared context should eventually
produce a Codex Prompt, Claude Prompt, Gemini Prompt, or Local LLM Prompt.
Only the selected Prompt Generator and its Provider Prompt Definition change;
the Engineering Intent and canonical section semantics stay identical.

## Repository structure

The canonical locations are:

- `forge/prompts/generators/` for Prompt Generators;
- `forge/prompts/templates/` for provider-specific Prompt Templates; and
- `forge/prompts/provider_definitions/` for versioned Provider Prompt
  Definitions.

These locations are declared and documented in Increment 1.9. No concrete
provider implementation or template is present.

## Compatibility boundary

`EngineeringPromptArtifact` remains a compatibility-only bootstrap artifact
derived from an approved Engineering Proposal. It is provider-neutral and
does not become a Runtime Prompt input, source, or alias. Runtime Prompt
Generation instead derives from an approved Engineering Intent.

## Out of scope

This increment implements no OpenAI, Claude, Gemini, or Local LLM provider;
no concrete prompt template; no prompt execution; no queue; no Studio; no
Execution Host replacement; and no Engineering Platform replacement.
