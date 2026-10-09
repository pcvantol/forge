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
