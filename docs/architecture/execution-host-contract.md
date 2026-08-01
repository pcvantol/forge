# Execution Host Contract 2.3

## Purpose

An **Execution Host** is a replaceable operational implementation that
performs bounded engineering execution after Forge has completed its reasoning.
Forge owns engineering reasoning; an Execution Host owns execution operations
and returns evidence. Forge interprets that evidence against its Constitution,
Architecture, Mission, Engineering Intent, and Engineering Action.

This contract establishes an abstraction only. It does not implement an
Execution Host, Forge Runtime, Runtime Provider, queue, transport, Studio, or
repository operation.

## Canonical execution contract

```text
Engineering Intent
  → Engineering Action
  → Runtime Prompt
  → Execution Host
  → Execution Runtime
  → Repository
  → Evidence
  → Forge
```

Engineering Action is deliberately retained between Intent and Runtime Prompt:
it is Forge's smallest intentional executable unit. A Runtime Prompt is a
transient provider-specific representation of that Action. The Host receives
the prompt as an execution artifact, rather than as architecture or authority.

## Responsibilities and boundaries

| Execution Host owns | Execution Host never owns |
| --- | --- |
| Execution; prompt delivery; runtime invocation; checkpoints; reports; logs; observability; retries; cleanup; qualification; execution evidence. | Architecture; engineering knowledge; Engineering Intent; roadmap; capability evolution; governance. |

A Host may report execution outcomes and repository observations. It must not
interpret evidence as architectural truth, change an Action or Intent, approve
work, determine governance, or redefine Forge knowledge.

## Lifecycle

The host-owned lifecycle is:

```text
Qualified → Prompt received → Prompt delivered → Runtime invoked
  → Checkpoint recorded → Evidence collected → Evidence returned → Cleaned up
```

Hosts may implement operational retry and failure mechanics internally, but
must retain checkpoints, reports, and the final evidence appropriate to their
execution. Qualification is host-specific: a Host qualifies itself and returns
qualification evidence. Forge consumes that evidence; it does not operate
host qualification or execution telemetry.

## Dispatch and evidence correlation

The typed boundary consists of `ExecutionRequest`, `ExecutionDispatch`,
`ExecutionHostEvidence`, and the `ExecutionHost` protocol. A request carries
the requested host, Mission, Intent revision, Engineering Action, Runtime
Prompt, workspace, repository, correlation identity, dispatch timestamp, and
optional retry predecessor. Dispatch returns the immutable host run identifier.

Dispatch is correlation-idempotent. `recover_dispatch(request)` returns the
original immutable acknowledgement for an accepted request correlation, or
`None` when the host has not accepted it. This allows the Bootstrap Mission
Runner to persist a request before dispatch and resume after a crash without
reconstructing state from a report or relying on host-adapter process memory.

Every terminal evidence envelope and repository observation repeats the exact
correlation identity and host run identity, plus Mission, Intent revision,
Action, Runtime Prompt, repository, report, and retry relationship. Forge must
reject evidence that does not match the exact dispatch. This makes stale,
unrelated, generic-latest, and retry-predecessor evidence ineligible for
Mission progression.

## Evidence and observability

Every returned evidence envelope identifies the Host, correlation, host run,
report, outcome, and repository observation. Repository evidence identifies
the Mission, Intent revision, Action, Runtime Prompt, correlation, host run,
repository, observed repository revision, report, and a SHA-256 content digest.
This preserves provenance without granting a Host authority to interpret it.

Hosts own logs, reports, runtime diagnostics, and execution metrics. The
envelope carries references to these host-owned artifacts. Forge consumes the
references and repository evidence; Forge does not own execution telemetry.

## Transport

Transport belongs to the Execution Host. An iCloud Inbox, queue, or future API
is a host implementation detail and never part of Forge engineering knowledge.
Transport delivers a Runtime Prompt and returns host evidence; it does not
become a Mission Planner, an Architecture authority, or a Repository actor.

## Relationships

- **Engineering Intent and Engineering Action:** Forge-owned reasoning and
  planning records. A Host consumes neither as mutable authority; it executes
  the Runtime Prompt derived from an Action.
- **Runtime Providers:** future prompt/runtime consumers that are distinct from
  Host operations. A Provider does not acquire Host transport, retry,
  observability, qualification, or evidence responsibilities merely by
  consuming a prompt.
- **AI Architect Providers:** advisory reasoning providers. They return
  candidates to Forge and never execute engineering or become an Execution
  Host.
- **Forge Runtime:** a future Forge coordinator, not an Execution Host. It may
  coordinate Forge-owned reasoning but may not absorb host operational
  responsibility.

## Reference implementation and future hosts

Engineering Platform 1.5 is the first replaceable reference implementation of
this contract during Forge bootstrap. Its Bootstrap adapter is the sole place
where Inbox, report, polling, local status, and retry transport details may
exist. Scheduler core has no runtime dependency on that implementation.

Future replaceable hosts may include Engineering Platform, Forge Local Host,
Forge Cloud Host, GitHub Actions Host, and Enterprise Host. They are examples
of this abstraction, not implementations authorized by this increment.

## Repository structure

`forge/models/execution_host.py` holds immutable contract and evidence
envelopes only. It performs no I/O, execution, transport, runtime invocation,
repository mutation, telemetry collection, or qualification.

## Out of scope

No Engineering Platform, Codex, Claude, Gemini, Execution, Queue, Studio, or
concrete Host is implemented here. The Bootstrap Mission Runner consumes this
contract separately; it does not alter Host ownership.
