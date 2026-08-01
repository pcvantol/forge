# Forge Engineering Action Architecture Reconciliation Report 001

## Scope

Forge Phase B — Architecture Correction introduces Engineering Action as the
canonical smallest intentional engineering unit. This reconciliation updates
the architecture rather than implementing Action storage, prompt generation,
scheduling, Runtime, providers, execution, or execution hosts.

## Reconciled decisions

- The canonical hierarchy is Vision → Architecture → Roadmap → Mission →
  Engineering Intent → Engineering Action → Runtime Prompt → Execution →
  Evidence.
- A Mission is strategic and owns objective, scope, progress, and Intent
  memberships; it is not executable.
- An Engineering Intent is tactical and owns rationale, boundaries,
  validation, evidence, and architectural traceability; it is not directly
  executable.
- An Engineering Action is the smallest intentional, executable unit and is
  the only canonical source that produces a Runtime Prompt.
- Runtime Prompts remain transient, provider-specific execution artifacts.
- The future Bootstrap Mission Scheduler releases Actions, not Intents.

## Historical reconciliation

Bootstrap and Phase B records that described an Intent as the direct prompt
source retain their delivery history, but the current canonical architecture
now places an Action between Intent and Runtime Prompt. No historical artifact
is migrated and no runtime contract is changed by this report.

## Validation

Focused architecture-consistency tests verify Mission-to-Intent containment,
Intent-to-Action containment, Action-to-Runtime-Prompt production, and the
provider-specific Runtime Prompt boundary. Repository-wide tests and
whitespace validation provide local Genesis evidence.

## Recommended next increment

Implement the Bootstrap Mission Scheduler using Engineering Actions, rather
than Engineering Intents, as its released executable unit.
