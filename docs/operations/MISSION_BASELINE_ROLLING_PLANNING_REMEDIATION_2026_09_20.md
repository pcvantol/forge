MISSION_BASELINE_ROLLING_PLANNING_REMEDIATION = GEHAALD

# Mission baseline, rolling planning and submission remediation

The failed production MISSION-0003 is immutable evidence and its acceptance remains **NIET_GEHAALD_ONGEWIJZIGD**. This record contains only public product and qualification references; protected local receipts retain installation, actor and storage details. No production CENTRAL reset or new production Mission was executed.

## Root causes and owning corrections

| ID | Symptom | Proven cause | Owning product | Correction |
| --- | --- | --- | --- | --- |
| R1 | Forge Truth at `174adfe873d9970683d6214212cb3c6fea5a323c` while EP Managed workspace was at `83cf8dd6adc64b19575414aba7ac63d489f3b032` | Forge bound Truth to the Action but the selected clean EP workspace was not prepared to that exact revision before admission; a matching repository or branch name did not prove commit identity. EP correctly blocked before implementation. | Forge baseline authority; EP workspace preparation/admission | Forge binds every Action to exact Repository Truth; EP verifies repository/origin, lease/writer and Git state, prepares the workspace to the authorized SHA, rereads HEAD and binds execution to that state. |
| R2 | P1 created A and B before A evidence | The validated planner list was translated wholesale into durable Engineering Actions. The existing successor route did not need to run while B already existed. | Forge | Persist future ideas as forecast only; commit one immediately executable Action. Reassess accepted predecessor evidence, new Truth and remaining criteria before a real P2 decides B. |
| R3 | Historical submission still projected as executable QUEUED after terminal preimplementation block | The current readback relied on the immutable queue event instead of the resolved operator gate and released lease. Separate delegation/recovery checks showed there was no permitted continuation. | EP current submission projection; Forge dispatcher maintenance | EP v1.3 derives terminal `DISMISSED` disposition and executable=false from gate resolution and lease state while preserving the QUEUED event. Forge's owning updater reconciles a stale terminal dispatcher only with authenticated EP proof and the existing locks. |

The cross-product invariant per Action is **authorized Forge Action baseline = Forge Repository Truth = the exact EP prepared and execution workspace HEAD**. Project, repository, origin, branch, SHA, Truth revision, Action, submission, workspace, lease, preparation and execution mode are separately bound. EP fails closed for wrong repository/origin, dirty state, foreign writer or lease, missing or unreachable commit, uncertain preparation, stale proof and drift. A later Action may use a later accepted delivery revision; the Mission-start SHA is not permanent.

A forecast has no Action ID, submission, lease, delivery authority or completion status. It may remain in planning history for audit. The serial transition is:

`P1 → A canonical → A terminal evidence → Truth R1 and remaining criteria → real P2 → B canonical`.

If A proves all criteria, Forge closes the Mission after A. Invocation/input/output digests, predecessor evidence, limits and committed decision support replay without duplicate Actions or submissions; no-progress and Action ceilings remain bounded.

The historical submission keeps its original QUEUED event. EP v1.3 derives `DISMISSED`, terminal=true and execution_eligible=false from the dismissed operator gate and absence of an active lease. Separately, the Mission delegation is revoked and no owning recovery remains; neither an execution attempt nor a retry was fabricated. Current queue projections count executable items only. Forge and EP agree that the old submission cannot run.

## Evidence classes and product validation

