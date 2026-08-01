# Forge Foundation Document Loader 0.3

## Purpose

The Foundation Document Loader gives Forge a deterministic, local-only way to
consume a complete declarative Foundation Document. It is a validation and
model-construction boundary, not an execution, AI, repository, or network
capability.

## Lifecycle

```text
Local Foundation JSON document
  -> document type and version detection
  -> packaged schema resolution
  -> structural and cross-reference validation
  -> immutable model construction
  -> deterministic validation report
```

Only Forge-packaged schemas in the loader allow-list may be resolved. A
document's `$schema` value is never followed, so loading cannot produce a
network request or trust an unapproved schema source.

## Contracts and models

JSON Schemas remain the versioned interchange contracts. The loader validates
the composite envelope and its Workspace, Repository, Repository Catalog,
Knowledge Source, Capability, Engineering Mode, and Governance Profile
declarations before constructing the corresponding immutable Python models.
Invalid input returns a validation report and cannot create runtime models.

## Validation evidence

`ValidationReport.to_text()` produces stable, human-readable evidence. It
records status, document path when loaded from a file, resolved schema,
constructed model families, error count, warnings, and actionable corrections
for failures. It does not include input values, credentials, or remote data.

## Evolution boundary

Future Forge runtime capabilities may consume validated models, but must not
reinterpret a Foundation Document or bypass this validation boundary. Any new
schema version requires explicit local schema registration, compatibility
documentation, and validation coverage. Repository operations and knowledge
source mutation remain outside this capability.
