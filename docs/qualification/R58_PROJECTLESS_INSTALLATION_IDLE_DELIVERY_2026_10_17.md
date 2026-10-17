# R58 projectless installation scheduler readiness

Assignment L3-PROJECTLESS-INSTALLATION-IDLE-V1-20261017, R58/plan1.
Same sole LANE_3_WORK writer/session. R57 branch, PR298, original native-host
failures, evidence and budgets remain preserved and separately blocked; its
recurring timer stays PAUSED. R56 and predecessors remain CLOSED.
Canonical PATCH2.22.0→2.22.1/schema46; this own separate Finalization is NO_BUMP.

## Delivered boundary

The original clean installer0.4.29 GUI test installed both products and paired
the installation, but Forge demanded project-bound EP host configuration even
with no Mission work. The fix is entirely Forge-side. No installer, VM, helper,
login, credential, existing installed instance, or target repository is changed.
No dummy project, project registration, Mission identity or execution approval.

After the existing instance-owned provider readiness check, the scheduler uses
the existing RuntimeServiceLock and one validated read-only RuntimeBootstrap
snapshot. Only provable emptiness of all eleven canonical work/history tables
permits IDLE before full InstalledDynamicMissionRuntime composition. These
include immutable exchange audit and non-FK dispatcher/planning/bootstrap state.
Current schema, integrity, ownership, maintenance fence, lease and root identity
remain enforced. Missing, corrupt, invalid, uncertain, fenced or nonempty storage
retains the unchanged strict runtime path. There is no general exception-to-IDLE
fallback. Project choice remains a later Workspace action; installation readiness
never claims project authority or execution readiness.

This bounded fresh-empty classifier does not assert that arbitrary historical
completed Missions can run without project configuration. Provider failure still
blocks empty installations. Existing Mission/project/EP-host/authority checks and
runtime execution behavior remain required whenever work or uncertainty exists.

## Regression and installed evidence boundaries

Original empty-runtime source regression was RED before correction. Twelve
linked scheduler regressions cover provider readiness, persistent Mission work,
allocation/intake/dispatch/planning/audit uncertainty, missing/corrupt/fenced
storage, read-only storage digest and canonical lease behavior. Five additional
concurrency qualification guards reject duplicates, two winners, unknown/untyped
errors and wrong canonical transitions.

The ordinary noneditable installed HTTP qualifier compares346 product payload
files against source and wheel. It starts separate Forge Server OS processes
outside the checkout against the existing EP HTTP simulator. External Codex login,
OS-owner and Keychain resolution are explicitly synthetic test boundaries; no real
provider login, model call, live EP or physical VM acceptance is claimed.

The four cases prove: fresh projectless HTTP readiness IDLE/CONNECTED and
service_ready=true; same-instance restart/new PID with the same result;
canonical persistent resumable Mission without project remains NOT_READY with
PeerConfigurationError; a separately initialized zero-Mission runtime containing
only canonical uncertain dispatch evidence also remains NOT_READY. The latter
has a separate instance ID and does not inherit the Mission from the prior case.
Project/execution authority stays false. Own scratch and processes are cleaned.
Existing normal installed Mission execution separately proves one original
submission, completion and original readback/replay without duplicate effects.

## Failures and narrow qualification correction retained

The first wheel probe rejected stale ignored R57 build payload before effects;
original wheel/build/log retained, clean rebuild qualified. One extended installed
probe lacked the synthetic OS-owner fixture in a child and failed before the
expected project error; original retained. Another PASS shared uncertain evidence
with a prior Mission and was not sufficient independent proof; a new distinct
runtime closed that evidence gap. These do not become historical PASS retroactively.

CI39016840074 on f60f418 passed1652 canonical tests and strict changed-product
coverage789/917=86.04%, but failed the existing installed concurrent-start gate.
Original log/artifact retained; missing individual race outcomes were not
reconstructed. A controlled actual installed RED then GREEN demonstrated the
specific legitimate typed WAITING_FOR_EXECUTION→CREATED refusal after one winner.
The qualification classifier now recognizes only that exact observed canonical
refusal in addition to the prior exact refusal set. One winner, one rejection,
one planner/submission/POST, completion, replay and original readback remain
mandatory. Duplicate or unrelated outcomes still FAIL. Closed public diagnostics
expose only bounded enums/counts. The optional controlled fixture calls original
preflight and does not alter the normal matrix or product controller/deadlines.

Prior actual TDE39016840030 is assessment FAIL/repository FAILED, not PASS:
703OPEN/65CRITICAL/638HIGH. One new own qualifier.run complexity26 was removed by
helper extraction using the same radon6.0.1 analyzer; run now7, helpers≤8.
Legacy qualifier _phase32/main64 remain unchanged, concurrent helper30→25.
No policy, threshold, suppression or waiver was introduced. Original findings
and all cancelled/failed attempts remain retained separately.

## Qualified implementation and normal protected delivery

