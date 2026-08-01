# Forge Phase Completion Framework 1.0

Forge Phase Completion determines whether a bounded engineering phase may be
considered complete from declared, reproducible evidence. It is a local,
deterministic domain boundary; it does not fetch evidence, orchestrate work,
operate repositories, or grant execution authority.

## Contracts

`EngineeringPhase` identifies the bounded phase, its objective, and unique
declarative `CompletionCriterion` records. A criterion states a requirement;
it contains neither a run result nor a human assertion.

`CompletionEvidence` attaches an explicit `PASS` or `FAIL` result to exactly
one declared criterion. Its `ReproducibleEvidenceReference` always includes a
kind, source identity, source version, locator, and SHA-256 content digest.
It supports documentation, validation, tests, engineering artifacts, and
repair reports. References are pointers only: Forge neither embeds nor invents
their content.

`PhaseAssessment` is derived by `PhaseCompletionAssessor` from only the phase
and supplied evidence. Findings are sorted by criterion and code, so identical
declared input always produces the same result and explanation.

## Assessment states

- `NOT_STARTED`: no declared evidence addresses a phase criterion.
- `IN_PROGRESS`: evidence is partial, failed, unresolved, or references an
  undeclared criterion.
- `READY`: every required criterion has passing reproducible evidence, but no
  explicit closure declaration has been supplied.
- `COMPLETE`: the phase is ready and has an explicit, reproducibly referenced
  completion declaration.

The declaration is deliberately insufficient on its own: a human statement
cannot make a phase complete without passing evidence for every required
criterion.

## Future boundaries

Governance may later define who may supply a closure declaration and which
evidence kinds it accepts. Engineering Intent may later declare the criteria
and expected evidence for a phase. Neither capability is persisted, migrated,
or executed by this increment.
