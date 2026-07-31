# Forge Knowledge Consumption 0.4

## Lifecycle and authority

A Knowledge Source is an external, versioned evidence provider. A source is
registered locally with its identity, type, location, version, reference,
trust classification, and lifecycle state. Forge never clones, refreshes,
edits, or otherwise operates on the source.

`certified` sources are authoritative for the governed knowledge they declare.
`reference` and `unverified` sources can provide traceable context but do not
become authoritative merely by registration. Generated Forge output is not a
Knowledge Source and does not become knowledge automatically.

Source lifecycle is declarative: `available`, `deprecated`, or `retired`.
Every query result preserves that lifecycle and the source version/reference so
a human can judge evidence currency and authority.

## Read-only boundary

The registry persists Forge's own source declarations in local JSON. This does
not grant access to the referenced location. The initial consumer performs
deterministic matching against the declaration's identity and metadata only;
it does not extract content, retrieve remotely, use an LLM, or apply semantic
search. Its output is an evidence reference, not a generated answer.

## Knowledge Base relationship and future direction

A governed Knowledge Base may be represented by any generic source type; it
is not hardcoded into Forge. Forge consumes declared evidence while the source
owner retains authority and all write control. A future Architect Provider can
add explicitly governed retrieval adapters and synthesis only after preserving
this source identity, version, trust, lifecycle, and read-only boundary.
