# Criterion completion source finalization

Assignment: `L1-CRITERION-PLANNING-REPAIR-20260918`, 18 September 2026.
This is the separate source finalization for
[implementation PR #149](https://github.com/pcvantol/forge/pull/149), merged
through the protected route at
`6199a7645c15f078aa69d6246023b078069a9742`.
It is an intermediate delivery checkpoint: publication, exact registry
artifacts, safe installed activation and the final completion record remain
required within this same assignment.

## Immutable source and assurance

The independently reviewed implementation candidate is
`b368052ed59b18b19182ee724802f5d67d264340`, tree
`085c7b419efc10b782002167642a7462ec03958a`.
Separate Quality and Security reviewers did not author the implementation.
Both returned PASS with no open findings on this exact candidate. Quality
reran 171 focused tests with one opt-in skip; Security reran 50 focused tests.
The earlier three Quality findings and their corrections remain documented in
the [qualification record](CRITERION_COMPLETION_QUALIFICATION.md).

Owning validation passed 817 tests with one existing optional exact-artifact
test skipped, plus compilation, version policy, projection, JSON and whitespace
checks. The hosted required
[Test and static validation run](https://github.com/pcvantol/forge/actions/runs/35336005960)
passed; CodeQL, version validation and advisory TDE checks also passed before
merge. No branch protection or check requirement was bypassed.

A clean Git archive of that candidate produced qualified wheel and sdist
payloads. The noneditable wheel passed all eight normal installed composition
scenarios across separate processes. Candidate artifact digests are:

| Candidate artifact | SHA-256 |
| --- | --- |
| `forge_autonomy-2.7.25-py3-none-any.whl` | `3e288c76ec0b53a4aba795103eb72a53a7bb98667c7c9584ba87c02267762d45` |
| `forge_autonomy-2.7.25.tar.gz` | `9cf5f07cf16464cf531cfe89cf6d5133f14562b94ff3c7b61d57acaf717d91d9` |

These are candidate-only bytes, not the later published release artifacts.
The real provider result, retained failed attempt, EP HTTP qualification and
actual schema-38 migration fixture are separately scoped in the qualification
record. None represents a production Mission run.

## Delivered behavior and remaining delivery gates

Finalization review caught a producer/consumer mismatch before publication:
the release workflow now retains installed-composition summaries, while the
updater's original strict receipt shape rejected those additional fields.
This finalization binds both qualification and registry-readback summaries
to the exact 2.7.25 wheel and requires all eight expected outcomes, counts and
history/reopen guarantees. Captured summary-shape tests reject missing,
malformed, mismatched or incomplete evidence. Older release receipt shapes
remain unchanged. This is a bounded release-to-updater correction within the
same version and assignment; no published receipt is rewritten.

The [criterion assessment contract](../architecture/criterion-completion-v2.md)
binds substantive evidence to approved criterion semantics and preserves
original observations. Partial completion enters the durable successor route;
fully proven criteria can finish after one Action. Current-revision properties
are reobserved on later Repository Truth. Safe legacy readback, finite planning
and replay retain their explicit failure boundaries.

The release version is selected once as **2.7.25**, with schema **39** and the
bounded supported updater transition from **2.7.24/schema 38**. The normal
production workflow must build from the final protected source, retain exact
qualification/publication/completion receipts, verify downloaded PyPI bytes
and repeat the installed composition qualification. The existing updater must
then qualify and activate those exact bytes with preservation checks and a
new concrete peer-coordinated activation window.

The repository JSON route proves only its approved structural assertion;
`host_control` remains unsupported until authoritative EP control receipts
are exported. Provider usage is checked after generation, not guaranteed by a
hard token preflight. Those limitations remain prerequisites to evaluate for
any later Mission-3 preflight.

No production reset, Mission allocation/intake/planning or historical Mission
requalification is part of this finalization. The #148 results remain
`AUTONOMY_E2E_ACCEPTANCE = NIET_GEHAALD` and
`MISSION_EXECUTION_STATE = NIET_GESTART`.
