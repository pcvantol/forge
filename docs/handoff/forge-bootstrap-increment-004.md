# Forge Bootstrap Increment 004 Handoff

## Implemented capability

Forge Knowledge Consumption Foundation 0.4 provides a local registry for
versioned, read-only Knowledge Source declarations and a deterministic,
metadata-only evidence-reference interface. Source declarations now carry
version, reference, access mode, trust classification, and lifecycle state.

## Changed files

- `forge/models/foundation.py` and `forge/models/__init__.py`: additive
  knowledge contracts and enums.
- `forge/knowledge/registry.py` and `forge/knowledge/consumer.py`: local
  registry and read-only deterministic consumer.
- `schemas/knowledge-source-0.4.schema.json`: standalone 0.4 contract.
- `tests/test_knowledge_consumption.py` and `tests/test_schemas.py`: coverage
  for registration, invalid source rejection, read-only behavior, schema
  requirements, and deterministic retrieval.
- `README.md` and `docs/architecture/knowledge-consumption.md`: lifecycle,
  authority, read-only boundary, and future Architect Provider direction.

## Architecture decisions

- The registry owns only Forge's local source declarations; it never writes to
  or retrieves from an external source.
- Certified sources are authoritative by declaration. Other classifications
  remain traceable evidence, not automatically authoritative knowledge.
- The initial consumer matches declaration metadata only and returns a stable
  evidence reference with version, trust, and lifecycle metadata.
- The 0.4 schema is additive, leaving Foundation Document 0.3 loading
  compatible with its established 0.2 component schema contract.

## Limitations

- There is no content extraction, repository inspection, remote retrieval,
  semantic retrieval, LLM integration, runtime, agent, or write access.
- Source lifecycle and authority are declared metadata; this increment does
  not certify sources or verify their referenced content.

## Recommended next increment

Define a governed Architect Provider contract for explicit, read-only retrieval
adapters and source-backed evidence selection while retaining source identity,
version, authority, lifecycle, determinism, and human governance.