[Implementation PR299](https://github.com/pcvantol/forge/pull/299) normally
protected-squash-merged at2026-10-17T11:14:01Z to
44300fe7739c7c3ce7d1b4b7a7f7dca569316c04. Exact reviewed head
dfc1f1dcb321088be0be137a566f1bf8d6a812ea and actual protected main share
treeaa8103bad189eb37ac9f426f02a332606e4fc166. Active strict ruleset21986307
required the PR, resolved conversations and Test and static validation, with
zero bypass actors. Normal merge bound the exact expected head; source and
primary checkout history and all retained branches remain intact.

[Complete current CI39023848383](https://github.com/pcvantol/forge/actions/runs/39023848383)
SUCCESS:1659 canonical tests in1842.956s, five existing Linux/profile skips;
all ordinary installed integration and preservation steps passed. Strict
changed-production executable coverage server_runtime.py789/917=86.04%,
strictly greater than80.2%. CodeQL and canonical product version checks passed.
Actual hosted checkout3bd04e1718d9b9ee45ff0b4e1cc2df3e57cf7814 contains the
reviewed head as parent and has the identical tree verified against main.

[Projectless installed artifact12097409726](https://github.com/pcvantol/forge/actions/runs/39023848383/artifacts/12097409726)
contains four casesPASS and cleanuptrue; actual original ZIP SHA256
178cb7a43dfa3c29f360bc65efdb8f7837fb4d0912a1efb64afc41ea4b8f7487 matches
registry and CRC. Receipt SHA256
1a97382dc812b2472963a6f42919e394848017e50b2d32cdca3d4c3ee2ece878;
ordinary hosted wheel SHA256
1ed0064f7befdd583b6e8756933a0622b2d8b938239467acaef979871064271d.
All346 source/wheel/installed payloads verified. Earlier actual Mac installed
proofs retain their own different wheel/receipt digests; they are not retagged.

[Existing installed successor artifact12098571628](https://github.com/pcvantol/forge/actions/runs/39023848383/artifacts/12098571628)
proves102 scenariosPASS, including one original planner/submission/POST and
completion/replay for concurrent start. ZIP SHA256
30783230138103f8c6a5639222409c8650954fb1326a18e30bbb8872333c6db5.
[Candidate artifact12099400050](https://github.com/pcvantol/forge/actions/runs/39023848383/artifacts/12099400050)
has11 positive casesPASS plus the explicitly expected revoked-grant
negative control and cleanuptrue; ZIP SHA256
8d0d28f8f4cea5aaf1cdf9cea9110a979f5917867ac9e683c2a3876d533d154e.
[Preservation artifact12098593524](https://github.com/pcvantol/forge/actions/runs/39023848383/artifacts/12098593524)
is PRESERVATION_PRODUCER_PASS, seven cases/expected negative/cleanuptrue;
ZIP SHA256c13f4d23cb881defd75eb1941216ddab50275751fa2b0c35a969d895f566c3e2.
Original ZIPs, registry hashes and CRC independently checked.

A separate TDE coverage run39020535592 failed before assessment:1657 tests,
one existing Candidate BUSINESS/crash-after-effect error reading an empty PID
signal file while its writer was open. Original log remains retained; no
assessment was reconstructed. A deterministic paused actual file writer made
that visibility race RED. The test-only correction creates exclusive private
mode0600 pending storage, writes and closes the PID, then atomically publishes
the ready marker. Failure leaves no advertised boundary or pending file.
Two linked regressions GREEN; unchanged canonical boundary predicate, exact
child PID check, crash/kill/recovery and15/20/5-second deadlines. New ordinary
installed Candidate11PASS independently qualifies that correction. Product and
workflow bytes are unchanged by this synchronization repair.

[Current TDE39023848386](https://github.com/pcvantol/forge/actions/runs/39023848386)
ran1659 canonical testsPASS in2841.314s and all four capabilities VALID.
WorkflowSUCCESS is still actual assessmentFAIL/repositoryFAILED/exits2/2:
702OPEN complexity findings,65CRITICAL/637HIGH. The own new harness26 finding
was removed; retained existing debt is not relabelled PASS. No policy change,
suppression, waiver or acceptance/timeout relaxation. Both independent Quality
and Security audited all28 changed-path findings against source context and
found no concrete remaining scoped behavior/security blocker. Twenty-five
records concern unchanged source structures; three modified qualifier functions
remain real OPEN maintainability findings. Actual
[TDE artifact12097814707](https://github.com/pcvantol/forge/actions/runs/39023848386/artifacts/12097814707)
ZIP SHA256b2c8be9fd85e09e643a8d65980162b3140573e9d0098bddac516cf5090329781
matches registry and CRC. Hosted checkout/source/tree binding was verified.

Independent complete source/content and final actual-evidence PREMERGE
ASSURANCE PASS both bind exactdfc1f1d and the above original artifacts/logs,
strict coverage, source/tree/payload identity, negative controls and cleanup.
Own implementation consumed corrections6/installed candidatecycles14 and
Quality7/Security7 calls. All previous failed/superseded attempts, source,
proofs and budgets remain preserved; this Finalization adds its own review
and CI records without reset. Earlier complete CI39020535589 is separately
source-bound SUCCESS1657tests/2798.237s; it does not replace the current result.

## Own finalization and terminal boundary

This document records only actual scoped delivery evidence. Protected own
Finalization, NEW exact-final-main ordinary installed HTTP/restart evidence,
official protected-main release qualification/publication, immutable registry
artifact digests/readback and safe cleanup must all complete before terminal
CLOSED registration. Earlier candidate receipts are not a new final-main proof.
L1 controls its later installer product selection. No automatic successor.
