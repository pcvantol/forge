# Forge Codex CLI Runtime Prompt Rendering Report 001

## Scope

Phase C — Increment 3.3 implements the deterministic, non-executing Codex CLI
Runtime Prompt Renderer, its immutable model, compatibility metadata,
correlation model, documentation, and regression coverage.

## Findings

- Runtime Prompts differ from Missions: a Mission is a governed strategic
  contract; a Runtime Prompt is a transient presentation of one active Action.
- Runtime Prompts differ from Engineering Intents: an Intent preserves tactical
  planning meaning; the prompt preserves only the Intent identity and exact
  Action-bound execution context.
- Rendering is deterministic because all source data is immutable and supplied
  by the caller, unordered collections are normalized, identities are digest
  derived, and no clock or external state is read by the renderer.
- Capability Preflight consumes the explicit Execution Host Contract version,
  execution mode, required capabilities, and minimum runtime from prompt
  compatibility metadata before host delivery.
- Execution Hosts consume Runtime Prompts rather than Mission documents so
  operational execution cannot reinterpret planning or governance authority.

## Validation

Focused regression coverage exercises deterministic identical-input rendering,
single active Action rendering, Mission boundary preservation, Intent and
Action provenance preservation, prompt versioning, compatibility metadata,
correlation identity, and immutability. No AI provider invocation or Codex
execution occurs.

## Recommended next increment

Implement the **Bootstrap Execution Host Adapter**. It shall translate Codex
CLI Runtime Prompts into Engineering Platform 1.5 Inbox transactions while
preserving Execution Host independence.
