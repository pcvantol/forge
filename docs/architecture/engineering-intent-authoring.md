# Forge Engineering Intent Authoring 1.4

## Purpose and boundary

This document is the canonical authoring contract for future Forge Engineering
Intents. It establishes how repository-held knowledge becomes a bounded,
provider-independent Intent. It does not author an Intent, reconstruct a
bootstrap Intent, generate a runtime prompt, invoke a Runtime Provider,
perform AI reasoning, operate a repository, or execute work.

The original bootstrap conversations are historical provenance only. They are
not required authoring input and cannot originate an Engineering Intent.

## Canonical authoring path

```text
Repository Knowledge
  ↓
Architecture Context
  ↓
Roadmap Context
  ↓
Engineering History
  ↓
Engineering Intent
```

Repository Knowledge supplies the reviewed baseline. Architecture Context
interprets it against the Constitution and Founding Architecture Handbook.
Roadmap Context establishes the relevant direction without granting authority.
Engineering History prevents duplicate, contradictory, or superseded work.
Together these inputs prepare a candidate Engineering Intent; they do not
approve or execute it.

## Required authoring context

Every authoring context declares versioned, immutable references to all of:

- Constitution;
- Architecture Handbook;
- Roadmap;
- existing Engineering Intents;
- Repository Evidence;
- Capability Catalogue; and
- Knowledge Model.

The local `EngineeringIntentAuthoringContext` contract validates those source
classes deterministically. It also requires the candidate's objective,
rationale, affected capabilities, architecture references, expected evidence,
and validation. Applicable constitutional articles are captured as explicit
references; when no article applies, that absence remains an intentional,
reviewable declaration rather than an inferred result.

References retain their identity, version, and locator. The contract canonicalizes
their order for stable serialization. It performs no reading, retrieval,
inference, or mutation, so producing the same declared context yields the same
provider-independent representation.

## Traceability and constitutional relationship

Authoring implements the Constitution's repository-first, Engineering Intent,
runtime-independence, human-governance, evidence-first, and capability-first
principles. Repository Evidence establishes repository reality; the Handbook
does not replace constitutional authority; the Roadmap does not imply approval;
and existing Intents inform history without being silently overwritten.

The result must be sufficient to author an Intent that explains why the work is
needed, what capabilities it affects, which architecture and constitutional
constraints govern it, and how repository evidence and validation will assess
it. Human governance and the [Engineering Intent Lifecycle](engineering-intent-lifecycle.md)
continue to govern the Intent after it is authored.

## Runtime Provider boundary

```text
Engineering Intent
  ↓
Runtime Provider
  ↓
Runtime Prompt
  ↓
Execution
```

Engineering Intent remains Forge-owned and provider-independent. A future
Runtime Provider owns prompt generation only: it renders a transient,
provider-specific Runtime Prompt from an eligible Intent. The provider neither
authors, reinterprets, approves, nor changes canonical Intent meaning.
Execution remains outside this authoring model.

## Future evolution already established

Architecture Steward, Knowledge Distillation, Knowledge Reconciliation, and
Capability Evolution may later supply reviewed repository knowledge or assess
its evolution. They do not bypass this authoring path, become runtime prompt
generation, or make an Intent self-authorizing. Their existing conceptual
boundaries remain unchanged.

## Next boundary

The next increment should define Runtime Provider contracts: provider inputs,
derived Runtime Prompt outputs, determinism and traceability boundaries, while
preserving the authoring model and excluding execution.
