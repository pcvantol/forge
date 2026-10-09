# Approved workset release V1 — selected L3 r43

Assignment `L3-APPROVED-WORKSET-RELEASE-V1-20261009`; future consumer JOIN
`L3-L4-APPROVED-WORKSET-RELEASE-V1-20261009`. Development checkpoint, not
protected or installed qualification. r42 remains producer-qualified with
shared native UX open. L4's existing Forge2.11.0/1b00c735/schema031/wheel40f
combination and active qualification are unchanged.

## Existing service and bounded delta

| Route | Actual reused service/authority | Selected addition/proof |
| --- | --- | --- |
| Existing owner `/v1/worksets/{id}/propose`, `/decide`, `/arm`, `/disarm` | ApprovedWorklistService, canonical G001, real separate workset decisions | Reuse; never Candidate reapproval or a new scheduler |
| Existing scoped `/v1/worksets`, workset controls | Worklist projection; separate read and hold/unhold grants | Existing permissions stay unchanged |
| New `/v1/approved-workset-releases/capability` GET | Dedicated owner-issued release grant/current actual Solo signer | Explicit scope, finite subjects/actions/expiry/limits |
| New `/prepare` POST | Actual r42 registration/package, Candidate decisions, canonical envelope and original admission | Finite exact order, technical/human effect boundaries and concrete predecessor/order gaps; no effects |
| New `/commands` POST | Durable exact intent, existing workset propose/two decisions/arm or disarm | One explicit confirmed package, immutable original outcome plus current readback |
| New `/operations/{operation_id}` GET | Private scoped intent index plus original canonical workset receipt/projection | Reads never complete pending effects or tick runtime |
| Existing runtime tick | ApprovedWorklistActivation, RuntimeService, canonical Intake, dynamic runtime/real evidence | Original grant rechecked for future activation; real pre-admitted A→B compatibility |

The owner CLI `forge-workset-release-grant` issues/revokes only the distinct
finite release authority over already approved project-bound r42 subjects.
It cannot create or impersonate a role. Normal consumer CLI
`forge-workset-release` uses the same service: capability; prepare by selected
existing Mission IDs, expiry, finite activation limit and progression choice;
release with the previously displayed package and explicit confirmation;
disarm the original workset's future selection; operation current readback.
No user-authored planning JSON is needed for normal selection. Setup is an
owner operation, not implicit expansion of chat/read/hold authority.

## Exact meaning and recovery

A release package binds one installed instance/project/repository, existing
Candidate and subject revisions, original Mission IDs, complete approved
Mission/planning/effect policy, original scope decisions, hard predecessors,
finite expiry/activation ceiling, progression policy and real Solo operator
binding. Order is committed selection, not an inferred dependency. Missing
predecessors are reported rather than added. A new concept revision is outside
an old exact workset. Workset decisions approve membership/order/bounds, never
re-approve Candidate content.

Intent precedes effects. Aliases and restart preserve the original operation,
workset identity, immutable decisions/admissions and consumed ceilings.
Canonical workset arm/disarm and original receipt are saved together; replay
cannot rearm a withdrawn release. Half-completed effects remain pending.
Current authority and subject are checked at every actual mutation and future
activation. Original revoked rights are not restored by read/recovery. An
already active Mission's effects remain subject to existing runtime rules;
disarm does not cancel or undo them. Holds retain their own provenance.

Approved, released, selected, claimed, active, completed and physically
executable remain separate facts. Current blockers/claims/consumption come
from the existing projection. EP resources remain NOT_OBSERVED and
execution_ready=false in this release contract. Reads/prepare/reconnect and
release commands never invoke a provider, Intake, runtime.start or EP.

## Current development evidence

Real isolated HTTP grant/prepare/release/original/current/new-key replay/disarm
and revocation passed, preserving original Candidate decisions/Mission IDs and
zero extra model turns. A real chat-generated A/B plus unapproved C passes the
existing runtime/EP-HTTP simulator chain, authentic source effect evidence,
actual separate final acceptance for A and B, dependency wait and bounded
idle. Only external model/OS/repository/EP transport adapters are synthetic;
canonical governance, registration, admission, claims and runtime are real.

Owning convergence: Python3.14 full1358 tests PASS, one existing skip;
version2.12.0, JSON/projection/whitespace PASS; all11 changed production
files individually >80.2% executable-line coverage. The complete new23-case
matrix includes actual independent-process release/disarm/claim races, ten
crash/lost-response boundaries, grant revocation between decisions and before
start, stable original/current receipts, exact alias capacity, expiry/role/
project/held/order/budget denials and actual corrupted-storage fail-closed
proof. READ_ONLY, documentation and design effects survive actual runtime/EP
requests and source-bound evidence. Legacy source context remains readable;
new release preparation requires a genuine owner-published observation receipt
and never invents its timestamp. All failed/aborted development logs and
historical budget/evidence lineages are preserved.

