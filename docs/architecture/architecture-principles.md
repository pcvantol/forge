# Forge Architecture Principles

## Purpose and authority

The [Forge Constitution](../../knowledge/bootstrap/01_CONSTITUTION.md) is the
canonical constitutional statement of Forge's permanent engineering
principles. This document elaborates those principles through architecture
concepts; it and other detailed architecture documents must remain consistent
with the Constitution.

## Principles

### Workspace-first product understanding

A Workspace represents the software product. It establishes product identity,
operating context, and the catalog of repositories that contribute to that
product. A Workspace is not a repository and does not execute engineering
work. See [Workspace Model](workspace-foundation.md).

### Repository-first engineering

Repositories implement engineering and remain the engineering source of truth.
Repository evidence is authoritative when assessing repository reality and
outcomes. It overrides reviewer observations, prompt history, and other
non-repository accounts that conflict with observable repository evidence.
This authority evaluates an Engineering Intent; it does not silently rewrite
the intent itself. See [Repository Model](repository-model.md).

### Engineering Intent is canonical

Engineering Intent is the canonical, model-independent artifact for bounded
engineering work. It records the objective, architecture decisions, rationale,
scope, constraints, validation, and expected evidence. Governance may approve
progression, but approval does not turn a provider instruction into the
canonical record. See [Engineering Intent](engineering-intent.md).

### Runtime prompts are derived and transient

Prompt Generators derive runtime-specific prompts from approved Engineering
Intents for systems such as Codex CLI, Claude Code, and Gemini CLI. A Runtime
Provider consumes the intent-derived representation; it never owns or
redefines the intent. Runtime Prompts are transient execution artifacts, not
canonical engineering records. The retained Prompt Artifact is transitional
bootstrap compatibility, not an alternative authority.

### Human governance is explicit

Human governance controls approval, authority, and progression between
engineering stages. Declarative lifecycle labels, generated artifacts, and
runtime availability do not independently authorize work. See [Governance
Model](governance-model.md).

### Capability-driven architecture

Forge grows through bounded capabilities with explicit responsibility and
non-goals. A capability is not implemented merely because its concept is
documented. Future Runtime Providers, execution, queues, Studio, and other
features require separately governed capabilities.

### Execution modes are explicit

Execution context is selected explicitly rather than inferred from a runtime
name. Engineering Platform 1.5 is the temporary bootstrap execution host;
Forge consumes that host through stable execution contracts and has no runtime
coupling to it. Genesis Mode is the bootstrap execution profile. Other modes
may be introduced only through explicit capability and governance decisions.

### Readiness is composable

Workspace Readiness is a generic Forge capability. It evaluates whether the
workspace is prepared for a declared execution profile. Genesis Readiness and
Managed Readiness are profiles of that capability, rather than separate
products. Future capabilities may contribute additional readiness checks under
the same assessment model. See [Workspace Readiness](workspace-readiness.md).

### Phase completion is evidence-based

An engineering phase completes only when declared criteria have reproducible
evidence and an assessment reaches `COMPLETE`. Engineering success alone,
human opinion alone, or a closure statement alone is insufficient. See [Phase
Completion Framework](phase-completion-framework.md).

### Architecture drift compares intent and reality

Architecture Drift is determined by comparing Engineering Intent with
Repository Reality. Prompt history is not authoritative for that comparison,
because prompt renderings and runtime conventions are derived and may change.

### Product identity is a capability

Product Identity is a Forge capability. Bootstrap repositories may use
temporary working names until a separately governed capability establishes
public branding. Runtime names are execution details, not architectural
concepts.
