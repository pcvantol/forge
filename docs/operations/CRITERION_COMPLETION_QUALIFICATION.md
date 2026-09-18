# Criterion completion qualification boundaries

Assignment: `L1-CRITERION-PLANNING-REPAIR-20260918`. This record describes the
repair qualification. Release, installation and final handoff remain separate
delivery evidence; it does not change the negative Mission-3 acceptance in #148.

## Reproduced defect and corrected interpretation

The [installed baseline regression](CRITERION_COMPLETION_BASELINE_REGRESSION.md)
reproduces premature completion with the published Forge 2.7.24 wheel. Its
single successful receipt was associated with both criteria despite supporting
only one; the normal evaluator reported both proven and omitted successor
planning. Earlier generic A-to-B tests supplied an alternate criterion-evidence
function, so they did not qualify the installed producer/evaluator composition.

The [v2 contract](../architecture/criterion-completion-v2.md) separates approved
requirements, planned contributions, observed repository facts and assessment.
The supported repository assertion proves only its explicitly approved JSON
property at the exact delivered commit. It cannot prove application behavior,
test execution or access enforcement from a configuration flag. Host report
prose, `expected_evidence`, general PASS text and receipt integrity prove no
additional criterion semantics.

## Distinct qualification levels

| Evidence | What it demonstrates | Boundary |
| --- | --- | --- |
| Source regressions | Contract approval binding; missing, unrelated, malformed and conflicting observations; exact provenance; current and historical validity; multiple requirements and Actions; finite continuation; crash/replay and safe legacy handling | Focused product tests, with explicit external fixtures |
| `python -I -m forge.qualification.criterion_completion` | Normal installed factory, parser, admission, evaluator, planner integration, runner and durable state across separate processes; partial A-to-B, direct single-Action completion, misleading PASS, missing/invalid evidence, no progress, Action limit and later regression | Codex process, Host and immutable-repository transport fixtures; noneditable installed-wheel identity is required |
| Real Codex successor | One actual provider result passed the same parser, deterministic validator and durable materializer, producing a READY successor for the unmet approved criterion | Synthetic prior A, observations and approved Mission; zero real Host submissions |
| EP owner serializer and HTTP | Actual authenticated submission/readback/artifact routes and terminal serialization, consumed by the normal Forge HTTP adapter; distinct candidate and delivery identities and artifact digest retained | Isolated synthetic registration and temporary credential; terminal transaction state seeded; no lifecycle worker, provider or validation-command execution |

The first real Codex qualification failed exact objective binding and reported
20,170 input / 390 output tokens, exceeding the existing 16,000 input bound.
Its immutable result was retained and no successor was materialized. The adapter
now uses documented, bounded planner instructions and disables optional tool
features. The exact instruction content and tool settings participate in its
request digest. Missing, malformed or over-bound observed usage prevents
materialization and remains a recorded confirmed outcome, not retry permission.

After that source correction, one separately identified qualification using
Codex CLI 0.155.0 and its existing default model passed: **11,942 input / 378
output tokens**, within unchanged limits of 16,000 input, 4,096 output and
32,768 context, with a 300-second timeout. No model identity is invented where
CLI metadata omits it. This is observed compliance for that invocation.
Post-generation usage validation cannot prevent already-incurred usage and is
not a hard token-preflight guarantee.

EP qualification executed owner source
`aa73aa46322230aaf8afce4223fd497879d800d6`; the relevant serializer/readback
contract was compared with remote
`13691e4502c239e03558a9c79538ae9b7387938f`. Producer readback v1.2 and terminal
evidence v1.4 worked with isolated authentication. Missing and cross-project
authorization returned 401. Canonical COMPLETE with misleading validation
prose left both criteria unproven. The existing producer surface does not
export independently executed host control receipts; `host_control`
requirements therefore remain explicitly unsupported. No EP source change
was needed for Forge-owned repository observations.

## Preservation and delivery checks

An actual published 2.7.24 interpreter created the isolated schema-38 fixture.
Opening it with the repair migrated to schema 39 while preserving all rows in
the 45 nonmetadata tables, runtime identity and historical completion-v1
documents. The actual old interpreter then rejected schema 39. Updater tests
cover the bounded 2.7.24-to-2.7.25 transition, preserved history/security/reset
generation, distinct backup identity and crash reconciliation around activation.
The exact installed artifact must additionally pass the updater qualification.

Independent review found and corrected historical failed receipts blocking a
valid successor, an initial materialization that could exceed the approved
Action ceiling, and non-ASCII array indices incorrectly accepted as JSON
Pointer indices. Their source regressions retain the failed receipt, block
excess work before dispatch and preserve legitimate Unicode object keys.

The production release workflow runs the installed composition qualification
against its exact wheel before publication and again against downloaded PyPI
bytes. The sanitized summaries become part of the durable qualification and
publication receipts. Private stores, credentials, local identities, paths,
raw provider input/output and operational preservation digests are excluded
from public artifacts.

Historical `AUTONOMY_E2E_ACCEPTANCE = NIET_GEHAALD` and
`MISSION_EXECUTION_STATE = NIET_GESTART` remain unchanged. These repair tests
do not start Mission 3 or retrospectively qualify it.
