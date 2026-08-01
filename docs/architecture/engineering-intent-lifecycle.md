# Forge Engineering Intent Lifecycle 1.2

## Purpose and boundary

This document is the canonical lifecycle contract for Forge Engineering
Intents. It makes the Intent lifecycle explicit, versioned, immutable, and
locally verifiable. The contract is implemented by dependency-free value types
and pure validation only. It does not create or migrate an Intent, persist a
record, retrieve evidence, grant approval, invoke a Runtime Provider, execute
work, operate a repository, or implement a queue or Studio.

An Engineering Intent remains the canonical, model-independent dynamic planning
artifact for one bounded engineering increment. The Mission Planner creates it
within an Architect-approved Mission. It is governed by the
[Constitution](../../knowledge/bootstrap/01_CONSTITUTION.md), interpreted by
the [Founding Architecture Handbook](FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md),
and assessed against repository reality rather than a Runtime Prompt.

## Versioned record

`EngineeringIntent` has a stable `id`, an immutable `revision`, title,
objective, one established category, mandatory traceability, typed
relationships, optional evidence, optional human approval metadata, and a
`1.2` schema version. The record is immutable. From `PROPOSED` onward its
meaning cannot change; a changed bounded objective requires a distinct Intent
or a later revision governed outside this lifecycle contract. A status
transition changes status only and retains the complete declared content.

The supported categories are deliberately closed to the categories already
established by Forge: `Assessment`, `Implementation`, `Repair`, `Migration`,
`Knowledge Capture`, `Architecture Authoring`, and `Reconciliation`.

## Lifecycle states and transitions

| State | Meaning | Permitted next state |
| --- | --- | --- |
| `DRAFT` | A human or governed Forge process is preparing a bounded Intent. It has no execution authority. | `PROPOSED`, `SUPERSEDED` |
| `PROPOSED` | The immutable Intent is offered for human governance review. | `APPROVED`, `SUPERSEDED` |
| `APPROVED` | A human approval record identifies the approver, time, and decision reference. Approval is metadata and does not execute work. | `IMPLEMENTED`, `SUPERSEDED` |
| `IMPLEMENTED` | Reproducible implementation evidence records that the declared work was implemented. It is not completion. | `VERIFIED`, `SUPERSEDED` |
| `VERIFIED` | Implementation, validation, and repository evidence establish the declared outcome against repository reality. | `ARCHIVED`, `SUPERSEDED` |
| `SUPERSEDED` | A distinct successor has explicitly replaced this Intent. It is terminal. | none |
| `ARCHIVED` | A verified historical Intent is retained without further lifecycle progression. It is terminal. | none |

The normal path is `DRAFT → PROPOSED → APPROVED → IMPLEMENTED → VERIFIED →
ARCHIVED`. Supersession is the only governed exception: a non-terminal Intent
may move to `SUPERSEDED` only when the complete local Intent set proves the
reciprocal replacement relation described below. There are no skipped normal
transitions and no transitions from terminal states.

The mission-driven architecture supersedes the historical assumption that
humans approve every Intent: humans approve Missions and remain responsible for
governance, while Forge's future Mission Planner creates and reconciles active
Intents from repository evidence. This existing lifecycle contract preserves
historical record semantics until a separately authorized migration. Neither a
status label, generated artifact, provider availability, nor execution output
is an approval or verification decision.

## Relationships and supersession

The supported typed relationships are `replaces`, `depends_on`, `supersedes`,
`implements`, and `derived_from`. Relationship targets must exist in the
declared local Intent set; self-references and duplicate kind-target pairs are
invalid.

Supersession is deliberately two-sided. The successor declares
`supersedes → predecessor`; the predecessor in `SUPERSEDED` declares
`replaces → successor`. The relationship validator requires both records and
both links. This prevents an Intent from silently becoming superseded merely
because its status was changed. Active planning may also merge, split, or
retire an Intent; those operations must preserve immutable historical records
and their evidence and are not implemented by this lifecycle contract.

## Evidence and traceability

`IntentEvidence` is an immutable reproducible pointer with source identity,
source version, locator, and SHA-256 content digest. Its only classifications
are `implementation`, `validation`, `repository`, and `architectural`.
`IMPLEMENTED` requires implementation evidence. `VERIFIED` and `ARCHIVED`
require implementation, validation, and repository evidence; repository
evidence remains authoritative for repository reality.

Every Intent has an `IntentTraceability` declaration with versioned references
for each stage of the required chain:

```text
Vision → Architecture → Roadmap → Mission → Mission Planner → Engineering Intent → Engineering Action → Runtime Prompt → Execution Host → Repository → Evidence → Mission Planner
```

The lifecycle model requires the first five source stages. Evidence is added as
the Intent progresses; verification requires repository and validation
evidence, which completes the trace to observable repository reality.

## Canonical repository layout

Future persisted Engineering Intent artifacts use this canonical layout:

```text
engineering/
  intents/
    active/
    completed/
    superseded/
    templates/
```

This increment documents the layout only. It creates no Intent artifacts,
does not create or migrate bootstrap records, and does not define persistence
or file-loading behavior.

## Constitutional relationships

The lifecycle applies the Constitution's repository-first, Intent-canonical,
human-governed, evidence-first, and capability-bound principles. Constitutional
Validation can assess declared architectural content, but it does not create,
approve, transition, or verify an Intent. Phase Completion can consume
reproducible evidence, but its completion status does not alter this lifecycle.
Engineering Actions may later derive a transient prompt from an Intent; they
never own its lifecycle or canonical meaning.

## Next boundary

Forge Phase B — Increment 1.3 — Bootstrap Intent Migration may separately
reconstruct eligible bootstrap work as immutable Intent artifacts under this
contract. It must not weaken the lifecycle or treat historical prompts as
canonical Intent records.
