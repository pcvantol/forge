# Producer Contract 1.0

## Canonical boundary

**Forge owns the Producer Contract. Execution Hosts consume the Producer
Contract.** It is the canonical integration boundary between planning and
execution. A compliant Execution Host executes an Engineering Action without
depending on Forge implementation details.

```text
Mission → Producer → Execution Host Contract → Execution Host → Execution Evidence
```

A Producer is the upstream planning authority. Its identity is immutable and
traceable, but identity never changes Host execution semantics.

## Producer model

`ProducerIdentity` contains a stable ID, an extensible uppercase type, and a
version. Forge defines `HUMAN`, `FORGE`, `EXTERNAL`, and `UNKNOWN`; a compliant
consumer must preserve an unknown valid type rather than reject it. `Producer`
is an immutable identity plus contract version.

The Producer owns Mission, Mission Planning, Engineering Intents, Engineering
Actions, Runtime Prompt generation, Execution Policy, and Decision Evidence.
It never owns execution, execution evidence, execution receipts, reports, or
telemetry.

## Envelope

`ProducerContract` is immutable and versioned. It contains:

- Producer identity and contract version;
- correlation ID, optional Mission ID, and Engineering Action ID;
- a host-neutral `RuntimePromptEnvelope` with format, content, and digest;
- execution constraints and deterministic execution metadata;
- where Forge submits to EP, a separate Forge Action Context Envelope; and
- references to Host-owned receipts and execution evidence when they exist.

Receipts and evidence references are carried solely for traceability. They
remain owned and authored by the Execution Host. The envelope contains no
Forge classes, planning implementation, host transport, provider, or renderer
dependency.

## Forge Action Context Envelope 1.0

The complete Runtime Prompt is an Execution Host input and is never a Console
projection. For a Forge-to-EP submission, Forge additionally derives one
bounded Action Context Envelope from the immutable Action objective. The
envelope contains only:

- the Action ID;
- a whitespace-normalized, credential-redacted Action summary (maximum 500
  characters);
- the source Runtime-Prompt-generation digest;
- a deterministic generator ID, model label and generator version;
- a digest of the summary and a digest of the entire envelope.

The current generator is explicitly labelled
forge-redacted-action-summary / deterministic-template / 1.0. It is not
represented as an AI model: this avoids attributing generated reasoning where
the implementation is a deterministic safety-preserving projection.

The EP HTTP adapter transmits this document only in Forge provenance contract
1.2, records the envelope digest in Forge's immutable exchange audit, and
requires exact readback. EP/CENTRAL may display the separately persisted
summary and generator/digest metadata, but must not derive a replacement
summary from a Runtime Prompt, Forge's mutable execution context, or a current
Mission projection.

EP stores this envelope prospectively as immutable Central evidence. Runs
submitted before provenance 1.2 remain explicitly unavailable in the EP
Console; they are never backfilled.

## Lifecycle and relationships

Forge plans a Mission into Engineering Intents and Actions, derives a Runtime
Prompt, and presents one Producer Contract to a Host. The Host acknowledges
and executes it, then returns host-owned receipts and execution evidence.
Forge may interpret returned evidence as Decision Evidence but does not become
the execution-evidence authority. Repository Truth remains independent
architectural evidence; it is not reclassified as Host telemetry.

Every Runtime Prompt carries Producer identity, correlation ID, optional
Mission ID, Engineering Action identity, execution constraints, and execution
metadata. The legacy in-process Runtime Prompt forms are deterministically
bridged into this envelope by `ExecutionRequest`; this preserves compatibility
while making the Host-facing form canonical.

## Execution Host Contract

Hosts own execution, receipts, reports, telemetry, observability, and
execution evidence. Hosts never own Mission Planning, business or architecture
governance, Producer implementation, or Forge implementation. The host core
consumes `ExecutionRequest` and its `ProducerContract`; only a host adapter
may recognise a renderer or transport.

## Transitional DJConnect operation

Both operating paths remain valid without migration:

```text
Current: Human Architect → Engineering Prompt → Engineering Platform
Future:  Mission → Forge → Producer → Runtime Prompt → Engineering Platform
```

Engineering Platform's authenticated adapter is the sole transport mapping.
It validates and stores the prospective Action Context Envelope separately from
the Runtime Prompt and retains its execution/evidence ownership.

## Future hosts

Engineering Platform, a future Cloud Execution Host, and a future Enterprise
Execution Host may consume the same Producer Contract. Their transport,
qualification, runtime, receipts, reports, and telemetry remain independent
implementations.

## Repository structure

`forge/models/producer.py` is the canonical, dependency-free Producer model
and contract. `forge/models/execution_host.py` contains the host-neutral Host
boundary and deliberately imports no renderer. `forge/scheduler/adapter.py`
is the only current Engineering Platform-aware mapping.

## Out of scope

This increment does not make EP a Forge planning authority, expose raw Runtime
Prompt text in the Console, generate an AI-authored Action summary, backfill
historical executions, or change Host execution/evidence semantics.
