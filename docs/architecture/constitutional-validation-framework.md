# Forge Constitutional Validation Framework 1.1

## Purpose

Constitutional Validation is Forge's local conceptual model for determining
whether an architectural expression or a future Engineering Intent is
consistent with the [Forge Constitution](../../knowledge/bootstrap/01_CONSTITUTION.md).
It turns a declared, repository-driven architectural review into a stable
assessment without changing repository authority or performing enforcement.

The comparison is deliberately one-way:

```text
Repository Knowledge
        ↓
Constitution
        ↓
Assessment
```

Repository implementation and repository-held knowledge remain authoritative
for repository reality. A review report, an automated suggestion, or this
model's output cannot replace that evidence.

## Contracts

`ConstitutionalRule` represents one constitutional article by its canonical
article identity, title, description, rationale, and validation intent. It is
a declarative projection of the Constitution, not a replacement or editable
copy of it.

`ConstitutionalFinding` records one article-specific concern: the article,
severity (`WARNING` or `VIOLATION`), explanation, affected architectural
concept, and recommendation. A recommendation describes a possible next
review or reconciliation step; it does not authorize a modification.

`ConstitutionalAssessment` is immutable and contains a subject identity,
applicable rules, ordered findings, and one status:

| Status | Meaning |
| --- | --- |
| `PASS` | Applicable articles have no findings. |
| `WARNING` | Applicable articles have warnings and no violation. |
| `VIOLATION` | At least one applicable article has a violation. |
| `NOT_APPLICABLE` | No constitutional articles apply to the declared subject. |

`ConstitutionalAssessor` is a pure, local derivation boundary. It sorts rules
and findings by stable fields, rejects a finding for an inapplicable article,
and uses fixed precedence: no rules, then violation, then warning, then pass.
It does not read a repository, infer a rule, fetch evidence, invoke a Runtime
Provider, or modify anything.

## Architecture Handbook and Engineering Intent

The [Founding Architecture Handbook](FORGE_FOUNDING_ARCHITECTURE_HANDBOOK.md)
interprets repository-held architecture beneath the Constitution. Future
handbook authoring may use this framework to record whether a proposed or
reconciled architectural expression remains constitutionally consistent. The
assessment does not update the handbook or amend the Constitution.

Future Engineering Intents should explicitly identify the constitutional
articles that apply to their architectural decisions, constraints, expected
evidence, and validation. A future Intent-validation capability may construct
the input to this framework, but that capability is not implemented here. The
model neither stores Intents nor decides approval, lifecycle progression, or
execution.

## Related future capabilities

Constitutional Validation remains separate from the following concepts:

| Concept | Relationship | Not implemented by this framework |
| --- | --- | --- |
| Architecture Drift | May use a constitutional assessment alongside its Intent-to-Repository-Reality comparison. | Drift detection, evidence collection, or repair planning. |
| Phase Completion | May consume evidence from an assessment when a phase declares it relevant. | Completion criteria, closure, or phase status changes. |
| Knowledge Reconciliation | May use findings to guide human reconciliation of repository knowledge and handbook material. | Knowledge extraction, reconciliation, or authoring. |
| Engineering Intent Validation | May explicitly map an Intent to applicable articles and provide findings. | Intent storage, validation workflow, approval, or enforcement. |
| Runtime Providers | May receive a constitutionally reviewed Intent as derived execution context. | Provider integration, prompt translation, execution, or runtime control. |

This boundary preserves the constitutional order: the Constitution establishes
invariants; architecture and Intent interpret them; repository evidence grounds
assessment; human governance determines what happens next.
