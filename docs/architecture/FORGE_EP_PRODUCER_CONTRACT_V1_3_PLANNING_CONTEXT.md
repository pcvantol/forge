# Forge EP producer contract v1.3 planning context

Decision: `FORGE_EP_PRODUCER_CONTRACT_V1_3_PLANNING_CONTEXT`.

This document extends the prospective Forge-to-EP provenance envelope. It
does not change the EP producer-readback contract (`v1.2`), terminal-evidence
contract (`v1.2`), or the respective product authorities.

## Boundary and versioning

A new Forge submission uses
`constraints.forge_execution.contract_version: "1.3"`. It retains the v1.2
redacted Action Context Envelope and adds a distinct
`planning_context_envelope`, at envelope version `1.0`.

The planning envelope is immutable and digest-bound. Its identity must agree
with the enclosing Forge provenance for Mission/revision, Intent/revision and
Engineering Action. Forge persists the exact Producer Contract before any
transport request, and EP reflects the exact same envelope in readback and
terminal evidence. A mismatched or malformed copy fails closed.

The envelope contains only these bounded Forge planning facts when they were
actually supplied by the canonical Forge Mission state:

- Mission title;
- redacted business and engineering summaries;
- Forge Mission lifecycle snapshot at submission time;
- one opaque decision-evidence reference plus its digest.

It also contains the immutable Mission, Intent and Action identifiers,
`envelope_version`, and `envelope_digest`. Text is normalized, capped and
credential-redacted before it can leave Forge. The evidence reference accepts
only an opaque identifier vocabulary; no decision content, rationale,
alternatives or prompt text is sent.

Absent values stay absent. Forge does not derive display defaults, does not
copy a mutable runtime projection, and does not turn an EP receipt into Forge
submission provenance.

## Three separate fact families

CENTRAL/EP must project these families separately:

| Family | Owner | Examples |
| --- | --- | --- |
| Forge submission provenance | Forge, immutable at submission | producer/version, Mission/Intent/Action identity, safe Action Context and Planning Context envelopes |
| EP runtime facts | EP | execution phase, dispatcher status, start/update timestamps and execution host |
| returned evidence and receipts | EP, read by Forge | submission acceptance receipt, terminal receipt, report and execution evidence references |

The EP acceptance receipt confirms only that the submission was admitted and
binds Forge/EP versions plus the accepted-request digest. It is not an
execution receipt. A terminal evidence reference cannot exist at initial
submission, and must only appear after an EP terminal run returns it.

## Historical compatibility and rollout

EP continues to read v1.0/v1.1 provenance and v1.2 Action Context envelopes
without inventing new fields. Only future v1.3 submissions carry the planning
envelope. Historical records remain unchanged and explicitly lack planning
context where it was not captured.

Roll out an EP build that validates and readbacks v1.3 before a Forge build
starts submitting it. Forge otherwise fails closed on the existing versioned
admission/readback boundary; it never falls back to an unversioned or partial
planning payload.
