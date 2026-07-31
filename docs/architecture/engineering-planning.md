# Forge Engineering Planning Foundation 0.5

## Knowledge and planning

Knowledge Sources remain external, read-only evidence providers. Engineering
Planning does not retrieve, copy, summarize, or certify source content. Goals,
increment proposals, and plans hold typed `EvidenceReference` values that
preserve source identity, version, reference, and location so a human can
trace why intended work exists.

Evidence may point to a registered Knowledge Source, an evidence record, an
architecture document, or a foundation document. When configured with known
Knowledge Source identities, the local planning loader rejects an unknown
knowledge-source reference. Other reference kinds remain traceable document
pointers; 0.5 does not inspect their content.

## Proposal lifecycle

An Engineering Goal describes a desired workspace outcome. An Engineering
Increment Proposal links to that goal and records its bounded scope, expected
outcome, affected capabilities, dependencies, risk, rationale, and evidence.
An Engineering Plan orders proposals, states plan dependencies and assumptions,
and is either `draft` or `proposed`.

Neither status is approval. Planning records are intentionally declarative and
cannot modify a repository, invoke a tool, create a commit, or bypass
governance. Approval and execution require future, separately governed
capabilities.

## Local persistence and future Architect Provider boundary

`PlanningRegistry` stores one validated planning document in deterministic,
human-readable local JSON. The registry owns only Forge's local declarations;
it does not access referenced sources.

A future Architect Provider may propose or help assemble planning records only
through an explicit governed boundary. It must retain the evidence references,
human review requirement, deterministic validation, and the separation between
planning and execution established here.
