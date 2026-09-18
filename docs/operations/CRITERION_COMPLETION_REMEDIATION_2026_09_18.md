# Forge criterion-bound Mission completion — remediation completion

Date: 18 September 2026  
Result: **COMPLETED**  
Installed version/schema: **Forge 2.7.25 / schema 39**

This record completes the separate criterion-bound Mission-completion repair.
It does not change the historical Mission 3 outcome recorded by
[PR #148](https://github.com/pcvantol/forge/pull/148):
`AUTONOMY_E2E_ACCEPTANCE = NOT_MET` and
`MISSION_EXECUTION_STATE = NOT_STARTED`. No C01–C20 result was rewritten.
No production reset or Mission 3 execution was performed.

## Completion matrix

| Required outcome | Final result |
| --- | --- |
| `FORGE_CRITERION_COMPLETION_REMEDIATION` | **MET** |
| `ROOT_CAUSE_REPRODUCED` | **MET** — the installed 2.7.24 composition reproduced the complete faulty path |
| `CRITERION_SPECIFIC_EVIDENCE` | **MET** for the approved `repository_json` contract; `host_control` remains unsupported |
| `PARTIAL_COMPLETION_AND_SUCCESSOR_PLANNING` | **MET** |
| `VALID_SINGLE_ACTION_COMPLETION` | **MET** |
| `REPOSITORY_TRUTH_REASSESSMENT` | **MET** for distinct current-revision and historical-delivery semantics |
| `REPLAY_AND_RESTART_SAFETY` | **MET** within the tested persistence and reconciliation boundaries |
| `LEGACY_COMPATIBILITY_AND_HISTORY_PRESERVATION` | **MET** in source, isolated migration and production installation |
| `INSTALLED_NORMAL_COMPOSITION_QUALIFICATION` | **MET** — all eight scenarios passed on the exact published wheel |
| `REAL_PLANNER_ADAPTER_QUALIFICATION` | **MET** with the limits recorded below |
| `EP_EVIDENCE_CONTRACT_COMPATIBILITY` | **MET** for the tested serializer, HTTP and parser boundary |
| `PROTECTED_DELIVERY` | **MET** through PRs #149, #150 and #151 |
| `EXACT_ARTIFACT_PUBLICATION` | **MET** |
| `INSTALLED_ACTIVATION_AND_READBACK` | **MET** |
| `RESET_COMPATIBILITY` | **MET** — read-only preview was ready; reset was not executed |
| `SANITIZED_DOCUMENTATION` | **MET** by this protected record |
| `PRODUCTION_RESET` | **NOT_EXECUTED** |
| `MISSION_3` | **NOT_STARTED** |
| `PRIOR_MISSION_3_ACCEPTANCE` | **NOT_MET_UNCHANGED** |

## Root cause and correction

The published Forge 2.7.24 implementation associated the same successful
execution references with every approved criterion. The evaluator treated
current provenance as sufficient coverage. After Action A, the runner therefore
saw no unsatisfied criterion, closed the Mission and did not invoke successor
planning. The normal installed-baseline regression reproduced this result while
providing authoritative evidence for only part of the approved objective.

The correction makes completion a conjunction of versioned, criterion-specific
requirements. Forge observes the accepted delivery revision itself, binds each
observation to the Mission, criterion, requirement, contract and artifact, and
evaluates those observations before completion or successor planning. Planned
contribution, `expected_evidence`, provider prose and a COMPLETE execution
receipt are not completion evidence by themselves.

The supported `repository_json` source verifies a bounded artifact path,
JSON pointer and canonical expected value at the accepted delivery revision.
It proves that structural repository property only. A field containing `PASS`
does not prove that a test or authorization path ran. The installed Execution
Host remains responsible for runtime invocation and host evidence. Forge did
not invent an Engineering Platform field to cover missing `host_control`
evidence.

The architecture and detailed qualification boundaries are in
[criterion-completion-v2](../architecture/criterion-completion-v2.md),
[the baseline regression](CRITERION_COMPLETION_BASELINE_REGRESSION.md),
[the qualification record](CRITERION_COMPLETION_QUALIFICATION.md) and
[the source finalization](CRITERION_COMPLETION_SOURCE_FINALIZATION.md).

## Partial, single-Action and negative behavior

The normal-composition partial scenario uses two explicitly limited repository
predicates. After Action A, the first criterion is proven and the second remains
unsatisfied. Forge stores that assessment and gives the unchanged Mission,
remaining criterion and reason, prior contribution, terminal provenance and
current Repository Truth to the successor planner. The normal parser,
validation and durable materialization path creates Action B. Its newer
revision proves both criteria and allows closure.

That deterministic A→B composition uses explicit external-planner,
repository-transport and host-transport fixtures. It exercises the normal
submission and receipt path without a real or live host submission. The
separate real-provider result below qualifies the planner adapter without
turning this composition scenario into a live provider or host run.

The single-Action scenario proves both predicates at Action A's accepted
revision. The Mission closes after that Action without a dummy successor. No
product rule requires two Actions.

Negative coverage includes missing, empty and invalid observations; wrong or
conflicting identities and bindings; candidate, delivery, revision and digest
mismatches; misleading success text; later regression; no progress; and Action
limits. A new receipt identity for the same already-proven requirement is not
progress. Normalized duplicate work is refused, and finite limits also bound
unrecognized paraphrases.

`current_revision` requires observations at current Repository Truth.
`historical_delivery` preserves only its approved historical meaning. Existing
observations are not rewritten to a later revision. Conflicting facts for one
immutable revision fail closed.

Restart tests cover stored terminal assessment, durable provider output,
successor commit and policy pause. Replay reuses the durable identity and does
not create a second logical successor, submission or approval consumption.
This is evidence for the tested idempotence and reconciliation boundaries; it
is not a general exactly-once guarantee for external execution.

## Schema and historical preservation

Schema 39 adds the completion-v2 metadata under a reader fence. A real
published 2.7.24 interpreter created the schema 38 fixture. Migration preserved
all 45 non-metadata tables and existing completion-v1 history. The old
interpreter then refused schema 39. Completion-v1 records are not accepted as
completion-v2 evidence. Historical terminal Missions were not reopened, and
the legacy five-seed harness refuses new or partial execution before a host
call. Reset table classification did not change.

## Planner and Engineering Platform boundaries

The first real Codex planner attempt remains recorded as a failed confirmed
outcome. It failed exact objective binding and exceeded the existing input
limit. No successor was materialized and no retry authority was inferred.

After a bounded instruction correction and disabling optional tools, a separate
real invocation passed the same parser, validator and durable materializer:
11,942 input tokens and 378 output tokens, within the existing 16,000 input,
4,096 output and 32,768 context limits. It yielded one READY successor and no
host submission. Usage validation occurs after generation; it prevents unsafe
materialization but cannot reverse consumed tokens.

The Engineering Platform check exercised the Forge HTTP adapter and parser
against the owning serializer and handler with isolated authentication and
synthetic terminal transactions. Missing or cross-project authentication was
rejected. Candidate and delivery revisions remained distinct, and Forge
verified the artifact digest. Misleading validation prose in an authentic
COMPLETE response did not prove a criterion without observations. This proves
the tested contract boundary, not a live worker, host-control execution or
autonomous Mission.

## Protected delivery and validation

| Delivery | Exact protected result |
| --- | --- |
| [PR #149](https://github.com/pcvantol/forge/pull/149) — implementation | merge `6199a7645c15f078aa69d6246023b078069a9742`; independent Quality and Security PASS; required hosted checks PASS |
| [PR #150](https://github.com/pcvantol/forge/pull/150) — release and finalization | merge `61e02899277d4ee557696bb24a051916e8c961c2`; final candidate `ef08f1dc47b1ff1a26dae9252b11c2db108bb1dc`; Quality, Security, 818-test suite and hosted checks PASS |
| [PR #151](https://github.com/pcvantol/forge/pull/151) — managed resolver recovery | merge `cd1d10625ac53c25239fef4c15dc33f2f73613bb`; Quality, Security, 824-test suite and hosted checks PASS |

The release/updater finalization rejects incomplete installed-composition
receipts, requires the exact wheel and scenario effects, and rejects all 24
tested negative receipt mutations. The managed-resolver correction adds an
explicit, default-off reconciliation path for the same durable operation. It
accepts only a controller-source and controller-digest correction while the
old operation is provably `STAGED`, schema 38, fenced, quiescent and still
without backup or completion receipt.

## Publication and exact artifact identity

The normal production-release workflow
[run 35337571211](https://github.com/pcvantol/forge/actions/runs/35337571211)
completed all five jobs. Qualification, publication, registry readback and
terminal release completion are distinct receipts.

| Artifact or receipt | Exact result |
| --- | --- |
| Release | [forge-v2.7.25](https://github.com/pcvantol/forge/releases/tag/forge-v2.7.25) |
| Protected release source | `61e02899277d4ee557696bb24a051916e8c961c2` |
| Published wheel SHA-256 | `e0ea58bf6ce242d4eca66801ef4c764c7104b90df5503141a8ebf0006c1aa7b8` |
| Published sdist SHA-256 | `918db200a3970f75b6e0e6e338583cfab3784e648bf34ad613bbd0029efdab7b` |
| Qualified receipt SHA-256 | `1ccd8e1a86edb5ce5c87cb71b6bd94ec59d6799e7bb10a226718c965deb07afa` |
| Published/readback receipt SHA-256 | `d478df3cf06aa0176556814932fe75898b98691af4dee9b6520928b0084cac5f` |
| RELEASE_COMPLETE receipt SHA-256 | `bd33740bff86ba54dcf8f756ead2192e4029adfe40c303c7bc50361d7e44b783` |

All eight installed-composition scenarios passed on the final wheel before
publication, on registry-readback bytes, and in a separate non-editable local
installation. The owning updater also passed isolated normal installation,
COMPLETE replay and recovery at the database-swap-prepared, database-swap and
activation boundaries.

## Installed activation and readback

The first production attempt stopped safely before migration when the existing
installation was found to use the supported managed resolver topology. Its
failure record remains intact. No backup, migration, receipt or service start
occurred in that attempt.

[PR #151](https://github.com/pcvantol/forge/pull/151) supplied the narrowly
scoped resolver correction. The same operation,
`forge-update-2725-criterion-completion-20260918-001`, was then resumed once
with the exact published wheel and protected controller. The updater reported:

| Installed result | Evidence |
| --- | --- |
| Durable operation | same operation moved from `STAGED` to `COMPLETE` |
| Schema | `38 → 39` |
| Preservation | PASS; verified backup and history preservation |
| Installed artifact/source | exact published wheel and protected source binding PASS |
| Normal executable/interpreter/distribution | PASS at Forge 2.7.25 |
| Normal default and explicit status | PASS at schema 39 |
| Installed completion-v2 implementation | PASS |
| Database/history comparison | all 45 non-metadata tables unchanged |
| Mission/Action/planner counters | unchanged |
| Keychain and authenticated Forge→EP GET | PASS through the normal read-only route |
| Reset preview | `READABLE_READY`, no blockers; reset not executed |
| Service | not started |
| Mission/planner/provider/host submission | not started |

The post-installation verifier was read-only and did not invoke the updater.
Credentials, Keychain references, local target paths, database copies, backup
digests and private configuration remain outside repository history and
workflow output. The authenticated preflight proves the normal credential
route and application-level authorization; it does not claim cryptographic
peer identity.

## Final boundaries and handoff

The owning updater returned terminal COMPLETE and exited. A final targeted
process check found no updater, production verifier or published-update
qualification process. The two architecture lanes then recorded the scoped
completion and release in
[#141 revision 16](https://github.com/pcvantol/forge/issues/141) and
[#142 revision 14](https://github.com/pcvantol/forge/issues/142):

| Coordination scope | Final disposition |
| --- | --- |
| `FORGE_SOURCE_SCOPE` | `COMPLETED / RELEASED` |
| `FORGE_RELEASE_SCOPE` | `COMPLETED / RELEASED` |
| `FORGE_INSTALLATION_SCOPE` | `COMPLETED / RELEASED` |
| `SHARED_ACTIVATION_WINDOW` | `COMPLETED / RELEASED` |
| `ISOLATED_QUALIFICATION_SCOPE` | `COMPLETED / RELEASED` |
| `EP_READONLY_BOUNDARY` | `COMPLETED / RELEASED` |
| `SANITIZED_EVIDENCE_NAVIGATION` | `COMPLETED / RELEASED` |

These dispositions close only this assignment's coordination holds. They do
not remove product locks, release other assignments or grant new runtime
authority. The Engineering Platform production interaction was read-only. No
Engineering Platform source, worker or runtime state was changed.

This completion does not authorize a reset, Mission intake, Mission 3, the next
Mission, parallel Actions, backlog execution or a broader evidence source. A
future Mission-3 preflight requires a separately approved Mission whose criteria
fit available authoritative evidence. `host_control` stays
`UNSATISFIED / UNSUPPORTED_AUTHORITATIVE_EVIDENCE_SOURCE` until its owning
producer contract supplies such evidence.

Final invariants:

- `PRODUCTION_RESET = NOT_EXECUTED`
- `MISSION_3 = NOT_STARTED`
- `PRIOR_MISSION_3_ACCEPTANCE = NOT_MET_UNCHANGED`
- `FORGE_CRITERION_COMPLETION_REMEDIATION = COMPLETED`
