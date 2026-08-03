# Codex CLI Runtime Prompt Renderer 3.3

## Purpose

The Codex CLI Runtime Prompt Renderer is Forge's canonical presentation
boundary for one released Engineering Action. It produces one immutable,
transient, execution-ready Codex CLI Runtime Prompt and does not plan,
schedule, transport, invoke Codex, or operate a repository.

```text
Mission → Engineering Intent → Engineering Action → Codex CLI Runtime Prompt
→ Execution Host
```

## Contract and boundaries

The renderer accepts a Mission, an approved Engineering Intent pinned by that
Mission, and exactly one active Engineering Action belonging to that Intent
revision. It rejects any action outside the Mission membership or without the
required lifecycle state. It never creates or changes a Mission, Intent, or
Action.

A Runtime Prompt is not a Mission: a Mission is the governed contract that
defines strategic objective and boundaries across its Intent memberships. A
Runtime Prompt is the temporary, provider-specific delivery representation of
one Action. A Runtime Prompt is not an Engineering Intent: the Intent remains
the tactical planning record; the prompt contains only the exact action
objective and execution-facing context needed by Codex CLI.

The prior 1.9 generic Runtime Prompt generator remains the provider-neutral
intermediate abstraction. This 3.3 renderer is a distinct Codex-specific
presentation layer and does not relabel or alter the generic contract.

## Rendered content

Every prompt contains Mission identity, objective, and in/out-of-scope
boundaries; Intent identity and tactical context; Action identity and
objective; repository id, revision, state digest, and capture timestamp;
constraints; expected validation; expected repository evidence; execution
mode; renderer and schema versions; Runtime Prompt and correlation identities;
and Execution Host compatibility metadata.

When Forge has selected an Agent Role and model policy, the renderer projects
only policy version, stable decision digest, and resulting execution
constraints. It does not expose Agent Role, Model Profile, Reasoning Profile,
or provider selection to the Execution Host. See the [Agent Role and Model
Selection Policy](agent-role-model-selection-policy.md).

Compatibility declares the Execution Host Contract version, execution mode,
required capabilities, and minimum supported runtime. Capability Preflight
consumes these declared fields before a host accepts delivery: it compares the
host contract and mode and verifies each required capability and runtime
minimum. The renderer does not implement or communicate with Capability
Preflight, keeping the renderer host-agnostic.

## Deterministic rendering

The caller supplies the immutable repository snapshot, including its capture
timestamp. The renderer reads no clock, environment, repository, network, or
provider state. It canonicalizes all unordered string collections by sorting
them, serializes source material as sorted-key compact JSON, derives the prompt
identity from that source digest, and derives the correlation identity from
the Mission, Intent, Action, and source digest. The rendered line ordering is
fixed. Therefore identical Mission, Intent, Action, repository state, and
rendering inputs produce byte-identical prompts.

## Relationships

- **Mission Planner:** owns dynamic Intent planning; it is not called by the
  renderer.
- **Mission Intake:** is a future source of approved Mission work and does not
  render prompts.
- **Execution Host:** consumes the rendered artifact, not Mission documents;
  this prevents execution operations from interpreting or modifying planning
  authority.
- **Bootstrap Execution Host Adapter:** translates this artifact into an
  Engineering Platform 1.5 Inbox transaction while preserving Forge's host
  independence; see [its contract](bootstrap-execution-host-adapter.md).
- **Capability Preflight:** consumes only the explicit compatibility metadata
  before delivery; it neither changes the prompt nor becomes a planner.

## Out of scope

No Mission Intake, Mission Planner, Execution Host Adapter implementation, Codex invocation,
Execution Host communication, repository operation, or engineering execution
is implemented here.