Still required: exact committed-source/noneditable candidate qualification and
the genuine revoked-positive detector, independent complete exact-head Quality
and Security, required CI, protected implementation/nonempty NO_BUMP
finalization, fresh exact-final-main HTTP/CLI/runtime simulator qualification,
actual main CI/TDE readbacks and safe cleanup. No live EP, signing, paid model
probe, consumer UI, public release, full PRM/F5 or family closure is claimed.


### Independent Security repair round1

The first complete exact-head review on05d1b58377bcbe3f7b65c46ca262a2e7fc0bf6ee
returned Quality PASS / Security FAIL. Both original reports and all prior
qualification attempts are retained. An active alias cannot reauthorize a
revoked original partial release: original intent/grant/signer/project/subjects
are rechecked before journal alias publication and every remaining release
effect. The original Business decision is preserved and no Architecture/arm
is added after revocation. Disarm remains independently authorized.

New `released-` lineage and durable release receipts cannot become legacy by
removing/nulling capability metadata. Projection, claims, start and arm fail
closed; genuine legacy worksets retain compatibility. Actual process-crash /
new active alias and product-generated canonical metadata corruption cases are
included in the mandatory installed matrix, now at least25 cases. A corrected
external concurrency adapter was separately qualified4PASS. The fresh complete
owning gate and installed25/control qualification are running; fresh complete
exact-head Quality/Security, protected merge, finalization and exact-final-main
qualification remain open. No review-budget reset or L4 pin change occurred.


### Required installed legacy hold compatibility repair round2

The old hosted05d1 installed hold gate and fresh local89f7 installed hold
both failed at case43: a previously selected/admitted APPROVED_PLANNABLE
Mission with lost claim-ID correlation must continue after future-only hold.
The original42 successful cases/failure receipts and both prior exact-head
review pairs are retained. Projection now distinguishes genuine selected
claim operation/subject/generation and canonical workset-policy assignment
from mere pre-admission. This preserves ongoing selected work while blocking
unclaimed pre-admitted A/B members. The actual new hold/zero-claim/zero-provider/
zero-EP case is mandatory, raising the selected installed matrix to26.

Formal bounded repairround2 is active; no budget reset, gate relaxation,
Candidate reapproval or L4 pin/scope change. Fresh full owning/source coverage,
installed26/control AND existing43-case hold gate, complete exact-head Q/S,
protected delivery/finalization/final-main remain required.


### Whole-scope Quality budget-readback repair round3

The complete exact2c3e626 review returned Security PASS / Quality FAIL(P2):
projection used the admission fallback as if it were an activation claim for
finite-budget exhaustion. The runtime already denied B correctly, while the
readback could incorrectly report READY after accepted A consumed the one
allowed activation. Both reports and1361/26/43 evidence remain preserved.

An actual separate-process chatA/B release withmaximum_activations1, real A
source evidence and final acceptance reproduced the false READY before the
fix(1FAIL6.540s). Projection now tests the canonical selected claim, preserving
original Mission admissions separately. The exact same test passes after the
fix(1PASS6.608s): A COMPLETE, B APPROVED_PLANNABLE, one claim/provider/EP,
eight genuine governance decisions/two existing admissions, B and continuation
BLOCKED/ACTIVATION_LIMIT_EXHAUSTED. No new activation/budget decision is added.
The required installed matrix minimum is27. Formal bounded repairround3 is
consumed without reset. Fresh full owning/strictcoverage/installed27/control,
complete exact-head Q/S, all existing required CI, protected delivery,
nonemptyNO_BUMP finalization and fresh exact-final-main remain open.


## Protected source and implementation-main completion snapshot

PR267 was ordinarily protected squashmerged at966f24ecf9a7fcf17d28a552795569d0de4397ea
from exact independently Quality/SecurityPASS bbad4934a748b3a9b51cbacf3f9769ae3b0cd34f.
Required hostedCI37934063071 succeeded with every retained installed gate and
the new27-case release/revocation detector. Wholeown1362PASS/oneexisting skip,
all11changedproductionstrict>80.2%, freshcandidateinstalled27/control and
legacyhold43 are exact current evidence. Allthree formal repairs and historical
FAIL/PASS/aborted/cancelled attempts remain preserved, without reset.

A NEW noneditable build/install on the actual committed implementation-main
966f24ec passed27 again, with true original-grant revocation detection and
cleanup. This snapshot is captured in the committed qualification JSON;
implementation-mainCI37939524199 was still running at snapshot publication.
Normal nonemptyNO_BUMP2.12.0 finalization retains the original event lineage.
Actual FINAL-main readback, new clean-source build/install/27/control, current
mainCI/TDE/artifacts and cleanup remain required AFTER protected finalization;
the final SHA is not predicted or represented by this implementation snapshot.

TDEPR37934063184 expired its unchanged15minute observe budget during coverage,
before assessment: cancelled/NOT_ASSESSED, never policyPASS. The historical
r42assessment/policyFAIL remains separate, with no broad remediation or relaxed
budget/profile. L4 remains on2.11.0/1b00c735 and its old schema/wheel/GUI scope;
no liveEP/model-quality/native-consumer/fullPRM claim is made. The separately
selected access-continuity successor remains read-only until r43closure and
its explicit budget disposition; it adds no r43corrective allowance.