| Evidence class | Scope | Result |
| --- | --- | --- |
| Focused source/fixture/subprocess regressions | Exact baseline, old clean preparation, wrong/dirty/busy/drift failures, rolling P1/A/P2/B, replay/limits, submission history/current/restart | PASS in the Forge and EP product suites. |
| Complete repository validation | Forge 886 tests (one established skip) on final updater controller; EP 2,014 tests and product checks on release candidate; compilation, schemas, packaging, versioning, diff and required CI | PASS. |
| Independent Quality and Security | Exact Forge PR #164 and EP PR #290 product candidates; exact Forge updater PRs #165, #166 and #167 after corrections | Separate PASS records. |
| Real isolated candidate-wheel qualification | Normal Forge controller, real planner/provider, authenticated HTTP to isolated EP, real Managed workspace and protected target delivery | Positive and negative scenarios PASS; full protected local evidence retained. |
| Published-wheel qualification | Registry-downloaded Forge 2.7.27 and EP 2.3.91 in isolated data | Fresh positive Mission COMPLETED through A, real P2, B and protected delivery; separate negative scenario PASS including terminal submission across restart. Three earlier positive attempts remain failed evidence and are not counted as passes. |
| Production read-only verification | Installed versions, peer, data integrity, historical Mission and current submission | Forge 2.7.27/schema 39 and EP 2.3.91/server schema 72 healthy; peer PASS; historical Mission unchanged; old submission `DISMISSED`, not executable, active queue depth 0. |

The required focused regression inventory is retained in the owning source suites:

| Required cases | Decisive owning tests and observed contract |
| --- | --- |
| Workspace/baseline 1–13 | EP `tests/engineering/test_execution_host.py` covers exact preparation of old clean main, already-exact no-op, dirty/wrong repository/origin/unreachable SHA, uncertain Git outcome, changed HEAD/origin and index lock before provider or reviewer. `test_managed_workspace_readiness.py` covers read-only scope and known blockers. Forge `test_ep_http_adapter.py` checks exact requested/candidate/baseline bindings and rejects mismatched receipts. |
| Rolling planning 14–28 | Forge `test_dynamic_mission_capability.py` proves P1 forecast never creates B and valid one-Action completion; `test_terminal_continuation_replay.py` proves new evidence-bound successor, provider result replay, restart idempotence, no-progress and Action limits; `test_action_derivation.py` rejects stale or duplicate successor work. Candidate and published live Mission timelines bind A terminal evidence to the later P2/B. |
| Terminal submission 29–37 | EP `test_submission_service.py` keeps QUEUED history but derives terminal `DISMISSED` and executable=false, protects resumable holds, and verifies queue operation idempotence; `test_parity_lifecycle_dispatcher.py` checks release/retry chains; dashboard and restart tests check current queue/telemetry. Installed historical v1.3 readback and active queue depth 0 provide production read-only verification. |
| Cross-product 38–44 | Forge adapter receipt/baseline tests, EP exact workspace preparation/drift tests, real isolated protected-delivery Missions, and their restart/readback evidence bind requested, prepared and execution SHA; terminal old submissions are not re-ingested as new runs. |

The pre-T0 execution manifest now includes `PRE_T0_MANAGED_WORKSPACE_READINESS` beside command surface, input validation, data-root resolution, authority and delegation readiness. It inspects the target repository, origin, workspace identity/HEAD, clean and writer state and preparation capability without moving the workspace or starting a planner, Action, provider or submission. EP performs the exact mutating preparation later for each authorized Action.

## Baseline and planning qualification

| Action | Forge baseline | EP pre-HEAD | Prepared HEAD | Execution HEAD | Result |
| --- | --- | --- | --- | --- | --- |
| Candidate A | `e5e03facd5927f890a874f27cd730ac7be0bccb8` | `bc55819388115fe0e0dd83d0d30a543c59ff1bfb` | `e5e03facd5927f890a874f27cd730ac7be0bccb8` | `e5e03facd5927f890a874f27cd730ac7be0bccb8` | Qualified protected delivery |
| Candidate B | `a0356f71f6054af8acd85306377999e8439ba2ef` | `a0356f71f6054af8acd85306377999e8439ba2ef` | `a0356f71f6054af8acd85306377999e8439ba2ef` | `a0356f71f6054af8acd85306377999e8439ba2ef` | Qualified protected delivery |
| Published A | `b6e5f0ee7d54d12c1910ce6fea2d85a959d4a0ff` | `51c21ee883fc45535dc2d960a6405435d62060e9` | `b6e5f0ee7d54d12c1910ce6fea2d85a959d4a0ff` | `b6e5f0ee7d54d12c1910ce6fea2d85a959d4a0ff` | Qualified protected delivery at `bcb4ee3dcbc456d277a3196a4fd768086cd6305d` |
| Earlier published attempt B | `bcb4ee3dcbc456d277a3196a4fd768086cd6305d` | `bcb4ee3dcbc456d277a3196a4fd768086cd6305d` | `bcb4ee3dcbc456d277a3196a4fd768086cd6305d` | Provider began at that baseline | Finalization blocked on dirty checkout; failed qualification |
| Published negative Action | `f35617f91daa66638ff3db7f84bfaf3ace1f341e` | `51c21ee883fc45535dc2d960a6405435d62060e9` | `f35617f91daa66638ff3db7f84bfaf3ace1f341e`, then controlled untracked drift | No provider execution HEAD | BLOCK before implementation |
| Published final positive A | `75cc0c3a713e4032502dd8c743403f55f9abad73` | `51c21ee883fc45535dc2d960a6405435d62060e9` | `75cc0c3a713e4032502dd8c743403f55f9abad73` | `75cc0c3a713e4032502dd8c743403f55f9abad73` | Protected implementation [#61](https://github.com/pcvantol/forge-mission-qualification/pull/61), finalization [#62](https://github.com/pcvantol/forge-mission-qualification/pull/62) and reconciliation [#63](https://github.com/pcvantol/forge-mission-qualification/pull/63), R1 `598f1f860e48300abe306417a7edba568fa785a6` |
| Published final positive B | `598f1f860e48300abe306417a7edba568fa785a6` | `598f1f860e48300abe306417a7edba568fa785a6` | `598f1f860e48300abe306417a7edba568fa785a6` | `598f1f860e48300abe306417a7edba568fa785a6` | Protected implementation [#64](https://github.com/pcvantol/forge-mission-qualification/pull/64), finalization [#65](https://github.com/pcvantol/forge-mission-qualification/pull/65) and reconciliation [#66](https://github.com/pcvantol/forge-mission-qualification/pull/66); final Truth `15246b6f890a48c6cf767213fc01ffbfc1e5d79f`, Mission COMPLETED |

| Planner | Trigger | Repository Truth | Predecessor evidence | Remaining criteria | Forecast | Materialized Action |
| --- | --- | --- | --- | --- | --- | --- |
| Candidate P1 | Mission start | R0 | None | Skip and reverse | None emitted; multi-item forecast covered by source regressions | Skip A only |
| Candidate P2 | Accepted A terminal evidence | R1 | A delivery and validation | Reverse | None emitted | Reverse B only |
| Published P1 | One isolated Mission start | `b6e5f0ee7d54d12c1910ce6fea2d85a959d4a0ff` | None | Skip and reverse | None emitted | Skip A only |
| Published P2 | Accepted A terminal evidence at `13:52:11` UTC | `bcb4ee3dcbc456d277a3196a4fd768086cd6305d` | A delivery and validation | Reverse | None emitted | Reverse B at `13:52:40` UTC |
| Published final P1 | One isolated Mission start at `15:35:36` UTC | `75cc0c3a713e4032502dd8c743403f55f9abad73` | None | Skip and reverse | None emitted | Skip A at `15:36:01` UTC only |
| Published final P2 | Accepted A terminal evidence at `15:55:39` UTC | `598f1f860e48300abe306417a7edba568fa785a6` | A protected delivery and validation | Reverse | None emitted | Reverse B at `15:56:07` UTC only |

The candidate ordering readback is A creation `11:32:05` < A terminal evidence `11:51:21` < P2 invocation after Forge's `11:52:09` reconciliation < B creation `11:52:38` UTC. Candidate B delivered terminal evidence at `12:11:06` UTC and the Mission completed. The candidate negative fixture blocked before provider implementation, then its owning gate lifecycle yielded `DISMISSED`, no lease and executable=false across restart. These are distinct from the published-byte run and from production read-only verification.

The first published-byte ordering was P1 `13:32:16` < A durable materialization `13:32:45` < A terminal execution `13:51:38` < Forge evidence reconciliation and new P2 `13:52:11` < B durable materialization/submission `13:52:40` UTC. At P2 start, only A was in the canonical Action list, Repository Truth was `bcb4ee3dcbc456d277a3196a4fd768086cd6305d`, the skip criterion was PROVEN and reverse remained UNSATISFIED. P1 and P2 have different derivation request and planning snapshot digests. Their outputs emitted no forecast item; the P1 A+B forecast separation is additionally exercised by source regressions. B's implementation merged in protected target [#52](https://github.com/pcvantol/forge-mission-qualification/pull/52), but EP blocked finalization because its provider left a dirty Managed checkout. Forge marked that isolated Mission FAILED. There was no manual resume; the run is retained as failed qualification evidence. Protected target [#53](https://github.com/pcvantol/forge-mission-qualification/pull/53) restored the prefeature state. The next run merged A implementation [#54](https://github.com/pcvantol/forge-mission-qualification/pull/54) and finalization [#55](https://github.com/pcvantol/forge-mission-qualification/pull/55), then blocked before terminal A evidence because the candidate-bound reconciliation Quality and Security calls returned `UNRESOLVED`. Its unmerged [#56](https://github.com/pcvantol/forge-mission-qualification/pull/56) was closed, and protected [#57](https://github.com/pcvantol/forge-mission-qualification/pull/57) restored the test entrypoint. A third run merged A implementation [#58](https://github.com/pcvantol/forge-mission-qualification/pull/58) and finalization [#59](https://github.com/pcvantol/forge-mission-qualification/pull/59), then blocked reconciliation because its qualification instructions ran B's future reverse selector before B existed. Protected [#60](https://github.com/pcvantol/forge-mission-qualification/pull/60) restored the entrypoint for a new run with an explicit Action A/B validation boundary. None of the failed runs is counted as a successful published-byte positive qualification.

The final published-byte positive run proves P1 `15:35:36` < A creation `15:36:01` < EP A terminal evidence `15:55:12` < Forge A reconciliation and P2 invocation `15:55:39` < B creation `15:56:07` < EP B terminal evidence `16:10:25` < Mission COMPLETED `16:10:55` UTC. P2 has a different generation request and derivation request digest from P1, binds A's accepted protected delivery and R1, and materializes B only against the remaining reverse criterion. The controller exited successfully after one Mission start, two Actions and two real planner decisions. A used protected target PRs #61–#63; B used #64–#66. EP reported implementation, validation, separate Quality and Security, finalization and reconciliation terminal; Forge marked both criteria PROVEN and Repository Truth at `15246b6f890a48c6cf767213fc01ffbfc1e5d79f`.

## Submission lifecycle

| Submission | Historical event | Current disposition | Lease | Delegation | Recovery | Executable? |
| --- | --- | --- | --- | --- | --- | --- |
| Failed production MISSION-0003 submission `sub-c799a12244905ed02e8d7a52f0eba6e1` | QUEUED, admission blocked before implementation | `DISMISSED` terminal in EP v1.3 | Released | Revoked | None | No |
| Candidate negative qualification | QUEUED, preparation blocked before implementation | `DISMISSED` terminal, persists after restart | Released | Revoked | None | No |
| Published negative qualification | QUEUED, exact preparation followed by controlled untracked drift | `DISMISSED` terminal, persists after restart | Released | Revoked | None | No |

## Protected delivery, release and installation

| Product | PR | Candidate | Quality | Security | Checks | Merge |
| --- | --- | --- | --- | --- | --- | --- |
| EP | [#290](https://github.com/pcvantol/engineering-platform/pull/290) | `da1143a6c26afdad78034d244a027b9ef09ad4ba` | PASS | PASS | Required checks PASS | `701ebe5f573e82b1e79548604acca1a05273715f` |
| Forge | [#164](https://github.com/pcvantol/forge/pull/164) | `b19fcd936f91aae5dcc0f93954dad1f54a2d3ca1` | PASS | PASS | Required checks PASS | `d429ea07fcf8d5a6504ffea69f0022458491a9e7` |
| Forge updater | [#165](https://github.com/pcvantol/forge/pull/165) | `702e73ad6d652473bc27075b6f770d467f7b3077` | PASS | PASS | Required checks PASS; nonblocking TDE observe failed | `452ce63cd5514c0413e2f3ae923089f24c1ff459` |
| Forge updater | [#166](https://github.com/pcvantol/forge/pull/166) | `674718d68c63d776865f74a112de9cb6e5274852` | PASS | PASS | Required checks PASS | `80e2ae69cf9675ec18b357a439e6e5ea296c806f` |
| Forge updater | [#167](https://github.com/pcvantol/forge/pull/167) | `756040999174e1d5d3867234a9d46d7275583785` | PASS | PASS | Required checks PASS | `693dca7803071b266e7afe18b7df300acb5874d4` |

EP was installed first through its owning quiesce and update operation. During the quiescent installation gap before Forge activation, old Forge 2.7.26 rejected EP's expanded advertised contract-version list in peer preflight, despite EP retaining the v1.2 default. That intermediate installed pair was **not operationally compatible**. The preactivation resource check found no active production Mission or Forge controller; no production Mission was started during the interval. There was no continuous cross-product maintenance fence across this gap. Forge 2.7.27 was then activated through its owning updater and authenticated peer preflight passed before any new production Mission activity. This gap and its operational boundary remain explicit installation evidence. Product wheel source and external release/update-controller source are distinct identities. Historical [Forge #163](https://github.com/pcvantol/forge/pull/163) is the failed-attempt handoff, and #162 is its predecessor; neither contains this product fix or changes the historical acceptance.

| Product | Version | Schema | Source SHA | Wheel SHA-256 | Sdist SHA-256 | Registry readback |
| --- | --- | --- | --- | --- | --- | --- |
| Forge | 2.7.27 | 39 | `d429ea07fcf8d5a6504ffea69f0022458491a9e7` | `9fef5f0eb95075e209f007d30e6c97afe2a2e67d4d099591729506131ee3415e` | `327698574368126a873403ea31981426f6888ebc90b48b32cab917e06e51a1e8` | Exact published bytes re-downloaded and compared; [release workflow](https://github.com/pcvantol/forge/actions/runs/35510317678) complete. |
| EP | 2.3.91 | server 72 / engineering 45 | `701ebe5f573e82b1e79548604acca1a05273715f` | `62ad3a526a424e2b343ce9cc499ce9782613d947ebd719816d253ea7530f1be0` | `3c66e2623130ba2207149646de3b131c0fd66288dcb4c2d1e2950680bc17661f` | Exact published bytes re-downloaded and compared; [release workflow](https://github.com/pcvantol/engineering-platform/actions/runs/35510266074) complete. |

| Product | Previous | Installed | Schema | Update operation | Artifact digest | Identity preserved | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Forge | 2.7.26 | 2.7.27 | 39 | Same durable owning operation, after protected controller reconciliation | Wheel digest above | Runtime, installation, projects, governance, credentials and history preserved | COMPLETE |
| EP | 2.3.90 | 2.3.91 | server 72 / engineering 45 | Owning plan/prepare/admit/apply operation | Wheel digest above | Instance, project, repository, credential and history preserved | COMPLETE |

| Scenario | Artifact bytes | Real planner/provider | Real EP | Managed workspace | Protected delivery | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Candidate positive | Non-editable candidate wheels | Yes | Yes | Older clean to R0, then A delivery to R1 | Target #42–#47 | PASS |
| Candidate negative | Non-editable candidate wheels | Yes | Yes | Deliberately unsafe after preparation | Blocked before implementation | PASS |
| Published positive | Registry-downloaded wheels above | Yes | Yes | Older clean to exact R0; later R1 | Target #61–#66 | PASS; one Mission start, A evidence before real P2/B, Mission COMPLETED |
| Published negative | Registry-downloaded wheels above | Yes | Yes | Older clean workspace fast-forwarded to exact Action SHA, then controlled untracked drift | Blocked before provider implementation; no delivery PR | PASS; v1.3 historical QUEUED/current DISMISSED, active queue 0 across restart |

## Reset compatibility and next production Mission-3 recipe

No product schema version changed in this slice: Forge remains 39 and EP remains server 72 / engineering 45. Forecast is stored in the existing Mission planning history, not as an Action or new table. EP's terminal disposition is a current projection of existing immutable lifecycle evidence. Existing Mission purge and protected audit/reset classification therefore remain valid; no external workspace content is copied into CENTRAL. The owning updaters qualified installation from the actual prior versions without a production reset.

`NEXT_MISSION_3_RESET_REQUIRED = YES`. The frozen C19/C20 contract used a generation-1 execution-clean baseline before T0. The failed production MISSION-0003 left Mission, planning, Action, submission, gate and lease events in that generation. Its corrected terminal queue projection alone does not make the old generation a clean new acceptance population. The next attempt must use the already qualified joint Forge/EP reset/coordinator route on CENTRAL as an explicit *future* preparation, with its own preview, authorization, prepare/backups, same-operation revalidation, Forge and EP apply/verify/authorize-resume/finish and post-reopen readback. **No production reset was executed here.**

The next production attempt is an unexecuted operator recipe:

1. Require published Forge 2.7.27/schema 39 and EP 2.3.91/server 72 / engineering 45 with the exact wheel digests above and healthy compatible peer readback.
2. Run the separate authorized clean-CENTRAL reset workflow, preserving installation/instance, projects, credentials, profile, revocations, budgets and high-watermarks; verify the new dataset generation and no historical re-ingest. Do not run it as part of this remediation.
3. Perform fresh read-only command, input, data-root, authority, delegation and `PRE_T0_MANAGED_WORKSPACE_READINESS` checks. Read the repository-bound target/profile/policy and prove Mission scope/evidence fit. The workspace check records repository/origin, Managed workspace ID, current HEAD, clean/busy/writer/lease state and exact-baseline preparation capability; it does not mutate to a future unknown Action SHA.
4. Freeze the unchanged C01–C20 criteria and explicit telemetry/report/export population. Define T0 immediately before the first future mutating delegation reservation. Obtain the normal Business and Architecture approvals, admit the already-approved Mission, reserve/activate one Mission-scoped delegation and start exactly one Forge controller.
5. After that start, observe externally read-only. Expect `P1 → A created → A workspace prepared → A execution/delivery → A evidence → P2 → B created → B execution/delivery → Mission completion`, with baseline equality at each execution, independent Q/S, protected merges, finalization and criteria readback. Accept C19/C20 only against the new generation and attempt scope.

This recipe reserves no Mission ID, approval, grant, Action or planner invocation. A new production acceptance requires its own explicit kickoff, attempt identity and T0. No new production Mission was started in this remediation; MISSION-0003 was never reopened, retried, resumed or rewritten.

## Scoped resource handoff

All isolated qualification Missions are terminal. Their test delegations were revoked, failed gates were dismissed through the owning lifecycle, and the isolated EP services were stopped through the product route after readback. Temporary qualification-only authentication entries were removed. Local evidence and failed-attempt history remain protected for audit; target worktrees were not deleted as a gate workaround. Production credentials, services and MISSION-0003 remain intact. The next production acceptance starts only by a new explicit operator kickoff after the required separate reset.
